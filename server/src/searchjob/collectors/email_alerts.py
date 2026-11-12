"""Vagas a partir de alertas por e-mail e leitura das respostas das empresas.

LinkedIn, Indeed, InfoJobs e Catho mandam alertas de vagas por e-mail. Ler esses
e-mails (via IMAP, numa conta só para isso) traz vagas desses sites sem raspar
nenhum deles. A mesma leitura reconhece respostas das empresas e atualiza o
status da candidatura.

A caixa é aberta somente leitura: nada é apagado nem marcado como lido.
"""

from __future__ import annotations

import contextlib
import hashlib
import imaplib
import logging
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from ..config import Settings
from ..db import Database
from ..models import JobPosting
from ..responses import apply_response
from ..skills import extract_skills, normalize
from .base import clean_text

log = logging.getLogger(__name__)

ALERT_DOMAINS = {
    "linkedin.com": "linkedin",
    "indeed.com": "indeed",
    "indeedemail.com": "indeed",
    "infojobs.com.br": "infojobs",
    "catho.com.br": "catho",
    "vagas.com.br": "vagas",
    "glassdoor.com": "glassdoor",
}
GENERIC_TEXT = re.compile(
    r"^(ver (a )?vaga|ver (todas|mais)|candidat|saiba mais|inscreva|clique|apply|view|"
    r"see (all|more)|unsubscribe|cancelar|descadastr|gerenciar|configur|privacidade|ajuda)"
)
_BLOCK_TAGS = {"p", "div", "br", "tr", "td", "li", "table", "h1", "h2", "h3", "h4"}
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class _LinkParser(HTMLParser):
    """Coleta (href, linhas de texto) de cada link do e-mail."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, list[str]]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._parts = []
        elif self._href is not None and tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            lines = [ln for ln in clean_text("".join(self._parts)).splitlines() if ln]
            self.links.append((self._href, lines))
            self._href = None
        elif self._href is not None and tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)


def _job_id(source: str, url: str) -> tuple[str, str] | None:
    """(id externo, URL canônica) para links de vaga conhecidos."""
    parts = urlsplit(url)
    host, path = parts.netloc.lower(), parts.path
    query = parse_qs(parts.query)
    if source == "linkedin" and (m := re.search(r"/jobs/view/(?:[^/]*?-)?(\d{6,})", path)):
        return m.group(1), f"https://www.linkedin.com/jobs/view/{m.group(1)}/"
    if source == "indeed" and "jk" in query:
        jk = query["jk"][0]
        return jk, f"https://br.indeed.com/viewjob?jk={jk}"
    if source in {"infojobs", "catho", "vagas", "glassdoor"} and (
        m := re.search(r"(\d{5,})", path)
    ):
        base = f"{parts.scheme or 'https'}://{host}{path}"
        return m.group(1), base
    return None


def _split_company_location(line: str) -> tuple[str | None, str | None]:
    pieces = [p.strip() for p in re.split(r"\s+[·•|]\s+|\s+-\s+", line) if p.strip()]
    if not pieces:
        return None, None
    return pieces[0], (pieces[1] if len(pieces) > 1 else None)


def _workplace(text: str) -> str | None:
    norm = normalize(text)
    if re.search(r"remot|home ?office", norm):
        return "remote"
    if re.search(r"hibrid|hybrid", norm):
        return "hybrid"
    return None


def _city_state(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    clean = re.sub(r"\(.*?\)", "", location).strip(" ,")
    parts = [p.strip() for p in clean.split(",") if p.strip()]
    if not parts or _workplace(parts[0]):
        return None, None
    return parts[0], (parts[1] if len(parts) > 1 else None)


def parse_alert(html: str, source: str, received: str | None = None) -> list[JobPosting]:
    """Extrai as vagas de um e-mail de alerta (HTML)."""
    parser = _LinkParser()
    parser.feed(html)
    found: dict[str, dict[str, Any]] = {}
    for href, lines in parser.links:
        ident = _job_id(source, href)
        if not ident:
            continue
        external_id, url = ident
        useful = [ln for ln in lines if not GENERIC_TEXT.search(normalize(ln))]
        entry = found.setdefault(external_id, {"url": url, "lines": []})
        if len(useful) > len(entry["lines"]):  # o link com mais texto costuma ter tudo
            entry["lines"] = useful
    jobs = []
    for external_id, entry in found.items():
        lines = entry["lines"]
        if not lines or len(lines[0]) < 4:
            continue
        title = lines[0][:200]
        company, location = _split_company_location(lines[1]) if len(lines) > 1 else (None, None)
        if location is None and len(lines) > 2:
            location = lines[2]
        city, state = _city_state(location)
        text = "\n".join(lines)
        jobs.append(
            JobPosting(
                source=source,
                external_id=external_id,
                title=title,
                url=entry["url"],
                company=company,
                description=text,
                city=city,
                state=state,
                workplace_type=_workplace(text),
                published_at=received,
                skills=extract_skills(text),
            )
        )
    return jobs


def alert_source(sender_domain: str) -> str | None:
    for domain, source in ALERT_DOMAINS.items():
        if sender_domain == domain or sender_domain.endswith("." + domain):
            return source
    return None


def _body(msg: EmailMessage) -> tuple[str, str]:
    """(html, texto) do e-mail."""
    html_part = msg.get_body(preferencelist=("html",))
    text_part = msg.get_body(preferencelist=("plain",))
    html = html_part.get_content() if html_part else ""
    text = text_part.get_content() if text_part else clean_text(html)
    return html, text


def handle_message(
    db: Database, settings: Settings, msg: EmailMessage, stats: dict[str, Any]
) -> str:
    """Processa um e-mail e devolve o resultado (para registro)."""
    from ..pipeline import store_job  # import tardio: pipeline importa os coletores

    name, address = parseaddr(msg.get("From", ""))
    domain = address.rsplit("@", 1)[-1].lower()
    subject = str(msg.get("Subject", ""))
    try:
        received = parsedate_to_datetime(msg["Date"]).astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        received = None
    html, text = _body(msg)

    source = alert_source(domain)
    if source:
        jobs = parse_alert(html, source, received) if html else []
        for job in jobs:
            store_job(db, settings, job, stats)
        return f"alert:{source}:{len(jobs)}"

    updated = apply_response(
        db,
        sender=f"{name} {domain}",
        subject=subject,
        body=text,
        received=received[:10] if received else None,
    )
    if updated:
        return f"response:{updated['status']}:{updated['id']}"
    return "ignored"


class Mailbox(Protocol):
    def select(self, mailbox: str = ..., readonly: bool = ...) -> Any: ...
    def search(self, charset: str | None, *criteria: str) -> Any: ...
    def fetch(self, message_set: str, message_parts: str) -> Any: ...
    def logout(self) -> Any: ...


def connect(settings: Settings) -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, timeout=30)
    conn.login(settings.imap_user, settings.imap_password)
    return conn


def _imap_date(day: date) -> str:
    return f"{day.day:02d}-{_MONTHS[day.month - 1]}-{day.year}"


def iter_messages(mailbox: Mailbox, folder: str, days: int) -> Iterator[tuple[str, bytes]]:
    mailbox.select(folder, readonly=True)
    since = _imap_date(datetime.now(UTC).date() - timedelta(days=days))
    _, data = mailbox.search(None, "SINCE", since)
    for num in (data[0] or b"").split():
        msg_num = num.decode() if isinstance(num, bytes) else str(num)
        _, parts = mailbox.fetch(msg_num, "(BODY.PEEK[])")
        raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
        if raw:
            yield msg_num, raw


def process_mailbox(
    db: Database,
    settings: Settings,
    stats: dict[str, Any],
    mailbox: Mailbox | None = None,
) -> dict[str, int]:
    """Lê os e-mails recentes uma única vez cada. Erros viram ``stats['errors']``."""
    summary = {"emails": 0, "alerts": 0, "responses": 0}
    own_connection = mailbox is None
    try:
        mailbox = mailbox or connect(settings)
    except (OSError, imaplib.IMAP4.error) as exc:
        stats["errors"].append(f"e-mail: falha ao conectar ({exc})")
        return summary
    try:
        for _, raw in iter_messages(mailbox, settings.imap_folder, settings.imap_days):
            msg = message_from_bytes(raw, policy=policy.default)
            message_id = (msg.get("Message-ID") or "").strip() or hashlib.sha1(raw).hexdigest()
            if db.email_processed(message_id):
                continue
            outcome = handle_message(db, settings, msg, stats)
            db.mark_email_processed(message_id, outcome)
            summary["emails"] += 1
            if outcome.startswith("alert:"):
                summary["alerts"] += 1
            elif outcome.startswith("response:"):
                summary["responses"] += 1
    except (OSError, imaplib.IMAP4.error) as exc:
        stats["errors"].append(f"e-mail: {exc}")
    finally:
        if own_connection:
            with contextlib.suppress(OSError, imaplib.IMAP4.error):
                mailbox.logout()
    log.info("E-mails processados: %s", summary)
    return summary
