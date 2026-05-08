"""Common scraper contract: async fetch() -> list[CorpusDoc]."""
from __future__ import annotations

from abc import ABC, abstractmethod

from castelino.agents.personas.corpus import CorpusDoc


class PersonaScraper(ABC):
    persona_id: str

    @abstractmethod
    async def fetch(self) -> list[CorpusDoc]:
        ...
