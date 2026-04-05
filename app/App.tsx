/**
 * app/App.tsx
 * Entry point — Multitel Reportes
 * Sets up MSAL, navigation and auth guard.
 * Token stored in Android Keystore via expo-secure-store. NEVER AsyncStorage.
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { StatusBar } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import MSALClient from 'react-native-msal';
import * as SecureStore from 'expo-secure-store';
import * as SplashScreen from 'expo-splash-screen';
import Constants from 'expo-constants';

import LoginScreen from './src/screens/LoginScreen';
import DashboardScreen from './src/screens/DashboardScreen';
import FormularioScreen from './src/screens/FormularioScreen';
import FotosScreen from './src/screens/FotosScreen';
import { COLORS } from './src/theme/colors';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export type RootStackParamList = {
  Login: undefined;
  Dashboard: undefined;
  Formulario: { reporteId?: string };
  Fotos: {
    slotKey: string;
    slotLabel: string;
    tipoReporte: 'PlantaExterna' | 'CPE';
    onPhotoCaptured: (uri: string) => void;
  };
};

const Stack = createNativeStackNavigator<RootStackParamList>();

SplashScreen.preventAutoHideAsync().catch(() => {});

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------
export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [appIsReady, setAppIsReady] = useState(false);

  // MSAL inicializado dentro del componente para evitar
  // que npx expo config falle al leer el módulo nativo
  const extra = Constants.expoConfig?.extra ?? {};
  const msalInstance = useRef(new MSALClient({
    auth: {
      clientId: extra.azureClientId ?? '',
      authority: `https://login.microsoftonline.com/${extra.azureTenantId ?? ''}`,
      redirectUri: 'msauth://com.multitel.reportes/callback',
    },
  })).current;

  useEffect(() => {
    initializeAuth();
  }, []);

  const initializeAuth = async () => {
    try {
      const cachedToken = await SecureStore.getItemAsync('msal_access_token');
      const tokenExpiry = await SecureStore.getItemAsync('msal_token_expiry');

      if (cachedToken && tokenExpiry) {
        const expiryTime = parseInt(tokenExpiry, 10);
        const now = Date.now();
        if (now < expiryTime - 60_000) {
          setIsAuthenticated(true);
        } else {
          const refreshed = await silentRefresh();
          setIsAuthenticated(refreshed);
        }
      } else {
        setIsAuthenticated(false);
      }
    } catch (error) {
      console.error('Auth init error:', error);
      setIsAuthenticated(false);
    } finally {
      setAppIsReady(true);
    }
  };

  const silentRefresh = async (): Promise<boolean> => {
    try {
      const accounts = await msalInstance.getAccounts();
      if (!accounts || accounts.length === 0) return false;

      const result = await msalInstance.acquireTokenSilent({
        scopes: ['User.Read', 'offline_access'],
        account: accounts[0],
        forceRefresh: false,
      });

      if (result?.accessToken) {
        await SecureStore.setItemAsync('msal_access_token', result.accessToken);
        const expiry = (result.expiresOn ?? Date.now() + 3600_000).toString();
        await SecureStore.setItemAsync('msal_token_expiry', expiry);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  };

  const onLayoutRootView = useCallback(async () => {
    if (appIsReady) {
      await SplashScreen.hideAsync();
    }
  }, [appIsReady]);

  if (!appIsReady || isAuthenticated === null) {
    return null;
  }

  return (
    <NavigationContainer onReady={onLayoutRootView}>
      <StatusBar
        barStyle="light-content"
        backgroundColor={COLORS.header}
        translucent={false}
      />
      <Stack.Navigator
        initialRouteName={isAuthenticated ? 'Dashboard' : 'Login'}
        screenOptions={{ headerShown: false }}
      >
        <Stack.Screen name="Login" component={LoginScreen} />
        <Stack.Screen name="Dashboard" component={DashboardScreen} />
        <Stack.Screen
          name="Formulario"
          component={FormularioScreen}
          options={{ animation: 'slide_from_right' }}
        />
        <Stack.Screen
          name="Fotos"
          component={FotosScreen}
          options={{ animation: 'slide_from_bottom' }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}