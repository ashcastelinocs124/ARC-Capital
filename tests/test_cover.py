import httpx

from castelino import cover, substack


def test_prompt_clamps_title_and_scene_and_keeps_only_people_the_post_names():
    daly = cover.Person(name="Mary Daly", role="SF Fed President", look="thoughtful")
    ghost = cover.Person(name="Someone Invented", role="CEO", look="grim")
    brief = cover.CoverBrief(
        title="inflation heats up again today", people=[daly, ghost], scene=list("abcdefg")
    )
    text = cover.prompt(brief, "Mary Daly said the Fed can wait.")
    assert '"INFLATION HEATS UP"' in text
    assert "a; b; c; d; e." in text
    assert "Mary Daly (SF Fed President), thoughtful" in text and "Someone Invented" not in text
    generic = cover.prompt(brief, "Mary Daly said the Fed can wait.", people=False)
    assert "Mary Daly" not in generic and "generic businesspeople" in generic


def test_cached_cover_is_reused_and_a_failure_returns_none(tmp_path, monkeypatch):
    png = tmp_path / "c.png"
    png.write_bytes(b"x")

    def boom(self, **kw):
        raise RuntimeError("model down")

    monkeypatch.setattr(cover.CoverArtist, "__call__", boom)
    assert cover.make(png, "h", ["s"]) == png  # cached: no model call
    assert cover.make(png, "h", ["s"], force=True) is None  # failure never raises


class FakeClient:
    """Just enough of httpx.Client for push(): a draft that may already have a cover."""

    def __init__(self, draft):
        self.draft, self.put_json = draft, None

    def __call__(self, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _r(self, body):
        return httpx.Response(200, json=body, request=httpx.Request("GET", "https://x"))

    def get(self, url):
        return self._r(self.draft)

    def post(self, url, json):
        return self._r({"url": "https://img/cover.png"})

    def put(self, url, json):
        self.put_json = json
        return self._r({})


def _push(tmp_path, monkeypatch, draft):
    monkeypatch.setenv("SUBSTACK_PUBLICATION_URL", "https://pub")
    monkeypatch.setenv("SUBSTACK_SID", "sid")
    client, calls = FakeClient(draft), []
    monkeypatch.setattr(substack.httpx, "Client", client)
    marker = tmp_path / "m.json"
    marker.write_text('{"draft_id": 1}')
    png = tmp_path / "c.png"
    png.write_bytes(b"x")
    substack.push(
        marker=marker,
        title="t",
        subtitle="s",
        pngs={},
        body=lambda up: {},
        label="d",
        cover=lambda: calls.append(1) or png,
    )
    return client.put_json, calls


def test_cover_is_set_only_on_a_draft_without_one(tmp_path, monkeypatch):
    sent, calls = _push(tmp_path, monkeypatch, {"cover_image": None})
    assert sent["cover_image"] == "https://img/cover.png" and calls == [1]
    sent, calls = _push(tmp_path, monkeypatch, {"cover_image": "https://mine.png"})
    assert "cover_image" not in sent and calls == []  # your own cover is kept, nothing is drawn
