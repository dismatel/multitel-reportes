/**
 * msalConfig.ts
 * Configuracion de Azure AD SSO con @azure/msal-react-native.
 * El token de acceso y refresh token se almacenan en Android Keystore
 * via expo-secure-store (nunca en AsyncStorage).
 *
 * SEGURIDAD: Ningun secreto (APIM key, client secrets) se expone en el
 * bundle del cliente. Los valores sensibles se inyectan en build-time
 * exclusivamente via EAS Secrets (extra.*) y nunca via EXPO_PUBLIC_*.
 * La APIM Subscription Key es manejada unicamente por el backend
 * (Azure Functions), jamas por la app movil.
 */
import Constants from 'expo-constants';

const extra = Constants.expoConfig?.extra ?? {};

// Configuracion del App Registration Azure AD
// NOTA: azureClientId y azureTenantId se inyectan via EAS Secrets
// en eas.json > build > env (sin prefijo EXPO_PUBLIC_).
export const MSAL_CONFIG = {
   auth: {
        clientId: extra.azureClientId ?? '',
        authority: `https://login.microsoftonline.com/${extra.azureTenantId ?? ''}`,
        redirectUri: 'msauth://com.multitel.reportes/callback',
   },
   cache: {
        // Usar SecureStorage (Android Keystore) en lugar de AsyncStorage
     cacheLocation: 'secureStorage',
        storeAuthStateInCookie: false,
   },
};

// Scopes requeridos por la app
export const AUTH_SCOPES = [
   'openid',
   'profile',
   'offline_access',
   `api://${extra.azureClientId ?? ''}/access_as_user`,
   'User.Read',
   'Files.ReadWrite.All',
   'Sites.ReadWrite.All',
 ];

// Scopes para Graph API
export const GRAPH_SCOPES = [
   'https://graph.microsoft.com/User.Read',
   'https://graph.microsoft.com/Files.ReadWrite.All',
 ];

export const API_BASE_URL =
   extra.apiBaseUrl ??
   'https://multitel-apim.azure-api.net';

// FIX [A-1 ALTO-SEGURIDAD]: APIM_SUBSCRIPTION_KEY eliminada del cliente.
// Esta clave es un secreto de backend y NUNCA debe enviarse desde la app movil.
// El bundle APK es extraible y cualquier valor EXPO_PUBLIC_* queda expuesto
// en texto plano dentro del JS bundle.
// La autenticacion hacia APIM se realiza via Bearer token (MSAL/Azure AD),
// que es el mecanismo de seguridad correcto. Si se requiere subscription key,
// debe ser agregada por el Azure Function backend usando su variable de
// entorno APIM_SUBSCRIPTION_KEY (sin prefijo EXPO_PUBLIC_).
//
// export const APIM_SUBSCRIPTION_KEY = ...  <-- ELIMINADO INTENCIONALMENTE

// Roles de Azure AD App Roles
export const ROLES = {
   TECNICO: 'Tecnico',
   SUPERVISOR: 'Supervisor',
   ADMIN: 'Admin',
} as const;

export type AppRole = (typeof ROLES)[keyof typeof ROLES];
 
