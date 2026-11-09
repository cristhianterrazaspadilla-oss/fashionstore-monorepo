"""Modelos de Dominio y DTOs: Órdenes de Pago y Métodos Preparados (CU22 Stripe Test E2).

Mapeo de las tablas en PostgreSQL (0009_modelo_final_66):
- comercial.metodos_preparados
- comercial.ordenes_pago
- comercial.eventos_proveedor
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from backend.app.core.database import Base


def _ahora_utc():
    return datetime.now(timezone.utc)


class MetodoPreparado(Base):
    __tablename__ = "metodos_preparados"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_metodos_preparados_id_empresa"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False, index=True)
    proveedor = Column(String(32), nullable=False, default="STRIPE")
    cliente_proveedor_cifrado = Column(LargeBinary, nullable=False)
    metodo_proveedor_cifrado = Column(LargeBinary, nullable=False)
    preparacion_proveedor_cifrado = Column(LargeBinary, nullable=True)
    estado = Column(String(16), nullable=False, default="PENDIENTE")  # LISTO, REVOCADO, PENDIENTE
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    revocado_en = Column(DateTime(timezone=True), nullable=True)


class OrdenPago(Base):
    __tablename__ = "ordenes_pago"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_ordenes_pago_id_empresa"),
        UniqueConstraint("proveedor", "clave_externa", name="uq_ordenes_pago_prov_clave"),
        UniqueConstraint("proveedor", "referencia_externa", name="uq_ordenes_pago_prov_ref"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    contexto = Column(String(12), nullable=False)  # PEDIDO, CAMBIO, RESERVA, VENTA
    pedido_id = Column(UUID(as_uuid=True), nullable=True)
    reserva_id = Column(UUID(as_uuid=True), ForeignKey("comercial.reservas.id"), nullable=True)
    venta_id = Column(UUID(as_uuid=True), ForeignKey("comercial.ventas.id"), nullable=True)
    cambio_id = Column(UUID(as_uuid=True), nullable=True)
    proveedor = Column(String(32), nullable=False, default="STRIPE")
    clave_externa = Column(String(120), nullable=False)
    referencia_externa = Column(String(180), nullable=True)
    estado = Column(String(32), nullable=False, default="PENDIENTE")  # PENDIENTE, REQUIERE_ACCION_CLIENTE, CAPTURADO, FALLIDO
    monto_bob = Column(Numeric(14, 2), nullable=False)
    tasa_id = Column(UUID(as_uuid=True), ForeignKey("plataforma.tasas_cambio.id"), nullable=True)
    monto_usd = Column(Numeric(14, 2), nullable=True)
    centavos_usd = Column(BigInteger, nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    actualizada_en = Column(DateTime(timezone=True), default=_ahora_utc, onupdate=_ahora_utc, nullable=False)


class EventoProveedor(Base):
    __tablename__ = "eventos_proveedor"
    __table_args__ = (
        UniqueConstraint("proveedor", "evento_externo_id", name="uq_eventos_prov_id"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    orden_pago_id = Column(UUID(as_uuid=True), ForeignKey("comercial.ordenes_pago.id"), nullable=True)
    proveedor = Column(String(32), nullable=False)
    evento_externo_id = Column(String(180), nullable=False)
    tipo = Column(String(100), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    payload_ref = Column(Text, nullable=True)
    estado = Column(String(20), nullable=False, default="RECIBIDO")
    recibido_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    procesado_en = Column(DateTime(timezone=True), nullable=True)


# -------------------------------------------------------------
# DTOs Pydantic para CU22 (E2)
# -------------------------------------------------------------

class MetodoPrepararDTO(BaseModel):
    huella_dispositivo: Optional[str] = Field(None, description="Huella o identificador de dispositivo del cliente")


class MetodoConfirmarDTO(BaseModel):
    payment_method_id: Optional[str] = Field(None, description="ID de PaymentMethod retornado por Stripe tras confirmación en cliente")


class MetodoPreparadoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    preparacion_pago_id: uuid.UUID
    client_secret: Optional[str] = None
    estado: str  # PENDIENTE, LISTO, REVOCADO
    proveedor: str = "STRIPE"


class OrdenPagoCrearDTO(BaseModel):
    contexto: str = Field(..., description="Contexto: PEDIDO, CAMBIO, RESERVA, VENTA")
    recurso_id: uuid.UUID = Field(..., description="ID del recurso (venta, pedido, reserva o cambio)")
    oferta_revision: Optional[int] = Field(1, description="Revisión de oferta aceptada")
    metodo_preparado_id: Optional[uuid.UUID] = Field(None, description="Método preparado online previo si aplica")
    consentimiento_cobro_posterior: Optional[bool] = Field(False, description="Consentimiento explícito para cobro posterior")


class OrdenPagoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    orden_pago_id: uuid.UUID
    estado: str  # PENDIENTE, REQUIERE_ACCION_CLIENTE, CAPTURADO, FALLIDO
    monto_bob: Decimal
    monto_usd: Optional[Decimal] = None
    centavos_usd: Optional[int] = None
    tasa_id: Optional[uuid.UUID] = None
    client_secret: Optional[str] = None
    referencia_externa: Optional[str] = None


class ContinuarAccionDTO(BaseModel):
    payment_intent_id: Optional[str] = Field(None, description="PaymentIntent ID confirmado por cliente en 3DS")


class LineaRecuperadaCajaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    variante_id: uuid.UUID
    cantidad: int
    precio_unitario_bob: Decimal
    descuento_bob: Decimal = Decimal("0.00")
    sku: Optional[str] = None
    nombre_producto: Optional[str] = None


class OrdenActivaCajaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    orden_pago_id: uuid.UUID
    venta_id: uuid.UUID
    stripe_payment_intent_id: Optional[str] = None
    client_secret: Optional[str] = None
    monto_bob: Decimal
    monto_usd: Optional[Decimal] = None
    centavos_usd: Optional[int] = None
    tasa_bob_por_usd: Optional[Decimal] = None
    estado_orden: str
    estado: Optional[str] = None  # Compatibilidad hacia atrás con inspectores de prueba previos
    sucursal_id: uuid.UUID
    turno_caja_id: Optional[uuid.UUID] = None
    cliente_id: Optional[uuid.UUID] = None
    procedencia: str = "PRESENCIAL"  # "TURNO_OFFLINE" | "PRESENCIAL"
    lineas: List[LineaRecuperadaCajaDTO] = Field(default_factory=list)
    estado_verificacion: str = "VERIFICADO"  # "VERIFICADO" | "NO_VERIFICADO_ERROR_PASARELA" | "PROVISIONAL_PENDIENTE_INTENTO"
    provisional: Optional[bool] = False


__all__ = [
    "MetodoPreparado",
    "OrdenPago",
    "EventoProveedor",
    "MetodoPrepararDTO",
    "MetodoConfirmarDTO",
    "MetodoPreparadoDTO",
    "OrdenPagoCrearDTO",
    "OrdenPagoDTO",
    "ContinuarAccionDTO",
    "LineaRecuperadaCajaDTO",
    "OrdenActivaCajaDTO",
]
