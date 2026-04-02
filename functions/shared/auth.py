"""
functions/shared/auth.py
JWT verification middleware for Azure Functions.
Provides require_auth decorator with RBAC and Play Integrity validation.
"""
import os
import json
import logging
import functools
import hashlib
import time
from typing import Callable, List, Optional

import requests
from jose import jwt, JWTError
import azure.functions as func

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (loaded from Key Vault / Application Settings)
# ---------------------------------------------------------------------------
TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")
CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
ALLOWED_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "multitel.com")
PLAY_INTEGRITY_PACKAGE = os.environ.get("ANDROID_PACKAGE_NAME", "com.multitel.reportes")

JWKS_URL = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"

_jwks_cache: dict = {"keys": [], "expires_at": 0}
_JWKS_TTL = 3600


def _get_jwks() -> list:
    now = time.time()
    if now < _jwks_cache["expires_at"] and _jwks_cache["keys"]:
        return _jwks_cache["keys"]
    try:
        resp = requests.get(JWKS_URL, timeout=10)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
        _jwks_cache["keys"] = keys
        _jwks_cache["expires_at"] = now + _JWKS_TTL
        return keys
    except Exception as exc:
        logger.error("Failed to fetch JWKS: %s", exc)
        return _jwks_cache.get("keys", [])


def verify_azure_ad_token(token: str) -> dict:
    if not token:
        raise ValueError("Missing token")
    keys = _get_jwks()
    if not keys:
        raise ValueError("Could not retrieve signing keys")
    try:
        claims = jwt.decode(
            token,
            keys,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=ISSUER,
            options={"verify_exp": True},
        )
    except JWTError as exc:
        raise ValueError(f"Token validation failed: {exc}") from exc
    upn = claims.get("upn") or claims.get("preferred_username") or ""
    if not upn.lower().endswith(f"@{ALLOWED_DOMAIN}"):
        raise ValueError(f"Account domain not allowed: {upn}")
    return claims


def get_user_roles(claims: dict) -> List[str]:
    return claims.get("roles", [])


def require_auth(required_roles: Optional[List[str]] = None):
    """Decorator factory: verifies Azure AD JWT + RBAC on every function call."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(req: func.HttpRequest, *args, **kwargs) -> func.HttpResponse:
            auth_header = req.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return _unauthorized("Authorization header missing or malformed")
            token = auth_header[len("Bearer "):]
            try:
                claims = verify_azure_ad_token(token)
            except ValueError as exc:
                logger.warning("Auth failed: %s", exc)
                return _unauthorized(str(exc))
            roles = get_user_roles(claims)
            if required_roles:
                if not any(r in roles for r in required_roles):
                    logger.warning(
                        "RBAC denied user=%s roles=%s required=%s",
                        claims.get("upn"), roles, required_roles,
                    )
                    return _forbidden("Insufficient privileges")
            kwargs["user_claims"] = claims
            kwargs["user_roles"] = roles
            return fn(req, *args, **kwargs)
        return wrapper
    return decorator


def verify_play_integrity(integrity_token: str) -> bool:
    """Verify Play Integrity API token against Google's API."""
    if not integrity_token:
        logger.warning("Play Integrity: no token provided")
        return False
    try:
        import google.oauth2.service_account as sa
        import google.auth.transport.requests as ga_requests
        creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
        creds_info = json.loads(creds_json)
        credentials = sa.Credentials.from_service_account_info(
            creds_info, scopes=["https://www.googleapis.com/auth/playintegrity"]
        )
        ga_requests.Request()(credentials, None, None)
        access_token = credentials.token

        api_url = (
            f"https://playintegrity.googleapis.com/v1/"
            f"{PLAY_INTEGRITY_PACKAGE}:decodeIntegrityToken"
        )
        resp = requests.post(
            api_url,
            json={"integrity_token": integrity_token},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Play Integrity API returned %s", resp.status_code)
            return False
        verdict = resp.json()
        token_payload = verdict.get("tokenPayloadExternal", {})
        app_integrity = token_payload.get("appIntegrity", {})
        if app_integrity.get("appRecognitionVerdict") not in (
            "PLAY_RECOGNIZED", "UNRECOGNIZED_VERSION"
        ):
            return False
        device_integrity = token_payload.get("deviceIntegrity", {})
        if "MEETS_BASIC_INTEGRITY" not in device_integrity.get(
            "deviceRecognitionVerdict", []
        ):
            return False
        if app_integrity.get("packageName") != PLAY_INTEGRITY_PACKAGE:
            return False
        return True
    except Exception as exc:
        logger.error("Play Integrity verification error: %s", exc)
        return False


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file for .pptx integrity verification."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _unauthorized(message: str) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"error": "Unauthorized", "detail": message}),
        status_code=401,
        headers={
            "Content-Type": "application/json",
            "WWW-Authenticate": 'Bearer realm="multitel-reportes"',
        },
    )


def _forbidden(message: str) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"error": "Forbidden", "detail": message}),
        status_code=403,
        headers={"Content-Type": "application/json"},
    )
