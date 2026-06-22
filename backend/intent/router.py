import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

INTENT_KEYWORDS = {
    # Music playback
    "MUSIC_PLAY": ["mets", "joue", "lance", "musique", "ecouter", "écouter"],
    "MUSIC_PAUSE": ["pause", "stop", "arrete", "arrête", "stoppe", "tais-toi", "tais toi",
                     "chut", "silence", "la ferme", "suffit", "ca suffit", "ça suffit"],
    "MUSIC_RESUME": ["reprends", "continue", "relance", "remets", "remet", "encore", "repart"],
    "MUSIC_NEXT": ["suivant", "suivante", "passe", "skip", "prochaine", "change",
                    "autre chose", "j'aime pas", "c'est nul", "pas ca", "pas ça"],
    "MUSIC_PREV": ["precedent", "précédent", "precedente", "précédente", "reviens",
                    "avant", "d'avant", "la derniere", "la dernière"],
    # Volume
    "MUSIC_VOLUME_UP": ["plus fort", "monte le son", "augmente", "monte le volume",
                         "plus haut", "plus de son", "monte"],
    "MUSIC_VOLUME_DOWN": ["moins fort", "baisse le son", "diminue", "baisse le volume",
                           "baisser le son", "baisser", "plus bas", "plus doucement",
                           "plus doux", "doucement", "trop fort"],
    "MUSIC_VOLUME_SET": ["volume a", "volume à", "volume au", "son a", "son à",
                          "mets le volume", "mets le son", "pourcent", "%"],
    "MUSIC_MUTE": ["coupe le son", "mute", "muet", "couper le son"],
    "MUSIC_UNMUTE": ["remet le son", "remets le son", "unmute", "du son"],
    # Music info / search
    "MUSIC_WHAT": ["c'est quoi", "c'est qui", "quel morceau", "quelle chanson",
                    "qui chante", "quel artiste", "quel titre", "c'est quel"],
    "MUSIC_FIND": ["trouve moi", "trouve-moi", "cherche moi", "cherche-moi",
                    "la chanson qui dit", "la musique qui dit", "qui fait", "le morceau qui", "le son qui",
                    "je recherche", "je me souviens plus", "je me rappelle plus", "ça fait", "ça dit",
                    "comment s'appelle", "comment elle s'appelle"],
    "MUSIC_PLAYLIST": ["playlist", "ma playlist", "mes playlists"],
    "MUSIC_AI_MIX": ["fais moi", "fais-moi", "cree moi", "crée moi", "genere", "génère",
                      "fabrique", "fabriquer", "compose", "concocte",
                      "ambiance", "mix de", "selection de", "sélection de",
                      "compile", "propose moi", "propose-moi",
                      "prepare", "prépare", "liste de lecture",
                      "les meilleur", "qui ont marqué", "pour se motiver",
                      "top", "classement", "les plus",
                      "playlist de", "playlist pour"],
    # YouTube
    "YOUTUBE_PLAY": ["youtube", "video", "vidéo", "regarde", "montre", "clip",
                      "dessin anime", "dessin animé", "épisode", "episode"],
    "YOUTUBE_STOP": ["ferme la video", "ferme la vidéo", "quitte", "stop video",
                      "stop vidéo", "arrete la video", "arrête la vidéo"],
    # Weather
    "WEATHER": ["meteo", "météo", "temps qu'il fait", "temperature", "température",
                 "pluie", "soleil", "temps dehors", "quel temps", "fait il beau",
                 "fait-il beau", "pleut", "il pleut"],
    # System
    "SLEEP": ["dodo", "dort", "dors", "eteins", "éteins", "bonne nuit", "nuit",
              "au revoir", "a demain", "à demain"],
    "WAKE": ["reveille", "réveille", "allume", "debout", "leve", "lève", "bonjour"],
    "TIME": ["heure", "quelle heure"],
    "REPEAT": ["repete", "répète", "redis", "repeter", "répéter", "redit"],
    "CANCEL": ["annule", "non merci", "rien", "laisse tomber", "oublie"],
    "TIMER": ["minuteur", "timer", "chrono", "rappelle moi dans", "dans minutes"],
    # Domotique
    "DOMOTIQUE_VOLETS_OPEN": ["ouvre les volets", "ouvrir les volets", "leve les volets", "lève les volets",
                               "monte les volets"],
    "DOMOTIQUE_VOLETS_CLOSE": ["ferme les volets", "fermer les volets", "baisse les volets",
                                "descends les volets"],
    "DOMOTIQUE_PORTAIL": ["ouvre le portail", "ouvrir le portail", "ferme le portail",
                           "fermer le portail", "portail"],
    "DOMOTIQUE_GUINGUETTE_ON": ["allume la guinguette", "allumer la guinguette"],
    "DOMOTIQUE_GUINGUETTE_OFF": ["eteins la guinguette", "éteins la guinguette",
                                  "eteindre la guinguette", "éteindre la guinguette"],
    # Social
    "GREETING": ["bonjour", "salut", "coucou", "hello", "hey"],
    "THANKS": ["merci", "super", "genial", "génial", "parfait", "cool", "top"],
}

# Control intents have priority over content intents when both match
PRIORITY_INTENTS = {
    "MUSIC_VOLUME_DOWN", "MUSIC_VOLUME_UP", "MUSIC_VOLUME_SET",
    "MUSIC_MUTE", "MUSIC_UNMUTE",
    "MUSIC_NEXT", "MUSIC_PREV", "MUSIC_PAUSE", "MUSIC_RESUME",
    "MUSIC_WHAT", "YOUTUBE_STOP", "CANCEL", "REPEAT", "TIME",
    "GREETING", "THANKS",
    "DOMOTIQUE_VOLETS_OPEN", "DOMOTIQUE_VOLETS_CLOSE",
    "DOMOTIQUE_PORTAIL", "DOMOTIQUE_GUINGUETTE_ON", "DOMOTIQUE_GUINGUETTE_OFF",
}

# Keywords that should NEVER trigger MUSIC_PLAY (they have "mets" or "musique" but mean something else)
ANTI_PLAY_WORDS = ["plus fort", "moins fort", "monte", "baisse", "volume", "mets le son",
                    "mets le volume", "mets plus fort"]


def extract_query(text: str, intent: str) -> str:
    """Extract the search query from the transcript after removing intent keywords."""
    cleaned = text.lower().strip().rstrip(".")

    # Remove wake word
    for wake in ["hey pi", "pi board", "piboard", "terminator"]:
        cleaned = cleaned.replace(wake, "")

    # Remove intent trigger words (longest first to avoid partial matches)
    keywords = sorted(INTENT_KEYWORDS.get(intent, []), key=len, reverse=True)
    for kw in keywords:
        cleaned = cleaned.replace(kw, " ")

    # Retire iterativement les mots de tete sans valeur de recherche, jusqu'a
    # tomber sur le vrai debut de la requete. Couvre :
    #  - restes de commande mal transcrits ("mais/met/mes/metz/mai" pour "mets"),
    #  - articles/prepositions ("la musique DE ...", "moi DU ...") laisses apres
    #    le retrait des mots-cles -> evite "mais la vanessa de doc gyneco" ou
    #    "de phil collins" / "du stromae".
    _LEAD = re.compile(
        r"^\s*(?:mais|mets|met|metz|mes|mai|joue|lance|de la|du|des|de|d'|le|la|les|un|une|sur|moi|à|a)\b\s*",
        re.I)
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _LEAD.sub("", cleaned.strip(), count=1)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def _build_french_numbers() -> dict[str, int]:
    """Construit la table FR COMPLETE 0-100 (orthographe usuelle Vosk, sans
    accents). Couvre unites, dizaines en -et-un/-N, soixante-dix..-dix-neuf,
    quatre-vingt(s)/-N, cent. Sert au parsing volume ET timer."""
    units = ["zero", "un", "deux", "trois", "quatre", "cinq", "six", "sept",
             "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze",
             "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
    tens = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante",
            60: "soixante", 80: "quatre-vingt"}
    table: dict[str, int] = {}
    for i, w in enumerate(units):
        table[w] = i
    for base, tw in tens.items():
        table[tw] = base
        for d in range(1, 10):
            val = base + d
            if val > 99:
                break
            link = "-et-un" if d == 1 and base in (20, 30, 40, 50, 60) else "-" + units[d]
            table[tw + link] = val
    # 70-79 = soixante-dix.. ; 90-99 = quatre-vingt-dix..
    for d in range(10, 20):
        table["soixante-" + units[d]] = 60 + d
        table["quatre-vingt-" + units[d]] = 80 + d
    # variantes orthographiques courantes
    table["une"] = 1  # feminin ('dans une heure', 'une minute')
    table["quatre-vingts"] = 80
    table["soixante-et-onze"] = 71
    table["cent"] = 100
    return table


_FRENCH_NUMBERS = _build_french_numbers()

# Mots-cles ancrant une valeur numerique sur le reglage de volume (frontiere de mot).
_VOLUME_ANCHOR = re.compile(r"\b(?:volume|son|pourcent)\b|%", re.I)


def _match_french_number(text: str) -> int | None:
    """Cherche un nombre ecrit en lettres, frontiere de mot, longest-first
    (soixante-quinze avant quinze, dix-sept avant dix/sept)."""
    lower = text.lower()
    for word, val in sorted(_FRENCH_NUMBERS.items(), key=lambda x: -len(x[0])):
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            return val
    return None


def extract_volume_value(text: str) -> int | None:
    """Extract a volume percentage from text like 'volume a 30%' or 'volume a soixante'.

    La valeur doit etre ancree sur un mot-cle volume (volume/son/pourcent/%)
    borne par frontiere de mot : on ne lit le nombre QUE dans le segment qui
    suit le mot-cle (sauf 'NN%' ou le chiffre precede directement le %). Evite
    qu'un numero de piste ('joue la chanson 7') ne regle le volume. Retourne
    None si le chiffre est hors [0,100] (pas de repli silencieux)."""
    lower = text.lower()

    # Cas 'NN%' : chiffre colle au pourcent, ou qu'il soit dans la phrase.
    m = re.search(r'(\d+)\s*%', lower)
    if m:
        val = int(m.group(1))
        return val if 0 <= val <= 100 else None

    anchor = _VOLUME_ANCHOR.search(lower)
    if not anchor:
        return None

    after = lower[anchor.end():]

    # 'deux cents' / 'trois cents' (>100) : compose explicitement hors plage.
    if re.search(r"\b(?:deux|trois|quatre|cinq|six|sept|huit|neuf)\s+cents?\b", after):
        return None

    m = re.search(r'(\d+)\s*%?', after)
    if m:
        val = int(m.group(1))
        return val if 0 <= val <= 100 else None

    # Nombre en lettres apres le mot-cle volume.
    val = _match_french_number(after)
    if val is not None:
        return val

    # Cas "30 %" / "30 pourcent" : l'unite pourcent/% est la seule ancre et le
    # CHIFFRE la precede immediatement (safe : on ne prend que le chiffre colle
    # a l'ancre, pas un nombre lointain -> pas de regression 'joue la chanson 7').
    a = anchor.group(0)
    if "cent" in a or "%" in a:
        mb = re.search(r'(\d+)\s*$', lower[:anchor.start()].rstrip())
        if mb:
            val = int(mb.group(1))
            return val if 0 <= val <= 100 else None
    return None


def extract_timer_minutes(text: str) -> int | None:
    """Extract timer duration from text like 'minuteur 10 minutes' ou
    'rappelle moi dans dix minutes'. Repli sur les nombres FR ecrits en
    lettres si aucun chiffre n'est present. Resultat borne a [1, 24h]."""
    m = re.search(r'(\d+)\s*(?:minute|min|heure|h\b)', text)
    minutes = None
    if m:
        minutes = int(m.group(1))
        # 'dans une heure' / '2 heures' / '2 h' -> conversion en minutes.
        # (le \bheures?\b couvre le pluriel 'heures', oublie auparavant)
        if re.search(r'\b(?:heures?|h)\b', text[m.start():]):
            minutes *= 60
    else:
        fr = _match_french_number(text)
        if fr is not None:
            minutes = fr
            if re.search(r'\bheures?\b', text):
                minutes *= 60
    if minutes is None:
        return None
    return max(1, min(minutes, 24 * 60))


def route(text: str, active_context: str | None = None) -> tuple[str, str]:
    """Route a transcript to an intent.

    Args:
        text: The transcribed text
        active_context: Current active domain (music/youtube/None) for contextual routing

    Returns (intent, query) tuple.
    """
    lower = text.lower().strip()

    # Score each intent by keyword matches
    scores: dict[str, int] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return "GENERAL", text

    # --- Anti-confusion rules ---

    # "mets plus fort" → VOLUME_UP, not MUSIC_PLAY
    if "MUSIC_PLAY" in scores and any(w in lower for w in ANTI_PLAY_WORDS):
        del scores["MUSIC_PLAY"]

    # "volume" alone without a number → could be VOLUME_UP context, don't match VOLUME_SET
    if "MUSIC_VOLUME_SET" in scores and extract_volume_value(lower) is None:
        del scores["MUSIC_VOLUME_SET"]

    if not scores:
        return "GENERAL", text

    # --- Special cases ---

    # Number + volume keyword → VOLUME_SET. Mots-clés sur FRONTIÈRE DE MOT pour
    # éviter « son » ⊂ « chanson » : « joue la chanson 7 » ne doit PAS régler le volume.
    if extract_volume_value(lower) is not None and (
        re.search(r"\b(volume|son|pourcent)\b", lower) or "%" in lower):
        logger.info("[INTENT] '%s' -> MUSIC_VOLUME_SET", text[:50])
        return "MUSIC_VOLUME_SET", text

    # "stop" when YouTube is playing → YOUTUBE_STOP instead of MUSIC_PAUSE
    if "MUSIC_PAUSE" in scores and active_context == "youtube":
        logger.info("[INTENT] '%s' -> YOUTUBE_STOP (context=youtube)", text[:50])
        return "YOUTUBE_STOP", text

    # --- Priority-based routing ---

    # Priority intents (volume, next, pause) beat content intents
    priority_matches = {k: v for k, v in scores.items() if k in PRIORITY_INTENTS}
    if priority_matches:
        best_intent = max(priority_matches, key=priority_matches.get)
    else:
        # MUSIC_FIND beats everything
        if "MUSIC_FIND" in scores:
            best_intent = "MUSIC_FIND"
        # AI_MIX beats MUSIC_PLAY and MUSIC_PLAYLIST
        elif "MUSIC_AI_MIX" in scores and ("MUSIC_PLAY" in scores or "MUSIC_PLAYLIST" in scores):
            best_intent = "MUSIC_AI_MIX"
        # YOUTUBE_PLAY beats MUSIC_PLAY
        elif "YOUTUBE_PLAY" in scores and "MUSIC_PLAY" in scores:
            best_intent = "YOUTUBE_PLAY"
        else:
            best_intent = max(scores, key=scores.get)

    query = extract_query(text, best_intent)
    logger.info("[INTENT] '%s' -> %s (query='%s')", text[:50], best_intent, query)
    return best_intent, query
