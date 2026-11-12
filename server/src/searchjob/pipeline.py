"""Ciclo principal: coletar → filtrar → salvar → analisar com IA."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import httpx

from .analyzer import analyze_pending
from .collectors import Collector, GupyCollector
from .config import Settings
from .db import Database
from .filters import enrich, exclusion_reason
from .llm import LLMClient
from .models import JobPosting
from .skills import normalize

log = logging.getLogger(__name__)


def build_collectors(settings: Settings) -> list[Collector]:
    return [
        GupyCollector(
            max_pages=settings.max_pages_per_term,
            delay_seconds=settings.request_delay_seconds,
        )
    ]


def build_llm(settings: Settings) -> LLMClient:
    return LLMClient(
        settings.llm_base_url,
        settings.llm_model,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
    )


def passes_location(job: JobPosting, preferred_states: Sequence[str]) -> bool:
    """Sem filtro, vaga remota ou sem estado informado: passa."""
    if not preferred_states or job.is_remote or not job.state:
        return True
    wanted = {normalize(s) for s in preferred_states}
    return normalize(job.state) in wanted


def new_stats() -> dict[str, Any]:
    return {"found": 0, "new": 0, "filtered": 0, "excluded": 0, "excluded_reasons": {},
            "errors": []}


def store_job(db: Database, settings: Settings, job: JobPosting, stats: dict[str, Any]) -> None:
    """Aplica localização, exclusões e enriquecimento e salva. Usado por todas as fontes."""
    stats["found"] += 1
    if not passes_location(job, settings.preferred_states):
        stats["filtered"] += 1
        return
    reason = exclusion_reason(job, settings.exclude_title_terms, settings.blocked_terms)
    if reason:
        stats["excluded"] += 1
        reasons = stats["excluded_reasons"]
        reasons[reason] = reasons.get(reason, 0) + 1
        return
    enrich(job, settings.max_experience_years)
    if db.upsert_job(job):
        stats["new"] += 1


def collect(
    db: Database,
    settings: Settings,
    collectors: Sequence[Collector] | None = None,
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    collectors = collectors if collectors is not None else build_collectors(settings)
    stats = stats if stats is not None else new_stats()
    for collector in collectors:
        for term in settings.search_terms:
            try:
                for job in collector.fetch(term):
                    store_job(db, settings, job, stats)
            except httpx.HTTPError as exc:
                msg = f"{collector.source} / '{term}': {exc}"
                log.warning("Falha na coleta: %s", msg)
                stats["errors"].append(msg)
    log.info("Coleta concluída: %s", stats)
    return stats


def run_cycle(db: Database, settings: Settings, llm: LLMClient) -> dict[str, Any]:
    stats = collect(db, settings)
    stats["analyzed"] = analyze_pending(
        db, llm, settings.load_profile(), limit=settings.analyze_batch_size
    )
    db.save_run(stats)
    return stats
