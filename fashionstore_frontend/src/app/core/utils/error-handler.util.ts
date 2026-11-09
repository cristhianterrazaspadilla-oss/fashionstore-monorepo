import { HttpErrorResponse } from '@angular/common/http';

/**
 * Utilidad para formatear errores provenientes de la API (FastAPI / HTTP)
 * Convierte arrays de validación 422 y objetos en texto claro y amigable en español.
 */

function esObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === 'object' && valor !== null;
}

interface DetalleValidacionItem {
  loc?: unknown[];
  msg?: unknown;
  type?: unknown;
}

function esDetalleValidacion(item: unknown): item is DetalleValidacionItem {
  return esObjeto(item) && ('loc' in item || 'msg' in item);
}

function extraerDetail(error: unknown): unknown {
  if (!error) return null;

  if (error instanceof HttpErrorResponse) {
    if (error.status === 0) {
      return 'No se pudo conectar con el servidor. Verifica tu conexión a internet.';
    }
    if (esObjeto(error.error)) {
      if ('detail' in error.error) return error.error['detail'];
      if ('message' in error.error) return error.error['message'];
      if ('mensaje' in error.error) return error.error['mensaje'];
    }
    if (typeof error.error === 'string' && error.error.trim().length > 0) {
      return error.error;
    }
    if (error.status === 401) {
      return 'Sesión expirada o no autorizada. Inicia sesión nuevamente.';
    }
    if (error.status === 403) {
      return 'No tienes permisos para realizar esta acción.';
    }
    if (error.status === 404) {
      return 'El recurso solicitado no fue encontrado.';
    }
    if (error.status === 409) {
      return 'Ocurrió un conflicto con el estado actual de la operación.';
    }
    return error.message;
  }

  if (esObjeto(error)) {
    if (esObjeto(error['error'])) {
      const errSub = error['error'];
      if ('detail' in errSub) return errSub['detail'];
      if ('message' in errSub) return errSub['message'];
      if ('mensaje' in errSub) return errSub['mensaje'];
    }
    if ('detail' in error) return error['detail'];
    if ('message' in error) return error['message'];
    if ('mensaje' in error) return error['mensaje'];
    if (typeof error['error'] === 'string') return error['error'];
  }

  if (typeof error === 'string') {
    return error;
  }

  return null;
}

export function formatearErrorApi(error: unknown, fallback = 'No se pudo completar la operación.'): string {
  if (!error) return fallback;

  const detail = extraerDetail(error);

  if (typeof detail === 'string') {
    return traducirMensajeComun(detail);
  }

  if (Array.isArray(detail)) {
    const mensajes = detail.map((d: unknown) => {
      if (typeof d === 'string') return traducirMensajeComun(d);
      if (esDetalleValidacion(d)) {
        const campo = Array.isArray(d.loc) && d.loc.length > 0 ? String(d.loc[d.loc.length - 1]) : '';
        const etiquetaCampo = traducirCampo(campo);
        const textoMsg = typeof d.msg === 'string' ? traducirMensajeComun(d.msg) : 'Valor no válido';
        return etiquetaCampo ? `${etiquetaCampo}: ${textoMsg}` : textoMsg;
      }
      if (esObjeto(d)) {
        if (typeof d['msg'] === 'string') return traducirMensajeComun(String(d['msg']));
        if (typeof d['mensaje'] === 'string') return traducirMensajeComun(String(d['mensaje']));
        return 'Datos no válidos';
      }
      return String(d);
    });
    return mensajes.filter(Boolean).join('. ') || fallback;
  }

  if (esObjeto(detail)) {
    if (typeof detail['mensaje'] === 'string') return traducirMensajeComun(String(detail['mensaje']));
    if (typeof detail['msg'] === 'string') return traducirMensajeComun(String(detail['msg']));
    if (typeof detail['message'] === 'string') return traducirMensajeComun(String(detail['message']));

    const entradas = Object.entries(detail)
      .filter(([k]) => k !== 'codigo')
      .map(([k, v]) => `${traducirCampo(k)}: ${traducirMensajeComun(String(v))}`)
      .join(', ');
    return entradas || fallback;
  }

  return fallback;
}

function traducirCampo(campo: string): string {
  const mapa: Record<string, string> = {
    correo_electronico: 'Correo electrónico',
    contrasenia: 'Contraseña',
    nombres: 'Nombres',
    apellidos: 'Apellidos',
    fecha_visita: 'Fecha de visita',
    fecha_nacimiento: 'Fecha de nacimiento',
    telefono: 'Teléfono',
    cantidad: 'Cantidad',
    detalle_venta_id: 'Línea de venta',
    variante_id: 'Prenda / Variante',
    sucursal_id: 'Sucursal',
    causa: 'Causa documentada',
    motivo: 'Motivo',
    precio: 'Precio',
    direccion: 'Dirección'
  };
  return mapa[campo] || (campo !== 'body' ? campo : '');
}

function traducirMensajeComun(msg: string): string {
  if (!msg) return '';
  if (msg.includes('value is not a valid email address')) {
    return 'Ingresá un formato de correo válido (ejemplo: usuario@correo.com)';
  }
  if (msg.includes('String should have at least') || msg.includes('ensure this value has at least')) {
    return 'Debe tener al menos la longitud mínima requerida';
  }
  if (msg.includes('Field required') || msg.includes('field required')) {
    return 'Este campo es obligatorio';
  }
  if (msg.includes('Input should be a valid date')) {
    return 'Formato de fecha no válido';
  }
  if (msg.includes('Input should be a valid UUID')) {
    return 'No se pudo identificar el registro';
  }
  return msg;
}
