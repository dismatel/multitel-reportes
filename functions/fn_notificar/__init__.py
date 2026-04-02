"""
fn_notificar/__init__.py
Envia push notification al tecnico via Graph API
y alerta en Teams al supervisor con botones Aprobar/Rechazar.
Roles: Tecnico, Supervisor
"""
import json, logging, os
from datetime import datetime, timezone
import azure.functions as func
import requests
from azure.identity import DefaultAzureCredential
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.auth import require_auth

logger = logging.getLogger(__name__)
GRAPH_API_BASE = os.environ.get("GRAPH_API_BASE", "https://graph.microsoft.com/v1.0")
TEAMS_TEAM_ID = os.environ.get("TEAMS_TEAM_ID", "")
TEAMS_CHANNEL_ID = os.environ.get("TEAMS_CHANNEL_ID", "")
TEAMS_WEBHOOK_SUPERVISORES = os.environ.get("TEAMS_WEBHOOK_SUPERVISORES", "")
FUNCTIONS_APP_NAME = os.environ.get("FUNCTIONS_APP_NAME", "multitel-reportes-fn")

def _get_graph_token():
      cred = DefaultAzureCredential()
      return cred.get_token("https://graph.microsoft.com/.default").token

def _enviar_teams_adaptive_card(reporte_id, cliente, tecnico_nombre, url_pptx, url_pdf, tipo_reporte):
      """Envia Adaptive Card a Teams con botones Aprobar/Rechazar."""
      approve_url = f"https://{FUNCTIONS_APP_NAME}.azurewebsites.net/api/fn_aprobar"
      tipo_label = "Planta Externa" if tipo_reporte == "planta_externa" else "CPE"
      card = {
          "type": "message",
          "attachments": [{
              "contentType": "application/vnd.microsoft.card.adaptive",
              "contentUrl": None,
              "content": {
                  "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                  "type": "AdaptiveCard",
                  "version": "1.4",
                  "body": [
                      {
                          "type": "TextBlock",
                          "size": "Medium",
                          "weight": "Bolder",
                          "text": f"Nuevo Reporte {tipo_label} — Aprobacion Requerida",
                          "color": "Accent"
                      },
                      {
                          "type": "FactSet",
                          "facts": [
                              {"title": "Cliente:", "value": cliente},
                              {"title": "Tecnico:", "value": tecnico_nombre},
                              {"title": "Reporte ID:", "value": reporte_id},
                              {"title": "Tipo:", "value": tipo_label},
                              {"title": "Fecha:", "value": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M CST")},
                          ]
                      },
                      {
                          "type": "ActionSet",
                          "actions": [
                              {
                                  "type": "Action.OpenUrl",
                                  "title": "Ver PPTX",
                                  "url": url_pptx,
                                  "style": "default"
                              },
                              {
                                  "type": "Action.OpenUrl",
                                  "title": "Ver PDF",
                                  "url": url_pdf or url_pptx,
                                  "style": "default"
                              },
                          ]
                      },
                      {
                          "type": "ActionSet",
                          "actions": [
                              {
                                  "type": "Action.Http",
                                  "title": "Aprobar",
                                  "method": "POST",
                                  "url": approve_url,
                                  "body": json.dumps({"reporte_id": reporte_id, "accion": "aprobar"}),
                                  "style": "positive"
                              },
                              {
                                  "type": "Action.Http",
                                  "title": "Rechazar",
                                  "method": "POST",
                                  "url": approve_url,
                                  "body": json.dumps({"reporte_id": reporte_id, "accion": "rechazar"}),
                                  "style": "destructive"
                              }
                          ]
                      }
                  ]
              }
          }]
      }
      if TEAMS_WEBHOOK_SUPERVISORES:
                h = {"Content-Type": "application/json"}
                r = requests.post(TEAMS_WEBHOOK_SUPERVISORES, headers=h, json=card, timeout=30)
                r.raise_for_status()
                return True
            if TEAMS_TEAM_ID and TEAMS_CHANNEL_ID:
                      token = _get_graph_token()
                      h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                      url = f"{GRAPH_API_BASE}/teams/{TEAMS_TEAM_ID}/channels/{TEAMS_CHANNEL_ID}/messages"
                      r = requests.post(url, headers=h, json=card, timeout=30)
                      r.raise_for_status()
                      return True
                  logger.warning("No hay configuracion de Teams disponible.")
    return False

def _notificar_tecnico_graph(tecnico_upn, reporte_id, mensaje):
      """Envia notificacion push al tecnico via Graph API Chat."""
    try:
              token = _get_graph_token()
              h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
              url = f"{GRAPH_API_BASE}/users/{tecnico_upn}/teamwork/installedApps"
              r = requests.get(url, headers=h, timeout=30)
              if r.status_code != 200:
                            logger.warning(f"No se pudo obtener apps del tecnico {tecnico_upn}: {r.status_code}")
                            return False
                        chat_url = f"{GRAPH_API_BASE}/chats"
        chat_body = {
                      "chatType": "oneOnOne",
                      "members": [
                                        {
                                                              "@odata.type": "#microsoft.graph.aadUserConversationMember",
                                                              "roles": ["owner"],
                                                              "user@odata.bind": f"https://graph.microsoft.com/v1.0/users/{tecnico_upn}",
                                        }
                      ]
        }
        chat_r = requests.post(chat_url, headers=h, json=chat_body, timeout=30)
        if chat_r.status_code not in (200, 201):
                      logger.warning(f"No se pudo crear chat con tecnico: {chat_r.status_code}")
                      return False
                  chat_id = chat_r.json().get("id")
        msg_body = {
                      "body": {
                                        "content": f"Tu reporte <b>{reporte_id}</b> ha sido enviado para aprobacion.<br/>{mensaje}",
                                        "contentType": "html"
                      }
        }
        msg_url = f"{GRAPH_API_BASE}/chats/{chat_id}/messages"
        msg_r = requests.post(msg_url, headers=h, json=msg_body, timeout=30)
        msg_r.raise_for_status()
        return True
except Exception as e:
        logger.warning(f"Error notificando al tecnico: {e}")
        return False

def _actualizar_estado_dataverse(reporte_id, estado):
      try:
                from azure.identity import DefaultAzureCredential
                dataverse_url = os.environ["DATAVERSE_URL"]
                cred = DefaultAzureCredential()
                token = cred.get_token(f"{dataverse_url}/.default").token
                entity = os.environ.get("DATAVERSE_ENTITY_REPORTES", "multitel_reportes")
                h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                     "OData-MaxVersion": "4.0", "OData-Version": "4.0", "If-Match": "*"}
                body = {"multitel_estado": estado, "multitel_fechanotificacion": datetime.now(timezone.utc).isoformat()}
                r = requests.patch(f"{dataverse_url}/api/data/v9.2/{entity}s({reporte_id})", headers=h, json=body, timeout=30)
                r.raise_for_status()
except Exception as e:
        logger.warning(f"No se pudo actualizar estado en Dataverse: {e}")

@require_auth(required_roles=["Tecnico", "Supervisor"])
def main(req: func.HttpRequest) -> func.HttpResponse:
      logger.info("fn_notificar invocado.")
    try:
              body = req.get_json()
except ValueError:
        return func.HttpResponse('{"error":"Body JSON invalido."}', status_code=400, mimetype="application/json")
    reporte_id = body.get("reporte_id")
    cliente = body.get("cliente", "")
    tecnico_nombre = body.get("tecnico_nombre", "")
    tecnico_upn = body.get("tecnico_upn", "")
    url_pptx = body.get("url_pptx", "")
    url_pdf = body.get("url_pdf", "")
    tipo_reporte = body.get("tipo_reporte", "planta_externa")
    if not reporte_id:
              return func.HttpResponse('{"error":"reporte_id requerido."}', status_code=400, mimetype="application/json")
    results = {"reporte_id": reporte_id, "teams_notificado": False, "tecnico_notificado": False}
    try:
              results["teams_notificado"] = _enviar_teams_adaptive_card(
                  reporte_id, cliente, tecnico_nombre, url_pptx, url_pdf, tipo_reporte)
except Exception as e:
        logger.error(f"Error Teams: {e}", exc_info=True)
        results["teams_error"] = str(e)
    if tecnico_upn:
              mensaje = f"Reporte enviado para aprobacion. Cliente: {cliente}"
        results["tecnico_notificado"] = _notificar_tecnico_graph(tecnico_upn, reporte_id, mensaje)
    _actualizar_estado_dataverse(reporte_id, "notificado")
    results["timestamp"] = datetime.now(timezone.utc).isoformat()
    return func.HttpResponse(json.dumps(results), status_code=200, mimetype="application/json")
