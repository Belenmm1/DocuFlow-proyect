"""
app/main.py
Entrypoint FastAPI con lifespan para inicialización de tablas y verificación
de Redis al arrancar (Mejora 2.1).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.database import create_tables
from app.utils.logger import get_logger
from app.api.v1.routes import documents, reports
from app.api.v1.routes import auth
from app.core.middleware import RateLimitUserMiddleware
from app.core.security_headers import SecurityHeadersMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup y shutdown de la aplicación."""
    # ── Startup ────────────────────────────────────────────────────────────
    logger.info("Iniciando %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Crear tablas si no existen
    create_tables()
    logger.info("Tablas verificadas/creadas")

    # Verificar conectividad con Redis
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        logger.info("Redis conectado | url=%s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis no disponible | error=%s | las tareas Celery no funcionarán", exc)

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────
    logger.info("Cerrando aplicación")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Sistema de procesamiento inteligente de documentos",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middlewares ────────────────────────────────────────────────────────────
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitUserMiddleware)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")


@app.get("/health", tags=["infra"])
async def health():
    """Health check básico. Mejora 7.3 lo expandirá con checks de DB, Redis, OpenAI."""
    return {"status": "ok", "version": settings.APP_VERSION}