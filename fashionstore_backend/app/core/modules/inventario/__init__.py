"""Módulo canónico: Inventario y Abastecimiento (CU04, CU07)."""
from backend.app.core.modules.inventario.models import (
    LoteRecepcion,
    DetalleLoteRecepcion,
    InventarioSucursal,
    MovimientoInventario,
)
from backend.app.core.modules.inventario.schemas import (
    ProveedorCrearDTO,
    ProveedorDTO,
    DetalleLoteCrearDTO,
    LoteRecepcionCrearDTO,
    DetalleLoteDTO,
    LoteRecepcionDTO,
    FiltroOpcionItemDTO,
    TallaOpcionDTO,
    ColorOpcionDTO,
    FiltrosOpcionesDTO,
    DisponibilidadSucursalDTO,
)

__all__ = [
    "LoteRecepcion",
    "DetalleLoteRecepcion",
    "InventarioSucursal",
    "MovimientoInventario",
    "ProveedorCrearDTO",
    "ProveedorDTO",
    "DetalleLoteCrearDTO",
    "LoteRecepcionCrearDTO",
    "DetalleLoteDTO",
    "LoteRecepcionDTO",
    "FiltroOpcionItemDTO",
    "TallaOpcionDTO",
    "ColorOpcionDTO",
    "FiltrosOpcionesDTO",
    "DisponibilidadSucursalDTO",
]
