/**
 * Utilidades para manejo de fecha y hora en el huso horario oficial de Bolivia (America/La_Paz, UTC-04:00)
 * y persistencia de identificadores de dispositivo y ventana de privacidad.
 */

const CLAVE_DISPOSITIVO = 'fs_dispositivo_id';
const CLAVE_LOGIN_ONLINE = 'fs_login_online_en';
const VENTANA_PRIVACIDAD_HORAS = 8;
const UUID_V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function generarUuidV4Seguro(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Obtiene o inicializa un identificador de dispositivo único y estable en formato UUID v4.
 * Si existía un identificador previo no conforme a UUID (ej. 'disp-...'), lo migra transparentemente.
 */
export function obtenerDispositivoId(): string {
  if (typeof window === 'undefined' || !window.localStorage) {
    return '00000000-0000-4000-8000-000000000000';
  }
  let id = localStorage.getItem(CLAVE_DISPOSITIVO);
  if (!id || !UUID_V4_REGEX.test(id)) {
    id = generarUuidV4Seguro();
    try {
      localStorage.setItem(CLAVE_DISPOSITIVO, id);
    } catch {}
  }
  return id;
}

/**
 * Registra el instante del último inicio de sesión en línea para controlar la ventana de privacidad de 8 horas.
 */
export function registrarLoginOnline(): void {
  if (typeof window !== 'undefined' && window.localStorage) {
    localStorage.setItem(CLAVE_LOGIN_ONLINE, Date.now().toString());
  }
}

/**
 * Limpia la marca de inicio de sesión en línea al cerrar sesión.
 */
export function limpiarLoginOnline(): void {
  if (typeof window !== 'undefined' && window.localStorage) {
    localStorage.removeItem(CLAVE_LOGIN_ONLINE);
  }
}

/**
 * Verifica si la ventana de privacidad (8 horas desde el último inicio de sesión en línea) está activa.
 */
export function esVentanaPrivacidadValida(): boolean {
  if (typeof window === 'undefined' || !window.localStorage) {
    return false;
  }
  const valor = localStorage.getItem(CLAVE_LOGIN_ONLINE);
  if (!valor) {
    return false;
  }
  const timestamp = parseInt(valor, 10);
  if (isNaN(timestamp)) {
    return false;
  }
  const horasTranscurridas = (Date.now() - timestamp) / (1000 * 60 * 60);
  return horasTranscurridas < VENTANA_PRIVACIDAD_HORAS;
}

/**
 * Genera una cadena de fecha/hora en formato ISO 8601 con el offset explícito de Bolivia (-04:00).
 * Calcula el tiempo exacto independientemente del huso horario del equipo cliente.
 */
export function obtenerHoraBoliviaIso(fecha: Date = new Date()): string {
  // Bolivia es UTC-4 constante todo el año (sin horario de verano).
  const boliviaMs = fecha.getTime() - 4 * 60 * 60 * 1000;
  const d = new Date(boliviaMs);
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const min = String(d.getUTCMinutes()).padStart(2, '0');
  const ss = String(d.getUTCSeconds()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}T${hh}:${min}:${ss}-04:00`;
}

/**
 * Formatea una fecha ISO para presentación en pantalla en hora de Bolivia.
 */
export function formatearFechaBolivia(fechaIso?: string | null): string {
  if (!fechaIso) return '—';
  try {
    const d = new Date(fechaIso);
    if (isNaN(d.getTime())) return fechaIso;
    return new Intl.DateTimeFormat('es-BO', {
      timeZone: 'America/La_Paz',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    }).format(d);
  } catch {
    return fechaIso;
  }
}
