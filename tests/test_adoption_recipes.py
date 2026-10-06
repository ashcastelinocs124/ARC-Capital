import json

import httpx

from castelino.adoption.sources.jobs import JobCounts, JobsFetcher
from castelino.adoption.sources.recipes import Recipe, replay


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_json_recipe_pages_until_empty():
    def handler(request):
        page = int(request.url.params["page"])
        jobs = {1: ["ML Engineer", "Cook"], 2: ["Barista"]}.get(page, [])
        return httpx.Response(200, json={"data": {"jobs": [{"name": t} for t in jobs]}})

    r = Recipe(
        kind="json", url="https://x.example/api?page={page}", items="data.jobs", title="name"
    )
    assert replay(r, client(handler)) == ["ML Engineer", "Cook", "Barista"]


def test_json_recipe_stops_when_site_ignores_page_param():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[{"title": "Same Job"}])  # every page identical

    r = Recipe(kind="json", url="https://x.example/jobs?p={page}")
    assert replay(r, client(handler)) == ["Same Job"]
    assert len(calls) == 2


def test_json_recipe_post_body_offset_stays_an_int():
    def handler(request):
        body = json.loads(request.content)
        assert isinstance(body["from"], int) and body["q"] == ""
        jobs = [{"title": "Data Scientist"}] if body["from"] == 0 else []
        return httpx.Response(200, json={"hits": jobs})

    r = Recipe(
        kind="json",
        url="https://x.example/search",
        method="POST",
        body={"from": "{offset}", "size": 10, "q": ""},
        items="hits",
        page_size=10,
    )
    assert replay(r, client(handler)) == ["Data Scientist"]


def test_unpaged_json_recipe_is_one_request():
    r = Recipe(kind="json", url="https://x.example/all.json", items="jobs")
    h = client(lambda req: httpx.Response(200, json={"jobs": [{"title": "AI Engineer"}]}))
    assert replay(r, h) == ["AI Engineer"]


def test_fetcher_replays_saved_recipe_and_misses_cleanly(tmp_path):
    (tmp_path / "ACME.json").write_text(
        Recipe(kind="json", url="https://x.example/all.json", items="jobs").model_dump_json()
    )
    h = client(
        lambda req: httpx.Response(
            200, json={"jobs": [{"title": "Machine Learning Engineer"}, {"title": "Clerk"}]}
        )
    )
    boards = {"ACME": ("recipe", "ACME"), "GONE": ("recipe", "GONE")}
    f = JobsFetcher(boards, http=h, recipes_dir=tmp_path)
    assert f.counts("ACME") == JobCounts(ai=1, total=2)
    assert f.counts("GONE") is None  # no recipe file → Hire missing, not a crash
