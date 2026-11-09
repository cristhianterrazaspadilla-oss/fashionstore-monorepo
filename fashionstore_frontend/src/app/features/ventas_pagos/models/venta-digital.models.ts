import type { DecimalApi } from '../../../core/models/comunes.models';

export type CanalDigital      = 'WEB' | 'MOVIL';

export type ModalidadEntrega  = 'RECOJO' | 'DELIVERY';

export type EstadoPagoStripe  = 'SIN_INTENCION' | 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'ANULADO';

export type EstadoVenta       = 'PENDIENTE_PAGO' | 'PAGADA' | 'CANCELADA' | 'PARCIALMENTE_DEVUELTA' | 'DEVUELTA';

export type EstadoPedido      = 'SOLICITADO' | 'PREPARADO' | 'LISTO_RECOJO' | 'EN_REPARTO' | 'RECOGIDO' | 'ENTREGADO' | 'CANCELADO';

export type SiguienteEstadoPedido = 'PREPARADO' | 'LISTO_RECOJO' | 'EN_REPARTO' | 'RECOGIDO' | 'ENTREGADO';

export type EstadoCarrito     = 'ACTIVO' | 'CONVERTIDO' | 'ABANDONADO';

// Carrito

export interface LineaCarritoDTO {
  id: string;
  variante_id: string;
  cantidad: number;
  precio_unitario: DecimalApi;
  descuento_unitario: DecimalApi;
  promocion_id: string | null;
  subtotal: DecimalApi;
}

export interface CarritoDTO {
  id: string;
  cliente_id: string;
  canal: CanalDigital;
  estado: EstadoCarrito;
  creada_en: string;
  actualizada_en: string;
  lineas: LineaCarritoDTO[];
  subtotal: DecimalApi;
  descuento_total: DecimalApi;
  total: DecimalApi;
}

export interface LineaAgregarDTO {
  variante_id: string;
  cantidad: number;
}

export interface LineaActualizarDTO {
  cantidad: number;
}

export interface CoberturaSucursalDTO {
  sucursal_id: string;
  sucursal_nombre: string;
  cubre_todo: boolean;
  faltantes: string[];
}

export interface CoberturaDTO {
  sucursales: CoberturaSucursalDTO[];
}

export interface CheckoutCrearDTO {
  sucursal_id: string;
  canal: CanalDigital;
  modalidad: ModalidadEntrega;
  direccion?: string;
  anillo_destino?: number;
}

export interface CheckoutRespuestaDTO {
  venta_id: string;
  numero: string;
  estado: EstadoVenta;
  total: DecimalApi;
  expira_en: string;
  pedido_entrega_id: string;
}

// Stripe

export type EstadoMetodoPreparado = 'PENDIENTE' | 'LISTO' | 'REVOCADO';

export interface MetodoPrepararDTO {
  huella_dispositivo?: string;
}

export interface MetodoPreparadoDTO {
  preparacion_pago_id: string;
  client_secret: string;
  estado: EstadoMetodoPreparado;
  setup_intent_id?: string;
  proveedor?: string;
}

export type EstadoOrdenPago = 'PENDIENTE' | 'REQUIERE_ACCION_CLIENTE' | 'CAPTURADO' | 'FALLIDO';

export interface OrdenPagoCrearDTO {
  contexto: 'VENTA' | 'PEDIDO';
  recurso_id: string;
  oferta_revision?: number;
  metodo_preparado_id?: string;
  consentimiento_cobro_posterior?: boolean;
}

export interface OrdenPagoDTO {
  orden_pago_id: string;
  estado: EstadoOrdenPago;
  monto_bob: DecimalApi;
  monto_usd?: DecimalApi;
  centavos_usd?: number;
  tasa_id?: string;
  client_secret?: string;
}

export interface ContinuarAccionDTO {
  payment_intent_id: string;
}

export interface PedidoCompraDTO {
  pedido_id: string;
  oferta_revision?: number;
  total_bob: DecimalApi;
  estado_pago: string;
  estado_cumplimiento: string;
  creada_en?: string;
}

export interface IntencionCrearDTO {
  venta_id: string;
}

export interface IntencionDTO {
  payment_intent_id: string;
  venta_id: string;
  monto: DecimalApi;
  moneda: string;
  estado: EstadoPagoStripe;
  client_secret: string | null;
}

export interface EstadoPagoDTO {
  venta_id: string;
  estado_venta: EstadoVenta;
  estado_pago: EstadoPagoStripe;
  payment_intent_id: string | null;
  monto: DecimalApi;
  expira_en: string | null;
}

// Entregas / Pedidos

export interface CotizacionDTO {
  sucursal_id: string;
  anillo_sucursal: number | null;
  anillo_destino: number;
  tarifa_base: DecimalApi;
  incremento_anillo: DecimalApi;
  costo_entrega: DecimalApi;
}

export interface PedidoDTO {
  id: string;
  venta_id: string;
  sucursal_id: string;
  modalidad: ModalidadEntrega;
  estado: EstadoPedido;
  anillo_sucursal: number | null;
  anillo_destino: number | null;
  direccion: string | null;
  tarifa_base: DecimalApi;
  incremento_anillo: DecimalApi;
  costo_entrega: DecimalApi;
  codigo_recojo: string | null;
  creada_en: string;
  puede_cancelar: boolean;
  puede_transicionar: boolean;
  siguiente_estado: SiguienteEstadoPedido | null;
}

export interface FiltrosPedidoDTO {
  sucursal_id?: string;
  estado?: string;
  limit?: number;
  offset?: number;
}

export interface PedidoListaDTO {
  total: number;
  limit: number;
  offset: number;
  items: PedidoDTO[];
}

export interface TransicionPedidoDTO {
  estado: EstadoPedido;
}


export interface VentaDigitalDTO {
  id: string;
  numero: string;
  cliente_id: string | null;
  reserva_id: string | null;
  sucursal_id: string;
  cajero_id: string | null;
  canal: CanalDigital | 'PRESENCIAL';
  estado: EstadoVenta;
  subtotal: DecimalApi;
  descuento: DecimalApi;
  adelanto_descontado: DecimalApi;
  costo_entrega: DecimalApi;
  total: DecimalApi;
  creada_en: string;
  confirmada_en: string | null;
  expira_en: string | null;
  detalles: VentaDetalleDTO[];
}

export interface VentaDetalleDTO {
  id: string;
  detalle_reserva_id: string | null;
  variante_id: string;
  cantidad: number;
  precio_unitario: DecimalApi;
  descuento: DecimalApi;
  promocion_id: string | null;
  costo_promedio: DecimalApi | null;
}
