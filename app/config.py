from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DocuFlow"
    APP_VERSION: str = "2.1.0"
    APP_ENV: str = "development"  # "development" | "production"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # Database
    DATABASE_URL: str = "sqlite:///./docuflow.db"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = ""   # Si vacío, usa REDIS_URL
    CELERY_RESULT_BACKEND: str = ""  # Si vacío, usa REDIS_URL

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
    CACHE_TTL_ANALYSIS: int = 3600   # 1 hora — resultado del análisis IA
    CACHE_TTL_STATS: int = 300       # 5 minutos — métricas de /stats/summary

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()