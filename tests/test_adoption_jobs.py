import json

import httpx

from castelino.adoption.sources.jobs import JobCounts, JobsFetcher, is_ai_ml_role, load_boards


def test_is_ai_ml_role():
    for t in [
        "Senior Machine Learning Engineer",
        "Research Scientist, NLP",
        "Data Scientist",
        "Staff AI Engineer",
        "LLM Applied Scientist",
    ]:
        assert is_ai_ml_role(t), t
    for t in ["Account Executive", "Software Engineer", "AI Sales Manager", "Maintenance Engineer"]:
        assert not is_ai_ml_role(t), t


def handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if "boards-api.greenhouse.io/v1/boards/acme/jobs" in u:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {"title": "Senior Machine Learning Engineer"},
                    {"title": "Account Executive"},
                    {"title": "Software Engineer"},
                ]
            },
        )
    if "api.lever.co/v0/postings/lvr" in u:
        return httpx.Response(
            200, json=[{"text": "Research Scientist, NLP"}, {"text": "Recruiter"}]
        )
    if u == "https://wdco.wd5.myworkdayjobs.com/wday/cxs/wdco/Careers/jobs":
        # 25 postings: a full page of 20 then 5; one has no title (seen live on Caterpillar's board).
        offset = json.loads(request.content)["offset"]
        jobs = [{"title": "Machine Learning Engineer"}] * 3 + [{"title": "Nurse"}] * 21 + [{}]
        return httpx.Response(200, json={"total": 25, "jobPostings": jobs[offset : offset + 20]})
    if u.startswith(
        "https://ora.example.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    ):
        finder = request.url.params["finder"]
        assert "siteNumber=CX_1" in finder
        # Page 1 is short (24 of 25), as Oracle really does mid-listing; reading must go on.
        pages = {
            "offset=0": [{"Title": "AI Engineer"}] + [{"Title": "Teller"}] * 23,
            "offset=25": [{"Title": "Teller"}],
        }
        reqs = next((v for k, v in pages.items() if finder.endswith(k)), [])
        return httpx.Response(200, json={"items": [{"requisitionList": reqs}]})
    if u == "https://recruiting2.ultipro.com/TEN1/JobBoard/abc-123/JobBoardView/LoadSearchResults":
        skip = json.loads(request.content)["opportunitySearch"]["Skip"]
        return httpx.Response(
            200, json={"opportunities": [{"Title": "Data Scientist"}] if skip == 0 else []}
        )
    if u.startswith("https://www.amazon.jobs/en/search.json"):
        first = request.url.params["offset"] == "0"
        jobs = [{"title": "Applied Scientist"}, {"title": "Area Manager"}] if first else []
        return httpx.Response(200, json={"jobs": jobs})
    return httpx.Response(404)


def fetcher():
    boards = {
        "ACME": ("greenhouse", "acme"),
        "LVR": ("lever", "lvr"),
        "WD": ("workday", "wdco/wd5/Careers"),
        "ORA": ("oracle", "ora.example.com/CX_1"),
        "AMZN": ("amazon", "amazon"),
        "UKG": ("ukg", "recruiting2.ultipro.com/TEN1/abc-123"),
        "BAD": ("icims", "x"),
        "GONE": ("greenhouse", "missing"),
    }
    return JobsFetcher(boards, http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_counts_every_supported_board():
    f = fetcher()
    assert f.counts("ACME") == JobCounts(ai=1, total=3)
    assert f.counts("LVR") == JobCounts(ai=1, total=2)
    assert f.counts("WD") == JobCounts(ai=3, total=24)  # both pages read; untitled posting skipped
    assert f.counts("ORA") == JobCounts(ai=1, total=25)  # kept reading past the short page
    assert f.counts("AMZN") == JobCounts(ai=1, total=2)
    assert f.counts("UKG") == JobCounts(ai=1, total=1)


def test_counts_none_when_unmapped_unsupported_or_failing():
    f = fetcher()
    assert f.counts("NOPE") is None
    assert f.counts("BAD") is None
    assert f.counts("GONE") is None


def test_load_boards(tmp_path):
    p = tmp_path / "job_boards.csv"
    p.write_text("ticker,ats,token\nacme,greenhouse,acme-inc\nLVR,lever,lvr\n")
    assert load_boards(p) == {"ACME": ("greenhouse", "acme-inc"), "LVR": ("lever", "lvr")}
