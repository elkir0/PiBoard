import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info("[WS] +1 client (%d total)", len(self.active))

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        logger.info("[WS] -1 client (%d restants)", len(self.active))

    async def broadcast(self, message: dict):
        for client in self.active:
            try:
                await client.send_json(message)
            except Exception:
                pass
