import type { DecimalApi } from '../../../core/models/comunes.models';

export type AccionDecision = 'PROMOCION' | 'LIQUIDACION' | 'TRASLADO' | 'REPOSICION' | 'MANTENER';

export type FuncionReporte =
  | 'ventasPorSucursal'
  | 'inventarioPorSucursal'
  | 'ventasPorTemporada'
  | 'stockCritico'
  | 'topVendidos'
  | 'efectividadReservas'
  | 'rotacionPorTemporada';

export interface DashboardSucursalItem {
  sucursal_id: string;
  sucursal_nombre: string;
  ventas: number;
  ingresos: DecimalApi;
}

export interface DashboardTopProducto {
  producto: string;
  unidades: number;
}

export interface DashboardStockCritico {
  sku: string;
  sucursal_id: string;
  disponible: number;
  existencia: number;
}

export interface ConversionReservasDTO {
  total: number;
  completadas: number;
  tasa: number;
}

export interface EfectividadPromocionesDTO {
  con_promocion: number;
  sin_promocion: number;
  descuento_total: DecimalApi;
}

export interface DashboardDTO {
  desde: string | null;
  hasta: string | null;
  ventas_total: number;
  ingresos_total: DecimalApi;
  margen_bruto_total: DecimalApi;
  ticket_promedio: DecimalApi;
  ventas_brutas?: DecimalApi;
  descuentos?: DecimalApi;
  devoluciones?: DecimalApi;
  reembolsos?: DecimalApi;
  neto_comercial?: DecimalApi;
  dinero_capturado?: DecimalApi;
  pedidos_pendientes_cumplimiento?: number;
  monto_pedidos_pendientes?: DecimalApi;
  por_sucursal: DashboardSucursalItem[];
  top_productos: DashboardTopProducto[];
  stock_critico: DashboardStockCritico[];
  valorizacion_total: DecimalApi;
  conversion_reservas: ConversionReservasDTO;
  estados_pedidos: Record<string, number>;
  efectividad_promociones: EfectividadPromocionesDTO;
}

// ========================================================
// CU24: Reportes Tipados Interpretados por IA (4 tipos)
// ========================================================

export type TipoReportePermitido =
  | 'VENTAS_POR_SUCURSAL'
  | 'RANKING_PRODUCTOS'
  | 'EVOLUCION_SEMANAL'
  | 'INGRESOS_POR_CATEGORIA'
  | 'MENOR_EXISTENCIA';

export interface ReporteInterpretadoPeticionDTO {
  consulta: string;
  tipo_reporte?: TipoReportePermitido;
  sucursal_id?: string;
  desde?: string;
  hasta?: string;
  categoria_id?: string;
  producto_id?: string;
  agrupacion?: 'GLOBAL' | 'SUCURSAL';
  limite?: number;
  orden?: 'ASC' | 'DESC';
  presentacion?: 'TABLA' | 'GRAFICO';
}

export interface ReporteInterpretadoResultadoDTO {
  consulta_id: string;
  tipo_reporte: TipoReportePermitido;
  filtros_efectivos: Record<string, unknown>;
  columnas: string[];
  filas: Array<Record<string, unknown>>;
  totales: Record<string, unknown>;
  grafico_sugerido: string;
  narrativa: string;
  generado_en: string;
  origen: string;
  proveedor?: string;
}

// ========================================================
// CU10: Pronósticos Supervisados de Demanda
// ========================================================

export type OrigenDatosML = 'AUTO' | 'REAL' | 'SINTETICO_REPRODUCIBLE';

export interface PronosticoDemandaPeticionDTO {
  sucursal_id?: string;
  producto_id?: string;
  semanas_adelante?: number;
  origen_datos?: OrigenDatosML;
  semilla?: number;
}

export interface PrediccionDemandaItemDTO {
  sucursal_id?: string;
  producto_id?: string;
  producto_nombre: string;
  semana: number;
  unidades_estimadas: number;
  confianza: number;
}

export interface MetricasPronosticoDTO {
  estado: 'ENTRENADO' | 'DATOS_INSUFICIENTES';
  mae?: number;
  rmse?: number;
  r2?: number;
  baseline_mae?: number;
  mejora_vs_baseline_pct?: number;
  razon?: string;
  train_size?: number;
  val_size?: number;
  semilla?: number;
  [key: string]: unknown;
}

export interface PronosticoDemandaResultadoDTO {
  modelo_id: string;
  modelo_version: string;
  dataset_version: string;
  metricas: MetricasPronosticoDTO;
  origen_datos: string;
  entrenado_en: string;
  predicciones: PrediccionDemandaItemDTO[];
}

// ========================================================
// CU11: Segmentación No Supervisada de Productos
// ========================================================

export interface SegmentacionProductosPeticionDTO {
  num_grupos?: number;
  periodo_dias?: number;
  origen_datos?: OrigenDatosML;
  semilla?: number;
}

export interface GrupoProductoDTO {
  grupo_id: number;
  nombre_grupo: string;
  descripcion: string;
  cantidad_productos: number;
  centroide: Record<string, number>;
  productos_muestra: Array<Record<string, unknown>>;
}

export interface MetricasSegmentacionDTO {
  estado: 'ENTRENADO' | 'DATOS_INSUFICIENTES';
  num_clusters?: number;
  inercia?: number;
  silhouette_score?: number | null;
  num_productos?: number;
  semilla?: number;
  razon?: string;
  [key: string]: unknown;
}

export interface SegmentacionProductosResultadoDTO {
  modelo_id: string;
  modelo_version: string;
  metricas: MetricasSegmentacionDTO;
  origen_datos: string;
  generado_en: string;
  grupos: GrupoProductoDTO[];
}

// ========================================================
// Compatibilidad legada Ciclo 3
// ========================================================

export interface ReportePedirDTO {
  consulta: string;
}

export interface ReporteRespuestaDTO {
  funcion_usada: FuncionReporte;
  parametros: Record<string, unknown>;
  datos: Record<string, unknown>;
  narrativa: string;
  proveedor: string;
}

export interface DecisionPedirDTO {
  dias_ventana?: number;
  umbral_rotacion?: number;
}

export interface DecisionItemDTO {
  variante_id: string;
  sku: string;
  accion: AccionDecision;
  detalle: string;
  stock_total: number;
  ventas_periodo: number;
  reposicion_sugerida: number;
}

export interface DecisionRespuestaDTO {
  items: DecisionItemDTO[];
  proveedor: string;
}
