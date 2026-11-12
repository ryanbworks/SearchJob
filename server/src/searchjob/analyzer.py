"""Uso da IA local: nota de aderência das vagas e respostas para perguntas abertas."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .db import Database
from .llm import LLMClient, LLMError, LLMUnavailable, extract_json

log = logging.getLogger(__name__)

MAX_DESCRIPTION_CHARS = 6000

ANALYSIS_SYSTEM = (
    "Você é um recrutador experiente da área de TI no Brasil. Avalie, com honestidade, "
    "o quanto o candidato combina com a vaga. Responda SOMENTE com um objeto JSON válido, "
    "sem texto fora dele."
)

ANALYSIS_TEMPLATE = """\
PERFIL DO CANDIDATO:
{profile}

VAGA: {title} — {company} ({location})
{warnings}DESCRIÇÃO:
{description}

Responda neste formato JSON:
{{
  "score": <inteiro de 0 a 10; 10 = candidato muito aderente>,
  "summary": "<uma frase curta explicando a nota>",
  "requirements": ["<requisitos principais da vaga, no máximo 8>"],
  "missing": ["<requisitos obrigatórios que o candidato NÃO demonstra, no máximo 5>"]
}}
Considere vagas de nível júnior/estágio/N1 mais aderentes a quem está começando.
Penalize vagas sênior ou que exigem experiência longa que o candidato não tem."""

ANSWER_SYSTEM = (
    "Você ajuda um candidato a preencher formulários de candidatura em português do Brasil. "
    "Escreva em primeira pessoa, de forma natural, objetiva e profissional. "
    "Use apenas fatos presentes no perfil; nunca invente experiências, empresas ou certificações. "
    "Responda apenas com o texto da resposta, sem aspas e sem comentários."
)


@dataclass(slots=True)
class Analysis:
    score: int
    summary: str
    requirements: list[str]
    missing: list[str]


def _str_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def _location(job: dict[str, Any]) -> str:
    if (job.get("workplace_type") or "") == "remote":
        return "remoto"
    parts = [p for p in (job.get("city"), job.get("state")) if p]
    place = "/".join(parts) or "local não informado"
    return f"{place}, {job.get('workplace_type') or 'modalidade não informada'}"


def analyze_job(llm: LLMClient, profile: str, job: dict[str, Any]) -> Analysis:
    prompt = ANALYSIS_TEMPLATE.format(
        profile=profile.strip() or "(perfil não informado)",
        title=job.get("title", ""),
        company=job.get("company") or "empresa não informada",
        location=_location(job),
        warnings=(f"AVISOS DETECTADOS: {'; '.join(job['flags'])}\n" if job.get("flags") else ""),
        description=(job.get("description") or "")[:MAX_DESCRIPTION_CHARS],
    )
    raw = llm.chat(
        [{"role": "system", "content": ANALYSIS_SYSTEM}, {"role": "user", "content": prompt}],
        temperature=0.1,
    )
    data = extract_json(raw)
    try:
        score = int(round(float(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    return Analysis(
        score=max(0, min(10, score)),
        summary=str(data.get("summary") or "").strip()[:400],
        requirements=_str_list(data.get("requirements"), 8),
        missing=_str_list(data.get("missing"), 5),
    )


def analyze_pending(db: Database, llm: LLMClient, profile: str, limit: int = 30) -> int:
    """Analisa vagas ainda sem nota. Para cedo se o servidor de IA estiver offline."""
    done = 0
    for job in db.pending_analysis(limit):
        try:
            result = analyze_job(llm, profile, job)
        except LLMUnavailable as exc:
            log.warning("IA indisponível, análise adiada: %s", exc)
            break
        except LLMError as exc:
            log.warning("Falha ao analisar vaga %s: %s", job["id"], exc)
            continue
        db.save_analysis(
            job["id"],
            score=result.score,
            summary=result.summary,
            requirements=result.requirements,
            missing=result.missing,
        )
        done += 1
    return done


def answer_question(
    llm: LLMClient,
    profile: str,
    question: str,
    *,
    job: dict[str, Any] | None = None,
    page_context: str = "",
    max_chars: int | None = None,
) -> str:
    context = ""
    if job:
        context = (
            f"VAGA: {job.get('title')} — {job.get('company') or ''}\n"
            f"{(job.get('description') or '')[:3000]}"
        )
    elif page_context:
        context = f"TEXTO DA PÁGINA DA VAGA:\n{page_context[:3000]}"
    limit = f"\nLimite: no máximo {max_chars} caracteres." if max_chars else ""
    prompt = (
        f"PERFIL DO CANDIDATO:\n{profile.strip()}\n\n{context}\n\n"
        f"PERGUNTA DO FORMULÁRIO: {question.strip()}{limit}"
    )
    answer = llm.chat(
        [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=500,
    ).strip().strip('"')
    if max_chars and len(answer) > max_chars:
        answer = answer[:max_chars].rsplit(" ", 1)[0].rstrip(",;") + "."
    return answer
