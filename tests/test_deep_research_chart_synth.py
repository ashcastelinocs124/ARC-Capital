from castelino.agents.base import FakeLLMClient
from castelino.agents.research.deep.models import (
    ChartSpec,
    ChartType,
    DeepResearchReport,
    SubFinding,
)
from castelino.agents.research.deep.synthesizer import Synthesizer


def test_synthesizer_passes_through_chart_specs():
    fake = FakeLLMClient()
    fake.register("DeepResearchReport", lambda s, u: DeepResearchReport(
        exec_summary="Apple is rate sensitive.",
        confidence=0.8,
        chart_specs=[ChartSpec(type=ChartType.PRICE_HISTORY, title="AAPL 1Y",
                               symbols=["AAPL"], rationale="price trend")],
    ))
    syn = Synthesizer(llm=fake)
    report = syn.synthesize(
        reworded_query="How is Apple doing?",
        findings=[SubFinding(sub_question_id="q1", summary="up")],
    )
    assert len(report.chart_specs) == 1
    assert report.chart_specs[0].symbols == ["AAPL"]
