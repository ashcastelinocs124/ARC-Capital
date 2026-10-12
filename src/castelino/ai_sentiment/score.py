"""Deterministic scoring: which provider a post is about, and a word-list sentiment.

ponytail: a word list misses sarcasm and new slang; data/ai_sentiment/lexicon.yaml is the knob,
and the card highlights matched words so misses are visible.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

NEG_WINDOW = 3  # a negator up to 3 words back flips the term
WORD = re.compile(r"[a-z0-9']+")
# sentences and contrast words: "Claude is fast but GPT is slow" scores each side separately
CLAUSE = re.compile(r"[.!?;\n]+|\b(?:but|while|whereas|vs|versus)\b", re.I)


def families_of(text: str, lex: dict) -> set[str]:
    t = text.lower()
    return {
        fam
        for fam, kws in lex["families"].items()
        if any(re.search(rf"\b{re.escape(k)}\b", t) for k in kws)
    }


def post_score(text: str, lex: dict) -> tuple[int, list[str]]:
    """Sum of +1/-1 per matched term (phrases first), flipped by a nearby negator."""
    toks = WORD.findall(text.lower())
    terms = [(t.split(), +1) for t in lex["positive"]] + [(t.split(), -1) for t in lex["negative"]]
    terms.sort(key=lambda x: -len(x[0]))  # longest phrase wins
    negators = set(lex.get("negators", []))
    total, hits, i = 0, [], 0
    while i < len(toks):
        for words, sign in terms:
            if toks[i : i + len(words)] == words:
                flip = any(w in negators for w in toks[max(0, i - NEG_WINDOW) : i])
                total += -sign if flip else sign
                hits.append(" ".join(words))
                i += len(words)
                break
        else:
            i += 1
    return total, hits


def daily(posts: list[dict], accounts: dict[str, str], lex: dict) -> dict[str, dict]:
    """One day's posts -> per provider counts, net = %pos - %neg, and up to 3 sample posts.

    A post by someone affiliated with a lab never counts toward that lab.
    """
    out: dict[str, dict] = {}
    for p in posts:
        fams = families_of(p["text"], lex)
        clauses = CLAUSE.split(p["text"])
        for fam in fams:
            if accounts.get(p["author"], "") == fam:
                continue
            mine = " . ".join(c for c in clauses if fam in families_of(c, lex))
            s, hits = post_score(mine, lex)
            if not hits and len(fams) == 1:  # "Tried Claude today. Honestly impressive"
                s, hits = post_score(p["text"], lex)
            f = out.setdefault(fam, {"n": 0, "pos": 0, "neg": 0, "neu": 0, "samples": []})
            f["n"] += 1
            f["pos" if s > 0 else "neg" if s < 0 else "neu"] += 1
            f["samples"].append({**p, "score": s, "hits": hits})
    for f in out.values():
        f["net"] = round(100 * (f["pos"] - f["neg"]) / f["n"], 1)
        f["samples"] = sorted(f["samples"], key=lambda x: -len(x["hits"]))[:3]
    return out


def series(history: dict[str, dict], fam: str) -> list[tuple[str, float]]:
    """7-day average net per day (fewer days at the start of history); days without posts skipped."""
    days = sorted(history)
    if not days:
        return []
    start, end = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    out = []
    d = start
    while d <= end:
        window = [(d - timedelta(days=k)).isoformat() for k in range(7)]
        vals = [history[w][fam]["net"] for w in window if fam in history.get(w, {})]
        if vals:
            out.append((d.isoformat(), round(sum(vals) / len(vals), 1)))
        d += timedelta(days=1)
    return out


def delta(levels: list[tuple[str, float]]) -> float | None:
    """Rate of change: latest 7-day level minus the level 7 days earlier (None without it)."""
    if not levels:
        return None
    last_day, last = levels[-1]
    week_ago = date.fromisoformat(last_day) - timedelta(days=7)
    # the earlier level must itself be a full week, i.e. 14 days of history
    if week_ago - timedelta(days=6) < date.fromisoformat(levels[0][0]):
        return None
    prev = dict(levels).get(week_ago.isoformat())
    return None if prev is None else round(last - prev, 1)
