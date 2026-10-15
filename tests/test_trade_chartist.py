import pytest

from castelino.agents.trade import chartist, llm, store
from castelino.agents.trade.models import SECTIONS, ChartSpec, Frame, SpecList, StandIn
from tests.test_trade_forms import SERIES, SRC
from tests.trade_fakes import FakeClient, parsed

PICKS = {
    "intro": "quadrant",
    "bull": "slope",
    "bear": "waterfall",
    "question": "bars",
    "technical": "dial",
    "read": "compare",
    "watch": "threshold_band",
}


def spec(section, form, pick=True):
    return ChartSpec(
        section=section,
        form=form,
        series=SERIES[form],
        window_days=365,
        threshold=0.6 if form == "threshold_band" else None,
        title=f"{form} for {section}",
        why="w",
        agent_pick=pick,
    )


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("ARC_TRADE_DIR", str(tmp_path / "trades"))
    c = FakeClient()
    monkeypatch.setattr(llm, "_client", lambda m: c)
    idea = store.create("India")
    idea.frame = Frame(
        title="India",
        thesis="India diversifies AI",
        stand_ins=[StandIn(ticker="INDA", role="subject", label="India")],
        horizon_months=12,
        prove_wrong=["INDA's 26-week correlation with SMH rises above 0.6"],
        why_now_query="q",
    )
    return c, idea


def test_variety_rule():
    good = [spec(s, f) for s, f in PICKS.items()]
    assert chartist.variety_errors(good) == []
    plain = [spec(s, "bars") for s in ("intro", "bull", "bear")] + [
        spec(s, f) for s, f in list(PICKS.items())[3:]
    ]
    errs = chartist.variety_errors(plain)
    assert any("at most 2 plain" in e for e in errs)
    assert any("at least 6 different forms" in e for e in errs)


def test_propose_draws_every_option_and_makes_c_facts(setup):
    fake, idea = setup
    specs = [spec(s, f) for s, f in PICKS.items()] + [spec("bull", "line", pick=False)]
    fake.script = [parsed(SpecList(specs=specs))]
    options, facts = chartist.propose(idea, llm.Meter(), src=SRC)
    assert {o.spec.section for o in options} == set(SECTIONS)
    assert all(o.file and (store.charts_dir(idea.id) / o.file).exists() for o in options)
    assert facts and all(f.id.startswith("C1.") for f in facts)
    assert set(options[0].fact_ids) <= {f.id for f in facts}
    assert sum(o.spec.agent_pick for o in options if o.spec.section == "bull") == 1


def test_propose_retries_when_a_section_has_nothing_drawable(setup):
    fake, idea = setup
    bad_watch = spec("watch", "line").model_copy(update={"series": ["INDA"]})
    first = [spec(s, f) for s, f in PICKS.items() if s != "watch"] + [bad_watch]
    again = [spec(s, f) for s, f in PICKS.items()]
    fake.script = [parsed(SpecList(specs=first)), parsed(SpecList(specs=again))]
    options, _ = chartist.propose(idea, llm.Meter(), src=SRC)
    watch = [o for o in options if o.spec.section == "watch" and o.file]
    assert watch and "watch" in fake.calls[1][1]["messages"][-1]["content"]


def test_another_uses_the_talk_model(setup, monkeypatch):
    fake, idea = setup
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    fake.script = [parsed(SpecList(specs=[spec("bear", "calendar")]))]
    opt, _ = chartist.another(idea, "bear", llm.Meter(), src=SRC)
    assert opt.spec.form == "calendar" and opt.file
    assert fake.calls[0][1]["model"] == "deepseek/deepseek-v4-pro"


def test_a_title_with_a_number_no_fact_has_is_dropped(setup):
    _, idea = setup
    bad = spec("intro", "quadrant").model_copy(update={"title": "India is up 99.9% on AI"})
    options, facts = chartist._draw(idea, [bad], SRC, 1, 0)
    assert options[0].file is None and "99.9%" in options[0].error and facts == []
