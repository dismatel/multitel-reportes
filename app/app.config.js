// app.config.js
// NO usar plugin react-native-msal — causa TypeError en expo config
// El redirect URI de MSAL se configura via withAndroidManifest directamente

const { withAndroidManifest } = require('@expo/config-plugins');

// Plugin manual para agregar el redirect URI de MSAL al AndroidManifest
// sin cargar react-native-msal (que importa @azure/msal-browser incompatible con Node CJS)
const withMsalRedirectUri = (config) => {
  return withAndroidManifest(config, (config) => {
    const manifest = config.modResults;
    const app = manifest.manifest.application[0];

    if (!app.activity) app.activity = [];

    // Verificar si ya existe la actividad de MSAL
    const msalActivity = 'com.microsoft.identity.client.BrowserTabActivity';
    const exists = app.activity.some(
      (a) => a.$?.['android:name'] === msalActivity
    );

    if (!exists) {
      app.activity.push({
        $: {
          'android:name': msalActivity,
          'android:exported': 'true',
        },
        'intent-filter': [
          {
            action: [{ $: { 'android:name': 'android.intent.action.VIEW' } }],
            category: [
              { $: { 'android:name': 'android.intent.category.DEFAULT' } },
              { $: { 'android:name': 'android.intent.category.BROWSABLE' } },
            ],
            data: [
              {
                $: {
                  'android:scheme': 'msauth',
                  'android:host': 'com.multitel.reportes',
                  'android:path': '/callback',
                },
              },
            ],
          },
        ],
      });
    }

    return config;
  });
};

module.exports = {
  expo: {
    name: "Multitel Reportes",
    slug: "multitel-reportes",
    version: "1.0.0",
    orientation: "portrait",
    icon: "./assets/icon.png",
    userInterfaceStyle: "light",
    splash: {
      image: "./assets/splash.png",
      resizeMode: "contain",
      backgroundColor: "#3A3A3A",
    },
    ios: {
      supportsTablet: false,
      bundleIdentifier: "com.multitel.reportes",
    },
    android: {
      adaptiveIcon: {
        foregroundImage: "./assets/adaptive-icon.png",
        backgroundColor: "#3A3A3A",
      },
      package: "com.multitel.reportes",
      versionCode: 1,
      permissions: [
        "CAMERA",
        "ACCESS_FINE_LOCATION",
        "ACCESS_COARSE_LOCATION",
        "READ_EXTERNAL_STORAGE",
        "WRITE_EXTERNAL_STORAGE",
        "INTERNET",
        "ACCESS_NETWORK_STATE",
        "android.permission.CAMERA",
        "android.permission.RECORD_AUDIO",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_FINE_LOCATION",
      ],
      jsEngine: "hermes",
    },
    web: {
      favicon: "./assets/favicon.png",
    },
    plugins: [
      "expo-camera",
      [
        "expo-location",
        {
          locationAlwaysAndWhenInUsePermission:
            "Multitel Reportes necesita acceso a tu ubicacion para el stamp de coordenadas en las fotos de evidencia.",
        },
      ],
      [
        "expo-secure-store",
        {
          faceIDPermission:
            "Allow $(PRODUCT_NAME) to access your Face ID biometric data.",
        },
      ],
      withMsalRedirectUri,  // Plugin manual — NO carga @azure/msal-browser
    ],
    extra: {
      eas: {
        projectId: "63a17f1b-3954-4bc3-ac64-3a16821c946d",
      },
      azureTenantId: "66797fac-f1e9-48e6-9c02-a314295a1fb0",
      azureClientId: "a7c7e762-06b8-4072-8110-63eae1f65cf1",
      apiBaseUrl:
        "https://multitel-functions-etbzhzfbgbb2d8de.eastus2-01.azurewebsites.net",
    },
    owner: "multitel",
  },
};
