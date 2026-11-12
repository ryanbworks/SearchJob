"""Configuração via variáveis de ambiente (prefixo ``SJ_``) ou arquivo ``.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SJ_", extra="ignore")

    # Armazenamento
    data_dir: Path = Path("data")

    # Segurança da API (vazio = sem autenticação; use apenas em testes)
    api_key: str = ""

    # Coleta
    search_terms: list[str] = [
        "suporte tecnico",
        "help desk",
        "service desk",
        "analista de suporte",
        "tecnico de informatica",
    ]
    # Filtro opcional por UF/estado (ex.: ["São Paulo", "SP"]). Vagas remotas sempre passam.
    preferred_states: list[str] = []
    # Vagas com estes termos no título são descartadas na coleta.
    exclude_title_terms: list[str] = [
        "senior", "sênior", "sr", "pleno", "coordenador", "coordenadora", "gerente",
        "especialista", "supervisor", "supervisora", "lider", "líder", "head",
    ]
    # Termos que descartam a vaga se aparecerem no título ou na descrição (ex.: "comissão").
    blocked_terms: list[str] = []
    # Acima disso a vaga é mantida, mas recebe um aviso e a IA considera isso na nota.
    max_experience_years: int = 2
    max_pages_per_term: int = 4
    request_delay_seconds: float = 1.0

    # IA local (qualquer servidor compatível com a API da OpenAI: Ollama, LM Studio, llama.cpp)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_api_key: str = "local"
    llm_timeout_seconds: float = 180.0
    analyze_batch_size: int = 30

    # Agendamento
    scheduler_enabled: bool = True
    timezone: str = "America/Sao_Paulo"
    collect_every_hours: int = 3
    report_hour: int = 18

    # Alertas de vaga por e-mail (LinkedIn, Indeed, InfoJobs, Catho…) e respostas das empresas.
    # Use uma conta só para isso. No Gmail: verificação em 2 etapas + "senha de app".
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    imap_folder: str = "INBOX"
    imap_days: int = 7

    # Notificação opcional
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def imap_enabled(self) -> bool:
        return bool(self.imap_host and self.imap_user and self.imap_password)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "searchjob.db"

    @property
    def profile_path(self) -> Path:
        return self.data_dir / "profile.md"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    def _profile_raw(self) -> str:
        for path in (self.profile_path, self.data_dir / "profile.example.md"):
            if path.exists():
                return path.read_text(encoding="utf-8")
        return ""

    def load_profile(self) -> str:
        """Perfil em texto usado pela IA (sem o bloco de contato)."""
        return split_front_matter(self._profile_raw())[1]

    def load_profile_contact(self) -> dict[str, str]:
        """Dados de contato do bloco ``---`` no topo do perfil (usados só no currículo)."""
        return split_front_matter(self._profile_raw())[0]


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Separa um bloco ``chave: valor`` entre linhas ``---`` no início do texto."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return {}, text
    data: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep and key.strip() and value.strip():
            data[key.strip().lower()] = value.strip()
    return data, "\n".join(lines[end + 1 :]).lstrip("\n")


@lru_cache
def get_settings() -> Settings:
    return Settings()
