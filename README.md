# TaxPilot AI — AI-powered Indian ITR filing automation (monorepo scaffold)

This repository contains a **production-oriented scaffold** for **TaxPilot AI**: a modular full-stack platform you can extend into a regulated, production-grade filing product (legal review, CBDT schema certification, SOC2, DPDP program, and so on).

## What is included

- **Frontend:** Next.js 15 (App Router), TypeScript, TailwindCSS, Framer Motion, minimal shadcn-style `Button`, dashboard + wizard shells.
- **Backend:** FastAPI, SQLAlchemy models for core tables, JWT auth, encrypted local document storage (Fernet), OCR/PDF extraction + optional OpenAI/LangChain structured extraction, tax/regime/validation/deduction services, Celery worker hook, OpenAPI at `/docs`.
- **Data:** PostgreSQL schema via `Base.metadata.create_all` (swap to Alembic for real migrations).
- **Infra:** `docker-compose.yml` (Postgres, Redis, API, worker, web), GitHub Actions CI, `.env.example`.

## Streamlit Community Cloud (hosted UI)

The **Streamlit** filing lab runs from the **repository root** (not from `backend/`).

1. Push this repo to GitHub.
2. [share.streamlit.io](https://share.streamlit.io) → **New app** → select repo/branch.
3. **Main file path:** `app.py`
4. Cloud installs **root** `requirements.txt` and **`packages.txt`** (Tesseract for OCR).

Details, troubleshooting, and file list: **`DEPLOY.txt`**.

After deploy, your preview URL is shown in the Streamlit dashboard (typically `https://<app-name>.streamlit.app`).

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

### Promote a user to admin (SQL)

```bash
docker compose exec postgres psql -U taxpilot -d taxpilot -c "UPDATE users SET role='admin' WHERE email='you@example.com';"
```

## Legacy / Streamlit layer (repo root)

The Streamlit app (`app.py` + `tax_engine.py`, `form16_parser.py`, …) is the **Streamlit Cloud–deployable** surface. The CLI remains `python main.py <form16.pdf>`.

## Roadmap (not yet fully implemented)

Official ITR XML schema generation, e-filing integration, AIS/26AS reconciliation engine, production S3 + KMS, WhatsApp provider, voice (ASR/TTS), CSC dashboards, bulk CA mode, full RAG ingestion of circulars, surcharge/marginal relief completeness, and DPDP DPIA artifacts.

See `docs/ARCHITECTURE.md` for diagrams and extension points.

## Compliance status (honest checklist)

| Area | Status |
|------|--------|
| Enterprise compliance | **Not yet** — policies, certifications, and org controls are not implemented as a finished program. |
| Production hardening | **Not yet** — defaults are suitable for demos; add threat modeling, DR, observability, and secrets management for real workloads. |
| Legal e-filing completeness | **Not yet** — not CBDT-certified output; users must not treat exports as filed returns. |

**Preview:** locally — Streamlit `http://localhost:8501`, web `http://localhost:3000`, API `http://localhost:8000/docs`. Hosted Streamlit URL comes from [Streamlit Cloud](https://share.streamlit.io) after you deploy (see `DEPLOY.txt`).
