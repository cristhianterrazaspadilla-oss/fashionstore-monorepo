"""Esquemas DTO del paquete Catálogo (CU05, CU06, CU22)."""
import uuid
import re
from decimal import Decimal
from datetime import date, datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ---------- Talla ----------
class TallaCrearDTO(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=30, description="Nombre de la talla (S/M/L...)")
    orden: int = Field(default=0, ge=0, le=32767, description="Orden de visualización")
    activo: bool = Field(default=True, description="Talla activa")


class TallaActualizarDTO(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=30)
    orden: Optional[int] = Field(None, ge=0, le=32767)
    activo: Optional[bool] = None


class TallaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nombre: str
    orden: int
    activo: bool


# ---------- Color ----------
class ColorCrearDTO(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=60, description="Nombre del color")
    codigo_hex: Optional[str] = Field(None, max_length=7, description="Código hex #RRGGBB")
    activo: bool = Field(default=True)

    @field_validator("codigo_hex")
    @classmethod
    def validar_hex(cls, v):
        if v is None:
            return v
        if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError("codigo_hex debe ser formato #RRGGBB")
        return v.upper()


class ColorActualizarDTO(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=60)
    codigo_hex: Optional[str] = Field(None, max_length=7)
    activo: Optional[bool] = None

    @field_validator("codigo_hex")
    @classmethod
    def validar_hex(cls, v):
        if v is None:
            return v
        if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError("codigo_hex debe ser formato #RRGGBB, ej #FF0000")
        return v.upper()


class ColorDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nombre: str
    codigo_hex: Optional[str] = None
    activo: bool


# ---------- Categoría ----------
class CategoriaCrearDTO(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100, description="Nombre de la categoría")
    descripcion: Optional[str] = Field(None, description="Descripción")
    categoria_padre_id: Optional[uuid.UUID] = Field(None, description="ID de categoría padre (jerarquía)")
    activo: bool = Field(default=True)


class CategoriaActualizarDTO(BaseModel):
    categoria_padre_id: Optional[uuid.UUID] = None
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    descripcion: Optional[str] = None
    activo: Optional[bool] = None


class CategoriaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    categoria_padre_id: Optional[uuid.UUID] = None
    nombre: str
    descripcion: Optional[str] = None
    activo: bool


# ---------- Temporada ----------
class TemporadaCrearDTO(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100, description="Nombre de la temporada")
    fecha_inicio: Optional[date] = Field(None, description="Fecha inicio")
    fecha_fin: Optional[date] = Field(None, description="Fecha fin")
    activa: bool = Field(default=True)

    @field_validator("fecha_fin")
    @classmethod
    def validar_fechas(cls, v, info):
        fecha_inicio = info.data.get("fecha_inicio")
        if v is not None and fecha_inicio is not None and v < fecha_inicio:
            raise ValueError("fecha_fin no puede ser anterior a fecha_inicio")
        return v


class TemporadaActualizarDTO(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    activa: Optional[bool] = None


class TemporadaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nombre: str
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    activa: bool


# ---------- Colección ----------
class ColeccionCrearDTO(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100, description="Nombre de la colección")
    descripcion: Optional[str] = Field(None, description="Descripción")
    activa: bool = Field(default=True)


class ColeccionActualizarDTO(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    descripcion: Optional[str] = None
    activa: Optional[bool] = None


class ColeccionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nombre: str
    descripcion: Optional[str] = None
    activa: bool


# ---------- Imagen Producto ----------
class ImagenProductoCrearDTO(BaseModel):
    enlace_imagen: str = Field(..., min_length=5, description="URL o enlace de la imagen")
    texto_alternativo: Optional[str] = Field(None, max_length=180)
    orden: int = Field(default=0, ge=0, le=32767)
    es_principal: bool = Field(default=False)


class ImagenProductoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    producto_id: uuid.UUID
    enlace_imagen: str
    texto_alternativo: Optional[str] = None
    orden: int
    es_principal: bool


ImagenCrearDTO = ImagenProductoCrearDTO
ImagenDTO = ImagenProductoDTO


# ---------- Producto ----------
class ProductoCrearDTO(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=180, description="Nombre del producto")
    descripcion: Optional[str] = Field(None, description="Descripción detallada")
    categoria_id: Optional[uuid.UUID] = Field(None, description="Categoría a la que pertenece")
    proveedor_principal_id: Optional[uuid.UUID] = Field(None, description="Proveedor principal")
    genero: Optional[str] = Field(None, max_length=30, description="Género: HOMBRE/MUJER/UNISEX/NIÑO")
    marca: Optional[str] = Field(None, max_length=100)
    precio_base: Decimal = Field(..., ge=0, description="Precio base >=0")
    activo: bool = Field(default=True)
    imagenes: List[ImagenProductoCrearDTO] = Field(default_factory=list, description="Lista de imágenes")
    temporada_ids: List[uuid.UUID] = Field(default_factory=list, description="IDs de temporadas asociadas")
    coleccion_ids: List[uuid.UUID] = Field(default_factory=list, description="IDs de colecciones asociadas")


class ProductoActualizarDTO(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=180)
    descripcion: Optional[str] = None
    categoria_id: Optional[uuid.UUID] = None
    proveedor_principal_id: Optional[uuid.UUID] = None
    genero: Optional[str] = Field(None, max_length=30)
    marca: Optional[str] = Field(None, max_length=100)
    precio_base: Optional[Decimal] = Field(None, ge=0)
    activo: Optional[bool] = None
    imagenes: Optional[List[ImagenProductoCrearDTO]] = None
    temporada_ids: Optional[List[uuid.UUID]] = None
    coleccion_ids: Optional[List[uuid.UUID]] = None


class ProductoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    categoria_id: Optional[uuid.UUID] = None
    proveedor_principal_id: Optional[uuid.UUID] = None
    nombre: str
    descripcion: Optional[str] = None
    genero: Optional[str] = None
    marca: Optional[str] = None
    precio_base: Decimal
    activo: bool
    creado_en: datetime
    actualizado_en: datetime
    imagenes: List[ImagenProductoDTO] = Field(default_factory=list)
    temporada_ids: List[uuid.UUID] = Field(default_factory=list)
    coleccion_ids: List[uuid.UUID] = Field(default_factory=list)
    variantes: List["VariantePublicaDTO"] = Field(default_factory=list)



class ComponenteColorDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    color_id: uuid.UUID
    orden: int


class ColorCompuestoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nombre: str
    componentes: List[ComponenteColorDTO] = Field(default_factory=list)


class SucursalPublicaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nombre: str
    ciudad_nombre: Optional[str] = None


class PromocionDescargaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tipo: str
    valor: str = Field(..., description="Valor decimal string BOB o porcentaje")
    cantidad_minima: int = Field(default=1, ge=1)
    vigente_desde: Optional[datetime] = None
    vigente_hasta: Optional[datetime] = None
    variante_ids: List[uuid.UUID] = Field(default_factory=list)


class DisponibilidadSucursalItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sucursal_id: uuid.UUID
    disponible_conocido: int = Field(..., ge=0)
    actualizado_en: datetime


class PromocionAplicableDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    codigo: str
    nombre: str
    tipo: str
    valor: str = Field(..., description="Valor decimal string BOB")
    cantidad_minima: int = Field(default=1, ge=1)
    vigente_desde: Optional[datetime] = None
    vigente_hasta: Optional[datetime] = None


class VariantePublicaDTO(BaseModel):
    """Vista pública de variante: sin costo_promedio, costo_ultimo u otros campos internos."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    producto_id: uuid.UUID
    talla_id: uuid.UUID
    color_id: uuid.UUID
    sku: str
    codigo_barras: Optional[str] = None
    precio: Decimal
    peso_gramos: Optional[int] = None
    recurso_prueba_virtual: Optional[str] = None
    activa: bool
    precio_bob: Optional[str] = None
    disponibilidad: int = 0
    disponibilidad_por_sucursal: List[DisponibilidadSucursalItemDTO] = Field(default_factory=list)
    promociones: List[PromocionAplicableDTO] = Field(default_factory=list)


class ProductoPublicoDTO(BaseModel):
    """Vista pública del catálogo: sin proveedores, costos ni campos internos."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    categoria_id: Optional[uuid.UUID] = None
    nombre: str
    descripcion: Optional[str] = None
    genero: Optional[str] = None
    marca: Optional[str] = None
    precio_base: Decimal
    imagenes: List[ImagenProductoDTO] = Field(default_factory=list)
    temporada_ids: List[uuid.UUID] = Field(default_factory=list)
    coleccion_ids: List[uuid.UUID] = Field(default_factory=list)
    variantes: List[VariantePublicaDTO] = Field(default_factory=list)



class CatalogoProductosPaginadoDTO(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[ProductoPublicoDTO]

# ---------- Variante ----------
class VarianteCrearDTO(BaseModel):
    producto_id: uuid.UUID = Field(..., description="ID del producto")
    talla_id: uuid.UUID = Field(..., description="ID de la talla")
    color_id: uuid.UUID = Field(..., description="ID del color")
    sku: str = Field(..., min_length=2, max_length=80, description="SKU único")
    codigo_barras: Optional[str] = Field(None, max_length=80, description="Código de barras único")
    precio: Decimal = Field(..., ge=0, description="Precio de la variante >=0")
    peso_gramos: Optional[int] = Field(None, gt=0, description="Peso en gramos >0")
    activa: bool = Field(default=True)
    recurso_prueba_virtual: Optional[str] = Field(None, description="Recurso prueba virtual (nullable Ciclo3)")

    @field_validator("sku")
    @classmethod
    def validar_sku(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("sku no puede estar vacío")
        return v

    @field_validator("codigo_barras")
    @classmethod
    def validar_codigo(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        return v


class VarianteActualizarDTO(BaseModel):
    sku: Optional[str] = Field(None, min_length=2, max_length=80)
    codigo_barras: Optional[str] = Field(None, max_length=80)
    precio: Optional[Decimal] = Field(None, ge=0)
    peso_gramos: Optional[int] = Field(None, gt=0)
    activa: Optional[bool] = None
    recurso_prueba_virtual: Optional[str] = None


class VarianteDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    producto_id: uuid.UUID
    talla_id: uuid.UUID
    color_id: uuid.UUID
    sku: str
    codigo_barras: Optional[str] = None
    precio: Decimal
    peso_gramos: Optional[int] = None
    costo_promedio: Decimal
    costo_ultimo: Decimal
    recurso_prueba_virtual: Optional[str] = None
    activa: bool


# (VariantePublicaDTO unificada definida arriba)


# ---------- Opciones de Filtro y Disponibilidad (CU06) ----------
class FiltroOpcionItemDTO(BaseModel):
    id: uuid.UUID
    nombre: str


class TallaOpcionDTO(BaseModel):
    id: uuid.UUID
    nombre: str
    orden: int


class ColorOpcionDTO(BaseModel):
    id: uuid.UUID
    nombre: str
    codigo_hex: Optional[str] = None


class FiltrosOpcionesDTO(BaseModel):
    categorias: List[FiltroOpcionItemDTO] = Field(default_factory=list)
    tallas: List[TallaOpcionDTO] = Field(default_factory=list)
    colores: List[ColorOpcionDTO] = Field(default_factory=list)
    temporadas: List[FiltroOpcionItemDTO] = Field(default_factory=list)
    colecciones: List[FiltroOpcionItemDTO] = Field(default_factory=list)
    generos: List[str] = Field(default_factory=list)
    marcas: List[str] = Field(default_factory=list)


class DisponibilidadSucursalDTO(BaseModel):
    inventario_id: uuid.UUID
    variante_id: uuid.UUID
    sucursal_id: uuid.UUID
    sucursal_nombre: str
    ciudad_id: uuid.UUID
    ciudad_nombre: str
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    disponible: int
    reservado: int
    comprometido_traslado: int
    en_transito: int
    actualizado_en: Optional[datetime] = None


# ---------- Promociones (CU22) ----------
TipoPromocion = Literal["PORCENTAJE", "MONTO_FIJO"]


class PromocionCrearDTO(BaseModel):
    codigo: str = Field(..., min_length=3, max_length=40)
    nombre: str = Field(..., min_length=3, max_length=180)
    descripcion: Optional[str] = None
    tipo: TipoPromocion
    valor: Decimal = Field(..., ge=0)
    cantidad_minima: int = Field(default=1, ge=1, description="Cantidad minima para aplicar")
    activa: bool = True
    vigencia_inicio: Optional[datetime] = None
    vigencia_fin: Optional[datetime] = None
    variante_ids: List[uuid.UUID] = Field(default_factory=list)


class PromocionActualizarDTO(BaseModel):
    nombre: Optional[str] = Field(None, min_length=3, max_length=180)
    descripcion: Optional[str] = None
    tipo: Optional[TipoPromocion] = None
    valor: Optional[Decimal] = Field(None, ge=0)
    cantidad_minima: Optional[int] = Field(None, ge=1)
    activa: Optional[bool] = None
    vigencia_inicio: Optional[datetime] = None
    vigencia_fin: Optional[datetime] = None


class PromocionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    tipo: str
    valor: Decimal
    cantidad_minima: int = Field(default=1, ge=1)
    activa: bool
    vigencia_inicio: Optional[datetime] = None
    vigencia_fin: Optional[datetime] = None
    creada_en: datetime
    variante_ids: List[uuid.UUID] = Field(default_factory=list)


class PromocionListaDTO(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[PromocionDTO]


class AsociarVariantesDTO(BaseModel):
    variante_ids: List[uuid.UUID] = Field(..., min_length=1)


# ---------- Descarga offline de catálogo (CU03 / CU16) ----------
class CatalogoDescargaVarianteDTO(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "70000000-0000-4000-8000-000000000001",
                "sku": "VES-NEG-M",
                "codigo_barras": "7771234567890",
                "talla_id": "a0000000-0000-4000-8000-000000000001",
                "talla": "M",
                "color_id": "b0000000-0000-4000-8000-000000000001",
                "color": "Negro",
                "codigo_hex": "#000000",
                "precio_bob": "120.00",
                "disponibilidad": 5,
            }
        },
    )

    id: uuid.UUID
    sku: str
    codigo_barras: Optional[str] = None
    talla_id: uuid.UUID
    talla: str
    color_id: uuid.UUID
    color: str
    codigo_hex: Optional[str] = None
    precio_bob: str = Field(..., description="Precio público en BOB con dos posiciones decimales, nunca float")
    disponibilidad: int = Field(default=0, ge=0, description="Disponibilidad pública conocida en el ámbito de sucursal")
    disponibilidad_por_sucursal: List[DisponibilidadSucursalItemDTO] = Field(default_factory=list)


class CatalogoDescargaProductoDTO(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "c0000000-0000-4000-8000-000000000001",
                "categoria_id": "d0000000-0000-4000-8000-000000000001",
                "categoria": "Vestidos",
                "nombre": "Vestido Casual Elegante",
                "descripcion": "Vestido midi de temporada en tela fresca",
                "genero": "Femenino",
                "marca": "FashionStore",
                "precio_base_bob": "120.00",
                "imagenes": [],
                "temporadas": ["Primavera 2026"],
                "colecciones": ["Colección Urbana"],
                "variantes": [],
            }
        },
    )

    id: uuid.UUID
    categoria_id: Optional[uuid.UUID] = None
    categoria: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    genero: Optional[str] = None
    marca: Optional[str] = None
    precio_base_bob: str = Field(..., description="Precio base en BOB con dos posiciones decimales")
    imagenes: List[ImagenProductoDTO] = Field(default_factory=list)
    temporadas: List[str] = Field(default_factory=list)
    colecciones: List[str] = Field(default_factory=list)
    variantes: List[CatalogoDescargaVarianteDTO] = Field(default_factory=list)


class CatalogoDescargaDTO(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "empresa_id": "20000000-0000-4000-8000-000000000001",
                "empresa_codigo": "fashionstore",
                "empresa_nombre": "FashionStore",
                "sucursal_id": None,
                "ambito_sucursal": "TODAS",
                "catalogo_version": 1,
                "descargado_en": "2026-10-25T17:00:00Z",
                "total_productos": 1,
                "total_variantes": 1,
                "productos": [],
            }
        },
    )

    empresa_id: uuid.UUID
    empresa_codigo: str
    empresa_nombre: str
    sucursal_id: Optional[uuid.UUID] = None
    ambito_sucursal: Optional[str] = Field("TODAS", description="Ámbito de sucursal de la descarga: 'TODAS' o nombre/código de la sucursal específica")
    catalogo_version: int = Field(..., ge=1, description="Versión monótona del catálogo publicada por la empresa")
    generado_en: datetime = Field(..., description="Fecha y hora UTC del corte central del catálogo")
    descargado_en: datetime = Field(..., description="Alias heredado de generado_en")
    ambito_sucursales: List[uuid.UUID] = Field(default_factory=list)
    sucursales: List[SucursalPublicaDTO] = Field(default_factory=list)
    colores: List[ColorCompuestoDTO] = Field(default_factory=list)
    promociones: List[PromocionDescargaDTO] = Field(default_factory=list)
    total_productos: int = Field(..., ge=0)
    total_variantes: int = Field(..., ge=0)
    productos: List[CatalogoDescargaProductoDTO] = Field(default_factory=list)
