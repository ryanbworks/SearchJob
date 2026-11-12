"""Relatório diário em HTML (servido em /report e salvo em data/reports)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, PackageLoader, select_autoescape

from .config import Settings
from .db import Database
from .models import JobStatus

_env = Environment(
    loader=PackageLoader("searchjob", "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

WORKPLACE_LABELS = {"remote": "Remoto", "hybrid": "Híbrido", "on-site": "Presencial"}


def _location(job: dict[str, Any]) -> str:
    kind = WORKPLACE_LABELS.get(job.get("workplace_type") or "", "")
    place = "/".join(p for p in (job.get("city"), job.get("state")) if p)
    return " · ".join(p for p in (kind, place) if p) or "Local não informado"


def build_context(
    db: Database, *, since_hours: int = 24, limit: int = 30, tz: str = "America/Sao_Paulo"
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    jobs = db.list_jobs(status=JobStatus.NEW, since=since, limit=limit)
    for job in jobs:
        job["location"] = _location(job)
    insights = db.insights(days=30)
    return {
        "generated_at": datetime.now(ZoneInfo(tz)).strftime("%d/%m/%Y %H:%M"),
        "since_hours": since_hours,
        "jobs": jobs,
        "analyzed": sum(1 for j in jobs if j.get("score") is not None),
        "insights": insights,
        "top_skills": insights["skills"][:12],
        "applied_total": insights["status"].get(JobStatus.APPLIED.value, 0),
    }


def render_report(context: dict[str, Any]) -> str:
    return _env.get_template("report.html").render(**context)


def write_daily_report(db: Database, settings: Settings) -> tuple[Path, dict[str, Any]]:
    context = build_context(db, tz=settings.timezone)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")
    path = settings.reports_dir / f"{stamp}.html"
    path.write_text(render_report(context), encoding="utf-8")
    return path, context
