"""Notificação opcional do resumo diário via bot do Telegram."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger(__name__)


def format_summary(jobs: list[dict[str, Any]], report_url: str | None = None) -> str:
    if not jobs:
        return "SearchJob: nenhuma vaga nova hoje."
    lines = [f"SearchJob: {len(jobs)} vaga(s) nova(s) hoje. Melhores:"]
    for job in jobs[:5]:
        score = job.get("score")
        nota = f"[{score}/10] " if score is not None else ""
        lines.append(f"• {nota}{job['title']} — {job.get('company') or '?'}\n  {job['url']}")
    if report_url:
        lines.append(f"\nRelatório completo: {report_url}")
    return "\n".join(lines)


def send_telegram(settings: Settings, text: str, client: httpx.Client | None = None) -> bool:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return False
    client = client or httpx.Client(timeout=15)
    try:
        resp = client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Falha ao enviar Telegram: %s", exc)
        return False
    return True
