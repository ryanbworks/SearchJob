"""API REST consumida pela extensão do Firefox e pelo relatório."""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

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
from .llm import LLMClient, LLMError, LLMUnavailable
from .models import JobStatus
from .pipeline import build_llm, run_cycle
from .report import build_context, render_report

log = logging.getLogger(__name__)

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


def create_app(
    settings: Settings | None = None,
    db: Database | None = None,
    llm: LLMClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    db = db or Database(settings.database_path)
    llm = llm or build_llm(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if settings.scheduler_enabled:
            from .scheduler import start_scheduler

            scheduler = start_scheduler(settings, db, llm)
        if not settings.api_key:
            log.warning("SJ_API_KEY vazio: a API está sem autenticação!")
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

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
        try:
            text = answer_question(
                llm,
                settings.load_profile(),
                body.question,
                job=job,
                page_context=body.page_context,
                max_chars=body.max_chars,
            )
        except LLMUnavailable as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        except LLMError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
        return AnswerResponse(answer=text)

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
