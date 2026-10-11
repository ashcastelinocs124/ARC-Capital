"""The trend desk's shared board: desks post what others could use, with the facts behind it."""

from __future__ import annotations

import threading

from castelino.agents.update.models import Fact
from castelino.agents.weekly.models import BoardPost


class Board:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.posts: list[BoardPost] = []
        self.facts: dict[str, Fact] = {}

    def post(self, agent: str, note: str, facts: list[Fact]) -> BoardPost:
        p = BoardPost(agent=agent, note=note, fact_ids=[f.id for f in facts])
        with self._lock:
            self.posts.append(p)
            self.facts.update({f.id: f for f in facts})
        return p

    def read(self, agent: str) -> tuple[list[BoardPost], list[Fact]]:
        with self._lock:
            posts = [p for p in self.posts if p.agent != agent]
            facts = [self.facts[i] for p in posts for i in p.fact_ids]
        return posts, facts
