# DocuFlow — Guía de Deploy en Railway

## Arquitectura en Railway

DocuFlow tiene 5 servicios en Railway:
| Servicio | Qué hace | Dockerfile |
|---|---|---|
| **api** | FastAPI + Alembic migrations | `Dockerfile.api` |
| **worker** | Celery (procesa documentos) | `Dockerfile.api` |
| **frontend** | Next.js 14 | `Dockerfile.frontend` |
| **PostgreSQL** | Plugin de Railway | — |
| **Redis** | Plugin de Railway | — |

---

## Paso 1 — Subir el código a GitHub

```bash
git init
git add .
git commit -m "feat: initial deploy"
git remote add origin https://github.com/TU_USUARIO/docuflow.git
git push -u origin main
```

---

## Paso 2 — Crear proyecto en Railway

1. Ir a [railway.app](https://railway.app) → **New Project**
2. **Deploy from GitHub repo** → seleccionar el repo

Railway crea automáticamente el primer servicio. Lo vamos a usar como **api**.

---

## Paso 3 — Agregar plugins

En el dashboard, dentro del proyecto:
1. **+ New** → **Database** → **PostgreSQL** ✓
2. **+ New** → **Database** → **Redis** ✓

---

## Paso 4 — Configurar el servicio API

Clic en el servicio que creó Railway → **Settings**:

- **Root Directory**: `/` (dejar vacío)
- **Build → Dockerfile Path**: `Dockerfile.api`
- **Deploy → Start Command**:
  ```
  alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
  ```

Ir a **Variables** → **Raw Editor** y pegar:
```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
APP_ENV=production
DEBUG=false
SECRET_KEY=GENERAR_CON_openssl_rand_-hex_32
CORS_ORIGINS=https://TU_FRONTEND.up.railway.app
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
ACCESS_TOKEN_EXPIRE_MINUTES=60
ALGORITHM=HS256
CELERY_CONCURRENCY=2
UPLOADS_DIR=/app/uploads
VECTOR_STORE_DIR=/app/vector_stores
TIMEZONE=America/Argentina/Buenos_Aires
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
SENTRY_DSN=
```

---

## Paso 5 — Crear servicio Worker

1. **+ New** → **GitHub Repo** → mismo repo
2. **Settings**:
   - **Root Directory**: `/` (vacío)
   - **Build → Dockerfile Path**: `Dockerfile.api`
   - **Deploy → Start Command**:
     ```
     celery -A app.workers.celery_app worker --loglevel=info --concurrency=2 -Q documents
     ```
3. **Variables** → copiar las mismas variables que el API (sin CORS_ORIGINS)

---

## Paso 6 — Crear servicio Frontend

1. **+ New** → **GitHub Repo** → mismo repo
2. **Settings**:
   - **Root Directory**: `/` (vacío)
   - **Build → Dockerfile Path**: `Dockerfile.frontend`
   - **Deploy → Start Command**: `node server.js`
3. **Variables**:
   ```env
   NEXT_PUBLIC_API_URL=https://TU_API.up.railway.app
   NEXTAUTH_URL=https://TU_FRONTEND.up.railway.app
   NEXTAUTH_SECRET=GENERAR_CON_openssl_rand_-hex_32
   ```

> ⚠️ **Importante**: `NEXT_PUBLIC_API_URL` se incrusta en el bundle durante el build.
> Si cambiás la URL del API, hay que re-deployar el frontend.

---

## Paso 7 — Deploy automático con GitHub Actions

1. Railway → **Account Settings** → **Tokens** → **Create Token** → copiar

2. GitHub → repo → **Settings** → **Secrets and variables** → **Actions**:
   - `RAILWAY_TOKEN` → token de Railway
   - `SECRET_KEY` → `openssl rand -hex 32`
   - `OPENAI_API_KEY` → tu key de OpenAI

3. Push a `main` → el workflow en `.github/workflows/ci.yml` corre automáticamente:
   ```
   lint → test → railway up
   ```

---

## Verificar el deploy

```bash
railway login
railway link   # vincular repo local al proyecto Railway

railway status
railway logs --service api
railway logs --service worker
```

Endpoints clave:
- `GET /api/v1/health` — health check del API
- `GET /docs` — Swagger UI
- `GET /api/v1/documents` — lista de documentos

---

## Troubleshooting

| Problema | Causa | Solución |
|---|---|---|
| Build falla "Cannot find package.json" | Dockerfile.frontend no encuentra frontend/ | Verificar Root Directory = `/` |
| API no conecta a DB | DATABASE_URL mal configurada | Usar `${{Postgres.DATABASE_URL}}` |
| Worker no procesa | REDIS_URL falta en worker | Copiar variables del API al worker |
| CORS error | CORS_ORIGINS no actualizado | Actualizar con URL exacta del frontend |
| Migraciones fallan | DB no inicializada | Railway inicializa PostgreSQL automáticamente |

---

## Generación de secrets

```bash
# SECRET_KEY
openssl rand -hex 32

# NEXTAUTH_SECRET  
openssl rand -base64 32
```
