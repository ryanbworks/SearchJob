"""Filtros de qualidade: descarta vagas que não servem e extrai salário e experiência."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .models import JobPosting
from .skills import normalize

_MONEY = r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
_SALARY_RE = re.compile(
    rf"r\$\s*{_MONEY}(?:\s*(?:a|ate|-|–|e)\s*(?:r\$\s*)?{_MONEY})?"
)
_MIL_RE = re.compile(r"(?:salario|remuneracao|bolsa)[^\n]{0,40}?(\d+(?:,\d)?)\s*mil\b")
_SALARY_CONTEXT = re.compile(r"salari|remunera|faixa|bolsa|pagamento|ganho")
_BENEFIT_CONTEXT = re.compile(
    r"\b(vr|va|vt|vale|alimenta|refeic|auxilio|ajuda de custo|plr|bonus|premio|seguro|"
    r"reembolso|comiss|gympass|wellhub|diaria|por dia|hora)"
)

_NUMBER_WORDS = {
    "um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3", "quatro": "4",
    "cinco": "5", "seis": "6", "sete": "7", "oito": "8", "dez": "10",
}
_WORD_YEARS_RE = re.compile(rf"\b({'|'.join(_NUMBER_WORDS)})(?=\s*\(?\d*\)?\s*anos?\b)")
_EXPERIENCE_RES = [
    re.compile(r"(?:minimo|pelo menos|ao menos)\s*(?:de\s*)?(\d{1,2})\s*\+?\s*anos?"),
    re.compile(r"(\d{1,2})\s*\+?\s*anos?\s*(?:ou mais\s*)?(?:de|em)\s*experiencia"),
    re.compile(r"experiencia\s*(?:minima\s*)?(?:de|com|:)?\s*(\d{1,2})\s*\+?\s*anos?"),
]


def _to_float(raw: str) -> float:
    return float(raw.replace(".", "").replace(",", "."))


def extract_salary(text: str) -> tuple[float | None, float | None]:
    """Faixa salarial mensal em R$ quando a vaga informa, ignorando benefícios."""
    norm = normalize(text)
    candidates: list[tuple[bool, list[float]]] = []
    for match in _SALARY_RE.finditer(norm):
        before = norm[max(0, match.start() - 40) : match.start()]
        if _BENEFIT_CONTEXT.search(before[-30:]):
            continue
        values = [_to_float(v) for v in match.groups() if v]
        values = [v for v in values if 800 <= v <= 50_000]
        if values:
            candidates.append((bool(_SALARY_CONTEXT.search(before)), values))
    for match in _MIL_RE.finditer(norm):
        value = _to_float(match.group(1)) * 1000
        if 800 <= value <= 50_000:
            candidates.append((True, [value]))
    if not candidates:
        return None, None
    # Prefere o valor que aparece perto de "salário"/"remuneração".
    _, values = next((c for c in candidates if c[0]), candidates[0])
    return min(values), max(values)


def extract_min_experience(text: str) -> int | None:
    """Anos mínimos de experiência pedidos (``None`` se a vaga não diz)."""
    norm = _WORD_YEARS_RE.sub(lambda m: _NUMBER_WORDS[m.group(1)], normalize(text))
    years = []
    for regex in _EXPERIENCE_RES:
        for match in regex.finditer(norm):
            value = int(match.group(1))
            if 0 < value <= 15:  # acima disso costuma ser idade ("maior de 18 anos")
                years.append(value)
    return max(years) if years else None


def _contains_term(text: str, term: str) -> bool:
    term = normalize(term).strip()
    return bool(term) and re.search(rf"\b{re.escape(term)}\b", text) is not None


def exclusion_reason(
    job: JobPosting, exclude_title_terms: Sequence[str], blocked_terms: Sequence[str]
) -> str | None:
    """Motivo para descartar a vaga antes de salvar, ou ``None`` se ela serve."""
    title = normalize(job.title)
    for term in exclude_title_terms:
        if _contains_term(title, term):
            return f"título contém '{term}'"
    full_text = f"{title}\n{normalize(job.description)}"
    for term in blocked_terms:
        if _contains_term(full_text, term):
            return f"contém o termo bloqueado '{term}'"
    return None


def enrich(job: JobPosting, max_experience_years: int) -> JobPosting:
    """Preenche salário, experiência mínima e avisos da vaga."""
    text = f"{job.title}\n{job.description}"
    job.salary_min, job.salary_max = extract_salary(text)
    job.min_experience = extract_min_experience(text)
    flags = []
    if job.min_experience is not None and job.min_experience > max_experience_years:
        flags.append(f"Pede {job.min_experience} anos de experiência")
    if "CNH" in job.skills:
        flags.append("Exige ou valoriza CNH")
    job.flags = flags
    return job
