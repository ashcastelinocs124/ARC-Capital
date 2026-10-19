"""Writer (Claude Opus 5.5): writes the report as points, each owned by the researcher whose facts it uses,
from every finding and fact; the number guard sends it back once."""

from __future__ import annotations

from castelino.agents.research.deep import guard
from castelino.agents.research.deep.models import (
    ChartSpec,
    Point,
    ReportDraft,
    ResearchReport,
    ResearchSession,
    StepError,
)
from castelino.agents.trade import llm
from castelino.agents.weekly.editor import AnthropicEditorClient
from castelino.config import get_settings

SYSTEM = """You are ARC Research's editor. Write a research report that answers the research question,
using only the researchers' findings and facts: every number must be one of the cited facts' numbers.
- title: the answer as a short claim. subtitle: one line on scope.
- points: 5 to 10, in the order a reader needs them. Each point belongs to ONE researcher: agent is that
  researcher's letter, and the point uses only facts that researcher lists (facts it read from the board
  count). headline: one sentence stating the finding; the report's Key findings are these headlines.
  body: 2 to 4 sentences of evidence. fact_ids: every fact the point uses.
- A fact whose source is "@handle on X" is what that person said, never a fact: write "@handle says ..."
  in the same sentence as any figure from it.
- caveats: the main limits of this evidence.
- chart_specs: 0 to {max_charts} charts, only these types: price_history (one ticker in symbols),
  comparison (2 to 4 tickers in symbols), econ_indicator (series_id = a FRED id), yield_curve. Leave
  symbols empty and series_id "" where they don't apply. Prefer none to a weak chart.
Style: plain words, no dashes as punctuation (no "—" or "–"), no fact ids in the prose."""


def brief(s: ResearchSession) -> str:
    parts = [f"Research question: {s.question}"]
    for a in s.agents:
        if a.error or not a.findings:
            continue
        findings = "\n".join(f"- {f.claim} [{', '.join(f.fact_ids)}]" for f in a.findings)
        facts = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in a.facts)
        parts.append(
            f"## Researcher {a.letter} · {a.brief.name}\nAngle: {a.brief.angle}\n"
            f"Findings:\n{findings}\nFacts:\n{facts}"
        )
    return "\n\n".join(parts)


def owner_letter(agent: str) -> str:
    """ "B", "B · Who leads" or "Researcher B" → "B"."""
    t = agent.strip().removeprefix("Researcher ").strip()
    return t[:1].upper()


def write(s: ResearchSession, meter: llm.Meter, *, client=None) -> ResearchReport:
    cfg = get_settings().deep_research
    client = client or AnthropicEditorClient(
        cfg.writer_model, cfg.writer_effort, cfg.writer_max_tokens, agent="research_writer"
    )
    system = SYSTEM.format(max_charts=cfg.max_charts)
    by = s.fact_map()
    owners = {a.letter for a in s.agents if a.findings}
    msgs = [{"role": "user", "content": brief(s)}]
    errs: list[str] = []
    for _ in range(2):
        out, _content = client.parse(system=system, messages=msgs, schema=ReportDraft)
        meter.tokens(cfg.writer_model, *client.last_usage)
        points = [p.model_copy(update={"agent": owner_letter(p.agent)}) for p in out.points]
        out = out.model_copy(update={"points": points})
        if not (errs := guard.report_errors(out, by, owners)):
            break
        msgs += [
            {"role": "assistant", "content": out.model_dump_json()},
            {
                "role": "user",
                "content": "Fix these and write the whole report again: " + "; ".join(errs),
            },
        ]
    else:
        raise StepError("The writer's report failed the number check: " + "; ".join(errs[:8]))
    points = [
        Point(
            id=f"p{k}",
            agent=p.agent,
            headline=guard.strip_ids(p.headline),
            body=guard.strip_ids(p.body),
            fact_ids=[i for i in dict.fromkeys(p.fact_ids) if i in by],
        )
        for k, p in enumerate(out.points, 1)
    ]
    specs = [
        ChartSpec(
            type=c.type,
            title=c.title,
            rationale=c.rationale,
            symbols=c.symbols,
            series_id=c.series_id,
            lookback_days=cfg.chart_lookback_days_default,
        )
        for c in out.chart_specs
    ]
    return ResearchReport(
        title=out.title,
        subtitle=out.subtitle,
        points=points,
        caveats=out.caveats,
        chart_specs=specs,
    )
