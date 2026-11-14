"""Constant-time Bearer authentication helpers."""

import hmac
from fastapi import HTTPException, Request, status

from app.config import get_settings


def verify_bearer_token(authorization: str | None) -> None:
    """Validate Authorization: Bearer <token> using constant-time comparison."""
    expected = get_settings().knowledge_bearer_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KNOWLEDGE_BEARER_TOKEN is not configured",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    provided = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_bearer(request: Request) -> None:
    """FastAPI dependency enforcing Bearer authentication."""
    verify_bearer_token(request.headers.get("authorization"))
