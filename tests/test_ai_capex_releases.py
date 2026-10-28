from castelino.adoption.sources.edgar import Release
from castelino.dashboards.ai_capex import releases
from castelino.dashboards.ai_capex.releases import Kpi, KpiTable

TEXT = (
    "Microsoft Cloud revenue was $49.1 billion. Azure and other cloud services revenue increased 40%. "
    "Commercial remaining performance obligation increased 51% to $683 billion."
)
REL = Release("MSFT", "0000950170-26-000101", "8-K", "2026-10-28", "https://sec.gov/x/ex99.htm")


def test_checked_drops_unprinted():
    table = KpiTable(
        period="first quarter fiscal 2027",
        kpis=[
            Kpi(name="Azure growth", value=40, unit="percent", quote="Azure and other cloud services revenue increased 40%"),
            Kpi(name="RPO", value=690, unit="billions", quote="Commercial remaining performance obligation increased 51% to $683 billion"),
            Kpi(name="made up", value=12, unit="percent", quote="Copilot seats grew 12%"),
        ],
    )  # fmt: skip
    kept = releases.checked_kpis(table, TEXT)
    assert [k.name for k in kept.kpis] == ["Azure growth"]


class FakeClient:
    def release_text(self, r):
        return TEXT


class CountingReader:
    calls = 0

    def __call__(self, **ctx):
        CountingReader.calls += 1
        assert "commercial remaining performance obligation" in ctx["wanted"]
        return KpiTable(
            period="first quarter fiscal 2027",
            kpis=[Kpi(name="commercial remaining performance obligation", value=683, unit="billions",
                      quote="Commercial remaining performance obligation increased 51% to $683 billion")],
        )  # fmt: skip


def test_read_release_uses_cache(tmp_path):
    CountingReader.calls = 0
    first = releases.read_release("MSFT", REL, FakeClient(), tmp_path, reader=CountingReader)
    again = releases.read_release("MSFT", REL, FakeClient(), tmp_path, reader=CountingReader)
    assert CountingReader.calls == 1
    assert first == again
    assert first["kpis"]["commercial remaining performance obligation"]["value"] == 683
    assert first["accession"] == REL.accession and first["url"] == REL.url
