from __future__ import annotations

from email.message import EmailMessage

from searchjob.collectors.email_alerts import (
    alert_source,
    parse_alert,
    process_mailbox,
)
from searchjob.config import Settings
from searchjob.models import JobStatus
from searchjob.pipeline import new_stats
from searchjob.responses import classify, company_key

LINKEDIN_HTML = """
<table>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/3987654321/?trackingId=abc">
      <p>Analista de Suporte Técnico</p>
      <p>Empresa Alfa · São Paulo, SP (Híbrido)</p>
    </a>
    <a href="https://www.linkedin.com/comm/jobs/view/3987654321/?trk=x">Ver vaga</a>
  </td></tr>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/3911112222/">
      <div>Help Desk N1</div><div>Beta Serviços · Brasil (Remoto)</div>
    </a>
  </td></tr>
  <tr><td><a href="https://www.linkedin.com/comm/jobs/search/">Ver todas as vagas</a></td></tr>
</table>
"""

INDEED_HTML = """
<a href="https://br.indeed.com/rc/clk?jk=a1b2c3d4e5&from=ja">Técnico de Informática</a>
<p>Gama Tecnologia - Campinas, SP</p>
"""


def _email(sender: str, subject: str, html: str | None = None, text: str | None = None,
           message_id: str = "<1@test>") -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "vagas@example.com"
    msg["Subject"] = subject
    msg["Date"] = "Thu, 12 Nov 2026 10:00:00 -0300"
    msg["Message-ID"] = message_id
    msg.set_content(text or "versão em texto")
    if html:
        msg.add_alternative(html, subtype="html")
    return msg.as_bytes()


class FakeMailbox:
    def __init__(self, messages: list[bytes]):
        self.messages = messages
        self.readonly = None

    def select(self, mailbox="INBOX", readonly=False):
        self.readonly = readonly
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        assert criteria[0] == "SINCE"
        nums = " ".join(str(i + 1) for i in range(len(self.messages)))
        return "OK", [nums.encode()]

    def fetch(self, num, parts):
        assert "PEEK" in parts  # não pode marcar como lido
        return "OK", [(b"1 (BODY[] {123}", self.messages[int(num) - 1]), b")"]

    def logout(self):
        return "BYE", []


def test_alert_source():
    assert alert_source("linkedin.com") == "linkedin"
    assert alert_source("e.linkedin.com") == "linkedin"
    assert alert_source("gmail.com") is None


def test_parse_linkedin_alert():
    jobs = parse_alert(LINKEDIN_HTML, "linkedin")
    assert [j.external_id for j in jobs] == ["3987654321", "3911112222"]
    first, second = jobs
    assert first.title == "Analista de Suporte Técnico"
    assert first.company == "Empresa Alfa"
    assert first.url == "https://www.linkedin.com/jobs/view/3987654321/"
    assert (first.city, first.workplace_type) == ("São Paulo", "hybrid")
    assert second.workplace_type == "remote"
    assert second.company == "Beta Serviços"


def test_parse_indeed_alert():
    jobs = parse_alert(INDEED_HTML, "indeed")
    assert len(jobs) == 1
    assert jobs[0].external_id == "a1b2c3d4e5"
    assert jobs[0].url == "https://br.indeed.com/viewjob?jk=a1b2c3d4e5"
    assert jobs[0].title == "Técnico de Informática"


def test_classify_responses():
    assert classify("Convite para entrevista", "") == JobStatus.INTERVIEW
    assert classify("Atualização", "Infelizmente não seguiremos com sua candidatura") == (
        JobStatus.REJECTED
    )
    assert classify("Newsletter", "Confira nossas novidades") is None
    assert company_key("Empresa Alfa LTDA") == "empresa alfa"


def test_process_mailbox_collects_alerts_and_updates_status(db, make_job, tmp_path):
    settings = Settings(data_dir=tmp_path, imap_days=3)
    db.upsert_job(make_job("9", company="Gama Tecnologia LTDA"))
    applied = db.list_jobs()[0]
    db.update_job(applied["id"], status=JobStatus.APPLIED)

    messages = [
        _email("LinkedIn <jobalerts-noreply@linkedin.com>", "Novas vagas", LINKEDIN_HTML,
               message_id="<a@li>"),
        _email("Recrutamento <talentos@gamatec.com.br>",
               "Gama Tecnologia: convite para entrevista",
               text="Olá! Gostaríamos de agendar uma entrevista.", message_id="<b@gama>"),
        _email("Loja <promo@loja.com>", "Ofertas", text="Promoção", message_id="<c@x>"),
    ]
    mailbox = FakeMailbox(messages)
    stats = new_stats()
    summary = process_mailbox(db, settings, stats, mailbox=mailbox)

    assert mailbox.readonly is True
    assert summary == {"emails": 3, "alerts": 1, "responses": 1}
    assert stats["new"] == 2
    assert db.get_job(applied["id"])["status"] == "interview"
    assert "convite para entrevista" in db.get_job(applied["id"])["notes"]

    # Segunda leitura: nada é reprocessado
    again = process_mailbox(db, settings, new_stats(), mailbox=FakeMailbox(messages))
    assert again == {"emails": 0, "alerts": 0, "responses": 0}


def test_rejection_after_interview_and_no_downgrade(db, make_job, tmp_path):
    settings = Settings(data_dir=tmp_path)
    db.upsert_job(make_job("5", company="Delta Hospitalar"))
    job_id = db.list_jobs()[0]["id"]
    db.update_job(job_id, status=JobStatus.INTERVIEW)

    messages = [
        _email("Delta <rh@delta.com>", "Processo seletivo Delta Hospitalar",
               text="Infelizmente optamos por outro candidato.", message_id="<r@delta>"),
        _email("Delta <rh@delta.com>", "Delta Hospitalar - entrevista",
               text="Vamos agendar?", message_id="<s@delta>"),
    ]
    process_mailbox(db, settings, new_stats(), mailbox=FakeMailbox(messages))
    assert db.get_job(job_id)["status"] == "rejected"


def test_process_mailbox_reports_connection_error(db, tmp_path):
    settings = Settings(data_dir=tmp_path, imap_host="127.0.0.1", imap_port=1,
                        imap_user="x", imap_password="y")
    stats = new_stats()
    summary = process_mailbox(db, settings, stats)
    assert summary["emails"] == 0
    assert stats["errors"] and stats["errors"][0].startswith("e-mail:")
