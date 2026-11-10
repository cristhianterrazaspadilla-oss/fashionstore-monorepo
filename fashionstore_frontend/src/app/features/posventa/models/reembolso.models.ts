import type { DecimalApi } from '../../../core/models/comunes.models';

export type EstadoReembolso = 'PENDIENTE_AUTORIZACION' | 'AUTORIZADO' | 'EN_PROCESO' | 'COMPLETADO' | 'FALLIDO' | 'RECHAZADO';
export type MedioReembolso = 'STRIPE' | 'SALDO' | 'EFECTIVO';

export interface ReembolsoSolicitudDTO {
  origen_tipo: 'VENTA' | 'PEDIDO' | 'DEVOLUCION' | 'CAMBIO';
  origen_id: string;
  motivo_codigo: string;
  motivo_descripcion?: string;
  unidades?: number;
}

export interface ReembolsoComponenteDTO {
  id: string;
  medio: MedioReembolso;
  monto_bob: DecimalApi;
  estado: string;
  pago_id?: string | null;
  monto_usd?: DecimalApi | null;
  centavos_usd?: number | null;
  tasa_bob_por_usd?: DecimalApi | null;
}

// Nombres de la respuesta real de Posventa, sin suponer un medio unico.
export interface ReembolsoDetalleDTO {
  id: string;
  empresa_id: string;
  cliente_id: string;
  origen_tipo: string;
  origen_id: string;
  motivo_codigo: string;
  estado: EstadoReembolso;
  monto_bob: DecimalApi;
  revision: number;
  creada_en: string;
  autorizada_en?: string | null;
  completada_en?: string | null;
  componentes: ReembolsoComponenteDTO[];
}

export interface ReembolsoAutorizarDTO { motivo_aprobacion?: string; }
export interface ReembolsoEjecutarDTO { clave_ejecucion: string; }
