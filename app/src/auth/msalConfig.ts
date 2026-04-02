/**
 * msalConfig.ts
  * Configuracion de Azure AD SSO con @azure/msal-react-native.
   * El token de acceso y refresh token se almacenan en Android Keystore
    * via expo-secure-store (nunca en AsyncStorage).
     */
     import Constants from 'expo-constants';

     const extra = Constants.expoConfig?.extra ?? {};

     // Configuracion del App Registration Azure AD
     export const MSAL_CONFIG = {
       auth: {
           clientId: extra.azureClientId ?? process.env.EXPO_PUBLIC_AZURE_CLIENT_ID ?? '',
               authority: `https://login.microsoftonline.com/${extra.azureTenantId ?? process.env.EXPO_PUBLIC_AZURE_TENANT_ID}`,
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
                                                           process.env.EXPO_PUBLIC_API_BASE_URL ??
                                                             'https://multitel-apim.azure-api.net';

                                                             export const APIM_SUBSCRIPTION_KEY =
                                                               process.env.EXPO_PUBLIC_APIM_SUBSCRIPTION_KEY ?? '';

                                                               // Roles de Azure AD App Roles
                                                               export const ROLES = {
                                                                 TECNICO: 'Tecnico',
                                                                   SUPERVISOR: 'Supervisor',
                                                                     ADMIN: 'Admin',
                                                                     } as const;

                                                                     export type AppRole = (typeof ROLES)[keyof typeof ROLES];
