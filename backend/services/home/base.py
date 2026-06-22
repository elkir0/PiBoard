"""Interface commune aux fournisseurs domotique (lite / Home Assistant).

`main.py` pilote la domotique via ce contrat. Le registre d'appareils vient de
la **config** (`config.json` section `home.devices`), pas du code — chaque
utilisateur déclare ses appareils. Modèle d'un appareil (dict) :

    {
      "id":        "volet_gauche",         # identifiant interne (clé)
      "name":      "Volet Gauche",         # libellé affiché
      "kind":      "cover" | "gate" | "switch",   # type générique (UI + mapping)
      # --- lite (drivers Shelly/Kasa) ---
      "driver":    "shelly_roller" | "shelly_cover_g2" | "shelly_relay_g3" | "kasa_plug",
      "mac":       "AABBCCDDEEFF",         # pour l'autodécouverte par MAC
      "shelly_id": "shelly1minig3-...",    # ou par id Shelly
      # --- home assistant ---
      "ha_entity": "cover.volet_gauche"    # entity_id HA
    }

`kind` :
  - **cover**  : volet/store -> open/close/stop/position.
  - **gate**   : portail (relais impulsionnel) -> trigger.
  - **switch** : prise/relais on/off -> on/off/toggle.

Tout est async ; aucune méthode ne lève (échec -> log + valeur dégradée). Un
registre vide = domotique désactivée proprement.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


def load_registry() -> list[dict]:
    """Liste des appareils déclarés en config (`home.devices`). [] si absent."""
    try:
        from admin.config_manager import config
        devs = config.get("home", "devices", [])
        return devs if isinstance(devs, list) else []
    except Exception:
        return []


class HomeProvider(ABC):
    """Contrat commun à tous les providers domotique. Les libellés de méthode
    (roller_/portail/plug_) sont historiques mais opèrent GÉNÉRIQUEMENT selon le
    `kind` des appareils du registre (cover / gate / switch)."""

    @abstractmethod
    async def start(self) -> None:
        """Initialise (découverte, auth…). Ne crashe jamais."""

    @abstractmethod
    async def get_status(self) -> dict:
        """État de tous les appareils -> {id: {name, kind, online, ...}}."""

    # --- Volets (kind=cover) ---
    @abstractmethod
    async def roller_open(self, device_id: str) -> bool: ...
    @abstractmethod
    async def roller_close(self, device_id: str) -> bool: ...
    @abstractmethod
    async def roller_stop(self, device_id: str) -> bool: ...
    @abstractmethod
    async def roller_position(self, device_id: str, pos: int) -> bool: ...
    @abstractmethod
    async def open_all_rollers(self) -> bool:
        """Ouvre tous les appareils kind=cover."""
    @abstractmethod
    async def close_all_rollers(self) -> bool:
        """Ferme tous les appareils kind=cover."""

    # --- Portail (kind=gate, impulsion) ---
    @abstractmethod
    async def trigger_portail(self) -> bool:
        """Déclenche l'appareil kind=gate (impulsion)."""

    # --- Prises / relais (kind=switch) ---
    @abstractmethod
    async def plug_on(self, device_id: str = "guinguette") -> bool: ...
    @abstractmethod
    async def plug_off(self, device_id: str = "guinguette") -> bool: ...
    @abstractmethod
    async def plug_toggle(self, device_id: str = "guinguette") -> bool: ...
