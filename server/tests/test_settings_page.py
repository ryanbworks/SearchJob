from __future__ import annotations

import json

import pytest
from fakes import fake_llm
from fastapi.testclient import TestClient

from searchjob.api import create_app
from searchjob.config import Settings
from searchjob.settings_view import mask_email

API_KEY = "chave-de-teste-bem-longa-123"
KEY = {"X-API-Key": API_KEY}
PROFILE = """---
nome: Maria Exemplo
email: maria@example.com
telefone: (11) 90000-0000
---
# Perfil
## Conhecimentos
- Windows 10/11 e redes (DNS, DHCP)
"""


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path,
        api_key=API_KEY,
        scheduler_enabled=False,
        imap_host="imap.gmail.com",
        imap_user="vagas.maria@gmail.com",
        imap_password="senha-do-imap",
        telegram_bot_token="token-telegram-secreto",
        telegram_chat_id="123",
    )


@pytest.fixture
def client(settings, db):
    llm, _ = fake_llm()
    with TestClient(create_app(settings, db=db, llm=llm)) as c:
        c.llm = llm
        yield c


def test_mask_email():
    assert mask_email("vagas.maria@gmail.com") == "va***@gmail.com"
    assert mask_email("") == ""


def test_config_never_exposes_secrets(client):
    resp = client.get("/api/config", headers=KEY)
    assert resp.status_code == 200
    for secret in (API_KEY, "senha-do-imap", "token-telegram-secreto", "vagas.maria@gmail.com"):
        assert secret not in resp.text
    data = resp.json()
    assert data["email"]["user"] == "va***@gmail.com"
    assert client.get("/api/config").status_code == 401


def test_checks_flag_example_profile(client):
    checks = {c["id"]: c for c in client.get("/api/config", headers=KEY).json()["checks"]}
    assert checks["api_key"]["level"] == "ok"
    assert checks["profile"]["level"] == "warn"  # ainda sem data/profile.md
    assert checks["llm"]["level"] == "ok"
    assert checks["imap"]["level"] == "ok"
    assert checks["collect"]["level"] == "warn"


def test_update_preferences_applies_and_persists(client, settings):
    body = {
        "search_terms": ["help desk", "suporte n1"],
        "blocked_terms": ["comissão"],
        "max_experience_years": 1,
        "llm_model": "llama3.1:8b",
        "llm_base_url": "http://192.168.0.10:1234/v1/",
        "collect_every_hours": 6,
    }
    resp = client.put("/api/preferences", json=body, headers=KEY)
    assert resp.status_code == 200
    data = resp.json()
    assert data["search"]["terms"] == ["help desk", "suporte n1"]
    assert data["filters"]["blocked_terms"] == ["comissão"]
    assert settings.max_experience_years == 1
    assert settings.collect_every_hours == 6
    assert client.llm.model == "llama3.1:8b"
    assert client.llm.base_url == "http://192.168.0.10:1234/v1"

    saved = json.loads((settings.data_dir / "preferences.json").read_text(encoding="utf-8"))
    assert saved["search_terms"] == ["help desk", "suporte n1"]

    # Mudança parcial mantém o restante
    client.put("/api/preferences", json={"report_hour": 20}, headers=KEY)
    saved = json.loads((settings.data_dir / "preferences.json").read_text(encoding="utf-8"))
    assert saved["report_hour"] == 20 and saved["max_experience_years"] == 1


@pytest.mark.parametrize(
    "body",
    [
        {"search_terms": []},
        {"api_key": "tentando-trocar"},  # segredos não são editáveis
        {"report_hour": 25},
        {"llm_base_url": "ftp://x"},
    ],
)
def test_update_preferences_validation(client, body):
    assert client.put("/api/preferences", json=body, headers=KEY).status_code == 422


def test_reset_preferences(client, settings):
    client.put("/api/preferences", json={"max_experience_years": 5}, headers=KEY)
    resp = client.delete("/api/preferences", headers=KEY)
    assert resp.status_code == 200
    assert not (settings.data_dir / "preferences.json").exists()
    assert settings.max_experience_years == Settings().max_experience_years


def test_preferences_loaded_on_startup(tmp_path, db):
    (tmp_path / "preferences.json").write_text(
        json.dumps({"search_terms": ["técnico de campo"], "report_hour": 9}), encoding="utf-8"
    )
    settings = Settings(data_dir=tmp_path, scheduler_enabled=False)
    llm, _ = fake_llm()
    create_app(settings, db=db, llm=llm)
    assert settings.search_terms == ["técnico de campo"]
    assert settings.report_hour == 9


def test_profile_read_and_write(client, settings):
    first = client.get("/api/profile", headers=KEY).json()
    assert first["using_example"] is True

    resp = client.put("/api/profile", json={"markdown": PROFILE}, headers=KEY)
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"]["using_example"] is False
    assert data["profile"]["contact_fields"]["telefone"] is True
    assert "Windows" in data["profile"]["skills"]
    assert "maria@example.com" not in data["profile"]["markdown"]  # contato fica fora da IA
    assert settings.profile_path.read_text(encoding="utf-8").startswith("---")
    assert client.get("/api/profile", headers=KEY).json()["using_example"] is False

    assert client.put("/api/profile", json={"markdown": "curto"}, headers=KEY).status_code == 422


def test_configuracoes_page_is_served(client):
    page = client.get("/configuracoes")
    assert page.status_code == 200
    assert "Configurações" in page.text
    assert client.get("/static/configuracoes.js").status_code == 200
