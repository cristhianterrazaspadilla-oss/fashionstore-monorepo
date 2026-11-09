import type { DecimalApi } from '../../../core/models/comunes.models';

export type TipoMovimientoSaldo = 'CREDITO' | 'RETENCION' | 'DEBITO' | 'RESTAURACION';

export interface MovimientoSaldoDTO {
  id: string;
  tipo: TipoMovimientoSaldo;
  monto_bob: DecimalApi;
  saldo_resultante_bob: DecimalApi;
  motivo: string;
  creado_en: string;
  referencia_origen_id?: string | null;
  referencia_tipo?: string | null;
}

export interface SaldoResumenDTO {
  saldo_disponible_bob: DecimalApi;
  saldo_retenido_bob: DecimalApi;
  saldo_total_bob?: DecimalApi;
  movimientos: MovimientoSaldoDTO[];
}

export interface AplicarSaldoDTO {
  monto_bob: number;
  revision?: number;
}

export interface SaldoAplicadoDTO {
  saldo_disponible_bob: DecimalApi;
  saldo_retenido_bob: DecimalApi;
  movimiento_id: string;
  restante_por_pagar_bob: DecimalApi;
}
