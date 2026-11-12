from searchjob.models import JobStatus


def test_upsert_is_idempotent(db, make_job):
    assert db.upsert_job(make_job("1")) is True
    assert db.upsert_job(make_job("1", title="Título atualizado")) is False
    jobs = db.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Título atualizado"
    assert jobs[0]["skills"] == ["Windows", "Active Directory"]


def test_analysis_and_ordering(db, make_job):
    db.upsert_job(make_job("1"))
    db.upsert_job(make_job("2"))
    first, second = (j["id"] for j in db.list_jobs())
    db.save_analysis(second, score=9, summary="Ótima", requirements=["Windows"], missing=[])
    db.save_analysis(first, score=4, summary="Fraca", requirements=[], missing=["Inglês"])

    ranked = db.list_jobs()
    assert [j["score"] for j in ranked] == [9, 4]
    assert ranked[1]["missing"] == ["Inglês"]
    assert db.pending_analysis(10) == []
    assert len(db.list_jobs(min_score=5)) == 1


def test_status_update_and_url_match(db, make_job):
    db.upsert_job(make_job("7", url="https://empresa.gupy.io/job/7?source=portal"))
    job = db.find_by_url("https://empresa.gupy.io/job/7?outro=param")
    assert job is not None

    updated = db.update_job(job["id"], status=JobStatus.APPLIED, notes="Enviado")
    assert updated["status"] == "applied"
    assert updated["notes"] == "Enviado"
    assert db.list_jobs(status=JobStatus.NEW) == []


def test_insights_counts_skills(db, make_job):
    db.upsert_job(make_job("1", skills=["Windows"]))
    db.upsert_job(make_job("2", skills=["Windows", "ITIL"]))
    data = db.insights(days=30)
    assert data["total_jobs"] == 2
    assert data["skills"][0] == {"skill": "Windows", "count": 2, "percent": 100.0}
    assert data["status"] == {"new": 2}
