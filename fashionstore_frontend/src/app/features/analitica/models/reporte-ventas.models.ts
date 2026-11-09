export interface VentaSucursal {
  id: string;
  numero: string;
  creada_en: string;
  fecha_central?: string;
  fecha_fisica_local?: string;
  cliente_id?: string;
  reserva_id?: string;
  canal: string;
  estado: string;
  unidades: number;
  subtotal: number;
  descuento: number;
  adelanto_descontado: number;
  total: number;
  costo_total?: number;
  margen_bruto?: number;
}

export interface ReporteVentasResumen {
  total_ventas: number;
  unidades: number;
  monto_total: number;
  ticket_promedio: number;
  costo_total?: number;
  margen_bruto_total?: number;
  ventas_brutas?: number;
  total_descuentos?: number;
  total_devoluciones?: number;
  total_reembolsos?: number;
  neto_comercial?: number;
}

export interface ReporteVentas {
  total: number;
  limit: number;
  offset: number;
  resumen: ReporteVentasResumen;
  items: VentaSucursal[];
}
