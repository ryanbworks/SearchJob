"""Preferências editáveis pelo painel, salvas em ``data/preferences.json``.

Elas sobrepõem os valores do ``.env`` e passam a valer na hora. Segredos (chave da API,
senha do e-mail, token do Telegram) ficam de fora de propósito: só no ``.env``.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .config import Settings

Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]

MAX_PROFILE_CHARS = 50_000


class Preferences(BaseModel):
    """Campos que podem ser alterados pelo painel. Todos opcionais (só o que mudou)."""

    model_config = ConfigDict(extra="forbid")

    search_terms: list[Term] | None = Field(default=None, min_length=1, max_length=30)
    preferred_states: list[Term] | None = Field(default=None, max_length=27)
    exclude_title_terms: list[Term] | None = Field(default=None, max_length=50)
    blocked_terms: list[Term] | None = Field(default=None, max_length=50)
    max_experience_years: int | None = Field(default=None, ge=0, le=20)
    max_pages_per_term: int | None = Field(default=None, ge=1, le=20)
    llm_base_url: str | None = Field(default=None, pattern=r"^https?://\S+$", max_length=300)
    llm_model: str | None = Field(default=None, min_length=1, max_length=120)
    collect_every_hours: int | None = Field(default=None, ge=1, le=24)
    report_hour: int | None = Field(default=None, ge=0, le=23)


EDITABLE = tuple(Preferences.model_fields)


def _path(settings: Settings) -> Path:
    return settings.data_dir / "preferences.json"


def load_preferences(settings: Settings) -> dict[str, Any]:
    path = _path(settings)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Preferences.model_validate(raw).model_dump(exclude_none=True)
    except (ValueError, OSError):
        return {}  # arquivo corrompido ou inválido: mantém os valores do .env


def apply_preferences(settings: Settings, prefs: dict[str, Any]) -> None:
    for key, value in prefs.items():
        if key in EDITABLE:
            setattr(settings, key, value)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save_preferences(settings: Settings, changes: Preferences) -> dict[str, Any]:
    """Mescla as mudanças, grava o arquivo e aplica nas configurações em uso."""
    current = load_preferences(settings)
    current.update(changes.model_dump(exclude_none=True))
    _atomic_write(_path(settings), json.dumps(current, ensure_ascii=False, indent=2))
    apply_preferences(settings, current)
    return current


def reset_preferences(settings: Settings) -> None:
    """Apaga as preferências do painel e volta aos valores do .env (ou padrão)."""
    _path(settings).unlink(missing_ok=True)
    base = Settings()
    apply_preferences(settings, {key: getattr(base, key) for key in EDITABLE})


def read_profile_raw(settings: Settings) -> str:
    for path in (settings.profile_path, settings.data_dir / "profile.example.md"):
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


def write_profile(settings: Settings, markdown: str) -> None:
    if len(markdown) > MAX_PROFILE_CHARS:
        raise ValueError(f"Perfil muito grande (máximo {MAX_PROFILE_CHARS} caracteres)")
    text = markdown.replace("\r\n", "\n").rstrip() + "\n"
    _atomic_write(settings.profile_path, text)
