from __future__ import annotations

import httpx

from searchjob.config import Settings
from searchjob.notify import format_summary
from searchjob.pipeline import collect, passes_location
from searchjob.report import build_context, render_report


class FakeCollector:
    source = "fake"

    def __init__(self, jobs, fail_on=None):
        self.jobs = jobs
        self.fail_on = fail_on

    def fetch(self, term):
        if term == self.fail_on:
            raise httpx.ConnectError("sem rede")
        yield from self.jobs


def test_passes_location(make_job):
    states = ["São Paulo"]
    assert passes_location(make_job(state="Sao Paulo"), states)
    assert not passes_location(make_job(state="Bahia"), states)
    assert passes_location(make_job(state="Bahia", workplace_type="remote"), states)
    assert passes_location(make_job(state="Bahia"), [])


def test_collect_dedupes_filters_and_reports_errors(db, make_job, tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        search_terms=["suporte", "help desk", "quebrado"],
        preferred_states=["São Paulo"],
    )
    jobs = [make_job("1"), make_job("2", state="Bahia")]
    stats = collect(db, settings, collectors=[FakeCollector(jobs, fail_on="quebrado")])

    assert stats["found"] == 4  # 2 vagas x 2 termos que funcionaram
    assert stats["new"] == 1
    assert stats["filtered"] == 2
    assert len(stats["errors"]) == 1
    assert len(db.list_jobs()) == 1


def test_report_renders_jobs_and_escapes_html(db, make_job):
    db.upsert_job(make_job("1", title="<script>alert(1)</script> Suporte"))
    html = render_report(build_context(db))
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html


def test_format_summary():
    assert "nenhuma vaga" in format_summary([])
    text = format_summary([{"title": "Help Desk", "company": "X", "url": "http://a", "score": 8}])
    assert "[8/10] Help Desk" in text
