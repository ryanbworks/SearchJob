from __future__ import annotations

import pytest
from fakes import fake_llm, offline_llm
from fastapi.testclient import TestClient

from searchjob.api import create_app
from searchjob.config import Settings

KEY = {"X-API-Key": "segredo"}


@pytest.fixture
def settings(tmp_path) -> Settings:
    (tmp_path / "profile.md").write_text("Sei Windows e atendimento.", encoding="utf-8")
    return Settings(data_dir=tmp_path, api_key="segredo", scheduler_enabled=False)


@pytest.fixture
def client(settings, db, make_job):
    db.upsert_job(make_job("1", url="https://empresa.gupy.io/job/1?jobBoardSource=gupy_portal"))
    llm, _ = fake_llm("Tenho facilidade com atendimento ao usuário.")
    with TestClient(create_app(settings, db=db, llm=llm)) as c:
        yield c


def test_health_is_public(client):
    assert client.get("/health").json()["status"] == "ok"


def test_requires_api_key(client):
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs", headers={"X-API-Key": "errada"}).status_code == 401
    assert client.get("/api/jobs", headers=KEY).status_code == 200


def test_list_match_and_update(client):
    jobs = client.get("/api/jobs", headers=KEY).json()
    assert len(jobs) == 1
    job_id = jobs[0]["id"]

    match = client.get(
        "/api/jobs/match", params={"url": "https://empresa.gupy.io/job/1"}, headers=KEY
    )
    assert match.status_code == 200 and match.json()["id"] == job_id

    resp = client.patch(f"/api/jobs/{job_id}", json={"status": "applied"}, headers=KEY)
    assert resp.json()["status"] == "applied"
    assert client.patch("/api/jobs/999", json={"status": "applied"}, headers=KEY).status_code == 404
    invalid = client.patch(f"/api/jobs/{job_id}", json={"status": "xyz"}, headers=KEY)
    assert invalid.status_code == 422


def test_answer_uses_llm(client):
    resp = client.post("/api/answer", json={"question": "Por que você?", "job_id": 1}, headers=KEY)
    assert resp.status_code == 200
    assert "atendimento" in resp.json()["answer"]


def test_answer_returns_503_when_llm_offline(settings, db):
    with TestClient(create_app(settings, db=db, llm=offline_llm())) as c:
        resp = c.post("/api/answer", json={"question": "Fale de você"}, headers=KEY)
    assert resp.status_code == 503


def test_report_and_insights(client):
    html = client.get("/report", params={"key": "segredo"})
    assert html.status_code == 200
    assert "Relatório diário" in html.text
    assert "Analista de Suporte" in html.text
    assert client.get("/api/insights", headers=KEY).json()["total_jobs"] == 1
