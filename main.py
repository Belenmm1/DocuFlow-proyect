"""
main.py — 
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.database import create_tables
from app.utils.logger import get_logger
from app.api.v1.routes import documents, reports, auth
from app.api.v1.routes import chat
from app.api.v1.routes import integrations
from app.api.v1.routes import billing
from app.api.v1.routes import api_keys
from app.api.v1.routes import admin
from app.api.v1.routes import health as health_router      
from app.core.middleware import RateLimitUserMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.startup_checks import run_startup_checks
from app.core.observability import init_sentry, RequestTimingMiddleware  

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────
    logger.info("Iniciando %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Sentry: se inicializa lo antes posible para capturar errores de arranque
    init_sentry()                                          # ← Bloque 7.3

    run_startup_checks()
    create_tables()
    logger.info("Tablas verificadas/creadas")

    vector_dir = Path("./vector_stores")
    vector_dir.mkdir(exist_ok=True)

    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        logger.info("Redis conectado | url=%s", settings.REDIS_URL)
    except Exception as exc:
        logger.warning("Redis no disponible | error=%s", exc)

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────
    logger.info("Cerrando aplicación")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Sistema de procesamiento inteligente de documentos",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middlewares — el orden importa (se ejecutan de abajo hacia arriba) ─────────
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestTimingMiddleware)          
app.add_middleware(RateLimitUserMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(health_router.router,  prefix="/api/v1")   
app.include_router(auth.router,           prefix="/api/v1")
app.include_router(documents.router,      prefix="/api/v1")
app.include_router(reports.router,        prefix="/api/v1")
app.include_router(chat.router,           prefix="/api/v1")
app.include_router(integrations.router,   prefix="/api/v1")
app.include_router(billing.router,        prefix="/api/v1")
app.include_router(api_keys.router,       prefix="/api/v1")
app.include_router(admin.router,          prefix="/api/v1")
