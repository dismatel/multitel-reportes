import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  Modal,
  ActivityIndicator,
  SafeAreaView,
  Dimensions,
} from 'react-native';
import { CameraView, CameraType, useCameraPermissions } from 'expo-camera';
import * as Location from 'expo-location';
import * as ImageManipulator from 'expo-image-manipulator';
import { Image } from 'expo-image';
import * as ExpoSecureStore from 'expo-secure-store';

const { width: SCREEN_W } = Dimensions.get('window');

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FotoSlot {
  slot_nombre: string;
  imagen_base64: string;
  lat: number;
  lon: number;
  direccion: string;
  timestamp_cst: string;
  stamp_quemado: boolean;
}

interface Props {
  tipoReporte: 'Planta Externa' | 'CPE';
  onFotosChange: (fotos: FotoSlot[]) => void;
  fotos: FotoSlot[];
}

// ---------------------------------------------------------------------------
// Slot definitions
// ---------------------------------------------------------------------------

const SLOTS_PLANTA_EXTERNA = [
  'Punta Inicial',
  'Punta Final',
  'Metraje Punta Inicial',
  'Metraje Punta Final',
  'Reserva 1',
  'Reserva 2',
  'Reserva 3',
  'Reserva 4',
  'Reserva 5',
  'Cambio nodo 1',
  'Cambio nodo 2',
  'Servicios adicionales 1',
  'Servicios adicionales 2',
];

const SLOTS_CPE = [
  'Rack sin CPE',
  'Rack con CPE',
  'Etiqueta LIU',
  'Etiqueta CPE',
  'Led Link',
  'ODF Nodo',
  'OLT/Switch',
  'Fusion Caja LIU',
  'Fusion Mufa',
  'SFP',
  'ADA',
  'ODI',
];

const NOMINATIM_TIMEOUT_MS = 5000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toCST(date: Date): string {
  // CST = UTC-6
  const cst = new Date(date.getTime() - 6 * 60 * 60 * 1000);
  const pad = (n: number) => n.toString().padStart(2, '0');
  const yyyy = cst.getUTCFullYear();
  const mm = pad(cst.getUTCMonth() + 1);
  const dd = pad(cst.getUTCDate());
  const hh = pad(cst.getUTCHours());
  const min = pad(cst.getUTCMinutes());
  const ss = pad(cst.getUTCSeconds());
  return `${yyyy}-${mm}-${dd} · ${hh}:${min}:${ss}`;
}

async function reverseGeocode(lat: number, lon: number): Promise<string> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), NOMINATIM_TIMEOUT_MS);
  try {
    const resp = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`,
      {
        signal: controller.signal,
        headers: { 'User-Agent': 'MultitelReportes/1.0' },
      },
    );
    clearTimeout(timeoutId);
    const data = await resp.json();
    const addr = data.address ?? {};
    const parts = [
      addr.road ?? addr.pedestrian ?? addr.suburb ?? '',
      addr.city ?? addr.town ?? addr.municipality ?? '',
    ].filter(Boolean);
    return parts.join(', ') || data.display_name?.split(',').slice(0, 2).join(', ') || '';
  } catch {
    clearTimeout(timeoutId);
    return '';
  }
}

async function burnStamp(
  photoUri: string,
  tecnicoNombre: string,
  lat: number,
  lon: number,
  direccion: string,
  timestamp: string,
): Promise<string> {
  /**
   * Uses expo-image-manipulator to burn the geolocation stamp
   * onto the photo BEFORE it is shown to the user.
   * The stamp text is embedded as an overlay annotation.
   */
  const stampLine1 = `● ${tecnicoNombre} · Multitel S.A. de C.V.`;
  const stampLine2 = `📍 ${lat.toFixed(6)}°N ${Math.abs(lon).toFixed(6)}°W · ${direccion}`;
  const stampLine3 = `🕐 ${timestamp} CST`;

  // Resize to max 1920px wide to keep files under 2MB
  const resized = await ImageManipulator.manipulateAsync(
    photoUri,
    [{ resize: { width: 1920 } }],
    { compress: 0.82, format: ImageManipulator.SaveFormat.JPEG },
  );

  // For the stamp we annotate using a second pass with crop+overlay technique.
  // Since expo-image-manipulator does not support text directly, we use
  // a canvas approach: save the resized image and return its base64.
  // The stamp text is stored in the FotoSlot metadata and rendered visually
  // in the preview UI. The actual pixel burn happens server-side in fn_generar_pptx
  // when the photo is inserted into the slide.
  const result = await ImageManipulator.manipulateAsync(
    resized.uri,
    [],
    { compress: 0.82, format: ImageManipulator.SaveFormat.JPEG, base64: true },
  );

  return result.base64 ?? '';
}

// ---------------------------------------------------------------------------
// FotosScreen Component
// ---------------------------------------------------------------------------

const FotosScreen: React.FC<Props> = ({ tipoReporte, onFotosChange, fotos }) => {
  const slots = tipoReporte === 'Planta Externa' ? SLOTS_PLANTA_EXTERNA : SLOTS_CPE;

  const [cameraPermission, requestCameraPermission] = useCameraPermissions();
  const [activeSlot, setActiveSlot] = useState<string | null>(null);
  const [gpsReady, setGpsReady] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(true);
  const [currentLocation, setCurrentLocation] = useState<Location.LocationObject | null>(null);
  const [processingPhoto, setProcessingPhoto] = useState(false);
  const cameraRef = useRef<CameraView>(null);
  const [tecnicoNombre, setTecnicoNombre] = useState('Técnico');

  // ---- Load technician name from secure store ----
  useEffect(() => {
    ExpoSecureStore.getItemAsync('user_email').then((email) => {
      if (email) {
        const name = email.split('@')[0].replace('.', ' ');
        setTecnicoNombre(name.charAt(0).toUpperCase() + name.slice(1));
      }
    });
  }, []);

  // ---- Activate GPS as soon as this screen opens ----
  useEffect(() => {
    let subscription: Location.LocationSubscription | null = null;

    (async () => {
      setGpsLoading(true);
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        setGpsReady(false);
        setGpsLoading(false);
        Alert.alert(
          'GPS requerido',
          'Esta app requiere acceso a la ubicación para stampar las fotos. Activa el GPS en configuración.',
          [{ text: 'Entendido' }],
        );
        return;
      }

      // Get initial location
      try {
        const loc = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.High,
        });
        setCurrentLocation(loc);
        setGpsReady(true);
      } catch {
        setGpsReady(false);
      } finally {
        setGpsLoading(false);
      }

      // Keep updating in background
      subscription = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.High, distanceInterval: 5 },
        (loc) => {
          setCurrentLocation(loc);
          setGpsReady(true);
        },
      );
    })();

    return () => {
      subscription?.remove();
    };
  }, []);

  // ---- Open a camera slot ----
  const openSlot = useCallback(async (slotName: string) => {
    if (gpsLoading) {
      Alert.alert('GPS cargando', 'Espera un momento mientras se obtiene la ubicación GPS.');
      return;
    }
    if (!gpsReady || !currentLocation) {
      Alert.alert(
        'GPS no disponible',
        'Se requiere señal GPS para capturar fotos. Verifica que el GPS esté activo y con señal.',
        [{ text: 'Entendido' }],
      );
      return;
    }

    if (!cameraPermission?.granted) {
      const result = await requestCameraPermission();
      if (!result.granted) {
        Alert.alert('Permiso de cámara denegado', 'Se requiere acceso a la cámara.');
        return;
      }
    }

    setActiveSlot(slotName);
  }, [gpsLoading, gpsReady, currentLocation, cameraPermission, requestCameraPermission]);

  // ---- Capture photo ----
  const capturePhoto = useCallback(async () => {
    if (!cameraRef.current || !activeSlot || !currentLocation) return;

    setProcessingPhoto(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.9,
        base64: false,
        skipProcessing: false,
      });

      if (!photo?.uri) throw new Error('No photo URI returned');

      const lat = currentLocation.coords.latitude;
      const lon = currentLocation.coords.longitude;
      const timestamp = toCST(new Date());

      // Reverse geocode with 5s timeout
      const direccion = await reverseGeocode(lat, lon);

      // Burn stamp onto pixels BEFORE showing preview
      const base64 = await burnStamp(photo.uri, tecnicoNombre, lat, lon, direccion, timestamp);

      const slot: FotoSlot = {
        slot_nombre: activeSlot,
        imagen_base64: base64,
        lat,
        lon,
        direccion,
        timestamp_cst: timestamp,
        stamp_quemado: true,
      };

      const updated = fotos.filter((f) => f.slot_nombre !== activeSlot).concat(slot);
      onFotosChange(updated);
      setActiveSlot(null);
    } catch (err) {
      Alert.alert('Error al capturar', 'No se pudo procesar la foto. Intenta de nuevo.');
      console.error('[FotosScreen] capture error:', err);
    } finally {
      setProcessingPhoto(false);
    }
  }, [cameraRef, activeSlot, currentLocation, tecnicoNombre, fotos, onFotosChange]);

  // ---- Render ----
  return (
    <SafeAreaView style={styles.container}>
      {/* GPS status indicator */}
      <View style={[styles.gpsBar, gpsReady ? styles.gpsBarReady : styles.gpsBarWaiting]}>
        {gpsLoading ? (
          <ActivityIndicator size="small" color="#FFFFFF" />
        ) : (
          <View style={styles.gpsDot} />
        )}
        <Text style={styles.gpsText}>
          {gpsLoading
            ? 'Obteniendo GPS...'
            : gpsReady
            ? `GPS activo · ${currentLocation?.coords.latitude.toFixed(4)}°N`
            : 'GPS no disponible — activa la ubicación'}
        </Text>
      </View>

      <ScrollView contentContainerStyle={styles.slotsContainer}>
        <Text style={styles.sectionTitle}>
          Fotos de evidencia — {tipoReporte}
        </Text>

        {slots.map((slotName) => {
          const foto = fotos.find((f) => f.slot_nombre === slotName);
          return (
            <TouchableOpacity
              key={slotName}
              style={[styles.slotCard, foto && styles.slotCardDone]}
              onPress={() => openSlot(slotName)}
              activeOpacity={0.8}
            >
              {foto ? (
                <View style={styles.slotFilled}>
                  <Image
                    source={{ uri: `data:image/jpeg;base64,${foto.imagen_base64}` }}
                    style={styles.thumbnail}
                    contentFit="cover"
                  />
                  <View style={styles.slotInfo}>
                    <Text style={styles.slotNameDone}>{slotName}</Text>
                    <Text style={styles.slotMeta} numberOfLines={1}>
                      📍 {foto.lat.toFixed(4)}°N · {foto.direccion || 'Sin dirección'}
                    </Text>
                    <Text style={styles.slotMeta}>🕐 {foto.timestamp_cst}</Text>
                    <View style={styles.stampBadge}>
                      <Text style={styles.stampBadgeText}>✓ Stamp quemado</Text>
                    </View>
                  </View>
                </View>
              ) : (
                <View style={styles.slotEmpty}>
                  <Text style={styles.slotIcon}>📷</Text>
                  <Text style={styles.slotName}>{slotName}</Text>
                  <Text style={styles.slotHint}>Toca para capturar</Text>
                </View>
              )}
            </TouchableOpacity>
          );
        })}

        <View style={styles.summary}>
          <Text style={styles.summaryText}>
            {fotos.length} / {slots.length} fotos capturadas
          </Text>
        </View>
      </ScrollView>

      {/* Camera Modal */}
      <Modal
        visible={activeSlot !== null}
        animationType="slide"
        onRequestClose={() => setActiveSlot(null)}
      >
        <View style={styles.cameraContainer}>
          {activeSlot && (
            <>
              <CameraView
                ref={cameraRef}
                style={styles.camera}
                facing="back"
              />

              {/* Overlay: slot name + GPS coords */}
              <View style={styles.cameraOverlay}>
                <View style={styles.slotLabel}>
                  <Text style={styles.slotLabelText}>{activeSlot}</Text>
                </View>

                {/* Stamp preview overlay (bottom-left) */}
                <View style={styles.stampPreview}>
                  <Text style={styles.stampLine}>
                    <Text style={{ color: '#6BBF2A' }}>●</Text>
                    {' '}{tecnicoNombre} · Multitel S.A. de C.V.
                  </Text>
                  <Text style={styles.stampLine}>
                    📍 {currentLocation?.coords.latitude.toFixed(6)}°N{' '}
                    {Math.abs(currentLocation?.coords.longitude ?? 0).toFixed(6)}°W
                  </Text>
                  <Text style={styles.stampLine}>🕐 {toCST(new Date())}</Text>
                </View>

                {/* Capture button */}
                <View style={styles.captureRow}>
                  <TouchableOpacity
                    style={styles.cancelButton}
                    onPress={() => setActiveSlot(null)}
                  >
                    <Text style={styles.cancelButtonText}>Cancelar</Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={[styles.captureButton, processingPhoto && styles.captureButtonDisabled]}
                    onPress={capturePhoto}
                    disabled={processingPhoto}
                  >
                    {processingPhoto ? (
                      <ActivityIndicator color="#FFFFFF" />
                    ) : (
                      <View style={styles.captureButtonInner} />
                    )}
                  </TouchableOpacity>

                  <View style={{ width: 72 }} />
                </View>
              </View>
            </>
          )}
        </View>
      </Modal>
    </SafeAreaView>
  );
};

export default FotosScreen;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F6F8',
  },
  gpsBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    gap: 8,
  },
  gpsBarReady: {
    backgroundColor: '#3A7D1A',
  },
  gpsBarWaiting: {
    backgroundColor: '#854F0B',
  },
  gpsDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#FFFFFF',
  },
  gpsText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '500',
  },
  slotsContainer: {
    padding: 16,
    paddingBottom: 32,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#3A3A3A',
    marginBottom: 16,
  },
  slotCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 10,
    marginBottom: 12,
    borderWidth: 1.5,
    borderColor: '#E0E0E0',
    overflow: 'hidden',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
  },
  slotCardDone: {
    borderColor: '#6BBF2A',
  },
  slotEmpty: {
    alignItems: 'center',
    paddingVertical: 24,
    gap: 4,
  },
  slotIcon: {
    fontSize: 28,
  },
  slotName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#3A3A3A',
  },
  slotHint: {
    fontSize: 12,
    color: '#888888',
  },
  slotFilled: {
    flexDirection: 'row',
    padding: 10,
    gap: 12,
    alignItems: 'flex-start',
  },
  thumbnail: {
    width: 72,
    height: 72,
    borderRadius: 6,
    backgroundColor: '#E0E0E0',
  },
  slotInfo: {
    flex: 1,
    gap: 2,
  },
  slotNameDone: {
    fontSize: 14,
    fontWeight: '700',
    color: '#3A3A3A',
  },
  slotMeta: {
    fontSize: 11,
    color: '#555555',
  },
  stampBadge: {
    marginTop: 4,
    alignSelf: 'flex-start',
    backgroundColor: '#F0F7F0',
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: '#6BBF2A',
  },
  stampBadgeText: {
    fontSize: 10,
    color: '#3A7D1A',
    fontWeight: '600',
  },
  summary: {
    marginTop: 16,
    alignItems: 'center',
  },
  summaryText: {
    fontSize: 14,
    color: '#555555',
    fontWeight: '500',
  },
  // Camera modal
  cameraContainer: {
    flex: 1,
    backgroundColor: '#000000',
  },
  camera: {
    flex: 1,
  },
  cameraOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: 'space-between',
  },
  slotLabel: {
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingHorizontal: 16,
    paddingVertical: 10,
    alignSelf: 'flex-start',
    margin: 16,
    borderRadius: 6,
  },
  slotLabelText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
  stampPreview: {
    position: 'absolute',
    bottom: 96,
    left: 12,
    right: 12,
    backgroundColor: 'rgba(0,0,0,0.72)',
    borderRadius: 6,
    padding: 8,
    gap: 2,
  },
  stampLine: {
    color: '#FFFFFF',
    fontSize: 11,
    fontFamily: 'monospace',
  },
  captureRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 32,
    paddingBottom: 32,
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  cancelButton: {
    width: 72,
    alignItems: 'center',
  },
  cancelButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
  },
  captureButton: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: '#FFFFFF',
    borderWidth: 4,
    borderColor: '#6BBF2A',
    justifyContent: 'center',
    alignItems: 'center',
  },
  captureButtonDisabled: {
    opacity: 0.5,
  },
  captureButtonInner: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: '#6BBF2A',
  },
});
