import asyncio
import base64
import logging
import tempfile
from pathlib import Path

from audio.output import play_audio_file

# MISTRAL_API_KEY vient de config.py. Import defensif : si config.py n'expose
# pas encore la cle (ancienne version), on retombe sur la variable d'env pour
# ne jamais casser l'import du module au demarrage.
try:
    from config import MISTRAL_API_KEY
except ImportError:  # pragma: no cover
    import os
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

try:
    from config import TTS_PROVIDER
except ImportError:  # pragma: no cover
    import os
    TTS_PROVIDER = os.getenv("TTS_PROVIDER", "gateway")

from services.gateway import GatewayClient

try:
    from admin.config_manager import config as admin_config
except ImportError:
    admin_config = None

logger = logging.getLogger(__name__)

# SDK Mistral (Voxtral TTS). Absent en dev Mac -> mode degrade gere proprement.
try:
    from mistralai import Mistral
    HAS_MISTRAL = True
except ImportError:
    HAS_MISTRAL = False
    logger.warning("[TTS] mistralai non disponible")

# Piper (TTS local de secours). Charge une seule fois au start().
try:
    from piper import PiperVoice, SynthesisConfig
    HAS_PIPER = True
except ImportError:
    HAS_PIPER = False
    logger.warning("[TTS] piper non disponible")

# Modeles / presets Voxtral TTS (admin-overridables via la section "tts").
# NB : le SDK Mistral 1.12.4 n'expose PAS audio.speech -> on appelle l'endpoint
# REST /v1/audio/speech directement en httpx (verifie live sur le Pi).
# voice_id est OBLIGATOIRE (None -> 400, 'default' -> 404). Pas de voix FR
# preset cote Mistral : on prend une voix neutre, le francais est rendu par le
# modele multilingue. Pour une vraie voix FR locale, basculer provider='piper'.
MISTRAL_TTS_URL = "https://api.mistral.ai/v1/audio/speech"
DEFAULT_TTS_MODEL = "voxtral-mini-tts-latest"
DEFAULT_TTS_VOICE = "en_paul_neutral"
# Voix Voxtral MLX cote passerelle (chemin nominal local). Distincte de
# DEFAULT_TTS_VOICE (preset cloud) car les presets cloud sont invalides gateway.
DEFAULT_GATEWAY_VOICE = "fr_female"

# Voix Piper locale (le .onnx.json se trouve a cote du .onnx). Chemin DERIVE de la
# racine du repo (<repo>/voices/…), plus de /home/... code en dur. Surchargeable
# via config.json tts.piper_voice_path.
PIPER_VOICE_PATH = str(Path(__file__).resolve().parent.parent.parent / "voices" / "fr_FR-siwis-medium.onnx")


def _get_provider() -> str:
    """Provider TTS actif : 'gateway' (Voxtral MLX local Mac mini, defaut) |
    'voxtral' (cloud Mistral) | 'piper' (local Pi). Surchargeable via l'admin."""
    if admin_config:
        return admin_config.get("tts", "provider", TTS_PROVIDER)
    return TTS_PROVIDER


def _get_tts_model() -> str:
    if admin_config:
        return admin_config.get("tts", "model", DEFAULT_TTS_MODEL)
    return DEFAULT_TTS_MODEL


def _get_tts_voice() -> str:
    if admin_config:
        return admin_config.get("tts", "voice", DEFAULT_TTS_VOICE)
    return DEFAULT_TTS_VOICE


def _get_piper_voice_path() -> str:
    if admin_config:
        return admin_config.get("tts", "piper_voice_path", PIPER_VOICE_PATH)
    return PIPER_VOICE_PATH


def _get_gateway_voice() -> str:
    """Voix Voxtral MLX cote passerelle (chemin nominal). Defaut 'fr_female' :
    les presets Voxtral cloud (tts.voice='en_paul_neutral') ne sont PAS valides
    pour la gateway, on garde donc une cle dediee surchargeable via l'admin."""
    if admin_config:
        return admin_config.get("tts", "gateway_voice", DEFAULT_GATEWAY_VOICE)
    return DEFAULT_GATEWAY_VOICE


class TTSEngine:
    def __init__(self):
        # Client Mistral (Voxtral TTS cloud) — moteur de secours.
        self._client = None
        # Voix Piper chargee une fois — moteur de secours local.
        self._piper = None
        # Passerelle Mac mini (Voxtral MLX local) — moteur principal gratuit.
        self._gw = GatewayClient()

    async def start(self):
        if _get_provider() == "gateway" and self._gw.available():
            logger.info("[TTS] Provider = gateway local (%s)", self._gw.url)
        # Moteur de secours cloud : Voxtral TTS via le SDK Mistral.
        if HAS_MISTRAL and MISTRAL_API_KEY:
            self._client = Mistral(api_key=MISTRAL_API_KEY)
            logger.info("[TTS] Client Mistral (Voxtral TTS) initialise")
        else:
            logger.info("[TTS] Voxtral indisponible (pas de cle API)")

        # Moteur de secours : Piper local, charge une seule fois.
        if HAS_PIPER:
            voice_path = _get_piper_voice_path()
            if Path(voice_path).exists():
                try:
                    loop = asyncio.get_event_loop()
                    self._piper = await loop.run_in_executor(
                        None, PiperVoice.load, voice_path
                    )
                    logger.info("[TTS] Voix Piper chargee (%s)", voice_path)
                except Exception as e:
                    logger.error("[TTS] Erreur chargement Piper: %s", e)
            else:
                logger.info("[TTS] Voix Piper introuvable (%s)", voice_path)

        # Aucun moteur disponible -> mode mock.
        if not self._client and not self._piper:
            logger.info("[TTS] Mode mock (aucun moteur disponible)")

    async def speak(self, text: str, duck_callback=None):
        # duck_callback conserve dans la signature mais inutilise :
        # le ducking est desactive (TTS et musique partagent la sortie AirPlay).
        provider = _get_provider()
        gw_on = provider == "gateway" and self._gw.available()

        if not self._client and not self._piper and not gw_on:
            logger.info("[TTS] Mock: '%s'", text[:60])
            return

        wav_bytes = None

        if gw_on:
            # Principal GRATUIT : Voxtral MLX local (Mac mini). Secours -> Piper -> Voxtral cloud.
            wav_bytes = await self._synth_gateway(text)
            if wav_bytes is None and self._piper:
                logger.info("[TTS] Passerelle KO -> Piper (secours local)")
                wav_bytes = await self._synth_piper(text)
            if wav_bytes is None and self._client:
                logger.info("[TTS] Passerelle KO -> Voxtral cloud (secours)")
                wav_bytes = await self._synth_voxtral(text)
        elif provider == "piper" and self._piper:
            # Provider 'piper' force -> on saute Voxtral directement.
            wav_bytes = await self._synth_piper(text)
        else:
            # 'voxtral' : Voxtral cloud en principal, Piper en secours sur erreur.
            if self._client:
                wav_bytes = await self._synth_voxtral(text)
            if wav_bytes is None and self._piper:
                logger.info("[TTS] Bascule sur Piper (secours local)")
                wav_bytes = await self._synth_piper(text)

        if not wav_bytes:
            logger.error("[TTS] Aucun audio genere")
            return

        # Ecrit le WAV en fichier temporaire et le joue via la chaine existante
        # (paplay/mpv -> AirPlay -> Devialet). Nettoyage apres lecture.
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp_path = f.name
            logger.info("[TTS] Lecture audio (%d bytes)", len(wav_bytes))
            await play_audio_file(tmp_path)
        except Exception as e:
            logger.error("[TTS] Erreur lecture: %s", e)
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    async def _synth_gateway(self, text: str) -> bytes | None:
        """Synthese via la passerelle Mac mini (Voxtral 4B MLX local, voix
        _get_gateway_voice() defaut fr_female). Renvoie le WAV 24 kHz, ou None
        si la passerelle est injoignable (-> secours)."""
        try:
            wav = await self._gw.tts(text, voice=_get_gateway_voice())
            if wav and len(wav) > 44:  # > en-tete WAV
                return wav
            logger.error("[TTS] Passerelle: WAV vide")
            return None
        except Exception as e:
            logger.error("[TTS] Erreur passerelle: %s", e)
            return None

    async def _synth_voxtral(self, text: str) -> bytes | None:
        """Synthese via Voxtral TTS — endpoint REST /v1/audio/speech (httpx async).

        Le SDK Mistral 1.12.4 n'a pas de methode audio.speech : on POST le JSON
        directement. La reponse est {"audio_data": "<wav base64>"} -> on decode.
        None si erreur (la chaine speak() bascule alors sur Piper).
        """
        import httpx
        try:
            payload = {
                "model": _get_tts_model(),
                "input": text,
                "voice_id": _get_tts_voice(),
                "response_format": "wav",
            }
            headers = {
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                resp = await client.post(MISTRAL_TTS_URL, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error("[TTS] Voxtral HTTP %d: %s", resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            # {"audio_data": "<wav base64>"}
            return base64.b64decode(data["audio_data"])
        except Exception as e:
            logger.error("[TTS] Erreur Voxtral: %s", e)
            return None

    async def _synth_piper(self, text: str) -> bytes | None:
        """Synthese via Piper local (synth bloquante -> executor). None si erreur."""
        if not self._piper:
            return None
        try:
            import wave
            loop = asyncio.get_event_loop()

            def _call():
                # Piper ecrit un WAV 22050 Hz mono int16 dans un fichier temp.
                fd = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                fd.close()
                try:
                    with wave.open(fd.name, "wb") as wf:
                        self._piper.synthesize_wav(
                            text, wf, syn_config=SynthesisConfig(length_scale=1.0)
                        )
                    return Path(fd.name).read_bytes()
                finally:
                    Path(fd.name).unlink(missing_ok=True)

            return await loop.run_in_executor(None, _call)
        except Exception as e:
            logger.error("[TTS] Erreur Piper: %s", e)
            return None
