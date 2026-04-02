# functions/shared/__init__.py
from .auth import require_auth, verify_azure_ad_token, verify_play_integrity, compute_sha256, get_user_roles

__all__ = [
    "require_auth",
    "verify_azure_ad_token",
    "verify_play_integrity",
    "compute_sha256",
    "get_user_roles",
]
