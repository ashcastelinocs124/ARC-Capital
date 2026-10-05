from castelino.adoption.extract import ai_passages, extract_claims
from castelino.adoption.guard import keep_verified
from castelino.adoption.models import Claim, ExtractedClaims
from castelino.agents.base import FakeLLMClient


def test_guard_keeps_verbatim_and_drops_invented():
    text = "Intro.  We deployed machine\nlearning to route orders.  Other text."
    kept, dropped = keep_verified(
        [Claim(quote="we deployed machine learning to route orders", depth=2),
         Claim(quote="we cured cancer with AI", depth=3)],
        text,
    )
    assert [c.depth for c in kept] == [2]
    assert len(dropped) == 1


def test_guard_drops_bad_depth_and_duplicates():
    text = "We use AI today."
    kept, dropped = keep_verified(
        [Claim(quote="We use AI today.", depth=2),
         Claim(quote="we use ai today.", depth=2),
         Claim(quote="We use AI today.", depth=9)],
        text,
    )
    assert len(kept) == 1 and len(dropped) == 2


def test_ai_passages_merges_nearby_and_splits_far():
    text = "AI helps. AI helps. AI helps. " + ("filler " * 400) + "We rolled out generative AI in support."
    ps = ai_passages(text, max_passages=10, window=50)
    assert len(ps) == 2
    assert "generative AI" in ps[1]


def test_ai_passages_ignores_lowercase_noise_and_caps_count():
    assert ai_passages("said the maid ai went home", max_passages=5, window=50) == []
    text = ("AI here. " + "filler " * 200) * 10
    assert len(ai_passages(text, max_passages=3, window=20)) == 3


def _fake(monkeypatch, claims):
    fake = FakeLLMClient()
    fake.register("ExtractedClaims", lambda s, u: ExtractedClaims(claims=claims))
    monkeypatch.setattr("castelino.agents.base._LIVE_CLIENT_SINGLETON", fake)
    return fake


def test_extract_claims_runs_llm_then_guard(monkeypatch):
    fake = _fake(monkeypatch, [
        Claim(quote="we deployed machine learning to route orders", depth=2),
        Claim(quote="invented", depth=3),
    ])
    text = "Boilerplate. We deployed machine learning to route orders. More."
    kept, dropped = extract_claims("ACME", text, max_passages=5, window=100)
    assert [c.depth for c in kept] == [2] and len(dropped) == 1
    assert len(fake.call_log) == 1 and "ACME" in fake.call_log[0][3]


def test_extract_claims_skips_llm_without_ai_mentions(monkeypatch):
    fake = _fake(monkeypatch, [])
    assert extract_claims("ACME", "nothing relevant here", max_passages=5, window=100) == ([], [])
    assert fake.call_log == []
