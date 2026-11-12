"""Resumo da configuração atual para a aba Configurações (somente leitura, sem segredos)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import __version__
from .config import Settings
from .db import Database
from .llm import LLMClient
from .skills import extract_skills

CONTACT_FIELDS = ["nome", "email", "telefone", "cidade", "linkedin", "github"]


def mask_email(value: str) -> str:
    user, _, domain = value.partition("@")
    if not domain:
        return "***" if value else ""
    return f"{user[:2]}***@{domain}"


def _check(check_id: str, label: str, level: str, detail: str, fix: str = "") -> dict[str, str]:
    """level: ok | warn | off (opcional e desligado)."""
    return {"id": check_id, "label": label, "level": level, "detail": detail, "fix": fix}


def build_config_view(settings: Settings, db: Database, llm: LLMClient) -> dict[str, Any]:
    profile = settings.load_profile()
    contact = settings.load_profile_contact()
    using_example = not settings.profile_path.exists()
    llm_online = llm.is_available()
    runs = db.runs_since(7)
    last_run = runs[0] if runs else None

    checks = [
        _check(
            "api_key", "Chave de acesso",
            "ok" if len(settings.api_key) >= 16 else "warn",
            "Configurada." if len(settings.api_key) >= 16
            else "Vazia ou curta: qualquer um na rede poderia acessar.",
            "Defina SJ_API_KEY no .env com 16+ caracteres aleatórios.",
        ),
        _check(
            "profile", "Perfil (profile.md)",
            "warn" if using_example else "ok",
            "Usando o perfil de EXEMPLO: as notas da IA não refletem você."
            if using_example else f"{len(profile)} caracteres lidos.",
            "Copie data/profile.example.md para data/profile.md e escreva o seu.",
        ),
    ]
    missing_contact = [f for f in CONTACT_FIELDS[:3] if not contact.get(f)]
    checks.append(_check(
        "contact", "Contato do currículo",
        "warn" if missing_contact else "ok",
        f"Faltando: {', '.join(missing_contact)}." if missing_contact
        else "Nome, e-mail e telefone preenchidos.",
        "Preencha o bloco entre --- no topo do profile.md.",
    ))
    checks.append(_check(
        "llm", "IA local",
        "ok" if llm_online else "warn",
        f"Online ({settings.llm_model})." if llm_online
        else "Offline: notas, entrevista e currículo ficam pendentes.",
        "Ligue o Ollama ou o LM Studio e confira SJ_LLM_BASE_URL.",
    ))
    checks.append(_check(
        "imap", "Alertas por e-mail",
        "ok" if settings.imap_enabled else "off",
        f"Lendo {mask_email(settings.imap_user)} em {settings.imap_host}."
        if settings.imap_enabled else "Opcional, não configurado.",
        "Veja docs/alertas-email.md.",
    ))
    checks.append(_check(
        "telegram", "Aviso no Telegram",
        "ok" if settings.telegram_bot_token and settings.telegram_chat_id else "off",
        "Configurado." if settings.telegram_bot_token else "Opcional, não configurado.",
        "Defina SJ_TELEGRAM_BOT_TOKEN e SJ_TELEGRAM_CHAT_ID.",
    ))
    recent = last_run and datetime.fromisoformat(last_run["ran_at"]) >= datetime.now(UTC) - (
        timedelta(hours=settings.collect_every_hours * 2 + 1)
    )
    checks.append(_check(
        "collect", "Coleta automática",
        "ok" if recent else "warn",
        f"Última coleta em {last_run['ran_at']}." if last_run else "Nenhuma coleta registrada.",
        "Use 'Coletar agora' no painel ou confira os logs do container.",
    ))

    return {
        "version": __version__,
        "checks": checks,
        "summary": {
            "ok": sum(c["level"] == "ok" for c in checks),
            "warn": sum(c["level"] == "warn" for c in checks),
            "off": sum(c["level"] == "off" for c in checks),
        },
        "search": {
            "terms": settings.search_terms,
            "preferred_states": settings.preferred_states,
            "max_pages_per_term": settings.max_pages_per_term,
        },
        "filters": {
            "exclude_title_terms": settings.exclude_title_terms,
            "blocked_terms": settings.blocked_terms,
            "max_experience_years": settings.max_experience_years,
        },
        "llm": {
            "base_url": settings.llm_base_url,
            "model": settings.llm_model,
            "online": llm_online,
            "batch_size": settings.analyze_batch_size,
        },
        "schedule": {
            "enabled": settings.scheduler_enabled,
            "collect_every_hours": settings.collect_every_hours,
            "report_hour": settings.report_hour,
            "timezone": settings.timezone,
        },
        "email": {
            "enabled": settings.imap_enabled,
            "host": settings.imap_host,
            "user": mask_email(settings.imap_user),
            "folder": settings.imap_folder,
            "days": settings.imap_days,
        },
        "profile": {
            "using_example": using_example,
            "contact_fields": {f: bool(contact.get(f)) for f in CONTACT_FIELDS},
            "skills": extract_skills(profile),
            "markdown": profile,
        },
        "runs": [
            {
                "ran_at": r["ran_at"],
                "found": r.get("found", 0),
                "new": r.get("new", 0),
                "excluded": r.get("excluded", 0),
                "analyzed": r.get("analyzed"),
                "errors": len(r.get("errors") or []),
            }
            for r in runs[:8]
        ],
    }
