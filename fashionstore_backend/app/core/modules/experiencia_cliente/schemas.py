"""Schemas del módulo Experiencia Cliente (CU17, CU18, CU20)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

CONSENTIMIENTO_VIGENTE = "decart-v1"


class PruebaVirtualDTO(BaseModel):
    variante_id: uuid.UUID
    compatible: bool
    imagen_prenda_url: str
    prompt_prenda: str
    proveedor: str = "DECART"
    modelo: str = "lucy-2.5"
    aviso_orientativo: str = (
        "Visualización orientativa; no garantiza talla, color, reproducción exacta ni ajuste físico."
    )


class AutorizacionCrearDTO(BaseModel):
    variante_id: uuid.UUID
    consentimiento_version: str = Field(..., description="Debe ser 'decart-v1'")


class AutorizacionDTO(BaseModel):
    client_token: str
    expires_at: datetime
    modelo: str = "lucy-2.5"
    max_session_duration_seconds: int = 120
    imagen_prenda_url: str
    prompt_prenda: str


class NavegacionCrearDTO(BaseModel):
    evento: Literal["VISTA", "PRUEBA_VIRTUAL", "CARRITO", "COMPRA", "BUSQUEDA"] = Field(
        ..., description="Evento sanitizado; nunca incluye contenido audiovisual"
    )
    variante_id: Optional[uuid.UUID] = None
    producto_id: Optional[uuid.UUID] = None


class RecomendacionPedirDTO(BaseModel):
    limite: int = Field(5, ge=1, le=20)
    categoria: Optional[str] = None
    talla: Optional[str] = None


class RecomendacionItemDTO(BaseModel):
    producto_id: uuid.UUID
    variante_id: uuid.UUID
    nombre: str
    precio: Decimal
    disponible: int
    motivo: str


class RecomendacionRespuestaDTO(BaseModel):
    items: List[RecomendacionItemDTO]
    proveedor: str = "DETERMINISTA"


class BusquedaVozDTO(BaseModel):
    texto: str = Field(..., min_length=2, max_length=500)


class BusquedaRespuestaDTO(BaseModel):
    filtros: dict
    total: int
    items: List[RecomendacionItemDTO]
    proveedor: str = "DETERMINISTA"


from backend.app.core.modules.analitica.schemas import (
    ReportePedirDTO,
    ReporteRespuestaDTO,
    DecisionPedirDTO,
    DecisionItemDTO,
    DecisionRespuestaDTO,
)


__all__ = [
    "CONSENTIMIENTO_VIGENTE",
    "PruebaVirtualDTO",
    "AutorizacionCrearDTO",
    "AutorizacionDTO",
    "NavegacionCrearDTO",
    "RecomendacionPedirDTO",
    "RecomendacionItemDTO",
    "RecomendacionRespuestaDTO",
    "BusquedaVozDTO",
    "BusquedaRespuestaDTO",
    "ReportePedirDTO",
    "ReporteRespuestaDTO",
    "DecisionPedirDTO",
    "DecisionItemDTO",
    "DecisionRespuestaDTO",
]
