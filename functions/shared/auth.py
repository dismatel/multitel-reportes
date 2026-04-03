"""
functions/shared/auth.py
JWT verification middleware for Azure Functions.
Provides require_auth decorator with RBAC and Play Integrity validation.

FIX [C-1]: Migrated from python-jose (CVE-2024-33663) to PyJWT>=2.8.
           Uses jwt.decode() with PyJWKClient for JWKS-based RS256 verification.
"""
import os
import json
import logging
import functools
import hashlib
import time
from typing import Callable, List, Optional

import requests
import jwt as pyjwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError, DecodeError
from jwt import PyJWKClient
import azure.functions as func

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (loaded from Key Vault / Application Settings)
# ---------------------------------------------------------------------------
TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")
CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
ALLOWED_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "grupomultitel.com")
PLAY_INTEGRITY_PACKAGE = os.environ.get("ANDROID_PACKAGE_NAME", "com.multitel.reportes")

JWKS_URL = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"

# PyJWKClient handles key caching and rotation automatically (cache_keys=True by default).
# It fetches JWKS on first use and refreshes when a kid is not found.
_jwks_client = PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)


def get_secret(secret_name: str) -> str:
    """
    Retrieve a secret from Azure Key Vault or Application Settings.
    Uses DefaultAzureCredential (Managed Identity in production).
    """
    # First check environment (Application Settings / local.settings.json)
    value = os.environ.get(secret_name, "")
    if value:
        return value
    # Fallback: Azure Key Vault via SDK
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        vault_url = os.environ.get("AZURE_KEYVAULT_URL", "")
        if not vault_url:
            raise ValueError(f"Secret '{secret_name}' not found in env and AZURE_KEYVAULT_URL not set")
        cred = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=cred)
        return client.get_secret(secret_name).value or ""
    except Exception as exc:
        logger.error("get_secret failed for '%s': %s", secret_name, exc)
        raise


def verify_azure_ad_token(token: str) -> dict:
    """
    Validate an Azure AD Bearer JWT using PyJWT + JWKS endpoint.
    Verifies: signature (RS256), expiry, audience (CLIENT_ID),
              issuer, and email domain.

    FIX [C-1]: Replaced python-jose (CVE-2024-33663 — algorithm confusion
               allowing signature bypass) with PyJWT 2.9+ which correctly
               enforces algorithm restrictions via PyJWKClient.
    """
    if not token:
        raise ValueError("Missing token")
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
    except Exception as exc:
        logger.error("JWKS key fetch failed: %s", exc)
        raise ValueError(f"Could not retrieve signing key: {exc}") from exc

    try:
        claims = pyjwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=ISSUER,
            options={
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
                "require": ["exp", "aud", "iss", "upn"],
            },
        )
    except ExpiredSignatureError as exc:
        raise ValueError("Token has expired") from exc
    except DecodeError as exc:
        raise ValueError(f"Token decode error: {exc}") from exc
    except InvalidTokenError as exc:
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
