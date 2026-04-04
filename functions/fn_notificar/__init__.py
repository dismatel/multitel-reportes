import os                  # FIX M-6: import os a nivel de módulo
import hmac                # FIX A-4: comparación segura de claves
import azure.functions as func
import json
import logging
from datetime import datetime, timezone

from ..shared.auth import require_auth, get_secret

logger = logging.getLogger(__name__)


def _write_audit_log(
    reporte_id: str,
    sistema: str,
    accion: str,
    resultado: str,
    detalles: str = "",
) -> None:
    """Write audit entry to SharePoint via Graph API."""
    try:
        import httpx
        from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

        _mi_client_id = os.environ.get("MANAGED_IDENTITY_CLIENT_ID", "")
        cred = (
            ManagedIdentityCredential(client_id=_mi_client_id)
            if _mi_client_id
            else DefaultAzureCredential()
        )
        graph_token = cred.get_token("https://graph.microsoft.com/.default").token
        sharepoint_site_id = get_secret("SHAREPOINT_SITE_ID")
        audit_list_id = get_secret("SHAREPOINT_AUDIT_LIST_ID")

        entry = {
            "fields": {
                "Title": f"[{accion}] {reporte_id}",
                "ReporteId": reporte_id,
                "Usuario": sistema,
                "Accion": accion,
                "Resultado": resultado,
                "Detalles": detalles[:500] if detalles else "",
                "Timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }

        httpx.post(
            f"https://graph.microsoft.com/v1.0/sites/{sharepoint_site_id}"
            f"/lists/{audit_list_id}/items",
            headers={
                "Authorization": f"Bearer {graph_token}",
                "Content-Type": "application/json",
            },
            json=entry,
            timeout=10.0,
        )
    except Exception as exc:
        logger.warning("audit_log_write_failed accion=%s err=%s", accion, exc)


def _send_email_notification(
    graph_token: str,
    tecnico_email: str,
    reporte_id: str,
    pptx_url: str,
    pdf_url: str,
) -> None:
    """Send email to technician via Graph API sendMail endpoint."""
    import httpx

    payload = {
        "message": {
            "subject": f"Reporte {reporte_id} generado exitosamente",
            "body": {
                "contentType": "HTML",
                "content": (
                    f"<p>Tu reporte <strong>{reporte_id}</strong> fue generado."
                    f"</p><p>"
                    f'<a href="{pptx_url}">Descargar PPTX</a> &nbsp;|&nbsp; '
                    f'<a href="{pdf_url}">Descargar PDF</a>'
                    f"</p>"
                ),
            },
            "toRecipients": [{"emailAddress": {"address": tecnico_email}}],
        }
    }

    resp = httpx.post(
        f"https://graph.microsoft.com/v1.0/users/{tecnico_email}/sendMail",
        headers={
            "Authorization": f"Bearer {graph_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15.0,
    )
    resp.raise_for_status()


def _send_teams_approval_card(
    pa_webhook: str,
    reporte_id: str,
    tecnico_email: str,
    pptx_url: str,
    pdf_url: str,
) -> None:
    """
    POST to Power Automate webhook which triggers an Adaptive Card in Teams
    with Aprobar / Rechazar buttons for the supervisor.
    """
    import httpx

    resp = httpx.post(
        pa_webhook,
        json={
            "reporte_id": reporte_id,
            "tecnico_email": tecnico_email,
            "pptx_url": pptx_url,
            "pdf_url": pdf_url,
            "accion": "REPORTE_LISTO_PARA_APROBACION",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        timeout=15.0,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Azure Function entry point
# ---------------------------------------------------------------------------

def main(req: func.HttpRequest, **kwargs) -> func.HttpResponse:
    """
    POST /api/notificar
    Internal endpoint — called by fn_generar_pptx orchestrator after files
    are uploaded to OneDrive. No user-facing RBAC (sistema call), but
    validates a shared function key from Key Vault.

    Body: { reporte_id, tecnico_email, pptx_url, pdf_url }
    """
    # FIX A-4: usar hmac.compare_digest para prevenir timing attacks
    expected_key = get_secret("FN_NOTIFICAR_KEY")
    provided_key = req.headers.get("x-functions-key", "")

    if not hmac.compare_digest(
        provided_key.encode("utf-8"),
        expected_key.encode("utf-8"),
    ):
        logger.warning(
            "notificar_unauthorized attempt from %s",
            req.headers.get("x-forwarded-for", "unknown"),
        )
        return func.HttpResponse(
            json.dumps({"error": "Unauthorized"}),
            status_code=401,
            mimetype="application/json",
        )

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Payload JSON inválido"}),
            status_code=400,
            mimetype="application/json",
        )

    reporte_id = body.get("reporte_id", "")
    tecnico_email = body.get("tecnico_email", "")
    pptx_url = body.get("pptx_url", "")
    pdf_url = body.get("pdf_url", "")

    if not all([reporte_id, tecnico_email]):
        return func.HttpResponse(
            json.dumps({"error": "reporte_id y tecnico_email son requeridos"}),
            status_code=400,
            mimetype="application/json",
        )

    from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
    _mi_client_id = os.environ.get("MANAGED_IDENTITY_CLIENT_ID", "")
    cred = (
        ManagedIdentityCredential(client_id=_mi_client_id)
        if _mi_client_id
        else DefaultAzureCredential()
    )
    graph_token = cred.get_token("https://graph.microsoft.com/.default").token

    errors = []

    # ---- Email notification to technician ----
    try:
        _send_email_notification(
            graph_token, tecnico_email, reporte_id, pptx_url, pdf_url
        )
        logger.info("email_sent reporte_id=%s to=%s", reporte_id, tecnico_email)
    except Exception as exc:
        logger.error("email_send_failed reporte_id=%s err=%s", reporte_id, exc)
        errors.append(f"email: {exc}")

    # ---- Teams Adaptive Card con botones Aprobar/Rechazar ----
    try:
        pa_webhook = get_secret("POWER_AUTOMATE_APPROVAL_WEBHOOK")
        _send_teams_approval_card(
            pa_webhook, reporte_id, tecnico_email, pptx_url, pdf_url
        )
        logger.info("teams_card_sent reporte_id=%s", reporte_id)
    except Exception as exc:
        logger.error("teams_card_failed reporte_id=%s err=%s", reporte_id, exc)
        errors.append(f"teams: {exc}")

    # ---- Audit log ----
    resultado = "ERROR: " + "; ".join(errors) if errors else "OK"
    _write_audit_log(reporte_id, "sistema", "NOTIFICAR", resultado)

    status = 207 if errors else 200
    return func.HttpResponse(
        json.dumps({
            "reporte_id": reporte_id,
            "notificaciones_enviadas": not bool(errors),
            "errors": errors,
        }),
        status_code=status,
        mimetype="application/json",
    )
