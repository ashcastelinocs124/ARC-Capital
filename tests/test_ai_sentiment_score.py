from castelino.ai_sentiment import score

LEX = {
    "positive": ["fast", "better", "best", "impressive", "love"],
    "negative": ["worse", "broken", "outage", "rate limit", "hallucinates", "slow"],
    "negators": ["not", "no", "never", "isn't", "don't"],
    "families": {
        "Anthropic": ["claude", "anthropic", "opus", "haiku"],
        "OpenAI": ["gpt", "chatgpt", "openai"],
        "Google": ["gemini", "nano banana"],
    },
}
ACCOUNTS = {"dev_a": "", "oai_staff": "OpenAI", "indie": ""}


def test_families_by_keyword():
    assert score.families_of("Claude Opus vs GPT-6 today", LEX) == {"Anthropic", "OpenAI"}
    assert score.families_of("Nano Banana 2.1 is wild", LEX) == {"Google"}
    assert score.families_of("opusculum is a word", LEX) == set()  # whole words only


def test_post_score_counts_words_and_phrases():
    s, hits = score.post_score("Haiku is fast and better, but the rate limit is broken", LEX)
    assert s == 0 and hits == ["fast", "better", "rate limit", "broken"]


def test_negation_flips_within_three_words():
    assert score.post_score("this is not fast at all", LEX)[0] == -1
    assert score.post_score("not that it matters, it is fast", LEX)[0] == 1  # 'not' is 5 words back


def test_daily_scores_and_own_lab_rule():
    posts = [
        {"url": "u1", "author": "dev_a", "text": "Claude is impressive"},
        {"url": "u2", "author": "dev_a", "text": "GPT outage again, worse than last week"},
        {
            "url": "u3",
            "author": "oai_staff",
            "text": "GPT is the best",
        },  # own lab: skipped for OpenAI
        {"url": "u4", "author": "oai_staff", "text": "Claude feels slow"},  # counts for Anthropic
        {"url": "u5", "author": "indie", "text": "Claude docs updated"},  # neutral
    ]
    d = score.daily(posts, ACCOUNTS, LEX)
    a = d["Anthropic"]
    assert (a["n"], a["pos"], a["neg"], a["neu"]) == (3, 1, 1, 1)
    assert a["net"] == 0.0
    o = d["OpenAI"]
    assert (o["n"], o["neg"], o["net"]) == (1, 1, -100.0)
    assert o["samples"][0]["url"] == "u2" and o["samples"][0]["hits"] == ["outage", "worse"]
    assert "Google" not in d


def test_level_and_delta():
    hist = {f"2026-10-{d:02d}": {"Anthropic": {"net": float(d)}} for d in range(1, 15)}
    lv = score.series(hist, "Anthropic")
    assert lv[-1] == ("2026-10-14", 11.0)  # mean of days 8..14
    assert score.delta(lv) == 7.0  # 11 - mean of days 1..7 (4)
    short = {k: v for k, v in hist.items() if k <= "2026-10-10"}
    assert score.delta(score.series(short, "Anthropic")) is None  # needs 14 days


def test_comparison_post_scores_each_provider_on_its_own_clause():
    posts = [
        {"url": "u", "author": "dev_a", "text": "Claude is fast but GPT is slow. Gemini is better."}
    ]
    d = score.daily(posts, ACCOUNTS, LEX)
    assert (d["Anthropic"]["pos"], d["OpenAI"]["neg"], d["Google"]["pos"]) == (1, 1, 1)
    assert d["OpenAI"]["samples"][0]["hits"] == ["slow"]


def test_provider_named_without_opinion_in_its_clause_uses_whole_post():
    posts = [{"url": "u", "author": "dev_a", "text": "Tried Claude today. Honestly impressive"}]
    assert score.daily(posts, ACCOUNTS, LEX)["Anthropic"]["pos"] == 1
