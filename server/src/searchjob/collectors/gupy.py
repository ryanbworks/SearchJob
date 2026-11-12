"""Coletor do portal público de vagas da Gupy (portal.gupy.io).

Usa o mesmo endpoint JSON que o próprio portal consome no navegador, com poucas
requisições e intervalo entre páginas, para não sobrecarregar o serviço.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

import httpx

from ..models import JobPosting
from ..skills import extract_skills
from .base import USER_AGENT, clean_text

log = logging.getLogger(__name__)

API_URL = "https://portal.gupy.io/api/job-search/jobs"


def parse_job(item: dict[str, Any]) -> JobPosting:
    description = clean_text(item.get("description"))
    title = (item.get("name") or "").strip()
    return JobPosting(
        source="gupy",
        external_id=str(item["id"]),
        title=title,
        url=item.get("jobUrl") or "",
        company=item.get("careerPageName"),
        description=description,
        city=item.get("city") or None,
        state=item.get("state") or None,
        workplace_type=item.get("workplaceType") or None,
        published_at=item.get("publishedDate"),
        deadline=item.get("applicationDeadline"),
        skills=extract_skills(f"{title}\n{description}"),
    )


class GupyCollector:
    source = "gupy"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        page_size: int = 50,
        max_pages: int = 4,
        delay_seconds: float = 1.0,
    ):
        self.client = client or httpx.Client(
            timeout=30, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        self.page_size = page_size
        self.max_pages = max_pages
        self.delay_seconds = delay_seconds

    def fetch(self, term: str) -> Iterator[JobPosting]:
        offset = 0
        for page in range(self.max_pages):
            if page and self.delay_seconds:
                time.sleep(self.delay_seconds)
            resp = self.client.get(
                API_URL, params={"jobName": term, "limit": self.page_size, "offset": offset}
            )
            resp.raise_for_status()
            payload = resp.json()
            items = payload.get("data") or []
            for item in items:
                try:
                    job = parse_job(item)
                except (KeyError, TypeError) as exc:
                    log.warning("Vaga da Gupy ignorada (formato inesperado): %s", exc)
                    continue
                if job.url:
                    yield job
            total = (payload.get("pagination") or {}).get("total", 0)
            offset += self.page_size
            if not items or offset >= total:
                break
