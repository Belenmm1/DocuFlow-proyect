"""
app/services/webhook_dispatcher.py

Bloque 5.1 (complemento) + 5.2 — Dispatcher de webhooks con firma HMAC-SHA256
y reintentos con backoff exponencial.

Usado desde:
  - app/workers/tasks.py  (dispatch after done/failed)
  - app/api/v1/routes/webhooks_route.py  (test endpoint)
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.models.webhook import WebhookConfig
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Máximo de reintentos para dispatch real (distinto al test endpoint)
MAX_DISPATCH_RETRIES = 4
BACKOFF_SECONDS      = [5, 15, 60, 300]   # 5s, 15s, 1min, 5min


def _sign_payload(secret: str, body: bytes) -> str:
    """
    Genera la firma HMAC-SHA256:
      sha256=<hex_digest>
    Compatible con la convención de GitHub / Stripe.
    """
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


async def dispatch_webhook(
    webhook: WebhookConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Envía el payload al endpoint del webhook con firma HMAC.
    Retorna un dict con { success, status_code, error }.

    Para el endpoint /test se llama una sola vez (sin reintentos).
    Para disparo real desde tasks.py usar dispatch_webhook_with_retry.
    """
    body = json.dumps(payload, ensure_ascii=False, default=str).encode()
    signature = _sign_payload(webhook.secret, body)

    headers = {
        "Content-Type":          "application/json",
        "X-DocuFlow-Signature":  signature,
        "X-DocuFlow-Event":      payload.get("event", "unknown"),
        "X-DocuFlow-Webhook-Id": webhook.id,
        "X-DocuFlow-Delivery":   _delivery_id(),
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(str(webhook.url), content=body, headers=headers)

        success = 200 <= resp.status_code < 300
        logger.info(
            "Webhook dispatch | id=%s | url=%s | status=%s | success=%s",
            webhook.id, webhook.url, resp.status_code, success,
        )
        return {"success": success, "status_code": resp.status_code, "error": None}

    except httpx.TimeoutException as exc:
        logger.warning("Webhook timeout | id=%s | url=%s", webhook.id, webhook.url)
        return {"success": False, "status_code": None, "error": f"Timeout: {exc}"}
    except Exception as exc:
        logger.error(
            "Webhook error | id=%s | url=%s | error=%s", webhook.id, webhook.url, exc
        )
        return {"success": False, "status_code": None, "error": str(exc)}


async def dispatch_webhook_with_retry(
    webhook: WebhookConfig,
    payload: dict[str, Any],
) -> None:
    """
    Envía el webhook con hasta MAX_DISPATCH_RETRIES reintentos y backoff.
    Pensado para llamadas desde Celery tasks (usar _run_async).
    """
    import asyncio

    for attempt in range(MAX_DISPATCH_RETRIES + 1):
        result = await dispatch_webhook(webhook, payload)
        if result["success"]:
            return

        if attempt < MAX_DISPATCH_RETRIES:
            wait = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
            logger.warning(
                "Webhook retry %d/%d in %ds | id=%s",
                attempt + 1, MAX_DISPATCH_RETRIES, wait, webhook.id,
            )
            await asyncio.sleep(wait)
        else:
            logger.error(
                "Webhook definitivamente fallido después de %d intentos | id=%s | error=%s",
                MAX_DISPATCH_RETRIES, webhook.id, result["error"],
            )


def _delivery_id() -> str:
    """UUID-like delivery ID basado en timestamp."""
    import uuid
    return str(uuid.uuid4())
