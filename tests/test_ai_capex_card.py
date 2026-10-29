import matplotlib.image as mpimg

from castelino.dashboards.ai_capex import card

DOC = {
    "as_of": "2026-10-28",
    "companies": [
        {"ticker": t, "name": t, "kind": "hyperscaler",
         "quarters": [{"q": q, "capex": v} for q, v in (("2026Q1", 30.0), ("2026Q2", 36.0))]}
        for t in ("MSFT", "GOOGL", "AMZN", "META", "ORCL")
    ],
    "totals": {
        "quarters": [{"q": "2026Q1", "capex": 150.0, "reported": 5, "of": 5},
                     {"q": "2026Q2", "capex": 180.0, "reported": 5, "of": 5}],
        "yoy_pct": 74, "ttm_capex": 611.0, "ttm_yoy_pct": 66, "backlog": 1818.0, "backlog_growth_pct": 125,
    },
}  # fmt: skip


def test_card_chart_ends_at_the_latest_full_quarter():
    # a 3-of-5 quarter drawn as the last bar reads as capex collapsing on the most-shared image
    doc = {
        "totals": {
            "quarters": DOC["totals"]["quarters"]
            + [{"q": "2026Q3", "capex": 102.0, "reported": 3, "of": 5}]
        }
    }
    assert [q["q"] for q in card.chart_quarters(doc)] == ["2026Q1", "2026Q2"]


def test_draw_writes_1200x630_png(tmp_path):
    p = card.draw(DOC, tmp_path / "card.png")
    assert mpimg.imread(p).shape[:2] == (630, 1200)


def test_og_page_tags():
    html = '<html><head><title>ARC Research</title><meta property="og:title" content="old" /></head><body></body></html>'
    out = card.og_page(html, DOC)
    assert out.count('property="og:title"') == 1 and "old" not in out
    assert "<title>AI Demand &amp; Capex · ARC Research</title>" in out
    assert "https://arcresearch.markets/api/dashboards/ai-capex/card-2026-10-28.png" in out
    assert 'name="twitter:card" content="summary_large_image"' in out
    assert "$180bn" in out and "Q2 2026" in out and "$1.82tn" in out


def test_og_no_snapshot_noop(tmp_path):
    (tmp_path / "index.html").write_text("<html><head></head></html>")
    card.write_og(tmp_path, tmp_path / "missing.json")
    assert not (tmp_path / "dashboards").exists()


def _script(name):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_export_copies_the_dated_card(tmp_path, monkeypatch):
    mod = _script("export_snapshot")
    monkeypatch.setattr(mod, "OUT", tmp_path / "out")
    src = tmp_path / "data" / "ai_capex"
    src.mkdir(parents=True)
    (src / "card.png").write_bytes(b"png")
    assert mod.copy_dashboard_card({"as_of": "2026-10-28"}, src) is True
    dst = tmp_path / "out" / "dashboards" / "ai-capex" / "card-2026-10-28.png"
    assert dst.read_bytes() == b"png"
    assert mod.copy_dashboard_card({"as_of": "2026-10-29"}, tmp_path / "nowhere") is False
    assert "/dashboards/ai-capex" in mod.PATHS


def test_og_pages_always_leaves_a_copy(tmp_path):
    (tmp_path / "index.html").write_text("<html><head></head></html>")
    _script("og_pages").main(tmp_path)  # no snapshot: the plain page, so the rewrite never 404s
    assert (tmp_path / "dashboards" / "ai-capex.html").read_text() == "<html><head></head></html>"
