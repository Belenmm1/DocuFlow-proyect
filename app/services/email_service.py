"""
app/services/email_service.py

Bloque 5.2 — Notificaciones Email

Soporta dos backends:
  - SMTP  : cualquier servidor SMTP (Gmail, Mailgun, Postfix, etc.)
  - SendGrid : vía API HTTP (recomendado para producción en Railway)

El backend activo se elige con:
  EMAIL_BACKEND=smtp   →  usa SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS
  EMAIL_BACKEND=sendgrid → usa SENDGRID_API_KEY

Variable de control global:
  NOTIFICATIONS_EMAIL_ENABLED=true/false  (default: false)

Uso desde tasks.py (Celery):
  from app.services.email_service import send_analysis_complete_email
  await send_analysis_complete_email(user_email, doc)

Uso desde contexto sync (Celery worker):
  import asyncio
  asyncio.get_event_loop().run_until_complete(
      send_analysis_complete_email(...)
  )
"""

import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Guard rápido
# ─────────────────────────────────────────────────────────────────────────────

def email_enabled() -> bool:
    return settings.NOTIFICATIONS_EMAIL_ENABLED


# ─────────────────────────────────────────────────────────────────────────────
# Templates HTML
# ─────────────────────────────────────────────────────────────────────────────

def _render_analysis_complete(
    *,
    user_email: str,
    filename: str,
    doc_id: int,
    category: Optional[str],
    summary: Optional[str],
    keywords: Optional[list],
    sentiment: Optional[str],
    app_url: str,
) -> tuple[str, str]:
    """
    Retorna (subject, html_body) para el email de análisis completado.
    """
    subject = f"✅ DocuFlow: análisis completado — {filename}"

    category_badge = f"<span class='badge'>{category}</span>" if category else ""
    summary_block  = f"<p class='summary'>{summary}</p>" if summary else "<p><em>Sin resumen disponible.</em></p>"
    kw_html        = ""
    if keywords:
        kw_html = "<div class='keywords'>" + "".join(
            f"<span class='kw'>{k}</span>" for k in keywords[:10]
        ) + "</div>"

    sentiment_color = {
        "positivo": "#22c55e",
        "negativo": "#ef4444",
        "neutral":  "#6b7280",
    }.get((sentiment or "").lower(), "#6b7280")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>DocuFlow — Análisis completado</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          background: #f4f4f5; color: #18181b; }}
  .wrapper {{ max-width: 600px; margin: 32px auto; background: #ffffff;
              border-radius: 12px; overflow: hidden;
              box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
  .header  {{ background: #1e40af; padding: 28px 32px; color: #fff; }}
  .header h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -.5px; }}
  .header p  {{ font-size: 13px; opacity: .8; margin-top: 4px; }}
  .body    {{ padding: 28px 32px; }}
  .section {{ margin-bottom: 20px; }}
  .label   {{ font-size: 11px; font-weight: 600; text-transform: uppercase;
              letter-spacing: .06em; color: #71717a; margin-bottom: 6px; }}
  .filename {{ font-size: 16px; font-weight: 600; color: #1e40af; word-break: break-all; }}
  .badge   {{ display: inline-block; background: #eff6ff; color: #1d4ed8;
              border: 1px solid #bfdbfe; border-radius: 99px;
              padding: 2px 10px; font-size: 12px; font-weight: 600; }}
  .summary {{ font-size: 14px; line-height: 1.6; color: #3f3f46; }}
  .keywords {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }}
  .kw      {{ background: #f4f4f5; border-radius: 6px; padding: 3px 10px;
              font-size: 12px; color: #52525b; }}
  .sentiment {{ display: inline-block; background: {sentiment_color}22;
                color: {sentiment_color}; border-radius: 6px;
                padding: 3px 10px; font-size: 13px; font-weight: 600; }}
  .cta     {{ text-align: center; padding: 8px 0 4px; }}
  .btn     {{ display: inline-block; background: #1e40af; color: #fff !important;
              text-decoration: none; padding: 12px 28px; border-radius: 8px;
              font-size: 14px; font-weight: 600; }}
  .footer  {{ background: #f4f4f5; padding: 16px 32px; text-align: center;
              font-size: 11px; color: #a1a1aa; }}
  hr {{ border: none; border-top: 1px solid #f0f0f0; margin: 18px 0; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>DocuFlow</h1>
    <p>Tu análisis de documento está listo</p>
  </div>
  <div class="body">
    <div class="section">
      <div class="label">Documento procesado</div>
      <div class="filename">{filename}</div>
    </div>

    {"<div class='section'><div class='label'>Tipo detectado</div>" + category_badge + "</div>" if category else ""}

    <div class="section">
      <div class="label">Resumen</div>
      {summary_block}
    </div>

    {"<div class='section'><div class='label'>Palabras clave</div>" + kw_html + "</div>" if kw_html else ""}

    {"<div class='section'><div class='label'>Sentimiento</div><span class='sentiment'>" + (sentiment or "").capitalize() + "</span></div>" if sentiment else ""}

    <hr/>
    <div class="cta">
      <a class="btn" href="{app_url}/documents/{doc_id}">Ver documento completo →</a>
    </div>
  </div>
  <div class="footer">
    DocuFlow · Este email fue enviado a {user_email} porque tienes notificaciones activadas.<br/>
    Doc ID #{doc_id}
  </div>
</div>
</body>
</html>"""

    return subject, html


def _render_analysis_failed(
    *,
    user_email: str,
    filename: str,
    doc_id: int,
    error_message: Optional[str],
    app_url: str,
) -> tuple[str, str]:
    """Retorna (subject, html_body) para el email de error en análisis."""
    subject = f"❌ DocuFlow: error al procesar — {filename}"

    error_block = (
        f"<pre class='error-code'>{error_message[:500]}</pre>"
        if error_message
        else "<p><em>Sin detalle disponible.</em></p>"
    )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          background: #f4f4f5; color: #18181b; }}
  .wrapper {{ max-width: 600px; margin: 32px auto; background: #fff;
              border-radius: 12px; overflow: hidden;
              box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
  .header  {{ background: #dc2626; padding: 28px 32px; color: #fff; }}
  .header h1 {{ font-size: 22px; font-weight: 700; }}
  .header p  {{ font-size: 13px; opacity: .8; margin-top: 4px; }}
  .body    {{ padding: 28px 32px; }}
  .label   {{ font-size: 11px; font-weight: 600; text-transform: uppercase;
              letter-spacing: .06em; color: #71717a; margin-bottom: 6px; }}
  .filename {{ font-size: 16px; font-weight: 600; color: #dc2626; word-break: break-all; }}
  .error-code {{ background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px;
                  padding: 12px; font-size: 12px; color: #7f1d1d;
                  white-space: pre-wrap; word-break: break-all; }}
  .cta     {{ text-align: center; padding: 16px 0 4px; }}
  .btn     {{ display: inline-block; background: #dc2626; color: #fff !important;
              text-decoration: none; padding: 12px 28px; border-radius: 8px;
              font-size: 14px; font-weight: 600; }}
  .footer  {{ background: #f4f4f5; padding: 16px 32px; text-align: center;
              font-size: 11px; color: #a1a1aa; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>DocuFlow</h1>
    <p>Ocurrió un error al procesar tu documento</p>
  </div>
  <div class="body">
    <div style="margin-bottom:20px">
      <div class="label">Documento</div>
      <div class="filename">{filename}</div>
    </div>
    <div style="margin-bottom:20px">
      <div class="label">Detalle del error</div>
      {error_block}
    </div>
    <p style="font-size:13px;color:#52525b">
      Podés volver a subir el documento o contactar soporte si el problema persiste.
    </p>
    <div class="cta">
      <a class="btn" href="{app_url}/documents/{doc_id}">Ver documento →</a>
    </div>
  </div>
  <div class="footer">
    DocuFlow · Doc ID #{doc_id}
  </div>
</div>
</body>
</html>"""

    return subject, html


# ─────────────────────────────────────────────────────────────────────────────
# Backends de envío
# ─────────────────────────────────────────────────────────────────────────────

async def _send_via_smtp(
    *,
    to_email: str,
    subject: str,
    html_body: str,
) -> None:
    """
    Envía un email vía SMTP.
    Corre el bloqueo en un executor para no bloquear el event loop.
    """
    def _blocking_send():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = settings.EMAIL_FROM
        msg["To"]      = to_email

        # Parte plain-text de fallback
        plain = "Este email requiere un cliente con soporte HTML."
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        context = ssl.create_default_context()

        if settings.SMTP_TLS:
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                context=context,
                timeout=10,
            ) as server:
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASS)
                server.sendmail(settings.EMAIL_FROM, to_email, msg.as_string())
        else:
            with smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=10,
            ) as server:
                server.ehlo()
                server.starttls(context=context)
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASS)
                server.sendmail(settings.EMAIL_FROM, to_email, msg.as_string())

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _blocking_send)
    logger.info("Email enviado via SMTP | to=%s | subject=%s", to_email, subject)


async def _send_via_sendgrid(
    *,
    to_email: str,
    subject: str,
    html_body: str,
) -> None:
    """
    Envía un email vía SendGrid Mail Send API v3.
    Docs: https://docs.sendgrid.com/api-reference/mail-send/mail-send
    """
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from":    {"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                "Content-Type":  "application/json",
            },
        )

    if resp.status_code not in (200, 202):
        raise RuntimeError(
            f"SendGrid error {resp.status_code}: {resp.text[:200]}"
        )

    logger.info(
        "Email enviado via SendGrid | to=%s | subject=%s | status=%s",
        to_email, subject, resp.status_code,
    )


async def _dispatch_email(
    *,
    to_email: str,
    subject: str,
    html_body: str,
) -> None:
    """Elige el backend correcto y envía el email."""
    if not email_enabled():
        logger.debug(
            "Email desactivado (NOTIFICATIONS_EMAIL_ENABLED=false). "
            "Saltando envío a %s", to_email,
        )
        return

    backend = settings.EMAIL_BACKEND.lower()

    try:
        if backend == "sendgrid":
            await _send_via_sendgrid(
                to_email=to_email, subject=subject, html_body=html_body
            )
        elif backend == "smtp":
            await _send_via_smtp(
                to_email=to_email, subject=subject, html_body=html_body
            )
        else:
            logger.error(
                "EMAIL_BACKEND desconocido: '%s'. "
                "Valores válidos: smtp | sendgrid", backend
            )
    except Exception as exc:
        # Nunca propagamos errores de email — no deben romper el pipeline
        logger.error(
            "Error al enviar email | to=%s | backend=%s | error=%s",
            to_email, backend, exc,
        )


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

async def send_analysis_complete_email(
    user_email: str,
    *,
    filename: str,
    doc_id: int,
    category: Optional[str] = None,
    summary: Optional[str] = None,
    keywords: Optional[list] = None,
    sentiment: Optional[str] = None,
) -> None:
    """
    Notifica al usuario que el análisis IA de su documento está listo.

    Llamar desde el Celery task tras marcar el documento como 'done':

        from app.services.email_service import send_analysis_complete_email
        _run_async(send_analysis_complete_email(
            user.email,
            filename=doc.filename,
            doc_id=doc.id,
            category=doc.doc_category,
            summary=doc.summary,
            keywords=doc.keywords,
            sentiment=doc.sentiment,
        ))
    """
    app_url = settings.APP_URL.rstrip("/")
    subject, html = _render_analysis_complete(
        user_email=user_email,
        filename=filename,
        doc_id=doc_id,
        category=category,
        summary=summary,
        keywords=keywords,
        sentiment=sentiment,
        app_url=app_url,
    )
    await _dispatch_email(to_email=user_email, subject=subject, html_body=html)


async def send_analysis_failed_email(
    user_email: str,
    *,
    filename: str,
    doc_id: int,
    error_message: Optional[str] = None,
) -> None:
    """
    Notifica al usuario que el procesamiento de su documento falló.
    """
    app_url = settings.APP_URL.rstrip("/")
    subject, html = _render_analysis_failed(
        user_email=user_email,
        filename=filename,
        doc_id=doc_id,
        error_message=error_message,
        app_url=app_url,
    )
    await _dispatch_email(to_email=user_email, subject=subject, html_body=html)
