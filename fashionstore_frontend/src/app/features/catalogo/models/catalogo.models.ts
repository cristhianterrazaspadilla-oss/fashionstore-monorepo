export interface TallaDTO { id: string; nombre: string; orden: number; activo: boolean; }

export interface ComponenteColorDTO { color_id: string; orden: number; }

export interface ColorDTO {
  id: string;
  nombre: string;
  codigo_hex?: string;
  activo: boolean;
  componentes?: ComponenteColorDTO[];
}

export interface CategoriaDTO { id: string; nombre: string; descripcion?: string; categoria_padre_id?: string; activo: boolean; }

export interface TemporadaDTO { id: string; nombre: string; fecha_inicio?: string; fecha_fin?: string; activa: boolean; }

export interface ColeccionDTO { id: string; nombre: string; descripcion?: string; activa: boolean; }

export interface ProductoDTO {
  id: string;
  categoria_id?: string;
  proveedor_principal_id?: string;
  nombre: string;
  descripcion?: string;
  genero?: string;
  marca?: string;
  precio_base: number;
  activo: boolean;
  creado_en: string;
  actualizado_en: string;
  imagenes: ImagenProductoDTO[];
  temporada_ids: string[];
  coleccion_ids: string[];
  // Metadatos para presentación de copia local y promociones
  es_copia_local?: boolean;
  promocion_badge?: string;
  disponibilidad_conocida_total?: number;
  variantes_locales?: VarianteDTO[];
}

export interface ImagenProductoDTO {
  id: string;
  producto_id: string;
  enlace_imagen: string;
  texto_alternativo?: string;
  orden: number;
  es_principal: boolean;
}

export interface VarianteDTO {
  producto_nombre?: string;
  talla_nombre?: string;
  color_nombre?: string;
  id: string;
  producto_id: string;
  talla_id: string;
  color_id: string;
  sku: string;
  codigo_barras?: string;
  precio: number;
  precio_bob?: string;
  peso_gramos?: number;
  costo_promedio: number;
  costo_ultimo: number;
  recurso_prueba_virtual?: string;
  activa: boolean;
  disponibilidad_conocida?: number;
}

// Catálogo público

export interface CatalogoFiltroParams {
  texto?: string;
  categoria_id?: string;
  talla_id?: string;
  color_id?: string;
  componentes_color?: string[];
  modo_color?: 'EXACTO' | 'TODOS_COMPONENTES';
  temporada_id?: string;
  coleccion_id?: string;
  genero?: string;
  marca?: string;
  precio_min?: number;
  precio_max?: number;
  codigo_hex?: string;
  sucursal_id?: string;
  empresa_codigo?: string;
  empresa_id?: string;
  limit?: number;
  offset?: number;
}

export interface DisponibilidadItem {
  sucursal_id: string;
  sucursal_nombre: string;
  ciudad_nombre: string;
  direccion: string;
  disponible: number;
  reservado: number;
  comprometido_traslado: number;
  en_transito: number;
  actualizado_en: string;
  es_disponibilidad_conocida?: boolean;
}

// DTOs de descarga offline (descarga de catalogo / consulta catalogo offline)

export interface CatalogoDescargaVarianteDTO {
  id: string;
  sku: string;
  codigo_barras?: string;
  talla_id: string;
  talla: string;
  color_id: string;
  color: string;
  codigo_hex?: string;
  precio_bob: string;
  disponibilidad: number;
  disponibilidad_por_sucursal?: { sucursal_id: string; disponible_conocido: number; actualizado_en?: string }[];
}

export interface CatalogoDescargaProductoDTO {
  id: string;
  categoria_id?: string;
  categoria?: string;
  nombre: string;
  descripcion?: string;
  genero?: string;
  marca?: string;
  precio_base_bob: string;
  imagenes: ImagenProductoDTO[];
  temporadas: string[];
  colecciones: string[];
  variantes: CatalogoDescargaVarianteDTO[];
}

export interface CatalogoDescargaDTO {
  empresa_id: string;
  empresa_codigo: string;
  empresa_nombre?: string;
  sucursal_id?: string | null;
  ambito_sucursal?: string;
  ambito_sucursales?: string[];
  catalogo_version: number;
  descargado_en: string;
  generado_en?: string;
  total_productos: number;
  total_variantes: number;
  productos: CatalogoDescargaProductoDTO[];
  colores?: ColorDTO[];
  promociones?: {
    id: string;
    tipo: string;
    valor: string;
    cantidad_minima: number;
    vigente_desde: string;
    vigente_hasta?: string;
    variante_ids?: string[];
  }[];
}
