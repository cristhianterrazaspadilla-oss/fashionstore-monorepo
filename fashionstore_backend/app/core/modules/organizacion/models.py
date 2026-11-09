"""Modelos del paquete organizacional (CU03 / CU15 / CU12 / RF03).

Define las entidades Ciudad, Sucursal y TasaCambio.
"""
import uuid
from sqlalchemy import (
    Column, String, Text, Boolean, SmallInteger, Numeric, ForeignKey,
    UniqueConstraint, CheckConstraint, Index, Integer, DateTime, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.core.reloj import utcnow


class Ciudad(Base):
    __tablename__ = "ciudades"
    __table_args__ = {"schema": "organizacion"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(100), nullable=False, unique=True)
    activo = Column(Boolean, nullable=False, default=True)

    sucursales = relationship("Sucursal", back_populates="ciudad")


class Sucursal(Base):
    __tablename__ = "sucursales"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_sucursales_id_empresa"),
        Index(
            "uq_sucursales_empresa_ciudad_nombre", "empresa_id", "ciudad_id",
            text("lower(nombre)"), unique=True,
        ),
        CheckConstraint(
            "modalidad_adelanto IS NULL OR modalidad_adelanto IN ('MONTO_FIJO','PORCENTAJE')",
            name="ck_sucursales_modalidad_adelanto",
        ),
        CheckConstraint("valor_adelanto >= 0", name="ck_sucursales_valor_adelanto_nneg"),
        CheckConstraint(
            "modalidad_adelanto IS NULL OR modalidad_adelanto <> 'PORCENTAJE' OR valor_adelanto <= 100",
            name="ck_sucursales_adelanto_porcentaje_max",
        ),
        CheckConstraint(
            "(adelanto_activo = FALSE) OR (modalidad_adelanto IS NOT NULL AND valor_adelanto > 0)",
            name="ck_sucursales_adelanto_coherente",
        ),
        {"schema": "organizacion"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(
        UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True
    )
    ciudad_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.ciudades.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    direccion = Column(Text, nullable=False)
    telefono = Column(String(30), nullable=True)
    numero_anillo = Column(SmallInteger, nullable=True)
    tarifa_base_delivery = Column(Numeric(12, 2), nullable=False, default=0)
    incremento_anillo_delivery = Column(Numeric(12, 2), nullable=False, default=0)
    anillo_minimo_delivery = Column(SmallInteger, nullable=False, default=1)
    anillo_maximo_delivery = Column(SmallInteger, nullable=False, default=10)
    delivery_activo = Column(Boolean, nullable=False, default=True)
    activa = Column(Boolean, nullable=False, default=True)
    revision = Column(Integer, nullable=False, default=1)
    # Politica de adelanto por sucursal (decision 13, RN-03)
    adelanto_activo = Column(Boolean, nullable=False, default=False)
    modalidad_adelanto = Column(String(20), nullable=True)
    valor_adelanto = Column(Numeric(12, 2), nullable=False, default=0)

    ciudad = relationship("Ciudad", back_populates="sucursales")


class TasaCambio(Base):
    """CU12: Tasa de conversión oficial BOB/USD de la plataforma con vigencias no solapadas."""
    __tablename__ = "tasas_cambio"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_tasas_cambio_version_pos"),
        CheckConstraint("tasa_bob_por_usd > 0", name="ck_tasas_cambio_tasa_pos"),
        CheckConstraint("vigente_hasta IS NULL OR vigente_desde < vigente_hasta", name="ck_tasas_cambio_vigencia"),
        {"schema": "plataforma"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version = Column(Integer, nullable=False, unique=True)
    tasa_bob_por_usd = Column(Numeric(18, 8), nullable=False)
    vigente_desde = Column(DateTime(timezone=True), nullable=False)
    vigente_hasta = Column(DateTime(timezone=True), nullable=True)
    motivo = Column(Text, nullable=False)
    creada_por = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    creada_en = Column(DateTime(timezone=True), default=utcnow, nullable=False)
