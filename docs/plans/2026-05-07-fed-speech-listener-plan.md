# Fed Speech Listener Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `SPEECH_DEVIATION` trigger source that streams live FOMC press conference audio through Deepgram STT, scores each sentence on a hawkish/dovish lexicon, and fires the existing pipeline when a 5-sentence rolling window deviates >1.5σ from the speaker's own 12-month rhetorical baseline.

**Architecture:** Three layers under `src/castelino/triggers/speech/`. Layer 1 (offline persona builder) scrapes Fed speeches and aggregates a per-speaker `BaselineVector`. Layer 2 (event-driven async listener) streams audio for scheduled events through a pluggable `SpeechToTextProvider`. Layer 3 (real-time deviation scorer) z-scores rolling windows against the persona; on >1.5σ, escalates to gpt-4o-mini for confirmation, then emits a `TriggerRecord` into the existing pipeline. The orchestrator graph requires zero changes — speech triggers enter at `current_event` like any other trigger.

**Tech Stack:** Python 3.11, Pydantic 2.x, Typer, pytest, OpenAI structured output (`chat.completions.parse`), Deepgram streaming SDK (new), httpx + BeautifulSoup for Fed website scraping, asyncio for the listener.

**Reference design:** `docs/plans/2026-05-07-fed-speech-listener-design.md`

**Key learnings to honor (from `learnings.md`):**
- Use top-level `chat.completions.parse(response_format=...)` not `.beta.` (Stage B LLM call)
- `max_completion_tokens` not `max_tokens` for forward compatibility with reasoning models
- Hard rules must be structurally enforced, not prompt-dependent (cooldown, threshold gating)
- Defense in depth — both Stage-A threshold check AND Stage-B LLM gate must agree before emitting

---

## Task 1: Add `SPEECH_DEVIATION` to TriggerSource enum

**Files:**
- Modify: `src/castelino/memory/schemas.py` (TriggerSource enum)
- Test: `tests/test_trigger_layer.py` (extend existing)

**Step 1: Write the failing test**

```python
# tests/test_trigger_layer.py — add to existing file
def test_speech_deviation_trigger_source_exists():
    from castelino.memory.schemas import TriggerSource
    assert TriggerSource.SPEECH_DEVIATION.value == "speech_deviation"
```

**Step 2: Run test to verify it fails**

`pytest tests/test_trigger_layer.py::test_speech_deviation_trigger_source_exists -v`
Expected: FAIL — `AttributeError: SPEECH_DEVIATION`

**Step 3: Add the enum value**

In `src/castelino/memory/schemas.py`, find `class TriggerSource(str, Enum)` and add:
```python
SPEECH_DEVIATION = "speech_deviation"
```

**Step 4: Run test to verify it passes**

`pytest tests/test_trigger_layer.py::test_speech_deviation_trigger_source_exists -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/memory/schemas.py tests/test_trigger_layer.py
git commit -m "feat(triggers): add SPEECH_DEVIATION TriggerSource"
```

---

## Task 2: Create the hawkish/dovish lexicon YAML

**Files:**
- Create: `data/lexicons/hawkish_dovish_v1.yaml`
- Test: `tests/test_speech_lexicon.py` (new)

**Step 1: Write the failing test**

```python
# tests/test_speech_lexicon.py
from pathlib import Path
import yaml

def test_lexicon_v1_loads_with_required_sections():
    path = Path("data/lexicons/hawkish_dovish_v1.yaml")
    data = yaml.safe_load(path.read_text())
    assert data["version"] == "v1"
    assert isinstance(data["hawkish_phrases"], dict)
    assert isinstance(data["dovish_phrases"], dict)
    assert isinstance(data["hedges"], list)
    assert all(0.0 < w <= 1.0 for w in data["hawkish_phrases"].values())
    assert all(-1.0 <= w < 0.0 for w in data["dovish_phrases"].values())

def test_lexicon_has_at_least_30_signal_phrases():
    path = Path("data/lexicons/hawkish_dovish_v1.yaml")
    data = yaml.safe_load(path.read_text())
    total = len(data["hawkish_phrases"]) + len(data["dovish_phrases"])
    assert total >= 30, "lexicon too thin to be meaningful"
```

**Step 2: Run test to verify it fails**

`pytest tests/test_speech_lexicon.py -v`
Expected: FAIL — file not found.

**Step 3: Create the lexicon file**

```yaml
# data/lexicons/hawkish_dovish_v1.yaml
version: v1
description: Hawkish/dovish signal lexicon for Fed speech analysis. v1 seed.

hawkish_phrases:
  "further firming": 0.7
  "further tightening": 0.7
  "act decisively": 0.6
  "remain restrictive": 0.6
  "additional firming": 0.65
  "more restrictive": 0.6
  "elevated price pressures": 0.5
  "inflation persistent": 0.5
  "persistent inflation": 0.5
  "inflation remains too high": 0.55
  "tight labor market": 0.3
  "robust labor market": 0.25
  "policy firming": 0.55
  "warranted": 0.35
  "vigilant": 0.35
  "more work to do": 0.45
  "long way to go": 0.4

dovish_phrases:
  "patient": -0.4
  "be patient": -0.45
  "accommodative": -0.7
  "moderating": -0.4
  "moderation": -0.35
  "approaching balance": -0.5
  "considerable progress": -0.4
  "good progress": -0.35
  "encouraging": -0.3
  "softening": -0.4
  "easing pressure": -0.45
  "balanced": -0.25
  "well-positioned": -0.3
  "data dependent": -0.15
  "carefully": -0.2
  "gradually": -0.25

hedges:
  - "could"
  - "might"
  - "may"
  - "we'll see"
  - "data will tell"
  - "remains to be seen"
  - "uncertain"
  - "depends on"
  - "subject to"
  - "if appropriate"
```

**Step 4: Run test to verify it passes**

`pytest tests/test_speech_lexicon.py -v`
Expected: PASS (both tests).

**Step 5: Commit**

```bash
git add data/lexicons/hawkish_dovish_v1.yaml tests/test_speech_lexicon.py
git commit -m "feat(speech): seed hawkish/dovish lexicon v1"
```

---

## Task 3: Implement `score_sentence()`

**Files:**
- Create: `src/castelino/triggers/speech/__init__.py`
- Create: `src/castelino/triggers/speech/scorer.py`
- Test: `tests/test_speech_scorer.py` (new)

**Step 1: Write the failing tests**

```python
# tests/test_speech_scorer.py
import pytest
from castelino.triggers.speech.scorer import score_sentence, load_lexicon

LEX = load_lexicon("hawkish_dovish_v1")

def test_neutral_sentence_scores_near_zero():
    s = score_sentence("Today the Committee met to discuss policy.", lexicon=LEX)
    assert -0.05 <= s <= 0.05

def test_hawkish_phrase_scores_positive():
    s = score_sentence("Further firming may be warranted.", lexicon=LEX)
    assert s > 0.5

def test_dovish_phrase_scores_negative():
    s = score_sentence("We will be patient and remain accommodative.", lexicon=LEX)
    assert s < -0.5

def test_clipped_to_unit_range():
    s = score_sentence(
        "Further firming further tightening additional firming remain restrictive.",
        lexicon=LEX,
    )
    assert -1.0 <= s <= 1.0

def test_hedging_dampens_magnitude():
    bare = score_sentence("Inflation will remain elevated.", lexicon=LEX)
    hedged = score_sentence("Inflation could possibly remain elevated.", lexicon=LEX)
    assert abs(hedged) < abs(bare)
```

**Step 2: Run tests to verify they fail**

`pytest tests/test_speech_scorer.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# src/castelino/triggers/speech/__init__.py
"""Live Fed speech trigger source — STT + persona-based deviation scoring."""
```

```python
# src/castelino/triggers/speech/scorer.py
"""Sentence-level hawkish/dovish scorer.

The scoring function is the load-bearing invariant: identical scoring is used
for both the offline persona baseline and the live listener, so z-score
deviations compare like-for-like. If the lexicon changes, version it (v2,
v3, ...) and rebuild every persona from the historical corpus.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Lexicon:
    version: str
    hawkish_phrases: dict[str, float]
    dovish_phrases: dict[str, float]
    hedges: tuple[str, ...]


def load_lexicon(version: str = "hawkish_dovish_v1") -> Lexicon:
    path = Path("data/lexicons") / f"{version}.yaml"
    raw = yaml.safe_load(path.read_text())
    return Lexicon(
        version=raw["version"],
        hawkish_phrases=dict(raw["hawkish_phrases"]),
        dovish_phrases=dict(raw["dovish_phrases"]),
        hedges=tuple(raw["hedges"]),
    )


def score_sentence(text: str, *, lexicon: Lexicon) -> float:
    """Score a sentence on hawkish-dovish ∈ [-1, +1]. Hedges dampen magnitude."""
    lowered = text.lower()
    raw = 0.0
    for phrase, weight in lexicon.hawkish_phrases.items():
        if phrase in lowered:
            raw += weight
    for phrase, weight in lexicon.dovish_phrases.items():
        if phrase in lowered:
            raw += weight  # weight is already negative

    hedge_count = sum(1 for h in lexicon.hedges if h in lowered)
    if hedge_count > 0:
        raw *= max(0.4, 1.0 - 0.2 * hedge_count)

    return max(-1.0, min(1.0, raw))
```

**Step 4: Run tests to verify they pass**

`pytest tests/test_speech_scorer.py -v`
Expected: 5/5 PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/ tests/test_speech_scorer.py
git commit -m "feat(speech): score_sentence() lexicon scorer with hedge dampening"
```

---

## Task 4: Pydantic models for persona

**Files:**
- Create: `src/castelino/triggers/speech/models.py`
- Test: `tests/test_speech_models.py` (new)

**Step 1: Write the failing tests**

```python
# tests/test_speech_models.py
from datetime import datetime, UTC
from castelino.triggers.speech.models import (
    BaselineVector, ScoredSpeech, SpeakerPersona, SpeechSegment,
)

def test_scored_speech_round_trips_json():
    s = ScoredSpeech(
        speech_id="20260301-powell-brookings",
        date=datetime(2026, 3, 1, tzinfo=UTC),
        venue="Brookings",
        score=-0.22,
        n_policy_sentences=84,
    )
    assert ScoredSpeech.model_validate_json(s.model_dump_json()) == s

def test_baseline_vector_validates():
    bv = BaselineVector(
        hawkish_dovish_mean=-0.15,
        hawkish_dovish_std=0.20,
        key_phrase_frequencies={"data dependent": 0.85},
        hedging_density=0.18,
    )
    assert bv.hawkish_dovish_mean == -0.15

def test_speaker_persona_round_trips():
    bv = BaselineVector(
        hawkish_dovish_mean=-0.15, hawkish_dovish_std=0.20,
        key_phrase_frequencies={}, hedging_density=0.18,
    )
    p = SpeakerPersona(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair, Federal Reserve",
        baseline_window_days=365,
        last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=bv,
        lexicon_version="hawkish_dovish_v1",
    )
    assert SpeakerPersona.model_validate_json(p.model_dump_json()).speaker_id == "powell"

def test_speech_segment_immutable_text():
    seg = SpeechSegment(
        speaker_id="powell",
        text="Further firming may be warranted.",
        timestamp=datetime.now(UTC),
        event_id="fomc-2026-04",
    )
    assert seg.text.startswith("Further")
```

**Step 2: Run tests to verify they fail**

`pytest tests/test_speech_models.py -v`
Expected: FAIL — module not found.

**Step 3: Implement**

```python
# src/castelino/triggers/speech/models.py
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class ScoredSpeech(BaseModel):
    speech_id: str
    date: datetime
    venue: str = ""
    score: float = Field(ge=-1.0, le=1.0)
    n_policy_sentences: int = Field(ge=0)


class BaselineVector(BaseModel):
    hawkish_dovish_mean: float = Field(ge=-1.0, le=1.0)
    hawkish_dovish_std: float = Field(ge=0.0)
    key_phrase_frequencies: dict[str, float] = Field(default_factory=dict)
    hedging_density: float = Field(ge=0.0, le=1.0)


class SpeakerPersona(BaseModel):
    speaker_id: str
    full_name: str
    role: str
    baseline_window_days: int = 365
    last_updated: datetime
    speeches_in_window: list[ScoredSpeech] = Field(default_factory=list)
    baseline_vector: BaselineVector
    lexicon_version: str


class SpeechSegment(BaseModel):
    speaker_id: str
    text: str
    timestamp: datetime
    event_id: str
```

**Step 4: Run tests**

`pytest tests/test_speech_models.py -v`
Expected: 4/4 PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/models.py tests/test_speech_models.py
git commit -m "feat(speech): persona + segment Pydantic models"
```

---

## Task 5: Speech-level aggregator (sentences → speech score)

**Files:**
- Modify: `src/castelino/triggers/speech/scorer.py` (add function)
- Test: `tests/test_speech_scorer.py` (extend)

**Step 1: Write the failing test**

```python
# tests/test_speech_scorer.py — extend
from castelino.triggers.speech.scorer import score_speech, load_lexicon

LEX = load_lexicon("hawkish_dovish_v1")

def test_score_speech_filters_neutral_sentences():
    sentences = [
        "Good morning, everyone.",                    # neutral, filtered
        "Today the Committee met.",                   # neutral, filtered
        "Further firming may be warranted.",          # hawkish ~+0.65
        "Inflation persistent and elevated.",         # hawkish, but with hedge guard
    ]
    result = score_speech(sentences, lexicon=LEX)
    assert result.n_policy_sentences == 2  # neutrals filtered
    assert result.score > 0.3  # mean of policy-relevant sentences only

def test_score_speech_zero_when_no_policy_sentences():
    result = score_speech(["Hello.", "Good to be here."], lexicon=LEX)
    assert result.score == 0.0
    assert result.n_policy_sentences == 0
```

**Step 2: Run test — FAIL (function missing)**

**Step 3: Implement**

Append to `src/castelino/triggers/speech/scorer.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SpeechScoreResult:
    score: float
    n_policy_sentences: int


POLICY_RELEVANT_THRESHOLD = 0.05


def score_speech(sentences: list[str], *, lexicon: Lexicon) -> SpeechScoreResult:
    """Aggregate a speech: mean of policy-relevant sentence scores."""
    scored = [score_sentence(s, lexicon=lexicon) for s in sentences]
    policy = [x for x in scored if abs(x) > POLICY_RELEVANT_THRESHOLD]
    if not policy:
        return SpeechScoreResult(score=0.0, n_policy_sentences=0)
    return SpeechScoreResult(
        score=sum(policy) / len(policy),
        n_policy_sentences=len(policy),
    )
```

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/scorer.py tests/test_speech_scorer.py
git commit -m "feat(speech): aggregate sentence scores into speech score"
```

---

## Task 6: Baseline aggregator (speeches → time-weighted mean/std)

**Files:**
- Create: `src/castelino/triggers/speech/baseline.py`
- Test: `tests/test_speech_baseline.py` (new)

**Step 1: Write the failing tests**

```python
# tests/test_speech_baseline.py
import math
from datetime import datetime, timedelta, UTC
from castelino.triggers.speech.baseline import build_baseline
from castelino.triggers.speech.models import ScoredSpeech

def _ss(score: float, days_ago: int) -> ScoredSpeech:
    return ScoredSpeech(
        speech_id=f"s-{days_ago}",
        date=datetime.now(UTC) - timedelta(days=days_ago),
        score=score,
        n_policy_sentences=10,
    )

def test_baseline_unweighted_mean_when_half_life_is_huge():
    speeches = [_ss(0.0, 30), _ss(-0.4, 60), _ss(0.4, 90)]
    bv = build_baseline(speeches, half_life_months=10000)
    assert bv.hawkish_dovish_mean == pytest.approx(0.0, abs=1e-3)

def test_baseline_recent_weighted_higher():
    speeches = [_ss(+1.0, 1), _ss(-1.0, 365)]
    bv = build_baseline(speeches, half_life_months=6)
    assert bv.hawkish_dovish_mean > 0.5  # recent dominates

def test_baseline_std_tracks_dispersion():
    tight = [_ss(0.1, i) for i in range(1, 11)]
    wide = [_ss(0.5 if i % 2 else -0.3, i) for i in range(1, 11)]
    assert build_baseline(tight, half_life_months=6).hawkish_dovish_std < \
           build_baseline(wide, half_life_months=6).hawkish_dovish_std

def test_baseline_empty_raises():
    import pytest as _pt
    with _pt.raises(ValueError):
        build_baseline([], half_life_months=6)
```

(Add `import pytest` at top of test file.)

**Step 2: Run — FAIL (module missing)**

**Step 3: Implement**

```python
# src/castelino/triggers/speech/baseline.py
"""Aggregate scored speeches into a time-weighted BaselineVector."""
from __future__ import annotations

import math
from datetime import datetime, UTC

from castelino.triggers.speech.models import BaselineVector, ScoredSpeech


def _months_ago(d: datetime) -> float:
    delta = datetime.now(UTC) - d
    return delta.total_seconds() / (30.44 * 86400)


def build_baseline(
    speeches: list[ScoredSpeech],
    *,
    half_life_months: float = 6.0,
    key_phrase_frequencies: dict[str, float] | None = None,
    hedging_density: float = 0.0,
) -> BaselineVector:
    if not speeches:
        raise ValueError("Cannot build baseline from empty speech list")

    decay = math.log(2.0) / half_life_months
    weights = [math.exp(-decay * _months_ago(s.date)) for s in speeches]
    total_w = sum(weights)
    mean = sum(w * s.score for w, s in zip(weights, speeches)) / total_w

    var = sum(w * (s.score - mean) ** 2 for w, s in zip(weights, speeches)) / total_w
    std = math.sqrt(var) or 0.05  # floor to avoid divide-by-zero in z-score later

    return BaselineVector(
        hawkish_dovish_mean=mean,
        hawkish_dovish_std=std,
        key_phrase_frequencies=key_phrase_frequencies or {},
        hedging_density=hedging_density,
    )
```

**Step 4: Run tests** — Expected: 4/4 PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/baseline.py tests/test_speech_baseline.py
git commit -m "feat(speech): time-weighted baseline aggregator with std floor"
```

---

## Task 7: Fed website scraper

**Files:**
- Create: `src/castelino/triggers/speech/scrapers/__init__.py`
- Create: `src/castelino/triggers/speech/scrapers/fed.py`
- Test: `tests/test_speech_scraper_fed.py` (new)
- Add dep: `beautifulsoup4` (verify in `pyproject.toml`)

**Step 1: Confirm/Add dependency**

```bash
grep -E "beautifulsoup4|httpx" pyproject.toml
# If beautifulsoup4 missing, add it under [project] dependencies and run:
pip install -e .
```

**Step 2: Write the failing tests**

```python
# tests/test_speech_scraper_fed.py
from datetime import datetime
from pathlib import Path
import pytest
from castelino.triggers.speech.scrapers.fed import (
    parse_speech_page, parse_speech_index,
)

FIXTURES = Path(__file__).parent / "fixtures" / "fed"

def test_parse_speech_page_extracts_text_and_metadata():
    html = (FIXTURES / "powell_2026-03-01_brookings.html").read_text()
    parsed = parse_speech_page(html, url="https://example/2026/powell.htm")
    assert "Jerome H. Powell" in parsed.speaker
    assert parsed.date.year == 2026
    assert len(parsed.text) > 500
    assert "Brookings" in parsed.venue or parsed.venue != ""

def test_parse_speech_index_returns_links():
    html = (FIXTURES / "speech_index_2026.html").read_text()
    items = parse_speech_index(html, base_url="https://federalreserve.gov")
    assert len(items) >= 1
    assert all(item.url.startswith("https://") for item in items)
    assert all(item.speaker for item in items)
```

Provide minimal HTML fixtures under `tests/fixtures/fed/` — one speech page and one index page (use real Fed HTML, anonymized as needed; ~50-100 lines each is enough).

**Step 3: Run — FAIL (module + fixtures missing)**

**Step 4: Implement scraper**

```python
# src/castelino/triggers/speech/scrapers/fed.py
"""Scrape federalreserve.gov speeches by speaker.

Layout (as of 2026):
- Index: federalreserve.gov/newsevents/speech/<year>-speeches.htm
- Detail: federalreserve.gov/newsevents/speech/<speaker>YYYYMMDDa.htm
HTML is mostly stable but parsing is defensive.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, UTC
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class SpeechIndexItem:
    url: str
    speaker: str
    date: datetime
    title: str


@dataclass(frozen=True)
class ParsedSpeech:
    speaker: str
    date: datetime
    venue: str
    title: str
    text: str
    url: str


_DATE_RX = re.compile(r"(\w+ \d+, \d{4})")


def parse_speech_page(html: str, *, url: str) -> ParsedSpeech:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.find("h3", class_="title") or soup.find("h1") or soup.title or soup).get_text(strip=True)
    speaker = (soup.find("p", class_="speaker") or soup.find(class_="byline"))
    speaker_txt = speaker.get_text(strip=True) if speaker else ""
    date_blob = soup.find("p", class_="article__time") or soup.find(class_="article-date")
    date_txt = date_blob.get_text(strip=True) if date_blob else ""
    m = _DATE_RX.search(date_txt) or _DATE_RX.search(html[:5000])
    date = datetime.strptime(m.group(1), "%B %d, %Y").replace(tzinfo=UTC) if m else datetime.now(UTC)
    venue_blob = soup.find("p", class_="location") or soup.find(class_="article__location")
    venue = venue_blob.get_text(strip=True) if venue_blob else ""
    body = soup.find("div", id="article") or soup.find("div", class_="col-xs-12 col-sm-8 col-md-8")
    text = body.get_text(" ", strip=True) if body else soup.get_text(" ", strip=True)
    return ParsedSpeech(
        speaker=speaker_txt, date=date, venue=venue, title=title, text=text, url=url,
    )


def parse_speech_index(html: str, *, base_url: str) -> list[SpeechIndexItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[SpeechIndexItem] = []
    for row in soup.select("div.row.eventlist__item, .panel--default tr, .speech-item"):
        link = row.find("a", href=True)
        if not link:
            continue
        url = urljoin(base_url, link["href"])
        title = link.get_text(strip=True)
        speaker_el = row.find(class_="speaker") or row.find_all("td")
        speaker = speaker_el.get_text(strip=True) if hasattr(speaker_el, "get_text") else ""
        date_blob = row.find("time") or row
        m = _DATE_RX.search(date_blob.get_text(" ", strip=True))
        date = datetime.strptime(m.group(1), "%B %d, %Y").replace(tzinfo=UTC) if m else datetime.now(UTC)
        items.append(SpeechIndexItem(url=url, speaker=speaker, date=date, title=title))
    return items
```

Add a thin async fetcher in the same module:

```python
import httpx

INDEX_URL = "https://www.federalreserve.gov/newsevents/speech/{year}-speeches.htm"

async def fetch_speeches_for_speaker(
    *, speaker_match: str, year: int, client: httpx.AsyncClient,
) -> list[ParsedSpeech]:
    idx_html = (await client.get(INDEX_URL.format(year=year))).text
    items = [i for i in parse_speech_index(idx_html, base_url=str(client.base_url) or "https://www.federalreserve.gov")
             if speaker_match.lower() in i.speaker.lower()]
    out: list[ParsedSpeech] = []
    for item in items:
        html = (await client.get(item.url)).text
        out.append(parse_speech_page(html, url=item.url))
    return out
```

**Step 5: Run tests** — Expected: 2/2 PASS.

**Step 6: Commit**

```bash
git add src/castelino/triggers/speech/scrapers/ tests/test_speech_scraper_fed.py tests/fixtures/fed/
git commit -m "feat(speech): scraper for federalreserve.gov speech pages"
```

---

## Task 8: Sentence splitter (transcript → list[str])

**Files:**
- Modify: `src/castelino/triggers/speech/scorer.py` (add helper)
- Test: `tests/test_speech_scorer.py` (extend)

**Step 1: Write the failing test**

```python
def test_split_sentences_handles_abbreviations():
    from castelino.triggers.speech.scorer import split_sentences
    text = "The U.S. economy grew. Inflation cooled. Mr. Powell spoke."
    out = split_sentences(text)
    assert len(out) == 3
    assert out[0].startswith("The U.S.")
```

**Step 2: Run — FAIL**

**Step 3: Implement** in `scorer.py`:

```python
import re

# Common abbreviations that should NOT split a sentence
_ABBREV = {"U.S.", "Mr.", "Mrs.", "Dr.", "Sen.", "Rep.", "Gov.", "e.g.", "i.e.", "vs.", "etc."}

def split_sentences(text: str) -> list[str]:
    placeholder_text = text
    for abbr in _ABBREV:
        placeholder_text = placeholder_text.replace(abbr, abbr.replace(".", "<DOT>"))
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", placeholder_text)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]
```

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/scorer.py tests/test_speech_scorer.py
git commit -m "feat(speech): sentence splitter that respects U.S./Mr. abbreviations"
```

---

## Task 9: Persona builder orchestrator

**Files:**
- Create: `src/castelino/triggers/speech/persona.py`
- Test: `tests/test_speech_persona.py` (new)

**Step 1: Write the failing tests**

```python
# tests/test_speech_persona.py
import json
from datetime import datetime, timedelta, UTC
from pathlib import Path

import pytest

from castelino.triggers.speech.persona import (
    build_persona_from_speeches, load_persona, save_persona,
)
from castelino.triggers.speech.scrapers.fed import ParsedSpeech


def _ps(text: str, days_ago: int) -> ParsedSpeech:
    return ParsedSpeech(
        speaker="Jerome H. Powell",
        date=datetime.now(UTC) - timedelta(days=days_ago),
        venue="Test",
        title="t",
        text=text,
        url=f"https://x/{days_ago}",
    )

def test_build_persona_aggregates_correctly(tmp_path, monkeypatch):
    # 3 fixture speeches: dovish, neutral, hawkish
    speeches = [
        _ps("We will be patient. Accommodative for now. Considerable progress.", 30),
        _ps("The economy is balanced. Risks remain two-sided.", 60),
        _ps("Further firming may be warranted. Inflation persistent.", 10),
    ]
    persona = build_persona_from_speeches(
        speaker_id="powell",
        full_name="Jerome H. Powell",
        role="Chair, Federal Reserve",
        speeches=speeches,
        lexicon_version="hawkish_dovish_v1",
    )
    assert persona.speaker_id == "powell"
    assert len(persona.speeches_in_window) == 3
    assert persona.baseline_vector.hawkish_dovish_std > 0.0
    assert persona.lexicon_version == "hawkish_dovish_v1"

def test_save_and_load_persona_round_trip(tmp_path):
    from castelino.triggers.speech.models import (
        BaselineVector, SpeakerPersona,
    )
    p = SpeakerPersona(
        speaker_id="powell", full_name="J.P.", role="Chair",
        baseline_window_days=365, last_updated=datetime.now(UTC),
        speeches_in_window=[],
        baseline_vector=BaselineVector(
            hawkish_dovish_mean=0.0, hawkish_dovish_std=0.1,
            key_phrase_frequencies={}, hedging_density=0.1,
        ),
        lexicon_version="hawkish_dovish_v1",
    )
    save_persona(p, root=tmp_path)
    loaded = load_persona("powell", root=tmp_path)
    assert loaded == p
```

**Step 2: Run — FAIL (module missing)**

**Step 3: Implement**

```python
# src/castelino/triggers/speech/persona.py
"""Persona builder + persistence."""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from castelino.config import get_settings
from castelino.triggers.speech.baseline import build_baseline
from castelino.triggers.speech.models import (
    BaselineVector, ScoredSpeech, SpeakerPersona,
)
from castelino.triggers.speech.scorer import (
    Lexicon, load_lexicon, score_speech, split_sentences,
)
from castelino.triggers.speech.scrapers.fed import ParsedSpeech


def _personas_dir(root: Path | None = None) -> Path:
    if root is not None:
        return root / "personas"
    return get_settings().resolved_paths.data / "personas"


def build_persona_from_speeches(
    *,
    speaker_id: str,
    full_name: str,
    role: str,
    speeches: list[ParsedSpeech],
    lexicon_version: str,
    baseline_window_days: int = 365,
    half_life_months: float = 6.0,
) -> SpeakerPersona:
    lex = load_lexicon(lexicon_version)
    scored: list[ScoredSpeech] = []
    for sp in speeches:
        sentences = split_sentences(sp.text)
        result = score_speech(sentences, lexicon=lex)
        scored.append(ScoredSpeech(
            speech_id=sp.url.rsplit("/", 1)[-1].replace(".htm", ""),
            date=sp.date, venue=sp.venue, score=result.score,
            n_policy_sentences=result.n_policy_sentences,
        ))
    bv = build_baseline(scored, half_life_months=half_life_months)
    return SpeakerPersona(
        speaker_id=speaker_id, full_name=full_name, role=role,
        baseline_window_days=baseline_window_days,
        last_updated=datetime.now(UTC),
        speeches_in_window=scored, baseline_vector=bv,
        lexicon_version=lexicon_version,
    )


def save_persona(p: SpeakerPersona, *, root: Path | None = None) -> Path:
    d = _personas_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{p.speaker_id}.json"
    path.write_text(p.model_dump_json(indent=2))
    return path


def load_persona(speaker_id: str, *, root: Path | None = None) -> SpeakerPersona:
    path = _personas_dir(root) / f"{speaker_id}.json"
    return SpeakerPersona.model_validate_json(path.read_text())
```

**Step 4: Run tests** — Expected: 2/2 PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/persona.py tests/test_speech_persona.py
git commit -m "feat(speech): persona builder + JSON persistence"
```

---

## Task 10: Rolling sentence window + Stage A z-score

**Files:**
- Create: `src/castelino/triggers/speech/deviation.py`
- Test: `tests/test_speech_deviation.py` (new)

**Step 1: Write the failing tests**

```python
# tests/test_speech_deviation.py
from datetime import datetime, UTC
from castelino.triggers.speech.deviation import RollingWindow, compute_deviation
from castelino.triggers.speech.models import BaselineVector

BL = BaselineVector(
    hawkish_dovish_mean=-0.15, hawkish_dovish_std=0.20,
    key_phrase_frequencies={}, hedging_density=0.18,
)

def test_window_keeps_only_last_n():
    w = RollingWindow(size=3)
    for s in [0.1, 0.2, 0.3, 0.4]:
        w.push(s)
    assert w.values() == [0.2, 0.3, 0.4]

def test_window_min_required_blocks_score():
    w = RollingWindow(size=5, min_required=3)
    w.push(0.5)
    assert w.mean() is None  # not enough
    w.push(0.5); w.push(0.5)
    assert w.mean() == 0.5

def test_compute_deviation_against_dovish_baseline():
    # baseline mean -0.15, std 0.20; window mean +0.38 → ~+2.65σ
    sigma = compute_deviation(window_mean=0.38, baseline=BL)
    assert 2.5 < sigma < 2.8

def test_compute_deviation_returns_zero_when_at_baseline():
    sigma = compute_deviation(window_mean=-0.15, baseline=BL)
    assert sigma == 0.0
```

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# src/castelino/triggers/speech/deviation.py
"""Rolling window + z-score deviation calculator (Stage A)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from castelino.triggers.speech.models import BaselineVector


@dataclass
class RollingWindow:
    size: int
    min_required: int = 3
    _buf: deque = None  # set in __post_init__

    def __post_init__(self):
        self._buf = deque(maxlen=self.size)

    def push(self, score: float) -> None:
        self._buf.append(score)

    def values(self) -> list[float]:
        return list(self._buf)

    def mean(self) -> float | None:
        if len(self._buf) < self.min_required:
            return None
        return sum(self._buf) / len(self._buf)


def compute_deviation(*, window_mean: float, baseline: BaselineVector) -> float:
    """Z-score: how many σ is the rolling window from the speaker's baseline?"""
    return (window_mean - baseline.hawkish_dovish_mean) / baseline.hawkish_dovish_std
```

**Step 4: Run tests** — Expected: 4/4 PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/deviation.py tests/test_speech_deviation.py
git commit -m "feat(speech): rolling window + Stage-A z-score deviation"
```

---

## Task 11: Stage B LLM confirmation (StructuredAgent)

**Files:**
- Create: `src/castelino/triggers/speech/llm_gate.py`
- Test: `tests/test_speech_llm_gate.py` (new)

Mirrors the pattern of `triggers/significance.py`.

**Step 1: Write the failing tests**

```python
# tests/test_speech_llm_gate.py
from castelino.agents.base import FakeLLMClient
from castelino.triggers.speech.llm_gate import (
    SpeechShiftClassification, classify_speech_shift,
)
from castelino.triggers.speech.models import BaselineVector

BL = BaselineVector(
    hawkish_dovish_mean=-0.15, hawkish_dovish_std=0.20,
    key_phrase_frequencies={}, hedging_density=0.18,
)

def test_classify_speech_shift_returns_structured_output():
    fake = FakeLLMClient(canned=SpeechShiftClassification(
        is_shift=True, direction="hawkish", magnitude=0.7,
        decisive_phrase="Further policy firming may be warranted.",
        rationale="Out-of-character for Powell's recent baseline.",
    ))
    result = classify_speech_shift(
        client=fake,
        full_name="Jerome H. Powell",
        baseline=BL,
        rolling_window_text="Further firming may be warranted...",
    )
    assert result.is_shift is True
    assert result.direction == "hawkish"
    assert fake.stats.n_calls == 1
```

(May need to extend `FakeLLMClient` to accept canned typed responses — check `agents/base.py` for the exact contract.)

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# src/castelino/triggers/speech/llm_gate.py
"""Stage B — LLM confirmation gate for tone shifts.

Only invoked when Stage A z-score crosses the threshold. Mirrors
significance.score_batch — keeps LLM out of the hot path.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

from castelino.agents.base import LLMClient
from castelino.triggers.speech.models import BaselineVector


class SpeechShiftClassification(BaseModel):
    is_shift: bool
    direction: Literal["hawkish", "dovish", "neutral"]
    magnitude: float = Field(ge=0.0, le=1.0)
    decisive_phrase: str
    rationale: str


SYSTEM = """\
You evaluate whether a Fed speaker has shifted tone meaningfully relative to
their own recent baseline. Be skeptical: only flag a shift if the phrasing
is materially different from how this person has been talking. A hawk being
hawkish is NOT a shift. A dove turning hawkish IS.
Return JSON only.
"""

USER = """\
Speaker: {full_name}
Their recent baseline tone: hawkish_dovish_mean={mean:+.2f}, std={std:.2f}
(negative = dovish, positive = hawkish)

The last few sentences they spoke:
\"\"\"{window}\"\"\"

Is this a meaningful tone shift relative to their baseline?
"""


def classify_speech_shift(
    *,
    client: LLMClient,
    full_name: str,
    baseline: BaselineVector,
    rolling_window_text: str,
    model: str = "gpt-4o-mini",
) -> SpeechShiftClassification:
    return client.parse(
        model=model,
        system=SYSTEM,
        user=USER.format(
            full_name=full_name,
            mean=baseline.hawkish_dovish_mean,
            std=baseline.hawkish_dovish_std,
            window=rolling_window_text,
        ),
        schema=SpeechShiftClassification,
        max_completion_tokens=400,
    )
```

> **HONOR LEARNING**: use `chat.completions.parse(...)` (not `.beta.`) and `max_completion_tokens` (not `max_tokens`). Implementation goes via `LLMClient.parse` which already does this — see `agents/base.py`.

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/llm_gate.py tests/test_speech_llm_gate.py
git commit -m "feat(speech): Stage-B LLM confirmation classifier"
```

---

## Task 12: Trigger emitter (cooldown + structural threshold gating)

**Files:**
- Create: `src/castelino/triggers/speech/emitter.py`
- Test: `tests/test_speech_emitter.py` (new)

**Step 1: Write the failing tests**

```python
# tests/test_speech_emitter.py
from datetime import datetime, UTC
from castelino.agents.base import FakeLLMClient
from castelino.triggers.speech.emitter import SpeechTriggerEmitter
from castelino.triggers.speech.llm_gate import SpeechShiftClassification
from castelino.triggers.speech.models import BaselineVector, SpeechSegment

BL = BaselineVector(
    hawkish_dovish_mean=-0.15, hawkish_dovish_std=0.20,
    key_phrase_frequencies={}, hedging_density=0.18,
)

CANNED_SHIFT = SpeechShiftClassification(
    is_shift=True, direction="hawkish", magnitude=0.7,
    decisive_phrase="Further policy firming may be warranted.", rationale="ok",
)
CANNED_NO_SHIFT = SpeechShiftClassification(
    is_shift=False, direction="neutral", magnitude=0.0,
    decisive_phrase="", rationale="baseline",
)

def _seg(text: str) -> SpeechSegment:
    return SpeechSegment(
        speaker_id="powell", text=text, timestamp=datetime.now(UTC),
        event_id="fomc-2026-04",
    )

def test_emitter_below_threshold_no_llm_no_trigger():
    fake = FakeLLMClient(canned=CANNED_NO_SHIFT)
    em = SpeechTriggerEmitter(
        speaker_id="powell", full_name="J.P.", baseline=BL,
        threshold_sigma=1.5, llm_client=fake,
    )
    for txt in ["Today the Committee met.", "Hello, everyone."]:
        em.ingest(_seg(txt))
    assert em.triggers == []
    assert fake.stats.n_calls == 0  # below threshold = no LLM call

def test_emitter_above_threshold_with_confirmation_emits_trigger():
    fake = FakeLLMClient(canned=CANNED_SHIFT)
    em = SpeechTriggerEmitter(
        speaker_id="powell", full_name="Jerome H. Powell", baseline=BL,
        threshold_sigma=1.5, llm_client=fake,
    )
    for txt in [
        "Further firming may be warranted.",
        "Inflation persistent and elevated.",
        "We will act decisively.",
        "Persistent inflation requires policy firming.",
        "Remain restrictive.",
    ]:
        em.ingest(_seg(txt))
    assert len(em.triggers) == 1
    trg = em.triggers[0]
    assert trg.source.value == "speech_deviation"
    assert "shift" in trg.headline.lower()

def test_emitter_cooldown_caps_at_one_trigger_per_event():
    fake = FakeLLMClient(canned=CANNED_SHIFT)
    em = SpeechTriggerEmitter(
        speaker_id="powell", full_name="J.P.", baseline=BL,
        threshold_sigma=1.5, llm_client=fake,
    )
    sustained = ["Further firming may be warranted."] * 20
    for txt in sustained:
        em.ingest(_seg(txt))
    assert len(em.triggers) == 1  # cooldown
```

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# src/castelino/triggers/speech/emitter.py
"""Real-time emitter: ingests SpeechSegments, emits TriggerRecords on shifts.

Structural guarantees:
- Threshold check is enforced BEFORE LLM call (no LLM cost on calm speech).
- Cooldown caps emissions at one per event_id (no flood from sustained shifts).
- Both Stage A (|σ| > threshold) AND Stage B (LLM is_shift=True) must agree.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from castelino.agents.base import LLMClient
from castelino.memory.schemas import TriggerRecord, TriggerSource
from castelino.triggers.speech.deviation import RollingWindow, compute_deviation
from castelino.triggers.speech.llm_gate import (
    SpeechShiftClassification, classify_speech_shift,
)
from castelino.triggers.speech.models import BaselineVector, SpeechSegment
from castelino.triggers.speech.scorer import (
    POLICY_RELEVANT_THRESHOLD, load_lexicon, score_sentence,
)

log = logging.getLogger(__name__)


@dataclass
class SpeechTriggerEmitter:
    speaker_id: str
    full_name: str
    baseline: BaselineVector
    threshold_sigma: float
    llm_client: LLMClient
    lexicon_version: str = "hawkish_dovish_v1"
    window_size: int = 5
    triggers: list[TriggerRecord] = field(default_factory=list)
    _fired_event_ids: set[str] = field(default_factory=set)
    _windows_by_event: dict[str, RollingWindow] = field(default_factory=dict)
    _texts_by_event: dict[str, list[str]] = field(default_factory=dict)
    _lexicon = None

    def __post_init__(self):
        self._lexicon = load_lexicon(self.lexicon_version)

    def ingest(self, segment: SpeechSegment) -> None:
        if segment.event_id in self._fired_event_ids:
            return  # cooldown
        score = score_sentence(segment.text, lexicon=self._lexicon)
        win = self._windows_by_event.setdefault(
            segment.event_id, RollingWindow(size=self.window_size, min_required=3),
        )
        texts = self._texts_by_event.setdefault(segment.event_id, [])
        if abs(score) > POLICY_RELEVANT_THRESHOLD:
            win.push(score)
            texts.append(segment.text)
            if len(texts) > self.window_size:
                texts.pop(0)
        win_mean = win.mean()
        if win_mean is None:
            return
        sigma = compute_deviation(window_mean=win_mean, baseline=self.baseline)
        if abs(sigma) <= self.threshold_sigma:
            return
        # Stage B: confirm with LLM
        verdict = classify_speech_shift(
            client=self.llm_client,
            full_name=self.full_name,
            baseline=self.baseline,
            rolling_window_text=" ".join(texts),
        )
        if not verdict.is_shift:
            log.info("speech: σ=%.2f exceeded but LLM disagreed", sigma)
            return
        self._emit(segment, sigma, verdict)

    def _emit(self, segment, sigma, verdict: SpeechShiftClassification) -> None:
        trg = TriggerRecord(
            source=TriggerSource.SPEECH_DEVIATION,
            headline=f"{self.full_name}: {verdict.direction} shift mid-speech",
            significance=min(0.95, 0.6 + 0.3 * verdict.magnitude),
            asset_classes_affected=["rates", "equities", "fx"],
            raw_event_data={
                "speaker_id": self.speaker_id,
                "deviation_sigma": sigma,
                "decisive_phrase": verdict.decisive_phrase,
                "transcript_window": " ".join(self._texts_by_event[segment.event_id]),
                "event_id": segment.event_id,
            },
            one_sentence_reason=(
                f"{self.full_name} shifted {verdict.direction} "
                f"({sigma:+.1f}σ): «{verdict.decisive_phrase}»"
            ),
        )
        self.triggers.append(trg)
        self._fired_event_ids.add(segment.event_id)
```

**Step 4: Run tests** — Expected: 3/3 PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/emitter.py tests/test_speech_emitter.py
git commit -m "feat(speech): trigger emitter with structural threshold + cooldown"
```

---

## Task 13: SpeechToTextProvider interface + Fake

**Files:**
- Create: `src/castelino/triggers/speech/stt.py`
- Test: `tests/test_speech_stt_fake.py` (new)

**Step 1: Write the failing tests**

```python
# tests/test_speech_stt_fake.py
import asyncio
from datetime import datetime, UTC
from castelino.triggers.speech.stt import FakeSTTProvider, TranscriptEvent

def test_fake_stt_yields_canned_sequence():
    canned = [
        TranscriptEvent(text="Hello.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Further firming.", timestamp=datetime.now(UTC), is_final=True),
    ]
    provider = FakeSTTProvider(canned=canned)
    async def collect():
        out = []
        async for ev in provider.stream(audio_url="fake://"):
            out.append(ev)
        return out
    out = asyncio.run(collect())
    assert len(out) == 2
    assert out[1].text == "Further firming."
```

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# src/castelino/triggers/speech/stt.py
"""SpeechToTextProvider interface + Fake implementation.

Real Deepgram impl lives in stt_deepgram.py (Task 14) — kept separate so
unit tests don't pull the SDK.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    timestamp: datetime
    is_final: bool


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def stream(self, *, audio_url: str) -> AsyncIterator[TranscriptEvent]:
        ...


class FakeSTTProvider(SpeechToTextProvider):
    """Yields a canned sequence — used by tests and dry-runs."""

    def __init__(self, canned: list[TranscriptEvent]):
        self._canned = list(canned)

    async def stream(self, *, audio_url: str) -> AsyncIterator[TranscriptEvent]:
        for ev in self._canned:
            yield ev
```

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/stt.py tests/test_speech_stt_fake.py
git commit -m "feat(speech): SpeechToTextProvider interface + Fake for tests"
```

---

## Task 14: Deepgram STT provider

**Files:**
- Create: `src/castelino/triggers/speech/stt_deepgram.py`
- Test: `tests/test_speech_stt_deepgram.py` (new)
- Add dep: `deepgram-sdk` (verify in `pyproject.toml`)

**Step 1: Add dependency**

```bash
# In pyproject.toml under [project] dependencies, add:
#   "deepgram-sdk>=3,<4",
pip install -e .
```

**Step 2: Write the failing tests** — mock the SDK so tests don't hit the network.

```python
# tests/test_speech_stt_deepgram.py
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from castelino.triggers.speech.stt_deepgram import DeepgramSTTProvider

def test_deepgram_provider_constructs_with_api_key():
    p = DeepgramSTTProvider(api_key="dg_test", model="nova-2-finance")
    assert p.model == "nova-2-finance"

@patch("castelino.triggers.speech.stt_deepgram.DeepgramClient")
def test_stream_calls_sdk_with_url(mock_dg):
    p = DeepgramSTTProvider(api_key="dg_test", model="nova-2-finance")

    async def go():
        async for _ in p.stream(audio_url="https://stream/x.m3u8"):
            pass
    # Using a fake async iterator; just asserting the SDK got called.
    asyncio.run(go())
    assert mock_dg.called
```

**Step 3: Run — FAIL (module + dep missing)**

**Step 4: Implement** (sketch — adjust to current Deepgram SDK shape):

```python
# src/castelino/triggers/speech/stt_deepgram.py
"""Deepgram streaming provider. Live audio → TranscriptEvent stream."""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, UTC

from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions

from castelino.triggers.speech.stt import (
    SpeechToTextProvider, TranscriptEvent,
)


class DeepgramSTTProvider(SpeechToTextProvider):
    def __init__(self, *, api_key: str, model: str = "nova-2-finance"):
        self.model = model
        self._client = DeepgramClient(api_key)

    async def stream(self, *, audio_url: str) -> AsyncIterator[TranscriptEvent]:
        # NOTE: For URL streaming we use the prerecorded-from-URL path with
        # streaming=true equivalent. Adjust to whatever the SDK exposes for
        # live URL ingestion. Sketch:
        connection = self._client.listen.asynclive.v("1")
        async def on_transcript(_self, result, **_):
            txt = result.channel.alternatives[0].transcript
            if not txt:
                return
            await queue.put(TranscriptEvent(
                text=txt, timestamp=datetime.now(UTC),
                is_final=result.is_final,
            ))

        import asyncio
        queue: asyncio.Queue[TranscriptEvent] = asyncio.Queue()
        connection.on(LiveTranscriptionEvents.Transcript, on_transcript)
        await connection.start(LiveOptions(model=self.model, smart_format=True))
        # ... feed audio_url chunks into connection (impl detail per SDK) ...
        try:
            while True:
                ev = await queue.get()
                yield ev
        finally:
            await connection.finish()
```

> Note: Deepgram SDK shape may have evolved — confirm against current docs (use the doc-search skill) when implementing this task. Treat the sketch as a starting point.

**Step 5: Run tests** — Expected: PASS.

**Step 6: Commit**

```bash
git add src/castelino/triggers/speech/stt_deepgram.py tests/test_speech_stt_deepgram.py pyproject.toml
git commit -m "feat(speech): Deepgram STT provider implementation"
```

---

## Task 15: Stream URL resolver (FOMC presser)

**Files:**
- Create: `src/castelino/triggers/speech/streams.py`
- Test: `tests/test_speech_streams.py` (new)

**Step 1: Write the failing tests**

```python
# tests/test_speech_streams.py
from pathlib import Path
from castelino.triggers.speech.streams import (
    parse_fomc_live_url, FOMC_MONETARY_POLICY_PAGE,
)

FIX = Path(__file__).parent / "fixtures" / "fed"

def test_parse_fomc_live_url_finds_youtube_link():
    html = (FIX / "monetary_policy_page.html").read_text()
    url = parse_fomc_live_url(html)
    assert url is not None
    assert "youtube" in url or "youtu.be" in url

def test_parse_fomc_live_url_returns_none_when_no_link():
    assert parse_fomc_live_url("<html><body>nothing</body></html>") is None
```

Provide a fixture with a YouTube link in the HTML.

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# src/castelino/triggers/speech/streams.py
"""Resolve live audio stream URLs for scheduled Fed events."""
from __future__ import annotations

import re

FOMC_MONETARY_POLICY_PAGE = "https://www.federalreserve.gov/monetarypolicy.htm"

_YT_RX = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+")


def parse_fomc_live_url(html: str) -> str | None:
    m = _YT_RX.search(html)
    return m.group(0) if m else None
```

(A separate async fetcher that GETs the page goes in this same module — keep
parsing pure for unit-testability.)

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/streams.py tests/test_speech_streams.py tests/fixtures/fed/monetary_policy_page.html
git commit -m "feat(speech): FOMC live stream URL resolver"
```

---

## Task 16: Listener — STT events → SpeechSegments

**Files:**
- Create: `src/castelino/triggers/speech/listener.py`
- Test: `tests/test_speech_listener.py` (new)

The listener buffers final transcript events into complete sentences and yields `SpeechSegment` objects.

**Step 1: Write the failing tests**

```python
# tests/test_speech_listener.py
import asyncio
from datetime import datetime, UTC
from castelino.triggers.speech.listener import listen
from castelino.triggers.speech.stt import FakeSTTProvider, TranscriptEvent

def test_listener_buffers_partials_and_emits_per_sentence():
    canned = [
        TranscriptEvent(text="Today the Committee met.", timestamp=datetime.now(UTC), is_final=True),
        TranscriptEvent(text="Further firming may be", timestamp=datetime.now(UTC), is_final=False),
        TranscriptEvent(text="Further firming may be warranted.", timestamp=datetime.now(UTC), is_final=True),
    ]
    provider = FakeSTTProvider(canned=canned)

    async def go():
        out = []
        async for seg in listen(
            provider=provider, audio_url="fake://", speaker_id="powell",
            event_id="fomc-2026-04",
        ):
            out.append(seg)
        return out

    out = asyncio.run(go())
    assert len(out) == 2
    assert out[0].text == "Today the Committee met."
    assert "warranted" in out[1].text
    assert all(seg.event_id == "fomc-2026-04" for seg in out)
```

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# src/castelino/triggers/speech/listener.py
"""Stream listener: STT events → SpeechSegment per complete sentence."""
from __future__ import annotations

from collections.abc import AsyncIterator

from castelino.triggers.speech.models import SpeechSegment
from castelino.triggers.speech.scorer import split_sentences
from castelino.triggers.speech.stt import SpeechToTextProvider


async def listen(
    *,
    provider: SpeechToTextProvider,
    audio_url: str,
    speaker_id: str,
    event_id: str,
) -> AsyncIterator[SpeechSegment]:
    """Yield one SpeechSegment per complete sentence from the live stream."""
    async for ev in provider.stream(audio_url=audio_url):
        if not ev.is_final:
            continue
        for sentence in split_sentences(ev.text):
            yield SpeechSegment(
                speaker_id=speaker_id, text=sentence,
                timestamp=ev.timestamp, event_id=event_id,
            )
```

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/listener.py tests/test_speech_listener.py
git commit -m "feat(speech): listener buffering STT events into sentence segments"
```

---

## Task 17: CalendarEvent extension

**Files:**
- Modify: `src/castelino/triggers/calendar.py` (add fields to `CalendarEvent`)
- Test: `tests/test_speech_calendar_extension.py` (new)

**Step 1: Write the failing test**

```python
# tests/test_speech_calendar_extension.py
from datetime import datetime, UTC
from castelino.triggers.calendar import CalendarEvent

def test_calendar_event_supports_speech_fields():
    e = CalendarEvent(
        name="FOMC Press Conference",
        timestamp=datetime.now(UTC),
        region="US",
        impact="high",
        asset_classes_affected=["rates", "equities"],
        has_live_stream=True,
        speaker_id="powell",
    )
    assert e.has_live_stream is True
    assert e.speaker_id == "powell"

def test_calendar_event_defaults():
    e = CalendarEvent(
        name="x", timestamp=datetime.now(UTC), region="US",
        impact="low", asset_classes_affected=[],
    )
    assert e.has_live_stream is False
    assert e.speaker_id is None
```

**Step 2: Run — FAIL**

**Step 3: Add fields to `CalendarEvent` model** with defaults to avoid breaking existing usage.

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/calendar.py tests/test_speech_calendar_extension.py
git commit -m "feat(triggers): CalendarEvent.has_live_stream + speaker_id"
```

---

## Task 18: Configuration schema

**Files:**
- Modify: `src/castelino/config.py` (`SpeechCfg` model + Settings field)
- Modify: `config.yaml` (default speech section)
- Test: `tests/test_speech_config.py` (new)

**Step 1: Write the failing test**

```python
# tests/test_speech_config.py
from castelino.config import get_settings

def test_speech_config_has_defaults():
    s = get_settings()
    assert s.speech.enabled is True
    assert s.speech.deviation_threshold_sigma == 1.5
    assert s.speech.lexicon_version == "hawkish_dovish_v1"
    assert s.speech.window_size == 5
    assert "powell" in [sp.id for sp in s.speech.speakers]
```

**Step 2: Run — FAIL**

**Step 3: Implement**

In `config.py`:

```python
class SpeechSpeakerCfg(BaseModel):
    id: str
    full_name: str
    role: str

class SpeechCfg(BaseModel):
    enabled: bool = True
    stt_provider: str = "deepgram"
    deepgram_model: str = "nova-2-finance"
    lexicon_version: str = "hawkish_dovish_v1"
    window_size: int = 5
    deviation_threshold_sigma: float = 1.5
    half_life_months: float = 6.0
    baseline_window_days: int = 365
    llm_model: str = "gpt-4o-mini"
    speakers: list[SpeechSpeakerCfg] = Field(default_factory=list)

# Add to Settings:
    speech: SpeechCfg = SpeechCfg()
```

In `config.yaml`:

```yaml
speech:
  enabled: true
  stt_provider: deepgram
  deepgram_model: nova-2-finance
  lexicon_version: hawkish_dovish_v1
  window_size: 5
  deviation_threshold_sigma: 1.5
  half_life_months: 6.0
  baseline_window_days: 365
  llm_model: gpt-4o-mini
  speakers:
    - id: powell
      full_name: Jerome H. Powell
      role: Chair, Federal Reserve
```

**Step 4: Run test** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/config.py config.yaml tests/test_speech_config.py
git commit -m "feat(speech): config schema + Powell default speaker"
```

---

## Task 19: CLI command — `castelino persona-refresh`

**Files:**
- Modify: `src/castelino/orchestrator/cli.py` (add command)
- Test: `tests/test_speech_cli.py` (new)

**Step 1: Write the failing test**

Use `typer.testing.CliRunner` to assert the command exists and accepts the expected args.

```python
# tests/test_speech_cli.py
from typer.testing import CliRunner
from castelino.orchestrator.cli import app

def test_persona_refresh_help_lists_speaker():
    r = CliRunner().invoke(app, ["persona-refresh", "--help"])
    assert r.exit_code == 0
    assert "speaker" in r.stdout.lower()
```

**Step 2: Run — FAIL**

**Step 3: Add command**

```python
# In src/castelino/orchestrator/cli.py
@app.command("persona-refresh")
def persona_refresh(
    speaker: str = typer.Option("powell", help="Speaker id (e.g. powell)."),
    year: int = typer.Option(None, help="Year to scrape; default current."),
):
    """Scrape Fed website and rebuild the rolling-window persona."""
    import asyncio
    import httpx
    from datetime import datetime, UTC
    from castelino.config import get_settings
    from castelino.triggers.speech.persona import (
        build_persona_from_speeches, save_persona,
    )
    from castelino.triggers.speech.scrapers.fed import fetch_speeches_for_speaker

    cfg = get_settings()
    sp = next((s for s in cfg.speech.speakers if s.id == speaker), None)
    if not sp:
        print(f"[red]Unknown speaker:[/red] {speaker}")
        raise typer.Exit(1)
    yr = year or datetime.now(UTC).year

    async def _run():
        async with httpx.AsyncClient(base_url="https://www.federalreserve.gov", timeout=30) as c:
            speeches = await fetch_speeches_for_speaker(
                speaker_match=sp.full_name.split()[-1], year=yr, client=c,
            )
        persona = build_persona_from_speeches(
            speaker_id=sp.id, full_name=sp.full_name, role=sp.role,
            speeches=speeches, lexicon_version=cfg.speech.lexicon_version,
            baseline_window_days=cfg.speech.baseline_window_days,
            half_life_months=cfg.speech.half_life_months,
        )
        path = save_persona(persona)
        print(f"[green]Persona saved:[/green] {path}")
        print(f"  speeches: {len(persona.speeches_in_window)}  "
              f"mean: {persona.baseline_vector.hawkish_dovish_mean:+.3f}  "
              f"std: {persona.baseline_vector.hawkish_dovish_std:.3f}")

    asyncio.run(_run())
```

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/orchestrator/cli.py tests/test_speech_cli.py
git commit -m "feat(cli): castelino persona-refresh"
```

---

## Task 20: Runner integration — drain speech triggers

**Files:**
- Create: `src/castelino/triggers/speech/queue.py` (in-memory triggers queue)
- Modify: `src/castelino/triggers/runner.py` (drain inside `tick()`)
- Test: `tests/test_speech_runner_integration.py` (new)

**Why a queue?** The async listener runs in its own task — it pushes triggers; the synchronous `tick()` drains them. Memory-only queue is fine because triggers carry the event_id; durability is handled by the journal write inside `fire_pipeline`.

**Step 1: Write the failing tests**

```python
# tests/test_speech_runner_integration.py
from castelino.triggers.speech.queue import speech_trigger_queue
from castelino.memory.schemas import TriggerRecord, TriggerSource

def test_queue_offer_and_drain_round_trip():
    speech_trigger_queue.clear()
    speech_trigger_queue.offer(TriggerRecord(
        source=TriggerSource.SPEECH_DEVIATION,
        headline="x", significance=0.8,
        asset_classes_affected=[], one_sentence_reason="x",
    ))
    drained = speech_trigger_queue.drain()
    assert len(drained) == 1
    assert speech_trigger_queue.drain() == []  # idempotent
```

```python
# Same file — wire into runner.tick path
def test_tick_fires_pipeline_when_speech_trigger_present(monkeypatch):
    from castelino.triggers import runner as r
    from castelino.memory.schemas import TriggerRecord, TriggerSource
    from castelino.triggers.speech.queue import speech_trigger_queue

    fired = []
    monkeypatch.setattr(r, "fire_pipeline", lambda trg, **kw: fired.append(trg) or {})
    # Stub other branches so tick doesn't go past speech-drain on its own:
    monkeypatch.setattr(r, "fetch_recent", lambda **kw: [])
    monkeypatch.setattr(r.calmod, "events_due", lambda: [])
    monkeypatch.setattr(r, "_check_regime_shift", lambda s: None)
    monkeypatch.setattr(r, "_check_conviction", lambda lf: (None, []))
    monkeypatch.setattr(r, "_trigger_cron_fallback", lambda lf: None)

    speech_trigger_queue.clear()
    speech_trigger_queue.offer(TriggerRecord(
        source=TriggerSource.SPEECH_DEVIATION,
        headline="Powell hawkish shift", significance=0.85,
        asset_classes_affected=[], one_sentence_reason="x",
    ))
    out = r.tick()
    assert out == "speech"
    assert fired and fired[0].source.value == "speech_deviation"
```

**Step 2: Run — FAIL**

**Step 3: Implement**

```python
# src/castelino/triggers/speech/queue.py
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
```

In `runner.tick()`, **between** calendar (path 0) and black swan (path 1):

```python
    # ── Path 0.5: Speech deviation triggers from live listener ──
    from castelino.triggers.speech.queue import speech_trigger_queue
    pending = speech_trigger_queue.drain()
    if pending:
        trg = pending[0]
        log.info("SPEECH trigger: %s", trg.headline)
        fire_pipeline(trg, recent_headlines=[trg.headline])
        return "speech"
```

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/queue.py src/castelino/triggers/runner.py tests/test_speech_runner_integration.py
git commit -m "feat(speech): in-mem trigger queue + runner.tick integration"
```

---

## Task 21: Speech event persistence

**Files:**
- Create: `src/castelino/triggers/speech/events.py` (event log writer)
- Test: `tests/test_speech_events.py` (new)

Each live event produces one JSON file with the full transcript, scored sentences, and any triggers fired. Used for offline review and the dashboard.

**Step 1: Write the failing test**

```python
# tests/test_speech_events.py
from datetime import datetime, UTC
from pathlib import Path
from castelino.triggers.speech.events import SpeechEventRecord, save_event_record

def test_save_event_record_round_trip(tmp_path):
    rec = SpeechEventRecord(
        event_id="fomc-2026-04",
        speaker_id="powell",
        started_at=datetime.now(UTC),
        scored_sentences=[("Hello.", 0.0), ("Further firming.", 0.7)],
        triggers_fired=[],
    )
    path = save_event_record(rec, root=tmp_path)
    loaded = SpeechEventRecord.model_validate_json(path.read_text())
    assert loaded.event_id == "fomc-2026-04"
    assert len(loaded.scored_sentences) == 2
```

**Step 2: Run — FAIL**

**Step 3: Implement** with a Pydantic model + writer.

```python
# src/castelino/triggers/speech/events.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from castelino.config import get_settings
from castelino.memory.schemas import TriggerRecord


class SpeechEventRecord(BaseModel):
    event_id: str
    speaker_id: str
    started_at: datetime
    scored_sentences: list[tuple[str, float]] = Field(default_factory=list)
    triggers_fired: list[TriggerRecord] = Field(default_factory=list)


def _events_dir(root: Path | None = None) -> Path:
    if root is not None:
        return root / "speech_events"
    return get_settings().resolved_paths.data / "speech_events"


def save_event_record(rec: SpeechEventRecord, *, root: Path | None = None) -> Path:
    d = _events_dir(root); d.mkdir(parents=True, exist_ok=True)
    path = d / f"{rec.event_id}.json"
    path.write_text(rec.model_dump_json(indent=2))
    return path
```

**Step 4: Run tests** — Expected: PASS.

**Step 5: Commit**

```bash
git add src/castelino/triggers/speech/events.py tests/test_speech_events.py
git commit -m "feat(speech): per-event JSON record persistence"
```

---

## Task 22: End-to-end replay test (recorded transcript → triggers)

**Files:**
- Create: `tests/integration/test_speech_replay_e2e.py`
- Create: `tests/fixtures/fed/powell_replay_transcript.txt` (one realistic FOMC presser)

**Step 1: Add a fixture transcript** — ~100 sentences, mix of neutral + dovish opening, hawkish pivot in the middle.

**Step 2: Write the test**

```python
# tests/integration/test_speech_replay_e2e.py
from datetime import datetime, UTC
from pathlib import Path

from castelino.agents.base import FakeLLMClient
from castelino.triggers.speech.emitter import SpeechTriggerEmitter
from castelino.triggers.speech.llm_gate import SpeechShiftClassification
from castelino.triggers.speech.models import (
    BaselineVector, SpeechSegment,
)
from castelino.triggers.speech.scorer import (
    load_lexicon, split_sentences,
)


def test_replay_dovish_to_hawkish_pivot_emits_one_trigger():
    text = (Path("tests/fixtures/fed/powell_replay_transcript.txt")).read_text()
    sentences = split_sentences(text)
    baseline = BaselineVector(
        hawkish_dovish_mean=-0.15, hawkish_dovish_std=0.20,
        key_phrase_frequencies={}, hedging_density=0.18,
    )
    fake = FakeLLMClient(canned=SpeechShiftClassification(
        is_shift=True, direction="hawkish", magnitude=0.7,
        decisive_phrase="Further firming may be warranted.",
        rationale="ok",
    ))
    em = SpeechTriggerEmitter(
        speaker_id="powell", full_name="J.P.",
        baseline=baseline, threshold_sigma=1.5, llm_client=fake,
    )
    for s in sentences:
        em.ingest(SpeechSegment(
            speaker_id="powell", text=s,
            timestamp=datetime.now(UTC), event_id="fomc-2026-04",
        ))
    assert len(em.triggers) == 1
    assert em.triggers[0].source.value == "speech_deviation"
```

**Step 3: Run — Expected: PASS.**

**Step 4: Commit**

```bash
git add tests/integration/test_speech_replay_e2e.py tests/fixtures/fed/powell_replay_transcript.txt
git commit -m "test(speech): e2e replay covers dovish→hawkish pivot"
```

---

## Task 23: Smoke test CLI command (`castelino speech-test --dry-run`)

**Files:**
- Modify: `src/castelino/orchestrator/cli.py`
- Test: `tests/test_speech_cli.py` (extend)

Live listener against the next FOMC presser, dry-run only — logs what would have triggered, doesn't fire the pipeline.

**Step 1: Write the failing test**

```python
def test_speech_test_dry_run_command_exists():
    r = CliRunner().invoke(app, ["speech-test", "--help"])
    assert r.exit_code == 0
    assert "dry-run" in r.stdout.lower()
```

**Step 2: Run — FAIL**

**Step 3: Add command** that wires `listen() → emitter.ingest()`, but instead of pushing onto `speech_trigger_queue`, just prints the would-be trigger.

**Step 4: Commit**

```bash
git add src/castelino/orchestrator/cli.py tests/test_speech_cli.py
git commit -m "feat(cli): castelino speech-test for dry-run smoke checks"
```

---

## Task 24: Documentation pass

**Files:**
- Modify: `CLAUDE.md` — append a "Completed Work" entry summarising the feature
- Modify: `learnings.md` — capture lessons from implementation (Deepgram quirks, lexicon tuning notes, etc.)

Use `/document-changes` and `/capture-learnings` skills.

**Commit:**

```bash
git add CLAUDE.md learnings.md
git commit -m "docs: log Fed speech listener completion + learnings"
```

---

## Definition of done

- `pytest -q` passes locally with no failures, no skips except network-bound ones
- `castelino persona-refresh --speaker powell` runs end-to-end against the live Fed website and produces `data/personas/powell.json` with ≥10 speeches in the rolling window
- `castelino speech-test --dry-run` produces a transcript + would-be trigger log against a real or recorded FOMC presser
- New `SPEECH_DEVIATION` trigger source flows through the existing pipeline with no graph changes (verified by `tests/test_speech_runner_integration.py`)
- All commits are individually green
