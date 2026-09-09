"""Journalisation d'une ligne structurée par requête HTTP."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("core.request")

CHEMINS_IGNORES = frozenset({"/health", "/metrics"})


def niveau_pour(status: int) -> int:
    """5xx = panne du service, 4xx = appel incorrect, le reste = normal."""
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    return logging.INFO


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        debut = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Requête en erreur",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": round((time.perf_counter() - debut) * 1000, 1),
                },
            )
            raise

        duree_ms = round((time.perf_counter() - debut) * 1000, 1)

        if request.url.path not in CHEMINS_IGNORES:
            logger.log(
                niveau_pour(response.status_code),
                "%s %s -> %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duree_ms,
                    "query": str(request.url.query) or None,
                },
            )

        response.headers["X-Request-ID"] = request_id
        return response
