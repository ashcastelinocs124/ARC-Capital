from pathlib import Path

from fastapi.testclient import TestClient

from castelino.dashboard.endpoints import agent_catalog as cat


def _by_id(entries):
    return {e["id"]: e for e in entries}


def test_every_agent_class_in_code_is_registered():
    # adding a StructuredAgent without an agents.yaml entry must fail here
    body = cat.build_catalog()
    assert body["unregistered"] == []


def test_structured_agent_gets_live_prompt_tier_and_schema():
    e = _by_id(cat.build_catalog()["agents"])["update_agent"]
    assert "ARC Research" in e["prompt"] and e["prompt_source"].endswith(
        "UpdateAgent.system_prompt()"
    )
    assert e["tier"] == "reasoning" and e["model"]
    assert "headline" in [f["name"] for f in e["output"]["fields"]]
    assert e["tools"] and e["memory"]["reads"] and e["memory"]["persists"]


def test_prompt_constant_reference_for_non_structured_agent():
    e = _by_id(cat.build_catalog()["agents"])["deep_synthesizer"]
    assert e["prompt"] and ":SYNTH_SYSTEM" in e["prompt_source"]


def test_unregistered_and_broken_entries_do_not_500(tmp_path):
    reg = tmp_path / "agents.yaml"
    reg.write_text(
        "agents:\n"
        "  - {id: ghost, name: Ghost, group: Test, class: castelino.nope.Missing,\n"
        "     summary: s, tools: [], memory: {reads: [], writes: [], persists: none}}\n"
    )
    body = cat.build_catalog(reg)
    ghost = _by_id(body["agents"])["ghost"]
    assert ghost["error"] and ghost["prompt"] is None
    assert "UpdateAgent" in {u["class_name"] for u in body["unregistered"]}


def test_endpoint_serves_catalog(monkeypatch):
    from castelino.dashboard.main import app

    r = TestClient(app).get("/agents/catalog")
    assert r.status_code == 200
    data = r.json()
    assert len(data["agents"]) >= 18 and data["groups"]


def test_registry_file_lives_at_repo_root():
    assert cat.REGISTRY == Path(cat.ROOT) / "agents.yaml"


def test_dependencies_report_whether_each_key_is_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    deps = {
        d["key"]: d for d in _by_id(cat.build_catalog()["agents"])["update_agent"]["dependencies"]
    }
    assert deps["OPENAI_API_KEY"]["required"] is True and deps["OPENAI_API_KEY"]["set"] is True
    assert deps["FRED_API_KEY"]["required"] is False and deps["FRED_API_KEY"]["set"] is False
    assert "sk-test" not in str(deps)  # presence only, never the value


def test_every_agent_declares_dependencies():
    missing = [
        e["id"] for e in cat.build_catalog()["agents"] if "dependencies" not in e["raw_keys"]
    ]
    assert missing == []
