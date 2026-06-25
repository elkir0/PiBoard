"""Runtime config validation shared by WebSocket and tests."""

# Couples (section, cle) modifiables via config_set. JAMAIS 'auth' ni cle arbitraire.
ALLOWED_CONFIG_KEYS = {
    ("tts", "provider"), ("tts", "voice"), ("tts", "model"), ("tts", "piper_voice_path"),
    ("llm", "model"), ("llm", "max_tokens"), ("llm", "system_prompt"),
    ("wakeword", "threshold"), ("wakeword", "cooldown_s"), ("wakeword", "engine"),
    ("wakeword", "name"), ("wakeword", "livekit_model"),
    ("audio", "output_sink"),
    ("ui", "locale"), ("ui", "accent_color"), ("ui", "bg_color"),
    ("screen", "brightness"), ("screen", "sleep_hour_start"), ("screen", "sleep_hour_end"),
}

# Mot-reveil & moteurs autorises (doivent matcher wakeword.py + l'UI Reglages).
WW_ENGINES = ("livekit", "oww")
WW_WORDS = ("terminator", "hey_jarvis", "hey_mycroft", "alexa")
WW_LIVEKIT_MODELS = ("terminator_v1", "terminator_v2")


def one_of(*allowed):
    """Coerceur enum : rejette (ValueError) toute valeur hors liste -> non persistee."""
    def _c(v):
        if v not in allowed:
            raise ValueError(v)
        return v
    return _c


def hex_color(v):
    """Coerceur couleur : '#RRGGBB' (ou 'RRGGBB') -> '#RRGGBB' majuscule."""
    if not isinstance(v, str):
        raise ValueError(v)
    s = v.strip().lstrip("#")
    if len(s) != 6 or any(c not in "0123456789abcdefABCDEF" for c in s):
        raise ValueError(v)
    return "#" + s.upper()


# Coercition type/plage par couple : evite de persister une valeur invalide
# ('abc' pour threshold, float pour max_tokens...) qui casserait wakeword.py/llm.
CONFIG_COERCE = {
    ("llm", "max_tokens"): lambda v: max(1, int(v)),
    ("wakeword", "threshold"): lambda v: min(1.0, max(0.0, float(v))),
    ("wakeword", "cooldown_s"): lambda v: max(0, int(v)),
    ("wakeword", "engine"): one_of(*WW_ENGINES),
    ("wakeword", "name"): one_of(*WW_WORDS),
    ("wakeword", "livekit_model"): one_of(*WW_LIVEKIT_MODELS),
    ("ui", "locale"): one_of("fr", "en"),
    ("ui", "accent_color"): hex_color,
    ("ui", "bg_color"): hex_color,
    ("screen", "brightness"): lambda v: min(100, max(10, int(v))),
    ("screen", "sleep_hour_start"): lambda v: min(23, max(0, int(v))),
    ("screen", "sleep_hour_end"): lambda v: min(23, max(0, int(v))),
}
