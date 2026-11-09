"""Paquete funcional: Organización (CU03 / previsto CU37).

Gestión de ciudades, sucursales, tarifas de delivery y políticas de adelanto.
"""
from backend.app.core.modules.organizacion.models import Ciudad, Sucursal
from backend.app.core.modules.organizacion.schemas import (
    CiudadCrearDTO, CiudadDTO, SucursalCrearDTO, SucursalDTO,
    ConfigurarTarifasDeliveryDTO, ConfigurarAdelantoDTO,
)
from backend.app.core.modules.organizacion.services.ciudad_service import CiudadService
from backend.app.core.modules.organizacion.services.sucursal_service import SucursalService

__all__ = [
    "Ciudad", "Sucursal",
    "CiudadCrearDTO", "CiudadDTO", "SucursalCrearDTO", "SucursalDTO",
    "ConfigurarTarifasDeliveryDTO", "ConfigurarAdelantoDTO",
    "CiudadService", "SucursalService",
]
