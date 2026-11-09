import { DecimalApi } from '../models/comunes.models';

export type { DecimalApi };

const ZONA = 'America/La_Paz';

export function aNumero(valor: DecimalApi | null | undefined): number {
  if (valor === null || valor === undefined || valor === '') return 0;
  const num = typeof valor === 'number' ? valor : parseFloat(String(valor).trim());
  return isNaN(num) ? 0 : num;
}

export function sumarImportes(...valores: Array<DecimalApi | null | undefined>): number {
  const suma = valores.reduce<number>((acc, v) => acc + aNumero(v), 0);
  return Math.round(suma * 100) / 100;
}

export function formatearBs(monto: DecimalApi | null | undefined): string {
  const n = aNumero(monto);
  return `Bs ${n.toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatearFecha(fecha: string | Date | null | undefined): string {
  if (!fecha) return '—';
  try {
    const d = typeof fecha === 'string' ? new Date(fecha) : fecha;
    if (isNaN(d.getTime())) return String(fecha);
    return d.toLocaleDateString('es-BO', {
      timeZone: ZONA,
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return String(fecha);
  }
}

export function formatearFechaHora(fecha: string | Date | null | undefined): string {
  if (!fecha) return '—';
  try {
    const d = typeof fecha === 'string' ? new Date(fecha) : fecha;
    if (isNaN(d.getTime())) return String(fecha);
    return d.toLocaleString('es-BO', {
      timeZone: ZONA,
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return String(fecha);
  }
}

/**
 * Convierte una fecha UTC o instante a formato YYYY-MM-DDTHH:mm
 * en la zona horaria America/La_Paz para campos datetime-local.
 */
export function fechaInputValue(fecha: string | Date | null | undefined): string {
  if (!fecha) return '';
  try {
    const d = typeof fecha === 'string' ? new Date(fecha) : fecha;
    if (isNaN(d.getTime())) return '';
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: ZONA,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(d);
    const get = (type: string) => parts.find(p => p.type === type)?.value ?? '00';
    return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
  } catch {
    return '';
  }
}

/**
 * Normaliza el valor de un campo datetime-local (YYYY-MM-DDTHH:mm)
 * para enviarlo al backend en hora boliviana con offset explícito (-04:00).
 */
export function entradaLocalIso(valorInput: string | null | undefined): string | undefined {
  if (!valorInput || !valorInput.trim()) return undefined;
  const limpio = valorInput.trim();
  if (limpio.length === 16) {
    return `${limpio}:00-04:00`;
  }
  if (limpio.length === 19) {
    return `${limpio}-04:00`;
  }
  return limpio;
}
