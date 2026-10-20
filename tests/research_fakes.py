"""Builders shared by the General Deep Research tests."""

from __future__ import annotations

from castelino.agents.research.deep.models import AgentRun, Brief, Finding
from castelino.agents.update.models import Fact


def fact(fid: str, text: str, numbers: list[float], url: str = "https://example.com/a") -> Fact:
    return Fact(
        id=fid, text=text, numbers=numbers, provenance="data", source_title="Test", source_url=url
    )


def xfact(fid: str, who: str, text: str, numbers: list[float], status: str = "1") -> Fact:
    return Fact(
        id=fid,
        text=f"@{who}: {text}",
        numbers=numbers,
        provenance="reported",
        source_title=f"@{who} on X",
        source_url=f"https://x.com/{who}/status/{status}",
    )


def brief(name: str = "Adoption rate") -> Brief:
    return Brief(name=name, angle=f"What is the {name.lower()}?", brief="Find survey data first.")


def agent(
    letter: str = "A", *, facts=None, findings=None, transcript=None, round_: int = 1
) -> AgentRun:
    if facts is None:
        facts = [fact(f"{letter}1", "AI use reached 9.2% of firms in 2026", [9.2])]
    if findings is None:
        findings = (
            [Finding(id=f"{letter}-f1", claim="9.2% of firms use AI", fact_ids=[facts[0].id])]
            if facts
            else []
        )
    return AgentRun(
        letter=letter,
        round=round_,
        brief=brief(),
        model="m",
        facts=facts,
        findings=findings,
        transcript=transcript,
    )
