import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  StatusBar,
  Image,
  SafeAreaView,
} from 'react-native';
import { Svg, Circle, Line, G } from 'react-native-svg';
import * as ExpoSecureStore from 'expo-secure-store';
import {
  PublicClientApplication,
  InteractionRequiredAuthError,
} from '@azure/msal-react-native';

// ---- Constants ----
const TENANT_ID = process.env.EXPO_PUBLIC_AZURE_TENANT_ID ?? '';
const CLIENT_ID = process.env.EXPO_PUBLIC_AZURE_CLIENT_ID ?? '';
const ALLOWED_DOMAIN = '@multitel.com';
const APP_VERSION = '1.0.0';

const MSAL_CONFIG = {
  auth: {
    clientId: CLIENT_ID,
    authority: `https://login.microsoftonline.com/${TENANT_ID}`,
    redirectUri: 'msauth://com.multitel.reportes/callback',
  },
};

const msalInstance = new PublicClientApplication(MSAL_CONFIG);

// ---- SVG Logo: Multitel fiber-optic nodes ----
const MultitelLogo: React.FC = () => (
  <Svg width={120} height={80} viewBox="0 0 120 80">
    {/* Fiber lines */}
    <Line x1="20" y1="40" x2="60" y2="20" stroke="#6BBF2A" strokeWidth="2" />
    <Line x1="20" y1="40" x2="60" y2="60" stroke="#6BBF2A" strokeWidth="2" />
    <Line x1="60" y1="20" x2="100" y2="40" stroke="#6BBF2A" strokeWidth="2" />
    <Line x1="60" y1="60" x2="100" y2="40" stroke="#6BBF2A" strokeWidth="2" />
    <Line x1="60" y1="20" x2="60" y2="60" stroke="#6BBF2A" strokeWidth="1.5" strokeDasharray="3,3" />
    {/* Nodes */}
    <Circle cx="20" cy="40" r="5" fill="#6BBF2A" />
    <Circle cx="60" cy="20" r="5" fill="#6BBF2A" />
    <Circle cx="60" cy="60" r="5" fill="#6BBF2A" />
    <Circle cx="100" cy="40" r="7" fill="#6BBF2A" />
    {/* Center hub */}
    <Circle cx="60" cy="40" r="3" fill="#FFFFFF" />
  </Svg>
);

// ---- Microsoft logo: 4 colored squares ----
const MicrosoftLogo: React.FC = () => (
  <Svg width={20} height={20} viewBox="0 0 21 21">
    <G>
      <rect x="1" y="1" width="9" height="9" fill="#F25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
      <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
      <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
    </G>
  </Svg>
);

// ---- Main Component ----
const LoginScreen: React.FC = () => {
  const [loading, setLoading] = useState(false);

  const handleLogin = useCallback(async () => {
    setLoading(true);
    try {
      await msalInstance.initialize();

      const result = await msalInstance.acquireTokenInteractive({
        scopes: ['openid', 'profile', 'email', 'offline_access'],
      });

      const email: string = result.account?.username ?? '';

      // Domain validation — ONLY @multitel.com accounts allowed
      if (!email.toLowerCase().endsWith(ALLOWED_DOMAIN)) {
        Alert.alert(
          'Acceso denegado',
          `Solo cuentas ${ALLOWED_DOMAIN} pueden acceder a esta aplicación.`,
          [{ text: 'Entendido' }],
        );
        await msalInstance.signOut({ account: result.account });
        setLoading(false);
        return;
      }

      // Store tokens in Android Keystore via expo-secure-store (NOT AsyncStorage)
      await ExpoSecureStore.setItemAsync(
        'msal_access_token',
        result.accessToken,
        { keychainAccessible: ExpoSecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY },
      );
      if (result.idToken) {
        await ExpoSecureStore.setItemAsync(
          'msal_id_token',
          result.idToken,
          { keychainAccessible: ExpoSecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY },
        );
      }
      await ExpoSecureStore.setItemAsync(
        'user_email',
        email,
        { keychainAccessible: ExpoSecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY },
      );

      // Navigation handled by App.tsx token state listener
    } catch (error) {
      if (error instanceof InteractionRequiredAuthError) {
        Alert.alert('Sesión requerida', 'Por favor inicia sesión para continuar.');
      } else {
        Alert.alert('Error de autenticación', 'No se pudo iniciar sesión. Intenta de nuevo.');
      }
      console.error('[LoginScreen] auth error:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor="#3A3A3A" />

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Multitel Reportes</Text>
      </View>

      {/* Body */}
      <View style={styles.body}>
        {/* Logo */}
        <View style={styles.logoContainer}>
          <MultitelLogo />
          <Text style={styles.companyName}>Multitel S.A. de C.V.</Text>
          <Text style={styles.tagline}>Sistema de Reportes de Fibra Óptica</Text>
        </View>

        {/* Login Button */}
        <TouchableOpacity
          style={[styles.loginButton, loading && styles.loginButtonDisabled]}
          onPress={handleLogin}
          disabled={loading}
          activeOpacity={0.85}
          accessibilityLabel="Continuar con Microsoft 365"
          accessibilityRole="button"
        >
          {loading ? (
            <ActivityIndicator color="#FFFFFF" size="small" />
          ) : (
            <View style={styles.loginButtonInner}>
              <MicrosoftLogo />
              <Text style={styles.loginButtonText}>Continuar con Microsoft 365</Text>
            </View>
          )}
        </TouchableOpacity>

        <Text style={styles.hint}>
          Usa tu cuenta corporativa @multitel.com
        </Text>
      </View>

      {/* Footer */}
      <View style={styles.footer}>
        <View style={styles.securityBadge}>
          <View style={styles.secureDot} />
          <Text style={styles.securityText}>Conexión segura · Azure AD</Text>
        </View>
        <Text style={styles.version}>v{APP_VERSION}</Text>
      </View>
    </SafeAreaView>
  );
};

export default LoginScreen;

// ---- Styles ----
const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#F5F6F8',
  },
  header: {
    backgroundColor: '#3A3A3A',
    height: 56,
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
  },
  headerTitle: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  body: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  logoContainer: {
    alignItems: 'center',
    marginBottom: 48,
  },
  companyName: {
    fontSize: 22,
    fontWeight: '700',
    color: '#3A3A3A',
    marginTop: 12,
    letterSpacing: 0.3,
  },
  tagline: {
    fontSize: 13,
    color: '#666666',
    marginTop: 4,
    textAlign: 'center',
  },
  loginButton: {
    backgroundColor: '#3A3A3A',
    borderRadius: 8,
    paddingVertical: 14,
    paddingHorizontal: 24,
    width: '100%',
    maxWidth: 320,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 3,
  },
  loginButtonDisabled: {
    opacity: 0.6,
  },
  loginButtonInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  loginButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
    letterSpacing: 0.2,
  },
  hint: {
    marginTop: 16,
    fontSize: 12,
    color: '#888888',
    textAlign: 'center',
  },
  footer: {
    paddingBottom: 24,
    alignItems: 'center',
    gap: 6,
  },
  securityBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F0F7F0',
    borderRadius: 20,
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: '#3A7D1A',
    gap: 6,
  },
  secureDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#6BBF2A',
  },
  securityText: {
    fontSize: 12,
    color: '#3A7D1A',
    fontWeight: '500',
  },
  version: {
    fontSize: 11,
    color: '#AAAAAA',
  },
});
