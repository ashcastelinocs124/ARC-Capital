from castelino.agents.research.deep.models import SourceRef
from castelino.agents.research.deep.sonar_client import (
    FakeSonarClient,
    SonarResult,
)


def test_fake_sonar_returns_registered_result():
    fake = FakeSonarClient()
    fake.register("inflation", SonarResult(
        content="CPI rose 3.1% YoY",
        sources=[SourceRef(title="BLS", url="https://bls.gov", snippet="CPI 3.1%")],
    ))
    out = fake.search("what is inflation right now")
    assert "3.1%" in out.content
    assert out.sources[0].url == "https://bls.gov"
    assert fake.call_count == 1


def test_fake_sonar_default_when_unmatched():
    fake = FakeSonarClient(default=SonarResult(content="no data", sources=[]))
    out = fake.search("anything")
    assert out.content == "no data"
