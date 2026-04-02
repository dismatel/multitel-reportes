/**
 * colors.ts — Identidad visual Multitel S.A. de C.V.
   * Header/navbar: #3A3A3A (gris oscuro del logo Multitel)
   * Color de accion primario: #6BBF2A (verde del logo Multitel)
 * Boton "Generar y guardar" (accion final irreversible): #3A3A3A
 * Checkboxes activos, pasos completados, nav activa: #6BBF2A
 * Fondo general: #F5F6F8
 */
export const COLORS = {
    // Colores de marca Multitel
  primary: '#6BBF2A',        // Verde Multitel — accion primaria
      primaryDark: '#5aa322',    // Verde oscuro
      primaryLight: '#8fd44a',   // Verde claro
      header: '#3A3A3A',         // Gris oscuro — header/navbar/botones irreversibles
      headerDark: '#2a2a2a',     // Gris muy oscuro

      // Fondos
      background: '#F5F6F8',     // Fondo general
      surface: '#FFFFFF',        // Superficie de tarjeta
      surfaceElevated: '#FFFFFF',

      // Textos
      textPrimary: '#1A1A1A',
      textSecondary: '#6B7280',
      textDisabled: '#9CA3AF',
      textOnPrimary: '#FFFFFF',  // Texto sobre verde Multitel
      textOnHeader: '#FFFFFF',   // Texto sobre header oscuro

      // Estados UI
      success: '#6BBF2A',        // Exito = verde Multitel
      warning: '#F59E0B',
      error: '#EF4444',
      info: '#3B82F6',

      // Bordes y divisores
      border: '#E5E7EB',
      divider: '#F3F4F6',

      // Acciones especificas
      buttonAction: '#6BBF2A',       // Boton de accion normal
      buttonFinal: '#3A3A3A',        // "Generar y guardar" (irreversible)
      checkboxActive: '#6BBF2A',     // Checkboxes activos
      stepCompleted: '#6BBF2A',      // Pasos completados en formulario
      navActive: '#6BBF2A',          // Navegacion activa

      // Stamp GPS de fotos
      stampBackground: 'rgba(0,0,0,0.72)',  // Fondo negro semitransparente
      stampText: '#FFFFFF',           // Texto blanco monoespaciado
      stampDot: '#6BBF2A',            // Punto verde antes del nombre

      // Utilidades
      white: '#FFFFFF',
      black: '#000000',
      transparent: 'transparent',
      overlay: 'rgba(0,0,0,0.5)',
    } as const;

export type ColorKey = keyof typeof COLORS;
