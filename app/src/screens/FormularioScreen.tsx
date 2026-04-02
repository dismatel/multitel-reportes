/**
 * app/src/screens/FormularioScreen.tsx
 * 5-step report form: Portada, Datos técnicos, Materiales, Fotos, Firmas.
 */
import React, { useState, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, Switch, Alert, ActivityIndicator, KeyboardAvoidingView,
  Platform, StatusBar,
} from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import * as SecureStore from 'expo-secure-store';

import { COLORS } from '../theme/colors';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList, 'Formulario'>;
type Route = RouteProp<RootStackParamList, 'Formulario'>;

// ---------------------------------------------------------------------------
// Template variable map — 60+ fields
// ---------------------------------------------------------------------------
interface FormData {
  // Paso 1: Portada
  tipoReporte: 'PlantaExterna' | 'CPE';
  cliente: 'Claro' | 'Tigo' | 'Otro';
  clienteNombre: string;
  idServicio: string;
  encargadoGrupo: string;
  fecha: string;
  coordinadora: string;
  supervisorLider: string;
  gerenteOperativo: string;
  // Paso 2: Datos técnicos
  nodo: string;
  tipoServicio: string;
  equipoInstalado: string;
  potenciaCajaLiu: string;
  perdidaCajaLiu: string;
  fusionCajaLiu: string;
  perdidaMufaUltima: string;
  fusionMufaUlt: string;
  instSFP: string;
  odf: string;
  rackSinCPE: string;
  rackConCPE: string;
  etiquetaLIU: string;
  etiquetaCPE: string;
  ledLink: string;
  oltSwitch: string;
  odfNodo: string;
  ada: string;
  odi: string;
  // Paso 3: Materiales (checkbox + cantidad)
  materiales: Record<string, { checked: boolean; cantidad: string }>;
  // Patchcords (PC01-PC28)
  patchcords: Array<{
    tipo: string; metraje: string; modo: 'SM' | 'MM';
    simplex: boolean; duplex: boolean; cantidad: string;
  }>;
  // Paso 4: Fotos (URI strings, keyed by slot)
  fotos: Record<string, string>;
  // Paso 5: Firmas (base64 SVG)
  firmaSupervisorLider: string;
  firmaCoordinadora: string;
  firmaGerenteOperativo: string;
}

const MATERIAL_KEYS = [
  'Mufa y cierre de empalme', 'Pernos', 'Alambres y cables',
  'Abrazaderas', 'Preformadas', 'Pigtail SC/APC', 'Pigtail SC/UPC',
  'Crucetas/Brazos/Coraza', 'Bandeja', 'Enfrentadores/Acoplador', 'Misceláneo',
];

const FOTO_SLOTS_PE = [
  'Punta Inicial', 'Punta Final', 'Metraje Punta Inicial', 'Metraje Punta Final',
  'Reserva 1', 'Reserva 2', 'Reserva 3', 'Reserva 4', 'Reserva 5',
  'Cambio Nodo 1', 'Cambio Nodo 2', 'Servicio Adicional 1', 'Servicio Adicional 2',
];

const FOTO_SLOTS_CPE = [
  'Rack sin CPE', 'Rack con CPE', 'Etiqueta LIU', 'Etiqueta CPE', 'Led Link',
  'ODF Nodo', 'OLT/Switch', 'Fusión Caja LIU', 'Fusión Mufa', 'SFP',
];

const PATCHCORD_TIPOS = [
  'SC/APC-SC/APC', 'SC/APC-SC/UPC', 'SC/UPC-SC/UPC', 'LC-LC', 'LC-SC/APC',
];
const PATCHCORD_METRAJES = ['1m', '3m', '5m', '10m', '15m', '20m', '30m'];

const INITIAL_MATERIALES = Object.fromEntries(
  MATERIAL_KEYS.map(k => [k, { checked: false, cantidad: '' }])
);

const INITIAL_PATCHCORDS = PATCHCORD_TIPOS.flatMap(tipo =>
  PATCHCORD_METRAJES.map(metraje => ({
    tipo, metraje, modo: 'SM' as const, simplex: false, duplex: false, cantidad: '',
  }))
);

const INITIAL_FORM: FormData = {
  tipoReporte: 'PlantaExterna',
  cliente: 'Claro',
  clienteNombre: '', idServicio: '', encargadoGrupo: '',
  fecha: new Date().toISOString().split('T')[0],
  coordinadora: '', supervisorLider: '', gerenteOperativo: '',
  nodo: '', tipoServicio: '', equipoInstalado: '',
  potenciaCajaLiu: '', perdidaCajaLiu: '', fusionCajaLiu: '',
  perdidaMufaUltima: '', fusionMufaUlt: '', instSFP: '',
  odf: '', rackSinCPE: '', rackConCPE: '',
  etiquetaLIU: '', etiquetaCPE: '', ledLink: '', oltSwitch: '', odfNodo: '',
  ada: '', odi: '',
  materiales: INITIAL_MATERIALES,
  patchcords: INITIAL_PATCHCORDS,
  fotos: {},
  firmaSupervisorLider: '', firmaCoordinadora: '', firmaGerenteOperativo: '',
};

const STEP_LABELS = ['Portada', 'Datos técnicos', 'Materiales', 'Fotos', 'Firmas'];

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------
export default function FormularioScreen() {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormData>(INITIAL_FORM);
  const [saving, setSaving] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  const updateField = useCallback(<K extends keyof FormData>(key: K, val: FormData[K]) => {
    setForm(prev => ({ ...prev, [key]: val }));
  }, []);

  const fotoSlots = form.tipoReporte === 'PlantaExterna' ? FOTO_SLOTS_PE : FOTO_SLOTS_CPE;

  // Validation per step
  const validateStep = (): boolean => {
    if (step === 0) {
      if (!form.clienteNombre.trim()) { Alert.alert('Error', 'Nombre de cliente requerido'); return false; }
      if (!form.idServicio.trim()) { Alert.alert('Error', 'ID de servicio requerido'); return false; }
    }
    if (step === 1) {
      if (!form.nodo.trim()) { Alert.alert('Error', 'Nodo requerido'); return false; }
    }
    if (step === 3) {
      const missing = fotoSlots.filter(s => !form.fotos[s]);
      if (missing.length > 0) {
        Alert.alert('Fotos incompletas', `Faltan fotos: ${missing.slice(0, 3).join(', ')}${missing.length > 3 ? '...' : ''}`);
        return false;
      }
    }
    return true;
  };

  const goNext = () => {
    if (!validateStep()) return;
    if (step < 4) {
      setStep(s => s + 1);
      scrollRef.current?.scrollTo({ y: 0, animated: false });
    }
  };

  const goBack = () => {
    if (step > 0) { setStep(s => s - 1); scrollRef.current?.scrollTo({ y: 0, animated: false }); }
    else navigation.goBack();
  };

  const handleSubmit = async () => {
    if (!form.firmaSupervisorLider && !form.firmaCoordinadora) {
      Alert.alert('Firmas requeridas', 'Al menos una firma es requerida para generar el reporte.');
      return;
    }
    Alert.alert(
      'Generar y guardar',
      'Esta acción generará el reporte .pptx y .pdf y lo enviará para aprobación. ¿Continuar?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Confirmar', style: 'destructive', onPress: submitReporte },
      ]
    );
  };

  const submitReporte = async () => {
    setSaving(true);
    try {
      const token = await SecureStore.getItemAsync('msal_access_token');
      const APIM = process.env.EXPO_PUBLIC_APIM_BASE_URL ?? '';

      // Step 1: guardar_reporte
      const guardarResp = await fetch(`${APIM}/api/reportes`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload()),
      });
      if (!guardarResp.ok) throw new Error(`guardar_reporte: ${guardarResp.status}`);
      const { id } = await guardarResp.json();

      // Step 2: generar_pptx (async — returns job_id immediately)
      const generarResp = await fetch(`${APIM}/api/reportes/${id}/generar`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ reporte_id: id }),
      });
      if (!generarResp.ok) throw new Error(`generar_pptx: ${generarResp.status}`);

      Alert.alert(
        '¡Reporte enviado!',
        'El reporte se está generando. Recibirás una notificación cuando esté listo para aprobación.',
        [{ text: 'OK', onPress: () => navigation.navigate('Dashboard') }]
      );
    } catch (err: any) {
      Alert.alert('Error', err.message ?? 'No se pudo enviar el reporte. Intenta de nuevo.');
    } finally {
      setSaving(false);
    }
  };

  const buildPayload = () => ({
    tipo_reporte: form.tipoReporte,
    cliente: form.cliente,
    cliente_nombre: form.clienteNombre,
    id_servicio: form.idServicio,
    encargado_grupo: form.encargadoGrupo,
    fecha: form.fecha,
    coordinadora: form.coordinadora,
    supervisor_lider: form.supervisorLider,
    gerente_operativo: form.gerenteOperativo,
    nodo: form.nodo,
    tipo_servicio: form.tipoServicio,
    equipo_instalado: form.equipoInstalado,
    mediciones: {
      PotenciaCajaLiu: form.potenciaCajaLiu,
      PerdidaCajaLiu: form.perdidaCajaLiu,
      FusionCajaLiu: form.fusionCajaLiu,
      PerdidaMufaUltima: form.perdidaMufaUltima,
      FusionMufaUlt: form.fusionMufaUlt,
      InstSFP: form.instSFP,
      ODF: form.odf,
      RackSinCPE: form.rackSinCPE,
      RackConCPE: form.rackConCPE,
      EtiquetaLIU: form.etiquetaLIU,
      EtiquetaCPE: form.etiquetaCPE,
      LedLink: form.ledLink,
      OLTSwitch: form.oltSwitch,
      ODFNodo: form.odfNodo,
      ADA: form.ada,
      ODI: form.odi,
    },
    materiales: form.materiales,
    patchcords: form.patchcords,
    fotos: form.fotos,
    firmas: {
      supervisor_lider: form.firmaSupervisorLider,
      coordinadora: form.firmaCoordinadora,
      gerente_operativo: form.firmaGerenteOperativo,
    },
  });

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <StatusBar barStyle="light-content" backgroundColor={COLORS.header} />

      {/* Header with progress */}
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backBtn}>
          <Text style={styles.backText}>{'‹'}</Text>
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>{STEP_LABELS[step]}</Text>
          <View style={styles.progressBar}>
            {STEP_LABELS.map((_, i) => (
              <View
                key={i}
                style={[
                  styles.progressSegment,
                  { backgroundColor: i <= step ? COLORS.primary : 'rgba(255,255,255,0.25)' },
                ]}
              />
            ))}
          </View>
        </View>
        <Text style={styles.stepCounter}>{step + 1}/5</Text>
      </View>

      <ScrollView ref={scrollRef} style={styles.body} keyboardShouldPersistTaps="handled">
        {step === 0 && <PasoPortada form={form} update={updateField} />}
        {step === 1 && <PasoDatosTecnicos form={form} update={updateField} />}
        {step === 2 && <PasoMateriales form={form} setForm={setForm} />}
        {step === 3 && (
          <PasoFotos
            form={form}
            fotoSlots={fotoSlots}
            navigation={navigation}
            updateField={updateField}
          />
        )}
        {step === 4 && <PasoFirmas form={form} update={updateField} onSubmit={handleSubmit} saving={saving} />}
        <View style={{ height: 32 }} />
      </ScrollView>

      {/* Navigation buttons */}
      {step < 4 && (
        <View style={styles.navRow}>
          <TouchableOpacity style={styles.navBtnSecondary} onPress={goBack}>
            <Text style={styles.navBtnSecondaryText}>{step === 0 ? 'Cancelar' : 'Anterior'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.navBtnPrimary} onPress={goNext}>
            <Text style={styles.navBtnPrimaryText}>Siguiente</Text>
          </TouchableOpacity>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// Step 1: Portada
// ---------------------------------------------------------------------------
function PasoPortada({ form, update }: any) {
  return (
    <View style={styles.stepContainer}>
      <Text style={styles.sectionLabel}>Tipo de reporte</Text>
      <View style={styles.toggleRow}>
        {(['PlantaExterna', 'CPE'] as const).map(t => (
          <TouchableOpacity
            key={t}
            style={[styles.toggleBtn, form.tipoReporte === t && styles.toggleBtnActive]}
            onPress={() => update('tipoReporte', t)}
          >
            <Text style={[styles.toggleBtnText, form.tipoReporte === t && styles.toggleBtnTextActive]}>
              {t === 'PlantaExterna' ? 'Planta Externa' : 'CPE'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.sectionLabel}>Cliente</Text>
      <View style={styles.toggleRow}>
        {(['Claro', 'Tigo', 'Otro'] as const).map(c => (
          <TouchableOpacity
            key={c}
            style={[styles.toggleBtn, form.cliente === c && styles.toggleBtnActive]}
            onPress={() => update('cliente', c)}
          >
            <Text style={[styles.toggleBtnText, form.cliente === c && styles.toggleBtnTextActive]}>{c}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <FormField label="Nombre del cliente *" value={form.clienteNombre} onChange={v => update('clienteNombre', v)} />
      <FormField label="ID de servicio / instancia *" value={form.idServicio} onChange={v => update('idServicio', v)} />
      <FormField label="Encargado de grupo" value={form.encargadoGrupo} onChange={v => update('encargadoGrupo', v)} />
      <FormField label="Fecha" value={form.fecha} onChange={v => update('fecha', v)} placeholder="YYYY-MM-DD" />
      <FormField label="Coordinadora" value={form.coordinadora} onChange={v => update('coordinadora', v)} />
      <FormField label="Supervisor Líder" value={form.supervisorLider} onChange={v => update('supervisorLider', v)} />
      <FormField label="Gerente Operativo" value={form.gerenteOperativo} onChange={v => update('gerenteOperativo', v)} />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Datos técnicos
// ---------------------------------------------------------------------------
function PasoDatosTecnicos({ form, update }: any) {
  return (
    <View style={styles.stepContainer}>
      <FormField label="Nodo *" value={form.nodo} onChange={v => update('nodo', v)} />
      <FormField label="Tipo de servicio" value={form.tipoServicio} onChange={v => update('tipoServicio', v)} />
      <FormField label="Equipo instalado" value={form.equipoInstalado} onChange={v => update('equipoInstalado', v)} />

      <Text style={styles.sectionLabel}>Mediciones ópticas</Text>
      <FormField label="Potencia Caja LIU (dBm)" value={form.potenciaCajaLiu} onChange={v => update('potenciaCajaLiu', v)} keyboardType="numeric" />
      <FormField label="Pérdida Caja LIU (dB)" value={form.perdidaCajaLiu} onChange={v => update('perdidaCajaLiu', v)} keyboardType="numeric" />
      <FormField label="Fusión Caja LIU" value={form.fusionCajaLiu} onChange={v => update('fusionCajaLiu', v)} keyboardType="numeric" />
      <FormField label="Pérdida Mufa Última (dB)" value={form.perdidaMufaUltima} onChange={v => update('perdidaMufaUltima', v)} keyboardType="numeric" />
      <FormField label="Fusión Mufa Últ." value={form.fusionMufaUlt} onChange={v => update('fusionMufaUlt', v)} keyboardType="numeric" />
      <FormField label="Inst. SFP" value={form.instSFP} onChange={v => update('instSFP', v)} />

      {form.tipoReporte === 'CPE' && (
        <>
          <Text style={styles.sectionLabel}>Equipos CPE</Text>
          <FormField label="ODF" value={form.odf} onChange={v => update('odf', v)} />
          <FormField label="Rack sin CPE" value={form.rackSinCPE} onChange={v => update('rackSinCPE', v)} />
          <FormField label="Rack con CPE" value={form.rackConCPE} onChange={v => update('rackConCPE', v)} />
          <FormField label="Etiqueta LIU" value={form.etiquetaLIU} onChange={v => update('etiquetaLIU', v)} />
          <FormField label="Etiqueta CPE" value={form.etiquetaCPE} onChange={v => update('etiquetaCPE', v)} />
          <FormField label="Led Link" value={form.ledLink} onChange={v => update('ledLink', v)} />
          <FormField label="OLT/Switch" value={form.oltSwitch} onChange={v => update('oltSwitch', v)} />
          <FormField label="ODF Nodo" value={form.odfNodo} onChange={v => update('odfNodo', v)} />
          <FormField label="ADA" value={form.ada} onChange={v => update('ada', v)} />
          <FormField label="ODI" value={form.odi} onChange={v => update('odi', v)} />
        </>
      )}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Step 3: Materiales
// ---------------------------------------------------------------------------
function PasoMateriales({ form, setForm }: any) {
  const toggleMaterial = (key: string, checked: boolean) => {
    setForm((prev: FormData) => ({
      ...prev,
      materiales: { ...prev.materiales, [key]: { ...prev.materiales[key], checked, cantidad: checked ? prev.materiales[key].cantidad : '' } },
    }));
  };

  const setCantidad = (key: string, cantidad: string) => {
    setForm((prev: FormData) => ({
      ...prev,
      materiales: { ...prev.materiales, [key]: { ...prev.materiales[key], cantidad } },
    }));
  };

  return (
    <View style={styles.stepContainer}>
      <Text style={styles.sectionLabel}>Materiales generales</Text>
      {MATERIAL_KEYS.map(key => (
        <View key={key} style={styles.materialRow}>
          <Switch
            value={form.materiales[key].checked}
            onValueChange={v => toggleMaterial(key, v)}
            trackColor={{ false: '#ddd', true: COLORS.primary }}
            thumbColor={form.materiales[key].checked ? '#fff' : '#fff'}
          />
          <Text style={styles.materialLabel} numberOfLines={1}>{key}</Text>
          {form.materiales[key].checked && (
            <TextInput
              style={styles.cantidadInput}
              value={form.materiales[key].cantidad}
              onChangeText={v => setCantidad(key, v)}
              keyboardType="numeric"
              placeholder="Cant."
              placeholderTextColor="#aaa"
            />
          )}
        </View>
      ))}

      <Text style={[styles.sectionLabel, { marginTop: 20 }]}>Patchcords</Text>
      {PATCHCORD_TIPOS.map(tipo => (
        <View key={tipo} style={styles.patchcordSection}>
          <Text style={styles.patchcordTipo}>{tipo}</Text>
          {PATCHCORD_METRAJES.map(metraje => {
            const idx = form.patchcords.findIndex((p: any) => p.tipo === tipo && p.metraje === metraje);
            if (idx < 0) return null;
            const pc = form.patchcords[idx];
            const updatePC = (field: string, val: any) => {
              setForm((prev: FormData) => {
                const arr = [...prev.patchcords];
                arr[idx] = { ...arr[idx], [field]: val };
                return { ...prev, patchcords: arr };
              });
            };
            return (
              <View key={metraje} style={styles.patchcordRow}>
                <Text style={styles.patchcordMetraje}>{metraje}</Text>
                <TouchableOpacity onPress={() => updatePC('simplex', !pc.simplex)} style={[styles.modeBtn, pc.simplex && styles.modeBtnActive]}>
                  <Text style={[styles.modeBtnText, pc.simplex && styles.modeBtnTextActive]}>SX</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => updatePC('duplex', !pc.duplex)} style={[styles.modeBtn, pc.duplex && styles.modeBtnActive]}>
                  <Text style={[styles.modeBtnText, pc.duplex && styles.modeBtnTextActive]}>DX</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => updatePC('modo', pc.modo === 'SM' ? 'MM' : 'SM')} style={[styles.modeBtn, pc.modo === 'SM' && styles.modeBtnActive]}>
                  <Text style={[styles.modeBtnText, pc.modo === 'SM' && styles.modeBtnTextActive]}>{pc.modo}</Text>
                </TouchableOpacity>
                {(pc.simplex || pc.duplex) && (
                  <TextInput
                    style={styles.cantidadInput}
                    value={pc.cantidad}
                    onChangeText={v => updatePC('cantidad', v)}
                    keyboardType="numeric"
                    placeholder="Cant."
                    placeholderTextColor="#aaa"
                  />
                )}
              </View>
            );
          })}
        </View>
      ))}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Step 4: Fotos
// ---------------------------------------------------------------------------
function PasoFotos({ form, fotoSlots, navigation, updateField }: any) {
  return (
    <View style={styles.stepContainer}>
      <Text style={styles.hint}>
        Toca cada slot para capturar la foto. El GPS y el stamp se aplican automáticamente.
      </Text>
      {fotoSlots.map((slot: string) => {
        const uri = form.fotos[slot];
        return (
          <TouchableOpacity
            key={slot}
            style={[styles.fotoSlot, uri ? styles.fotoSlotDone : styles.fotoSlotPending]}
            onPress={() =>
              navigation.navigate('Fotos', {
                slotKey: slot,
                slotLabel: slot,
                tipoReporte: form.tipoReporte,
                onPhotoCaptured: (capturedUri: string) => {
                  updateField('fotos', { ...form.fotos, [slot]: capturedUri });
                },
              })
            }
          >
            <Text style={styles.fotoSlotIcon}>{uri ? '✓' : '📷'}</Text>
            <View style={{ flex: 1 }}>
              <Text style={[styles.fotoSlotLabel, uri && styles.fotoSlotLabelDone]}>{slot}</Text>
              {uri && <Text style={styles.fotoSlotUri} numberOfLines={1}>Capturada</Text>}
            </View>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Step 5: Firmas
// ---------------------------------------------------------------------------
function PasoFirmas({ form, update, onSubmit, saving }: any) {
  return (
    <View style={styles.stepContainer}>
      <Text style={styles.hint}>
        Las firmas digitales se insertan en la plantilla. Se requiere al menos una firma para continuar.
      </Text>

      {[
        { label: 'Supervisor Líder', key: 'firmaSupervisorLider' },
        { label: 'Coordinadora', key: 'firmaCoordinadora' },
        { label: 'Gerente Operativo', key: 'firmaGerenteOperativo' },
      ].map(({ label, key }) => (
        <View key={key} style={styles.firmaBox}>
          <Text style={styles.firmaLabel}>{label}</Text>
          <View style={styles.firmaCanvas}>
            {form[key] ? (
              <Text style={styles.firmaDone}>✓ Firma registrada</Text>
            ) : (
              <Text style={styles.firmaPlaceholder}>Toca para firmar</Text>
            )}
          </View>
          <TouchableOpacity
            style={styles.firmaClearBtn}
            onPress={() => update(key, form[key] ? '' : 'signature_placeholder')}
          >
            <Text style={styles.firmaClearText}>{form[key] ? 'Borrar firma' : 'Agregar firma'}</Text>
          </TouchableOpacity>
        </View>
      ))}

      <TouchableOpacity
        style={[styles.submitBtn, saving && { opacity: 0.7 }]}
        onPress={onSubmit}
        disabled={saving}
      >
        {saving ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.submitBtnText}>Generar y guardar</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Reusable FormField
// ---------------------------------------------------------------------------
function FormField({
  label, value, onChange, placeholder, keyboardType,
}: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; keyboardType?: any;
}) {
  return (
    <View style={styles.fieldWrapper}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={styles.fieldInput}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder ?? label}
        placeholderTextColor="#aaa"
        keyboardType={keyboardType ?? 'default'}
      />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const styles = StyleSheet.create({
  header: {
    backgroundColor: COLORS.header, flexDirection: 'row',
    alignItems: 'center', paddingHorizontal: 12,
    paddingTop: 10, paddingBottom: 10, gap: 8,
  },
  backBtn: { padding: 8 },
  backText: { color: '#fff', fontSize: 28, lineHeight: 28 },
  headerTitle: { color: '#fff', fontSize: 16, fontWeight: '700' },
  stepCounter: { color: 'rgba(255,255,255,0.7)', fontSize: 13, fontWeight: '600' },
  progressBar: { flexDirection: 'row', gap: 4, marginTop: 6 },
  progressSegment: { flex: 1, height: 3, borderRadius: 2 },
  body: { flex: 1, backgroundColor: COLORS.background },
  stepContainer: { padding: 16 },
  sectionLabel: {
    fontSize: 12, fontWeight: '700', color: COLORS.header,
    textTransform: 'uppercase', letterSpacing: 0.5,
    marginTop: 16, marginBottom: 8,
  },
  hint: { fontSize: 13, color: '#666', marginBottom: 12, lineHeight: 18 },
  toggleRow: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  toggleBtn: {
    flex: 1, paddingVertical: 10, borderRadius: 8,
    borderWidth: 1.5, borderColor: '#ddd', alignItems: 'center',
    backgroundColor: '#fff',
  },
  toggleBtnActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + '18' },
  toggleBtnText: { fontSize: 13, fontWeight: '600', color: '#666' },
  toggleBtnTextActive: { color: COLORS.primary },
  fieldWrapper: { marginBottom: 12 },
  fieldLabel: { fontSize: 12, fontWeight: '600', color: '#555', marginBottom: 4 },
  fieldInput: {
    backgroundColor: '#fff', borderRadius: 8, borderWidth: 1,
    borderColor: '#e0e0e0', paddingHorizontal: 12, paddingVertical: 10,
    fontSize: 14, color: COLORS.header,
  },
  materialRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  materialLabel: { flex: 1, fontSize: 14, color: COLORS.header },
  cantidadInput: {
    width: 64, borderWidth: 1, borderColor: '#ddd', borderRadius: 6,
    paddingHorizontal: 8, paddingVertical: 6, fontSize: 13,
    textAlign: 'center', color: COLORS.header,
  },
  patchcordSection: { marginBottom: 12 },
  patchcordTipo: { fontSize: 13, fontWeight: '700', color: COLORS.primary, marginBottom: 4 },
  patchcordRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: '#f5f5f5',
  },
  patchcordMetraje: { width: 36, fontSize: 12, color: '#555' },
  modeBtn: {
    paddingHorizontal: 8, paddingVertical: 4, borderRadius: 4,
    borderWidth: 1, borderColor: '#ddd',
  },
  modeBtnActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + '18' },
  modeBtnText: { fontSize: 11, color: '#666', fontWeight: '600' },
  modeBtnTextActive: { color: COLORS.primary },
  fotoSlot: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 14, marginBottom: 10, borderRadius: 10,
    borderWidth: 1.5,
  },
  fotoSlotPending: { backgroundColor: '#fff', borderColor: '#ddd', borderStyle: 'dashed' },
  fotoSlotDone: { backgroundColor: '#F0F7F0', borderColor: COLORS.primary },
  fotoSlotIcon: { fontSize: 20 },
  fotoSlotLabel: { fontSize: 14, fontWeight: '600', color: '#555' },
  fotoSlotLabelDone: { color: '#2E7D32' },
  fotoSlotUri: { fontSize: 11, color: '#888', marginTop: 2 },
  firmaBox: { marginBottom: 20 },
  firmaLabel: { fontSize: 13, fontWeight: '700', color: COLORS.header, marginBottom: 8 },
  firmaCanvas: {
    height: 100, backgroundColor: '#fff', borderRadius: 8,
    borderWidth: 1, borderColor: '#ddd', borderStyle: 'dashed',
    alignItems: 'center', justifyContent: 'center',
  },
  firmaDone: { fontSize: 14, color: '#2E7D32', fontWeight: '600' },
  firmaPlaceholder: { fontSize: 13, color: '#bbb' },
  firmaClearBtn: { alignSelf: 'flex-end', marginTop: 6 },
  firmaClearText: { fontSize: 12, color: COLORS.primary, fontWeight: '600' },
  submitBtn: {
    backgroundColor: COLORS.header, marginTop: 24,
    paddingVertical: 18, borderRadius: 12, alignItems: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2, shadowRadius: 8, elevation: 4,
  },
  submitBtnText: { color: '#fff', fontSize: 17, fontWeight: '700' },
  navRow: {
    flexDirection: 'row', gap: 12, padding: 16,
    backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#eee',
  },
  navBtnSecondary: {
    flex: 1, paddingVertical: 14, borderRadius: 10,
    borderWidth: 1.5, borderColor: '#ddd', alignItems: 'center',
  },
  navBtnSecondaryText: { fontSize: 15, fontWeight: '600', color: '#555' },
  navBtnPrimary: {
    flex: 2, paddingVertical: 14, borderRadius: 10,
    backgroundColor: COLORS.primary, alignItems: 'center',
  },
  navBtnPrimaryText: { fontSize: 15, fontWeight: '700', color: '#fff' },
});
