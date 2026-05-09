"""Conviction-ledger feed adapter for figure-deviation.

Wave 7 Task 7.3 — translates a scored FigurePost (with its lexicon's
directional tags) into a `HeadlineScore`-shaped record that the existing
`triggers/conviction.py` ledger can ingest.

The adapter maps the directional-tag vocabulary (usd_up, em_equity_down,
gold_up, etc.) into the ledger's growth/inflation directions. The mapping
is deliberately conservative: tags that cleanly reflect growth or inflation
movement get translated; others (sector-specific like xle_up) are dropped
from the ledger feed but still surface in the trigger's directional_tags
on emission.

The translation table lives here, in the adapter, NOT in the dispatcher —
keeping the dispatcher's concerns about market-direction tagging
out of the per-figure scoring loop.
"""
from __future__ import annotations

from castelino.triggers import conviction
from castelino.triggers.figure_deviation.dispatcher import PostScoredEvent
from castelino.triggers.significance import HeadlineScore


# ────────────────────────── translation table ──────────────────────────────
#
# Maps figure-deviation directional tags to (growth_direction, inflation_direction)
# tuples for the conviction ledger. None means 'no signal on that axis'.

_TAG_TO_LEDGER_DIRECTION: dict[str, tuple[str | None, str | None]] = {
    # (growth_direction, inflation_direction) ∈ {"up", "down", None}
    # USD / dollar
    "usd_up":           ("up", None),
    "usd_down":         ("down", None),
    # Rates
    "rates_up":         (None, "up"),
    "rates_down":       (None, "down"),
    # Gold / safe haven
    "gold_up":          (None, "up"),
    "gold_down":        (None, "down"),
    # EM equity
    "em_equity_up":     ("up", None),
    "em_equity_down":   ("down", None),
    "china_exposed_down": ("down", None),
    "semis_down":       ("down", None),
    # Oil
    "wti_up":           (None, "up"),
    "wti_down":         (None, "down"),
    "xle_up":           (None, "up"),
    # Misc — no growth/inflation signal
    "ibit_up":          (None, None),
    "btc_up":           (None, None),
    "ita_up":           (None, None),
    "lmt_up":           (None, None),
    "xlk_down":         (None, None),
    "qqq_down":         (None, None),
    "fed_independence_risk_up": (None, None),
}


def _translate_tags(tags: list[str]) -> tuple[str, str]:
    """Translate a list of directional tags into (growth_dir, inflation_dir)
    in {'up', 'down', 'neutral'} via majority vote across mapped tags."""
    def _consensus(signals: list[str]) -> str:
        if not signals:
            return "neutral"
        ups = signals.count("up")
        downs = signals.count("down")
        if ups > downs:
            return "up"
        if downs > ups:
            return "down"
        return "neutral"

    growth_signals: list[str] = []
    inflation_signals: list[str] = []
    for t in tags:
        g, i = _TAG_TO_LEDGER_DIRECTION.get(t, (None, None))
        if g is not None:
            growth_signals.append(g)
        if i is not None:
            inflation_signals.append(i)
    return _consensus(growth_signals), _consensus(inflation_signals)


# ────────────────────────── public hook ────────────────────────────────────


def feed_conviction_ledger(event: PostScoredEvent) -> None:
    """Hook installable as the dispatcher's `on_post_scored` callback.

    For each scored post with non-zero score AND at least one mappable
    directional tag, append a synthetic HeadlineScore to the conviction
    ledger so accumulated materiality contributes to the cron-fired
    conviction trigger even when no individual deviation fires.
    """
    abs_score = abs(event.score_value)
    if abs_score < 0.05:
        return  # below noise floor; skip
    growth_dir, inflation_dir = _translate_tags(event.directional_tags)
    if growth_dir == "neutral" and inflation_dir == "neutral":
        return  # no growth/inflation signal in these tags
    # Materiality matches the existing convention (0..1 scale, threshold 0.3
    # in conviction.py). Use the score magnitude scaled to that range.
    materiality = max(0.3, min(1.0, abs_score))
    headline_id = (
        f"figure_deviation:{event.figure_id}:{event.lexicon}:{event.post.event_id}"
    )
    score_record = HeadlineScore(
        headline_id=headline_id,
        title=f"[{event.figure_id}/{event.lexicon}] {event.post.text[:160]}",
        materiality=materiality,
        one_sentence_reason=(
            f"figure-deviation contribution from {event.figure_id} on "
            f"{event.lexicon} (tags: {', '.join(event.directional_tags)})"
        ),
        growth_direction=growth_dir,
        inflation_direction=inflation_dir,
    )
    try:
        conviction.append([score_record])
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "conviction.append raised for figure_deviation feed; ignoring",
        )
