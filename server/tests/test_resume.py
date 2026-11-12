from __future__ import annotations

import json

from fakes import fake_llm
from fastapi.testclient import TestClient

from searchjob.api import create_app
from searchjob.config import Settings, split_front_matter
from searchjob.resume import generate_resume, profile_section, skill_in_profile

PROFILE = """---
nome: Maria Exemplo
email: maria@example.com
cidade: Campinas/SP
---
# Perfil
## Formação
- Análise e Desenvolvimento de Sistemas (cursando, 1º semestre)
## Conhecimentos
- Windows 10/11, formatação e drivers
- Redes básicas: DNS e DHCP
- Python básico
## Idiomas
- Inglês intermediário (leitura)
"""

REPLY = json.dumps(
    {
        "headline": "Suporte Técnico | Help Desk N1",
        "summary": "Estudante de ADS com prática em Windows e redes.",
        "skills": ["Windows 10/11", "DNS e DHCP", "Active Directory", "Python", "Windows 10/11"],
        "highlights": [{"title": "Homelab", "description": "Configurei DNS."}, {"x": 1}],
        "keywords_used": ["Windows", "DNS"],
        "missing_keywords": ["Active Directory", "ITIL"],
    },
    ensure_ascii=False,
)


def test_split_front_matter():
    contact, body = split_front_matter(PROFILE)
    assert contact == {"nome": "Maria Exemplo", "email": "maria@example.com",
                       "cidade": "Campinas/SP"}
    assert body.startswith("# Perfil")
    assert "maria@example.com" not in body
    assert split_front_matter("sem bloco") == ({}, "sem bloco")


def test_profile_sections():
    _, body = split_front_matter(PROFILE)
    assert profile_section(body, "forma") == [
        "Análise e Desenvolvimento de Sistemas (cursando, 1º semestre)"
    ]
    assert profile_section(body, "idioma") == ["Inglês intermediário (leitura)"]


def test_skill_in_profile():
    _, body = split_front_matter(PROFILE)
    assert skill_in_profile("Python", body)
    assert skill_in_profile("DNS / DHCP", body)  # mesma categoria de requisito
    assert not skill_in_profile("Active Directory", body)


def test_generate_resume_removes_invented_skills():
    _, body = split_front_matter(PROFILE)
    llm, _ = fake_llm(REPLY)
    resume = generate_resume(llm, body, {"title": "Help Desk", "description": "AD e DNS"})
    assert resume["skills"] == ["Windows 10/11", "DNS e DHCP", "Python"]
    assert resume["removed_skills"] == ["Active Directory"]
    assert len(resume["highlights"]) == 1
    assert resume["missing_keywords"] == ["Active Directory", "ITIL"]


def test_resume_endpoint(tmp_path, db, make_job):
    (tmp_path / "profile.md").write_text(PROFILE, encoding="utf-8")
    settings = Settings(data_dir=tmp_path, api_key="k", scheduler_enabled=False)
    db.upsert_job(make_job("1"))
    llm, sent = fake_llm(REPLY)
    with TestClient(create_app(settings, db=db, llm=llm)) as client:
        data = client.post("/api/jobs/1/resume", headers={"X-API-Key": "k"}).json()
        assert data["contact"]["nome"] == "Maria Exemplo"
        assert data["education"][0].startswith("Análise")
        assert data["job"]["id"] == 1
        # O bloco de contato não vai para a IA
        assert "maria@example.com" not in sent[0]["messages"][1]["content"]

        client.post("/api/jobs/1/resume", headers={"X-API-Key": "k"})
        assert len(sent) == 1  # cache
        assert client.get("/curriculo").status_code == 200
