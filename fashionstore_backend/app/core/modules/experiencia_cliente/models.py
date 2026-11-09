"""Modelos de Dominio: Experiencia Cliente (CU17, CU18, CU20)."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from backend.app.core.database import Base


def _ahora_utc():
    return datetime.now(timezone.utc)


class HistorialNavegacion(Base):
    """inteligencia.historial_navegacion — eventos incl. PRUEBA_VIRTUAL (CU17/CU18)."""

    __tablename__ = "historial_navegacion"
    __table_args__ = (
        Index("idx_navegacion_cliente_fecha", "cliente_id", "creada_en"),
        Index("idx_navegacion_evento", "evento"),
        UniqueConstraint("id", "empresa_id", name="uq_historial_navegacion_id_empresa"),
        {"schema": "inteligencia"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    cliente_id = Column(
        UUID(as_uuid=True), ForeignKey("seguridad.clientes.usuario_id"), nullable=True
    )
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    variante_id = Column(
        UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=True
    )
    producto_id = Column(
        UUID(as_uuid=True), ForeignKey("catalogo.productos.id"), nullable=True
    )
    evento = Column(String(40), nullable=False)
    metadatos = Column(JSONB, nullable=False, default=dict)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)


class SolicitudIA(Base):
    """inteligencia.solicitudes_ia — auditoría de IA con respuesta y datos (CU18/20/21/25)."""

    __tablename__ = "solicitudes_ia"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('RECOMENDACION','BUSQUEDA_VOZ','REPORTE','DECISION_INVENTARIO')",
            name="ck_solicitudes_ia_tipo",
        ),
        Index("idx_solicitudes_tipo_fecha", "tipo", "creada_en"),
        Index("idx_solicitudes_usuario", "usuario_id"),
        UniqueConstraint("id", "empresa_id", name="uq_solicitudes_ia_id_empresa"),
        {"schema": "inteligencia"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    cliente_id = Column(
        UUID(as_uuid=True), ForeignKey("seguridad.clientes.usuario_id"), nullable=True
    )
    tipo = Column(String(30), nullable=False)
    entrada = Column(Text, nullable=False, default="")
    funcion_usada = Column(String(60), nullable=True)
    parametros = Column(JSONB, nullable=False, default=dict)
    respuesta = Column(Text, nullable=False, default="")
    datos = Column(JSONB, nullable=False, default=dict)
    proveedor = Column(String(20), nullable=False, default="DETERMINISTA")
    latencia_ms = Column(Integer, nullable=False, default=0)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)


__all__ = [
    "HistorialNavegacion",
    "SolicitudIA",
]
