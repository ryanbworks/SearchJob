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

CREATE TABLE IF NOT EXISTS ai_documents (
    job_id     INTEGER NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (job_id, kind)
);

CREATE TABLE IF NOT EXISTS collect_runs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at   TEXT NOT NULL,
    stats    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_emails (
    message_id   TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL,
    outcome      TEXT
);
"""

# Colunas adicionadas depois da primeira versão. Aplicadas em bancos novos e antigos.
MIGRATIONS: dict[str, str] = {
    "salary_min": "REAL",
    "salary_max": "REAL",
    "min_experience": "INTEGER",
    "flags": "TEXT NOT NULL DEFAULT '[]'",
}

JSON_COLUMNS = ("skills", "requirements", "missing", "flags")


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
            existing = {row["name"] for row in c.execute("PRAGMA table_info(jobs)")}
            for column, ddl in MIGRATIONS.items():
                if column not in existing:
                    c.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}")

    # ------------------------------------------------------------------ escrita
    def upsert_job(self, job: JobPosting) -> bool:
        """Insere a vaga se for nova. Retorna ``True`` quando inseriu."""
        with self.conn() as c:
            exists = c.execute(
                "SELECT 1 FROM jobs WHERE source = ? AND external_id = ?",
                (job.source, job.external_id),
            ).fetchone()
            extracted = (
                job.salary_min,
                job.salary_max,
                job.min_experience,
                json.dumps(job.flags, ensure_ascii=False),
            )
            if exists:
                c.execute(
                    """UPDATE jobs SET title = ?, description = ?, deadline = ?, skills = ?,
                              salary_min = ?, salary_max = ?, min_experience = ?, flags = ?
                       WHERE source = ? AND external_id = ?""",
                    (
                        job.title,
                        job.description,
                        job.deadline,
                        json.dumps(job.skills, ensure_ascii=False),
                        *extracted,
                        job.source,
                        job.external_id,
                    ),
                )
                return False
            c.execute(
                """
                INSERT INTO jobs (source, external_id, title, company, description, url, city,
                                  state, workplace_type, published_at, deadline, skills,
                                  collected_at, salary_min, salary_max, min_experience, flags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    *extracted,
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

    def jobs_since(self, days: int) -> list[dict[str, Any]]:
        """Vagas coletadas nos últimos ``days`` dias (sem a descrição, para ser leve)."""
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.conn() as c:
            rows = c.execute(
                """SELECT id, source, title, company, url, city, state, workplace_type,
                          published_at, collected_at, skills, score, summary, requirements,
                          missing, status, status_updated_at, salary_min, salary_max,
                          min_experience, flags
                   FROM jobs WHERE collected_at >= ? ORDER BY collected_at DESC""",
                (since,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def jobs_with_status(self, *statuses: JobStatus) -> list[dict[str, Any]]:
        marks = ", ".join("?" for _ in statuses)
        with self.conn() as c:
            rows = c.execute(
                f"SELECT * FROM jobs WHERE status IN ({marks}) ORDER BY status_updated_at DESC",
                [s.value for s in statuses],
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # ------------------------------------------------------------ documentos da IA
    def get_document(self, job_id: int, kind: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT content, created_at FROM ai_documents WHERE job_id = ? AND kind = ?",
                (job_id, kind),
            ).fetchone()
        if not row:
            return None
        return {**json.loads(row["content"]), "created_at": row["created_at"]}

    def save_document(self, job_id: int, kind: str, content: dict[str, Any]) -> dict[str, Any]:
        created = _now()
        with self.conn() as c:
            c.execute(
                """INSERT INTO ai_documents (job_id, kind, content, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (job_id, kind) DO UPDATE SET
                       content = excluded.content, created_at = excluded.created_at""",
                (job_id, kind, json.dumps(content, ensure_ascii=False), created),
            )
        return {**content, "created_at": created}

    # ------------------------------------------------------------ histórico de coletas
    def save_run(self, stats: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO collect_runs (ran_at, stats) VALUES (?, ?)",
                (_now(), json.dumps(stats, ensure_ascii=False, default=str)),
            )

    def runs_since(self, days: int) -> list[dict[str, Any]]:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.conn() as c:
            rows = c.execute(
                "SELECT ran_at, stats FROM collect_runs WHERE ran_at >= ? ORDER BY ran_at DESC",
                (since,),
            ).fetchall()
        return [{"ran_at": r["ran_at"], **json.loads(r["stats"])} for r in rows]

    # ------------------------------------------------------------ e-mails processados
    def email_processed(self, message_id: str) -> bool:
        with self.conn() as c:
            row = c.execute(
                "SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,)
            ).fetchone()
        return row is not None

    def mark_email_processed(self, message_id: str, outcome: str) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO processed_emails (message_id, processed_at, outcome) "
                "VALUES (?, ?, ?)",
                (message_id, _now(), outcome),
            )

    def status_counts(self) -> dict[str, int]:
        with self.conn() as c:
            rows = c.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

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
