"""Linha de comando: ``searchjob serve | collect | analyze | report | cycle``."""

from __future__ import annotations

import argparse
import json
import logging

from .analyzer import analyze_pending
from .config import get_settings
from .db import Database
from .pipeline import build_llm, collect, run_cycle
from .report import write_daily_report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="searchjob", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="logs detalhados")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="inicia a API e o agendador")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("collect", help="coleta vagas agora")
    sub.add_parser("analyze", help="analisa vagas pendentes com a IA")
    sub.add_parser("cycle", help="coleta e analisa")
    sub.add_parser("report", help="gera o relatório diário em HTML")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = get_settings()
    if args.command == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return

    db = Database(settings.database_path)
    if args.command == "collect":
        result = collect(db, settings)
        db.save_run(result)
    elif args.command == "analyze":
        result = {"analyzed": analyze_pending(db, build_llm(settings), settings.load_profile(),
                                              limit=settings.analyze_batch_size)}
    elif args.command == "cycle":
        result = run_cycle(db, settings, build_llm(settings))
    else:
        path, context = write_daily_report(db, settings)
        result = {"report": str(path), "jobs": len(context["jobs"])}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
