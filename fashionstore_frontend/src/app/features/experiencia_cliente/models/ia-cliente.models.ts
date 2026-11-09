import type { DecimalApi } from '../../../core/models/comunes.models';

export type EventoNavegacion  = 'VISTA' | 'PRUEBA_VIRTUAL' | 'CARRITO' | 'COMPRA' | 'BUSQUEDA';

export interface NavegacionCrearDTO {
  evento: EventoNavegacion;
  variante_id?: string;
  producto_id?: string;
}

export interface RecomendacionPedirDTO {
  limite?: number;
  categoria?: string;
  talla?: string;
}

export interface RecomendacionItemDTO {
  producto_id: string;
  variante_id: string;
  nombre: string;
  precio: DecimalApi;
  disponible: number;
  motivo: string;
}

export interface RecomendacionRespuestaDTO {
  items: RecomendacionItemDTO[];
  proveedor: string;
}

export interface BusquedaVozDTO {
  texto: string;
}

export interface FiltrosBusquedaDTO {
  categoria?: string;
  talla?: string;
  color?: string;
  temporada?: string;
  precio_min?: DecimalApi;
  precio_max?: DecimalApi;
  texto?: string;
}

export interface BusquedaRespuestaDTO {
  filtros: FiltrosBusquedaDTO | Record<string, unknown>;
  total: number;
  items: RecomendacionItemDTO[];
  proveedor: string;
}
