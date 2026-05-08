# FRED Calendar Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the static US economic calendar with live data from the FRED API `/fred/releases/dates` endpoint, keeping a small static list for non-US events (ECB, BoJ, OPEC).

**Architecture:** The calendar module gains a `_fetch_fred_releases()` function that queries FRED for upcoming US release dates, maps them via a configured release-ID-to-metadata table, and caches responses for 24h. `pull_calendar()` merges FRED US events with static non-US events. `FRED_API_KEY` is required.

**Tech Stack:** `requests` (already in deps), FRED REST API v1, JSON file caching.

---

### Task 1: Add FRED config to `config.yaml` and `config.py`

**Files:**
- Modify: `config.yaml` (add `fred:` section)
- Modify: `src/castelino/config.py` (add `FredCfg` model, wire into `Settings`)

**Step 1: Add `fred` section to config.yaml**

Add after the `triggers:` block:

```yaml
fred:
  # FRED release IDs mapped to our metadata.
  # See https://fred.stlouisfed.org/releases for full list.
  releases:
    10:
      name: "US CPI YoY"
      impact: "high"
      asset_classes: ["equity", "bond_etf", "fx"]
    13:
      name: "US Retail Sales"
      impact: "medium"
      asset_classes: ["equity"]
    14:
      name: "FOMC Rate Decision"
      impact: "high"
      asset_classes: ["equity", "bond_etf", "fx", "commodity_etf"]
    21:
      name: "US PCE YoY"
      impact: "high"
      asset_classes: ["equity", "bond_etf"]
    50:
      name: "US Non-Farm Payrolls"
      impact: "high"
      asset_classes: ["equity", "bond_etf", "fx"]
    53:
      name: "US GDP"
      impact: "high"
      asset_classes: ["equity", "bond_etf", "fx"]
    46:
      name: "US PPI"
      impact: "medium"
      asset_classes: ["equity", "bond_etf"]
  cache_ttl_hours: 24
```

**Step 2: Add `FredCfg` to config.py**

```python
class FredReleaseCfg(BaseModel):
    name: str
    impact: str  # high | medium | low
    asset_classes: list[str]


class FredCfg(BaseModel):
    releases: dict[int, FredReleaseCfg]
    cache_ttl_hours: int = 24
```

Add `fred: FredCfg` to the `Settings` model.

**Step 3: Make `fred_api_key` raise if unset**

The property already raises — confirm it's unchanged. It should raise `RuntimeError` when key is missing.

**Step 4: Run existing tests to confirm no regressions**

Run: `cd /Users/ash/Desktop/Castelino-Capital && python -m pytest tests/ -q`
Expected: All existing tests pass (config loads fine with the new optional section because tests monkeypatch or use defaults).

**Step 5: Commit**

```bash
git add config.yaml src/castelino/config.py
git commit -m "feat(config): add FRED release configuration for live US calendar"
```

---

### Task 2: Implement `_fetch_fred_releases()` in calendar module

**Files:**
- Modify: `src/castelino/triggers/calendar.py`

**Step 1: Write the failing test**

Add to `tests/test_trigger_layer.py`:

```python
def test_fred_fetch_parses_releases(monkeypatch, tmp_path):
    """FRED API response is parsed into CalendarEvents."""
    from castelino.triggers import calendar as calmod
    from castelino.config import get_settings

    # Stub the cache path
    monkeypatch.setattr(calmod, "_fred_cache_path", lambda: tmp_path / "fred_cache.json")

    near_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    fake_response = {
        "release_dates": [
            {"release_id": 10, "date": near_date},
            {"release_id": 50, "date": near_date},
            {"release_id": 999, "date": near_date},  # unknown release, should be skipped
        ]
    }

    class FakeResp:
        status_code = 200
        def json(self):
            return fake_response
        def raise_for_status(self):
            pass

    monkeypatch.setattr("requests.get", lambda *a, **kw: FakeResp())
    monkeypatch.setenv("FRED_API_KEY", "test-key")

    events = calmod._fetch_fred_releases()
    # Only release IDs 10 and 50 are in our config
    assert len(events) == 2
    names = {e.name for e in events}
    assert "US CPI YoY" in names
    assert "US Non-Farm Payrolls" in names
    assert all(e.region == "US" for e in events)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ash/Desktop/Castelino-Capital && python -m pytest tests/test_trigger_layer.py::test_fred_fetch_parses_releases -v`
Expected: FAIL — `_fetch_fred_releases` does not exist.

**Step 3: Implement `_fetch_fred_releases()`**

Add to `src/castelino/triggers/calendar.py`:

```python
import requests

def _fred_cache_path() -> Path:
    return get_settings().resolved_paths.cache / "fred_calendar.json"


def _fred_cache_is_fresh() -> bool:
    p = _fred_cache_path()
    if not p.exists():
        return False
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
    ttl = timedelta(hours=get_settings().fred.cache_ttl_hours)
    return (datetime.now(UTC) - mtime) < ttl


def _fetch_fred_releases() -> list[CalendarEvent]:
    """Fetch upcoming US release dates from FRED API. Caches for 24h."""
    cfg = get_settings()
    cache_path = _fred_cache_path()

    # Return cached if fresh
    if _fred_cache_is_fresh():
        raw = json.loads(cache_path.read_text())
        return _parse_fred_raw(raw)

    # Hit FRED API
    api_key = cfg.fred_api_key
    params = {
        "api_key": api_key,
        "file_type": "json",
        "include_release_dates_with_no_data": "true",
    }
    resp = requests.get(
        "https://api.stlouisfed.org/fred/releases/dates",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()

    # Cache the response
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(raw, indent=2))
    return _parse_fred_raw(raw)


def _parse_fred_raw(raw: dict) -> list[CalendarEvent]:
    """Convert FRED API JSON into CalendarEvents, filtering to configured releases."""
    cfg = get_settings()
    configured = cfg.fred.releases
    today = date.today()
    horizon = today + timedelta(days=90)
    events: list[CalendarEvent] = []

    for entry in raw.get("release_dates", []):
        rid = entry.get("release_id")
        if rid not in configured:
            continue
        d = date.fromisoformat(entry["date"])
        if d < today or d > horizon:
            continue
        meta = configured[rid]
        rt = time(13, 30, tzinfo=UTC)  # 8:30 ET default for US releases
        ts = datetime.combine(d, rt, tzinfo=UTC)
        events.append(
            CalendarEvent(
                timestamp=ts,
                name=meta.name,
                region="US",
                impact=meta.impact,
                asset_classes_affected=list(meta.asset_classes),
            )
        )
    return events
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/ash/Desktop/Castelino-Capital && python -m pytest tests/test_trigger_layer.py::test_fred_fetch_parses_releases -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/castelino/triggers/calendar.py tests/test_trigger_layer.py
git commit -m "feat(calendar): implement FRED API fetch with 24h caching"
```

---

### Task 3: Add FRED cache freshness test

**Files:**
- Modify: `tests/test_trigger_layer.py`

**Step 1: Write the test**

```python
def test_fred_cache_avoids_network_when_fresh(monkeypatch, tmp_path):
    """When cache exists and is fresh, no network call is made."""
    from castelino.triggers import calendar as calmod

    monkeypatch.setattr(calmod, "_fred_cache_path", lambda: tmp_path / "fred_cache.json")
    monkeypatch.setenv("FRED_API_KEY", "test-key")

    near_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    cached = {"release_dates": [{"release_id": 10, "date": near_date}]}
    cache_file = tmp_path / "fred_cache.json"
    cache_file.write_text(json.dumps(cached))

    # If requests.get is called, blow up
    def boom(*a, **kw):
        raise AssertionError("Network should not be hit when cache is fresh")

    monkeypatch.setattr("requests.get", boom)

    events = calmod._fetch_fred_releases()
    assert len(events) == 1
    assert events[0].name == "US CPI YoY"
```

**Step 2: Run test**

Run: `cd /Users/ash/Desktop/Castelino-Capital && python -m pytest tests/test_trigger_layer.py::test_fred_cache_avoids_network_when_fresh -v`
Expected: PASS (cache logic already implemented in Task 2)

**Step 3: Commit**

```bash
git add tests/test_trigger_layer.py
git commit -m "test(calendar): verify FRED cache avoids redundant network calls"
```

---

### Task 4: Refactor `pull_calendar()` to merge FRED + non-US static

**Files:**
- Modify: `src/castelino/triggers/calendar.py`

**Step 1: Write the failing test**

```python
def test_pull_calendar_merges_fred_and_non_us(monkeypatch, tmp_path):
    """pull_calendar returns both FRED US events and static non-US events."""
    from castelino.triggers import calendar as calmod

    monkeypatch.setattr(calmod, "_fred_cache_path", lambda: tmp_path / "fred_cache.json")
    monkeypatch.setattr(calmod, "_calendar_path", lambda: tmp_path / "calendar.json")
    monkeypatch.setenv("FRED_API_KEY", "test-key")

    near_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    cached = {"release_dates": [{"release_id": 14, "date": near_date}]}
    (tmp_path / "fred_cache.json").write_text(json.dumps(cached))

    events = calmod.pull_calendar(window_days=30)
    regions = {e.region for e in events}
    names = {e.name for e in events}
    assert "US" in regions
    assert "FOMC Rate Decision" in names
    # Non-US events should also be present (if any fall in window)
    # At minimum, the function should not crash
    assert all(isinstance(e, calmod.CalendarEvent) for e in events)
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `pull_calendar` still reads from the old static JSON.

**Step 3: Refactor `pull_calendar()`**

Replace the existing `pull_calendar` and remove `_DEFAULT_EVENTS` / `_bootstrap_calendar`:

```python
_NON_US_EVENTS: list[dict] = [
    {"date": "2026-06-04", "name": "ECB Rate Decision", "region": "EU", "impact": "high",
     "asset_classes": ["fx", "bond_etf"]},
    {"date": "2026-07-02", "name": "OPEC+ Meeting", "region": "GLOBAL", "impact": "high",
     "asset_classes": ["commodity_etf", "futures"]},
    {"date": "2026-07-25", "name": "BoJ Rate Decision", "region": "JP", "impact": "high",
     "asset_classes": ["fx", "bond_etf"]},
]


def _load_non_us_events(window_days: int = 30) -> list[CalendarEvent]:
    """Static non-US events within the window."""
    today = date.today()
    horizon = today + timedelta(days=window_days)
    events: list[CalendarEvent] = []
    for r in _NON_US_EVENTS:
        d = date.fromisoformat(r["date"])
        if d < today or d > horizon:
            continue
        rt = time(12, 0, tzinfo=UTC)
        ts = datetime.combine(d, rt, tzinfo=UTC)
        events.append(
            CalendarEvent(
                timestamp=ts,
                name=r["name"],
                region=r["region"],
                impact=r["impact"],
                asset_classes_affected=list(r["asset_classes"]),
            )
        )
    return events


def pull_calendar(window_days: int = 30) -> list[CalendarEvent]:
    """Merge FRED US events with static non-US events."""
    us_events = _fetch_fred_releases()
    # Filter US events to window
    today = date.today()
    horizon = today + timedelta(days=window_days)
    us_events = [e for e in us_events if today <= e.timestamp.date() <= horizon]

    non_us = _load_non_us_events(window_days)
    all_events = us_events + non_us
    return sorted(all_events, key=lambda e: e.timestamp)
```

**Step 4: Run full test suite**

Run: `cd /Users/ash/Desktop/Castelino-Capital && python -m pytest tests/test_trigger_layer.py -v`
Expected: All tests pass. Existing calendar tests may need fixture updates (they monkeypatch `_calendar_path` which is now only used for non-US; also need to monkeypatch `_fred_cache_path` and set `FRED_API_KEY`).

**Step 5: Fix any broken existing calendar tests**

The `test_calendar_bootstraps_with_defaults` and `test_calendar_filters_to_window` tests were written against the old static-only flow. Update them to monkeypatch `_fetch_fred_releases` to return an empty list (so they only test non-US path) or rewrite them to test the new merged behavior.

**Step 6: Commit**

```bash
git add src/castelino/triggers/calendar.py tests/test_trigger_layer.py
git commit -m "feat(calendar): pull_calendar merges FRED US + static non-US events"
```

---

### Task 5: Handle FRED API failure gracefully

**Files:**
- Modify: `src/castelino/triggers/calendar.py`
- Modify: `tests/test_trigger_layer.py`

**Step 1: Write the failing test**

```python
def test_fred_api_failure_uses_stale_cache(monkeypatch, tmp_path):
    """If FRED API is down but stale cache exists, use stale data with warning."""
    from castelino.triggers import calendar as calmod
    import time as time_mod

    cache_path = tmp_path / "fred_cache.json"
    monkeypatch.setattr(calmod, "_fred_cache_path", lambda: cache_path)
    monkeypatch.setenv("FRED_API_KEY", "test-key")

    near_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")
    cached = {"release_dates": [{"release_id": 10, "date": near_date}]}
    cache_path.write_text(json.dumps(cached))

    # Make cache stale (older than TTL)
    import os
    old_time = (datetime.now(UTC) - timedelta(hours=48)).timestamp()
    os.utime(cache_path, (old_time, old_time))

    # Network fails
    def fail(*a, **kw):
        raise requests.RequestException("timeout")

    monkeypatch.setattr("requests.get", fail)

    # Should still return events from stale cache
    events = calmod._fetch_fred_releases()
    assert len(events) == 1
    assert events[0].name == "US CPI YoY"
```

**Step 2: Update `_fetch_fred_releases` to fall back to stale cache**

Add a try/except around the network call:

```python
    try:
        resp = requests.get(
            "https://api.stlouisfed.org/fred/releases/dates",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(raw, indent=2))
    except (requests.RequestException, ValueError) as e:
        log.warning("FRED API request failed: %s — using stale cache", e)
        if cache_path.exists():
            raw = json.loads(cache_path.read_text())
        else:
            log.error("FRED API down and no cache exists; returning empty US calendar")
            return []

    return _parse_fred_raw(raw)
```

**Step 3: Run test**

Run: `cd /Users/ash/Desktop/Castelino-Capital && python -m pytest tests/test_trigger_layer.py::test_fred_api_failure_uses_stale_cache -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/castelino/triggers/calendar.py tests/test_trigger_layer.py
git commit -m "feat(calendar): graceful fallback to stale FRED cache on API failure"
```

---

### Task 6: Run full test suite and clean up

**Files:**
- All modified files

**Step 1: Run full test suite**

Run: `cd /Users/ash/Desktop/Castelino-Capital && python -m pytest tests/ -v`
Expected: All tests pass.

**Step 2: Run type checker**

Run: `cd /Users/ash/Desktop/Castelino-Capital && python -m mypy src/castelino/triggers/calendar.py --ignore-missing-imports`
Expected: No errors.

**Step 3: Run linter**

Run: `cd /Users/ash/Desktop/Castelino-Capital && python -m ruff check src/castelino/triggers/calendar.py`
Expected: Clean.

**Step 4: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: lint and type fixes for FRED calendar integration"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `config.yaml` | Add `fred:` section with release ID → metadata map |
| `src/castelino/config.py` | Add `FredReleaseCfg`, `FredCfg` models; add `fred` to `Settings` |
| `src/castelino/triggers/calendar.py` | Replace static US events with `_fetch_fred_releases()`, keep non-US static, merge in `pull_calendar()` |
| `tests/test_trigger_layer.py` | Add FRED parse, cache, and fallback tests; update existing calendar tests |
