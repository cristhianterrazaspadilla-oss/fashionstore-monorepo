/**
 * Mapper único de estados técnicos a etiquetas legibles y clases de estado.
 * No expone códigos de caso de uso, identificadores académicos ni nombres de tablas.
 */

export interface EstadoVisual {
  etiqueta: string;
  clase: string;
}

const MAPA_ESTADOS: Record<string, EstadoVisual> = {
  /* Pago */
  SIN_INTENCION:    { etiqueta: 'Sin intención',    clase: 'pendiente' },
  PENDIENTE:        { etiqueta: 'Pendiente',       clase: 'pendiente' },
  PENDIENTE_PAGO:   { etiqueta: 'Pendiente de pago', clase: 'pendiente' },
  APROBADO:         { etiqueta: 'Aprobado',         clase: 'aprobado' },
  RECHAZADO:        { etiqueta: 'Rechazado',        clase: 'rechazado' },
  ANULADO:          { etiqueta: 'Anulado',          clase: 'anulado' },

  /* Venta */
  PAGADA:           { etiqueta: 'Pagada',           clase: 'aprobado' },
  CANCELADA:        { etiqueta: 'Cancelada',        clase: 'cancelada' },

  /* Pedido */
  SOLICITADO:       { etiqueta: 'Solicitado',       clase: 'solicitado' },
  PREPARADO:        { etiqueta: 'Preparado',        clase: 'preparado' },
  LISTO_RECOJO:     { etiqueta: 'Listo para recoger', clase: 'listo' },
  EN_REPARTO:       { etiqueta: 'En camino',        clase: 'reparto' },
  RECOGIDO:         { etiqueta: 'Recogido',         clase: 'completado' },
  ENTREGADO:        { etiqueta: 'Entregado',        clase: 'completado' },

  /* Reserva */
  PENDIENTE_TRASLADO: { etiqueta: 'En traslado',    clase: 'traslado' },
  PREPARADA:        { etiqueta: 'Preparada',        clase: 'preparado' },
  ATENDIDA:         { etiqueta: 'Atendida',         clase: 'atendida' },
  COMPLETADA:       { etiqueta: 'Completada',       clase: 'completado' },

  /* Traslado */
  DESPACHADO:       { etiqueta: 'Despachado',       clase: 'reparto' },
  RECIBIDO:         { etiqueta: 'Recibido',         clase: 'completado' },

  /* Promoción */
  PORCENTAJE:       { etiqueta: 'Porcentaje',       clase: 'porcentaje' },
  MONTO_FIJO:       { etiqueta: 'Monto fijo',       clase: 'monto-fijo' },

  /* Decisión de inventario */
  PROMOCION:        { etiqueta: 'Promoción',        clase: 'promocion' },
  LIQUIDACION:      { etiqueta: 'Liquidación',      clase: 'liquidacion' },
  TRASLADO:         { etiqueta: 'Traslado',         clase: 'traslado' },
  REPOSICION:       { etiqueta: 'Reposición',       clase: 'reposicion' },
  MANTENER:         { etiqueta: 'Mantener',         clase: 'mantener' },

  /* Modalidad */
  RECOJO:           { etiqueta: 'Recojo en tienda', clase: 'recojo' },
  DELIVERY:         { etiqueta: 'Delivery',         clase: 'delivery' },
};

export function mapearEstado(estado: string): EstadoVisual {
  return MAPA_ESTADOS[estado] ?? { etiqueta: estado, clase: 'desconocido' };
}

export function etiquetaEstado(estado: string): string {
  return mapearEstado(estado).etiqueta;
}

/**
 * Retorna la clase CSS de badge correspondiente al estado.
 */
export function claseEstado(estado: string): string {
  const v = mapearEstado(estado);
  switch (v.clase) {
    case 'completado':
    case 'aprobado':
      return 'status-success';
    case 'rechazado':
    case 'cancelada':
    case 'anulado':
    case 'liquidacion':
      return 'status-danger';
    case 'pendiente':
    case 'solicitado':
    case 'preparado':
    case 'traslado':
    case 'reparto':
    case 'listo':
    case 'atendida':
      return 'status-warning';
    default:
      return 'status-neutral';
  }
}
