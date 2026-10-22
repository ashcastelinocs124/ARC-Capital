"""Charts on X release posts: segment treemaps from the SEC earnings release, beat or miss, and data
releases against forecast. Numbers come only from the filing or the post's own line."""

from datetime import date
from types import SimpleNamespace

from castelino import release_charts as rc
from castelino.adoption.sources.edgar import EdgarClient

FILING = (
    "Amounts in millions Net Sales % Change Versus Year Ago Earnings/(Loss) Before Income Taxes "
    "Beauty $ 4,410 6% $ 1,139 1% Grooming 1,889 4% 619 6% Health Care 3,318 3% 1,029 10% "
    "Baby, Feminine & Family Care 5,322 3% 1,390 (4)% Corporate 132 N/A (234) N/A"
)


def seg(name, sales, chg=None, profit=None, pchg=None):
    return rc.Segment(
        name=name, sales=sales, sales_change_pct=chg, profit=profit, profit_change_pct=pchg
    )


def table(*segs):
    return rc.SegmentTable(
        period="Q1 fiscal 2027",
        unit="millions",
        profit_label="Earnings before income taxes",
        segments=list(segs),
    )


def test_only_numbers_the_release_prints_are_kept():
    t = rc.checked(
        table(
            seg("Beauty", 4410, 6, 1139, 1),
            seg("Grooming", 1890, 4),  # 1,890 isn't in the filing: dropped
            seg("Health Care", 3318, 3, 1029, 11),  # 11% isn't: that change becomes None
            seg("Baby", 5322, 3, -1390, -4),  # printed in brackets: kept with its sign
        ),
        FILING,
    )
    assert [s.name for s in t.segments] == ["Beauty", "Health Care", "Baby"]
    assert t.segments[1].profit_change_pct is None and t.segments[2].profit_change_pct == -4


def test_segment_charts_draw_sales_and_profit_and_leave_out_a_loss(tmp_path):
    t = table(
        seg("Beauty", 4410, 6, 1139, 1),
        seg("Grooming", 1889, 4, 619, 6),
        seg("Health Care", 3318, 3, 1029, 10),
        seg("Corporate", 132, None, -234, None),
    )
    paths = rc.segment_charts("Procter & Gamble", t, "https://sec.gov/x/ex991.htm", tmp_path, "PG")
    assert [p.name for p in paths] == ["PG-sales.png", "PG-profit.png"]
    assert all(p.stat().st_size > 20_000 for p in paths)


def test_no_profit_chart_when_a_segment_has_no_profit_figure(tmp_path):
    t = table(seg("Automotive", 21000, 2, 1500), seg("Energy", 3400, 40))
    assert [p.name for p in rc.segment_charts("Tesla", t, "u", tmp_path, "TSLA")] == [
        "TSLA-sales.png"
    ]


def test_one_segment_that_is_nearly_everything_draws_no_treemap(tmp_path):
    t = table(seg("Family of Apps", 64158, None, 17117), seg("Reality Labs", 443, None, -4129))
    assert rc.segment_charts("Meta Platforms", t, "u", tmp_path, "META") == []


def test_box_names_lose_the_tables_filler_words():
    assert rc._short("Total automotive revenues") == "Automotive"
    assert rc._short("Services and other revenue") == "Services and other"
    assert rc._short("Beauty") == "Beauty"


def test_a_treemap_folds_its_smallest_boxes_into_other(tmp_path, monkeypatch):
    drawn = []
    monkeypatch.setattr(rc.wc, "_frame", lambda *a, **k: drawn.append(a[5]))
    items = [(f"S{i}", 100 - i, None) for i in range(11)]
    rc.treemap(items, "millions", "t", "s", "d", tmp_path / "x.png")
    calls = []
    ax = SimpleNamespace(
        add_patch=lambda r: calls.append(r),
        text=lambda *a, **k: None,
        set_xlim=lambda *a: None,
        set_ylim=lambda *a: None,
        axis=lambda *a: None,
    )
    drawn[0](ax)
    assert len(calls) == rc.MAX_BOXES


def test_beat_or_miss_reads_cents_and_billions_from_the_post_line(tmp_path):
    line = "$TSLA Q3: EPS 48 cents vs 45 cents expected; revenue $28.05 billion vs $27.88 billion expected."
    assert rc.beat_miss(line, "Tesla", tmp_path / "b.png") and (tmp_path / "b.png").exists()
    assert rc._EPS.search(line) and rc._num("", "48", " cents") == 0.48
    assert not rc.beat_miss("$TSLA Q3: results out.", "Tesla", tmp_path / "n.png")


def test_a_data_release_draws_actual_against_forecast_and_previous(tmp_path):
    e = {"actual": 194.0, "consensus": 200.0, "previous": 200.0, "unit": "K"}
    assert rc.data_chart("US Initial Jobless Claims", e, date(2026, 10, 22), tmp_path / "d.png")
    assert not rc.data_chart("x", {"actual": None, "consensus": 1.0}, date(2026, 10, 22), tmp_path / "e.png")  # fmt: skip


def test_a_failed_segment_lookup_still_posts_the_beat_or_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "segments", lambda *a: (_ for _ in ()).throw(RuntimeError("SEC down")))
    line = "$PG Q1: EPS $2 vs $1.88 expected; revenue $23.28 billion vs $22.80 billion expected."
    paths = rc.earnings_charts("Procter & Gamble", "PG", line, date(2026, 10, 22), tmp_path)
    assert [p.name for p in paths] == ["PG-vs-estimates.png"]


class FakeSEC:
    def __init__(self, filed: str):
        self.filed, self.urls = filed, []

    def get(self, url):
        self.urls.append(url)
        body = {
            "company_tickers.json": {"0": {"ticker": "PG", "cik_str": 80424}},
            "CIK0000080424.json": {
                "filings": {
                    "recent": {
                        "form": ["8-K", "8-K"],
                        "filingDate": [self.filed, self.filed],
                        "items": ["7.01,9.01", "2.02,9.01"],
                        "accessionNumber": ["0000080424-26-000252", "0000080424-26-000250"],
                        "primaryDocument": ["pg-20261022.htm", "pg-20261022.htm"],
                    }
                }
            },
            "index.json": {
                "directory": {
                    "item": [
                        {"name": "pg-20261022.htm", "size": "50918"},
                        {"name": "R1.htm", "size": "77413"},
                        {"name": "fy2627q1jas8-kexhibit991.htm", "size": "324466"},
                    ]
                }
            },
        }.get(url.rsplit("/", 1)[-1])
        return SimpleNamespace(
            json=lambda: body,
            text="<p>Beauty $ 4,410 6%</p>",
            raise_for_status=lambda: None,
        )


def test_the_earnings_release_is_exhibit_99_1_of_the_results_8k():
    sec = FakeSEC("2026-10-22")
    text, url = EdgarClient(
        "ARC test@example.com", http=sec, sleep=lambda s: None
    ).earnings_release("PG", date(2026, 10, 22))
    assert text == "Beauty $ 4,410 6%" and url.endswith(
        "000008042426000250/fy2627q1jas8-kexhibit991.htm"
    )


def test_no_release_filed_since_the_report_day_is_none():
    sec = FakeSEC("2026-07-30")
    client = EdgarClient("ARC test@example.com", http=sec, sleep=lambda s: None)
    assert client.earnings_release("PG", date(2026, 10, 22)) is None
