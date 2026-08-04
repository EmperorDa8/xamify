"""Supabase JWT verification for the API.

The frontend gates the whole app behind Supabase auth, but until now the backend
trusted any caller that got past CORS — meaning anyone could hit /parse and burn
AI tokens. This module verifies the Supabase access token the browser sends as a
`Authorization: Bearer <jwt>` header.

Two verification modes, picked automatically:
  - HS256 with SUPABASE_JWT_SECRET (the project's "JWT secret" / legacy secret).
  - Asymmetric (ES256/RS256) via the project's JWKS endpoint, derived from
    SUPABASE_URL — used by projects migrated to signing keys.

If NEITHER is configured the dependency fails OPEN (allows the request) but logs
a loud warning, so an existing deployment keeps working until the operator sets
SUPABASE_JWT_SECRET (or SUPABASE_URL) — at which point enforcement turns on with
no code change. Configure it in production to actually protect the endpoints.
"""
import logging
import os

import jwt
from fastapi import Header, HTTPException

log = logging.getLogger("xamio.auth")

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
# Supabase stamps user tokens with aud "authenticated".
SUPABASE_JWT_AUD = os.getenv("SUPABASE_JWT_AUD", "authenticated")

_warned_unconfigured = False
_jwk_client = None


def auth_enabled() -> bool:
    """True when we have a way to verify tokens (a secret or a JWKS URL)."""
    return bool(SUPABASE_JWT_SECRET or SUPABASE_URL)


def _get_jwk_client():
    global _jwk_client
    if _jwk_client is None and SUPABASE_URL:
        from jwt import PyJWKClient

        jwks_url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwk_client = PyJWKClient(jwks_url)
    return _jwk_client


def _decode(token: str) -> dict:
    """Verify the token and return its claims. Prefers the shared HS256 secret;
    falls back to JWKS (asymmetric) when the secret is absent or doesn't match
    (e.g. a project that has migrated to signing keys)."""
    last_err: Exception | None = None

    if SUPABASE_JWT_SECRET:
        try:
            return jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience=SUPABASE_JWT_AUD,
            )
        except jwt.InvalidAudienceError:
            raise
        except Exception as e:  # signature/format mismatch — maybe asymmetric
            last_err = e

    client = _get_jwk_client()
    if client is not None:
        signing_key = client.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            algorithms=["ES256", "RS256"],
            audience=SUPABASE_JWT_AUD,
        )

    if last_err:
        raise last_err
    raise RuntimeError("No JWT verifier configured.")


async def require_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: require a valid Supabase session.

    Returns the token claims (`sub` is the user id). Raises 401 on a missing or
    invalid token. Fails open (with a warning) only when auth is unconfigured.
    """
    global _warned_unconfigured
    if not auth_enabled():
        if not _warned_unconfigured:
            log.warning(
                "Supabase auth is NOT configured (set SUPABASE_JWT_SECRET or "
                "SUPABASE_URL) — API endpoints are currently UNAUTHENTICATED."
            )
            _warned_unconfigured = True
        return {"sub": None, "unauthenticated": True}

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header. Sign in and try again.",
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        return _decode(token)
    except HTTPException:
        raise
    except Exception as e:
        log.info("Rejected token: %s", e)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please sign in again.",
        )
