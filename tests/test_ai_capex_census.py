import io
from datetime import datetime

import openpyxl

from castelino.dashboards.ai_capex import census

Q7 = "In the last two weeks, did this business use Super Intelligence or SI (formerly AI)?"


def workbook(header: list, rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Response Estimates"
    for r in [header, *rows]:
        ws.append(r)
    dates = wb.create_sheet("Collection and Reference Dates")
    dates.append(["Sample Year", "Cycle", "Panel", "Smpdt", "Collection Start", "Col End", "Reference Period Start", "Ref End"])  # fmt: skip
    dates.append([3, 21, 1, 202621, datetime(2026, 10, 12), datetime(2026, 10, 25), datetime(2026, 9, 28), datetime(2026, 10, 11)])  # fmt: skip
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SIZE = workbook(
    ["Empsize", "Question ID", "Question", "Answer ID", "Answer", "202621", "202620"],
    [[c, 7, Q7, 1, "Yes", f"{v}%", "1.0%"] for c, v in zip("ABCDEFG", [24.3, 22.6, 24.6, 26.0, 29.0, 35.3, 43.6], strict=True)]
    + [["A", 7, Q7, 2, "No", "67.0%", "67.4%"], ["A", 24, "During the next six months ...", 1, "Yes", "28.1%", "27.3%"]],
)  # fmt: skip
NATIONAL = workbook(
    ["Question ID", "Question", "Answer ID", "Answer", "202621", "202620"],
    [[7, Q7, 1, "Yes", "24.6%", "23.8%"], [24, "During the next six months ...", 1, "Yes", "30.0%", "29.0%"]],
)  # fmt: skip


def test_census_reads_q7_yes_newest_column():
    got = census.parse(SIZE, NATIONAL)
    assert got["smpdt"] == "202621"
    assert got["ref_end"] == "2026-10-11"
    assert got["overall_pct"] == 24.6
    by = {c["code"]: c for c in got["by_class"]}
    assert [c["code"] for c in got["by_class"]] == list("ABCDEFG")
    assert by["A"] == {"code": "A", "label": "1–4", "pct": 24.3, "bucket": "small"}
    assert by["G"]["pct"] == 43.6 and by["G"]["bucket"] == "large" and by["G"]["label"] == "250+"
    assert by["E"]["bucket"] == "mid" and by["D"]["bucket"] == "small"
