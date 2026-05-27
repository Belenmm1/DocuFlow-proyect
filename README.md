<div align="center">

#  DocuFlow

### Intelligent Document Processing System

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)
[![CI/CD](https://img.shields.io/github/actions/workflow/status/Belenmm1/DocuFlow-proyect/ci.yml?style=flat-square&label=CI)](https://github.com/Belenmm1/DocuFlow-proyect/actions)

DocuFlow is a high-performance REST API that automates the extraction, analysis, and synthesis of data from unstructured documents. It combines FastAPI for low-latency requests, Celery for background processing, and LLMs to transform raw files into structured, actionable intelligence.

</div>

---

## Features

- **Multi-format support** — Ingests PDF, DOCX, and XLSX files
- **Async processing** — Non-blocking pipeline via Celery + Redis
- **AI analysis** — LangChain + GPT-4o-mini for entity extraction, classification, and summarization
- **RAG Chat** — Ask questions directly to any uploaded document
- **Multi-LLM** — Switchable between OpenAI, Anthropic, Google Gemini, and Ollama
- **Reports** — Export results to PDF (ReportLab) and Excel (XlsxWriter)
- **Integrations** — Google Drive and Dropbox connectors
- **Webhooks** — Configurable event dispatching on document processing completion
- **Billing** — Stripe-based subscription plans (Free / Pro / Enterprise)
- **API Keys** — Self-managed keys per user for programmatic access
- **Observability** — Sentry error tracking + structured logging
- **Frontend** — Full Next.js 14 dashboard with NextAuth.js authentication

---

##  Architecture

```
Client
  │
  ▼
Next.js 14 Frontend (NextAuth.js)
  │
  ▼
FastAPI  ──► Redis (cache + broker) ──► Celery Worker
  │                                          │
  ▼                                          ▼
PostgreSQL                            LangChain / LLM
                                       (GPT-4o-mini, Claude, Gemini, Ollama)
```

### Document processing flow

1. **Upload** — `POST /api/v1/documents/upload` → validation + `202 Accepted` + task ID
2. **Queue** — Document record created as `pending`; task dispatched to Celery via Redis
3. **Extract** — Worker detects MIME type; extracts text with `pdfplumber`, `python-docx`, or `pandas`
4. **Analyze** — LangChain pipeline runs entity extraction, classification, and summarization
5. **Persist** — Results saved to PostgreSQL and cached in Redis
6. **Poll** — `GET /api/v1/documents/{id}/status` until `completed`

---

##  Tech Stack

| Layer | Technology |
|---|---|
| **API** | FastAPI, Uvicorn, Pydantic |
| **Database** | PostgreSQL 16, SQLAlchemy ORM, Alembic |
| **Queue** | Celery, Redis |
| **AI** | LangChain, OpenAI GPT-4o-mini, Anthropic Claude, Google Gemini, Ollama |
| **Extraction** | pdfplumber, python-docx, openpyxl, pandas |
| **Reports** | ReportLab, XlsxWriter |
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, NextAuth.js |
| **UI libs** | Recharts, Lucide React, React Dropzone, React Hot Toast |
| **Billing** | Stripe |
| **Observability** | Sentry, structured logging |
| **Infra** | Docker, Docker Compose, GitHub Actions CI/CD |
| **Dashboard** | Streamlit (alternative visual interface) |

---

## 📁 Project Structure

```
docuflow/
├── app/
│   ├── api/v1/
│   │   ├── routes/          # auth, documents, chat, reports, billing,
│   │   │                    # integrations, api_keys, admin, webhooks, health
│   │   └── schemas/         # Pydantic request/response models
│   ├── core/                # security, rate limiting, middleware,
│   │                        # plan limits, cache, observability
│   ├── models/              # SQLAlchemy ORM (user, document, chat,
│   │                        # subscription, api_key, webhook, backup_log)
│   ├── schemas/             # shared Pydantic schemas
│   ├── services/            # extractor, ai_analyzer, rag_service,
│   │                        # report_generator, stripe_service,
│   │                        # email_service, webhook_dispatcher
│   │   └── integrations/    # Google Drive, Dropbox
│   ├── utils/               # file_handler, logger, audit_logger
│   └── workers/             # Celery app, tasks, scheduled_tasks (Beat)
├── frontend/                # Next.js 14 app
│   ├── app/                 # pages: dashboard, documents, login, register
│   ├── components/          # AppShell, ChatInterface, DocumentsTable,
│   │                        # Dropzone, StatsCards, StatusBadge
│   └── lib/                 # api client, theme
├── alembic/versions/        # DB migrations (0001 → 0008)
├── streamlit_app/           # Streamlit dashboard
├── tests/                   # pytest test suite
├── scripts/                 # backup.sh, migrate.sh, restore.sh, docker.sh
├── docker-compose.yml       # Full stack: api, worker, beat, redis, db, frontend
├── Dockerfile.api
├── Dockerfile.frontend
├── requirements.txt
└── .env.example
```

---

##  Quick Start (Docker)

### Prerequisites
- Docker + Docker Compose
- OpenAI API key (or Anthropic / Google / Ollama)

### 1. Clone and configure

```bash
git clone https://github.com/Belenmm1/DocuFlow-proyect.git
cd DocuFlow-proyect
cp .env.example .env
```

Edit `.env` and fill in the required values:

```env
SECRET_KEY=         # openssl rand -hex 32
POSTGRES_PASSWORD=  # your db password
OPENAI_API_KEY=     # sk-...
NEXTAUTH_SECRET=    # openssl rand -hex 32
```

### 2. Start all services

```bash
docker compose up -d
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| API docs (ReDoc) | http://localhost:8000/redoc |

### 3. Run migrations

```bash
docker compose exec api alembic upgrade head
```

---

##  Local Development

### Backend

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
.venv\Scripts\activate          # Windows

pip install -r requirements-dev.txt

# Start API
uvicorn main:app --reload

# Start Celery worker (separate terminal)
celery -A app.workers.celery_app worker --loglevel=info -Q documents

# Start Celery Beat scheduler (separate terminal)
celery -A app.workers.celery_app beat --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Streamlit dashboard (alternative)

```bash
streamlit run streamlit_app/app.py
```

---

##  API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register new user |
| `POST` | `/api/v1/auth/login` | Login (returns JWT) |
| `POST` | `/api/v1/documents/upload` | Upload document for processing |
| `GET` | `/api/v1/documents` | List documents (paginated, filterable, full-text search) |
| `GET` | `/api/v1/documents/{id}` | Get document details + AI analysis |
| `GET` | `/api/v1/documents/{id}/status` | Poll processing status |
| `DELETE` | `/api/v1/documents/{id}` | Delete document |
| `POST` | `/api/v1/documents/{id}/chat` | Chat with document (RAG) |
| `GET` | `/api/v1/documents/{id}/chat` | List conversations |
| `GET` | `/api/v1/reports` | Generate report (PDF or Excel) |
| `GET` | `/api/v1/billing/plans` | View available plans |
| `POST` | `/api/v1/billing/upgrade` | Upgrade subscription via Stripe |
| `GET` | `/api/v1/integrations/google` | Connect Google Drive |
| `GET` | `/api/v1/integrations/dropbox` | Connect Dropbox |
| `GET` | `/api/v1/health` | Health check |

Full interactive docs at `/docs` (Swagger UI) once the server is running.

---

## 📊 Subscription Plans

| Feature | Free | Pro | Enterprise |
|---|---|---|---|
| Max file size | 5 MB | 20 MB | 100 MB |
| Documents / month | 10 | 200 | Unlimited |
| API keys | — | 5 | 50 |
| PDF export | ✗ | ✓ | ✓ |
| Excel export | ✓ | ✓ | ✓ |
| RAG Chat | ✗ | ✓ | ✓ |
| Webhooks | ✗ | ✓ | ✓ |
| Integrations | ✗ | ✓ | ✓ |
| Rate limit | 10 req/min | 60 req/min | 1000 req/min |

---

##  Tests

```bash
# Run test suite
pytest tests/ -v

# With coverage report
pytest tests/ --cov=app --cov-report=html
```

CI requires ≥ 70% coverage to pass.

---

## AI Analysis Output

Every processed document returns a structured JSON object:

```json
{
  "summary": "Executive summary of the document",
  "classification": "Invoice | Contract | Report | ...",
  "key_points": ["..."],
  "entities": {
    "people": [],
    "organizations": [],
    "dates": [],
    "amounts": []
  },
  "sentiment": "positive | neutral | negative",
  "language": "en | es | ..."
}
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the required values. Key variables:

```env
# App
SECRET_KEY=           # Required — openssl rand -hex 32
APP_ENV=production

# Database
POSTGRES_USER=docuflow
POSTGRES_PASSWORD=    # Required
POSTGRES_DB=docuflow

# LLM (choose one provider)
LLM_PROVIDER=openai   # openai | anthropic | gemini | ollama
OPENAI_API_KEY=       # Required for OpenAI
ANTHROPIC_API_KEY=    # Required for Anthropic
GOOGLE_API_KEY=       # Required for Gemini

# Frontend
NEXTAUTH_SECRET=      # Required — openssl rand -hex 32
NEXT_PUBLIC_API_URL=http://localhost:8000

# Billing (optional)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
```

See `.env.example` for the full list.

---

## 📜 License

MIT © [Belenmm1](https://github.com/Belenmm1)
