# Guia de Configuracion Azure — Multitel Reportes

## Paso 1: Registro de Aplicacion Azure AD

### Parametros del App Registration

| Campo | Valor |
|---|---|
| **Nombre** | `Multitel Reportes` |
| **Tipo de cuenta** | Solo este directorio organizativo (single tenant) |
| **Redirect URI** | `msauth://com.multitel.reportes/callback` |
| **Plataforma** | Mobile and desktop applications |

### Permisos Graph API Requeridos

#### Permisos Delegados (necesitan consentimiento del usuario)
| Permission | Uso |
|---|---|
| `User.Read` | Obtener perfil del usuario autenticado |
| `Sites.ReadWrite.All` | Leer/escribir en SharePoint |
| `Files.ReadWrite.All` | Subir archivos a OneDrive |
| `Sites.Manage.All` | Crear carpetas en SharePoint |
| `offline_access` | Obtener refresh tokens |
| `openid` | Autenticacion OpenID Connect |
| `profile` | Datos del perfil del usuario |

### App Roles (para RBAC)

Crear los siguientes roles en el App Registration:
| ID | Display Name | Valor | Descripcion |
|---|---|---|---|
| (generado) | Tecnico | `Tecnico` | Tecnicos de campo — pueden crear reportes |
| (generado) | Supervisor | `Supervisor` | Supervisores — pueden aprobar reportes |
| (generado) | Admin | `Admin` | Administradores del sistema |

### API Scope (para autorizacion del backend)

1. En el App Registration ir a **Expose an API**
2. Agregar scope: `access_as_user`
3. URI del Application ID: `api://[CLIENT_ID]`
4. El scope completo queda: `api://[CLIENT_ID]/access_as_user`

---

## Paso 2: Azure Function App

### Configuracion

```bash
# Crear Function App
az functionapp create \
  --name multitel-reportes-fn \
    --resource-group rg-multitel-reportes \
      --storage-account multitelreportesst \
        --consumption-plan-location eastus \
          --runtime python \
            --runtime-version 3.11 \
              --functions-version 4 \
                --os-type Linux

                  # Habilitar Managed Identity
                  az functionapp identity assign \
                    --name multitel-reportes-fn \
                      --resource-group rg-multitel-reportes
                      ```

                      ### Asignar Permisos a Managed Identity

                      ```bash
                      # Obtener el Object ID de la Managed Identity
                      PRINCIPAL_ID=$(az functionapp identity show \
                        --name multitel-reportes-fn \
                          --resource-group rg-multitel-reportes \
                            --query principalId -o tsv)

                            # Asignar rol en Dataverse (necesita Dynamics 365 Admin)
                            # Se hace desde el centro de administracion de Power Platform

                            # Asignar permisos Graph API a la Managed Identity
                            az ad app permission grant \
                              --id $PRINCIPAL_ID \
                                --api 00000003-0000-0000-c000-000000000000 \
                                  --scope "Files.ReadWrite.All Sites.ReadWrite.All User.Read"
                                  ```

                                  ---

                                  ## Paso 3: Azure API Management (Rate Limiting)

                                  ### Crear APIM

                                  ```bash
                                  az apim create \
                                    --name multitel-apim \
                                      --resource-group rg-multitel-reportes \
                                        --publisher-name "Multitel S.A. de C.V." \
                                          --publisher-email admin@grupomultitel.com \
                                            --sku-name Consumption
                                            ```

                                            ### Politica de Rate Limiting (60 req/min por usuario)

                                            ```xml
                                            <policies>
                                              <inbound>
                                                  <rate-limit-by-key calls="60" renewal-period="60"
                                                        counter-key="@(context.Request.Headers.GetValueOrDefault("Authorization",""))"
                                                              increment-condition="@(context.Response.StatusCode >= 200 && context.Response.StatusCode < 300)"
                                                                    remaining-calls-header-name="X-RateLimit-Remaining"
                                                                          retry-after-header-name="Retry-After" />
                                                                              <base />
                                                                                </inbound>
                                                                                </policies>
                                                                                ```

                                                                                ---

                                                                                ## Paso 4: Microsoft Dataverse

                                                                                ### Entidades Requeridas

                                                                                #### multitel_reporte
                                                                                | Campo | Tipo | Descripcion |
                                                                                |---|---|---|
                                                                                | `multitel_reporteid` | Unique Identifier | ID unico del reporte |
                                                                                | `multitel_tiporeporte` | Text | planta_externa / cpe |
                                                                                | `multitel_cliente` | Text | Nombre del cliente |
                                                                                | `multitel_idservicio` | Text | ID del servicio |
                                                                                | `multitel_encargadogrupo` | Text | Nombre del encargado |
                                                                                | `multitel_fecha` | DateTime | Fecha del reporte |
                                                                                | `multitel_estado` | Text | borrador/generando/pendiente_aprobacion/aprobado/rechazado |
                                                                                | `multitel_tecnicoid` | Text | ID del tecnico |
                                                                                | `multitel_tecniconombre` | Text | Nombre del tecnico |
                                                                                | `multitel_upntecnico` | Text | UPN Azure AD del tecnico |
                                                                                | `multitel_datostecnicos` | Multiline Text | JSON con datos tecnicos |
                                                                                | `multitel_materiales` | Multiline Text | JSON con materiales |
                                                                                | `multitel_patchcords` | Multiline Text | JSON con patchcords |
                                                                                | `multitel_fotos` | Multiline Text | JSON con metadatos de fotos |
                                                                                | `multitel_url_pptx` | Text | URL OneDrive del PPTX |
                                                                                | `multitel_url_pdf` | Text | URL OneDrive del PDF |
                                                                                | `multitel_hashsha256_pptx` | Text | Hash SHA-256 del PPTX |
                                                                                | `multitel_hashsha256_pdf` | Text | Hash SHA-256 del PDF |
                                                                                | `multitel_fechacreacion` | DateTime | Fecha de creacion |
                                                                                | `multitel_fechageneracion` | DateTime | Fecha de generacion del documento |
                                                                                | `multitel_fechasubida` | DateTime | Fecha de subida a OneDrive |
                                                                                | `multitel_fechanotificacion` | DateTime | Fecha de notificacion |

                                                                                ---

                                                                                ## Paso 5: Power Automate — Flujo de Aprobacion

                                                                                ### Trigger
                                                                                HTTP Request a `/api/fn_aprobar` desde Teams Adaptive Card

                                                                                ### Pasos del Flujo
                                                                                1. **Trigger**: Boton Aprobar/Rechazar en Teams
                                                                                2. **Verificar token**: Validar JWT del supervisor
                                                                                3. **Actualizar Dataverse**: Cambiar estado a `aprobado` o `rechazado`
                                                                                4. **Notificar tecnico**: Enviar mensaje Teams al tecnico
                                                                                5. **Archivar en SharePoint**: Mover a carpeta de archivados

                                                                                ### Variables del Flujo
                                                                                - `reporte_id`: ID del reporte
                                                                                - `accion`: "aprobar" o "rechazar"
                                                                                - `supervisor_upn`: UPN del supervisor que aprueba/rechaza
                                                                                - `comentario`: Comentario opcional del supervisor

                                                                                ---

                                                                                ## Paso 6: Microsoft Teams — Configuracion de Notificaciones

                                                                                ### Opcion 1: Incoming Webhook (Recomendado para inicio)
                                                                                1. En Teams, ir al canal de supervisores
                                                                                2. Configuracion > Conectores > Incoming Webhook
                                                                                3. Crear y copiar la URL del webhook
                                                                                4. Guardar en `TEAMS_WEBHOOK_SUPERVISORES`

                                                                                ### Opcion 2: Graph API (Produccion)
                                                                                Requiere permisos adicionales en el App Registration:
                                                                                - `ChannelMessage.Send`
                                                                                - `Chat.Create`
                                                                                - `Chat.ReadWrite`

                                                                                ---

                                                                                ## Verificacion Final

                                                                                ```bash
                                                                                # Verificar Function App
                                                                                curl -X POST https://multitel-reportes-fn.azurewebsites.net/api/fn_guardar_reporte \
                                                                                  -H "Authorization: Bearer [TOKEN]" \
                                                                                    -H "Content-Type: application/json" \
                                                                                      -d '{"tipo_reporte": "planta_externa", "cliente": "Test"}'

                                                                                      # Esperado: 422 (datos incompletos) o 201 (creado exitosamente)
                                                                                      ```
