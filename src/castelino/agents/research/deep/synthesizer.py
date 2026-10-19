"""Writer (Claude Opus 5.5): writes the report as points, each owned by the researcher whose facts it uses,
from every finding and fact; the number guard sends it back once. For an addition it writes only new points,
from the new researchers' findings, and never touches the points already written."""

from __future__ import annotations

import re
from datetime import date

from castelino.agents.research.deep import guard
from castelino.agents.research.deep.models import (
    MorePoints,
    Point,
    ReportDraft,
    ResearchReport,
    ResearchSession,
    StepError,
)
from castelino.agents.trade import llm
from castelino.agents.weekly.editor import AnthropicEditorClient
from castelino.config import get_settings

_LETTER = re.compile(r"(?<![A-Za-z])([A-Pa-p])(?![A-Za-z])")  # an agent letter on its own
SYSTEM = """You are ARC Research's editor. Write a research report that answers the research question,
using only the researchers' findings and facts: every number must be one of the cited facts' numbers.
- title: the answer as a short claim. subtitle: one line on scope.
- points: 5 to 10, in the order a reader needs them. Each point belongs to ONE researcher: agent is that
  researcher's letter, and the point uses only facts that researcher lists (facts it read from the board
  count). headline: one sentence stating the finding; the report's Key findings are these headlines.
  body: 2 to 4 sentences of evidence. fact_ids: every fact the point uses.
- A fact whose source is "@handle on X" is what that person said, never a fact: write "@handle says ..."
  in the same sentence as any figure from it.
- Use the most recent figures: when facts measure the same thing, use the newest, and say when each
  figure is from. A figure older than 12 months needs its year and "the latest available" if it is.
- caveats: the main limits of this evidence.
Style: plain words, no dashes as punctuation (no "—" or "–"), no fact ids in the prose."""
MORE = """You are ARC Research's editor. The report is already written; new researchers have now covered
angles the analyst asked to add. Write NEW points from the new researchers' findings and facts only: every
number must be one of the cited facts' numbers, and never repeat what the report already says.
- points: 1 to 3 per new researcher, in the order a reader needs them. Each point belongs to ONE new
  researcher: agent is that researcher's letter, and the point uses only facts that researcher lists.
  headline: one sentence stating the finding. body: 2 to 4 sentences of evidence. fact_ids: every fact the
  point uses.
- A fact whose source is "@handle on X" is what that person said, never a fact: write "@handle says ..."
  in the same sentence as any figure from it.
- Use the most recent figures: when facts measure the same thing, use the newest, and say when each
  figure is from. A figure older than 12 months needs its year and "the latest available" if it is.
Style: plain words, no dashes as punctuation (no "—" or "–"), no fact ids in the prose."""


def brief(s: ResearchSession, letters: list[str] | None = None) -> str:
    parts = [f"Today is {date.today()}.\nResearch question: {s.question}"]
    for a in s.agents:
        if a.error or not a.findings or (letters is not None and a.letter not in letters):
            continue
        findings = "\n".join(f"- {f.claim} [{', '.join(f.fact_ids)}]" for f in a.findings)
        facts = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in a.facts)
        parts.append(
            f"## Researcher {a.letter} · {a.brief.name}\nAngle: {a.brief.angle}\n"
            f"Findings:\n{findings}\nFacts:\n{facts}"
        )
    return "\n\n".join(parts)


def owner_letter(agent: str) -> str:
    """ "B", "B · Who leads", "Researcher B" or "Agent B" → "B": the first standalone letter, so a word
    like "Agent" never becomes owner "A"."""
    m = _LETTER.search(agent)
    return m.group(1).upper() if m else agent.strip()[:1].upper()


def _checked(client, system: str, content: str, schema, by, owners: set[str], meter: llm.Meter):
    """The writer's draft once it passes the number guard: one retry with the errors, then StepError."""
    model = get_settings().deep_research.writer_model
    msgs = [{"role": "user", "content": content}]
    errs: list[str] = []
    for _ in range(2):
        out, _content = client.parse(system=system, messages=msgs, schema=schema)
        meter.tokens(model, *client.last_usage)
        points = [p.model_copy(update={"agent": owner_letter(p.agent)}) for p in out.points]
        out = out.model_copy(update={"points": points})
        draft = (
            out
            if isinstance(out, ReportDraft)
            else ReportDraft(title="", subtitle="", points=points, caveats=[])
        )
        if not (errs := guard.report_errors(draft, by, owners)):
            return out
        msgs += [
            {"role": "assistant", "content": out.model_dump_json()},
            {
                "role": "user",
                "content": "Fix these and write the whole report again: " + "; ".join(errs),
            },
        ]
    raise StepError("The writer's report failed the number check: " + "; ".join(errs[:8]))


def _client(client):
    cfg = get_settings().deep_research
    return client or AnthropicEditorClient(
        cfg.writer_model, cfg.writer_effort, cfg.writer_max_tokens, agent="research_writer"
    )


def _points(drafts, by, start: int, added: int | None = None) -> list[Point]:
    return [
        Point(
            id=f"p{k}",
            agent=p.agent,
            headline=guard.strip_ids(p.headline),
            body=guard.strip_ids(p.body),
            fact_ids=[i for i in dict.fromkeys(p.fact_ids) if i in by],
            added=added,
        )
        for k, p in enumerate(drafts, start)
    ]


def write(s: ResearchSession, meter: llm.Meter, *, client=None) -> ResearchReport:
    by = s.fact_map()
    owners = {a.letter for a in s.agents if a.findings}
    out = _checked(_client(client), SYSTEM, brief(s), ReportDraft, by, owners, meter)
    return ResearchReport(
        title=out.title,
        subtitle=out.subtitle,
        points=_points(out.points, by, 1),
        caveats=out.caveats,
    )


def write_more(
    s: ResearchSession, letters: list[str], added: int, meter: llm.Meter, *, client=None
) -> list[Point]:
    """New points from these researchers only, numbered after the report's last point."""
    by = s.fact_map()
    owners = {a.letter for a in s.agents if a.letter in letters and a.findings}
    says = "\n".join(f"- {p.headline}" for p in s.report.points)
    content = f"The report already says:\n{says}\n\n{brief(s, letters)}"
    out = _checked(_client(client), MORE, content, MorePoints, by, owners, meter)
    return _points(out.points, by, len(s.report.points) + 1, added)
