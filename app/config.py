from typing import List, Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DocuFlow"
    APP_VERSION: str = "2.5.0"
    APP_ENV: str = "development"  # "development" | "production"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ──────────────────────────────────────────────────────────────────────────
    # Database — Bloque 2.4
    # ──────────────────────────────────────────────────────────────────────────
    # Para desarrollo local puede seguir siendo SQLite:
    #   DATABASE_URL=sqlite:///./docuflow.db
    # Para producción (Railway / Docker):
    #   DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/docuflow
    #
    # IMPORTANTE: el driver psycopg2 requiere `psycopg2-binary` en requirements.txt.
    # Si usás asyncpg (async driver), cambiar por `postgresql+asyncpg://...`
    # ──────────────────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./docuflow.db"

    # Pool de conexiones (ignorado por SQLite)
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # recicla conexiones cada 30 min

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # ──────────────────────────────────────────────────────────────────────────
    # Multi-modelo — Bloque 3.3
    # ──────────────────────────────────────────────────────────────────────────
    # Proveedor de IA activo: openai | anthropic | gemini | ollama
    LLM_PROVIDER: str = "openai"

    # Modelo principal (vacío = usa el default del proveedor)
    #   openai:    gpt-4o-mini
    #   anthropic: claude-3-haiku-20240307
    #   gemini:    gemini-1.5-flash
    #   ollama:    llama3.2
    LLM_MODEL: str = ""

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Google Gemini
    GOOGLE_API_KEY: str = ""

    # ── Google Drive OAuth2 — Bloque 5.3 ─────────────────────────────────────
    GOOGLE_CLIENT_ID:     str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI:  str = "http://localhost:8000/api/v1/integrations/google/callback"

    # ── Dropbox OAuth2 — Bloque 5.3 ──────────────────────────────────────────
    DROPBOX_APP_KEY:      str = ""
    DROPBOX_APP_SECRET:   str = ""
    DROPBOX_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/dropbox/callback"

    # Ollama — Bloque 3.4
    OLLAMA_ENABLED: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"       # modelo principal local
    OLLAMA_MODEL_FAST: str = "llama3.2"  # modelo liviano local

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    # Upload
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 10

    # TTLs de caché (en segundos)
    CACHE_TTL_ANALYSIS: int = 3600
    CACHE_TTL_STATS: int = 300

    # ──────────────────────────────────────────────────────────────────────────
    # Notificaciones Email — Bloque 5.2
    # ──────────────────────────────────────────────────────────────────────────

    # Activar/desactivar envío de emails globalmente
    NOTIFICATIONS_EMAIL_ENABLED: bool = False

    # Backend: "smtp" | "sendgrid"
    EMAIL_BACKEND: str = "smtp"

    # Remitente (aparece en el "From" de todos los emails)
    EMAIL_FROM: str = "noreply@docuflow.app"
    EMAIL_FROM_NAME: str = "DocuFlow"

    # URL pública de la app (para los links dentro del email)
    APP_URL: str = "http://localhost:3000"

    # ── SMTP ──────────────────────────────────────────────────────────────────
    # Para Gmail: SMTP_HOST=smtp.gmail.com SMTP_PORT=465 SMTP_TLS=true
    # Para Mailgun SMTP: SMTP_HOST=smtp.mailgun.org SMTP_PORT=587
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_TLS: bool = True          # True → SMTP_SSL;  False → STARTTLS
    SMTP_USER: str = ""            # dejar vacío si el servidor no requiere auth
    SMTP_PASS: str = ""

    # ── SendGrid ──────────────────────────────────────────────────────────────
    SENDGRID_API_KEY: str = ""

    # ──────────────────────────────────────────────────────────────────────────
    # Stripe — Bloque 6.1
    # ──────────────────────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: str = ""          # sk_live_... o sk_test_...
    STRIPE_WEBHOOK_SECRET: str = ""      # whsec_... (del Dashboard de Stripe)
    STRIPE_PRICE_PRO: str = ""           # price_... del plan Pro
    STRIPE_PRICE_ENTERPRISE: str = ""    # price_... del plan Enterprise

    @property
    def is_postgres(self) -> bool:
        """True si la URL apunta a PostgreSQL (no SQLite)."""
        return self.DATABASE_URL.startswith("postgresql")

    # ──────────────────────────────────────────────────────────────────────────
    # Timezone — Mejoras v2.0
    # ──────────────────────────────────────────────────────────────────────────
    # Usada para mostrar fechas en la zona horaria correcta en logs y exports.
    # El frontend usa la timezone del navegador directamente (date-fns).
    TIMEZONE: str = "America/Argentina/Buenos_Aires"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"   # variables del .env no declaradas aquí no rompen el arranque


settings = Settings()
