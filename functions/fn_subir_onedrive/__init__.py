import azure.functions as func
import json
import logging
import hashlib
import os
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


def _sha256_file(file_path: str) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _upload_to_onedrive(
    graph_token: str,
    drive_id: str,
    reporte_id: str,
    local_path: str,
    remote_filename: str,
) -> str:
    """
    Upload a single file to OneDrive using Graph API large-file upload session
    for files >4MB, simple PUT for smaller files.
    Returns the webUrl of the uploaded file.
    """
    import httpx

    file_size = os.path.getsize(local_path)
    remote_path = f"/Multitel/Reportes/{reporte_id}/{remote_filename}"
    headers_base = {"Authorization": f"Bearer {graph_token}"}

    if file_size <= 4 * 1024 * 1024:
        # Simple PUT upload
        with open(local_path, "rb") as f:
            content = f.read()

        url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/root:{remote_path}:/content"
        )
        resp = httpx.put(
            url,
            headers={**headers_base, "Content-Type": "application/octet-stream"},
            content=content,
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json().get("webUrl", "")

    else:
        # Large file: create upload session then upload in chunks
        session_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/root:{remote_path}:/createUploadSession"
        )
        session_resp = httpx.post(
            session_url,
            headers={**headers_base, "Content-Type": "application/json"},
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=30.0,
        )
        session_resp.raise_for_status()
        upload_url = session_resp.json()["uploadUrl"]

        chunk_size = 5 * 1024 * 1024  # 5MB chunks
        uploaded = 0

        with open(local_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                end = uploaded + len(chunk) - 1
                resp = httpx.put(
                    upload_url,
                    headers={
                        "Content-Range": f"bytes {uploaded}-{end}/{file_size}",
                        "Content-Length": str(len(chunk)),
                    },
                    content=chunk,
                    timeout=120.0,
                )
                if resp.status_code in (200, 201):
                    return resp.json().get("webUrl", "")
                uploaded += len(chunk)

        return ""


def _update_dataverse_urls(
    reporte_id: str,
    pptx_url: str,
    pdf_url: str,
    pptx_sha256: str,
) -> None:
    """Patch Dataverse record with OneDrive URLs and PPTX SHA-256."""
    import httpx
    from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

    _mi_client_id = os.environ.get("MANAGED_IDENTITY_CLIENT_ID", "")

    cred = (

        ManagedIdentityCredential(client_id=_mi_client_id)

        if _mi_client_id

        else DefaultAzureCredential()

    )
    dataverse_url = get_secret("DATAVERSE_URL")
    token = cred.get_token("https://orgXXXXXXXX.crm.dynamics.com/.default").token

    httpx.patch(
        f"{dataverse_url}/api/data/v9.2/cr_multitelreportes"
        f"?$filter=cr_reporte_id eq '{reporte_id}'",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        },
        json={
            "cr_pptx_url": pptx_url,
            "cr_pdf_url": pdf_url,
            "cr_pptx_sha256": pptx_sha256,
            "cr_estado": "Generado",
        },
        timeout=15.0,
    )


# ---------------------------------------------------------------------------
# Azure Function entry point
# ---------------------------------------------------------------------------

def main(req: func.HttpRequest, **kwargs) -> func.HttpResponse:
    """
    POST /api/subir-onedrive
    Internal endpoint â called by fn_generar_pptx after generation completes.
    Receives file paths (temp storage), uploads both PPTX and PDF to
    /Multitel/Reportes/{reporte_id}/ in OneDrive, computes SHA-256 of PPTX,
    updates Dataverse with URLs and hash, writes audit log.

    Body: { reporte_id, pptx_path, pdf_path }
    """
    # Validate internal function key
    expected_key = get_secret("FN_SUBIR_ONEDRIVE_KEY")
    provided_key = req.headers.get("x-functions-key", "")
    if provided_key != expected_key:
        logger.warning("subir_onedrive_unauthorized")
        return func.HttpResponse(
            json.dumps({"error": "Unauthorized"}),
            status_code=401,
            mimetype="application/json",
        )

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Payload JSON invÃ¡lido"}),
            status_code=400,
            mimetype="application/json",
        )

    reporte_id = body.get("reporte_id", "")
    pptx_path = body.get("pptx_path", "")
    pdf_path = body.get("pdf_path", "")

    if not all([reporte_id, pptx_path, pdf_path]):
        return func.HttpResponse(
            json.dumps({"error": "reporte_id, pptx_path y pdf_path son requeridos"}),
            status_code=400,
            mimetype="application/json",
        )

    if not os.path.exists(pptx_path):
        return func.HttpResponse(
            json.dumps({"error": f"pptx_path no encontrado: {pptx_path}"}),
            status_code=404,
            mimetype="application/json",
        )

    if not os.path.exists(pdf_path):
        return func.HttpResponse(
            json.dumps({"error": f"pdf_path no encontrado: {pdf_path}"}),
            status_code=404,
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
    drive_id = get_secret("ONEDRIVE_DRIVE_ID")

    # ---- Compute SHA-256 of PPTX before upload ----
    try:
        pptx_sha256 = _sha256_file(pptx_path)
        logger.info("pptx_sha256 reporte_id=%s sha256=%s", reporte_id, pptx_sha256)
    except Exception as exc:
        logger.error("sha256_failed reporte_id=%s err=%s", reporte_id, exc)
        _write_audit_log(reporte_id, "sistema", "SUBIR_ONEDRIVE", "ERROR", f"sha256: {exc}")
        return func.HttpResponse(
            json.dumps({"error": "Error al computar SHA-256"}),
            status_code=500,
            mimetype="application/json",
        )

    # ---- Upload PPTX ----
    try:
        pptx_url = _upload_to_onedrive(
            graph_token, drive_id, reporte_id,
            pptx_path, f"reporte_{reporte_id}.pptx"
        )
        logger.info("pptx_uploaded reporte_id=%s url=%s", reporte_id, pptx_url)
    except Exception as exc:
        logger.error("pptx_upload_failed reporte_id=%s err=%s", reporte_id, exc)
        _write_audit_log(reporte_id, "sistema", "SUBIR_ONEDRIVE", "ERROR", f"pptx_upload: {exc}")
        return func.HttpResponse(
            json.dumps({"error": "Error al subir PPTX a OneDrive"}),
            status_code=500,
            mimetype="application/json",
        )

    # ---- Upload PDF ----
    try:
        pdf_url = _upload_to_onedrive(
            graph_token, drive_id, reporte_id,
            pdf_path, f"reporte_{reporte_id}.pdf"
        )
        logger.info("pdf_uploaded reporte_id=%s url=%s", reporte_id, pdf_url)
    except Exception as exc:
        logger.error("pdf_upload_failed reporte_id=%s err=%s", reporte_id, exc)
        _write_audit_log(reporte_id, "sistema", "SUBIR_ONEDRIVE", "ERROR", f"pdf_upload: {exc}")
        return func.HttpResponse(
            json.dumps({"error": "Error al subir PDF a OneDrive"}),
            status_code=500,
            mimetype="application/json",
        )

    # ---- Update Dataverse with URLs + SHA-256 ----
    try:
        _update_dataverse_urls(reporte_id, pptx_url, pdf_url, pptx_sha256)
    except Exception as exc:
        # Non-fatal: files are uploaded, URLs just aren't persisted yet
        logger.warning("dataverse_update_failed reporte_id=%s err=%s", reporte_id, exc)

    # ---- Audit log ----
    _write_audit_log(
        reporte_id, "sistema", "SUBIR_ONEDRIVE", "OK",
        f"pptx={pptx_url} pdf={pdf_url} sha256={pptx_sha256[:16]}..."
    )

    return func.HttpResponse(
        json.dumps({
            "reporte_id": reporte_id,
            "pptx_url": pptx_url,
            "pdf_url": pdf_url,
            "pptx_sha256": pptx_sha256,
        }),
        status_code=200,
        mimetype="application/json",
    )
