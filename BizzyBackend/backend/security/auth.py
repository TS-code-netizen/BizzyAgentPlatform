from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    subject: str
    approver: bool = False


def auth_required() -> bool:
    return os.getenv("APP_ENV", "development") not in {"development", "test"}


@lru_cache(maxsize=4)
def jwks_client(issuer: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json", timeout=3)


def current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Identity:
    if not auth_required():
        return Identity("owner", True)
    issuer = os.getenv("COGNITO_ISSUER", "")
    client_id = os.getenv("COGNITO_CLIENT_ID", "")
    if not issuer.startswith("https://cognito-idp.") or not client_id:
        raise HTTPException(503, "Authentication is not configured.")
    if credentials is None:
        raise HTTPException(401, "Sign in required.", headers={"WWW-Authenticate": "Bearer"})
    try:
        key = jwks_client(issuer).get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False, "require": ["exp", "iat", "sub", "iss", "token_use", "client_id"]},
        )
        if claims["token_use"] != "access" or claims["client_id"] != client_id:
            raise jwt.InvalidTokenError("Invalid access token.")
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise jwt.InvalidTokenError("Invalid subject.")
        groups = claims.get("cognito:groups", [])
        if not isinstance(groups, list):
            raise jwt.InvalidTokenError("Invalid groups.")
        return Identity(claims["sub"], "approvers" in groups)
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(503, "Authentication service unavailable.") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired access token.", headers={"WWW-Authenticate": "Bearer"}) from exc


def require_approver(identity: Identity = Depends(current_identity)) -> Identity:
    if not identity.approver:
        raise HTTPException(403, "Approver role required.")
    return identity
