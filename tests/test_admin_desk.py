import base64
import json

from fastapi.testclient import TestClient

from castelino.agents.update import desk
from castelino.agents.update.models import AgentOutput, Fact, MorningNote
from tests.test_update_runner import build, make_note, output, record


def test_runner_saves_briefs_for_the_desk(tmp_path):
    runner, _ = build(tmp_path)
    runner.run_if_due()
    assert (
        json.loads((tmp_path / "updates" / "briefs" / "2026-10-07.json").read_text())["macro"]
        == "m"
    )


def test_merge_output_continues_ids_and_reuses_known_facts():
    day = output("macro", n=3)  # facts M1..M3, findings macro-1..3
    new = output("macro", n=2)  # facts M1, M2 (M1's text is new below), findings macro-1, macro-2
    new.facts[0] = new.facts[0].model_copy(update={"text": "fresh fact: 3.71%"})
    findings, facts, added = desk.merge_output(day.findings, day.facts, new)
    assert added == 2
    assert [f.id for f in facts] == ["M1", "M2", "M3", "M4"]  # new M1 → M4; new M2 = known M2
    assert [f.id for f in findings][-2:] == ["macro-4", "macro-5"]
    assert findings[-2].fact_ids == ["M4"] and findings[-1].fact_ids == ["M2"]


def test_rebuild_rewrites_note_and_keeps_backup(tmp_path):
    runner, _ = build(tmp_path)
    runner.run_if_due()
    note = make_note()
    note.headline = "Rebuilt headline at 3.71%"
    runner.editor_fn = lambda *a: note
    assert runner.rebuild("2026-10-07") == "Rebuilt headline at 3.71%"
    assert record(tmp_path).note.headline == "Rebuilt headline at 3.71%"
    assert len(list((tmp_path / "updates").glob("hidden-rebuild-*/2026-10-07.json"))) == 1


def test_rebuild_guard_failure_keeps_old_note(tmp_path):
    runner, _ = build(tmp_path)
    runner.run_if_due()
    before = record(tmp_path).note.headline
    runner.editor_fn = lambda *a: MorningNote(
        headline="x", takeaways=[], items=[], themes_touched=[], new_themes=[]
    )
    try:
        runner.rebuild("2026-10-07")
        raise AssertionError("expected guard failure")
    except RuntimeError as e:
        assert "guard failed" in str(e)
    assert record(tmp_path).note.headline == before


def test_chat_context_scopes_to_the_agent():
    rec_out = [output(a) for a in ("macro", "news")]
    from castelino.agents.update.models import DailyRecordV2

    rec = DailyRecordV2(
        date="2026-10-07",
        generated_at="t",
        findings=[f for o in rec_out for f in o.findings],
        note=make_note(fids=("macro-1", "news-1", "macro-2")),
        exhibits=[],
        releases=[],
        rounds=0,
        data_gaps=[],
    )
    facts: list[Fact] = [f for o in rec_out for f in o.facts]
    ctx = desk.chat_context(rec, facts, "news")
    assert "[news-1]" in ctx and "[N1]" in ctx and "[macro-1]" not in ctx and "[M1]" not in ctx
    assert "headline" in desk.chat_context(rec, facts, "editor")


def _basic(pw):
    return {"Authorization": "Basic " + base64.b64encode(f"admin:{pw}".encode()).decode()}


def test_fly_app_requires_the_admin_password(tmp_path, monkeypatch):
    from castelino.dashboard.desk_app import app

    (tmp_path / "updates").mkdir()
    monkeypatch.setattr(desk, "_dirs", lambda: (tmp_path, tmp_path / "updates"))
    c = TestClient(app)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert c.get("/admin/desk/days", headers=_basic("")).status_code == 401  # unset = nobody
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    assert c.get("/admin/desk/days").status_code == 401
    assert c.get("/admin/desk/days", headers=_basic("wrong")).status_code == 401
    r = c.get("/admin/desk/days", headers=_basic("s3cret"))
    assert r.status_code == 200 and r.json() == {"days": []}
    assert (
        c.post("/refresh", headers=_basic("s3cret")).status_code == 404
    )  # only the desk is served


def test_session_cookie_matches_the_site_and_opens_fly(tmp_path, monkeypatch):
    from castelino.dashboard import desk_app

    # same exp + secret as frontend/middleware.ts sign() → identical signature
    assert (
        desk_app.session_sig(1800000000, "s3cret:with:colons")
        == "smEVKfcHCDy6cu9reOa4c-0zU9pAQgN9v_T7RNLKYy0"
    )
    (tmp_path / "updates").mkdir()
    monkeypatch.setattr(desk, "_dirs", lambda: (tmp_path, tmp_path / "updates"))
    monkeypatch.setenv("ADMIN_PASSWORD", "s3cret")
    c = TestClient(desk_app.app)
    exp = 4000000000
    good = f"arc_admin={exp}.{desk_app.session_sig(exp, 's3cret')}"
    assert c.get("/admin/desk/days", headers={"cookie": f"x=1; {good}"}).status_code == 200
    bad = f"arc_admin={exp + 1}.{desk_app.session_sig(exp, 's3cret')}"
    assert c.get("/admin/desk/days", headers={"cookie": bad}).status_code == 401
    old = f"arc_admin=1000.{desk_app.session_sig(1000, 's3cret')}"
    assert c.get("/admin/desk/days", headers={"cookie": old}).status_code == 401  # expired
    r = c.get("/admin/desk/days")
    assert r.status_code == 401 and "www-authenticate" not in r.headers


def test_rerun_endpoint_merges_findings(tmp_path, monkeypatch):
    from castelino.dashboard.endpoints import admin_desk
    from castelino.dashboard.main import app

    runner, _ = build(tmp_path)
    runner.run_if_due()
    monkeypatch.setattr(desk, "_dirs", lambda: (tmp_path, tmp_path / "updates"))
    seen = {}

    def fake_run(brief, ask, **kw):
        seen.update(brief=brief, ask=ask, kw=kw)
        out = output("news", n=1)
        return AgentOutput(
            facts=[out.facts[0].model_copy(update={"text": "new story 2%"})], findings=out.findings
        )

    monkeypatch.setattr(desk, "_run_fn", lambda agent: fake_run)
    monkeypatch.setattr(admin_desk.threading, "Thread", _Inline)
    r = TestClient(app).post("/admin/desk/2026-10-07/news/rerun", json={"ask": "dig into oil"})
    assert r.status_code == 200 and r.json()["state"] == "done", r.json()
    assert seen["brief"] == "n" and seen["ask"] == "dig into oil" and "day" in seen["kw"]
    assert [f.id for f in record(tmp_path).findings if f.agent == "news"] == [
        "news-1",
        "news-2",
        "news-3",
    ]


class _Inline:
    def __init__(self, target, daemon):
        self.target = target

    def start(self):
        self.target()
