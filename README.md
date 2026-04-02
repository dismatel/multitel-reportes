# Multitel Reportes

**App Android para tecnicos de campo de Multitel S.A. de C.V.**
Digitaliza reportes de instalacion de fibra optica con Azure Functions, Dataverse, Power Automate y OneDrive.

---

## Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| App movil | React Native + Expo (Android) |
| Backend | Azure Functions Python (serverless) |
| Base de datos | Microsoft Dataverse |
| Flujos | Power Automate |
| Almacenamiento | OneDrive via Microsoft Graph API |
| Autenticacion | Azure Active Directory SSO |
| Documentos | python-pptx + LibreOffice headless (Durable Function) |
| CI/CD | GitHub Actions + EAS Build |

---

## Estructura del Repositorio

```
multitel-reportes/
├── app/                          # React Native (Expo) — App Android
│   ├── src/
│   │   ├── auth/                 # Configuracion MSAL Azure AD
│   │   ├── screens/              # LoginScreen, DashboardScreen, FormularioScreen, FotosScreen
│   │   ├── theme/                # Colores e identidad visual Multitel
│   │   └── components/           # Componentes reutilizables
│   ├── app.json                  # Configuracion Expo
│   └── package.json
├── functions/                    # Azure Functions Python
│   ├── fn_guardar_reporte/       # Guarda reporte en Dataverse (rol: Tecnico)
│   ├── fn_generar_pptx/          # Durable Function: genera PPTX + PDF (rol: Tecnico)
│   ├── fn_subir_onedrive/        # Sube archivos a OneDrive (rol: Tecnico/Supervisor)
│   ├── fn_notificar/             # Notifica via Teams + Graph API (rol: Tecnico/Supervisor)
│   ├── shared/                   # auth.py — middleware JWT + Play Integrity + RBAC
│   ├── host.json                 # Configuracion Azure Functions host
│   └── requirements.txt
├── .github/workflows/
│   ├── test.yml                  # pytest + Jest en cada PR
│   ├── deploy-functions.yml      # Deploy Azure Functions en push a main
│   └── build-android.yml         # EAS Build APK firmado
├── flows/                        # Exportaciones Power Automate
├── scripts/
│   └── env.example               # Variables de entorno (plantilla)
└── docs/                         # Documentacion tecnica
```

---

## Configuracion Inicial

### 1. Registro de Aplicacion Azure AD

1. Ir a [portal.azure.com](https://portal.azure.com) > Azure Active Directory > App registrations
2. 2. Nuevo registro con estos parametros:
   3.    - **Nombre**: `Multitel Reportes`
         -    - **Tipo de cuenta**: Solo este directorio organizativo (single tenant)
              -    - **Redirect URI**: `msauth://com.multitel.reportes/callback`
                   - 3. Agregar permisos Graph API (Delegados):
                     4.    - `User.Read`, `Sites.ReadWrite.All`, `Files.ReadWrite.All`
                           -    - `Sites.Manage.All`, `offline_access`, `openid`, `profile`
                                - 4. Guardar `CLIENT_ID` y `TENANT_ID`
                                 
                                  5. ### 2. Configurar Secrets en GitHub
                                 
                                  6. Agregar los siguientes secrets en Settings > Secrets and variables > Actions:
                                 
                                  7. ```
                                     AZURE_CREDENTIALS          # JSON de Service Principal
                                     AZURE_TENANT_ID
                                     AZURE_CLIENT_ID
                                     AZURE_RESOURCE_GROUP
                                     DATAVERSE_URL
                                     SHAREPOINT_SITE_ID
                                     APIM_BASE_URL
                                     APIM_SUBSCRIPTION_KEY
                                     TEAMS_WEBHOOK_SUPERVISORES
                                     TEAMS_TEAM_ID
                                     TEAMS_CHANNEL_ID
                                     PLAY_INTEGRITY_DECRYPTION_KEY
                                     PLAY_INTEGRITY_VERIFICATION_KEY
                                     EXPO_TOKEN
                                     EAS_PROJECT_ID
                                     AZURE_FUNCTIONS_MASTER_KEY
                                     CODECOV_TOKEN
                                     ```

                                     ### 3. Configurar Variables de Entorno

                                     ```bash
                                     cp scripts/env.example scripts/.env
                                     # Editar scripts/.env con los valores reales
                                     ```

                                     ---

                                     ## Desarrollo Local

                                     ### Azure Functions

                                     ```bash
                                     cd functions
                                     python -m venv .venv
                                     source .venv/bin/activate  # Linux/Mac
                                     pip install -r requirements.txt
                                     pip install azure-functions-core-tools

                                     # Ejecutar localmente
                                     func start
                                     ```

                                     ### App React Native

                                     ```bash
                                     cd app
                                     npm install

                                     # Configurar variables de entorno
                                     cp ../.env.example .env.local
                                     # Editar .env.local

                                     # Iniciar desarrollo
                                     npx expo start --android
                                     ```

                                     ---

                                     ## CI/CD

                                     | Workflow | Disparo | Descripcion |
                                     |---|---|---|
                                     | `test.yml` | PR a main/develop | pytest (Functions) + Jest (App) + CodeQL |
                                     | `deploy-functions.yml` | Push a main | Deploy Azure Functions en produccion |
                                     | `build-android.yml` | Push a main o tag v*.*.* | EAS Build APK firmado |

                                     ---

                                     ## Seguridad

                                     - **Autenticacion**: Azure AD SSO en CADA request — ninguna funcion es publica
                                     - - **Tokens**: Almacenados en Android Keystore (expo-secure-store) — NUNCA AsyncStorage
                                       - - **RBAC**: `fn_guardar_reporte` solo acepta rol `Tecnico`; `fn_aprobar` solo acepta `Supervisor`
                                         - - **Play Integrity**: Backend rechaza APKs no firmados por Multitel
                                           - - **ProGuard/R8**: Habilitado en builds de release
                                             - - **Hashes SHA-256**: Calculados para cada .pptx y .pdf, guardados en Dataverse
                                               - - **Rate Limiting**: 60 req/min por usuario via Azure API Management
                                                 - - **HTTPS only**: Todas las comunicaciones cifradas
                                                  
                                                   - ---

                                                   ## Tipos de Reporte

                                                   ### Planta Externa (Diapositivas 1-9)
                                                   Portada, datos del nodo, punta inicial/final, reservas de cable 1-5, cambios de nodo, materiales, aprobaciones

                                                   ### CPE (Diapositivas 10-18)
                                                   Portada, rack previo/posterior, etiquetas CPE/LIU/ODF/Switch, mediciones opticas, ADA, ODI, materiales (patchcords), aprobaciones

                                                   ---

                                                   ## Identidad Visual

                                                   | Elemento | Color | Hex |
                                                   |---|---|---|
                                                   | Header/navbar | Gris oscuro Multitel | `#3A3A3A` |
                                                   | Accion primaria | Verde Multitel | `#6BBF2A` |
                                                   | Boton "Generar y guardar" | Gris oscuro | `#3A3A3A` |
                                                   | Checkboxes activos, pasos completados | Verde Multitel | `#6BBF2A` |
                                                   | Fondo general | Gris claro | `#F5F6F8` |

                                                   ---

                                                   ## Stamp GPS en Fotos

                                                   Las fotos de evidencia tienen el stamp quemado con:
                                                   - **Linea 1**: `● {tecnico} · Multitel S.A. de C.V.`
                                                   - - **Linea 2**: `{lat}°N {lon}°W · {direccion via Nominatim OSM}`
                                                     - - **Linea 3**: `{fecha ISO} · {hora} CST`
                                                      
                                                       - Fondo `rgba(0,0,0,0.72)`, fuente monoespaciada blanca.
                                                       - Si el GPS no esta disponible, bloquea el avance con alerta.
                                                      
                                                       - ---

                                                       ## Flujo Completo del Reporte

                                                       ```
                                                       Tecnico abre app
                                                           ↓ Login Azure AD SSO (token en Android Keystore)
                                                           ↓ Dashboard (lista reportes del mes)
                                                           ↓ Nuevo Reporte → FormularioScreen (5 pasos)
                                                               1. Portada (tipo, cliente, datos basicos)
                                                               2. Datos tecnicos y mediciones
                                                               3. Materiales (checkboxes + cantidades)
                                                               4. Fotos (expo-camera + GPS stamp)
                                                               5. Firmas digitales
                                                           ↓ fn_guardar_reporte → Dataverse (estado: borrador)
                                                           ↓ fn_generar_pptx (Durable) → .pptx + .pdf (job_id)
                                                           ↓ fn_subir_onedrive → /Multitel/Reportes/{ID}/
                                                           ↓ fn_notificar → Teams (card con Aprobar/Rechazar) + push al tecnico
                                                           ↓ Supervisor Aprobar/Rechazar en Teams
                                                           ↓ Dataverse actualizado (estado: aprobado/rechazado)
                                                       ```

                                                       ---

                                                       ## Contribucion

                                                       1. Fork del repositorio
                                                       2. 2. Crear rama feature: `git checkout -b feature/mi-feature`
                                                          3. 3. Commit con mensaje descriptivo
                                                             4. 4. Push y crear Pull Request a `develop`
                                                                5. 5. Los tests deben pasar antes del merge
                                                                  
                                                                   6. ---
                                                                  
                                                                   7. ## Licencia
                                                                  
                                                                   8. Propietario — Multitel S.A. de C.V. — Todos los derechos reservados.
                                                                  
                                                                   9. ---
                                                                  
                                                                   10. *Desarrollado con React Native, Expo, Azure Functions, Microsoft 365 y Power Platform.*
