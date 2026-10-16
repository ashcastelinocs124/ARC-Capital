import numpy as np
import pandas as pd
import pytest

from castelino.agents.trade import forms
from castelino.agents.trade.models import ChartSpec


def s(seed, n=900):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.Series(100 * np.exp(np.cumsum(0.0003 + rng.normal(0, 0.012, n))), index=idx)


def sectors(t):
    if t == "INDA":
        return {
            "technology": 0.076,
            "financial_services": 0.297,
            "energy": 0.083,
            "industrials": 0.102,
        }
    return {"technology": 0.603, "communication_services": 0.126, "consumer_cyclical": 0.101}


SRC = forms.Sources(
    yahoo=lambda t: s(sum(map(ord, t))),  # a stable seed per ticker (str hash changes per run)
    fred=lambda sid: s(7),
    sectors=sectors,
)
SERIES = {
    "line": ["yahoo:INDA"],
    "compare": ["yahoo:INDA", "yahoo:SMH", "yahoo:QQQ"],
    "bars": ["yahoo:INDA", "yahoo:SMH"],
    "scatter": ["yahoo:INDA", "yahoo:SMH"],
    "treemap": ["yahoo:INDA", "yahoo:QQQ"],
    "quadrant": ["yahoo:SMH", "yahoo:INDA", "yahoo:EWZ", "yahoo:QQQ"],
    "underwater": ["yahoo:INDA", "yahoo:SMH"],
    "slope": ["yahoo:SMH", "yahoo:INDA"],
    "waterfall": ["yahoo:INDA", "yahoo:INR=X"],
    "threshold_band": ["yahoo:INDA", "yahoo:SMH"],
    "dial": ["yahoo:INDA", "yahoo:SMH"],
    "calendar": ["yahoo:INDA", "yahoo:SMH"],
}


def spec(form, **kw):
    base = dict(
        section="bull",
        form=form,
        series=SERIES[form],
        window_days=365,
        threshold=0.6 if form == "threshold_band" else None,
        title=f"A {form} chart",
        why="w",
        agent_pick=True,
    )
    return ChartSpec(**{**base, **kw})


@pytest.mark.parametrize("form", sorted(forms.FORMS))
def test_every_form_draws_a_png_and_reports_numbers(form, tmp_path):
    nums = forms.render(spec(form), SRC, tmp_path / f"{form}.png", 1)
    assert (tmp_path / f"{form}.png").stat().st_size > 10_000
    assert nums and all(isinstance(v, float) for _, v in nums)


def test_charts_name_each_series_in_full_with_its_ticker(tmp_path):
    names = ["iShares MSCI India ETF", "VanEck Semiconductor ETF"]
    nums = forms.render(spec("bars", names=names), SRC, tmp_path / "b.png", 1)
    assert [label for label, _ in nums] == [
        "iShares MSCI India ETF (INDA) change",
        "VanEck Semiconductor ETF (SMH) change",
    ]
    bare = forms.render(spec("bars"), SRC, tmp_path / "c.png", 1)  # older specs carry no names
    assert bare[0][0] == "INDA change"
    # the agent sometimes writes the ticker into the name too (first live run, 2026-10-15)
    named = ["iShares MSCI India ETF (INDA)", "VanEck Semiconductor ETF"]
    twice = forms.render(spec("bars", names=named), SRC, tmp_path / "d.png", 1)
    assert twice[0][0] == "iShares MSCI India ETF (INDA) change"


@pytest.mark.parametrize("form", ["quadrant", "treemap"])
def test_named_series_still_look_up_sector_weights_by_ticker(form, tmp_path):
    names = [f"{sid.split(':')[1]} fund" for sid in SERIES[form]]
    nums = dict(forms.render(spec(form, names=names), SRC, tmp_path / "n.png", 1))
    tech = [v for label, v in nums.items() if label.startswith("INDA fund (INDA) tech")]
    assert tech == [7.6]


def test_a_title_the_frame_would_cut_off_is_an_error():
    """The house frame cuts "Exhibit n: <title>" at 72 characters; full names make titles long."""
    assert forms.spec_errors(spec("line", title="x" * 60)) == []
    assert forms.spec_errors(spec("line", title="x" * 61)) == [
        "title is over 60 characters and would be cut off; shorten the claim, keep the full names"
    ]


def test_catalog_has_twelve_forms_and_three_plain():
    assert len(forms.FORMS) == 12 and forms.PLAIN == {"line", "compare", "bars"}
    assert all(name in forms.catalog_text() for name in forms.FORMS)


def test_spec_errors():
    assert forms.spec_errors(spec("line")) == []
    pie = spec("line").model_copy(update={"form": "pie"})
    assert "unknown form pie" in forms.spec_errors(pie)
    errs = forms.spec_errors(spec("waterfall", series=["yahoo:INDA"]))
    assert any("needs 2 to 2 series" in e for e in errs)
    assert any("threshold" in e for e in forms.spec_errors(spec("threshold_band", threshold=None)))
    assert any("bad series" in e for e in forms.spec_errors(spec("line", series=["INDA"])))
