export interface CiudadDTO {
  id: string;
  nombre: string;
  activo: boolean;
}

export interface CiudadCrearDTO {
  nombre: string;
}

export interface CiudadActualizarDTO {
  nombre?: string;
  activo?: boolean;
}

export interface SucursalCrearDTO {
  ciudad_id: string;
  empresa_id?: string;
  nombre: string;
  direccion: string;
  telefono?: string;
  numero_anillo?: number;
  tarifa_base_delivery: number;
  incremento_anillo_delivery: number;
  anillo_minimo_delivery: number;
  anillo_maximo_delivery: number;
  delivery_activo: boolean;
}

export interface SucursalActualizarDTO {
  nombre?: string;
  ciudad_id?: string;
  direccion?: string;
  telefono?: string;
  numero_anillo?: number;
  tarifa_base_delivery?: number;
  incremento_anillo_delivery?: number;
  anillo_minimo_delivery?: number;
  anillo_maximo_delivery?: number;
  delivery_activo?: boolean;
  activa?: boolean;
  revision: number;
}

export interface ConfigurarTarifasDeliveryDTO {
  tarifa_base_delivery: number;
  incremento_anillo_delivery: number;
  anillo_minimo_delivery?: number;
  anillo_maximo_delivery?: number;
  delivery_activo?: boolean;
  revision?: number;
}

export interface SucursalDTO {
  id: string;
  empresa_id?: string;
  ciudad_id: string;
  ciudad_nombre?: string;
  nombre: string;
  direccion: string;
  telefono?: string;
  numero_anillo?: number;
  tarifa_base_delivery: number;
  incremento_anillo_delivery: number;
  anillo_minimo_delivery: number;
  anillo_maximo_delivery: number;
  delivery_activo: boolean;
  activa: boolean;
  revision?: number;
  adelanto_activo?: boolean;
  modalidad_adelanto?: 'MONTO_FIJO' | 'PORCENTAJE' | null;
  valor_adelanto?: number | null;
}

// --- CU02: Suscripción y Capacidades ---

export interface PlanDetalleDTO {
  id: string;
  codigo: string;
  nombre: string;
  max_sucursales_activas: number;
  reportes_generativos: boolean;
  modelos_ml: boolean;
  permite_operacion_offline: boolean;
  activo: boolean;
}

export interface AsignarSuscripcionDTO {
  plan_id: string;
  inicio_en: string;
  vence_en: string;
  motivo: string;
  revision?: number;
}

export interface SuscripcionRespuestaDTO {
  suscripcion_id: string;
  empresa_id: string;
  plan_id: string;
  plan_codigo: string;
  plan_nombre: string;
  version: number;
  revision: number;
  inicio_en: string;
  vence_en: string;
  gracia_hasta: string;
  estado_efectivo: string;
  capacidades: string[];
  sucursales_activas: number;
  limite_sucursales: number;
  permite_offline: boolean;
  creada_en: string;
  motivo?: string;
}
