export type EstadoReserva = 'PENDIENTE_TRASLADO' | 'PENDIENTE' | 'PREPARADA' | 'ATENDIDA' | 'COMPLETADA' | 'CANCELADA' | 'VENCIDA';

export type EstadoTraslado = 'SOLICITADO' | 'APROBADO' | 'RECHAZADO' | 'DESPACHADO' | 'RECIBIDO' | 'CANCELADO';

export interface LineaReservaCrear {
  variante_id: string;
  cantidad: number;
  sucursal_origen_id?: string;
}

export interface ReservaCrear {
  sucursal_destino_id: string;
  fecha_visita?: string;
  observacion?: string;
  lineas: LineaReservaCrear[];
}

export interface DetalleReserva {
  id: string;
  variante_id: string;
  cantidad_solicitada: number;
  cantidad_reservada: number;
  cantidad_pendiente_traslado: number;
  cantidad_vendida: number;
  cantidad_liberada: number;
  estado_linea: string;
}

export interface TrasladoResumen {
  id: string;
  sucursal_origen_id: string;
  sucursal_destino_id: string;
  estado: EstadoTraslado;
}

export interface Reserva {
  id: string;
  empresa_id?: string;
  cliente_id: string;
  sucursal_destino_id: string;
  codigo: string;
  estado: EstadoReserva;
  revision: number;
  fecha_creacion: string;
  origen_plazo_en?: string;
  fecha_visita?: string;
  vence_en: string;
  operacion_sincronizacion_id?: string | null;
  observacion?: string;
  adelanto_modalidad?: string;
  adelanto_valor?: number;
  adelanto_monto?: number;
  preparada_en?: string;
  atendida_en?: string;
  preparada_por?: string;
  atendida_por?: string;
  detalles: DetalleReserva[];
  traslados: TrasladoResumen[];
}

export interface ReservaCancelarDTO {
  revision: number;
}

export interface DetalleTraslado {
  id: string;
  traslado_id: string;
  detalle_reserva_id?: string;
  variante_id: string;
  cantidad: number;
}

export interface Traslado {
  id: string;
  reserva_id?: string;
  sucursal_origen_id: string;
  sucursal_destino_id: string;
  estado: EstadoTraslado;
  solicitado_por_id: string;
  aprobado_por_id?: string;
  fecha_solicitud: string;
  fecha_aprobacion?: string;
  fecha_despacho?: string;
  fecha_recepcion?: string;
  motivo_rechazo?: string;
  detalles: DetalleTraslado[];
}
