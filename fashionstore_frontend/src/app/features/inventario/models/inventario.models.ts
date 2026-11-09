export interface MovimientoKardexDTO {
  id: string;
  variante_id: string;
  sucursal_origen_id?: string;
  sucursal_destino_id?: string;
  responsable_id?: string;
  tipo: string;
  cantidad: number;
  costo_unitario: number;
  saldo_fisico?: number;
  valoracion_saldo?: number;
  referencia_tipo?: string;
  referencia_id?: string;
  linea_referencia_id?: string;
  fecha_hora: string;
  observacion?: string;
}

export interface ExistenciaDTO {
  id?: string;
  inventario_id?: string;
  variante_id: string;
  sku: string;
  producto_nombre: string;
  talla_nombre?: string;
  color_nombre?: string;
  codigo_hex?: string;
  sucursal_id: string;
  sucursal_nombre: string;
  ciudad_nombre: string;
  disponible: number;
  reservado: number;
  comprometido_traslado: number;
  en_transito: number;
  comprometido_caja?: number;
  comprometido_digital?: number;
  comprometido_cambio?: number;
  fisico?: number;
  libre?: number;
  cupo_offline?: number;
  existencia_total: number;
  costo_promedio: number;
  costo_ultimo: number;
  precio: number;
  valorizacion: number;
  actualizado_en: string;
}

export interface ValorizacionDTO {
  sucursal_id: string;
  sucursal_nombre: string;
  ciudad_nombre: string;
  total_existencia: number;
  valorizacion: number;
  margen_bruto_total?: number;
}

export interface ValorizacionGlobalDTO {
  total_existencia: number;
  valorizacion_total: number;
  detalle_por_sucursal: ValorizacionDTO[];
}
