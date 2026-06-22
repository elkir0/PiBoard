"""Runtime config manager — loads/saves backend/admin/config.json."""

import json
import copy
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "chunk_size": 1024,
        "error_threshold": 5,
        "pipewire_volume": 32768,
        # Sortie audio choisie (nom pactl du sink). "" = auto = Devialet (fallback).
        # SOURCE DE VÉRITÉ UNIQUE pour le routage de TOUS les émetteurs (musique/TTS/YouTube).
        "output_sink": "",
    },
    "wakeword": {
        "model": "hey_jarvis",
        "threshold": 0.48,
        "cooldown_s": 10.0,
        "engine": "livekit",   # livekit | oww (moteur réellement utilisé ; EWN retiré, non installé)
        "name": "terminator",  # mot-réveil (pertinent EWN)
    },
    "stt": {
        "language": "fr",
        "duration_s": 8.0,
        "rms_threshold": 500,
        "drain_s": 0.5,
    },
    "tts": {
        "provider": "gateway",          # "gateway" (Mac mini, gratuit, DEFAUT) | "voxtral" (cloud) | "piper" (local FR)
        "model": "voxtral-mini-tts-latest",
        "voice": "en_paul_neutral",      # voix preset Voxtral cloud (pas de preset FR cote Mistral)
        "gateway_voice": "fr_female",    # voix de la gateway Voxtral MLX (Mac mini)
        "piper_voice_path": str(Path(__file__).resolve().parent.parent.parent / "voices" / "fr_FR-siwis-medium.onnx"),
        "duck_volume": 20,
    },
    "llm": {
        "model": "mistral-small-latest",
        "max_tokens": 200,
        # Vide = prompt par defaut SELON LA LANGUE (ui.locale), géré dans llm.py.
        # Renseigner ici pour personnaliser (prioritaire sur la langue).
        "system_prompt": "",
    },
    "spotify": {
        "market": "FR",
        "search_limit": 10,
        "queue_display_limit": 10,
        "playlists_limit": 50,
        "device_watch_attempts": 30,
        "device_watch_interval_s": 30,
    },
    "youtube": {
        "format": "bestvideo[height<=720][vcodec^=avc]+bestaudio/bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "search_limit": 5,
        "search_timeout_s": 15,
        "vlc_volume": 256,
        "network_cache_ms": 8000,
        "stop_timeout_s": 3,
    },
    "weather": {
        "timezone": "auto",  # 'auto' = deduit des coordonnees (generique). Surchargeable.
        "forecast_days": 4,
        "fetch_timeout_s": 10,
    },
    "cameras": {
        "snapshot_width": 640,
        "snapshot_height": 360,
        "stream_width": 1280,
        "stream_height": 720,
        "stream_refresh_s": 0.1,
        "grid_refresh_ms": 1500,
        "auth_timeout_s": 3600,
    },
    "screen": {
        "sleep_hour_start": 22,
        "sleep_hour_end": 6,
        "brightness": 100,       # luminosité écran en % (10–100)
        "brightness_max": 255,   # valeur matérielle pour 100%
        # (night_volume/day_volume/quiet_hour_* retirés : plus de volume auto nuit/jour)
    },
    "ui": {
        "locale": "fr",          # langue de l'assistant + de l'UI : "fr" | "en"
        # Couleurs de marque (pilotent le thème Flutter via PBTheme.applyConfig).
        # Défauts = identité PI-Board ; modifiables pour rebrand sans recompiler.
        "accent_color": "#7C6FFF",
        "bg_color": "#060610",
        "swipe_threshold_px": 60,
        "page_transition_ms": 400,
        "clock_update_ms": 10000,
    },
    "system": {
        "backend_port": 8000,
        "ws_reconnect_ms": 3000,
        # Passe à true quand l'assistant de configuration (admin web) est terminé.
        # false sur une install neuve = le wizard s'ouvre automatiquement.
        "setup_complete": False,
    },
    # Domotique : registre d'appareils (vide = désactivée). Voir services/home/base.py
    # pour le modèle. Édité à la main / par l'assistant de config (à venir).
    "home": {
        "devices": [],
    },
}


def is_admin_writable(section: str, key: str | None = None) -> bool:
    """Section/cle editable via l'admin web HTTP : doit exister dans le SCHEMA
    DEFAULT_CONFIG et n'est JAMAIS 'auth' (hash mdp protege). Empeche l'injection
    de section/cle arbitraire via PUT /admin/api/config."""
    if section == "auth" or section not in DEFAULT_CONFIG:
        return False
    if key is None:
        return True
    return key in DEFAULT_CONFIG[section]


def admin_section_keys(section: str) -> set:
    """Cles autorisees (schema) pour une section editable via l'admin."""
    if section == "auth" or section not in DEFAULT_CONFIG:
        return set()
    return set(DEFAULT_CONFIG[section].keys())


# Anciens defauts de theme (#6c63ff/#0a0a0f) : INERTES avant P3.4 (theme Flutter
# code en dur) mais qui PILOTENT desormais l'UI. Un install existant ayant deja
# enregistre la page Interface de l'admin a persiste ces valeurs ; on les realigne
# sur le look historique (#7C6FFF/#060610) au chargement pour eviter un changement
# d'apparence non voulu. (Cas negligeable : un utilisateur ayant CHOISI exactement
# l'ancien defaut serait realigne aussi — c'etait le defaut, pas un choix.)
_LEGACY_THEME = {
    "accent_color": ("#6c63ff", "#7C6FFF"),
    "bg_color": ("#0a0a0f", "#060610"),
}


def _migrate_legacy_theme(cfg: dict) -> None:
    ui = cfg.get("ui")
    if not isinstance(ui, dict):
        return
    for key, (old, new) in _LEGACY_THEME.items():
        val = ui.get(key)
        if isinstance(val, str) and val.strip().lower() == old:
            ui[key] = new


class ConfigManager:
    """Manages runtime config with disk persistence."""

    def __init__(self):
        self._config: dict = {}
        self._load()

    # --- Public API ---

    def get_all(self) -> dict:
        """Return full config (deep copy)."""
        return copy.deepcopy(self._config)

    def get_section(self, section: str) -> dict:
        """Return one section or empty dict."""
        return copy.deepcopy(self._config.get(section, {}))

    def get(self, section: str, key: str, default=None):
        """Return a single value."""
        return self._config.get(section, {}).get(key, default)

    def set_section(self, section: str, values: dict):
        """Merge values into a section, preserving keys not in `values`."""
        if section not in self._config:
            self._config[section] = {}
        self._config[section].update(values)
        self._save()
        logger.info("[CONFIG] Section '%s' mise a jour: %s", section, list(values.keys()))

    def set(self, section: str, key: str, value):
        """Set a single key and save."""
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value
        self._save()
        logger.info("[CONFIG] %s.%s = %s", section, key, value)

    # --- Internal ---

    def _load(self):
        """Load from disk, fill missing keys from defaults."""
        saved = {}
        if CONFIG_PATH.exists():
            try:
                saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("[CONFIG] Erreur lecture %s: %s — utilisation defaults", CONFIG_PATH, e)

        # Deep-merge: defaults + saved (saved wins)
        merged = copy.deepcopy(DEFAULT_CONFIG)
        for section, defaults in DEFAULT_CONFIG.items():
            if section in saved and isinstance(saved[section], dict):
                merged[section].update(saved[section])

        # Keep any extra sections from saved that are not in defaults (e.g. auth)
        for section in saved:
            if section not in merged:
                merged[section] = saved[section]

        _migrate_legacy_theme(merged)

        self._config = merged
        logger.info("[CONFIG] Charge depuis %s", CONFIG_PATH)

    def _save(self):
        """Persist to disk."""
        try:
            CONFIG_PATH.write_text(
                json.dumps(self._config, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("[CONFIG] Erreur ecriture %s: %s", CONFIG_PATH, e)


# Singleton
config = ConfigManager()
