import asyncio
import logging
from datetime import datetime
from typing import Any

import requests

from config import WEATHER_LAT, WEATHER_LON, WEATHER_CITY

try:
    from admin.config_manager import config as _admin_config
except Exception:  # pragma: no cover
    _admin_config = None

logger = logging.getLogger(__name__)


def _timezone() -> str:
    """Fuseau pour Open-Meteo. Defaut 'auto' = deduit des coordonnees (generique,
    plus de fuseau personnel code en dur). Surchargeable via config.json
    weather.timezone (page Admin Meteo)."""
    if _admin_config:
        return _admin_config.get("weather", "timezone", "auto") or "auto"
    return "auto"

BASE_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes -> descriptions FR + icon keys
WMO_CODES = {
    0: ("ensoleille", "01d"),
    1: ("peu nuageux", "02d"),
    2: ("partiellement nuageux", "03d"),
    3: ("couvert", "04d"),
    45: ("brouillard", "50d"),
    48: ("brouillard givrant", "50d"),
    51: ("bruine legere", "09d"),
    53: ("bruine", "09d"),
    55: ("bruine forte", "09d"),
    61: ("pluie legere", "10d"),
    63: ("pluie", "10d"),
    65: ("forte pluie", "10d"),
    71: ("neige legere", "13d"),
    73: ("neige", "13d"),
    75: ("forte neige", "13d"),
    80: ("averses legeres", "09d"),
    81: ("averses", "09d"),
    82: ("fortes averses", "09d"),
    95: ("orage", "11d"),
    96: ("orage avec grele", "11d"),
    99: ("orage violent", "11d"),
}

# Conditions EN (l'icône est commune ; cf WMO_CODES pour le FR). Suit ui.locale.
WMO_CODES_EN = {
    0: "sunny", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 80: "light showers", 81: "showers", 82: "heavy showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "violent thunderstorm",
}
_DAYS = {
    "fr": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}


def _wx_locale() -> str:
    """Langue météo (config ui.locale), 'fr' par défaut."""
    if _admin_config:
        return (_admin_config.get("ui", "locale", "fr") or "fr").strip().lower()[:2]
    return "fr"


def _wmo(code: int) -> tuple[str, str]:
    """(condition localisée, icône) pour un code WMO."""
    cond_fr, icon = WMO_CODES.get(code, ("inconnu", "01d"))
    if _wx_locale() == "en":
        return WMO_CODES_EN.get(code, "unknown"), icon
    return cond_fr, icon


class WeatherService:
    def __init__(self):
        self._cache: dict | None = None

    async def get_current(self) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, self._fetch)

            current = data["current"]
            daily = data["daily"]
            hourly = data.get("hourly", {})

            wmo = current.get("weather_code", 0)
            condition, icon = _wmo(wmo)
            is_day = current.get("is_day", 1)
            if not is_day:
                icon = icon.replace("d", "n")

            parsed_hourly = self._parse_hourly(hourly)
            # UV "maintenant" : Open-Meteo n'expose pas uv_index en "current" -> on
            # prend l'uv_index de l'heure courante (1ere entree horaire), repli sur
            # le max du jour. Corrige le badge UV de l'UI (qui lisait un champ absent).
            uv_now = parsed_hourly[0].get("uv") if parsed_hourly else None
            if uv_now is None:
                uv_max = daily.get("uv_index_max") or []
                uv_now = uv_max[0] if uv_max else 0

            result = {
                "loaded": True,
                "city": WEATHER_CITY,
                "temp": round(current["temperature_2m"]),
                "feels_like": round(current["apparent_temperature"]),
                "humidity": round(current["relative_humidity_2m"]),
                "wind": round(current["wind_speed_10m"]),
                "gusts": round(current.get("wind_gusts_10m") or 0),
                "pressure": round(current.get("surface_pressure") or 0),
                "uv": round(uv_now or 0),
                "cloud_cover": current.get("cloud_cover", 0),
                "condition": condition,
                "icon": icon,
                "is_day": is_day,
                "forecast": self._parse_forecast(daily),
                "hourly": parsed_hourly,
            }
            self._cache = result
            logger.info("[METEO] %s: %d°C, %s, UV %s, nuages %d%%",
                        WEATHER_CITY, result["temp"], condition, result["uv"], result["cloud_cover"])
            return result

        except Exception as e:
            logger.error("[METEO] Erreur: %s", e)
            if self._cache:
                return self._cache
            return self._mock_data()

    def _fetch(self) -> dict:
        resp = requests.get(
            BASE_URL,
            params={
                "latitude": WEATHER_LAT,
                "longitude": WEATHER_LON,
                # best_match (PAS de models=… : forcer un modèle Météo-France met
                # precipitation_probability à null pour les Antilles). Champs enrichis.
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_gusts_10m,cloud_cover,surface_pressure,precipitation,is_day",
                "hourly": "temperature_2m,weather_code,precipitation_probability,rain,cloud_cover,wind_speed_10m,wind_gusts_10m,uv_index",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max,sunrise,sunset",
                "timezone": _timezone(),
                "forecast_days": 4,
                "forecast_hours": 24,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    _FR_DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

    def _parse_forecast(self, daily: dict) -> list[dict]:
        forecast = []
        for i in range(1, min(4, len(daily.get("time", [])))):
            date = datetime.strptime(daily["time"][i], "%Y-%m-%d")
            wmo = daily["weather_code"][i]
            condition, icon = _wmo(wmo)
            rp = daily.get("precipitation_probability_max") or []
            uv = daily.get("uv_index_max") or []
            forecast.append({
                # locale-independant (pas de setlocale fr_FR, souvent absent du Pi)
                "day": _DAYS[_wx_locale()][date.weekday()],
                "high": round(daily["temperature_2m_max"][i]),
                "low": round(daily["temperature_2m_min"][i]),
                "icon": icon,
                "condition": condition,
                "rain_prob": round(rp[i]) if i < len(rp) and rp[i] is not None else None,
                "uv": round(uv[i]) if i < len(uv) and uv[i] is not None else None,
            })
        return forecast

    def _parse_hourly(self, hourly: dict) -> list[dict]:
        """Parse next 12 hours of hourly data."""
        result = []
        times = hourly.get("time", [])
        now = datetime.now()
        current_hour = now.strftime("%Y-%m-%dT%H:00")

        started = False
        for i, t in enumerate(times):
            if t >= current_hour:
                started = True
            if not started:
                continue
            if len(result) >= 12:
                break

            wmo = hourly["weather_code"][i]
            _, icon = _wmo(wmo)
            hour_dt = datetime.strptime(t, "%Y-%m-%dT%H:%M")
            if hour_dt.hour < 6 or hour_dt.hour > 20:
                icon = icon.replace("d", "n")

            def _h(key, default=0):
                arr = hourly.get(key) or []
                return arr[i] if i < len(arr) and arr[i] is not None else default

            result.append({
                "hour": hour_dt.strftime("%Hh"),
                "temp": round(_h("temperature_2m")),
                "rain": _h("rain"),
                "rain_prob": round(_h("precipitation_probability")),
                "cloud": round(_h("cloud_cover")),
                "wind": round(_h("wind_speed_10m")),
                "gusts": round(_h("wind_gusts_10m")),
                "uv": round(_h("uv_index")),
                "icon": icon,
            })
        return result

    def format_spoken(self, data: dict) -> str:
        if not data.get("loaded"):
            return "Je n'ai pas pu recuperer la meteo."

        text = (
            f"A {data['city']}, il fait {data['temp']} degres, "
            f"{data['condition']}. "
            f"Humidite {data['humidity']}%, "
            f"vent {data['wind']} kilometres heure."
        )

        if data.get("forecast"):
            f = data["forecast"][0]
            text += f" Demain, entre {f['low']} et {f['high']} degres, {f['condition']}."

        # Add hourly hint
        hourly = data.get("hourly", [])
        rain_hours = [h for h in hourly[:6] if (h.get("rain") or 0) > 0.5]
        if rain_hours:
            text += f" Pluie prevue a {rain_hours[0]['hour']}."

        return text

    def _mock_data(self) -> dict:
        return {
            "loaded": False,
            "city": WEATHER_CITY,
            "temp": 28, "feels_like": 32, "humidity": 75, "wind": 15,
            "cloud_cover": 40, "condition": "partiellement nuageux", "icon": "02d", "is_day": 1,
            "forecast": [
                {"day": "Lun", "high": 30, "low": 24, "icon": "02d", "condition": "nuageux"},
                {"day": "Mar", "high": 29, "low": 23, "icon": "10d", "condition": "pluie legere"},
                {"day": "Mer", "high": 31, "low": 25, "icon": "01d", "condition": "ensoleille"},
            ],
            "hourly": [],
        }
