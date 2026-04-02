# /flows — Power Automate Exports

This directory contains exported Power Automate flow definitions (.json / .zip)
for the Multitel Reportes approval workflow.

## Flows

### 1. Reporte Aprobacion Flow
**Trigger:** HTTP webhook called by `fn_notificar` when a report is ready for review.

**Actions:**
1. Post Adaptive Card to supervisor Teams channel with:
   - Report details (cliente, nodo, tipo, fecha)
   - Links to OneDrive .pptx and .pdf files
   - Action buttons: **Aprobar** / **Rechazar** (with optional comment)
2. Wait for supervisor response (up to 72 hours)
3. Call `fn_aprobar` with the supervisor decision
4. Notify technician of the outcome

### 2. Reporte Recordatorio Flow
**Trigger:** Scheduled — runs every 24 hours.

**Actions:**
1. Query Dataverse for reports in `FirmaPendiente` state older than 48h
2. Send reminder card to supervisor Teams channel
3. Escalate to manager if older than 72h

## Deployment

1. Log in to [Power Automate](https://make.powerautomate.com) with a Multitel M365 account
2. Import the `.zip` files from this directory via **My flows > Import**
3. Configure the following connections:
   - Microsoft Teams connector (use the Multitel service account)
   - HTTP connector (point to APIM endpoint)
   - Dataverse connector (use the Multitel environment)
4. Enable both flows

## Environment Variables Required

| Variable | Description |
|---|---|
| `APIM_BASE_URL` | Base URL of Azure API Management |
| `APIM_SUBSCRIPTION_KEY` | API Management subscription key |
| `TEAMS_TEAM_ID` | ID of the Multitel Teams team |
| `TEAMS_CHANNEL_ID` | Channel ID for supervisor approvals |
| `DATAVERSE_ENVIRONMENT_URL` | Dataverse environment URL |

## Notes

- The Adaptive Card schema targets Teams Desktop v1.5+
- Approval buttons use Power Automate's built-in approval action for audit trail
- All HTTP calls use OAuth 2.0 with the Multitel Azure AD tenant
