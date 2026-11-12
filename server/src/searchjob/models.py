from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class JobStatus(StrEnum):
    NEW = "new"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    IGNORED = "ignored"


@dataclass(slots=True)
class JobPosting:
    """Vaga normalizada, independente da fonte."""

    source: str
    external_id: str
    title: str
    url: str
    company: str | None = None
    description: str = ""
    city: str | None = None
    state: str | None = None
    workplace_type: str | None = None  # on-site | hybrid | remote
    published_at: str | None = None
    deadline: str | None = None
    skills: list[str] = field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    min_experience: int | None = None  # anos exigidos, quando a vaga informa
    flags: list[str] = field(default_factory=list)  # avisos (ex.: "Pede 5 anos de experiência")

    @property
    def is_remote(self) -> bool:
        return (self.workplace_type or "").lower() == "remote"
