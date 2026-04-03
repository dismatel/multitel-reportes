import azure.functions as func
import json
import logging
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

from ..shared.auth import require_auth, get_secret

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema — validates the full form payload before touching Dataverse
# ---------------------------------------------------------------------------

class PatchcordRow(BaseModel):
    tipo: str          # SC/APC-SC/APC, SC/UPC-SC/UPC, etc.
    metraje: str       # 1m, 3m, 5m, 10m, 15m, 20m, 30m
    modo: str          # SM / MM
    cantidad: int = 0

class MaterialItem(BaseModel):
    nombre: str
    cantidad: int = 0
    activo: bool = False

class FirmaData(BaseModel):
    firmante: str
    rol: str           # supervisor_lider | coordinadora | gerente_operativo
    imagen_base64: str  # PNG en base64 de expo-signature-canvas
    timestamp: str

class FotoSlot(BaseModel):
    slot_nombre: str
    imagen_base64: str
    lat: float
    lon: float
    direccion: str
    timestamp_cst: str
    stamp_quemado: bool = True

class ReporteSchema(BaseModel):
    # ---- Paso 1: Portada ----
    tipo_reporte: str = Field(..., pattern="^(Planta Externa|CPE)$")
    cliente: str                       # Claro / Tigo / otro
    nombre_cliente: str
    id_servicio: str
    encargado_grupo: str
    fecha: str
    coordinadora: str
    encargados_grupos: str

    # ---- Paso 2: Datos técnicos ----
    nodo: str
    tipo_servicio: str
    equipo_instalado: str
    potencia_caja_liu: Optional[str] = ""
    perdida_caja_liu: Optional[str] = ""
    fusion_caja_liu: Optional[str] = ""
    perdida_mufa_ultima: Optional[str] = ""
    fusion_mufa_ult: Optional[str] = ""
    inst_sfp: Optional[str] = ""
    odf: Optional[str] = ""
    rack_sin_cpe: Optional[str] = ""
    rack_con_cpe: Optional[str] = ""
    etiqueta_liu: Optional[str] = ""
    etiqueta_cpe: Optional[str] = ""
    led_link: Optional[str] = ""
    olt_switch: Optional[str] = ""
    odf_nodo: Optional[str] = ""
    ada: Optional[str] = ""
    odi: Optional[str] = ""

    # ---- Paso 3: Materiales ----
    materiales: List[MaterialItem] = []
    patchcords: List[PatchcordRow] = []

    # ---- Paso 4: Fotos ----
    fotos: List[FotoSlot] = []

    # ---- Paso 5: Firmas ----
    supervisor_lider: str
    firma_supervisor_lider: FirmaData
    gerente_operativo: str
    firma_gerente_operativo: FirmaData
    firma_coordinadora: FirmaData

    # ---- Variables extras ----
    si_no: Optional[str] = ""
    patchcord_vars: Optional[dict] = {}   # PC01..PC28 libres

    @field_validator("fecha", mode="before")
    @classmethod
    def validate_fecha(cls, v):
        datetime.strptime(v, "%Y-%m-%d")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dataverse_client():
    from azure.identity import DefaultAzureCredential
    import httpx
    cred = DefaultAzureCredential()
    dataverse_url = get_secret("DATAVERSE_URL")  # e.g. https://orgXXXXXXXX.crm.dynamics.com
    # FIX [C-2]: Use DATAVERSE_URL as the token scope instead of hardcoded placeholder.
    # The Dataverse scope is always {dataverse_url}/.default (without trailing slash).
    scope_url = dataverse_url.rstrip("/")
    token = cred.get_token(f"{scope_url}/.default").token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
        "Prefer": "return=representation",
    }
    return dataverse_url, headers


def _write_dataverse(reporte_id: str, payload: dict, user_email: str) -> dict:
    import httpx
    dataverse_url, headers = _get_dataverse_client()

    record = {
        "cr_reporte_id": reporte_id,
        "cr_tipo_reporte": payload["tipo_reporte"],
        "cr_cliente": payload["cliente"],
        "cr_nombre_cliente": payload["nombre_cliente"],
        "cr_id_servicio": payload["id_servicio"],
        "cr_encargado_grupo": payload["encargado_grupo"],
        "cr_fecha": payload["fecha"],
        "cr_coordinadora": payload["coordinadora"],
        "cr_nodo": payload["nodo"],
        "cr_tipo_servicio": payload["tipo_servicio"],
        "cr_equipo_instalado": payload["equipo_instalado"],
        "cr_potencia_caja_liu": payload.get("potencia_caja_liu", ""),
        "cr_perdida_caja_liu": payload.get("perdida_caja_liu", ""),
        "cr_fusion_caja_liu": payload.get("fusion_caja_liu", ""),
        "cr_perdida_mufa_ultima": payload.get("perdida_mufa_ultima", ""),
        "cr_fusion_mufa_ult": payload.get("fusion_mufa_ult", ""),
        "cr_inst_sfp": payload.get("inst_sfp", ""),
        "cr_odf": payload.get("odf", ""),
        "cr_rack_sin_cpe": payload.get("rack_sin_cpe", ""),
        "cr_rack_con_cpe": payload.get("rack_con_cpe", ""),
        "cr_etiqueta_liu": payload.get("etiqueta_liu", ""),
        "cr_etiqueta_cpe": payload.get("etiqueta_cpe", ""),
        "cr_led_link": payload.get("led_link", ""),
        "cr_olt_switch": payload.get("olt_switch", ""),
        "cr_odf_nodo": payload.get("odf_nodo", ""),
        "cr_ada": payload.get("ada", ""),
        "cr_odi": payload.get("odi", ""),
        "cr_supervisor_lider": payload.get("supervisor_lider", ""),
        "cr_gerente_operativo": payload.get("gerente_operativo", ""),
        "cr_estado": "Enviado",
        "cr_tecnico_email": user_email,
        "cr_timestamp_creacion": datetime.now(timezone.utc).isoformat(),
        "cr_materiales_json": json.dumps(payload.get("materiales", [])),
        "cr_patchcords_json": json.dumps(payload.get("patchcords", [])),
        "cr_patchcord_vars_json": json.dumps(payload.get("patchcord_vars", {})),
        "cr_payload_sha256": _sha256_payload(payload),
    }

    response = httpx.post(
        f"{dataverse_url}/api/data/v9.2/cr_multitelreportes",
        headers=headers,
        json=record,
        timeout=30.0,
    )
    response.raise_for_status()
    created = response.json()
    return {
        "id": created.get("cr_reporte_id", reporte_id),
        "dataverse_record_id": created.get("cr_multitelreporteid", ""),
        "estado": "Enviado",
    }


def _sha256_payload(payload: dict) -> str:
    """Compute SHA-256 of the serialized payload for integrity tracking."""
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _write_audit_log(
    reporte_id: str,
    user_email: str,
    accion: str,
    resultado: str,
    detalles: str = "",
) -> None:
    """Write an audit entry to SharePoint list via Graph API."""
    try:
        import httpx
        from azure.identity import DefaultAzureCredential

        cred = DefaultAzureCredential()
        graph_token = cred.get_token("https://graph.microsoft.com/.default").token

        sharepoint_site_id = get_secret("SHAREPOINT_SITE_ID")
        audit_list_id = get_secret("SHAREPOINT_AUDIT_LIST_ID")

        entry = {
            "fields": {
                "Title": f"[{accion}] {reporte_id}",
                "ReporteId": reporte_id,
                "Usuario": user_email,
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
        # Audit log failure must NEVER break the main flow
        logger.warning("audit_log_write_failed: %s", exc)


# ---------------------------------------------------------------------------
# Azure Function entry point
# ---------------------------------------------------------------------------

@require_auth(required_roles=["Tecnico"])
def main(req: func.HttpRequest, **kwargs) -> func.HttpResponse:
    """
    POST /api/reportes
    Validates the full form payload, writes to Dataverse,
    triggers async PPTX generation and returns {id, estado, timestamp}.

    RBAC: only users with role 'Tecnico' in Azure AD may call this.
    """
    user_claims = kwargs.get("user_claims", {})  # FIX [C-1]: auth.py inyecta "user_claims", no "user_info"
    user_email = user_claims.get("upn") or user_claims.get("preferred_username", "unknown")
    reporte_id = str(uuid.uuid4())

    try:
        body = req.get_json()
    except ValueError as exc:
        logger.warning("invalid_json user=%s err=%s", user_email, exc)
        return func.HttpResponse(
            json.dumps({"error": "Payload JSON inválido"}),
            status_code=400,
            mimetype="application/json",
        )

    # ---- Schema validation ----
    try:
        reporte = ReporteSchema(**body)
    except Exception as exc:
        logger.warning("schema_validation_failed user=%s", user_email)
        return func.HttpResponse(
            json.dumps({"error": "Schema inválido", "detail": str(exc)}),
            status_code=422,
            mimetype="application/json",
        )

    payload_dict = reporte.dict()

    # ---- Compute payload hash before writing (no foto binaries in hash) ----
    hashable = {k: v for k, v in payload_dict.items() if k != "fotos"}
    payload_sha256 = _sha256_payload(hashable)
    logger.info("reporte_received id=%s user=%s sha256=%s", reporte_id, user_email, payload_sha256)

    # ---- Write to Dataverse ----
    try:
        result = _write_dataverse(reporte_id, payload_dict, user_email)
    except Exception as exc:
        logger.error("dataverse_write_failed id=%s err=%s", reporte_id, exc)
        _write_audit_log(reporte_id, user_email, "GUARDAR_REPORTE", "ERROR", str(exc))
        return func.HttpResponse(
            json.dumps({"error": "Error al guardar en Dataverse"}),
            status_code=500,
            mimetype="application/json",
        )

    # ---- Trigger async PPTX generation (fire and forget via Durable) ----
    try:
        import httpx
        generar_url = get_secret("FN_GENERAR_PPTX_URL")
        httpx.post(
            generar_url,
            json={"reporte_id": reporte_id, "payload": payload_dict},
            headers={"x-functions-key": get_secret("FN_GENERAR_PPTX_KEY")},
            timeout=5.0,
        )
    except Exception as exc:
        # Non-fatal: generation is async, user will get push notification when done
        logger.warning("generar_pptx_trigger_failed id=%s err=%s", reporte_id, exc)

    # ---- Audit log ----
    _write_audit_log(
        reporte_id,
        user_email,
        "GUARDAR_REPORTE",
        "OK",
        f"tipo={reporte.tipo_reporte} cliente={reporte.cliente}",
    )

    timestamp = datetime.now(timezone.utc).isoformat()
    return func.HttpResponse(
        json.dumps({"id": result["id"], "estado": result["estado"], "timestamp": timestamp}),
        status_code=201,
        mimetype="application/json",
    )
