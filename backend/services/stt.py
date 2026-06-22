"""STT streaming a interrupteur — trois moteurs, une seule interface.

  STT_MODE=vosk    -> local (Kaldi). Charge une fois (~1.7s, +150MB), puis
                      transcription en continu avec endpointing integre. Emet
                      des PARTIELS live au fur et a mesure (final=False) puis le
                      texte final (final=True). Aucun reseau.
  STT_MODE=voxtral -> Voxtral Realtime (cloud). Flux audio PCM -> events
                      delta texte ; endpointing via VAD Silero (audio/vad.py).
                      Partiels live aussi.
  STT_MODE=batch   -> Voxtral non-streaming : on collecte N secondes puis 1
                      seule requete. Fallback robuste, jamais de partiels.

Interface preservee (utilisee par main.py.on_wake) :
    STTEngine(on_transcript) ; await start() ; await send_audio(queue, duration_s)
    ; await stop() ; attrs .running .got_final ._client.
on_transcript(text, is_final) : is_final=False = affichage live uniquement,
is_final=True = declenche le routage d'intent cote main.py."""
import asyncio
import inspect
import io
import json
import logging
import os
import time
import wave
from typing import Awaitable, Callable

import httpx

try:
    from config import (MISTRAL_API_KEY, STT_MODE, VOSK_MODEL_PATH,
                        NEMOTRON_ASR_URL, NEMOTRON_ASR_TIMEOUT)
except ImportError:  # pragma: no cover
    MISTRAL_API_KEY = ""
    STT_MODE = "batch"
    VOSK_MODEL_PATH = ""
    NEMOTRON_ASR_URL = ""
    NEMOTRON_ASR_TIMEOUT = 15.0

logger = logging.getLogger(__name__)

try:
    from mistralai import Mistral
    HAS_MISTRAL = True
except ImportError:
    HAS_MISTRAL = False
    logger.warning("[STT] mistralai non disponible")

try:
    import vosk
    vosk.SetLogLevel(-1)  # coupe les logs Kaldi verbeux
    HAS_VOSK = True
except ImportError:
    HAS_VOSK = False

VOXTRAL_RT_MODEL = "voxtral-mini-transcribe-realtime-2602"  # de-risque live (P0)
VOXTRAL_BATCH_MODEL = "voxtral-mini-latest"

# Hallucinations classiques de Voxtral quand l'audio est du bruit/silence (le
# modele "complete" avec des outros YouTube). Filtrees sur le FINAL uniquement.
HALLUCINATIONS = [
    "merci d'avoir regardé", "sous-titres", "sous-titrage", "merci d'avoir écouté",
    "merci de votre attention", "a bientôt", "à bientôt",
    "n'oubliez pas de vous abonner", "abonnez-vous", "like et abonnez",
    "merci à tous", "partager cette vidéo", "réseaux sociaux", "n'hésite pas à",
    "n'hésitez pas à", "laisser un commentaire", "laissez un commentaire",
    "ne manquer aucune", "nouvelles vidéos", "cliquez sur", "clique sur", "la cloche",
]

# --- Cache modele Vosk (charge une seule fois pour tout le process) ---
_VOSK_MODEL = None
_VOSK_LOCK = asyncio.Lock()


async def _get_vosk_model():
    """Charge (une fois) et renvoie le modele Vosk, ou None si indisponible."""
    global _VOSK_MODEL
    if _VOSK_MODEL is not None:
        return _VOSK_MODEL
    if not HAS_VOSK or not VOSK_MODEL_PATH or not os.path.isdir(VOSK_MODEL_PATH):
        return None
    async with _VOSK_LOCK:
        if _VOSK_MODEL is None:
            loop = asyncio.get_event_loop()
            t0 = time.monotonic()
            _VOSK_MODEL = await loop.run_in_executor(None, vosk.Model, VOSK_MODEL_PATH)
            logger.info("[STT] Modele Vosk charge en %.2fs (%s)",
                        time.monotonic() - t0, VOSK_MODEL_PATH)
    return _VOSK_MODEL


async def preload_vosk():
    """Warm-up au demarrage : evite de payer le chargement au 1er wake word.
    En mode nemotron, Vosk sert aussi de moteur de capture/repli -> on le precharge."""
    if STT_MODE in ("vosk", "nemotron"):
        try:
            if await _get_vosk_model() is None:
                logger.warning("[STT] Vosk demande mais modele introuvable (%s)", VOSK_MODEL_PATH)
        except Exception as e:
            logger.error("[STT] Preload Vosk echoue: %s", e)


async def warmup_nemotron():
    """Pre-chauffe Nemotron au boot : la 1ere inference est lente (~13s a froid),
    les suivantes ~0.7s. En envoyant un court audio factice au demarrage, la 1ere
    VRAIE commande est deja rapide. No-op hors mode nemotron. Jamais bloquant."""
    if STT_MODE != "nemotron" or not NEMOTRON_ASR_URL:
        return
    try:
        import numpy as np
        audio = (np.random.randn(8000) * 40).astype(np.int16)  # 0.5s 16kHz tres faible
        wav = io.BytesIO()
        with wave.open(wav, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=httpx.Timeout(60)) as c:
            r = await c.post(
                (NEMOTRON_ASR_URL or "").rstrip("/") + "/v1/transcribe",
                files={"file": ("warmup.wav", wav.getvalue(), "audio/wav")},
                data={"lang": "fr-FR", "strip_lang_tags": "true"},
            )
            r.raise_for_status()
        logger.info("[STT] Nemotron pre-chauffe en %.1fs", time.monotonic() - t0)
    except Exception as e:
        logger.warning("[STT] Pre-chauffe Nemotron echouee (non bloquant): %s", e)


class STTEngine:
    def __init__(self, on_transcript: Callable[[str, bool], Awaitable[None]] | None = None):
        self.on_transcript = on_transcript
        self._client = None
        self.running = False
        self.got_final = False
        self.mode = STT_MODE
        self._consumed = []  # frames audio reellement consommees (fallback batch)
        self._vosk_ok = False  # Vosk dispo (partiels + repli) en mode nemotron
        self._nemo_url = (NEMOTRON_ASR_URL or "").rstrip("/")

    async def start(self):
        if HAS_MISTRAL and MISTRAL_API_KEY:
            self._client = Mistral(api_key=MISTRAL_API_KEY)

        # Determiner le mode effectif (bascule vers un fallback si indispo)
        if self.mode == "nemotron":
            # Nemotron (Mac mini) = STT principal ; Vosk reste le moteur de CAPTURE
            # (partiels live + endpointing) ET le REPLI si Nemotron tombe.
            self._vosk_ok = await _get_vosk_model() is not None
            if not self._nemo_url:
                self.mode = "vosk" if self._vosk_ok else ("batch" if self._client else "mock")
                logger.warning("[STT] Nemotron sans URL -> mode '%s'", self.mode)
            elif not self._vosk_ok:
                logger.warning("[STT] Nemotron actif SANS repli Vosk (modele absent)")
        elif self.mode == "vosk":
            if await _get_vosk_model() is None:
                self.mode = "batch" if self._client else "mock"
                logger.warning("[STT] Vosk indisponible -> mode '%s'", self.mode)
        elif self.mode in ("voxtral", "batch"):
            if not self._client:
                self.mode = "mock"
        else:
            self.mode = "batch" if self._client else "mock"

        logger.info("[STT] Mode actif: %s", self.mode)
        self.running = True

    async def send_audio(self, audio_queue: asyncio.Queue, duration_s: float = 6.0):
        self._consumed = []  # reset : audio reellement lu pendant CE send_audio
        try:
            if self.mode == "nemotron":
                await self._nemotron(audio_queue, duration_s)
            elif self.mode == "vosk":
                await self._stream_vosk(audio_queue, duration_s)
            elif self.mode == "voxtral":
                await self._stream_voxtral(audio_queue, duration_s)
            elif self.mode == "batch":
                await self._batch(audio_queue, duration_s)
            else:
                logger.info("[STT] Mode mock — pas de transcription")
        except Exception as e:
            logger.error("[STT] Erreur mode %s: %s", self.mode, e)
            # Filet de securite : si rien n'a ete emis, retranscrire en batch
            # l'audio DEJA CONSOMME (la queue est videe et la fenetre ecoulee ;
            # relire la queue ne capterait que du bruit post-commande).
            if not self.got_final and self.mode != "batch" and self._client and self._consumed:
                logger.info("[STT] -> fallback batch sur l'audio consomme (%d frames)",
                            len(self._consumed))
                try:
                    import numpy as np
                    audio = np.concatenate(self._consumed)
                    rms = int(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
                    if rms < 500:
                        logger.info("[STT] Audio consomme trop faible (rms=%d), skip", rms)
                    else:
                        text = await self._voxtral_transcribe(audio)
                        await self._emit(text, True)
                except Exception as e2:
                    logger.error("[STT] Fallback batch echoue: %s", e2)

    async def _emit(self, text: str, final: bool):
        """Pousse un partiel (final=False, affichage live) ou le final (routage)."""
        text = (text or "").strip()
        if not final:
            if text and self.on_transcript:
                await self.on_transcript(text, False)
            return
        if not text:
            return
        if any(h in text.lower() for h in HALLUCINATIONS):
            logger.warning("[STT] Hallucination filtree: '%s'", text)
            return
        self.got_final = True
        logger.info("[STT] FINAL: %s", text)
        if self.on_transcript:
            await self.on_transcript(text, True)

    # ------------------------------------------------------------------ Vosk
    async def _collect_vosk(self, audio_queue: asyncio.Queue, duration_s: float) -> str:
        """Streame Vosk : emet les PARTIELS live, fait l'endpointing, bufferise
        l'audio dans self._consumed, et RENVOIE le final Vosk (sans l'emettre) ->
        l'appelant choisit le final a router (Vosk seul, ou texte Nemotron)."""
        import numpy as np
        model = await _get_vosk_model()
        if model is None:
            raise RuntimeError("modele Vosk absent")
        loop = asyncio.get_event_loop()
        rec = vosk.KaldiRecognizer(model, 16000)

        start = time.monotonic()
        last_partial = ""
        spoke = False
        silence_chunks = 0
        SILENCE_RMS = 350        # en dessous = silence
        END_SILENCE_CHUNKS = 18  # ~1.1s de silence apres parole = fin (backstop)

        while self.running and (time.monotonic() - start) < duration_s:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if spoke:
                    break
                continue

            self._consumed.append(chunk)  # buffer (fallback batch / envoi Nemotron)
            # L'audio est continu (arecord stream sans arret) : on detecte la
            # fin de commande via le RMS, en plus de l'endpoint integre de Vosk.
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            silence_chunks = silence_chunks + 1 if rms < SILENCE_RMS else 0

            data = chunk.tobytes()
            is_end = await loop.run_in_executor(None, rec.AcceptWaveform, data)
            if is_end:
                # Result() finalise un segment cote Kaldi -> executor (peut bloquer)
                res = await loop.run_in_executor(None, rec.Result)
                seg = json.loads(res).get("text", "").strip()
                if seg:
                    return seg
            else:
                partial = json.loads(rec.PartialResult()).get("partial", "").strip()
                if partial and partial != last_partial:
                    last_partial = partial
                    spoke = True
                    await self._emit(partial, False)

            if spoke and silence_chunks >= END_SILENCE_CHUNKS:
                break

        # FinalResult() force le vidage/finalisation Kaldi (plusieurs 100 ms sur
        # Pi4) -> executor pour ne pas bloquer l'event loop.
        final_res = await loop.run_in_executor(None, rec.FinalResult)
        final = json.loads(final_res).get("text", "").strip()
        return final or last_partial

    async def _stream_vosk(self, audio_queue: asyncio.Queue, duration_s: float):
        """Mode Vosk pur : capture + emission du final Vosk pour le routage."""
        final = await self._collect_vosk(audio_queue, duration_s)
        await self._emit(final, True)

    # -------------------------------------------------------------- Nemotron ASR
    async def _nemotron(self, audio_queue: asyncio.Queue, duration_s: float):
        """Nemotron ASR (Mac mini) = transcription principale, bien plus precise.
        Vosk assure la CAPTURE (partiels live + endpointing) et le REPLI : on
        bufferise pendant que Vosk affiche les partiels, puis on envoie le buffer a
        Nemotron. Si Nemotron echoue/injoignable -> on emet le final Vosk deja calcule."""
        import numpy as np
        # 1) Capture : Vosk (partiels + endpointing + buffer) si dispo, sinon fenetre simple.
        vosk_final = ""
        if self._vosk_ok:
            try:
                vosk_final = await self._collect_vosk(audio_queue, duration_s)
            except Exception as e:
                logger.warning("[STT] Capture Vosk echouee (%s) -> fenetre simple", e)
                await self._collect_window(audio_queue, duration_s)
        else:
            await self._collect_window(audio_queue, duration_s)

        if not self._consumed:
            logger.info("[STT] Nemotron: pas d'audio collecte")
            return
        audio = np.concatenate(self._consumed)
        rms = int(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
        if rms < 500:
            logger.info("[STT] Audio trop faible (rms=%d), skip", rms)
            if vosk_final:
                await self._emit(vosk_final, True)
            return

        # 2) Transcription Nemotron (precise). Vide/echec -> repli sur le final Vosk.
        text = await self._nemotron_transcribe(audio)
        if text:
            await self._emit(text, True)
        elif vosk_final:
            logger.info("[STT] Nemotron vide/injoignable -> repli Vosk: '%s'", vosk_final)
            await self._emit(vosk_final, True)

    async def _collect_window(self, audio_queue: asyncio.Queue, duration_s: float):
        """Capture simple (sans Vosk) : bufferise jusqu'a ~1.1s de silence apres
        parole, ou duration_s. Pas de partiels. Utilise si Vosk est absent."""
        import numpy as np
        start = time.monotonic()
        spoke = False
        silence_chunks = 0
        SILENCE_RMS = 350
        END_SILENCE_CHUNKS = 18
        while self.running and (time.monotonic() - start) < duration_s:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if spoke:
                    break
                continue
            self._consumed.append(chunk)
            rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            if rms >= SILENCE_RMS:
                spoke = True
                silence_chunks = 0
            elif spoke:
                silence_chunks += 1
            if spoke and silence_chunks >= END_SILENCE_CHUNKS:
                break

    async def _nemotron_transcribe(self, audio: "object") -> str:
        """POST l'audio (int16 16kHz) en WAV multipart a l'API Nemotron LAN (Mac mini,
        POST /v1/transcribe). Renvoie le texte, ou '' si echec/injoignable (le repli
        Vosk prend alors le relais). Ne leve jamais (zero-crash)."""
        if not self._nemo_url:
            return ""
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())
        wav_bytes = wav_buf.getvalue()
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(NEMOTRON_ASR_TIMEOUT)) as c:
                r = await c.post(
                    self._nemo_url + "/v1/transcribe",
                    files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                    data={"lang": "fr-FR", "strip_lang_tags": "true"},
                )
                r.raise_for_status()
                txt = (r.json().get("text") or "").strip()
            logger.info("[STT] Nemotron OK en %.1fs: '%s'", time.monotonic() - t0, txt)
            return txt
        except Exception as e:
            logger.warning("[STT] Nemotron echec (%.1fs): %s", time.monotonic() - t0, e)
            return ""

    # --------------------------------------------------------------- Voxtral RT
    async def _stream_voxtral(self, audio_queue: asyncio.Queue, duration_s: float):
        """Voxtral Realtime : partiels live tant que le modele streame du texte.
        On bufferise l'audio envoye : si le realtime ne renvoie aucun final
        (modele temps-reel parfois muet selon l'audio), on retombe sur une
        transcription batch du buffer — qualite garantie, jamais de regression."""
        import numpy as np
        from mistralai.models import AudioFormat
        from audio.vad import SileroVAD

        vad = SileroVAD()
        start = time.monotonic()
        st = {"spoke": False, "silence_ms": 0, "stop": False}
        sent = self._consumed  # buffer des frames envoyees (= fallback batch instance)
        FRAME = 512
        FRAME_MS = int(FRAME / 16)  # 32 ms
        SPEECH_PROB = 0.5
        END_SILENCE_MS = 700

        async def audio_gen():
            buf = np.zeros(0, dtype=np.int16)
            while self.running and (time.monotonic() - start) < duration_s and not st["stop"]:
                try:
                    chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if st["spoke"]:
                        return
                    continue
                buf = np.concatenate([buf, chunk])
                while len(buf) >= FRAME:
                    frame = buf[:FRAME]
                    buf = buf[FRAME:]
                    if vad.available():
                        if vad.prob(frame) >= SPEECH_PROB:
                            st["spoke"] = True
                            st["silence_ms"] = 0
                        elif st["spoke"]:
                            st["silence_ms"] += FRAME_MS
                    sent.append(frame)
                    yield frame.tobytes()
                    if st["spoke"] and st["silence_ms"] >= END_SILENCE_MS:
                        return

        text_acc = ""
        stream = events = None
        try:
            stream = self._client.audio.realtime.transcribe_stream(
                audio_stream=audio_gen(),
                model=VOXTRAL_RT_MODEL,
                audio_format=AudioFormat(encoding="pcm_s16le", sample_rate=16000),
                target_streaming_delay_ms=300,
            )
            events = await stream if inspect.isawaitable(stream) else stream
            async for ev in events:
                # Les events sont les payloads directement (.type + .text).
                etype = str(getattr(ev, "type", "") or "")
                if etype.endswith("text.delta"):
                    delta = getattr(ev, "text", "") or ""
                    if delta:
                        text_acc += delta
                        await self._emit(text_acc, False)  # partiel live
                elif etype.endswith("done"):
                    final = getattr(ev, "text", None)
                    if final:
                        await self._emit(final, True)
                    st["stop"] = True
                    break
                elif "error" in etype:
                    logger.warning("[STT] Voxtral RT error: %s", getattr(ev, "error", ev))
                    break
        finally:
            st["stop"] = True
            # Relacher la connexion httpx sous-jacente (break/epuisement). Gardes
            # getattr : l'API exacte du SDK peut varier, on ne crashe jamais.
            for obj in (events, stream):
                closer = getattr(obj, "aclose", None) or getattr(obj, "close", None)
                if closer:
                    try:
                        res = closer()
                        if inspect.isawaitable(res):
                            await res
                    except Exception as e:
                        logger.debug("[STT] Fermeture stream Voxtral: %s", e)

        # Le realtime a streame un final ?
        if self.got_final:
            return
        if text_acc.strip():  # deltas mais pas de done.text propre
            await self._emit(text_acc, True)
            return
        # Rien du realtime -> fallback batch sur l'audio bufferise (qualite OK)
        if sent:
            logger.info("[STT] Voxtral RT muet -> fallback batch (%d frames)", len(sent))
            audio = np.concatenate(sent)
            text = await self._voxtral_transcribe(audio)
            await self._emit(text, True)

    async def _voxtral_transcribe(self, audio: "object") -> str:
        """Transcription batch Voxtral d'un tableau int16 16kHz -> texte."""
        if not self._client:
            return ""
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())
        wav_bytes = wav_buf.getvalue()
        loop = asyncio.get_event_loop()

        def _call():
            return self._client.audio.transcriptions.complete(
                model=VOXTRAL_BATCH_MODEL,
                file={"content": wav_bytes, "file_name": "audio.wav"},
                language="fr",
            )

        result = await loop.run_in_executor(None, _call)
        return (result.text or "").strip()

    # -------------------------------------------------------------- Voxtral batch
    async def _batch(self, audio_queue: asyncio.Queue, duration_s: float):
        import numpy as np
        if not self._client:
            return
        start = time.monotonic()
        all_samples = []
        while self.running and (time.monotonic() - start) < duration_s:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
                all_samples.append(chunk)
            except asyncio.TimeoutError:
                continue

        if not all_samples:
            logger.info("[STT] Pas d'audio collecte")
            return

        audio = np.concatenate(all_samples)
        rms = int(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
        logger.info("[STT] Audio collecte: %.1fs, %d samples, rms=%d",
                    time.monotonic() - start, len(audio), rms)
        if rms < 500:
            logger.info("[STT] Audio trop faible (rms=%d), skip", rms)
            return

        # Rejet de la musique constante (pas de pics de voix)
        chunk_size = 8000  # 500ms @16kHz
        float_audio = audio.astype(np.float32)
        chunk_rms = [np.sqrt(np.mean(float_audio[i:i + chunk_size] ** 2))
                     for i in range(0, len(float_audio) - chunk_size, chunk_size)]
        if chunk_rms:
            ratio = max(chunk_rms) / (min(chunk_rms) or 1)
            logger.info("[STT] Voice ratio: %.1f", ratio)
            if ratio < 1.5:
                logger.info("[STT] Audio constant (musique sans voix), skip")
                return

        logger.info("[STT] Envoi a Voxtral (batch)...")
        text = await self._voxtral_transcribe(audio)
        await self._emit(text, True)

    async def stop(self):
        self.running = False
        # Fermer le client Mistral cree au start() (un par wake) pour ne pas fuir
        # de connexions httpx. Gardes getattr : API SDK variable, jamais de crash.
        client, self._client = self._client, None
        if client is not None:
            closer = getattr(client, "aclose", None) or getattr(client, "close", None)
            if closer:
                try:
                    res = closer()
                    if inspect.isawaitable(res):
                        await res
                except Exception as e:
                    logger.debug("[STT] Fermeture client Mistral: %s", e)
        logger.info("[STT] Arrete")
