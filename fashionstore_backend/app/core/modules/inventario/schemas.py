"""Esquemas Pydantic / DTOs: Inventario, Proveedores y Recepción (CU04, CU07)"""
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

# ---------- Proveedor ----------

class ProveedorCrearDTO(BaseModel):
    razon_social: str = Field(..., min_length=2, max_length=180, description="Razón social del proveedor")
    nit: Optional[str] = Field(None, max_length=40, description="NIT del proveedor (único si se provee)")
    contacto: Optional[str] = Field(None, max_length=160, description="Persona de contacto")
    telefono: Optional[str] = Field(None, max_length=30, description="Teléfono")
    correo_electronico: Optional[str] = Field(None, max_length=160, description="Correo electrónico")
    direccion: Optional[str] = Field(None, description="Dirección")
    convenio: Optional[str] = Field(None, description="Convenio / notas")
    activo: bool = Field(default=True, description="Proveedor activo")

class ProveedorDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    razon_social: str
    nit: Optional[str] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    correo_electronico: Optional[str] = None
    direccion: Optional[str] = None
    convenio: Optional[str] = None
    activo: bool

# ---------- Recepción de Lotes ----------

class DetalleLoteCrearDTO(BaseModel):
    variante_id: uuid.UUID = Field(..., description="ID de la variante de producto a recibir")
    cantidad: int = Field(..., gt=0, description="Cantidad recibida (>0)")
    costo_unitario: Decimal = Field(..., ge=0, description="Costo unitario de compra (>=0)")

class LoteRecepcionCrearDTO(BaseModel):
    proveedor_id: uuid.UUID = Field(..., description="ID del proveedor")
    sucursal_id: uuid.UUID = Field(..., description="ID de la sucursal donde ingresa el inventario")
    temporada_id: Optional[uuid.UUID] = Field(None, description="Temporada opcional asociada al lote")
    coleccion_id: Optional[uuid.UUID] = Field(None, description="Colección opcional asociada al lote")
    recibido_por_id: uuid.UUID = Field(..., description="Usuario que recibe el lote")
    numero_documento: Optional[str] = Field(None, max_length=100, description="Número de documento/factura del proveedor")
    observacion: Optional[str] = Field(None, description="Observación")
    detalles: List[DetalleLoteCrearDTO] = Field(..., min_length=1, description="Al menos un detalle de variante")

class DetalleLoteDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    lote_id: uuid.UUID
    variante_id: uuid.UUID
    cantidad: int
    costo_unitario: Decimal

class LoteRecepcionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    proveedor_id: uuid.UUID
    sucursal_id: uuid.UUID
    temporada_id: Optional[uuid.UUID] = None
    coleccion_id: Optional[uuid.UUID] = None
    recibido_por_id: uuid.UUID
    numero_documento: Optional[str] = None
    fecha_recepcion: datetime
    observacion: Optional[str] = None
    detalles: List[DetalleLoteDTO] = Field(default_factory=list)

# ---------- Disponibilidad y Catálogo Extra ----------

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
