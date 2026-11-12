from __future__ import annotations

import pytest
from fakes import fake_llm, offline_llm

from searchjob.analyzer import analyze_job, analyze_pending, answer_question
from searchjob.llm import LLMError, extract_json

GOOD_REPLY = """<think>pensando...</think>
```json
{"score": 8.6, "summary": "Boa aderência para N1.",
 "requirements": ["Windows", "Atendimento"], "missing": ["ITIL"]}
```"""


def test_extract_json_tolerates_noise():
    assert extract_json('Claro! {"a": 1} espero ter ajudado')["a"] == 1
    with pytest.raises(LLMError):
        extract_json("sem json aqui")


def test_analyze_job_parses_and_clamps():
    llm, sent = fake_llm(GOOD_REPLY)
    result = analyze_job(llm, "Sei Windows", {"title": "Suporte N1", "description": "..."})
    assert result.score == 9
    assert result.missing == ["ITIL"]
    assert sent[0]["model"] == "modelo-teste"
    assert "Sei Windows" in sent[0]["messages"][1]["content"]


def test_analyze_job_clamps_out_of_range_score():
    llm, _ = fake_llm('{"score": 42}')
    assert analyze_job(llm, "", {"title": "x"}).score == 10


def test_analyze_pending_saves_results(db, make_job):
    db.upsert_job(make_job("1"))
    db.upsert_job(make_job("2"))
    llm, _ = fake_llm(GOOD_REPLY, "resposta inválida")
    assert analyze_pending(db, llm, "perfil") == 1
    scores = sorted((j["score"] for j in db.list_jobs()), key=lambda s: s is None)
    assert scores == [9, None]


def test_analyze_pending_stops_when_llm_offline(db, make_job):
    db.upsert_job(make_job("1"))
    assert analyze_pending(db, offline_llm(), "perfil") == 0
    assert len(db.pending_analysis(10)) == 1


def test_qwen3_thinking_is_disabled():
    from searchjob.llm import LLMClient, disable_thinking, uses_thinking

    assert uses_thinking("qwen3:8b") and uses_thinking("Qwen3-8B-Instruct")
    assert not uses_thinking("qwen2.5:3b-instruct")
    msgs = disable_thinking([{"role": "system", "content": "Seja breve."}])
    assert msgs[0]["content"] == "Seja breve. /no_think"
    assert disable_thinking([{"role": "user", "content": "oi"}])[0]["content"] == "/no_think"

    llm, sent = fake_llm('{"score": 5}')
    llm = LLMClient("http://llm.test/v1", "qwen3:8b", client=llm.client)
    analyze_job(llm, "perfil", {"title": "x"})
    assert sent[0]["messages"][0]["content"].endswith("/no_think")


def test_answer_question_respects_limit():
    llm, sent = fake_llm('"Tenho facilidade em explicar soluções técnicas de forma simples."')
    answer = answer_question(llm, "perfil", "Por que você?", max_chars=30)
    assert len(answer) <= 31
    assert not answer.startswith('"')
    assert "30 caracteres" in sent[0]["messages"][1]["content"]
