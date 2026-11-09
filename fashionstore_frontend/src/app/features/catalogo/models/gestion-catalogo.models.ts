import type { DecimalApi } from '../../../core/models/comunes.models';

export type TipoPromocion     = 'PORCENTAJE' | 'MONTO_FIJO';

export interface PromocionCrearDTO {
  codigo: string;
  nombre: string;
  descripcion?: string;
  tipo: TipoPromocion;
  valor: DecimalApi;
  activa?: boolean;
  vigencia_inicio?: string;
  vigencia_fin?: string;
  variante_ids?: string[];
}

export interface PromocionActualizarDTO {
  nombre?: string;
  descripcion?: string | null;
  tipo?: TipoPromocion;
  valor?: DecimalApi;
  activa?: boolean;
  vigencia_inicio?: string | null;
  vigencia_fin?: string | null;
}

export interface PromocionDTO {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string | null;
  tipo: TipoPromocion;
  valor: DecimalApi;
  activa: boolean;
  vigencia_inicio: string | null;
  vigencia_fin: string | null;
  creada_en: string;
  variante_ids: string[];
}

export interface PromocionListaDTO {
  total: number;
  limit: number;
  offset: number;
  items: PromocionDTO[];
}

export interface AsociarVariantesDTO {
  variante_ids: string[];
}


export interface ImagenProductoCrearDTO {
  enlace_imagen: string;
  texto_alternativo?: string;
  orden?: number;
  es_principal?: boolean;
}

export interface ProductoCrearDTO {
  nombre: string;
  descripcion?: string | null;
  categoria_id?: string | null;
  proveedor_principal_id?: string | null;
  genero?: string | null;
  marca?: string | null;
  precio_base: DecimalApi;
  activo?: boolean;
  imagenes?: ImagenProductoCrearDTO[];
  temporada_ids?: string[];
  coleccion_ids?: string[];
}

export interface ProductoActualizarDTO {
  nombre?: string;
  descripcion?: string | null;
  categoria_id?: string | null;
  proveedor_principal_id?: string | null;
  genero?: string | null;
  marca?: string | null;
  precio_base?: DecimalApi;
  activo?: boolean;
  imagenes?: ImagenProductoCrearDTO[];
  temporada_ids?: string[];
  coleccion_ids?: string[];
}

export interface VarianteCrearDTO {
  producto_id: string;
  talla_id: string;
  color_id: string;
  sku: string;
  codigo_barras?: string | null;
  precio: DecimalApi;
  peso_gramos?: number | null;
  activa?: boolean;
  recurso_prueba_virtual?: string | null;
}

export interface VarianteActualizarDTO {
  sku?: string;
  codigo_barras?: string | null;
  precio?: DecimalApi;
  peso_gramos?: number | null;
  activa?: boolean;
  recurso_prueba_virtual?: string | null;
}
