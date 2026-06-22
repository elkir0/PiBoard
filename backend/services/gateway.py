"""Client du lan-voice-gateway (Mac mini) — cerveau LLM + TTS LOCAL et GRATUIT.

Le Pi reste client leger : il POST du texte, recoit de l'intention JSON
(/llm/intent), une reponse courte (/llm/chat), une completion generique
(/llm/complete) ou un WAV 24 kHz (/tts). Auth par header X-LAN-VOICE-TOKEN.

Aucune exception ne doit casser la boucle vocale : les appelants (llm.py / tts.py)
gerent le fallback. Ici on leve si indisponible, eux decident."""
import logging

import httpx

try:
    from config import GATEWAY_URL, GATEWAY_TOKEN
except ImportError:  # pragma: no cover
    import os
    GATEWAY_URL = os.getenv("GATEWAY_URL", "")
    GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "")

logger = logging.getLogger(__name__)


class GatewayClient:
    def __init__(self, url: str = GATEWAY_URL, token: str = GATEWAY_TOKEN):
        self.url = (url or "").rstrip("/")
        self.token = token or ""

    def available(self) -> bool:
        return bool(self.url)

    def _headers(self) -> dict:
        return {"Content-Type": "application/json", "X-LAN-VOICE-TOKEN": self.token}

    async def _post(self, path: str, payload: dict, timeout: float) -> httpx.Response:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as c:
            r = await c.post(self.url + path, headers=self._headers(), json=payload)
            r.raise_for_status()
            return r

    async def chat(self, text: str, timeout: float = 15) -> str:
        r = await self._post("/llm/chat", {"text": text}, timeout)
        return (r.json().get("text") or "").strip()

    async def intent(self, text: str, timeout: float = 15) -> dict:
        r = await self._post("/llm/intent", {"text": text}, timeout)
        return r.json()

    async def complete(self, system: str, user: str, max_tokens: int = 200,
                       temperature: float = 0.2, json_mode: bool = False,
                       timeout: float = 25) -> str:
        r = await self._post("/llm/complete", {
            "system": system, "user": user, "max_tokens": max_tokens,
            "temperature": temperature, "json_mode": json_mode}, timeout)
        return (r.json().get("text") or "").strip()

    async def tts(self, text: str, voice: str = "fr_female", timeout: float = 30) -> bytes:
        r = await self._post("/tts", {"text": text, "voice": voice}, timeout)
        return r.content

    async def health(self, timeout: float = 4) -> dict:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as c:
            r = await c.get(self.url + "/health")
            return r.json()
