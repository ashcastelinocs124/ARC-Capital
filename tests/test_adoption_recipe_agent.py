import json
from types import SimpleNamespace

from castelino.adoption import recipe_agent
from castelino.adoption.recipe_agent import RecipeWriter

GOOD = {"kind": "json", "url": "https://jobs.acme.com/api?page={page}", "items": "jobs"}
EVIL = {"kind": "json", "url": "https://elsewhere.example/api", "items": "jobs"}


def call(name, **args):
    return SimpleNamespace(
        type="function_call", name=name, arguments=json.dumps(args), call_id=f"c-{name}"
    )


def reply(*calls, text=""):
    usage = SimpleNamespace(
        input_tokens=1000, output_tokens=100, input_tokens_details=SimpleNamespace(cached_tokens=0)
    )
    return SimpleNamespace(id="r", output=list(calls), output_text=text, usage=usage)


class FakeClient:
    """Plays back scripted model turns and records what our code sent back."""

    def __init__(self, turns):
        self.turns, self.sent = list(turns), []
        self.responses = self

    def create(self, **kw):
        self.sent.append(kw)
        return self.turns.pop(0)


class FakeBrowser:
    def open_page(self, url):
        return {"final_url": url, "title": "Careers", "text": "", "links": [], "json_requests": []}

    def close(self):
        pass


def writer(turns, monkeypatch, titles=("Machine Learning Engineer", "Cashier")):
    monkeypatch.setattr(recipe_agent.recipes, "replay", lambda r, **kw: list(titles))
    client = FakeClient(turns)
    return RecipeWriter(client=client, browser_factory=FakeBrowser), client


def test_submit_accepted_only_after_our_replay(monkeypatch):
    w, client = writer(
        [reply(call("test_recipe", recipe=GOOD)), reply(call("submit_recipe", recipe=GOOD))],
        monkeypatch,
    )
    res = w.run("ACME", "Acme Inc.", "https://careers.acme.com/")
    assert res.recipe is not None and res.count == 2 and res.steps == 2
    tested = json.loads(client.sent[1]["input"][0]["output"])
    assert tested == {"count": 2, "sample": ["Machine Learning Engineer", "Cashier"]}
    assert res.cost_usd == 2 * (1000 * 10 + 100 * 50) / 1e6


def test_recipe_on_another_host_is_refused(monkeypatch):
    w, client = writer(
        [reply(call("submit_recipe", recipe=EVIL)), reply(text="giving up")], monkeypatch
    )
    res = w.run("ACME", "Acme Inc.", "https://careers.acme.com/")
    assert res.recipe is None and res.note == "giving up"
    assert "not the company's site" in json.loads(client.sent[1]["input"][0]["output"])["error"]


def test_empty_replay_is_refused(monkeypatch):
    w, _ = writer(
        [reply(call("submit_recipe", recipe=GOOD)), reply(text="no jobs found")],
        monkeypatch,
        titles=(),
    )
    assert w.run("ACME", "Acme Inc.", "https://careers.acme.com/").recipe is None


def test_step_cap_stops_the_loop(monkeypatch):
    turns = [reply(call("open_page", url="https://careers.acme.com/"))] * 30
    w, client = writer(turns, monkeypatch)
    res = w.run("ACME", "Acme Inc.", "https://careers.acme.com/")
    assert res.recipe is None and "step cap" in res.note
    assert len(client.sent) == w._cfg.recipe_max_steps


def test_incomplete_recipe_is_refused(monkeypatch):
    # The site shows 400 jobs but replay only reads the first page of 2 (Apple's first try).
    turns = [reply(call("submit_recipe", recipe=GOOD, expected_total=400)), reply(text="stuck")]
    w, client = writer(turns, monkeypatch)
    assert w.run("ACME", "Acme Inc.", "https://careers.acme.com/").recipe is None
    assert (
        "paging is probably not working"
        in json.loads(client.sent[1]["input"][0]["output"])["error"]
    )
