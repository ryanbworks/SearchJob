"""Agregações do painel: lacunas do perfil, repetições, funil e tendências."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .db import Database
from .models import JobStatus
from .skills import SKILL_TIPS, extract_skills, normalize

FUNNEL_ORDER = [
    JobStatus.NEW,
    JobStatus.APPLIED,
    JobStatus.INTERVIEW,
    JobStatus.OFFER,
    JobStatus.REJECTED,
    JobStatus.IGNORED,
]
STATUS_LABELS = {
    "new": "Novas",
    "applied": "Candidatado",
    "interview": "Entrevista",
    "offer": "Proposta",
    "rejected": "Recusado",
    "ignored": "Ignorada",
}
WORKPLACE_LABELS = {"remote": "Remoto", "hybrid": "Híbrido", "on-site": "Presencial"}

# Palavras que não mudam a vaga em si (nível, siglas de contrato…)
_TITLE_NOISE = re.compile(
    r"\b(jr|junior|pleno|senior|sr|i{1,3}|n[123]|estagio|estagiario|vaga|pcd|clt|pj|"
    r"temporario|remoto|hibrido|presencial)\b"
)


def _pct(part: int, total: int) -> float:
    return round(100 * part / total, 1) if total else 0.0


def title_key(title: str) -> str:
    """Normaliza o título para achar vagas iguais escritas de jeitos diferentes."""
    text = re.sub(r"[^a-z0-9 ]+", " ", normalize(title))
    text = _TITLE_NOISE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _day(job: dict[str, Any]) -> str:
    return (job.get("published_at") or job.get("collected_at") or "")[:10]


def _top(counter: Counter[str], n: int, total: int) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count, "percent": _pct(count, total)}
        for label, count in counter.most_common(n)
    ]


def _skills_section(jobs: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    total = len(jobs)
    have = set(extract_skills(profile))
    counts = Counter(skill for job in jobs for skill in job["skills"])
    skills = [
        {
            "skill": skill,
            "count": count,
            "percent": _pct(count, total),
            "have": skill in have,
            "tip": SKILL_TIPS.get(skill, ""),
        }
        for skill, count in counts.most_common()
    ]
    asked = sum(s["count"] for s in skills)
    covered = sum(s["count"] for s in skills if s["have"])
    gaps = [s for s in skills if not s["have"]]
    strengths = [s for s in skills if s["have"]]
    return {
        "skills": skills,
        "coverage": _pct(covered, asked),
        "gaps": gaps,
        "strengths": strengths,
        "recommendations": gaps[:6],
        "resume_keywords": [s["skill"] for s in strengths[:12]],
        "profile_skills": sorted(have),
    }


def _ai_missing(jobs: list[dict[str, Any]], analyzed: int) -> list[dict[str, Any]]:
    """O que a IA mais apontou como faltando, juntando grafias diferentes."""
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for job in jobs:
        seen: set[str] = set()  # conta cada item no máximo uma vez por vaga
        for raw in job["missing"]:
            text = raw.strip(" .;")
            key = normalize(text)
            if not key or key in seen:
                continue
            seen.add(key)
            counts[key] += 1
            display.setdefault(key, text)
    return [
        {"label": display[k], "count": n, "percent": _pct(n, analyzed)}
        for k, n in counts.most_common(12)
    ]


def _repetition(jobs: list[dict[str, Any]], total: int) -> dict[str, Any]:
    companies: Counter[str] = Counter()
    titles: Counter[str] = Counter()
    title_display: dict[str, Counter[str]] = defaultdict(Counter)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for job in jobs:
        company = (job.get("company") or "").strip()
        key = title_key(job["title"])
        if company:
            companies[company] += 1
        if key:
            titles[key] += 1
            title_display[key][job["title"].strip()] += 1
        groups[(normalize(company), key)].append(job)

    reposts = []
    for group in groups.values():
        if len(group) < 2:
            continue
        days = sorted(_day(j) for j in group if _day(j))
        reposts.append(
            {
                "title": group[0]["title"],
                "company": group[0].get("company") or "Empresa não informada",
                "count": len(group),
                "first_seen": days[0] if days else None,
                "last_seen": days[-1] if days else None,
                "job_ids": [j["id"] for j in group],
            }
        )
    reposts.sort(key=lambda r: (-r["count"], r["title"]))

    top_titles = [
        {
            "label": title_display[key].most_common(1)[0][0],
            "count": count,
            "percent": _pct(count, total),
        }
        for key, count in titles.most_common(10)
    ]
    return {
        "companies": _top(companies, 10, total),
        "titles": top_titles,
        "reposts": reposts[:15],
        "repost_jobs": sum(r["count"] for r in reposts),
    }


def _timeline(jobs: list[dict[str, Any]], days: int, today: date) -> list[dict[str, Any]]:
    counts = Counter(_day(j) for j in jobs)
    start = today - timedelta(days=days - 1)
    result = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        result.append({"date": day, "count": counts.get(day, 0)})
    return result


def build_dashboard(
    db: Database, profile: str, *, days: int = 30, today: date | None = None
) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    jobs = db.jobs_since(days)
    total = len(jobs)
    analyzed = [j for j in jobs if j["score"] is not None]
    scores = [j["score"] for j in analyzed]

    status_counts = db.status_counts()
    funnel = [
        {
            "status": s.value,
            "label": STATUS_LABELS[s.value],
            "count": status_counts.get(s.value, 0),
        }
        for s in FUNNEL_ORDER
    ]
    sent = sum(status_counts.get(s, 0) for s in ("applied", "interview", "offer", "rejected"))
    answered = sum(status_counts.get(s, 0) for s in ("interview", "offer"))

    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat(timespec="seconds")
    new_today = sum(1 for j in jobs if (j.get("collected_at") or "") >= cutoff)
    workplace = Counter(
        WORKPLACE_LABELS.get(j.get("workplace_type") or "", "Não informado") for j in jobs
    )
    states = Counter(j["state"] for j in jobs if j.get("state"))

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "days": days,
        "kpis": {
            "total_jobs": total,
            "new_last_24h": new_today,
            "analyzed": len(analyzed),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "good_matches": sum(1 for s in scores if s >= 7),
            "applications": sent,
            "response_rate": _pct(answered, sent),
        },
        **_skills_section(jobs, profile),
        "ai_missing": _ai_missing(analyzed, len(analyzed)),
        **_repetition(jobs, total),
        "timeline": _timeline(jobs, days, today),
        "score_histogram": [{"score": s, "count": scores.count(s)} for s in range(11)],
        "workplace": _top(workplace, 5, total),
        "states": _top(states, 8, total),
        "funnel": funnel,
    }
