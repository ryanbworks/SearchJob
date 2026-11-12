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


def collect(
    db: Database, settings: Settings, collectors: Sequence[Collector] | None = None
) -> dict[str, Any]:
    collectors = collectors if collectors is not None else build_collectors(settings)
    stats: dict[str, Any] = {"found": 0, "new": 0, "filtered": 0, "errors": []}
    for collector in collectors:
        for term in settings.search_terms:
            try:
                for job in collector.fetch(term):
                    stats["found"] += 1
                    if not passes_location(job, settings.preferred_states):
                        stats["filtered"] += 1
                        continue
                    if db.upsert_job(job):
                        stats["new"] += 1
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
    return stats
