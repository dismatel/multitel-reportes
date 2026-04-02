"""
functions/fn_aprobar/__init__.py
Approval/rejection function — RBAC: Supervisor only.
Called from Power Automate when supervisor clicks Aprobar/Rechazar in Teams.
"""
import json
import logging
import os
from datetime import datetime, timezone

import azure.functions as func
import requests

from shared.auth import require_auth

logger = logging.getLogger(__name__)

DATAVERSE_URL = os.environ.get("DATAVERSE_URL", "")
GRAPH_API = "https://graph.microsoft.com/v1.0"
TEAMS_WEBHOOK = os.environ.get("TEAMS_WEBHOOK_SUPERVISORES", "")
SHAREPOINT_SITE_ID = os.environ.get("SHAREPOINT_SITE_ID", "")


@require_auth(required_roles=["Supervisor"])
def main(req: func.HttpRequest, **kwargs) -> func.HttpResponse:
    """
    POST /api/reportes/{reporte_id}/aprobar
    Body: { "accion": "aprobar" | "rechazar", "comentario": "..." }
    """
    user_claims = kwargs.get("user_claims", {})
    supervisor_name = user_claims.get("name", "Supervisor")
    supervisor_upn = user_claims.get("upn") or user_claims.get("preferred_username", "")

    reporte_id = req.route_params.get("reporte_id")
    if not reporte_id:
        return func.HttpResponse(
            json.dumps({"error": "reporte_id requerido"}),
            status_code=400,
            headers={"Content-Type": "application/json"},
        )

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "JSON invalido"}),
            status_code=400,
            headers={"Content-Type": "application/json"},
        )

    accion = body.get("accion", "").lower()
    if accion not in ("aprobar", "rechazar"):
        return func.HttpResponse(
            json.dumps({"error": "accion debe ser 'aprobar' o 'rechazar'"}),
            status_code=400,
            headers={"Content-Type": "application/json"},
        )

    comentario = body.get("comentario", "")
    nuevo_estado = "Aprobado" if accion == "aprobar" else "Rechazado"
    timestamp = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # 1. Update Dataverse: set estado + supervisor info
    # ------------------------------------------------------------------
    token = req.headers.get("Authorization", "").replace("Bearer ", "")
    dataverse_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
    }

    update_payload = {
        "cr123_estado": nuevo_estado,
        "cr123_supervisor": supervisor_name,
        "cr123_supervisor_upn": supervisor_upn,
        "cr123_comentario_aprobacion": comentario,
        "cr123_fecha_aprobacion": timestamp,
    }

    dataverse_resp = requests.patch(
        f"{DATAVERSE_URL}/api/data/v9.2/cr123_reportes({reporte_id})",
        headers=dataverse_headers,
        json=update_payload,
        timeout=15,
    )

    if dataverse_resp.status_code not in (200, 204):
        logger.error(
            "Dataverse update failed: status=%s", dataverse_resp.status_code
        )
        return func.HttpResponse(
            json.dumps({"error": "Error actualizando Dataverse"}),
            status_code=500,
            headers={"Content-Type": "application/json"},
        )

    # ------------------------------------------------------------------
    # 2. Audit log in SharePoint
    # ------------------------------------------------------------------
    _write_audit_log(
        token=token,
        usuario=supervisor_upn,
        accion=f"reporte_{accion}",
        reporte_id=reporte_id,
        resultado=nuevo_estado,
        timestamp=timestamp,
    )

    # ------------------------------------------------------------------
    # 3. Notify technician via Teams (simple message card)
    # ------------------------------------------------------------------
    _notify_technician(
        token=token,
        reporte_id=reporte_id,
        accion=accion,
        supervisor_name=supervisor_name,
        comentario=comentario,
    )

    logger.info("Reporte %s %s por %s", reporte_id, nuevo_estado, supervisor_upn)

    return func.HttpResponse(
        json.dumps({
            "id": reporte_id,
            "estado": nuevo_estado,
            "supervisor": supervisor_name,
            "timestamp": timestamp,
        }),
        status_code=200,
        headers={"Content-Type": "application/json"},
    )


def _write_audit_log(
    token: str,
    usuario: str,
    accion: str,
    reporte_id: str,
    resultado: str,
    timestamp: str,
) -> None:
    """Write entry to SharePoint audit list."""
    if not SHAREPOINT_SITE_ID:
        return
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "fields": {
            "Title": f"{accion} - {reporte_id}",
            "Usuario": usuario,
            "Accion": accion,
            "ReporteId": reporte_id,
            "Resultado": resultado,
            "Timestamp": timestamp,
        }
    }
    try:
        requests.post(
            f"{GRAPH_API}/sites/{SHAREPOINT_SITE_ID}/lists/AuditLog/items",
            headers=headers,
            json=payload,
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Audit log write failed: %s", exc)


def _notify_technician(
    token: str,
    reporte_id: str,
    accion: str,
    supervisor_name: str,
    comentario: str,
) -> None:
    """Send Teams message to technician's channel."""
    if not TEAMS_WEBHOOK:
        return
    emoji = "✅" if accion == "aprobar" else "❌"
    color = "00C853" if accion == "aprobar" else "D50000"
    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": color,
        "summary": f"Reporte {accion}do",
        "sections": [{
            "activityTitle": f"{emoji} Reporte {accion}do",
            "activitySubtitle": f"ID: {reporte_id}",
            "facts": [
                {"name": "Supervisor", "value": supervisor_name},
                {"name": "Comentario", "value": comentario or "Sin comentario"},
            ],
        }],
    }
    try:
        requests.post(TEAMS_WEBHOOK, json=payload, timeout=10)
    except Exception as exc:
        logger.warning("Teams notification failed: %s", exc)
