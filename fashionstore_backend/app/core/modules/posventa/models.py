"""Modelos de Dominio: Posventa — Saldos y Reembolsos (CU09, CU27).

Mapeo de las tablas en PostgreSQL (0009_modelo_final_66):
- comercial.movimientos_saldo
- comercial.obligaciones_reembolso
- comercial.componentes_reembolso
- comercial.ejecuciones_reembolso
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.app.core.database import Base


def _ahora_utc():
    return datetime.now(timezone.utc)


class MovimientoSaldo(Base):
    __tablename__ = "movimientos_saldo"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_movimientos_saldo_id_empresa"),
        UniqueConstraint("empresa_id", "referencia_unica", "tipo", name="uq_movimientos_saldo_empresa_ref_tipo"),
        Index("ix_movimientos_saldo_cuenta", "empresa_id", "cliente_id", "creado_en", "id"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False, index=True)
    tipo = Column(String(16), nullable=False)  # CREDITO, DEBITO, RETENCION, LIBERACION, RESTAURACION
    monto_bob = Column(Numeric(14, 2), nullable=False)
    origen_tipo = Column(String(24), nullable=False)  # VENTA, PEDIDO, CAMBIO, DEVOLUCION, REEMBOLSO, MANUAL
    origen_id = Column(UUID(as_uuid=True), nullable=False)
    referencia_unica = Column(UUID(as_uuid=True), nullable=False)
    estado = Column(String(20), nullable=False, default="CONFIRMADO")
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)


class ObligacionReembolso(Base):
    __tablename__ = "obligaciones_reembolso"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_obligaciones_reembolso_id_empresa"),
        UniqueConstraint("empresa_id", "origen_tipo", "origen_id", "motivo_codigo", name="uq_obligaciones_reembolso_empresa_origen_motivo"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False, index=True)
    origen_tipo = Column(String(20), nullable=False)  # PEDIDO, DEVOLUCION, CAMBIO, VENTA
    origen_id = Column(UUID(as_uuid=True), nullable=False)
    motivo_codigo = Column(String(60), nullable=False)
    estado = Column(String(30), nullable=False, default="PENDIENTE_AUTORIZACION")
    monto_bob = Column(Numeric(14, 2), nullable=False)
    politica_id = Column(UUID(as_uuid=True), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    autorizada_en = Column(DateTime(timezone=True), nullable=True)
    completada_en = Column(DateTime(timezone=True), nullable=True)

    componentes = relationship(
        "backend.app.core.modules.posventa.models.ComponenteReembolso",
        back_populates="obligacion",
        cascade="all, delete-orphan",
    )


class ComponenteReembolso(Base):
    __tablename__ = "componentes_reembolso"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_componentes_reembolso_id_empresa"),
        UniqueConstraint("obligacion_id", "pago_id", "medio", name="uq_componentes_reembolso_oblig_pago_medio"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    obligacion_id = Column(UUID(as_uuid=True), ForeignKey("comercial.obligaciones_reembolso.id"), nullable=False)
    pago_id = Column(UUID(as_uuid=True), ForeignKey("comercial.pagos.id"), nullable=True)
    medio = Column(String(20), nullable=False)  # STRIPE, EFECTIVO, SALDO
    monto_bob = Column(Numeric(14, 2), nullable=False)
    monto_usd = Column(Numeric(14, 2), nullable=True)
    centavos_usd = Column(BigInteger, nullable=True)
    tasa_bob_por_usd = Column(Numeric(18, 8), nullable=True)
    estado = Column(String(30), nullable=False, default="PENDIENTE")

    obligacion = relationship(
        "backend.app.core.modules.posventa.models.ObligacionReembolso",
        back_populates="componentes",
    )
    ejecuciones = relationship(
        "backend.app.core.modules.posventa.models.EjecucionReembolso",
        back_populates="componente",
        cascade="all, delete-orphan",
    )


class EjecucionReembolso(Base):
    __tablename__ = "ejecuciones_reembolso"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_ejecuciones_reembolso_id_empresa"),
        UniqueConstraint("empresa_id", "clave_ejecucion", name="uq_ejecuciones_reembolso_empresa_clave"),
        UniqueConstraint("proveedor", "referencia_externa", name="uq_ejecuciones_reembolso_prov_ref"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    componente_id = Column(UUID(as_uuid=True), ForeignKey("comercial.componentes_reembolso.id"), nullable=False)
    clave_ejecucion = Column(UUID(as_uuid=True), nullable=False)
    proveedor = Column(String(32), nullable=True)  # STRIPE, MANUAL_CAJA, SALDO_LIBRO
    referencia_externa = Column(String(180), nullable=True)
    estado = Column(String(30), nullable=False, default="EN_PROCESO")
    intento = Column(Integer, nullable=False, default=1)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    resuelta_en = Column(DateTime(timezone=True), nullable=True)

    componente = relationship(
        "backend.app.core.modules.posventa.models.ComponenteReembolso",
        back_populates="ejecuciones",
    )


__all__ = [
    "MovimientoSaldo",
    "ObligacionReembolso",
    "ComponenteReembolso",
    "EjecucionReembolso",
]
