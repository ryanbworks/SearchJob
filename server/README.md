# SearchJob — servidor

API (FastAPI), coletor de vagas, análise com IA local e relatório diário.
Visão geral do projeto no [README principal](../README.md) e deploy em
[docs/deploy-proxmox.md](../docs/deploy-proxmox.md).

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # ajuste SJ_API_KEY e a IA
cp data/profile.example.md data/profile.md

searchjob collect                  # coleta vagas agora
searchjob analyze                  # dá nota às vagas com a IA
searchjob email                    # lê alertas de vaga e respostas (IMAP)
searchjob report                   # gera data/reports/AAAA-MM-DD.html
searchjob serve                    # API em http://localhost:8000/docs
```

## Testes e lint

```bash
pytest
ruff check .
```

## Endpoints principais

| Método | Rota | Uso |
|---|---|---|
| GET | `/health` | status (público) |
| GET | `/api/jobs?status=new&min_score=6` | lista vagas ranqueadas |
| GET | `/api/jobs/match?url=...` | encontra a vaga da aba atual (extensão) |
| PATCH | `/api/jobs/{id}` | atualiza status: `applied`, `interview`, `rejected`... |
| POST | `/api/answer` | gera resposta para pergunta aberta com a IA |
| GET | `/painel` | painel web (a página pede a chave e busca `/api/dashboard`) |
| GET | `/api/dashboard?days=30` | dados do painel: lacunas, repetições, funil, tendências |
| GET | `/entrevista?job=ID` | página de preparação para entrevista |
| GET | `/curriculo?job=ID` | página do currículo adaptado (folha A4, "Salvar PDF") |
| POST | `/api/jobs/{id}/interview` | perguntas, casos práticos e pitch (`?regenerate=true` refaz) |
| POST | `/api/interview/feedback` | avalia uma resposta de treino |
| POST | `/api/jobs/{id}/resume` | currículo adaptado + contato e formação do perfil |
| GET | `/configuracoes` | aba de configurações (verificação, preferências, perfil) |
| GET | `/api/config` | configuração em vigor e verificações (sem segredos) |
| PUT / DELETE | `/api/preferences` | salva preferências (`data/preferences.json`) / volta ao `.env` |
| GET / PUT | `/api/profile` | lê / grava o `data/profile.md` |
| GET | `/api/insights?days=30` | requisitos mais pedidos e funil de candidaturas |
| POST | `/api/collect` | dispara coleta + análise em segundo plano |
| GET | `/report` | relatório HTML do dia |

Todas as rotas `/api/*` e `/report` exigem a chave em `X-API-Key` (ou `?key=` no relatório).
