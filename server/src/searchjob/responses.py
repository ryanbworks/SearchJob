"""Reconhece respostas das empresas (entrevista ou recusa) e atualiza a candidatura."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .db import Database
from .models import JobStatus
from .skills import normalize

_REJECTED = re.compile(
    r"infelizmente|nao (seguiremos|vamos seguir|foi selecionad|avancaremos|avancou)|"
    r"outros? candidat|optamos por|perfil mais aderente|processo (foi )?encerrad|"
    r"vaga (foi )?(encerrada|cancelada|preenchida)|nao daremos continuidade"
)
_INTERVIEW = re.compile(
    r"entrevista|agendar|agendamento|proxima (etapa|fase)|bate-?papo|teste tecnico|"
    r"dinamica|convite para|gostariamos de conversar|avancou para"
)
_COMPANY_NOISE = re.compile(r"\b(ltda|s\.?a|sa|eireli|me|grupo|holding|brasil|do brasil)\b")

# Ordem de "avanço": só atualiza quando o novo status vem depois do atual.
_RANK = {JobStatus.APPLIED: 1, JobStatus.INTERVIEW: 2, JobStatus.REJECTED: 3}


def classify(subject: str, body: str) -> JobStatus | None:
    """``INTERVIEW``, ``REJECTED`` ou ``None``. Recusa tem prioridade."""
    text = normalize(f"{subject}\n{body[:4000]}")
    if _REJECTED.search(text):
        return JobStatus.REJECTED
    if _INTERVIEW.search(text):
        return JobStatus.INTERVIEW
    return None


def company_key(company: str | None) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", normalize(company or ""))
    return re.sub(r"\s+", " ", _COMPANY_NOISE.sub(" ", text)).strip()


def find_job_for_email(db: Database, haystack: str) -> dict[str, Any] | None:
    """Candidatura em andamento cuja empresa aparece no remetente, assunto ou corpo."""
    text = " " + re.sub(r"[^a-z0-9 ]+", " ", normalize(haystack)) + " "
    for job in db.jobs_with_status(JobStatus.APPLIED, JobStatus.INTERVIEW):
        key = company_key(job.get("company"))
        if len(key) >= 3 and f" {key} " in text:
            return job
    return None


def apply_response(
    db: Database, *, sender: str, subject: str, body: str, received: str | None = None
) -> dict[str, Any] | None:
    """Atualiza o status da vaga se o e-mail for uma resposta reconhecida."""
    status = classify(subject, body)
    if status is None:
        return None
    job = find_job_for_email(db, f"{sender}\n{subject}\n{body[:2000]}")
    if job is None:
        return None
    current = JobStatus(job["status"])
    if _RANK[status] <= _RANK.get(current, 0):
        return None
    when = received or datetime.now(UTC).date().isoformat()
    note = f"{when}: e-mail \"{subject.strip()[:120]}\" → {status.value}"
    notes = f"{job['notes']}\n{note}" if job.get("notes") else note
    return db.update_job(job["id"], status=status, notes=notes)
