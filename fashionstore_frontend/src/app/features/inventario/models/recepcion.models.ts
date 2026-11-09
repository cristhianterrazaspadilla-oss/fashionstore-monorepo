export interface ProveedorDTO {
  id: string;
  razon_social: string;
  nit?: string;
  contacto?: string;
  telefono?: string;
  correo_electronico?: string;
  direccion?: string;
  convenio?: string;
  activo: boolean;
}

export interface ProveedorCrearDTO {
  razon_social: string;
  nit?: string;
  contacto?: string;
  telefono?: string;
  correo_electronico?: string;
  direccion?: string;
  convenio?: string;
  activo?: boolean;
}

export interface DetalleLoteCrearDTO {
  variante_id: string;
  cantidad: number;
  costo_unitario: number;
}

export interface LoteRecepcionCrearDTO {
  proveedor_id: string;
  sucursal_id: string;
  temporada_id?: string;
  coleccion_id?: string;
  recibido_por_id: string;
  numero_documento?: string;
  observacion?: string;
  detalles: DetalleLoteCrearDTO[];
}

export interface DetalleLoteDTO {
  id: string;
  lote_id: string;
  variante_id: string;
  cantidad: number;
  costo_unitario: number;
}

export interface LoteRecepcionDTO {
  id: string;
  proveedor_id: string;
  sucursal_id: string;
  temporada_id?: string;
  coleccion_id?: string;
  recibido_por_id: string;
  numero_documento?: string;
  fecha_recepcion: string;
  observacion?: string;
  detalles: DetalleLoteDTO[];
}
