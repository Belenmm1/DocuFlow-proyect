"""
app/utils/logger.py — Bloque 7.3
Logging estructurado en JSON para producción; texto legible en desarrollo.
"""
import logging
import os
import sys
import time
import json
from typing import Any


class JSONFormatter(logging.Formatter):
    """
    Emite cada log record como una línea JSON.
    Compatible con Cloud Logging (GCP/Railway) y Datadog.
    """

    RESERVED = {"msg", "args", "levelname", "name", "pathname", "filename",
                 "module", "exc_info", "exc_text", "stack_info", "lineno",
                 "funcName", "created", "msecs", "relativeCreated", "thread",
                 "threadName", "processName", "process", "message"}

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()

        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.message,
            "module":    record.module,
            "line":      record.lineno,
        }

        # Adjuntar campos extra que el llamador pasó como kwargs
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def _build_handler() -> logging.Handler:
    """Elige el handler y formatter según el entorno."""
    env = os.getenv("APP_ENV", "development").lower()
    handler = logging.StreamHandler(sys.stdout)

    if env == "production":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s — %(message)s")
        )

    return handler


def _configure_root() -> None:
    """Configura el root logger una sola vez."""
    root = logging.getLogger()
    if root.handlers:
        return  # ya configurado

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root.setLevel(level)
    root.addHandler(_build_handler())

    # Silenciar loggers muy verbosos de librerías externas
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retorna un logger con nombre; configura el root si todavía no se hizo."""
    _configure_root()
    return logging.getLogger(name)
