"""Authentication: validates Clerk-issued JWTs (or dev tokens in local dev)."""

from functools import lru_cache

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.errors import ApiError

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def _signing_key(token: str, settings: Settings):
    return _jwks_client(settings.clerk_jwks_url).get_signing_key_from_jwt(token).key


def verify_clerk_token(token: str, settings: Settings, key_resolver=_signing_key) -> str:
    if not settings.clerk_jwks_url or not settings.clerk_issuer:
        raise ApiError(500, "auth_misconfigured", "Clerk JWKS URL / issuer are not configured.")
    try:
        key = key_resolver(token, settings)
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={"require": ["exp", "sub", "iss"], "verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise ApiError(401, "invalid_token", f"Invalid or expired token: {exc}") from exc
    return str(claims["sub"])


def current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    if creds is None:
        raise ApiError(401, "not_authenticated", "Authentication required.")
    token = creds.credentials
    if settings.auth_mode == "dev":
        if token.startswith("dev:") and len(token) > 4:
            return token[4:]
        raise ApiError(401, "invalid_token", "Dev mode expects 'Bearer dev:<user_id>'.")
    return verify_clerk_token(token, settings)
