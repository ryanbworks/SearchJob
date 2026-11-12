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

    # Notificação opcional
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def database_path(self) -> Path:
        return self.data_dir / "searchjob.db"

    @property
    def profile_path(self) -> Path:
        return self.data_dir / "profile.md"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    def load_profile(self) -> str:
        """Lê o perfil/currículo em texto usado pela IA para avaliar as vagas."""
        if self.profile_path.exists():
            return self.profile_path.read_text(encoding="utf-8")
        example = self.data_dir / "profile.example.md"
        if example.exists():
            return example.read_text(encoding="utf-8")
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
