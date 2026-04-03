import azure.functions as func
import azure.durable_functions as df
import json
import logging
import os
import hashlib
import base64
import tempfile
import subprocess
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict
from io import BytesIO

from ..shared.auth import require_auth, get_secret

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SLIDE INDEX MAPS
# ---------------------------------------------------------------------------

PLANTA_EXTERNA_SLOTS: Dict[str, dict] = {
    "Punta Inicial":          {"slide": 2, "placeholder": 0},
    "Punta Final":            {"slide": 2, "placeholder": 1},
    "Reserva 1":              {"slide": 3, "placeholder": 0},
    "Reserva 2":              {"slide": 3, "placeholder": 1},
    "Reserva 3":              {"slide": 3, "placeholder": 2},
    "Reserva 4":              {"slide": 4, "placeholder": 0},
    "Reserva 5":              {"slide": 4, "placeholder": 1},
    "Cambio nodo 1":          {"slide": 5, "placeholder": 0},
    "Cambio nodo 2":          {"slide": 5, "placeholder": 1},
    "Servicios adicionales 1": {"slide": 5, "placeholder": 2},
    "Servicios adicionales 2": {"slide": 5, "placeholder": 3},
    "Metraje Punta Inicial":  {"slide": 2, "placeholder": 2},
    "Metraje Punta Final":    {"slide": 2, "placeholder": 3},
}

CPE_SLOTS: Dict[str, dict] = {
    "Rack sin CPE":     {"slide": 10, "placeholder": 0},
    "Rack con CPE":     {"slide": 10, "placeholder": 1},
    "Etiqueta LIU":     {"slide": 10, "placeholder": 2},
    "Etiqueta CPE":     {"slide": 11, "placeholder": 0},
    "Led Link":         {"slide": 11, "placeholder": 1},
    "ODF Nodo":         {"slide": 11, "placeholder": 2},
    "OLT/Switch":       {"slide": 11, "placeholder": 3},
    "Fusion Caja LIU":  {"slide": 12, "placeholder": 0},
    "Fusion Mufa":      {"slide": 13, "placeholder": 0},
    "SFP":              {"slide": 13, "placeholder": 1},
    "ADA":              {"slide": 14, "placeholder": 0},
    "ODI":              {"slide": 15, "placeholder": 0},
}

# ---------------------------------------------------------------------------
# RUN MERGING — CRITICAL: python-pptx splits {{Variable}} across multiple runs
# ---------------------------------------------------------------------------

def merge_runs_and_replace(paragraph, variables: dict) -> None:
    """
    Concatenate ALL runs of a paragraph, apply ALL variable replacements on
    the full text, then put the result in run[0] and clear the rest.
    Without this, {{Cliente}} split as {{ + Cliente + }} by pptx never matches.
    """
    if not paragraph.runs:
        return

    full_text = "".join(run.text for run in paragraph.runs)

    replaced = False
    for key, value in variables.items():
        placeholder = f"{{{{{key}}}}}"
        if placeholder in full_text:
            full_text = full_text.replace(placeholder, str(value) if value is not None else "")
            replaced = True

    if replaced or any(f"{{{{{k}}}}}" in full_text for k in variables):
        # Preserve formatting from first run, write merged text, clear rest
        paragraph.runs[0].text = full_text
        for run in paragraph.runs[1:]:
            run.text = ""


def replace_all_variables(prs, variables: dict) -> None:
    """Walk every paragraph in every shape in every slide and merge+replace."""
    from pptx.util import Inches, Pt
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    merge_runs_and_replace(paragraph, variables)
            # Tables
            if shape.shape_type == MSO_SHAPE_TYPE.TABLE:
                for row in shape.table.rows:
                    for cell in row.cells:
                        for paragraph in cell.text_frame.paragraphs:
                            merge_runs_and_replace(paragraph, variables)


# ---------------------------------------------------------------------------
# PHOTO INSERTION
# ---------------------------------------------------------------------------

def insert_photos(prs, fotos: list, tipo_reporte: str) -> None:
    """
    Insert stamped photos into the correct slide placeholder based on slot name
    and report type.  foto["imagen_base64"] contains the ALREADY-STAMPED image
    burned by the mobile app before upload.
    """
    from pptx.util import Inches, Emu
    from PIL import Image

    slot_map = PLANTA_EXTERNA_SLOTS if tipo_reporte == "Planta Externa" else CPE_SLOTS

    for foto in fotos:
        slot_nombre = foto.get("slot_nombre", "")
        imagen_b64 = foto.get("imagen_base64", "")
        if not imagen_b64 or slot_nombre not in slot_map:
            continue

        slot_info = slot_map[slot_nombre]
        slide_idx = slot_info["slide"]
        ph_idx = slot_info["placeholder"]

        if slide_idx >= len(prs.slides):
            logger.warning("slide_index_out_of_range slot=%s idx=%d", slot_nombre, slide_idx)
            continue

        slide = prs.slides[slide_idx]
        img_bytes = base64.b64decode(imagen_b64)

        # Find the correct picture placeholder by index
        target_ph = None
        pic_phs = [sh for sh in slide.placeholders
                   if sh.placeholder_format.idx not in (0, 1)]  # skip title/body
        # Fallback: use positional index among picture placeholders
        picture_shapes = [sh for sh in slide.shapes
                          if hasattr(sh, "placeholder_format") and sh.placeholder_format is not None]
        if ph_idx < len(picture_shapes):
            target_ph = picture_shapes[ph_idx]

        if target_ph is not None:
            try:
                from pptx.util import Emu
                left = target_ph.left
                top = target_ph.top
                width = target_ph.width
                height = target_ph.height
                # Remove placeholder and add picture in its place
                sp = target_ph._element
                sp.getparent().remove(sp)
                slide.shapes.add_picture(
                    BytesIO(img_bytes), left, top, width, height
                )
            except Exception as exc:
                logger.warning("photo_insert_failed slot=%s err=%s", slot_nombre, exc)
        else:
            # No placeholder found — append to slide at default position
            try:
                slide.shapes.add_picture(
                    BytesIO(img_bytes),
                    Inches(1), Inches(1), Inches(4), Inches(3)
                )
            except Exception as exc:
                logger.warning("photo_append_failed slot=%s err=%s", slot_nombre, exc)


# ---------------------------------------------------------------------------
# BUILD VARIABLE MAP from payload
# ---------------------------------------------------------------------------

def build_variable_map(payload: dict) -> dict:
    """Map all 60+ template variables from the form payload."""
    pc = payload.get("patchcord_vars", {})
    # Build PC01..PC28 defaults
    patchcord_map = {f"PC{i:02d}": pc.get(f"PC{i:02d}", "") for i in range(1, 29)}

    variables = {
        "Cliente":               payload.get("cliente", ""),
        "ID del Servicio":       payload.get("id_servicio", ""),
        "Encargado de grupo":    payload.get("encargado_grupo", ""),
        "Fecha":                 payload.get("fecha", ""),
        "Coordinadora":          payload.get("coordinadora", ""),
        "Encargados de grupos":  payload.get("encargados_grupos", ""),
        "Nodo":                  payload.get("nodo", ""),
        "Tipo de Servicio":      payload.get("tipo_servicio", ""),
        "Equipo Instalado":      payload.get("equipo_instalado", ""),
        "PotenciaCajaLiu":       payload.get("potencia_caja_liu", ""),
        "PerdidaCajaLiu":        payload.get("perdida_caja_liu", ""),
        "FusionCajaLiu":         payload.get("fusion_caja_liu", ""),
        "PerdidaMufaUltima":     payload.get("perdida_mufa_ultima", ""),
        "FusionMufaUlt":         payload.get("fusion_mufa_ult", ""),
        "InstSFP":               payload.get("inst_sfp", ""),
        "ODF":                   payload.get("odf", ""),
        "Rack sin CPE":          payload.get("rack_sin_cpe", ""),
        "Rack con CPE":          payload.get("rack_con_cpe", ""),
        "Etiqueta LIU":          payload.get("etiqueta_liu", ""),
        "Etiqueta CPE":          payload.get("etiqueta_cpe", ""),
        "Led Link":              payload.get("led_link", ""),
        "OLT/SWITCH":            payload.get("olt_switch", ""),
        "ODF Nodo":              payload.get("odf_nodo", ""),
        "ADA":                   payload.get("ada", ""),
        "ODI":                   payload.get("odi", ""),
        "Supervisor Lider":      payload.get("supervisor_lider", ""),
        "Firma Supervisor Lider": payload.get("firma_supervisor_lider", {}).get("imagen_base64", ""),
        "Gerente Operativo":     payload.get("gerente_operativo", ""),
        "Firma Gerente Operativo": payload.get("firma_gerente_operativo", {}).get("imagen_base64", ""),
        "Firma Coordinadora":    payload.get("firma_coordinadora", {}).get("imagen_base64", ""),
        "si/no":                 payload.get("si_no", ""),
        **patchcord_map,
    }
    return variables


# ---------------------------------------------------------------------------
# DURABLE FUNCTION — HTTP STARTER
# ---------------------------------------------------------------------------

@require_auth(required_roles=["Tecnico"])
async def http_start(req: func.HttpRequest, starter: str, **kwargs) -> func.HttpResponse:
    """
    HTTP trigger — returns job_id IMMEDIATELY without blocking.
    The heavy lifting runs asynchronously in the orchestrator.
    """
    client = df.DurableOrchestrationClient(starter)

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Payload JSON inválido"}),
            status_code=400,
            mimetype="application/json",
        )

    reporte_id = body.get("reporte_id")
    if not reporte_id:
        return func.HttpResponse(
            json.dumps({"error": "reporte_id requerido"}),
            status_code=400,
            mimetype="application/json",
        )

    # FIX [A-2]: Validar reporte_id como UUID para prevenir OData injection
    _UUID_RE = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    if not _UUID_RE.match(reporte_id):
        logger.warning("fn_generar_pptx: reporte_id no es un UUID válido: %s", reporte_id)
        return func.HttpResponse(
            json.dumps({"error": "reporte_id inválido"}),
            status_code=400,
            mimetype="application/json",
        )

    instance_id = await client.start_new("orchestrator", None, body)
    logger.info("durable_started reporte_id=%s instance=%s", reporte_id, instance_id)

    response = client.create_check_status_response(req, instance_id)
    return response


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# ---------------------------------------------------------------------------

def orchestrator(context: df.DurableOrchestrationContext):
    """Coordinates: generate PPTX → upload to OneDrive → notify."""
    payload_data = context.get_input()
    reporte_id = payload_data.get("reporte_id")

    try:
        # Step 1: Generate PPTX + PDF
        result = yield context.call_activity("generate_pptx_activity", payload_data)

        # Step 2: Upload to OneDrive
        upload_input = {
            "reporte_id": reporte_id,
            "pptx_path": result["pptx_path"],
            "pdf_path": result["pdf_path"],
            "payload": payload_data.get("payload", {}),
        }
        upload_result = yield context.call_activity("upload_files_activity", upload_input)

        # Step 3: Notify technician and supervisor
        notify_input = {
            "reporte_id": reporte_id,
            "tecnico_email": payload_data.get("payload", {}).get("tecnico_email", ""),
            "pptx_url": upload_result.get("pptx_url", ""),
            "pdf_url": upload_result.get("pdf_url", ""),
        }
        yield context.call_activity("notify_activity", notify_input)

        return {"status": "completed", "reporte_id": reporte_id}

    except Exception as exc:
        logger.error("orchestrator_failed reporte_id=%s err=%s", reporte_id, exc)
        raise


# ---------------------------------------------------------------------------
# ACTIVITY: generate PPTX + convert to PDF
# ---------------------------------------------------------------------------

def generate_pptx_activity(payload_data: dict) -> dict:
    """
    1. Load template from Azure Blob Storage
    2. Run merging + variable replacement
    3. Insert stamped photos into correct slide slots
    4. Save PPTX to temp dir
    5. Convert to PDF via LibreOffice headless
    6. Return paths to both files
    """
    from pptx import Presentation
    from azure.storage.blob import BlobServiceClient

    reporte_id = payload_data.get("reporte_id")
    payload = payload_data.get("payload", {})
    tipo_reporte = payload.get("tipo_reporte", "Planta Externa")

    # ---- Load template from Blob Storage ----
    blob_conn = get_secret("AZURE_STORAGE_CONNECTION_STRING")
    template_container = get_secret("TEMPLATE_CONTAINER_NAME")
    template_name = (
        "plantilla_planta_externa.pptx"
        if tipo_reporte == "Planta Externa"
        else "plantilla_cpe.pptx"
    )

    blob_client = BlobServiceClient.from_connection_string(blob_conn)
    container = blob_client.get_container_client(template_container)
    template_bytes = container.get_blob_client(template_name).download_blob().readall()

    prs = Presentation(BytesIO(template_bytes))

    # ---- Step A: Run merging + variable replacement ----
    variables = build_variable_map(payload)
    replace_all_variables(prs, variables)

    # ---- Step B: Insert photos into correct slide slots ----
    fotos = payload.get("fotos", [])
    insert_photos(prs, fotos, tipo_reporte)

    # ---- Step C: Save PPTX to temp directory ----
    tmp_dir = tempfile.mkdtemp(prefix=f"reporte_{reporte_id}_")
    pptx_path = os.path.join(tmp_dir, f"reporte_{reporte_id}.pptx")
    prs.save(pptx_path)

    # ---- Step D: Compute SHA-256 of the generated PPTX ----
    with open(pptx_path, "rb") as f:
        pptx_sha256 = hashlib.sha256(f.read()).hexdigest()
    logger.info("pptx_generated reporte_id=%s sha256=%s", reporte_id, pptx_sha256)

    # Store SHA-256 in Dataverse (non-blocking update)
    try:
        _update_sha256_dataverse(reporte_id, pptx_sha256)
    except Exception as exc:
        logger.warning("sha256_update_failed reporte_id=%s err=%s", reporte_id, exc)

    # ---- Step E: Convert PPTX to PDF via LibreOffice headless ----
    pdf_path = pptx_path.replace(".pptx", ".pdf")
    try:
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", tmp_dir, pptx_path],
            check=True,
            capture_output=True,
            timeout=120,
        )
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"LibreOffice did not produce PDF at {pdf_path}")
    except subprocess.TimeoutExpired:
        logger.error("libreoffice_timeout reporte_id=%s", reporte_id)
        raise
    except subprocess.CalledProcessError as exc:
        logger.error("libreoffice_failed reporte_id=%s stderr=%s", reporte_id, exc.stderr)
        raise

    return {
        "pptx_path": pptx_path,
        "pdf_path": pdf_path,
        "pptx_sha256": pptx_sha256,
    }


def _update_sha256_dataverse(reporte_id: str, sha256: str) -> None:
    """Patch the SHA-256 field on the Dataverse record."""
    import httpx
    from azure.identity import DefaultAzureCredential

    cred = DefaultAzureCredential()
    dataverse_url = get_secret("DATAVERSE_URL")
    token = cred.get_token(f"{dataverse_url.rstrip('/')}/.default").token  # FIX [C-2]: scope dinámico desde get_secret("DATAVERSE_URL")

    httpx.patch(
        f"{dataverse_url}/api/data/v9.2/cr_multitelreportes"
        f"?$filter=cr_reporte_id eq '{reporte_id}'",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        },
        json={"cr_pptx_sha256": sha256},
        timeout=15.0,
    )


# ---------------------------------------------------------------------------
# ACTIVITY: upload files (delegates to fn_subir_onedrive logic)
# ---------------------------------------------------------------------------

def upload_files_activity(upload_input: dict) -> dict:
    """
    Uploads PPTX + PDF to OneDrive via Microsoft Graph API.
    Path: /Multitel/Reportes/{reporte_id}/reporte_{reporte_id}.pptx|.pdf
    """
    import httpx
    from azure.identity import DefaultAzureCredential

    reporte_id = upload_input["reporte_id"]
    pptx_path = upload_input["pptx_path"]
    pdf_path = upload_input["pdf_path"]

    cred = DefaultAzureCredential()
    graph_token = cred.get_token("https://graph.microsoft.com/.default").token
    drive_id = get_secret("ONEDRIVE_DRIVE_ID")
    base_path = f"/Multitel/Reportes/{reporte_id}"
    headers = {"Authorization": f"Bearer {graph_token}"}

    def upload_file(local_path: str, remote_name: str) -> str:
        with open(local_path, "rb") as f:
            content = f.read()

        url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/root:{base_path}/{remote_name}:/content"
        )
        resp = httpx.put(
            url,
            headers={**headers, "Content-Type": "application/octet-stream"},
            content=content,
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json().get("webUrl", "")

    pptx_url = upload_file(pptx_path, f"reporte_{reporte_id}.pptx")
    pdf_url = upload_file(pdf_path, f"reporte_{reporte_id}.pdf")

    logger.info("files_uploaded reporte_id=%s pptx=%s pdf=%s", reporte_id, pptx_url, pdf_url)

    # Update URLs in Dataverse
    try:
        import httpx as hx
        from azure.identity import DefaultAzureCredential as DAC
        cred2 = DAC()
        dv_url = get_secret("DATAVERSE_URL")
        dv_token = cred2.get_token(f"{dv_url.rstrip('/')}/.default").token  # FIX [C-2]: scope dinámico desde get_secret("DATAVERSE_URL")
        hx.patch(
            f"{dv_url}/api/data/v9.2/cr_multitelreportes"
            f"?$filter=cr_reporte_id eq '{reporte_id}'",
            headers={
                "Authorization": f"Bearer {dv_token}",
                "Content-Type": "application/json",
                "OData-MaxVersion": "4.0",
                "OData-Version": "4.0",
            },
            json={"cr_pptx_url": pptx_url, "cr_pdf_url": pdf_url, "cr_estado": "Generado"},
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("dataverse_url_update_failed reporte_id=%s err=%s", reporte_id, exc)

    return {"pptx_url": pptx_url, "pdf_url": pdf_url}


# ---------------------------------------------------------------------------
# ACTIVITY: notify
# ---------------------------------------------------------------------------

def notify_activity(notify_input: dict) -> None:
    """Send push notification to technician + Teams card to supervisor."""
    import httpx
    from azure.identity import DefaultAzureCredential

    reporte_id = notify_input.get("reporte_id", "")
    tecnico_email = notify_input.get("tecnico_email", "")
    pptx_url = notify_input.get("pptx_url", "")
    pdf_url = notify_input.get("pdf_url", "")

    cred = DefaultAzureCredential()
    graph_token = cred.get_token("https://graph.microsoft.com/.default").token
    pa_webhook = get_secret("POWER_AUTOMATE_APPROVAL_WEBHOOK")

    # Graph API push notification to technician
    try:
        httpx.post(
            f"https://graph.microsoft.com/v1.0/users/{tecnico_email}/sendMail",
            headers={
                "Authorization": f"Bearer {graph_token}",
                "Content-Type": "application/json",
            },
            json={
                "message": {
                    "subject": f"Reporte {reporte_id} generado",
                    "body": {
                        "contentType": "HTML",
                        "content": (
                            f"<p>Tu reporte <b>{reporte_id}</b> fue generado exitosamente.</p>"
                            f'<p><a href="{pptx_url}">Descargar PPTX</a> | '
                            f'<a href="{pdf_url}">Descargar PDF</a></p>'
                        ),
                    },
                    "toRecipients": [{"emailAddress": {"address": tecnico_email}}],
                }
            },
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("email_notify_failed reporte_id=%s err=%s", reporte_id, exc)

    # Power Automate webhook — triggers Teams card with Aprobar/Rechazar buttons
    try:
        httpx.post(
            pa_webhook,
            json={
                "reporte_id": reporte_id,
                "tecnico_email": tecnico_email,
                "pptx_url": pptx_url,
                "pdf_url": pdf_url,
                "accion": "REPORTE_LISTO_PARA_APROBACION",
            },
            timeout=15.0,
        )
    except Exception as exc:
        logger.warning("teams_webhook_failed reporte_id=%s err=%s", reporte_id, exc)


# ---------------------------------------------------------------------------
# Durable Function app registration
# ---------------------------------------------------------------------------

main = df.Orchestrator.from_generator_function(orchestrator)
