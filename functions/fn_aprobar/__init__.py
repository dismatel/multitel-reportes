"""
functions/fn_aprobar/__init__.py
Approval/rejection function — RBAC: Supervisor only.
Called from Power Automate when supervisor clicks Aprobar/Rechazar in Teams.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone

import azure.functions as func
import requests

# FIX [CRÍTICO-5]: Import absoluto corregido a relativo.
# El import absoluto (from shared.auth) fallaba con ModuleNotFoundError
# porque Python no encuentra 'shared' como módulo top-level dentro del paquete.
# El import relativo (from ..shared.auth) es correcto para la estructura de carpetas.
from ..shared.auth import require_auth

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

    reporte_id = req.route_params.get("reporte_id", "")
    if not reporte_id:
                logger.warning("fn_aprobar: reporte_id faltante en ruta")
                return func.HttpResponse(
                    json.dumps({"error": "reporte_id requerido en la ruta"}),
                    status_code=400,
                    mimetype="application/json",
                )

    # FIX [A-2]: Validar reporte_id como UUID para prevenir OData injection
    _UUID_RE = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    if not _UUID_RE.match(reporte_id):
        logger.warning("fn_aprobar: reporte_id no es un UUID válido: %s", reporte_id)
        return func.HttpResponse(
            json.dumps({"error": "reporte_id inválido"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
                body = req.get_json()
except ValueError:
            logger.error("fn_aprobar: body JSON inválido")
            return func.HttpResponse(
                json.dumps({"error": "Body JSON inválido"}),
                status_code=400,
                mimetype="application/json",
            )

    accion = body.get("accion", "").lower()
    comentario = body.get("comentario", "")

    if accion not in ("aprobar", "rechazar"):
                return func.HttpResponse(
                                json.dumps({"error": "accion debe ser 'aprobar' o 'rechazar'"}),
                                status_code=400,
                                mimetype="application/json",
                )

    # ── 1. Actualizar estado en Dataverse ────────────────────────────────────
    nuevo_estado = "aprobado" if accion == "aprobar" else "rechazado"
    dataverse_patch_url = (
                f"{DATAVERSE_URL}/api/data/v9.2/multitel_reportes({reporte_id})"
    )

    try:
                from azure.identity import DefaultAzureCredential
                cred = DefaultAzureCredential()
                dv_token = cred.get_token(f"{DATAVERSE_URL.rstrip('/')}/.default").token  # FIX [C-2]: scope dinámico desde DATAVERSE_URL env var

        patch_payload = {
                        "multitel_estado": nuevo_estado,
                        "multitel_supervisor": supervisor_name,
                        "multitel_supervisor_upn": supervisor_upn,
                        "multitel_fecha_aprobacion": datetime.now(timezone.utc).isoformat(),
                        "multitel_comentario_supervisor": comentario,
        }
        dv_resp = requests.patch(
                        dataverse_patch_url,
                        json=patch_payload,
                        headers={
                                            "Authorization": f"Bearer {dv_token}",
                                            "Content-Type": "application/json",
                                            "OData-MaxVersion": "4.0",
                                            "OData-Version": "4.0",
                        },
                        timeout=30,
        )
        dv_resp.raise_for_status()
        logger.info(
                        "fn_aprobar: reporte %s actualizado a '%s' por %s",
                        reporte_id, nuevo_estado, supervisor_upn,
        )
except Exception as exc:
        logger.exception("fn_aprobar: error al actualizar Dataverse — %s", exc)
        return func.HttpResponse(
                        json.dumps({"error": "Error al actualizar estado en Dataverse", "detail": str(exc)}),
                        status_code=502,
                        mimetype="application/json",
        )

    # ── 2. Notificar al técnico vía Graph API (Teams chat) ───────────────────
    # NOTA: Teams Incoming Webhook (outlook.office.com) fue deprecado en ene-2025.
    # Aquí usamos Graph API directamente para enviar un mensaje al técnico.
    # Ver también fn_notificar para la lógica completa de notificaciones.
    try:
                graph_token = cred.get_token("https://graph.microsoft.com/.default").token

        emoji = "✅" if accion == "aprobar" else "❌"
        mensaje = (
                        f"{emoji} Reporte **{reporte_id}** ha sido **{nuevo_estado}** "
                        f"por {supervisor_name}."
        )
        if comentario:
                        mensaje += f"\n\n> {comentario}"

        # Obtener el UPN del técnico desde Dataverse para enviarle el mensaje
        get_url = f"{DATAVERSE_URL}/api/data/v9.2/multitel_reportes({reporte_id})?$select=multitel_tecnico_upn"
        get_resp = requests.get(
                        get_url,
                        headers={"Authorization": f"Bearer {dv_token}", "OData-Version": "4.0"},
                        timeout=15,
        )
        tecnico_upn = get_resp.json().get("multitel_tecnico_upn", "") if get_resp.ok else ""

        if tecnico_upn:
                        # Crear chat 1:1 o enviar a canal Teams si está configurado
                        teams_channel_id = os.environ.get("TEAMS_CHANNEL_ID", "")
                        teams_team_id = os.environ.get("TEAMS_TEAM_ID", "")

            if teams_team_id and teams_channel_id:
                                channel_msg_url = (
                                                        f"{GRAPH_API}/teams/{teams_team_id}/channels/{teams_channel_id}/messages"
                                )
                                graph_resp = requests.post(
                                    channel_msg_url,
                                    json={"body": {"contentType": "markdown", "content": mensaje}},
                                    headers={
                                        "Authorization": f"Bearer {graph_token}",
                                        "Content-Type": "application/json",
                                    },
                                    timeout=20,
                                )
                                if not graph_resp.ok:
                                                        logger.warning(
                                                                                    "fn_aprobar: no se pudo enviar notificación Teams — %s",
                                                                                    graph_resp.text,
                                                        )
            else:
                logger.info("fn_aprobar: TEAMS_TEAM_ID o TEAMS_CHANNEL_ID no configurados, omitiendo notificación")

except Exception as exc:
        # La notificación es best-effort; no falla el flujo principal
        logger.warning("fn_aprobar: error en notificación Teams (non-fatal) — %s", exc)

    return func.HttpResponse(
                json.dumps({
                                "reporte_id": reporte_id,
                                "estado": nuevo_estado,
                                "supervisor": supervisor_name,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
                status_code=200,
                mimetype="application/json",
    )
