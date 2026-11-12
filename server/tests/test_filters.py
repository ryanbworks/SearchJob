from __future__ import annotations

import sqlite3

import pytest

from searchjob.config import Settings
from searchjob.db import Database
from searchjob.filters import (
    enrich,
    exclusion_reason,
    extract_min_experience,
    extract_salary,
)
from searchjob.pipeline import collect


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Salário: R$ 2.000,00 + benefícios", (2000.0, 2000.0)),
        ("Faixa salarial R$ 1.800 a R$ 2.200", (1800.0, 2200.0)),
        ("Remuneração de R$1800 - 2400 mensais", (1800.0, 2400.0)),
        ("Salário compatível de 2,5 mil reais", (2500.0, 2500.0)),
        ("Vale refeição R$ 30,00 por dia e VA R$ 600", (None, None)),
        ("Sem informação de salário", (None, None)),
    ],
)
def test_extract_salary(text, expected):
    assert extract_salary(text) == expected


def test_extract_salary_prefers_salary_context_over_benefits():
    text = "Benefícios: auxílio home office R$ 150. Salário: R$ 2.300,00"
    assert extract_salary(text) == (2300.0, 2300.0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Experiência mínima de 3 anos em suporte", 3),
        ("Desejável 1 ano de experiência com atendimento", 1),
        ("Mínimo de dois anos atuando com redes", 2),
        ("5+ anos de experiência em infraestrutura", 5),
        ("Ser maior de 18 anos", None),
        ("Primeiro emprego! Não exigimos experiência", None),
    ],
)
def test_extract_min_experience(text, expected):
    assert extract_min_experience(text) == expected


def test_exclusion_reason(make_job):
    terms = ["sênior", "pleno", "sr"]
    assert exclusion_reason(make_job(title="Analista de Suporte Sênior"), terms, [])
    assert exclusion_reason(make_job(title="Suporte Técnico SR"), terms, [])
    assert exclusion_reason(make_job(title="Suporte Técnico Jr"), terms, []) is None
    # "sr" não pode casar dentro de outra palavra
    assert exclusion_reason(make_job(title="Técnico de Suporte - Srta"), terms, []) is None
    blocked = exclusion_reason(
        make_job(description="Ganhos por comissão e metas"), [], ["comissão"]
    )
    assert blocked == "contém o termo bloqueado 'comissão'"


def test_enrich_adds_flags(make_job):
    job = make_job(description="Salário R$ 2.100. Experiência mínima de 4 anos.",
                   skills=["CNH"])
    enrich(job, max_experience_years=2)
    assert job.salary_min == 2100.0
    assert job.min_experience == 4
    assert job.flags == ["Pede 4 anos de experiência", "Exige ou valoriza CNH"]


class ListCollector:
    source = "fake"

    def __init__(self, jobs):
        self.jobs = jobs

    def fetch(self, term):
        yield from self.jobs


def test_collect_excludes_and_records_run(db, make_job, tmp_path):
    settings = Settings(data_dir=tmp_path, search_terms=["suporte"])
    jobs = [
        make_job("1", description="Salário R$ 1.900"),
        make_job("2", title="Coordenador de Suporte"),
    ]
    stats = collect(db, settings, collectors=[ListCollector(jobs)])
    assert stats["new"] == 1
    assert stats["excluded"] == 1
    assert stats["excluded_reasons"] == {"título contém 'coordenador'": 1}
    saved = db.list_jobs()[0]
    assert saved["salary_min"] == 1900.0
    assert saved["flags"] == []

    db.save_run(stats)
    assert db.runs_since(1)[0]["excluded"] == 1


def test_migration_adds_columns_to_old_database(tmp_path):
    path = tmp_path / "antigo.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE jobs (id INTEGER PRIMARY KEY, source TEXT NOT NULL,
           external_id TEXT NOT NULL, title TEXT NOT NULL, company TEXT,
           description TEXT NOT NULL DEFAULT '', url TEXT NOT NULL, city TEXT, state TEXT,
           workplace_type TEXT, published_at TEXT, deadline TEXT,
           skills TEXT NOT NULL DEFAULT '[]', collected_at TEXT NOT NULL, score INTEGER,
           summary TEXT, requirements TEXT, missing TEXT, analyzed_at TEXT,
           status TEXT NOT NULL DEFAULT 'new', status_updated_at TEXT, notes TEXT,
           UNIQUE (source, external_id))"""
    )
    conn.commit()
    conn.close()

    db = Database(path)
    with db.conn() as c:
        columns = {row["name"] for row in c.execute("PRAGMA table_info(jobs)")}
    assert {"salary_min", "salary_max", "min_experience", "flags"} <= columns
