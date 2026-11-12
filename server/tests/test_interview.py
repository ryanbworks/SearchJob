from __future__ import annotations

import json

import pytest
from fakes import fake_llm, offline_llm
from fastapi.testclient import TestClient

from searchjob.api import create_app
from searchjob.config import Settings
from searchjob.interview import answer_feedback, generate_prep
from searchjob.llm import LLMError

KEY = {"X-API-Key": "k"}

PREP = json.dumps(
    {
        "questions": [
            {"question": "Como você resolve um usuário sem internet?", "why": "Diagnóstico",
             "tip": "Fale das camadas"},
            {"question": "", "why": "vazia, deve ser descartada"},
            "não é objeto",
        ],
        "scenarios": [{"situation": "Impressora não imprime", "steps": ["Ver fila", "Driver"]}],
        "pitch": "Sou estudante de TI...",
        "ask_them": ["Quais ferramentas o time usa?"],
    },
    ensure_ascii=False,
)


def test_generate_prep_cleans_output():
    llm, sent = fake_llm(PREP)
    prep = generate_prep(llm, "perfil", {"title": "Help Desk", "description": "GLPI"})
    assert len(prep["questions"]) == 1
    assert prep["scenarios"][0]["steps"] == ["Ver fila", "Driver"]
    assert prep["ask_them"] == ["Quais ferramentas o time usa?"]
    assert sent[0]["max_tokens"] >= 2000


def test_generate_prep_without_questions_fails():
    llm, _ = fake_llm('{"questions": []}')
    with pytest.raises(LLMError):
        generate_prep(llm, "perfil", {"title": "x"})


def test_feedback_clamps_score():
    llm, _ = fake_llm('{"score": 14, "strengths": ["Clara"], "improve": [], '
                      '"model_answer": "Eu verificaria..."}')
    fb = answer_feedback(llm, "perfil", "Pergunta?", "Minha resposta")
    assert fb["score"] == 10
    assert fb["strengths"] == ["Clara"]


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, api_key="k", scheduler_enabled=False)


def test_interview_endpoint_caches(settings, db, make_job):
    db.upsert_job(make_job("1"))
    llm, sent = fake_llm(PREP, PREP)
    with TestClient(create_app(settings, db=db, llm=llm)) as client:
        first = client.post("/api/jobs/1/interview", headers=KEY)
        assert first.status_code == 200
        assert first.json()["questions"][0]["question"].startswith("Como")
        assert "created_at" in first.json()

        client.post("/api/jobs/1/interview", headers=KEY)
        assert len(sent) == 1  # segunda chamada veio do cache

        client.post("/api/jobs/1/interview", params={"regenerate": "true"}, headers=KEY)
        assert len(sent) == 2

        assert client.post("/api/jobs/99/interview", headers=KEY).status_code == 404
        assert client.post("/api/jobs/1/interview").status_code == 401
        assert client.get("/entrevista").status_code == 200


def test_interview_endpoints_offline(settings, db, make_job):
    db.upsert_job(make_job("1"))
    with TestClient(create_app(settings, db=db, llm=offline_llm())) as client:
        assert client.post("/api/jobs/1/interview", headers=KEY).status_code == 503
        resp = client.post(
            "/api/interview/feedback",
            json={"question": "Por quê?", "answer": "Porque sim", "job_id": 1},
            headers=KEY,
        )
        assert resp.status_code == 503
