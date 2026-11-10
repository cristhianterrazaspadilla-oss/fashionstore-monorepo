import type { DecimalApi } from '../../../core/models/comunes.models';
import type { Comprobante } from '../../ventas_pagos/models/venta-presencial.models';

export interface Devolucion {
  id: string;
  detalle_venta_id: string;
  venta_id: string;
  variante_id: string;
  sucursal_id: string;
  cantidad: number;
  costo_unitario: number;
  motivo?: string;
  responsable_id?: string;
  fecha_hora: string;
}

export interface Merma {
  id: string;
  variante_id: string;
  sucursal_id: string;
  cantidad: number;
  costo_unitario: number;
  causa?: string;
  responsable_id?: string;
  fecha_hora: string;
}

// ==========================================
// CU20: Devoluciones Físicas e Inspecciones
// ==========================================

export type EstadoDevolucion =
  | 'SOLICITADA'
  | 'PENDIENTE_EVALUACION'
  | 'RECIBIDA'
  | 'EN_INSPECCION'
  | 'APROBADA_REPOSICION'
  | 'APROBADA_REEMBOLSO'
  | 'COMPLETADA'
  | 'RECHAZADA';

export type DictamenInspeccion = 'APROBADA_REPOSICION' | 'APROBADA_REEMBOLSO' | 'RECHAZADA';

export interface LineaDevolucionSolicitudDTO {
  detalle_venta_id: string;
  cantidad: number;
}

export interface DevolucionSolicitudDTO {
  venta_id: string;
  lineas: LineaDevolucionSolicitudDTO[];
  motivo_codigo: string;
  motivo_descripcion?: string;
}

export interface InspeccionDTO {
  condicion_fisica: string;
  responsabilidad_tienda: boolean;
  dictamen: DictamenInspeccion;
  observaciones?: string;
}

export interface DevolucionDTO {
  devolucion_id?: string;
  id?: string;
  venta_id: string;
  estado: EstadoDevolucion;
  motivo_codigo?: string;
  motivo_descripcion?: string;
  lineas?: LineaDevolucionSolicitudDTO[];
  inspeccion?: InspeccionDTO;
  creada_en?: string;
  empresa_id?: string;
  cliente_id?: string;
  detalles?: { id: string; detalle_venta_id: string; cantidad_solicitada: number; cantidad_recibida: number; cantidad_aceptada: number; condicion_fisica?: string }[];
}

export interface MermaCrearDTO {
  sucursal_id: string;
  variante_id: string;
  cantidad: number;
  motivo_codigo: string;
  descripcion: string;
}

export interface MermaDTO {
  merma_id: string;
  id?: string;
  kardex_id?: string;
  sucursal_id: string;
  variante_id: string;
  cantidad: number;
  motivo_codigo?: string;
  fecha_hora?: string;
}

// ==========================================
// CU08: Cambios de Prenda y Diferencias
// ==========================================

export type EstadoCambio =
  | 'SOLICITADO'
  | 'PENDIENTE_EVALUACION'
  | 'ESPERANDO_PAGO_CLIENTE'
  | 'DIFERENCIA_A_FAVOR'
  | 'COMPLETADO'
  | 'CANCELADO'
  | 'RECHAZADO';

export type DestinoDiferencia = 'SALDO' | 'REEMBOLSO' | 'PAGO_CLIENTE';

export interface LineaOriginalCambioDTO {
  detalle_venta_id?: string;
  variante_id: string;
  cantidad: number;
  precio_unitario_bob?: number;
}

export interface LineaReemplazoCambioDTO {
  variante_id: string;
  cantidad: number;
  precio_unitario_bob?: number;
}

export interface CambioSolicitudDTO {
  venta_id: string;
  lineas_originales: LineaOriginalCambioDTO[];
  reemplazos: LineaReemplazoCambioDTO[];
  modalidad: 'PRESENCIAL' | 'DELIVERY';
  motivo_codigo?: string;
  motivo_descripcion?: string;
}

export interface CambioDTO {
  cambio_id: string;
  nota_codigo: string;
  vence_espera_en: string;
  diferencia_bob: number;
  estado: EstadoCambio;
  creada_en?: string;
  venta_id?: string;
  lineas_originales?: LineaOriginalCambioDTO[];
  reemplazos?: LineaReemplazoCambioDTO[];
  motivo_codigo?: string;
}

export interface ResolverDiferenciaDTO {
  destino_diferencia: DestinoDiferencia;
  metodo_pago?: string;
}

// Extensión tipada de Comprobante para posventa
export interface ComprobantePosventa extends Comprobante {
  entregada_en?: string;
}
