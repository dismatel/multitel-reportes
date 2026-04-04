/**
 * app/src/screens/DashboardScreen.tsx
 * Technician dashboard — report list, stats, navigation.
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  StatusBar,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';

import { COLORS, STATUS_COLORS } from '../theme/colors';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList, 'Dashboard'>;

// FIX A-1: usar apiBaseUrl desde extra (no EXPO_PUBLIC_)
const extra = Constants.expoConfig?.extra ?? {};
const APIM_BASE = extra.apiBaseUrl ?? '';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Reporte {
  id: string;
  cliente: string;
  tipoReporte: 'PlantaExterna' | 'CPE';
  estado: 'Enviado' | 'Borrador' | 'FirmaPendiente';
  fecha: string;
  nodo: string;
}

interface Stats {
  totalMes: number;
  pendientesFirma: number;
  enviados: number;
}

const STATUS_LABELS: Record<Reporte['estado'], string> = {
  Enviado: 'Enviado',
  Borrador: 'Borrador',
  FirmaPendiente: 'Firma pendiente',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function DashboardScreen() {
  const navigation = useNavigation<Nav>();
  const [reportes, setReportes] = useState<Reporte[]>([]);
  const [stats, setStats] = useState<Stats>({ totalMes: 0, pendientesFirma: 0, enviados: 0 });
  const [tecnicoNombre, setTecnicoNombre] = useState('Técnico');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadUserInfo();
    fetchReportes();
  }, []);

  const loadUserInfo = async () => {
    try {
      const token = await SecureStore.getItemAsync('msal_access_token');
      if (!token) return;
      const resp = await fetch('https://graph.microsoft.com/v1.0/me', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok) {
        const me = await resp.json();
        setTecnicoNombre(me.displayName ?? me.userPrincipalName ?? 'Técnico');
      }
    } catch (e) {
      // Non-critical
    }
  };

  const fetchReportes = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const token = await SecureStore.getItemAsync('msal_access_token');
      if (!token) throw new Error('No token');

      const resp = await fetch(`${APIM_BASE}/api/reportes?tecnico=me&top=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      const lista: Reporte[] = data.value ?? [];
      setReportes(lista);

      const now = new Date();
      const mes = lista.filter(r => {
        const fecha = new Date(r.fecha);
        return fecha.getMonth() === now.getMonth() && fecha.getFullYear() === now.getFullYear();
      });
      setStats({
        totalMes: mes.length,
        pendientesFirma: lista.filter(r => r.estado === 'FirmaPendiente').length,
        enviados: lista.filter(r => r.estado === 'Enviado').length,
      });
    } catch (e) {
      // Show empty state
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const getIniciales = (nombre: string) => {
    return nombre
      .split(' ')
      .slice(0, 2)
      .map(n => n[0])
      .join('')
      .toUpperCase();
  };

  const renderReporte = ({ item }: { item: Reporte }) => {
    const sc = STATUS_COLORS[item.estado];
    return (
      <TouchableOpacity
        style={styles.reporteCard}
        onPress={() => navigation.navigate('Formulario', { reporteId: item.id })}
        activeOpacity={0.75}
      >
        <View style={styles.reporteLeft}>
          <Text style={styles.reporteCliente} numberOfLines={1}>{item.cliente}</Text>
          <Text style={styles.reporteNodo} numberOfLines={1}>{item.nodo} · {item.tipoReporte}</Text>
          <Text style={styles.reporteFecha}>{new Date(item.fecha).toLocaleDateString('es-SV')}</Text>
        </View>
        <View style={[styles.estadoBadge, { backgroundColor: sc.bg }]}>
          <Text style={[styles.estadoText, { color: sc.text }]}>{STATUS_LABELS[item.estado]}</Text>
        </View>
      </TouchableOpacity>
    );
  };

  const handleLogout = async () => {
    await SecureStore.deleteItemAsync('msal_access_token');
    await SecureStore.deleteItemAsync('msal_token_expiry');
    navigation.reset({ index: 0, routes: [{ name: 'Login' }] });
  };

  return (
    <View style={styles.root}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.header} />

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{getIniciales(tecnicoNombre)}</Text>
          </View>
          <View>
            <Text style={styles.headerGreeting}>Hola,</Text>
            <Text style={styles.headerNombre} numberOfLines={1}>{tecnicoNombre}</Text>
          </View>
        </View>
        <TouchableOpacity onPress={handleLogout} style={styles.logoutBtn}>
          <Text style={styles.logoutText}>Salir</Text>
        </TouchableOpacity>
      </View>

      {/* Stats cards */}
      <View style={styles.statsRow}>
        <View style={styles.statCard}>
          <Text style={styles.statNumber}>{stats.totalMes}</Text>
          <Text style={styles.statLabel}>Este mes</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={[styles.statNumber, { color: COLORS.primary }]}>{stats.pendientesFirma}</Text>
          <Text style={styles.statLabel}>Pendientes firma</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={[styles.statNumber, { color: STATUS_COLORS.Enviado.text }]}>{stats.enviados}</Text>
          <Text style={styles.statLabel}>Enviados</Text>
        </View>
      </View>

      {/* New report button */}
      <TouchableOpacity
        style={styles.nuevoReporteBtn}
        onPress={() => navigation.navigate('Formulario', {})}
        activeOpacity={0.85}
      >
        <Text style={styles.nuevoReporteBtnText}>+ Nuevo reporte</Text>
      </TouchableOpacity>

      {/* Report list */}
      <Text style={styles.sectionTitle}>Reportes recientes</Text>

      {loading ? (
        <ActivityIndicator color={COLORS.primary} style={{ marginTop: 32 }} size="large" />
      ) : (
        <FlatList
          data={reportes}
          keyExtractor={item => item.id}
          renderItem={renderReporte}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => fetchReportes(true)}
              colors={[COLORS.primary]}
              tintColor={COLORS.primary}
            />
          }
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Text style={styles.emptyText}>No hay reportes aún.</Text>
              <Text style={styles.emptySubText}>Toca "+ Nuevo reporte" para comenzar.</Text>
            </View>
          }
        />
      )}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.background },
  header: {
    backgroundColor: COLORS.header,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 14,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 },
  avatar: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: COLORS.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  avatarText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  headerGreeting: { color: 'rgba(255,255,255,0.65)', fontSize: 12 },
  headerNombre: { color: '#fff', fontSize: 16, fontWeight: '700', maxWidth: 200 },
  logoutBtn: { paddingVertical: 6, paddingHorizontal: 12 },
  logoutText: { color: 'rgba(255,255,255,0.7)', fontSize: 13 },
  statsRow: {
    flexDirection: 'row', gap: 10,
    paddingHorizontal: 16, paddingTop: 16,
  },
  statCard: {
    flex: 1, backgroundColor: '#fff', borderRadius: 12,
    paddingVertical: 14, paddingHorizontal: 10,
    alignItems: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06, shadowRadius: 4, elevation: 2,
  },
  statNumber: { fontSize: 26, fontWeight: '800', color: COLORS.header },
  statLabel: { fontSize: 11, color: '#888', marginTop: 2, textAlign: 'center' },
  nuevoReporteBtn: {
    backgroundColor: COLORS.primary,
    marginHorizontal: 16, marginTop: 16,
    paddingVertical: 16, borderRadius: 12,
    alignItems: 'center',
    shadowColor: COLORS.primary, shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3, shadowRadius: 8, elevation: 4,
  },
  nuevoReporteBtnText: { color: '#fff', fontSize: 17, fontWeight: '700' },
  sectionTitle: {
    paddingHorizontal: 16, paddingTop: 20, paddingBottom: 8,
    fontSize: 14, fontWeight: '700', color: COLORS.header,
    textTransform: 'uppercase', letterSpacing: 0.5,
  },
  listContent: { paddingHorizontal: 16, paddingBottom: 24 },
  reporteCard: {
    backgroundColor: '#fff', borderRadius: 12,
    flexDirection: 'row', alignItems: 'center',
    padding: 14, marginBottom: 10,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06, shadowRadius: 4, elevation: 2,
  },
  reporteLeft: { flex: 1 },
  reporteCliente: { fontSize: 15, fontWeight: '700', color: COLORS.header },
  reporteNodo: { fontSize: 12, color: '#666', marginTop: 2 },
  reporteFecha: { fontSize: 11, color: '#999', marginTop: 4 },
  estadoBadge: { borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4 },
  estadoText: { fontSize: 11, fontWeight: '700' },
  emptyState: { alignItems: 'center', paddingTop: 48 },
  emptyText: { fontSize: 16, color: '#999', fontWeight: '600' },
  emptySubText: { fontSize: 13, color: '#bbb', marginTop: 6 },
});