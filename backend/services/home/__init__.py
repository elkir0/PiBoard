"""Domotique pluggable — interface `HomeProvider` + fabrique.

Deux implémentations derrière une interface commune :
  - **lite** (`lite_provider.LiteHomeProvider`) : drivers intégrés Shelly/Kasa,
    registre d'appareils piloté par la config (aucune dépendance externe). DÉFAUT.
  - **homeassistant** (`ha_provider.HomeAssistantProvider`) : s'appuie sur une
    instance Home Assistant via son API REST (token), pour profiter de ses
    milliers d'intégrations. Nécessite HA_URL + HA_TOKEN.

`main.py` parle à `home` via l'interface `HomeProvider` ; le frontend reçoit des
messages génériques et ignore le provider actif.
"""
import logging

from .base import HomeProvider

logger = logging.getLogger(__name__)


def make_home_provider() -> HomeProvider:
    """Fabrique le provider domotique selon config.HOME_PROVIDER ('lite' par défaut)."""
    try:
        from config import HOME_PROVIDER
    except Exception:
        HOME_PROVIDER = "lite"
    kind = (HOME_PROVIDER or "lite").strip().lower()
    if kind in ("homeassistant", "ha", "home_assistant"):
        from .ha_provider import HomeAssistantProvider
        logger.info("[HOME] Provider actif: Home Assistant")
        return HomeAssistantProvider()
    if kind != "lite":
        logger.warning("[HOME] Provider '%s' inconnu -> repli lite", kind)
    logger.info("[HOME] Provider actif: lite (drivers intégrés)")
    from .lite_provider import LiteHomeProvider
    return LiteHomeProvider()


__all__ = ["HomeProvider", "make_home_provider"]
