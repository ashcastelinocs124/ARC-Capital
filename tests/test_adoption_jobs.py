import httpx

from castelino.adoption.sources.jobs import JobCounts, JobsFetcher, is_ai_ml_role, load_boards


def test_is_ai_ml_role():
    for t in ["Senior Machine Learning Engineer", "Research Scientist, NLP", "Data Scientist",
              "Staff AI Engineer", "LLM Applied Scientist"]:
        assert is_ai_ml_role(t), t
    for t in ["Account Executive", "Software Engineer", "AI Sales Manager", "Maintenance Engineer"]:
        assert not is_ai_ml_role(t), t


def handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if "boards-api.greenhouse.io/v1/boards/acme/jobs" in u:
        return httpx.Response(200, json={"jobs": [
            {"title": "Senior Machine Learning Engineer"}, {"title": "Account Executive"},
            {"title": "Software Engineer"}]})
    if "api.lever.co/v0/postings/lvr" in u:
        return httpx.Response(200, json=[{"text": "Research Scientist, NLP"}, {"text": "Recruiter"}])
    return httpx.Response(404)


def fetcher():
    boards = {"ACME": ("greenhouse", "acme"), "LVR": ("lever", "lvr"),
              "BAD": ("workday", "x"), "GONE": ("greenhouse", "missing")}
    return JobsFetcher(boards, http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_counts_greenhouse_and_lever():
    f = fetcher()
    assert f.counts("ACME") == JobCounts(ai=1, total=3)
    assert f.counts("LVR") == JobCounts(ai=1, total=2)


def test_counts_none_when_unmapped_unsupported_or_failing():
    f = fetcher()
    assert f.counts("NOPE") is None
    assert f.counts("BAD") is None
    assert f.counts("GONE") is None


def test_load_boards(tmp_path):
    p = tmp_path / "job_boards.csv"
    p.write_text("ticker,ats,token\nacme,greenhouse,acme-inc\nLVR,lever,lvr\n")
    assert load_boards(p) == {"ACME": ("greenhouse", "acme-inc"), "LVR": ("lever", "lvr")}
