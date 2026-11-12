"""Agendamento: coleta periódica e relatório no fim do dia."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from .config import Settings
from .db import Database
from .llm import LLMClient
from .notify import format_summary, send_telegram
from .pipeline import run_cycle
from .report import write_daily_report

log = logging.getLogger(__name__)


def daily_report(db: Database, settings: Settings) -> None:
    path, context = write_daily_report(db, settings)
    log.info("Relatório diário salvo em %s", path)
    send_telegram(settings, format_summary(context["jobs"]))


def start_scheduler(settings: Settings, db: Database, llm: LLMClient) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    scheduler.add_job(
        run_cycle,
        "interval",
        hours=settings.collect_every_hours,
        args=[db, settings, llm],
        id="collect",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(scheduler.timezone) + timedelta(seconds=30),
    )
    scheduler.add_job(
        daily_report,
        "cron",
        hour=settings.report_hour,
        args=[db, settings],
        id="daily_report",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info(
        "Agendador ativo: coleta a cada %sh, relatório às %sh",
        settings.collect_every_hours,
        settings.report_hour,
    )
    return scheduler
