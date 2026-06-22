import logging
import re

# MISTRAL_API_KEY n'est peut-etre pas encore declare dans config.py : import defensif
# pour ne jamais crasher la boucle principale (fallback sur la variable d'environnement).
try:
    from config import MISTRAL_API_KEY
except ImportError:  # pragma: no cover
    import os
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")

try:
    from config import LLM_PROVIDER
except ImportError:  # pragma: no cover
    import os
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gateway")

from services.gateway import GatewayClient

logger = logging.getLogger(__name__)

# Correspondance intentions passerelle (Ollama) -> outils du Pi (TOOL_DISPATCH).
# Le routeur local renvoie un vocabulaire restreint ; on le mappe sur les outils
# existants. Le reste (chat.small_answer, unknown, timer...) -> reponse texte.
_GW_INTENT_TO_TOOL = {
    "music.play":       ("play_music",   lambda e: {"query": e.get("query", "")}),
    "music.pause":      ("pause_music",  lambda e: {}),
    "music.next":       ("next_track",   lambda e: {}),
    "music.volume_set": ("set_volume",   lambda e: {"level": e.get("volume", e.get("level", ""))}),
    "home.light_on":    ("guinguette_on", lambda e: {}),
    "home.light_off":   ("guinguette_off", lambda e: {}),
}

try:
    from mistralai import Mistral
    HAS_MISTRAL = True
except ImportError:
    HAS_MISTRAL = False
    logger.warning("[LLM] mistralai non disponible")

try:
    from admin.config_manager import config as admin_config
except ImportError:
    admin_config = None

# Modeles Mistral utilises (juin 2026)
MODEL_FAST = "ministral-8b-latest"      # rapide/economique : normalize, extraction, playlist
DEFAULT_LLM_MODEL = "mistral-small-latest"  # cerveau conversationnel FR par defaut

# Prompt systeme par defaut, PAR LANGUE et DE-PERSONNALISE (aucun lieu code en dur).
# La langue vient de config ui.locale ; un prompt custom (config llm.system_prompt)
# reste prioritaire s'il est renseigne.
LOCALE_PROMPTS = {
    "fr": ("Tu es PI-Board, un assistant vocal de salon. Tu reponds de maniere concise "
           "et naturelle EN FRANCAIS (1-2 phrases max, lues a voix haute). Tu es "
           "sympathique et utile, et tu tutoies l'utilisateur."),
    "en": ("You are PI-Board, a living-room voice assistant. Answer concisely and "
           "naturally IN ENGLISH (1-2 sentences max, they are read aloud). Be friendly "
           "and helpful."),
}
DEFAULT_SYSTEM_PROMPT = LOCALE_PROMPTS["fr"]  # compat ascendante


def _locale() -> str:
    """Langue de l'assistant (config ui.locale), 'fr' par defaut. Code ISO 2 lettres."""
    if admin_config:
        return (admin_config.get("ui", "locale", "fr") or "fr").strip().lower()[:2]
    return "fr"


def _get_system_prompt() -> str:
    # Prompt personnalise par l'utilisateur prioritaire ; sinon prompt de la langue.
    if admin_config:
        custom = (admin_config.get("llm", "system_prompt", "") or "").strip()
        if custom:
            return custom
    return LOCALE_PROMPTS.get(_locale(), LOCALE_PROMPTS["fr"])


def _get_llm_model() -> str:
    if admin_config:
        return admin_config.get("llm", "model", DEFAULT_LLM_MODEL)
    return DEFAULT_LLM_MODEL


def _get_max_tokens() -> int:
    if admin_config:
        return admin_config.get("llm", "max_tokens", 200)
    return 200


def _strip_code_fence(text: str) -> str:
    """Retire d'eventuelles balises markdown ```...``` (mono-ligne ou multi-ligne).

    Robuste au cas ```{...}``` sur une seule ligne (sans saut de ligne) : \\s*
    consomme le newline optionnel, contrairement a un split('\\n') qui leverait
    IndexError.
    """
    text = re.sub(r'^```[a-zA-Z]*\s*', '', text.strip())
    text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()


def _coerce_songs(songs: list) -> list[str]:
    """Force une liste arbitraire en liste de strings 'Artiste - Titre' (max 15).

    Le LLM peut renvoyer des dicts {artist,title} au lieu de strings : on les
    reconstruit au lieu de les laisser fuiter (la signature promet list[str]).
    """
    out: list[str] = []
    for item in songs:
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s)
        elif isinstance(item, dict):
            artist = (item.get("artist") or item.get("Artiste") or "").strip()
            title = (item.get("title") or item.get("Titre")
                     or item.get("song") or "").strip()
            if artist and title:
                out.append(f"{artist} - {title}")
            elif title:
                out.append(title)
            elif artist:
                out.append(artist)
    return out[:15]


class LLMHandler:
    def __init__(self):
        self._client = None
        self._gw = GatewayClient()

    def _use_gateway(self) -> bool:
        """Cerveau local (Ollama via passerelle) actif et joignable ?"""
        return LLM_PROVIDER == "gateway" and self._gw.available()

    async def start(self):
        if self._use_gateway():
            logger.info("[LLM] Provider = gateway local (%s)", self._gw.url)
        if not HAS_MISTRAL or not MISTRAL_API_KEY:
            if not self._use_gateway():
                logger.info("[LLM] Mode mock (pas de cle API ni passerelle)")
            return
        # Client Mistral conserve comme fallback (si la passerelle tombe).
        self._client = Mistral(api_key=MISTRAL_API_KEY)
        logger.info("[LLM] Client Mistral initialise%s",
                    " (fallback)" if self._use_gateway() else "")

    async def normalize_music_query(self, raw_query: str) -> str:
        """Nettoie une requete musicale issue de la transcription STT via le LLM."""
        # En mode passerelle : on NE reveille PAS le 9B local pour ca (reactivite).
        # Deezer tolere le fuzzy ; la requete part telle quelle -> musique instantanee.
        if self._use_gateway():
            return raw_query
        if not self._client:
            return raw_query

        try:
            response = await self._client.chat.complete_async(
                model=MODEL_FAST,
                max_tokens=50,
                temperature=0,
                messages=[
                    {"role": "system", "content": (
                        "Tu recois une transcription vocale approximative d'une demande de musique. "
                        "Extrais et corrige le nom de l'artiste et/ou du morceau. "
                        "Reponds UNIQUEMENT avec la requete corrigee pour la recherche musicale, rien d'autre. "
                        "Exemples:\n"
                        "- 'mais de la musique par singuina' -> 'Singuila'\n"
                        "- 'joue du jazz' -> 'jazz'\n"
                        "- 'mets un son de dadou' -> 'Dadju'\n"
                        "- 'lance singula rossignol' -> 'Singuila Rossignol'\n"
                        "- 'mais par fin d'hier' -> 'Singuila'\n"
                        "- 'mis de la musique a Henri Salvador' -> 'Henri Salvador'\n"
                    )},
                    {"role": "user", "content": raw_query},
                ],
            )
            cleaned = response.choices[0].message.content.strip().strip('"\'')
            logger.info("[LLM] Normalize: '%s' -> '%s'", raw_query, cleaned)
            return cleaned
        except Exception as e:
            logger.error("[LLM] Normalize error: %s", e)
            return raw_query

    _IDENTIFY_SYSTEM = (
        "L'utilisateur decrit une chanson par ses paroles ou une description. "
        "Identifie la chanson. Prends en compte le genre musical mentionne. "
        "Reponds UNIQUEMENT avec 'Artiste - Titre' ou 'inconnu'."
    )

    async def identify_song(self, lyrics_hint: str) -> str | None:
        """Identifie une chanson via recherche web DuckDuckGo + extraction LLM.

        Mistral n'a pas de web_search hebergee : on s'appuie donc sur la recherche
        DuckDuckGo locale puis on extrait 'Artiste - Titre' avec ministral-8b.
        """
        # Cerveau LOCAL : extraction via la passerelle (la recherche web
        # DuckDuckGo reste reservee a Mistral). Sans cle Mistral, c'est le seul
        # chemin disponible pour MUSIC_FIND.
        if self._use_gateway():
            try:
                txt = await self._gw.complete(self._IDENTIFY_SYSTEM, lyrics_hint,
                                              max_tokens=80, temperature=0)
                result = (txt or "").strip().strip('"\'')
                if result and result.lower() != "inconnu":
                    logger.info("[LLM] (gateway) Song identified: '%s' -> '%s'",
                                lyrics_hint[:40], result)
                    return result
            except Exception as e:
                logger.error("[LLM] gateway identify err: %s", e)
            if not self._client:
                return None

        if not self._client:
            return None

        # Recherche web (DuckDuckGo) + extraction par le LLM
        result = await self._web_search_song(lyrics_hint)
        if result:
            return result

        # Fallback : connaissance du modele seule (sans recherche web)
        try:
            response = await self._client.chat.complete_async(
                model=MODEL_FAST,
                max_tokens=80,
                temperature=0,
                messages=[
                    {"role": "system", "content": (
                        "L'utilisateur decrit une chanson par ses paroles ou une description. "
                        "Identifie la chanson. Prends en compte le genre musical mentionne. "
                        "Reponds UNIQUEMENT avec 'Artiste - Titre' ou 'inconnu'."
                    )},
                    {"role": "user", "content": lyrics_hint},
                ],
            )
            result = response.choices[0].message.content.strip().strip('"\'')
            if result.lower() == "inconnu":
                return None
            logger.info("[LLM] Song identified (LLM): '%s' -> '%s'", lyrics_hint[:40], result)
            return result
        except Exception as e:
            logger.error("[LLM] Identify song error: %s", e)
            return None

    async def _web_search_song(self, query: str) -> str | None:
        """Cherche une chanson via DuckDuckGo + extraction LLM."""
        import asyncio, urllib.parse
        try:
            # Recherche HTML DuckDuckGo (pas de cle API, pas de blocage)
            search_q = urllib.parse.quote(f'paroles "{query}" chanson artiste')
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "-L", "--max-time", "8",
                f"https://html.duckduckgo.com/html/?q={search_q}",
                "-H", "User-Agent: Mozilla/5.0 (X11; Linux aarch64)",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
            except asyncio.TimeoutError:
                # Tuer + recolter curl pour ne pas laisser de process orphelin.
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
                logger.warning("[LLM] Web search timeout (curl tue)")
                return None
            html = stdout.decode(errors="ignore")

            if not self._client or len(html) < 200:
                return None

            # Extraction du texte visible des resultats
            import re
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text)[:4000]

            response = await self._client.chat.complete_async(
                model=MODEL_FAST,
                max_tokens=50,
                temperature=0,
                messages=[
                    {"role": "system", "content": (
                        "Voici les resultats d'une recherche web pour identifier une chanson a partir de ses paroles. "
                        "Extrais le nom de l'artiste et le titre de la chanson trouvee. "
                        "Reponds UNIQUEMENT avec 'Artiste - Titre' ou 'inconnu'."
                    )},
                    {"role": "user", "content": f"Paroles recherchees: {query}\n\nResultats:\n{text}"},
                ],
            )
            result = response.choices[0].message.content.strip().strip('"\'')
            if result.lower() != "inconnu" and "-" in result:
                logger.info("[LLM] Song identified (web): '%s' -> '%s'", query[:40], result)
                return result
        except Exception as e:
            logger.warning("[LLM] Web search failed: %s", e)
        return None

    _PLAYLIST_SYSTEM = (
        "Tu es un DJ expert. L'utilisateur te demande une playlist. "
        "Reponds UNIQUEMENT avec un objet JSON contenant une cle 'songs' "
        "dont la valeur est une liste de 12 morceaux. "
        "Chaque element est une string 'Artiste - Titre'. "
        "Choisis des morceaux varies, connus, qui correspondent parfaitement a la demande. "
        "Pas de commentaires, pas d'explication, juste le JSON.\n"
        'Exemple: {"songs": ["Marvin Gaye - Let\'s Get It On", "Barry White - Can\'t Get Enough"]}'
    )

    @staticmethod
    def _parse_playlist(text: str) -> list[str]:
        import json
        text = _strip_code_fence(text)
        data = json.loads(text)
        if isinstance(data, dict):
            songs = data.get("songs") or next(
                (v for v in data.values() if isinstance(v, list)), [])
        else:
            songs = data
        return _coerce_songs(songs) if isinstance(songs, list) else []

    async def generate_playlist(self, prompt: str) -> list[str]:
        """Demande au LLM de generer une playlist de titres pour une ambiance/theme."""
        # Cerveau LOCAL : completion JSON via la passerelle (Ollama mode json).
        if self._use_gateway():
            try:
                txt = await self._gw.complete(self._PLAYLIST_SYSTEM, prompt,
                                              max_tokens=500, temperature=0.8, json_mode=True)
                songs = self._parse_playlist(txt)
                logger.info("[LLM] (gateway) Playlist: %d morceaux pour '%s'", len(songs), prompt[:40])
                if songs:
                    return songs
            except Exception as e:
                logger.error("[LLM] gateway playlist err: %s", e)
            if not self._client:
                return []

        if not self._client:
            return []
        try:
            response = await self._client.chat.complete_async(
                model=MODEL_FAST,
                max_tokens=500,
                temperature=0.8,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": (
                        "Tu es un DJ expert. L'utilisateur te demande une playlist. "
                        "Reponds UNIQUEMENT avec un objet JSON contenant une cle 'songs' "
                        "dont la valeur est une liste de 12 morceaux. "
                        "Chaque element est une string 'Artiste - Titre'. "
                        "Choisis des morceaux varies, connus, qui correspondent parfaitement a la demande. "
                        "Pas de commentaires, pas d'explication, juste le JSON.\n"
                        "Exemple de reponse:\n"
                        '{"songs": ["Marvin Gaye - Let\'s Get It On", "Barry White - Can\'t Get Enough"]}'
                    )},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content.strip()
            # Parse JSON
            import json
            # Securite : retire d'eventuelles balises markdown
            text = _strip_code_fence(text)
            data = json.loads(text)
            # response_format json_object impose un objet : on en extrait la liste
            if isinstance(data, dict):
                songs = data.get("songs") or next(
                    (v for v in data.values() if isinstance(v, list)), []
                )
            else:
                songs = data
            if isinstance(songs, list):
                songs = _coerce_songs(songs)
                logger.info("[LLM] Playlist: %d morceaux pour '%s'", len(songs), prompt[:40])
                return songs
        except Exception as e:
            logger.error("[LLM] Playlist error: %s", e)
        return []

    async def route_with_tools(self, text: str, tools: list, context: str = "") -> dict:
        """Routage par function-calling : Mistral choisit un OUTIL ou repond en texte.

        Utilise ministral-8b (rapide, suffisant pour le routing d'intent — verifie
        live). Retourne {"tool": nom, "args": {...}} si un outil est appele, sinon
        {"text": "..."} pour une reponse conversationnelle. Jamais d'exception
        remontee : sur erreur on bascule sur une reponse texte (self.ask).
        """
        # Cerveau LOCAL : routeur d'intentions Ollama via la passerelle.
        if self._use_gateway():
            try:
                obj = await self._gw.intent(text)
                intent = obj.get("intent", "unknown")
                ent = obj.get("entities", {}) or {}
                if intent in _GW_INTENT_TO_TOOL:
                    name, argf = _GW_INTENT_TO_TOOL[intent]
                    logger.info("[LLM] gateway intent %s -> %s", intent, name)
                    return {"tool": name, "args": argf(ent)}
                return {"text": (obj.get("speak") or "").strip()
                        or "Desole, je n'ai pas bien compris."}
            except Exception as e:
                logger.error("[LLM] gateway intent err: %s", e)
                if not self._client:
                    return {"text": await self.ask(text, context)}
                # sinon : on retombe sur le tool-calling Mistral ci-dessous

        if not self._client:
            return {"text": "Je suis en mode test, je ne peux pas repondre pour le moment."}

        system = _get_system_prompt()
        if context:
            system += "\n\n" + context
        system += (
            "\n\nSi la demande correspond a une action disponible (musique, meteo, "
            "video YouTube, volets, portail, guinguette, volume), appelle l'outil adapte. "
            "Sinon, reponds normalement en une phrase courte."
        )

        try:
            response = await self._client.chat.complete_async(
                model=MODEL_FAST,
                max_tokens=_get_max_tokens(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                tools=tools,
                tool_choice="auto",
            )
            msg = response.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                tc = tool_calls[0]
                import json
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                logger.info("[LLM] Tool call: %s(%s)", tc.function.name, args)
                return {"tool": tc.function.name, "args": args}
            return {"text": (msg.content or "").strip()}
        except Exception as e:
            logger.error("[LLM] route_with_tools error: %s", e)
            return {"text": await self.ask(text, context)}

    async def ask(self, user_message: str, context: str = "") -> str:
        # Cerveau LOCAL : reponse conversationnelle courte via la passerelle.
        if self._use_gateway():
            try:
                txt = await self._gw.chat(user_message)
                if txt:
                    logger.info("[LLM] (gateway) Reponse: %s", txt[:80])
                    return txt
            except Exception as e:
                logger.error("[LLM] gateway chat err: %s", e)
            if not self._client:
                return "Desole, je n'ai pas pu traiter ta demande."

        if not self._client:
            return "Je suis en mode test, je ne peux pas repondre pour le moment."

        system = _get_system_prompt()
        if context:
            system += "\n\n" + context

        try:
            response = await self._client.chat.complete_async(
                model=_get_llm_model(),
                max_tokens=_get_max_tokens(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
            )
            text = response.choices[0].message.content
            logger.info("[LLM] Reponse: %s", text[:80])
            return text
        except Exception as e:
            logger.error("[LLM] Erreur: %s", e)
            return "Desole, je n'ai pas pu traiter ta demande."
