from __future__ import annotations

import pytest

from searchjob.db import Database
from searchjob.models import JobPosting


@pytest.fixture
def db() -> Database:
    return Database(":memory:")


@pytest.fixture
def make_job():
    def _make(external_id: str = "1", **overrides) -> JobPosting:
        data = {
            "source": "gupy",
            "external_id": external_id,
            "title": "Analista de Suporte Técnico Jr",
            "url": f"https://empresa.gupy.io/job/{external_id}",
            "company": "Empresa X",
            "description": "Atendimento N1, Windows, Active Directory e GLPI.",
            "city": "São Paulo",
            "state": "São Paulo",
            "workplace_type": "on-site",
            "published_at": "2026-11-12T10:00:00Z",
            "skills": ["Windows", "Active Directory"],
        }
        data.update(overrides)
        return JobPosting(**data)

    return _make
