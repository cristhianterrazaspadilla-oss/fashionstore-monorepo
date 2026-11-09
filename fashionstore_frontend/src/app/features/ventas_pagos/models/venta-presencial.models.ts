export type MetodoCaja = 'EFECTIVO' | 'TARJETA_CAJA' | 'QR_CAJA' | 'TRANSFERENCIA' | 'SALDO' | 'STRIPE_TEST';

export type MedioPagoPresencial = 'EFECTIVO' | 'SALDO' | 'STRIPE_TEST' | 'TARJETA_CAJA' | 'QR_CAJA' | 'TRANSFERENCIA';

export interface LineaVentaPresencialDTO {
  variante_id: string;
  cantidad: number;
  precio_unitario_bob?: number;
  descuento_bob?: number;
}

export interface IniciarVentaPresencialStripeDTO {
  sucursal_id: string;
  cliente_id?: string | null;
  turno_caja_id?: string | null;
  lineas: LineaVentaPresencialDTO[];
}

export interface IniciarVentaPresencialStripeRespuestaDTO {
  venta_id: string;
  orden_pago_id: string;
  stripe_payment_intent_id?: string | null;
  client_secret?: string | null;
  monto_bob: string;
  monto_usd: string;
  centavos_usd: number;
  tasa_bob_por_usd: string;
  estado_orden: 'PENDIENTE' | 'REQUIERE_ACCION_CLIENTE' | 'CAPTURADO' | 'FALLIDO' | 'CANCELADO';
  estado_verificacion?: 'VERIFICADO' | 'NO_VERIFICADO_ERROR_PASARELA' | 'PROVISIONAL_PENDIENTE_INTENTO';
  cliente_id?: string | null;
  turno_caja_id?: string | null;
  sucursal_id?: string;
}

export interface LineaRecuperadaCajaDTO {
  variante_id: string;
  cantidad: number;
  precio_unitario_bob: string;
  descuento_bob?: string;
  sku?: string;
  nombre_producto?: string;
}

export interface OrdenActivaCajaDTO {
  orden_pago_id: string;
  venta_id: string;
  stripe_payment_intent_id: string | null;
  client_secret?: string | null;
  monto_bob: string;
  monto_usd: string;
  centavos_usd: number;
  tasa_bob_por_usd: string;
  estado_orden: 'PENDIENTE' | 'REQUIERE_ACCION_CLIENTE' | 'CAPTURADO' | 'FALLIDO' | 'CANCELADO';
  sucursal_id: string;
  turno_caja_id?: string | null;
  cliente_id?: string | null;
  procedencia: 'TURNO_OFFLINE' | 'PRESENCIAL';
  lineas: LineaRecuperadaCajaDTO[];
  estado_verificacion: 'VERIFICADO' | 'NO_VERIFICADO_ERROR_PASARELA' | 'PROVISIONAL_PENDIENTE_INTENTO';
}

export interface VentaPresencialLiquidarDTO {
  venta_id?: string;
  orden_pago_id?: string;
  sucursal_id: string;
  lineas: LineaVentaPresencialDTO[];
  medio_pago: MedioPagoPresencial;
  efectivo_recibido_bob?: number;
  saldo_aplicado_bob?: number;
  stripe_payment_intent_id?: string | null;
  cliente_id?: string;
  turno_caja_id?: string;
  reserva_id?: string;
}

export interface VentaLiquidadaDTO {
  venta_id: string;
  numero: string;
  total_bob: number;
  comprobante_id: string;
  kardex_ids?: string[];
  medio_pago: string;
  cambio_entregado_bob?: number;
  cambio_bob?: number;
  estado_pago?: string;
  estado_entrega?: string;
  cliente_id?: string;
  fecha_hora?: string;
}

export interface Pago {
  id: string;
  contexto: string;
  reserva_id?: string;
  venta_id?: string;
  medio_pago?: string;
  metodo?: string;
  tipo_pago?: string;
  modalidad_adelanto?: string;
  monto: number;
  no_reembolsable: boolean;
  estado: string;
  pagado_en?: string;
}

export interface ItemVenta {
  detalle_reserva_id?: string;
  variante_id: string;
  cantidad: number;
  precio_unitario_bob?: number;
  descuento_bob?: number;
}

export interface VentaCrear {
  reserva_id?: string;
  sucursal_id: string;
  cliente_id?: string;
  metodo: MetodoCaja;
  items: ItemVenta[];
}

export interface DetalleVenta {
  id: string;
  detalle_reserva_id?: string;
  variante_id: string;
  cantidad: number;
  precio_unitario: number;
  descuento: number;
  costo_promedio?: number;
}

export interface Venta {
  id: string;
  numero: string;
  cliente_id?: string;
  reserva_id?: string;
  sucursal_id: string;
  cajero_id?: string;
  canal: string;
  estado: string;
  subtotal: number;
  descuento: number;
  adelanto_descontado: number;
  costo_entrega: number;
  total: number;
  creada_en: string;
  confirmada_en?: string;
  detalles: DetalleVenta[];
}

export interface Comprobante extends Venta {
  reserva_codigo?: string;
  sucursal_nombre?: string;
  cajero_nombre?: string;
  pagos: Pago[];
}
