"""Bearer-token authentication and identifier masking."""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import AuthNotConfiguredError

_bearer = HTTPBearer(auto_error=False)


def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Fail closed: with no configured token, protected endpoints are unavailable."""
    settings = request.app.state.services.settings
    expected = settings.api_auth_token.get_secret_value() if settings.api_auth_token else ""
    if not expected:
        raise AuthNotConfiguredError("API_AUTH_TOKEN is not configured; protected endpoints are disabled")
    supplied = credentials.credentials if credentials else ""
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def mask_identifier(value: object, visible: int = 3) -> str:
    """Mask an account number or similar identifier, keeping only the last ``visible`` chars."""
    text = "" if value is None else str(value)
    if not text:
        return ""
    if len(text) <= visible:
        return "*" * len(text)
    return "*" * (len(text) - visible) + text[-visible:]
