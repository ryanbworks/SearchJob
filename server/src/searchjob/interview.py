"""Preparação para entrevista com a IA local: perguntas prováveis, casos práticos e feedback."""

from __future__ import annotations

from typing import Any

from .llm import LLMClient, LLMError, extract_json

PREP_SYSTEM = (
    "Você é um analista de suporte experiente que também recruta para vagas de TI no Brasil e "
    "prepara candidatos em início de carreira para entrevistas. Seja prático e honesto. "
    "Use apenas fatos do perfil do candidato; nunca invente experiências. "
    "Responda SOMENTE com um objeto JSON válido."
)

PREP_TEMPLATE = """\
PERFIL DO CANDIDATO:
{profile}

VAGA: {title} — {company}
DESCRIÇÃO:
{description}

Gere a preparação para a entrevista desta vaga neste formato JSON:
{{
  "questions": [
    {{"question": "<pergunta provável>",
      "why": "<o que o entrevistador quer avaliar>",
      "tip": "<como responder bem usando o perfil, em 1-2 frases>"}}
  ],
  "scenarios": [
    {{"situation": "<problema real de suporte que pode cair no teste ou na entrevista>",
      "steps": ["<passo de diagnóstico/resolução, na ordem>"]}}
  ],
  "pitch": "<roteiro de 60 a 90 segundos para 'fale sobre você', em primeira pessoa>",
  "ask_them": ["<pergunta inteligente para o candidato fazer ao recrutador>"]
}}
Inclua 8 perguntas (comportamentais e técnicas, conforme os requisitos da vaga),
3 casos práticos com 4 a 6 passos cada e 3 perguntas para o recrutador."""

FEEDBACK_SYSTEM = (
    "Você é um entrevistador de vagas de suporte técnico júnior. Avalie a resposta do "
    "candidato com franqueza e gentileza, pensando no que um recrutador brasileiro espera. "
    "Responda SOMENTE com um objeto JSON válido."
)

FEEDBACK_TEMPLATE = """\
PERFIL DO CANDIDATO:
{profile}
{job}
PERGUNTA: {question}
RESPOSTA DO CANDIDATO: {answer}

Formato JSON:
{{
  "score": <inteiro de 0 a 10>,
  "strengths": ["<o que foi bom>"],
  "improve": ["<o que melhorar, de forma concreta>"],
  "model_answer": "<exemplo de resposta melhor, em primeira pessoa, só com fatos do perfil>"
}}"""


def _text(value: Any, limit: int = 600) -> str:
    return str(value or "").strip()[:limit]


def _texts(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [t for t in (_text(v, 400) for v in value) if t][:limit]


def _score(value: Any) -> int:
    try:
        return max(0, min(10, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def generate_prep(llm: LLMClient, profile: str, job: dict[str, Any]) -> dict[str, Any]:
    prompt = PREP_TEMPLATE.format(
        profile=profile.strip() or "(perfil não informado)",
        title=job.get("title", ""),
        company=job.get("company") or "empresa não informada",
        description=(job.get("description") or "")[:5000],
    )
    data = extract_json(
        llm.chat(
            [{"role": "system", "content": PREP_SYSTEM}, {"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2200,
        )
    )
    questions = [
        {"question": _text(q.get("question"), 400), "why": _text(q.get("why")),
         "tip": _text(q.get("tip"))}
        for q in data.get("questions") or []
        if isinstance(q, dict) and _text(q.get("question"))
    ][:10]
    if not questions:
        raise LLMError("A IA não gerou perguntas. Tente de novo.")
    scenarios = [
        {"situation": _text(s.get("situation"), 500), "steps": _texts(s.get("steps"), 8)}
        for s in data.get("scenarios") or []
        if isinstance(s, dict) and _text(s.get("situation"))
    ][:4]
    return {
        "questions": questions,
        "scenarios": scenarios,
        "pitch": _text(data.get("pitch"), 2000),
        "ask_them": _texts(data.get("ask_them"), 5),
    }


def answer_feedback(
    llm: LLMClient,
    profile: str,
    question: str,
    answer: str,
    job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_text = f"VAGA: {job.get('title')} — {job.get('company') or ''}\n" if job else ""
    prompt = FEEDBACK_TEMPLATE.format(
        profile=profile.strip() or "(perfil não informado)",
        job=job_text,
        question=question.strip(),
        answer=answer.strip(),
    )
    data = extract_json(
        llm.chat(
            [{"role": "system", "content": FEEDBACK_SYSTEM}, {"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=900,
        )
    )
    return {
        "score": _score(data.get("score")),
        "strengths": _texts(data.get("strengths"), 4),
        "improve": _texts(data.get("improve"), 4),
        "model_answer": _text(data.get("model_answer"), 2000),
    }
