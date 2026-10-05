"""SQLite store for the AI Adoption Index (stdlib sqlite3)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from castelino.adoption.index import Cell
from castelino.adoption.models import Claim, CompanyScore
from castelino.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS company_period(
  period TEXT, ticker TEXT, bucket TEXT, sector TEXT, market_cap REAL, accession TEXT,
  talk_raw REAL, hire_snapshot REAL, hire_raw REAL, spend_raw REAL,
  s_talk REAL, s_hire REAL, s_spend REAL, score REAL, pillars_used INTEGER,
  PRIMARY KEY(period, ticker));
CREATE TABLE IF NOT EXISTS filing_cache(
  ticker TEXT, accession TEXT, words INTEGER, talk_raw REAL, PRIMARY KEY(ticker, accession));
CREATE TABLE IF NOT EXISTS claims(ticker TEXT, accession TEXT, depth INTEGER, quote TEXT);
CREATE TABLE IF NOT EXISTS index_cell(
  period TEXT, sector TEXT, bucket TEXT, n INTEGER, ew REAL, cw REAL, thin INTEGER,
  PRIMARY KEY(period, sector, bucket));
"""

_COMPANY_COLS = (
    "ticker,bucket,sector,market_cap,accession,talk_raw,hire_snapshot,hire_raw,spend_raw,"
    "s_talk,s_hire,s_spend,score,pillars_used"
)


class AdoptionStore:
    def __init__(self, path: Path | None = None):
        if path is None:
            cfg = get_settings()
            path = cfg.root / cfg.adoption.data_dir / "adoption.db"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── filing cache (Talk carries forward until a new filing) ──────────
    def get_filing(self, ticker: str, accession: str) -> dict | None:
        with self._conn() as c:
            r = c.execute(
                "SELECT words, talk_raw FROM filing_cache WHERE ticker=? AND accession=?",
                (ticker, accession),
            ).fetchone()
        return dict(r) if r else None

    def put_filing(
        self, ticker: str, accession: str, words: int, talk_raw: float | None, claims: list[Claim]
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO filing_cache VALUES(?,?,?,?)",
                (ticker, accession, words, talk_raw),
            )
            c.execute("DELETE FROM claims WHERE ticker=? AND accession=?", (ticker, accession))
            c.executemany(
                "INSERT INTO claims VALUES(?,?,?,?)",
                [(ticker, accession, cl.depth, cl.quote) for cl in claims],
            )

    def claims_for(self, ticker: str, accession: str | None, limit: int = 5) -> list[dict]:
        if accession is None:
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT depth, quote FROM claims WHERE ticker=? AND accession=? "
                "ORDER BY depth DESC, rowid LIMIT ?",
                (ticker, accession, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def hire_history(self, ticker: str, before_period: str, n: int) -> list[float]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT hire_snapshot FROM company_period WHERE ticker=? AND period<? "
                "AND hire_snapshot IS NOT NULL ORDER BY period DESC LIMIT ?",
                (ticker, before_period, n),
            ).fetchall()
        return [r[0] for r in rows]

    # ── periods ─────────────────────────────────────────────────────────
    def save_period(self, period: str, scores: list[CompanyScore], cells: list[Cell]) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM company_period WHERE period=?", (period,))
            c.execute("DELETE FROM index_cell WHERE period=?", (period,))
            c.executemany(
                "INSERT INTO company_period VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        period,
                        s.company.ticker,
                        s.company.bucket,
                        s.company.sector,
                        s.company.market_cap,
                        s.accession,
                        s.raw.get("talk"),
                        s.hire_snapshot,
                        s.raw.get("hire"),
                        s.raw.get("spend"),
                        s.s.get("talk"),
                        s.s.get("hire"),
                        s.s.get("spend"),
                        s.score,
                        s.pillars_used,
                    )
                    for s in scores
                ],
            )
            c.executemany(
                "INSERT INTO index_cell VALUES(?,?,?,?,?,?,?)",
                [
                    (
                        period,
                        cell.sector or "",
                        cell.bucket,
                        cell.n,
                        cell.ew,
                        cell.cw,
                        int(cell.thin),
                    )
                    for cell in cells
                ],
            )

    def periods(self) -> list[str]:
        with self._conn() as c:
            rows = c.execute("SELECT DISTINCT period FROM index_cell ORDER BY period").fetchall()
        return [r[0] for r in rows]

    def cells(self, period: str) -> list[Cell]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT sector,bucket,n,ew,cw,thin FROM index_cell WHERE period=? ORDER BY bucket, sector",
                (period,),
            ).fetchall()
        return [
            Cell(r["sector"] or None, r["bucket"], r["n"], r["ew"], r["cw"], bool(r["thin"]))
            for r in rows
        ]

    def companies(
        self, period: str, sector: str | None = None, bucket: str | None = None
    ) -> list[dict]:
        sql = f"SELECT {_COMPANY_COLS} FROM company_period WHERE period=?"
        args: list = [period]
        if sector is not None:
            sql += " AND sector=?"
            args.append(sector)
        if bucket is not None:
            sql += " AND bucket=?"
            args.append(bucket)
        sql += " ORDER BY score IS NULL, score DESC, ticker"
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def series(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT period, bucket, ew FROM index_cell WHERE sector='' ORDER BY period"
            ).fetchall()
        by: dict[str, dict] = {}
        for r in rows:
            by.setdefault(r["period"], {"period": r["period"], "large_ew": None, "small_ew": None})
            by[r["period"]][f"{r['bucket']}_ew"] = r["ew"]
        return list(by.values())
