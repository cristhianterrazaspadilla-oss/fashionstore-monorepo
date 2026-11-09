"""Modelos del paquete Identidad y Empresas (CU01, CU02 / previstos CU26, CU27).

Define Rol, Usuario, Cliente y Empleado para autenticación y control de acceso.
"""
import uuid
from backend.app.core.reloj import utcnow
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, ForeignKey, Date, Integer,
    BigInteger, CheckConstraint, UniqueConstraint, Index, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (
        CheckConstraint("estado IN ('PENDIENTE_PLAN','ACTIVA','SUSPENDIDA')", name="ck_empresas_estado"),
        CheckConstraint("catalogo_version > 0", name="ck_empresas_catalogo_version"),
        CheckConstraint("plazo_cambios_dias > 0", name="ck_empresas_plazo_cambios"),
        {"schema": "organizacion"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo = Column(String(60), nullable=False, unique=True)
    nombre = Column(String(180), nullable=False)
    razon_social = Column(String(200), nullable=False, default="")
    nombre_comercial = Column(String(180), nullable=False, default="")
    estado = Column(String(24), nullable=False, default="PENDIENTE_PLAN")
    catalogo_version = Column(BigInteger, nullable=False, default=1)
    catalogo_actualizado_en = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    plazo_cambios_dias = Column(Integer, nullable=False, default=15)
    creada_en = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    actualizada_en = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Plan(Base):
    __tablename__ = "planes"
    __table_args__ = (
        CheckConstraint("max_sucursales_activas > 0", name="ck_planes_max_sucursales"),
        {"schema": "plataforma"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo = Column(String(30), nullable=False, unique=True)
    nombre = Column(String(80), nullable=False)
    max_sucursales_activas = Column(Integer, nullable=False)
    reportes_generativos = Column(Boolean, nullable=False, default=False)
    modelos_ml = Column(Boolean, nullable=False, default=False)
    permite_operacion_offline = Column(Boolean, nullable=False, default=True)
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Suscripcion(Base):
    __tablename__ = "suscripciones"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_suscripciones_version"),
        CheckConstraint("inicia_en < vence_en", name="ck_suscripciones_vigencia"),
        UniqueConstraint("empresa_id", "version", name="uq_suscripciones_empresa_version"),
        Index("ix_suscripciones_empresa_vence", "empresa_id", "vence_en"),
        {"schema": "organizacion"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plataforma.planes.id"), nullable=False)
    version = Column(Integer, nullable=False)
    inicia_en = Column(DateTime(timezone=True), nullable=False)
    vence_en = Column(DateTime(timezone=True), nullable=False)
    creada_en = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    creada_por = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    motivo = Column(Text, nullable=False)


class Rol(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "seguridad"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(50), nullable=False, unique=True)
    descripcion = Column(Text, nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    usuarios = relationship("Usuario", back_populates="rol")


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_usuarios_id_empresa"),
        Index(
            "uq_usuarios_empresa_correo", "empresa_id", text("lower(correo_electronico)"),
            unique=True, postgresql_where=text("empresa_id IS NOT NULL"),
        ),
        Index(
            "uq_usuarios_plataforma_correo", text("lower(correo_electronico)"),
            unique=True, postgresql_where=text("empresa_id IS NULL"),
        ),
        {"schema": "seguridad"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=True, index=True)
    rol_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.roles.id"), nullable=False)
    nombres = Column(String(100), nullable=False)
    apellidos = Column(String(100), nullable=False)
    correo_electronico = Column(String(160), nullable=False)
    contrasenia_hash = Column(String(255), nullable=False)
    telefono = Column(String(30), nullable=True)
    estado = Column(String(20), nullable=False, default="ACTIVO")
    revision = Column(Integer, nullable=False, default=1)
    creado_en = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    actualizado_en = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    rol = relationship("Rol", back_populates="usuarios")
    cliente = relationship("Cliente", back_populates="usuario", uselist=False, cascade="all, delete-orphan")
    empleado = relationship("Empleado", back_populates="usuario", uselist=False, cascade="all, delete-orphan")

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombres} {self.apellidos}".strip()


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = {"schema": "seguridad"}

    usuario_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id", ondelete="CASCADE"), primary_key=True)
    direccion_referencia = Column(Text, nullable=True)
    fecha_nacimiento = Column(Date, nullable=True)
    preferencias = Column(JSONB, nullable=False, default=dict)

    usuario = relationship("Usuario", back_populates="cliente")


class Empleado(Base):
    __tablename__ = "empleados"
    __table_args__ = {"schema": "seguridad"}

    usuario_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id", ondelete="CASCADE"), primary_key=True)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=True)
    cargo = Column(String(80), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)

    usuario = relationship("Usuario", back_populates="empleado")
