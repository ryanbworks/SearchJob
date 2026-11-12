FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . \
    && useradd --create-home --uid 1000 searchjob \
    && mkdir -p /app/data && chown searchjob:searchjob /app/data

COPY --chown=searchjob:searchjob data/profile.example.md /app/data/profile.example.md

USER searchjob
EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["searchjob", "serve", "--host", "0.0.0.0", "--port", "8000"]
