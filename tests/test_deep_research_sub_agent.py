from castelino.agents.base import FakeLLMClient
from castelino.agents.research.deep.models import SourceRef, SubFinding, SubQuestion
from castelino.agents.research.deep.sonar_client import FakeSonarClient, SonarResult
from castelino.agents.research.deep.sub_agent import SubAgent


def _fake_llm():
    fake = FakeLLMClient()
    fake.register("SubFinding", lambda s, u: SubFinding(
        sub_question_id="q1", summary="distilled", key_points=["a", "b"],
        confidence=0.8,
    ))
    return fake


def test_sub_agent_happy_path():
    sonar = FakeSonarClient()
    sonar.register("cpi", SonarResult(
        content="CPI was 3.1%", sources=[SourceRef(title="BLS", url="https://bls.gov")],
    ))
    sa = SubAgent(llm=_fake_llm(), sonar=sonar)
    finding = sa.run(SubQuestion(id="q1", text="What is current CPI?"))
    assert finding.sub_question_id == "q1"
    assert finding.summary == "distilled"
    # citations come from Sonar, merged onto the finding
    assert any(c.url == "https://bls.gov" for c in finding.citations)
    assert finding.error is None


def test_sub_agent_sonar_empty_flags_error():
    sonar = FakeSonarClient(default=SonarResult(content="", sources=[]))
    sa = SubAgent(llm=_fake_llm(), sonar=sonar)
    finding = sa.run(SubQuestion(id="q9", text="obscure thing"))
    assert finding.error is not None
    assert finding.sub_question_id == "q9"
    assert finding.confidence == 0.0
