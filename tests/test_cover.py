import httpx

from castelino import cover, substack


def test_prompt_clamps_title_and_scene_and_keeps_only_people_the_post_names():
    daly = cover.Person(name="Mary Daly", role="SF Fed President", org="SF Fed", look="thoughtful")
    huang = cover.Person(name="Jensen Huang", role="NVIDIA CEO", org="NVIDIA", look="stern")
    ghost = cover.Person(name="Someone Invented", role="CEO", org="Acme", look="grim")
    firm = cover.Person(name="NVIDIA", role="chipmaker", org="NVIDIA", look="stern")  # not a person
    brief = cover.CoverBrief(
        title="inflation heats up again today",
        concept="a tug of war between the Fed seal and an NVIDIA chip.",
        people=[daly, ghost, firm, huang],
        scene=list("abcdefg"),
    )
    text = cover.prompt(brief, "Mary Daly said the Fed can wait as NVIDIA fell.")
    assert '"INFLATION HEATS UP"' in text
    assert (
        "The idea: a tug of war between the Fed seal and an NVIDIA chip. In the background: a; b; c."
        in text
    )
    who = text.split("sharp focus,")[1]  # named in the post, or leads a company it names
    assert who.lstrip().startswith(
        "Mary Daly (SF Fed President), thoughtful; Jensen Huang (NVIDIA CEO)"
    )
    assert "Someone Invented" not in text and "NVIDIA (chipmaker)" not in text
    generic = cover.prompt(brief, "Mary Daly said the Fed can wait.", people=False)
    assert "Mary Daly" not in generic and "generic businessperson" in generic


def test_prompt_draws_in_the_given_style_with_no_numbers_and_at_most_two_people():
    people = [
        cover.Person(name=n, role="CEO", org=o, look="straining")
        for n, o in [
            ("Sundar Pichai", "Alphabet"),
            ("Satya Nadella", "Microsoft"),
            ("Lisa Su", "AMD"),
        ]
    ]
    brief = cover.CoverBrief(title="Cloud race", concept="a relay race", people=people, scene=[])
    text = cover.prompt(brief, "Alphabet, Microsoft and AMD reported.", style="poster")
    assert cover.STYLES["poster"] in text and cover.STYLES["photo"] not in text
    assert "no numbers, prices or percentages" in text and "In the background" not in text
    assert "Satya Nadella" in text and "Lisa Su" not in text  # 2 people at most


def test_each_cover_takes_the_next_style_so_no_two_in_a_row_match(tmp_path, monkeypatch):
    monkeypatch.setattr(cover, "_log", lambda: tmp_path / "cover_people.json")
    assert cover.next_style("a.png") == "photo"  # no covers yet
    (tmp_path / "cover_people.json").write_text('[{"key": "old.png", "people": []}]')
    assert cover.next_style("a.png") == "illustration"  # covers before the rotation were photo
    for key in ("a.png", "b.png", "c.png"):
        cover._remember(key, [], cover.next_style(key))
    assert [r["style"] for r in cover._rows()[1:]] == ["illustration", "poster", "papercut"]
    assert cover.next_style("d.png") == "photo"  # wraps around
    assert cover.next_style("c.png") == "papercut"  # a redraw keeps its own style


def test_prompt_never_draws_jerome_powell_as_fed_chair():
    # 2026-10-23 cover: asked for Susan M. Collins at the Fed, the image model drew a Powell look-alike
    collins = cover.Person(
        name="Susan M. Collins", role="Boston Fed President", org="Fed", look="calm"
    )
    brief = cover.CoverBrief(
        title="Oil shock",
        concept="the Fed chair on a see-saw",
        people=[collins],
        scene=["the Federal Reserve building"],
    )
    for text in (
        cover.prompt(brief, "Susan M. Collins said"),
        cover.prompt(brief, "", people=False),
    ):
        assert "never draw Jerome Powell" in text and "Kevin Warsh" in text
        assert "No other recognisable real person" in text


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


def test_a_person_the_post_does_not_name_is_whoever_holds_the_role_today(monkeypatch):
    from castelino.data import web_search

    powell = cover.Person(name="Jerome Powell", role="Chair", org="Fed", look="grim")
    for answer, who in [("Someone Else", "Someone Else"), ("Jensen Huang.", "Jensen Huang"),
                        ("Jensen Huang ([nvidia.com](https://x))", "Jensen Huang"),
                        ("I could not find that.", None)]:  # fmt: skip
        monkeypatch.setattr(web_search, "search", lambda system, user, a=answer: (a, []))
        assert cover.holder(powell) == who


def test_nobody_on_the_last_covers_comes_back_unless_named(tmp_path, monkeypatch):
    monkeypatch.setattr(cover, "_log", lambda: tmp_path / "cover_people.json")
    for key, who in [("a.png", ["Kevin Warsh"]), ("b.png", ["Jensen Huang"]), ("c.png", [])]:
        cover._remember(key, who)
    assert cover.recent_people("d.png") == ["Kevin Warsh", "Jensen Huang"]
    cover._remember("d.png", ["Lisa Su"])  # a 4th cover pushes the 1st out of the last 3
    assert cover.recent_people("e.png") == ["Jensen Huang", "Lisa Su"]
    assert "Lisa Su" not in cover.recent_people("d.png")  # a redraw doesn't count against itself

    warsh = cover.Person(name="Kevin Warsh", role="Fed Chair", org="Fed", look="grim")
    musk = cover.Person(name="Elon Musk", role="Tesla CEO", org="Tesla", look="calm")
    asks, drawn = [], []
    monkeypatch.setattr(cover.CoverArtist, "__call__", lambda self, **kw: asks.append(kw) or
                        cover.CoverBrief(title="T", concept="c", people=[warsh, musk], scene=["s"]))  # fmt: skip
    monkeypatch.setattr(
        cover, "draw", lambda text, path: drawn.append(text) or path.write_bytes(b"x")
    )
    monkeypatch.setattr(cover, "holder", lambda p: p.name)  # no live web search in tests
    cover._remember("e.png", ["Kevin Warsh"])
    cover.make(tmp_path / "f.png", "Warsh speaks as Tesla reports", ["The Fed and Tesla"])
    assert asks[-1]["avoid"] == ["Lisa Su", "Kevin Warsh"] and asks[-1]["use"] == []
    # the prompt also names today's Fed chair, so look only at the portraits
    portraits = drawn[-1].split("No other recognisable")[0]
    assert "Elon Musk" in portraits and "Kevin Warsh" not in portraits

    cover.make(tmp_path / "g.png", "Warsh speaks", ["The Fed"], force=True, use=["Kevin Warsh"])
    assert asks[-1]["avoid"] == [] and "Kevin Warsh" in drawn[-1]  # the analyst's pick wins
