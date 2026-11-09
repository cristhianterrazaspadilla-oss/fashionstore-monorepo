"""Modelos ORM de Analítica y Modelos ML — E2 (CU10, CU11, CU23, CU24, CU25)."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    BigInteger,
    ForeignKey,
    DateTime,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


def _ahora_utc():
    return datetime.now(timezone.utc)


class ModeloML(Base):
    __tablename__ = "modelos_ml"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_modelos_ml_id_empresa"),
        {"schema": "inteligencia", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    tipo = Column(String(50), nullable=False)  # PRONOSTICO_DEMANDA | SEGMENTACION_PRODUCTOS
    version = Column(Integer, nullable=False, default=1)
    origen_datos = Column(String(50), nullable=False, default="DATOS_REALES")
    semilla = Column(BigInteger, nullable=True, default=42)
    dataset_version = Column(String(50), nullable=False, default="v1.0")
    dataset_hash = Column(String(128), nullable=True)
    metricas = Column(JSONB, nullable=False, default=dict)
    artefacto_uri = Column(Text, nullable=False)
    artefacto_hash = Column(String(128), nullable=False)
    resultado_uri = Column(Text, nullable=False)
    resultado_hash = Column(String(128), nullable=False)
    esquema_resultado_version = Column(Integer, nullable=False, default=1)
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)


class SolicitudIA(Base):
    __tablename__ = "solicitudes_ia"
    __table_args__ = (
        {"schema": "inteligencia", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    cliente_id = Column(UUID(as_uuid=True), nullable=True)
    tipo = Column(String(50), nullable=False)
    entrada = Column(Text, nullable=False)
    funcion_usada = Column(String(100), nullable=True)
    parametros = Column(JSONB, nullable=True)
    respuesta = Column(Text, nullable=True)
    datos = Column(JSONB, nullable=True)
    proveedor = Column(String(50), nullable=True, default="gemini-3.8-flash")
    latencia_ms = Column(Integer, nullable=True, default=0)
    filtros_autorizados = Column(JSONB, nullable=True)
    snapshot_uri = Column(Text, nullable=True)
    snapshot_hash = Column(String(128), nullable=True)
    exportacion_uri = Column(Text, nullable=True)
    estado = Column(String(30), nullable=False, default="COMPLETADA")
    revision = Column(Integer, nullable=False, default=1)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
