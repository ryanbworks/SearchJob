from __future__ import annotations

import html
import re
from collections.abc import Iterator
from typing import Protocol

from ..models import JobPosting

# Cabeçalhos HTTP só aceitam ASCII: nada de acentos aqui.
USER_AGENT = "SearchJob/0.1 (+uso pessoal; coleta de baixa frequencia)"

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t]+")


def clean_text(raw: str | None) -> str:
    """Remove HTML simples e espaços repetidos, preservando quebras de linha."""
    if not raw:
        return ""
    text = re.sub(r"<\s*(br|/p|/li|/div)\s*/?>", "\n", raw, flags=re.I)
    text = html.unescape(_TAG_RE.sub("", text))
    lines = (_SPACE_RE.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


class Collector(Protocol):
    """Contrato de um coletor de vagas. Novas fontes só precisam implementar isso."""

    source: str

    def fetch(self, term: str) -> Iterator[JobPosting]: ...
