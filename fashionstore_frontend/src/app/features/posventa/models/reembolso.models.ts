import type { DecimalApi } from '../../../core/models/comunes.models';

export type EstadoReembolso =
  | 'PENDIENTE_AUTORIZACION'
  | 'SOLICITADO'
  | 'AUTORIZADO'
  | 'EN_PROCESO'
  | 'COMPLETADO'
  | 'FALLIDO'
  | 'RECHAZADO';

export type MedioReembolso = 'STRIPE' | 'SALDO' | 'EFECTIVO';

export interface ReembolsoSolicitudDTO {
  origen_tipo: 'VENTA' | 'PEDIDO' | 'DEVOLUCION' | 'CAMBIO';
  origen_id: string;
  motivo_codigo: string;
  motivo_descripcion?: string;
  unidades?: number;
}

export interface ReembolsoComponenteDTO {
  medio: MedioReembolso;
  monto_bob: DecimalApi;
  referencia?: string;
}

export interface ReembolsoDetalleDTO {
  reembolso_id: string;
  estado: EstadoReembolso;
  monto_bob: DecimalApi;
  medio_original: MedioReembolso;
  motivo_codigo: string;
  motivo_descripcion?: string;
  creado_en: string;
  actualizado_en?: string;
  autorizador_id?: string;
  componentes?: ReembolsoComponenteDTO[];
  origen_tipo?: string;
  origen_id?: string;
}

export interface ReembolsoAutorizarDTO {
  motivo_aprobacion?: string;
}

export interface ReembolsoEjecutarDTO {
  clave_ejecucion?: string;
}
