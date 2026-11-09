export interface AdministradorInicialDTO {
  nombre: string;
  correo: string;
  credencial_inicial: string;
  telefono?: string;
  cargo?: string;
}

export interface EmpresaCrearDTO {
  razon_social: string;
  nombre_comercial: string;
  empresa_codigo: string;
  administrador: AdministradorInicialDTO;
}

export interface EmpresaRespuestaDTO {
  empresa_id: string;
  empresa_codigo: string;
  administrador_id: string;
  estado: string;
  suscripcion_pendiente?: boolean;
  acceso_publico_propuesto?: string;
}

export interface EmpresaDetalleDTO {
  id: string;
  codigo: string;
  nombre: string;
  estado: string;
  catalogo_version?: number;
  plazo_cambios_dias?: number;
  creada_en?: string;
  actualizada_en?: string;
  razon_social?: string;
  nombre_comercial?: string;
  empresa_codigo?: string;
}
