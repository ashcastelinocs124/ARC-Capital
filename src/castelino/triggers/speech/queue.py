"""Process-local in-memory queue for speech triggers."""
from __future__ import annotations

from threading import Lock
from castelino.memory.schemas import TriggerRecord


class _SpeechTriggerQueue:
    def __init__(self):
        self._lock = Lock()
        self._items: list[TriggerRecord] = []

    def offer(self, trg: TriggerRecord) -> None:
        with self._lock:
            self._items.append(trg)

    def drain(self) -> list[TriggerRecord]:
        with self._lock:
            out, self._items = self._items, []
            return out

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


speech_trigger_queue = _SpeechTriggerQueue()
