__init__.py"""
functions/fn_health/__init__.py
FIX [B-4]: Health-check endpoint for Azure API Management and Load Balancer.

GET /api/health  — public (no auth required), returns 200 OK when the
                   function host is alive and the environment is configured.
                   Returns 503 if critical env vars are missing so that APIM
                   circuit-breaker can remove the instance from rotation.
"""
import json
import logging
import os
from datetime import datetime, timezone

import azure.functions as func

logger = logging.getLogger(__name__)

# Critical environment variables that must be present for the app to work.
_REQUIRED_ENV = [
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "DATAVERSE_URL",
]


def main(req: func.HttpRequest) -> func.HttpResponse:  # noqa: ARG001
    """
    Health-check endpoint — no authentication required.

    Response body:
        {
          "status": "healthy" | "degraded",
          "timestamp": "<ISO-8601 UTC>",
          "checks": {
            "env_vars": "ok" | "missing: [VAR1, VAR2]"
          }
        }

    HTTP status codes:
        200  — all checks pass (healthy)
        503  — one or more checks fail (degraded); APIM/LB should remove
               this instance from rotation until it recovers.
    """
    missing = [v for v in _REQUIRED_ENV if not os.environ.get(v)]

    checks = {
        "env_vars": "ok" if not missing else f"missing: {missing}",
    }

    if missing:
        status = "degraded"
        http_status = 503
        logger.warning("health_check degraded missing_vars=%s", missing)
    else:
        status = "healthy"
        http_status = 200
        logger.info("health_check ok")

    body = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }

    return func.HttpResponse(
        json.dumps(body),
        status_code=http_status,
        headers={"Content-Type": "application/json"},
    )
