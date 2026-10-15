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
    e = _by_id(cat.build_catalog()["agents"])["update_editor"]
    assert "ARC Research" in e["prompt"]
    assert e["prompt_source"].endswith("UpdateEditor.system_prompt()")
    assert e["tier"] == "reasoning" and e["model"] == "gpt-6-sol"
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
    assert "UpdateEditor" in {u["class_name"] for u in body["unregistered"]}


def test_endpoint_serves_catalog(monkeypatch):
    from castelino.dashboard.main import app

    r = TestClient(app).get("/admin/agents/catalog")
    assert r.status_code == 200
    data = r.json()
    assert len(data["agents"]) >= 13 and data["groups"]
    assert data["agents"][0]["prompt"] is not None or data["agents"][0]["error"]  # full detail


def test_public_catalog_is_high_level_only():
    from castelino.dashboard.main import app

    r = TestClient(app).get("/agents/catalog")
    assert r.status_code == 200
    data = r.json()
    assert len(data["agents"]) >= 13 and data["groups"] and data["pipelines"]
    allowed = {"id", "name", "group", "family", "summary"}
    assert all(set(a) == allowed for a in data["agents"])
    assert "unregistered" not in data and "systems" not in data
    # Sector Sentiment and AI Adoption stay on /admin only
    assert not {"sector-sentiment", "ai-adoption"} & {p["id"] for p in data["pipelines"]}
    assert not {"sector_narrative", "sector_prose", "adoption_extractor", "recipe_writer"} & {
        a["id"] for a in data["agents"]
    }
    assert "Research metrics" not in data["groups"]
    text = r.text
    for private in ("class_path", "prompt", "OPENAI_API_KEY", "castelino.agents", "gpt-6"):
        assert private not in text


def test_registry_file_lives_at_repo_root():
    assert cat.REGISTRY == Path(cat.ROOT) / "agents.yaml"


def test_dependencies_report_whether_each_key_is_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    deps = {
        d["key"]: d for d in _by_id(cat.build_catalog()["agents"])["macro_agent"]["dependencies"]
    }
    assert deps["OPENAI_API_KEY"]["required"] is True and deps["OPENAI_API_KEY"]["set"] is True
    assert deps["FRED_API_KEY"]["required"] is False and deps["FRED_API_KEY"]["set"] is False
    assert "sk-test" not in str(deps)  # presence only, never the value


def test_every_agent_declares_dependencies():
    missing = [
        e["id"] for e in cat.build_catalog()["agents"] if "dependencies" not in e["raw_keys"]
    ]
    assert missing == []


def test_system_diagrams_reference_real_agents_and_groups():
    body = cat.build_catalog()
    ids = {e["id"] for e in body["agents"]}
    groups = set(body["groups"])
    systems = body["systems"]
    assert {s["group"] for s in systems} == groups, "every group needs exactly one system diagram"
    for s in systems:
        for lane in s["lanes"]:
            where = f"{s['group']} / {lane['title']}"
            assert 1 <= len(lane["flow"]) <= 5, f"{where}: keep lanes to 5 steps or split them"
            for step in lane["flow"]:
                for box in step:
                    kind, _, rest = box.partition(":")
                    target = rest.split("|")[0]
                    if kind == "agent":
                        assert target in ids, f"{where}: unknown agent {target!r}"
                    if kind == "system":
                        assert target in groups, f"{where}: unknown system {target!r}"
            for ref in lane.get("loops", []) + lane.get("regions", []):
                assert 0 <= ref["from"] < len(lane["flow"]), where
                assert 0 <= ref["to"] < len(lane["flow"]), where


def test_every_agent_appears_in_its_groups_diagram():
    """Each agent's Arch tab on /agents shows the lanes it appears in, so none may be missing."""
    body = cat.build_catalog()
    drawn = {
        s["group"]: {
            b.partition(":")[2].split("|")[0]
            for lane in s["lanes"]
            for step in lane["flow"]
            for b in step
            if b.startswith("agent:")
        }
        for s in body["systems"]
    }
    missing = [e["id"] for e in body["agents"] if e["id"] not in drawn.get(e["group"], set())]
    assert not missing, f"add these agents to their group's diagram in agents.yaml: {missing}"


def test_pipelines_reference_real_agents_nodes_and_edges():
    """The public /agents graphs: every reference resolves, and every agent but the admin desk is drawn."""
    body = cat.build_catalog()
    ids = {e["id"] for e in body["agents"]}
    drawn = set()
    for p in body["pipelines"]:
        nodes = {n["id"]: n for n in p["nodes"]}
        groups = {g["id"]: g for g in p.get("groups", [])}
        boxes = nodes.keys() | groups.keys()
        assert len(boxes) == len(p["nodes"]) + len(groups), f"{p['id']}: duplicate node or group id"
        for n in nodes.values():
            where = f"{p['id']} / {n['id']}"
            assert n["kind"] in {
                "source",
                "llm",
                "code",
                "guard",
                "trigger",
                "human",
                "out",
                "stop",
            }, where
            assert n["layer"] in {"sources", "agents", "guardrails", "delivery"}, where
            assert (n["kind"] == "llm") == ("agent" in n), (
                f"{where}: llm nodes, and only they, name an agent"
            )
            if "agent" in n:
                assert n["agent"] in ids, f"{where}: unknown agent {n['agent']!r}"
                drawn.add(n["agent"])
        for g in groups.values():
            assert set(g["nodes"]) <= nodes.keys(), f"{p['id']} / group {g['id']}"
        edges = set()
        for e in p["edges"]:
            a, _, b = e.split("|")[0].partition(">")
            a, b = a.strip(), b.strip()
            assert a in boxes and b in boxes, f"{p['id']}: edge {e!r}"
            edges.add(f"{a}>{b}")
        for s in p["steps"]:
            where = f"{p['id']} / step {s['title']}"
            assert s["edges"], f"{where}: its number sits on its first edge"
            assert set(s["nodes"]) <= boxes, where
            assert {e.replace(" ", "") for e in s["edges"]} <= edges, where
    assert ids - drawn == {"desk_chat"}, (
        f"draw these agents in a pipeline: {ids - drawn - {'desk_chat'}}"
    )


def test_update_agent_family_groups_its_seven_agents():
    fam = [e["id"] for e in cat.build_catalog()["agents"] if e.get("family") == "Update Agent"]
    assert fam == [
        "update_orchestrator",
        "macro_agent",
        "news_agent",
        "alt_agent",
        "ai_agent",
        "update_editor",
        "desk_chat",
    ]
