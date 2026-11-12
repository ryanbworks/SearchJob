from __future__ import annotations

import httpx

from searchjob.collectors.base import clean_text
from searchjob.collectors.gupy import GupyCollector, parse_job

SAMPLE = {
    "id": 12819464,
    "name": "ANALISTA DE SUPORTE TECNICO JR",
    "applicationDeadline": "2026-12-29T00:00:00.000Z",
    "description": "Atendimento a usuários<br>Conhecimento em <b>Windows</b> e Office",
    "careerPageName": "Empresa Exemplo",
    "type": "vacancy_type_effective",
    "publishedDate": "2026-11-12T18:27:36.977Z",
    "workplaceType": "on-site",
    "city": "São Paulo",
    "state": "São Paulo",
    "jobUrl": "https://exemplo.gupy.io/job/abc?jobBoardSource=gupy_portal",
}


def test_clean_text_strips_html():
    assert clean_text("a<br>b <b>c</b>&amp;d") == "a\nb c&d"


def test_parse_job_maps_fields():
    job = parse_job(SAMPLE)
    assert job.source == "gupy"
    assert job.external_id == "12819464"
    assert job.company == "Empresa Exemplo"
    assert job.workplace_type == "on-site"
    assert "Windows" in job.skills
    assert "<b>" not in job.description


def test_fetch_paginates_until_total():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        offset = int(params["offset"])
        items = [dict(SAMPLE, id=offset + i) for i in range(2)] if offset < 3 else []
        return httpx.Response(200, json={"data": items, "pagination": {"total": 3}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = GupyCollector(client, page_size=2, max_pages=5, delay_seconds=0)
    jobs = list(collector.fetch("suporte"))

    assert len(calls) == 2
    assert calls[0]["jobName"] == "suporte"
    assert [j.external_id for j in jobs] == ["0", "1", "2", "3"]
