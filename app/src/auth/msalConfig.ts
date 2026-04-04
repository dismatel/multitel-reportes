/**
 * msalConfig.ts
 * Configuracion de Azure AD SSO con react-native-msal (no @azure/msal-react-native).
 */
import Constants from 'expo-constants';

const extra = Constants.expoConfig?.extra ?? {};

export const MSAL_CONFIG = {
  auth: {
    clientId: extra.azureClientId ?? '',
    authority: `https://login.microsoftonline.com/${extra.azureTenantId ?? ''}`,
    redirectUri: 'msauth://com.multitel.reportes/callback',
  },
  // ELIMINADO: cache.cacheLocation y cache.storeAuthStateInCookie
  // son propiedades de @azure/msal-browser, no de react-native-msal.
  // react-native-msal usa Android Keystore internamente.
};

export const AUTH_SCOPES = [
  'openid', 'profile', 'offline_access',
  `api://${extra.azureClientId ?? ''}/access_as_user`,
  'User.Read', 'Files.ReadWrite.All', 'Sites.ReadWrite.All',
];

export const GRAPH_SCOPES = [
  'https://graph.microsoft.com/User.Read',
  'https://graph.microsoft.com/Files.ReadWrite.All',
];

export const API_BASE_URL =
  extra.apiBaseUrl ?? 'https://multitel-apim.azure-api.net';

export const ROLES = {
  TECNICO: 'Tecnico', SUPERVISOR: 'Supervisor', ADMIN: 'Admin',
} as const;

export type AppRole = (typeof ROLES)[keyof typeof ROLES];