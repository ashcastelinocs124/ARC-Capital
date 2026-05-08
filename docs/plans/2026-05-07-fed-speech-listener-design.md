# Fed Speech Listener — Design Doc

**Date:** 2026-05-07
**Branch:** `feature/fed-speech-listener`
**Status:** Design approved, ready for implementation planning

---

## Goal

Add a new trigger source to Castelino Capital that ingests live audio from Fed
events (FOMC press conferences first), transcribes it in real time, and fires
the existing pipeline when a speaker's tone deviates meaningfully from their
own rhetorical baseline.

The signal is not "is this hawkish?" but "is this hawkish *for this person*?"
A dovish-leaning Powell suddenly using restrictive language is materially
different from a hawkish Waller doing the same thing. The persona supplies
the baseline against which surprise is measured.

## Non-goals

- Voice as a UI feature (no STT for CLI commands, no TTS notifications)
- Sentiment analysis of headlines / news (already covered by
  `triggers/significance.py`)
- Speech-to-text from arbitrary YouTube videos — scope is scheduled Fed events
  with predictable stream URLs
- Speakers outside the Fed (ECB / BoE / BoJ are explicit v2 scope)

## Architecture

Three layers under a new `src/castelino/triggers/speech/` package, plus a
new trigger source that drains into the existing pipeline.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 1 — Persona Builder            (offline, monthly cron)        │
│  -----------------------------------------------------------------   │
│  Scrape federalreserve.gov speeches by speaker → parse → score each  │
│  with the canonical lexicon → aggregate into a rolling 12-month      │
│  baseline → persist data/personas/<speaker_id>.json                  │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 2 — Live Stream Listener     (event-driven, async task)       │
│  -----------------------------------------------------------------   │
│  Calendar event marked has_live_stream → resolve YouTube/webcast     │
│  URL → stream audio chunks to Deepgram → emit SpeechSegment events   │
│  one per complete sentence                                            │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 3 — Deviation Scorer          (real-time, two-stage)          │
│  -----------------------------------------------------------------   │
│  Stage A: lexicon-score each sentence, maintain 5-sentence window,   │
│  z-score vs. persona baseline                                        │
│  Stage B: if |σ| > 1.5, escalate window to gpt-4o-mini for           │
│  confirmation, capture decisive phrase                               │
│  → on confirmed shift, emit TriggerRecord(SPEECH_DEVIATION)          │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                    existing pipeline (current_event → ...)
```

## The persona

`SpeakerPersona` (saved to `data/personas/<speaker_id>.json`):

```python
class BaselineVector(BaseModel):
    hawkish_dovish_mean: float           # weighted mean of speech scores
    hawkish_dovish_std: float            # dispersion
    key_phrase_frequencies: dict[str, float]   # rate of signal-phrase use
    hedging_density: float               # avg fraction of softeners

class SpeakerPersona(BaseModel):
    speaker_id: str                      # "powell"
    full_name: str                       # "Jerome H. Powell"
    role: str                            # "Chair, Federal Reserve"
    baseline_window_days: int = 365
    last_updated: datetime
    speeches_in_window: list[ScoredSpeech]
    baseline_vector: BaselineVector
```

### How the baseline is calculated

1. **Sentence scoring** — `score_sentence(text) -> float in [-1, +1]` using a
   versioned hawkish/dovish lexicon
   (`data/lexicons/hawkish_dovish_v1.yaml`). Hedging density dampens
   magnitude. The same function is used for both baseline construction and
   live scoring — this is the load-bearing invariant. If the lexicon is
   updated, version bumps and the entire historical corpus is re-scored.

2. **Speech aggregation** — for each historical speech, compute the mean of
   its policy-relevant sentences (filter `|score| > 0.05`). One number per
   speech.

3. **Baseline aggregation** — over the rolling 12-month window
   (~40-60 speeches for Powell), compute time-weighted mean and std. Half-life
   of 6 months so recent speeches dominate. This is the speaker's
   "current normal." No manual regime segmentation — drift is automatic.

### Refresh cadence

Monthly cron via `castelino persona-refresh`. Cheap (just scraping + scoring,
no LLM, no live audio). MVP scope: Powell only. Adding speakers is just
adding entries to `config.yaml::speech.speakers`.

## The live listener

Activated by the existing calendar trigger system. Calendar events gain a
`has_live_stream` field plus `speaker_id`. The watch loop spawns the
listener as an asyncio task ~5 minutes before scheduled start.

**Stream resolution** (`speech/streams.py`):
- FOMC press conferences: scrape `federalreserve.gov/monetarypolicy.htm`
  ~30 minutes before the event for the published live URL
- v2: other speeches via host-institution streams
- Fallback: if no stream URL is found, log a warning and skip — the calendar
  trigger still fires the pipeline through its existing path

**STT provider**: Deepgram streaming (recommended). ~300ms latency,
~$0.43/hour, financial-domain models. ~$0.30 per FOMC presser. Provider
is abstracted behind a `SpeechToTextProvider` interface so we can swap to
OpenAI Realtime or Whisper later.

**Output**: an async generator of `SpeechSegment(speaker_id, text,
timestamp)` events, one per complete sentence.

**Failure handling**:
- Stream drop → reconnect with backoff, log gap in transcript
- STT provider unavailable → fall back to logging the audio file for
  post-hoc analysis. Pipeline trigger does not fire, but the transcript is
  preserved
- Listener runs in its own asyncio task — never blocks the watch loop

## The deviation scorer

### Stage A — Real-time z-scoring

For every incoming `SpeechSegment`:

1. `score_sentence(text)` → float in `[-1, +1]`
2. Push into rolling 5-sentence window
3. If window has ≥3 policy-relevant sentences:
   ```
   window_mean = mean(window scores)
   deviation_sigma = (window_mean - persona.mean) / persona.std
   ```
4. Track auxiliary signals: hedging density of window vs. baseline,
   key-phrase frequency anomalies

### Stage B — LLM confirmation gate

Only when `|deviation_sigma| > 1.5` (configurable):

Prompt `gpt-4o-mini` (or `gpt-4o` if budget allows):
> "Speaker {full_name}'s recent baseline tone is {direction} (mean={mean},
> std={std}). They just said: «{rolling_window_text}». Is this a meaningful
> tone shift? Return JSON: {is_shift: bool, direction: hawkish|dovish,
> magnitude: 0-1, decisive_phrase: str, rationale: str}."

This mirrors `triggers/significance.score_batch` — keeps the LLM out of the
hot path until something looks interesting.

### Trigger emission

On confirmed shift:

```python
TriggerRecord(
    source=TriggerSource.SPEECH_DEVIATION,   # new enum value
    headline=f"{persona.full_name}: {direction} shift mid-speech",
    significance=min(0.95, 0.6 + 0.3 * magnitude),
    asset_classes_affected=["rates", "equities", "fx"],
    raw_event_data={
        "speaker_id": persona.speaker_id,
        "deviation_sigma": deviation_sigma,
        "decisive_phrase": phrase,
        "transcript_window": rolling_window_text,
        "event_id": event.event_id,
    },
    one_sentence_reason=(
        f"{persona.full_name} shifted {direction} "
        f"({deviation_sigma:+.1f}σ): «{phrase}»"
    ),
)
```

**Cooldown**: at most one trigger per scheduled speech event. After the
first shift fires, subsequent windows from the same event are scored and
logged but do not fire. Prevents one prolonged hawkish stretch from
producing 20 redundant triggers.

## Integration points

| File | Change |
|------|--------|
| `src/castelino/memory/schemas.py` | Add `SPEECH_DEVIATION` to `TriggerSource` enum |
| `src/castelino/triggers/calendar.py` | Add `has_live_stream` and `speaker_id` to `CalendarEvent` |
| `src/castelino/triggers/runner.py` | Drain pending speech triggers in `tick()` between calendar and black-swan paths |
| `src/castelino/orchestrator/cli.py` | New commands `persona-refresh`, `speech-test`, `speech-replay` |
| `config.yaml` | New `speech` section: `stt_provider`, `speakers`, `deviation_threshold_sigma`, `cooldown_hours` |

The orchestrator graph itself (`graph.py`) requires zero changes — a
`SPEECH_DEVIATION` trigger enters at `current_event` like any other.

## Persistence

- `data/personas/<speaker_id>.json` — persona records (one per speaker)
- `data/lexicons/hawkish_dovish_v1.yaml` — versioned scoring lexicon
- `data/speech_events/<event_id>.json` — full record per live event:
  - Event metadata, persona snapshot used, full transcript with per-sentence
    scores, all rolling-window deviations, any triggers fired, LLM
    rationales

Same hygiene as the existing journal — append-only, JSON, no DB.

## Observability

- Dashboard tab "Speech Events" — recent FOMC pressers + tone trajectory plot
  (sentence-by-sentence z-score over the speech timeline) + decisive-phrase
  highlights
- All speech scoring goes through structured logs at INFO; LLM escalations
  log full prompts/responses at DEBUG

## Testing strategy

- **Unit tests**:
  - `score_sentence` — fixture sentences with known hawkish/dovish content
  - Persona builder math — given canned scored speeches, assert mean/std
    match expected values
  - Z-score deviation logic — given baseline + window, assert correct sigma
  - Lexicon versioning — confirm corpus rescore on version bump
- **Integration tests**:
  - End-to-end replay: feed a recorded historical FOMC transcript through
    the scorer with a fixture persona, assert expected `SPEECH_DEVIATION`
    triggers fire (and only those)
  - Calendar → listener wiring: mock STT provider, fake stream, confirm
    listener spawns on schedule and tears down cleanly
- **Live smoke test**:
  - `castelino speech-test --dry-run` — runs against the next scheduled
    FOMC presser. Listens, scores, logs what would have triggered, but
    does not fire the pipeline. Used to validate stream resolution and
    real-world latency before going live

## Configuration (proposed)

```yaml
# config.yaml
speech:
  enabled: true
  stt_provider: deepgram             # deepgram | openai_realtime | whisper_local
  deepgram:
    model: nova-2-finance            # finance-tuned model
  speakers:
    - id: powell
      full_name: Jerome H. Powell
      role: Chair, Federal Reserve
  baseline:
    window_days: 365
    half_life_months: 6              # exponential time-weighting
  scoring:
    lexicon: hawkish_dovish_v1
    rolling_window_sentences: 5
    min_policy_sentences: 3
  trigger:
    deviation_threshold_sigma: 1.5
    cooldown_hours: 24               # one trigger per event, anyway
    llm_model: gpt-4o-mini
```

## Failure modes & mitigations

| Failure | Effect | Mitigation |
|---------|--------|------------|
| Stream URL not resolved | No live trigger | Calendar trigger still fires; warn in logs |
| STT API down | No live trigger | Save audio to disk for post-hoc replay |
| Lexicon false positives | Spurious triggers | Stage-B LLM gate filters before pipeline; cooldown caps damage |
| Persona stale (Fed governor turnover) | Wrong baseline | Monthly refresh; refuse to score if persona >60 days old |
| Stream lag spikes | Triggers fire after market reaction | Acceptable — this is a confirmation signal, not pure latency play |
| LLM disagrees with Stage A | No trigger | Logged for review; tightens lexicon over time |

## Risks and open questions

- **Lexicon quality is the load-bearing assumption.** v1 will start with ~50
  curated phrases; we expect to iterate based on observed false positives
  during the smoke-test phase.
- **Stream URL stability for FOMC pressers.** The Fed publishes the URL on
  their website but format/location could change. The scraper needs to be
  resilient and warn loudly on miss.
- **Time-weighted mean vs. plain mean** — open question whether a 6-month
  half-life is right; will tune empirically once the corpus is built.

## Out of scope (v2+)

- Other central banks (ECB, BoE, BoJ)
- Treasury / Congressional testimony of non-Fed officials
- Speeches without scheduled live streams (post-hoc transcript analysis)
- Voice-driven CLI / TTS notifications
- Multi-speaker disambiguation in panel discussions
