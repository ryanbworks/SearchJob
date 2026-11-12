"""Currículo adaptado por vaga: reorganiza o perfil para o que a vaga pede, sem inventar."""

from __future__ import annotations

import re
from typing import Any

from .llm import LLMClient, LLMError, extract_json
from .skills import extract_skills, normalize

RESUME_SYSTEM = (
    "Você é especialista em currículos para vagas de TI em início de carreira no Brasil e "
    "conhece os filtros automáticos (ATS). Sua tarefa é REORGANIZAR e REESCREVER o perfil "
    "do candidato para a vaga, usando as palavras da vaga quando forem verdadeiras. "
    "É proibido inventar experiências, empresas, cursos, certificações ou ferramentas que "
    "não estejam no perfil. Responda SOMENTE com um objeto JSON válido."
)

RESUME_TEMPLATE = """\
PERFIL DO CANDIDATO:
{profile}

VAGA: {title} — {company}
DESCRIÇÃO:
{description}

Formato JSON:
{{
  "headline": "<título profissional curto alinhado à vaga, ex.: Suporte Técnico | Help Desk N1>",
  "summary": "<resumo profissional de 3 a 4 frases, focado no que a vaga pede e o perfil comprova>",
  "skills": ["<conhecimentos que ESTÃO no perfil, do mais ao menos relevante para a vaga>"],
  "highlights": [
    {{"title": "<projeto, experiência ou atividade do perfil>",
      "description": "<1 a 2 frases com o que foi feito, usando termos da vaga>"}}
  ],
  "keywords_used": ["<palavras-chave da vaga presentes no currículo>"],
  "missing_keywords": ["<palavras-chave importantes da vaga que o perfil NÃO comprova>"]
}}"""


def _text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _texts(value: Any, limit: int, size: int = 120) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result = []
    for item in value:
        text = _text(item, size)
        if text and normalize(text) not in seen:
            seen.add(normalize(text))
            result.append(text)
    return result[:limit]


def skill_in_profile(skill: str, profile: str) -> bool:
    """A habilidade aparece no perfil (literalmente ou pela mesma categoria de requisito)?"""
    norm_skill, norm_profile = normalize(skill), normalize(profile)
    if norm_skill and norm_skill in norm_profile:
        return True
    categories = extract_skills(skill)
    return bool(categories) and set(categories) <= set(extract_skills(profile))


def profile_section(profile: str, heading_hint: str) -> list[str]:
    """Itens (linhas com '-') da seção do perfil cujo título contém ``heading_hint``."""
    items: list[str] = []
    inside = False
    for line in profile.splitlines():
        if line.startswith("#"):
            inside = heading_hint in normalize(line)
            continue
        if inside and line.strip().startswith(("-", "*")):
            items.append(line.strip().lstrip("-* ").strip())
    return items


def generate_resume(llm: LLMClient, profile: str, job: dict[str, Any]) -> dict[str, Any]:
    prompt = RESUME_TEMPLATE.format(
        profile=profile.strip() or "(perfil não informado)",
        title=job.get("title", ""),
        company=job.get("company") or "empresa não informada",
        description=(job.get("description") or "")[:5000],
    )
    data = extract_json(
        llm.chat(
            [{"role": "system", "content": RESUME_SYSTEM}, {"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1600,
        )
    )
    suggested = _texts(data.get("skills"), 20, 60)
    skills = [s for s in suggested if skill_in_profile(s, profile)]
    highlights = [
        {"title": _text(h.get("title"), 120), "description": _text(h.get("description"), 400)}
        for h in data.get("highlights") or []
        if isinstance(h, dict) and _text(h.get("title"), 120)
    ][:5]
    summary = _text(data.get("summary"), 900)
    if not summary:
        raise LLMError("A IA não gerou o resumo do currículo. Tente de novo.")
    return {
        "headline": _text(data.get("headline"), 120),
        "summary": summary,
        "skills": skills,
        "removed_skills": [s for s in suggested if s not in skills],
        "highlights": highlights,
        "keywords_used": _texts(data.get("keywords_used"), 15, 60),
        "missing_keywords": _texts(data.get("missing_keywords"), 10, 60),
    }
