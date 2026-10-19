"""Shared plumbing for the Macro / News / Alt agents: code builds Facts, the LLM picks Findings."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from castelino.agents.update.models import AgentName, Fact, Finding, FindingDrafts

_NUM = re.compile(r"(?<![\w.])[-+−]?\d[\d,]*(?:\.\d+)?")
_LINK = re.compile(r"\(?\[[^\]]*\]\([^)]*\)\)?|https?://\S+")  # md links + bare URLs

PICKER_RULES = """Rules:
- Pick the facts that matter most for a US macro investor today and write one finding per story.
- claim: one plain sentence. figure/unit: the single headline number of the finding (or null / "").
- fact_ids: the ids of the facts the finding rests on, exactly as given. Never cite an id not listed.
- Use only numbers that appear in the cited facts. Never invent, round differently, or compute.
- If nothing notable happened, return fewer findings rather than padding."""


def _site(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.") or url


def numbers_in(text: str) -> list[float]:
    out: list[float] = []
    for m in _NUM.finditer(text):
        try:
            out.append(float(m.group(0).replace(",", "").replace("−", "-")))
        except ValueError:
            continue
    return out


def facts_from_search(prefix: str, text: str, cites: list[tuple[str, str, int, int]]) -> list[Fact]:
    """One fact per line of a web-search answer that carries a citation; uncited lines dropped."""
    facts: list[Fact] = []
    pos = 0
    for line in text.split("\n"):
        start, end = pos, pos + len(line)
        pos = end + 1
        hit = next((c for c in cites if start <= c[2] <= end), None)
        body = _LINK.sub("", line).replace("**", "").strip(" -*•\t")
        if hit is None or not body:
            continue
        facts.append(
            Fact(
                id=f"{prefix}{len(facts) + 1}",
                text=body,
                numbers=numbers_in(body),
                provenance="reported",
                # web_search sometimes gives no title, only the URL: show the site instead
                source_title=hit[0] if hit[0] != hit[1] else _site(hit[1]),
                source_url=hit[1],
            )
        )
    return facts


def drafts_prompt(facts: list[Fact], brief: str, ask: str | None, cap: int) -> str:
    lines = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in facts)
    parts = [f"## Today's brief\n{brief}"]
    if ask:
        parts.append(f"## Follow-up from the orchestrator\n{ask}")
    parts += [
        f"## Facts (cite by id)\n{lines or '(no facts today)'}",
        f"Return at most {cap} findings.",
    ]
    return "\n\n".join(parts)


def to_findings(
    drafts: FindingDrafts, facts: list[Fact], agent: AgentName, cap: int
) -> list[Finding]:
    by_id = {f.id: f for f in facts}
    out: list[Finding] = []
    for d in drafts.findings:
        ids = [i for i in d.fact_ids if i in by_id]
        if not ids:
            continue  # the model cited nothing real: drop the finding
        first = by_id[ids[0]]
        out.append(
            Finding(
                id=f"{agent}-{len(out) + 1}",
                agent=agent,
                claim=d.claim,
                figure=d.figure,
                unit=d.unit,
                provenance=first.provenance,
                series=next((by_id[i].series for i in ids if by_id[i].series), None),
                source_title=first.source_title,
                source_url=first.source_url,
                fact_ids=ids,
            )
        )
        if len(out) == cap:
            break
    return out
