from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.security import decode_token
from app.models.database import SessionLocal
from app.models.user import User


class RateLimitUserMiddleware(BaseHTTPMiddleware):
    """
    Extrae el usuario del JWT (si existe) y lo guarda en request.state.rate_limit_user.
    Esto permite que el limiter use el user_id como clave y aplique
    límites diferenciados por plan.
    No bloquea el request si el token es inválido — eso lo hace get_current_user.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.rate_limit_user = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            payload = decode_token(token)
            if payload and payload.get("type") == "access":
                user_id = payload.get("sub")
                if user_id:
                    db = SessionLocal()
                    try:
                        user = db.query(User).filter(
                            User.id == user_id,
                            User.is_active == True,  # noqa: E712
                        ).first()
                        request.state.rate_limit_user = user
                    finally:
                        db.close()

        return await call_next(request)
