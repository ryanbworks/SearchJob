"""Persistência em SQLite (arquivo único, ideal para um container pequeno no Proxmox)."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import JobPosting, JobStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source            TEXT NOT NULL,
    external_id       TEXT NOT NULL,
    title             TEXT NOT NULL,
    company           TEXT,
    description       TEXT NOT NULL DEFAULT '',
    url               TEXT NOT NULL,
    city              TEXT,
    state             TEXT,
    workplace_type    TEXT,
    published_at      TEXT,
    deadline          TEXT,
    skills            TEXT NOT NULL DEFAULT '[]',
    collected_at      TEXT NOT NULL,
    score             INTEGER,
    summary           TEXT,
    requirements      TEXT,
    missing           TEXT,
    analyzed_at       TEXT,
    status            TEXT NOT NULL DEFAULT 'new',
    status_updated_at TEXT,
    notes             TEXT,
    UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_collected ON jobs (collected_at);
"""

JSON_COLUMNS = ("skills", "requirements", "missing")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for col in JSON_COLUMNS:
        raw = data.get(col)
        data[col] = json.loads(raw) if raw else []
    return data


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn: sqlite3.Connection | None = None
        if str(path) == ":memory:":
            self._memory_conn = self._connect()
        self.init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        if self._memory_conn is not None:
            with self._memory_conn:
                yield self._memory_conn
            return
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init(self) -> None:
        with self.conn() as c:
            c.executescript(SCHEMA)

    # ------------------------------------------------------------------ escrita
    def upsert_job(self, job: JobPosting) -> bool:
        """Insere a vaga se for nova. Retorna ``True`` quando inseriu."""
        with self.conn() as c:
            exists = c.execute(
                "SELECT 1 FROM jobs WHERE source = ? AND external_id = ?",
                (job.source, job.external_id),
            ).fetchone()
            if exists:
                c.execute(
                    """UPDATE jobs SET title = ?, description = ?, deadline = ?, skills = ?
                       WHERE source = ? AND external_id = ?""",
                    (
                        job.title,
                        job.description,
                        job.deadline,
                        json.dumps(job.skills, ensure_ascii=False),
                        job.source,
                        job.external_id,
                    ),
                )
                return False
            c.execute(
                """
                INSERT INTO jobs (source, external_id, title, company, description, url, city,
                                  state, workplace_type, published_at, deadline, skills,
                                  collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.source,
                    job.external_id,
                    job.title,
                    job.company,
                    job.description,
                    job.url,
                    job.city,
                    job.state,
                    job.workplace_type,
                    job.published_at,
                    job.deadline,
                    json.dumps(job.skills, ensure_ascii=False),
                    _now(),
                ),
            )
            return True

    def save_analysis(
        self,
        job_id: int,
        *,
        score: int,
        summary: str,
        requirements: list[str],
        missing: list[str],
    ) -> None:
        with self.conn() as c:
            c.execute(
                """UPDATE jobs SET score = ?, summary = ?, requirements = ?, missing = ?,
                       analyzed_at = ? WHERE id = ?""",
                (
                    score,
                    summary,
                    json.dumps(requirements, ensure_ascii=False),
                    json.dumps(missing, ensure_ascii=False),
                    _now(),
                    job_id,
                ),
            )

    def update_job(
        self, job_id: int, *, status: JobStatus | None = None, notes: str | None = None
    ) -> dict[str, Any] | None:
        with self.conn() as c:
            if status is not None:
                c.execute(
                    "UPDATE jobs SET status = ?, status_updated_at = ? WHERE id = ?",
                    (status.value, _now(), job_id),
                )
            if notes is not None:
                c.execute("UPDATE jobs SET notes = ? WHERE id = ?", (notes, job_id))
        return self.get_job(job_id)

    # ------------------------------------------------------------------ leitura
    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def find_by_url(self, url: str) -> dict[str, Any] | None:
        base = url.split("?", 1)[0].rstrip("/")
        if not base:
            return None
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM jobs WHERE url = ? OR url LIKE ? ORDER BY id DESC LIMIT 1",
                (url, base + "%"),
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_jobs(
        self,
        *,
        status: JobStatus | None = None,
        min_score: int | None = None,
        query: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if min_score is not None:
            clauses.append("score >= ?")
            params.append(min_score)
        if query:
            clauses.append("(title LIKE ? OR company LIKE ? OR description LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like])
        if since is not None:
            clauses.append("collected_at >= ?")
            params.append(since.isoformat(timespec="seconds"))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM jobs {where} "
            "ORDER BY score IS NULL, score DESC, published_at DESC LIMIT ? OFFSET ?"
        )
        with self.conn() as c:
            rows = c.execute(sql, (*params, limit, offset)).fetchall()
        return [_row_to_dict(r) for r in rows]

    def pending_analysis(self, limit: int) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM jobs WHERE analyzed_at IS NULL AND status = 'new' "
                "ORDER BY published_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def insights(self, days: int = 30) -> dict[str, Any]:
        """Agrega o que o mercado está pedindo e o andamento das candidaturas."""
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.conn() as c:
            rows = c.execute(
                "SELECT skills, workplace_type FROM jobs WHERE collected_at >= ?", (since,)
            ).fetchall()
            status_rows = c.execute(
                "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
            ).fetchall()
        skills: Counter[str] = Counter()
        workplace: Counter[str] = Counter()
        for row in rows:
            skills.update(json.loads(row["skills"] or "[]"))
            workplace[row["workplace_type"] or "desconhecido"] += 1
        total = len(rows)
        return {
            "days": days,
            "total_jobs": total,
            "skills": [
                {"skill": name, "count": n, "percent": round(100 * n / total, 1) if total else 0}
                for name, n in skills.most_common()
            ],
            "workplace": dict(workplace),
            "status": {r["status"]: r["n"] for r in status_rows},
        }
