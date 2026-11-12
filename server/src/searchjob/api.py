"""API REST consumida pela extensão do Firefox e pelo relatório."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, TypeVar

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .analyzer import answer_question
from .config import Settings, get_settings
from .dashboard import build_dashboard
from .db import Database
from .interview import answer_feedback, generate_prep
from .llm import LLMClient, LLMError, LLMUnavailable
from .models import JobStatus
from .pipeline import build_llm, run_cycle
from .preferences import (
    MAX_PROFILE_CHARS,
    Preferences,
    apply_preferences,
    load_preferences,
    read_profile_raw,
    reset_preferences,
    save_preferences,
    write_profile,
)
from .report import build_context, render_report
from .resume import generate_resume, profile_section
from .settings_view import build_config_view

log = logging.getLogger(__name__)
T = TypeVar("T")

STATIC_DIR = Path(__file__).parent / "static"


class JobUpdate(BaseModel):
    status: JobStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)


class AnswerRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    job_id: int | None = None
    page_context: str = Field(default="", max_length=20000)
    max_chars: int | None = Field(default=None, ge=50, le=5000)


class AnswerResponse(BaseModel):
    answer: str


class ProfileUpdate(BaseModel):
    markdown: str = Field(min_length=20, max_length=MAX_PROFILE_CHARS)


class FeedbackRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    answer: str = Field(min_length=3, max_length=6000)
    job_id: int | None = None


def call_llm(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Executa uma chamada à IA convertendo falhas em respostas HTTP claras."""
    try:
        return func(*args, **kwargs)
    except LLMUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


def create_app(
    settings: Settings | None = None,
    db: Database | None = None,
    llm: LLMClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    # Preferências salvas pelo painel sobrepõem o .env.
    apply_preferences(settings, load_preferences(settings))
    db = db or Database(settings.database_path)
    llm = llm or build_llm(settings)
    runtime: dict[str, Any] = {"scheduler": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.scheduler_enabled:
            from .scheduler import start_scheduler

            runtime["scheduler"] = start_scheduler(settings, db, llm)
        if not settings.api_key:
            log.warning("SJ_API_KEY vazio: a API está sem autenticação!")
        yield
        if runtime["scheduler"]:
            runtime["scheduler"].shutdown(wait=False)

    def refresh_runtime() -> None:
        """Leva as preferências novas para a IA e o agendador em execução."""
        llm.base_url = settings.llm_base_url.rstrip("/")
        llm.model = settings.llm_model
        if runtime["scheduler"]:
            from .scheduler import apply_schedule

            apply_schedule(runtime["scheduler"], settings)

    app = FastAPI(
        title="SearchJob API",
        version=__version__,
        description="Coleta e análise de vagas de suporte técnico com IA local.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(moz|chrome)-extension://.*$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def require_key(request: Request) -> None:
        if not settings.api_key:
            return
        provided = request.headers.get("X-API-Key") or request.query_params.get("key") or ""
        if not secrets.compare_digest(provided.encode(), settings.api_key.encode()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave de API inválida")

    auth = [Depends(require_key)]

    def job_or_404(job_id: int) -> dict[str, Any]:
        job = db.get_job(job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaga não encontrada")
        return job

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/painel")

    @app.get("/painel", include_in_schema=False)
    def painel() -> FileResponse:
        # A página não contém dados: ela busca /api/dashboard com a chave do usuário.
        return FileResponse(STATIC_DIR / "painel.html")

    @app.get("/entrevista", include_in_schema=False)
    def entrevista() -> FileResponse:
        return FileResponse(STATIC_DIR / "entrevista.html")

    @app.get("/curriculo", include_in_schema=False)
    def curriculo() -> FileResponse:
        return FileResponse(STATIC_DIR / "curriculo.html")

    @app.get("/configuracoes", include_in_schema=False)
    def configuracoes() -> FileResponse:
        return FileResponse(STATIC_DIR / "configuracoes.html")

    @app.get("/api/config", dependencies=auth)
    def config_view() -> dict[str, Any]:
        """Configuração em vigor, verificações e perfil. Nunca devolve senhas ou chaves."""
        return build_config_view(settings, db, llm)

    @app.put("/api/preferences", dependencies=auth)
    def update_preferences(body: Preferences) -> dict[str, Any]:
        """Salva as preferências editáveis e aplica na hora (sem reiniciar)."""
        save_preferences(settings, body)
        refresh_runtime()
        return build_config_view(settings, db, llm)

    @app.delete("/api/preferences", dependencies=auth)
    def clear_preferences() -> dict[str, Any]:
        """Volta para os valores do .env."""
        reset_preferences(settings)
        refresh_runtime()
        return build_config_view(settings, db, llm)

    @app.get("/api/profile", dependencies=auth)
    def get_profile() -> dict[str, Any]:
        return {
            "markdown": read_profile_raw(settings),
            "using_example": not settings.profile_path.exists(),
        }

    @app.put("/api/profile", dependencies=auth)
    def put_profile(body: ProfileUpdate) -> dict[str, Any]:
        """Grava o data/profile.md (perfil + bloco de contato)."""
        write_profile(settings, body.markdown)
        return build_config_view(settings, db, llm)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "llm_model": settings.llm_model}

    @app.get("/api/llm/status", dependencies=auth)
    def llm_status() -> dict[str, Any]:
        return {"available": llm.is_available(), "base_url": llm.base_url, "model": llm.model}

    @app.get("/api/jobs", dependencies=auth)
    def list_jobs(
        status_: Annotated[JobStatus | None, Query(alias="status")] = None,
        min_score: Annotated[int | None, Query(ge=0, le=10)] = None,
        q: Annotated[str | None, Query(max_length=100)] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[dict[str, Any]]:
        return db.list_jobs(
            status=status_, min_score=min_score, query=q, limit=limit, offset=offset
        )

    @app.get("/api/jobs/match", dependencies=auth)
    def match_job(url: Annotated[str, Query(min_length=8, max_length=2000)]) -> dict[str, Any]:
        job = db.find_by_url(url)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma vaga com essa URL")
        return job

    @app.get("/api/jobs/{job_id}", dependencies=auth)
    def get_job(job_id: int) -> dict[str, Any]:
        return job_or_404(job_id)

    @app.patch("/api/jobs/{job_id}", dependencies=auth)
    def update_job(job_id: int, body: JobUpdate) -> dict[str, Any]:
        job_or_404(job_id)
        return db.update_job(job_id, status=body.status, notes=body.notes)

    @app.post("/api/answer", dependencies=auth)
    def answer(body: AnswerRequest) -> AnswerResponse:
        job = job_or_404(body.job_id) if body.job_id is not None else None
        text = call_llm(
            answer_question,
            llm,
            settings.load_profile(),
            body.question,
            job=job,
            page_context=body.page_context,
            max_chars=body.max_chars,
        )
        return AnswerResponse(answer=text)

    @app.post("/api/jobs/{job_id}/interview", dependencies=auth)
    def interview_prep(job_id: int, regenerate: bool = False) -> dict[str, Any]:
        """Perguntas prováveis, casos práticos e pitch. Fica em cache por vaga."""
        job = job_or_404(job_id)
        if not regenerate and (cached := db.get_document(job_id, "interview")):
            return cached
        prep = call_llm(generate_prep, llm, settings.load_profile(), job)
        return db.save_document(job_id, "interview", prep)

    @app.post("/api/jobs/{job_id}/resume", dependencies=auth)
    def resume(job_id: int, regenerate: bool = False) -> dict[str, Any]:
        """Currículo adaptado à vaga (cache por vaga) + contato e formação do perfil."""
        job = job_or_404(job_id)
        profile = settings.load_profile()
        doc = None if regenerate else db.get_document(job_id, "resume")
        if doc is None:
            doc = db.save_document(
                job_id, "resume", call_llm(generate_resume, llm, profile, job)
            )
        return {
            **doc,
            "contact": settings.load_profile_contact(),
            "education": profile_section(profile, "forma"),
            "languages": profile_section(profile, "idioma"),
            "job": {"id": job["id"], "title": job["title"], "company": job.get("company")},
        }

    @app.post("/api/interview/feedback", dependencies=auth)
    def interview_feedback(body: FeedbackRequest) -> dict[str, Any]:
        job = job_or_404(body.job_id) if body.job_id is not None else None
        return call_llm(
            answer_feedback, llm, settings.load_profile(), body.question, body.answer, job=job
        )

    @app.get("/api/insights", dependencies=auth)
    def insights(days: Annotated[int, Query(ge=1, le=365)] = 30) -> dict[str, Any]:
        return db.insights(days=days)

    @app.get("/api/dashboard", dependencies=auth)
    def dashboard(days: Annotated[int, Query(ge=1, le=365)] = 30) -> dict[str, Any]:
        return build_dashboard(db, settings.load_profile(), days=days)

    @app.post("/api/collect", dependencies=auth, status_code=status.HTTP_202_ACCEPTED)
    def trigger_collect(tasks: BackgroundTasks) -> dict[str, str]:
        tasks.add_task(run_cycle, db, settings, llm)
        return {"status": "coleta iniciada"}

    @app.get("/report", dependencies=auth, response_class=HTMLResponse)
    def report(hours: Annotated[int, Query(ge=1, le=24 * 30)] = 24) -> str:
        return render_report(build_context(db, since_hours=hours, tz=settings.timezone))

    return app
