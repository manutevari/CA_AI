# TaxPilot AI — AI-powered Indian ITR filing automation (monorepo scaffold)

This repository contains a **production-oriented scaffold** for **TaxPilot AI**: a modular full-stack platform you can extend into a regulated, production-grade filing product (legal review, CBDT schema certification, SOC2, DPDP program, and so on).

## What is included

- **Frontend:** Next.js 15 (App Router), TypeScript, TailwindCSS, Framer Motion, minimal shadcn-style `Button`, dashboard + wizard shells.
- **Streamlit filing lab:** root `app.py` includes official Income Tax Department filing links, ITR form recommendation, online filing entry points, and official download utility links.
- **Dynamic agent providers:** Streamlit can route official-source search to Tavily and review reasoning to DeepSeek, Groq, or Hugging Face based on configured secrets.
- **Backend:** FastAPI, SQLAlchemy models for core tables, JWT auth, encrypted local document storage (Fernet), OCR/PDF extraction + optional OpenAI/LangChain structured extraction, tax/regime/validation/deduction services, agentic filing readiness runs, CA review checkpoints, Celery worker hook, OpenAPI at `/docs`.
- **Agentic workflow:** `/api/v1/agent/filings/{filing_id}/run` creates an auditable filing assessment with deterministic graph steps, confidence scoring, correction proposals, AIS/26AS mismatch checks, CBDT schema blockers, and human-in-the-loop review tasks.
- **Data:** PostgreSQL schema via `Base.metadata.create_all` (swap to Alembic for real migrations).
- **Compliance artifacts:** `docs/DPDP_COMPLIANCE.md` starts the DPDP consent, retention, erasure, and DPIA artifact set.
- **Infra:** `docker-compose.yml` (Postgres, Redis, API, worker, web), GitHub Actions CI, `.env.example`.

## Streamlit Community Cloud (hosted UI)

The **Streamlit** filing lab runs from the **repository root** (not from `backend/`).

1. Push this repo to GitHub.
2. [share.streamlit.io](https://share.streamlit.io) → **New app** → select repo/branch.
3. **Main file path:** `app.py`
4. Cloud installs **root** `requirements.txt` and **`packages.txt`** (Tesseract for OCR).

Details, troubleshooting, and file list: **`DEPLOY.txt`**.

After deploy, your preview URL is shown in the Streamlit dashboard (typically `https://<app-name>.streamlit.app`).

### Optional Streamlit secrets for dynamic agents

Set these in **Streamlit Community Cloud -> App -> Settings -> Secrets**. The app chooses providers dynamically and never displays secret values.

```toml
TAVILY_KEY = ""
tavily_key = ""
HF_API_KEY = ""
HF_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
HF_CHAT_ENDPOINT = ""
DEEPSEEK_API_KEY = ""
DEEPSEEK_MODEL = "deepseek-chat"
GROQ_API_KEY = ""
GROQ_MODEL = "llama-3.1-8b-instant"
MISTRAL_API_KEY = ""
MISTRAL_MODEL = "mistral-small-latest"
```

Provider selection:

- Tavily: official Income Tax source search.
- DeepSeek: first-choice deeper tax review notes when configured.
- Groq: low-latency review notes when DeepSeek is absent.
- Mistral: review notes when DeepSeek/Groq are absent.
- Hugging Face: fallback model provider, with `HF_CHAT_ENDPOINT` supported for dedicated endpoints.
- Deterministic rules: always available when no model/search key is configured.

## Quick start (Docker)

```bash
cp .env.example .env   # optional for local non-docker tweaks
docker compose up --build
```

- Web: `http://localhost:3000`
- API + Swagger: `http://localhost:8000/docs`

**Important:** API and worker must share the same `SECRET_KEY` / `ENCRYPTION_KEY` material. `docker-compose.yml` sets matching dev secrets; for production use a secrets manager.

## API smoke test

```bash
curl -s http://localhost:8000/api/v1/health
```

Register + auth:

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register   -H "Content-Type: application/json"   -d "{\"email\":\"you@example.com\",\"password\":\"longpassword\",\"full_name\":\"You\"}"
```

Use returned `access_token` as `Authorization: Bearer ...` for protected routes (`/filings`, `/documents/...`, `/tax/compute`, etc.).

Run an agent readiness assessment:

```bash
curl -s -X POST http://localhost:8000/api/v1/agent/filings/<filing_id>/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d "{\"objective\":\"Assess filing readiness with reconciliation and compliance gates\"}"
```

Review checkpoints are available at:

```bash
curl -s http://localhost:8000/api/v1/agent/filings/<filing_id>/review-checkpoints \
  -H "Authorization: Bearer <access_token>"
```

CA/admin bulk review queue:

```bash
curl -s http://localhost:8000/api/v1/agent/review-checkpoints?status_filter=pending \
  -H "Authorization: Bearer <access_token>"
```

### Promote a user to admin (SQL)

```bash
docker compose exec postgres psql -U taxpilot -d taxpilot -c "UPDATE users SET role='admin' WHERE email='you@example.com';"
```

## Legacy / Streamlit layer (repo root)

The Streamlit app (`app.py` + `tax_engine.py`, `form16_parser.py`, …) is the **Streamlit Cloud–deployable** surface. The CLI remains `python main.py <form16.pdf>`.

## Production gates still required

The repo now includes a first-pass agentic workflow, confidence scoring, review checkpoints, AIS/26AS comparison fields, and surcharge/marginal relief computation hooks. It still intentionally blocks production filing until these are completed and independently reviewed:

- Official CBDT JSON/XML schema generation and validator certification.
- Direct Income Tax portal filing integration with explicit taxpayer authorization.
- Production AIS/26AS/TRACES ingestion rather than user-supplied values.
- Alembic migrations, production object storage with KMS, and formal DPDP DPIA/retention artifacts.
- Full CA workspace with client assignment, delegation, maker-checker controls, and bulk review queues.
- Continuous legal rule-pack updates from official sources, including Income Tax Department slab pages and CBDT validation rule PDFs.

See `docs/ARCHITECTURE.md` for diagrams and extension points.
