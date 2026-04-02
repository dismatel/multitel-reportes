"""
fn_subir_onedrive/__init__.py
Sube PPTX y PDF a OneDrive via Microsoft Graph API.
Estructura: /Multitel/Reportes/{ID}/
Roles: Tecnico, Supervisor
"""
import json, logging, os, base64
from datetime import datetime, timezone
import azure.functions as func
import requests
from azure.identity import DefaultAzureCredential
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.auth import require_auth

logger = logging.getLogger(__name__)
GRAPH_API_BASE = os.environ.get("GRAPH_API_BASE", "https://graph.microsoft.com/v1.0")
ONEDRIVE_ROOT_PATH = os.environ.get("ONEDRIVE_ROOT_PATH", "/Multitel/Reportes")
SHAREPOINT_SITE_ID = os.environ.get("SHAREPOINT_SITE_ID", "")
DATAVERSE_URL = os.environ["DATAVERSE_URL"]

def _get_graph_token():
      cred = DefaultAzureCredential()
      return cred.get_token("https://graph.microsoft.com/.default").token

def _get_drive_url():
      if SHAREPOINT_SITE_ID:
                return f"{GRAPH_API_BASE}/sites/{SHAREPOINT_SITE_ID}/drive"
            return f"{GRAPH_API_BASE}/me/drive"

def _create_folder(token, drive_url, parent_ref, name):
      h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    get_r = requests.get(f"{drive_url}/items/{parent_ref}:/{name}", headers=h, timeout=30)
    if get_r.status_code == 200:
              return get_r.json()
          if parent_ref == "root":
                    url = f"{drive_url}/root/children"
else:
        url = f"{drive_url}/items/{parent_ref}:/children"
      r = requests.post(url, headers=h, json={"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"}, timeout=30)
    r.raise_for_status()
    return r.json()

def _ensure_folder(token, reporte_id):
      durl = _get_drive_url()
    _create_folder(token, durl, "root", "Multitel")
    _create_folder(token, durl, "root:/Multitel", "Reportes")
    item = _create_folder(token, durl, "root:/Multitel/Reportes", reporte_id)
    return item.get("id", ""), durl

def _upload_file(token, drive_url, folder_id, filename, content, ctype):
      h = {"Authorization": f"Bearer {token}", "Content-Type": ctype}
    if len(content) <= 4*1024*1024:
              r = requests.put(f"{drive_url}/items/{folder_id}:/{filename}:/content", headers=h, data=content, timeout=120)
              r.raise_for_status()
              return r.json()
          sh = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    sr = requests.post(f"{drive_url}/items/{folder_id}:/{filename}:/createUploadSession", headers=sh,
                               json={"item": {"@microsoft.graph.conflictBehavior": "replace", "name": filename}}, timeout=30)
    sr.raise_for_status()
    uurl = sr.json()["uploadUrl"]
    cs = 4*1024*1024
    total = len(content)
    up = 0
    while up < total:
              chunk = content[up:up+cs]
              end = min(up+cs-1, total-1)
              ch = {"Content-Length": str(len(chunk)), "Content-Range": f"bytes {up}-{end}/{total}", "Content-Type": ctype}
              cr = requests.put(uurl, headers=ch, data=chunk, timeout=120)
              if cr.status_code in (200, 201):
                            return cr.json()
                        cr.raise_for_status()
        up += len(chunk)
    return {}

def _share_link(token, drive_url, item_id):
      h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(f"{drive_url}/items/{item_id}/createLink", headers=h,
                              json={"type": "view", "scope": "organization"}, timeout=30)
    r.raise_for_status()
    return r.json().get("link", {}).get("webUrl", "")

def _update_dataverse(reporte_id, url_pptx, url_pdf):
      cred = DefaultAzureCredential()
    token = cred.get_token(f"{DATAVERSE_URL}/.default").token
    entity = os.environ.get("DATAVERSE_ENTITY_REPORTES", "multitel_reportes")
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                  "OData-MaxVersion": "4.0", "OData-Version": "4.0", "If-Match": "*"}
    body = {"multitel_url_pptx": url_pptx, "multitel_url_pdf": url_pdf,
                        "multitel_estado": "pendiente_aprobacion",
                        "multitel_fechasubida": datetime.now(timezone.utc).isoformat()}
    r = requests.patch(f"{DATAVERSE_URL}/api/data/v9.2/{entity}s({reporte_id})", headers=h, json=body, timeout=30)
    r.raise_for_status()

@require_auth(required_roles=["Tecnico", "Supervisor"])
def main(req: func.HttpRequest) -> func.HttpResponse:
      logger.info("fn_subir_onedrive invocado.")
    try:
              body = req.get_json()
except ValueError:
        return func.HttpResponse('{"error":"Body JSON invalido."}', status_code=400, mimetype="application/json")
    reporte_id = body.get("reporte_id")
    pptx_b64 = body.get("pptx_base64")
    pdf_b64 = body.get("pdf_base64")
    if not reporte_id or not pptx_b64:
              return func.HttpResponse('{"error":"reporte_id y pptx_base64 requeridos."}', status_code=400, mimetype="application/json")
    try:
              pptx_bytes = base64.b64decode(pptx_b64)
        pdf_bytes = base64.b64decode(pdf_b64) if pdf_b64 else None
except Exception as e:
        return func.HttpResponse(json.dumps({"error": f"Decode error: {e}"}), status_code=400, mimetype="application/json")
    try:
              token = _get_graph_token()
        folder_id, drive_url = _ensure_folder(token, reporte_id)
        pptx_fn = body.get("pptx_filename", f"Reporte_Multitel_{reporte_id}.pptx")
        pptx_item = _upload_file(token, drive_url, folder_id, pptx_fn, pptx_bytes,
                                             "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        url_pptx = _share_link(token, drive_url, pptx_item["id"])
        url_pdf = ""
        if pdf_bytes:
                      pdf_fn = body.get("pdf_filename", f"Reporte_Multitel_{reporte_id}.pdf")
                      pdf_item = _upload_file(token, drive_url, folder_id, pdf_fn, pdf_bytes, "application/pdf")
                      url_pdf = _share_link(token, drive_url, pdf_item["id"])
                  try:
                                _update_dataverse(reporte_id, url_pptx, url_pdf)
except Exception as ex:
            logger.warning(f"Dataverse update failed: {ex}")
        return func.HttpResponse(json.dumps({
                      "reporte_id": reporte_id, "url_pptx": url_pptx, "url_pdf": url_pdf,
                      "carpeta": f"{ONEDRIVE_ROOT_PATH}/{reporte_id}/",
                      "estado": "archivos_subidos", "timestamp": datetime.now(timezone.utc).isoformat()
        }), status_code=200, mimetype="application/json")
except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
