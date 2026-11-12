from __future__ import annotations

from datetime import UTC, datetime

from searchjob.dashboard import build_dashboard, title_key
from searchjob.models import JobStatus


def test_title_key_ignores_level_and_accents():
    assert title_key("Analista de Suporte Técnico Jr.") == title_key("ANALISTA DE SUPORTE TECNICO")
    assert title_key("Técnico de Informática II") == "tecnico de informatica"


def _seed(db, make_job):
    db.upsert_job(make_job("1", company="Acme", title="Suporte Técnico Jr",
                           skills=["Windows", "ITIL"]))
    db.upsert_job(make_job("2", company="Acme", title="Suporte Técnico",
                           skills=["Windows", "Active Directory"]))
    db.upsert_job(make_job("3", company="Beta", title="Help Desk N1", skills=["Windows"],
                           workplace_type="remote"))
    ids = {j["external_id"]: j["id"] for j in db.list_jobs()}
    db.save_analysis(ids["1"], score=8, summary="", requirements=[], missing=["ITIL", "Inglês"])
    db.save_analysis(ids["2"], score=5, summary="", requirements=[], missing=["itil."])
    db.update_job(ids["2"], status=JobStatus.APPLIED)
    db.update_job(ids["3"], status=JobStatus.INTERVIEW)
    return ids


def test_dashboard_gaps_and_strengths(db, make_job):
    _seed(db, make_job)
    data = build_dashboard(db, "Sei Windows e atendimento ao usuário.", days=30)

    assert data["kpis"]["total_jobs"] == 3
    assert data["kpis"]["avg_score"] == 6.5
    assert data["kpis"]["good_matches"] == 1
    # Windows (3 vagas) coberto; ITIL (1) e AD (1) não → 3 de 5 menções
    assert data["coverage"] == 60.0
    assert [s["skill"] for s in data["strengths"]] == ["Windows"]
    assert {s["skill"] for s in data["gaps"]} == {"ITIL", "Active Directory"}
    assert all(r["tip"] for r in data["recommendations"])
    assert data["resume_keywords"] == ["Windows"]


def test_dashboard_ai_missing_merges_spellings(db, make_job):
    _seed(db, make_job)
    data = build_dashboard(db, "", days=30)
    top = data["ai_missing"][0]
    assert top["label"].lower() == "itil"
    assert top["count"] == 2
    assert top["percent"] == 100.0


def test_dashboard_repetition_and_funnel(db, make_job):
    _seed(db, make_job)
    data = build_dashboard(db, "", days=30)

    assert data["reposts"][0]["company"] == "Acme"
    assert data["reposts"][0]["count"] == 2
    assert data["companies"][0] == {"label": "Acme", "count": 2, "percent": 66.7}
    funnel = {f["status"]: f["count"] for f in data["funnel"]}
    assert funnel["applied"] == 1 and funnel["interview"] == 1 and funnel["new"] == 1
    assert data["kpis"]["applications"] == 2
    assert data["kpis"]["response_rate"] == 50.0


def test_dashboard_timeline_is_zero_filled(db, make_job):
    db.upsert_job(make_job("1", published_at="2026-11-10T09:00:00Z"))
    today = datetime(2026, 11, 12, tzinfo=UTC).date()
    data = build_dashboard(db, "", days=7, today=today)
    assert len(data["timeline"]) == 7
    assert data["timeline"][-1]["date"] == "2026-11-12"
    assert {"date": "2026-11-10", "count": 1} in data["timeline"]
    assert sum(p["count"] for p in data["timeline"]) == 1
    assert len(data["score_histogram"]) == 11
