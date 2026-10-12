import pandas as pd
import pytest

from castelino.week_ahead import spend


def row(date, slug, c, p):
    return (
        f'{{\\"date\\":\\"{date} 00:00:00\\",\\"model_permaslug\\":\\"{slug}\\",'
        f'\\"variant\\":\\"standard\\",\\"total_completion_tokens\\":{c},'
        f'\\"total_prompt_tokens\\":{p},\\"count\\":1}}'
    )


def test_openrouter_share_sums_by_lab():
    rows = [
        row("2026-10-11", "deepseek/v4-flash-20260910", 10, 50),
        row("2026-10-11", "deepseek/v4-20260423", 0, 20),
        row("2026-10-11", "anthropic/claude-opus-5.5", 5, 15),
        row("2026-10-05", "stealth/space-bunny", 0, 0),
    ]
    out = spend.openrouter_share("<script>" + ",".join(rows) + "</script>")
    assert out["week"] == ["2026-10-05", "2026-10-11"] and out["basis"] == "top-20 models"
    assert out["labs"][0] == {"lab": "deepseek", "share": 80.0, "tokens": 80}
    assert out["labs"][1] == {"lab": "anthropic", "share": 20.0, "tokens": 20}
    assert round(sum(x["share"] for x in out["labs"]), 6) == 100.0


def test_openrouter_share_folds_tail_into_other():
    html = ",".join(row("2026-10-11", f"lab{i}/m", 0, 10 + i) for i in range(10))
    labs = spend.openrouter_share(html)["labs"]
    assert len(labs) == 9 and labs[-1]["lab"] == "other" and labs[-1]["tokens"] == 10 + 11


def test_openrouter_share_raises_when_page_changed():
    with pytest.raises(RuntimeError, match="0 rows"):
        spend.openrouter_share("<html>redesigned</html>")


def test_ramp_series_monthly():
    def fetch(sid):
        return pd.Series([55.7107, 56.1323], index=pd.to_datetime(["2026-07-01", "2026-08-01"]))

    out = spend.ramp(fetch)
    assert set(out) == set(spend.RAMP)
    assert out["RAMPAIALL"] == [["2026-07", 55.71], ["2026-08", 56.13]]
