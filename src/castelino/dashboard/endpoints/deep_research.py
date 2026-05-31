from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from castelino.agents.research.deep.orchestrator import DeepResearchOrchestrator
from castelino.agents.research.deep.store import ResearchStore

router = APIRouter()

# Overridable in tests (set to a tmp_path Path to avoid writing into data/research).
_store_root = None


def _orch() -> DeepResearchOrchestrator:
    store = ResearchStore(root=_store_root) if _store_root else ResearchStore()
    return DeepResearchOrchestrator(store=store)


class StartRequest(BaseModel):
    query: str


class AnswersRequest(BaseModel):
    answers: dict[str, str] = {}


@router.post("/research/start")
def research_start(req: StartRequest):
    sess = _orch().start(req.query)
    return {
        "session_id": sess.id,
        "reworded_query": sess.reworded_query,
        "clarifying_questions": [q.model_dump() for q in sess.clarifying_questions],
        "status": sess.status.value,
    }


def _run_research_job(session_id: str, answers: dict):
    orch = _orch()
    sess = orch.run_first_round(session_id, answers=answers)
    if sess.status.value != "failed":
        orch.finish(session_id)


@router.post("/research/{session_id}/answers")
def research_answers(session_id: str, req: AnswersRequest, bg: BackgroundTasks):
    orch = _orch()
    sess = orch.store.load(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="unknown session")
    bg.add_task(_run_research_job, session_id, req.answers)
    return {"session_id": session_id, "status": "researching"}


@router.get("/research/{session_id}")
def research_get(session_id: str):
    sess = _orch().store.load(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="unknown session")
    return sess.model_dump(mode="json")


@router.get("/research")
def research_list():
    return [
        {"id": s.id, "original_query": s.original_query, "status": s.status.value,
         "updated_at": s.updated_at.isoformat()}
        for s in _orch().store.list()
    ]
