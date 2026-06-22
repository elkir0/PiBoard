"""Short-term conversation memory for voice interactions.

Keeps track of recent commands and context so the assistant can
understand follow-up requests like "non pas celui-la" or "et lundi?".
"""

import time
import logging

logger = logging.getLogger(__name__)

MAX_HISTORY = 8
CONTEXT_TTL = 300  # 5 minutes — after this, context is forgotten


class ConversationMemory:
    """Simple short-term memory for voice pipeline."""

    def __init__(self):
        self._history: list[dict] = []
        self._last_tts: str = ""
        self._active_domain: str | None = None  # music, weather, youtube, etc.

    def add(self, intent: str, query: str, result: dict | None = None):
        """Record a command and its result."""
        entry = {
            "time": time.time(),
            "intent": intent,
            "query": query,
            "result": result or {},
        }
        self._history.append(entry)
        if len(self._history) > MAX_HISTORY:
            self._history = self._history[-MAX_HISTORY:]

        # Track active domain
        if intent.startswith("MUSIC_"):
            self._active_domain = "music"
        elif intent.startswith("YOUTUBE_"):
            self._active_domain = "youtube"
        elif intent == "WEATHER":
            self._active_domain = "weather"
        elif intent == "GENERAL":
            pass  # keep previous domain
        else:
            self._active_domain = None

        logger.info("[MEMORY] +%s query='%s' domain=%s", intent, query[:40], self._active_domain)

    def set_tts(self, text: str):
        """Store the last TTS response for 'repeat' command."""
        self._last_tts = text

    @property
    def last_tts(self) -> str:
        return self._last_tts

    @property
    def domain(self) -> str | None:
        """Active conversation domain, or None if expired."""
        if not self._history:
            return None
        last = self._history[-1]
        if time.time() - last["time"] > CONTEXT_TTL:
            return None
        return self._active_domain

    @property
    def last_intent(self) -> str | None:
        if not self._history:
            return None
        return self._history[-1].get("intent")

    @property
    def last_query(self) -> str | None:
        if not self._history:
            return None
        return self._history[-1].get("query")

    @property
    def last_result(self) -> dict:
        if not self._history:
            return {}
        return self._history[-1].get("result", {})

    def get_recent(self, n: int = 3) -> list[dict]:
        """Get the N most recent interactions (within TTL)."""
        now = time.time()
        return [
            h for h in self._history[-n:]
            if now - h["time"] < CONTEXT_TTL
        ]

    def format_for_llm(self) -> str:
        """Format recent context as text for the LLM system prompt."""
        recent = self.get_recent(4)
        if not recent:
            return ""

        lines = ["Contexte recent:"]
        for h in recent:
            ago = int(time.time() - h["time"])
            result_info = ""
            r = h.get("result", {})
            if r.get("title"):
                result_info = f" -> {r['title']}"
                if r.get("artist"):
                    result_info += f" de {r['artist']}"
            lines.append(f"- [{ago}s] {h['intent']}: \"{h['query']}\"{result_info}")

        if self._active_domain:
            lines.append(f"Domaine actif: {self._active_domain}")

        return "\n".join(lines)


# Singleton
memory = ConversationMemory()
