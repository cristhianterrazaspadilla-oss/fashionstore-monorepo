"""Schemas del módulo Posventa — Devoluciones, Mermas, Saldos y Reembolsos (CU09, CU12, CU27)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


# -------------------------------------------------------------
# Schemas CU12 / Mermas y Devoluciones
# -------------------------------------------------------------

class DevolucionCrearDTO(BaseModel):
    detalle_venta_id: uuid.UUID = Field(..., description="Linea de venta a devolver (parcial acumulable)")
    cantidad: int = Field(..., description="Cantidad a devolver (>0, validado en servicio -> 400)")
    motivo: Optional[str] = Field(None, description="Motivo de la devolucion")


class DevolucionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    detalle_venta_id: uuid.UUID
    venta_id: uuid.UUID
    variante_id: uuid.UUID
    sucursal_id: uuid.UUID
    cantidad: int
    costo_unitario: Decimal
    motivo: Optional[str] = None
    responsable_id: Optional[uuid.UUID] = None
    fecha_hora: datetime


class MermaCrearDTO(BaseModel):
    variante_id: uuid.UUID = Field(...)
    sucursal_id: uuid.UUID = Field(...)
    cantidad: int = Field(..., description="Cantidad mermada (>0, validado en servicio -> 400)")
    causa: Optional[str] = Field(None, description="Causa documentada (obligatoria -> 400 si falta)")
    responsable_id: Optional[uuid.UUID] = Field(None, description="Responsable (por defecto quien registra)")


class MermaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    variante_id: uuid.UUID
    sucursal_id: uuid.UUID
    cantidad: int
    costo_unitario: Decimal
    causa: Optional[str] = None
    responsable_id: Optional[uuid.UUID] = None
    fecha_hora: datetime


# -------------------------------------------------------------
# Schemas CU09 / Saldo Personal
# -------------------------------------------------------------

class MovimientoSaldoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tipo: str  # CREDITO, DEBITO, RETENCION, LIBERACION, RESTAURACION
    monto_bob: Decimal
    origen_tipo: str
    origen_id: uuid.UUID
    referencia_unica: uuid.UUID
    estado: str
    creado_en: datetime


class SaldoResumenDTO(BaseModel):
    saldo_disponible_bob: Decimal
    saldo_retenido_bob: Decimal
    movimientos: List[MovimientoSaldoDTO] = Field(default_factory=list)


class AplicarSaldoDTO(BaseModel):
    monto_bob: Decimal = Field(..., gt=0, description="Importe a retener/aplicar en BOB")
    revision: Optional[int] = Field(1, description="Revisión de la venta/pedido")


class SaldoAplicadoDTO(BaseModel):
    saldo_disponible_bob: Decimal
    saldo_retenido_bob: Decimal
    movimiento_id: uuid.UUID
    restante_por_pagar_bob: Decimal


# -------------------------------------------------------------
# Schemas CU27 / Reembolsos
# -------------------------------------------------------------

class ReembolsoSolicitudDTO(BaseModel):
    origen_tipo: str = Field(..., description="PEDIDO, DEVOLUCION, CAMBIO, VENTA")
    origen_id: uuid.UUID = Field(..., description="ID de la operación origen")
    motivo_codigo: str = Field(..., description="Código de causa o motivo")
    motivo_descripcion: Optional[str] = Field(None, description="Descripción opcional")
    unidades: Optional[int] = Field(None, description="Unidades declaradas si procede")


class ReembolsoAutorizarDTO(BaseModel):
    motivo_aprobacion: Optional[str] = Field(None, description="Justificación o motivo de aprobación")


class ReembolsoEjecutarDTO(BaseModel):
    clave_ejecucion: uuid.UUID = Field(..., description="UUID único de ejecución para evitar dobles desembolsos")


class ComponenteReembolsoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    medio: str  # STRIPE, EFECTIVO, SALDO
    monto_bob: Decimal
    monto_usd: Optional[Decimal] = None
    centavos_usd: Optional[int] = None
    tasa_bob_por_usd: Optional[Decimal] = None
    estado: str  # PENDIENTE, EN_PROCESO, COMPLETADO, FALLIDO
    pago_id: Optional[uuid.UUID] = None


class EjecucionReembolsoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    clave_ejecucion: uuid.UUID
    proveedor: Optional[str] = None
    referencia_externa: Optional[str] = None
    estado: str  # EN_PROCESO, COMPLETADO, FALLIDO
    intento: int
    creada_en: datetime
    resuelta_en: Optional[datetime] = None


class ReembolsoDetalleDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    empresa_id: uuid.UUID
    cliente_id: uuid.UUID
    origen_tipo: str
    origen_id: uuid.UUID
    motivo_codigo: str
    estado: str  # PENDIENTE_AUTORIZACION, AUTORIZADO, EN_PROCESO, COMPLETADO, FALLIDO, RECHAZADO
    monto_bob: Decimal
    revision: int = 1
    creada_en: datetime
    autorizada_en: Optional[datetime] = None
    completada_en: Optional[datetime] = None
    componentes: List[ComponenteReembolsoDTO] = Field(default_factory=list)


__all__ = [
    "DevolucionCrearDTO",
    "DevolucionDTO",
    "MermaCrearDTO",
    "MermaDTO",
    "MovimientoSaldoDTO",
    "SaldoResumenDTO",
    "AplicarSaldoDTO",
    "SaldoAplicadoDTO",
    "ReembolsoSolicitudDTO",
    "ReembolsoAutorizarDTO",
    "ReembolsoEjecutarDTO",
    "ComponenteReembolsoDTO",
    "EjecucionReembolsoDTO",
    "ReembolsoDetalleDTO",
]
