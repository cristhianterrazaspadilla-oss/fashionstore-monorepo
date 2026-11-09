"""Modelos de Dominio: Dispositivos, Notificaciones y Outbox (E2 Avisos y Recuperación).

Mapeo de tablas existentes en PostgreSQL (0009_modelo_final_66):
- seguridad.dispositivos_autorizados
- comercial.eventos_outbox
- comercial.notificaciones
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.app.core.database import Base


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class DispositivoAutorizado(Base):
    __tablename__ = "dispositivos_autorizados"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_dispositivos_aut_id_empresa"),
        UniqueConstraint("empresa_id", "usuario_id", "canal", "dispositivo_id", name="uq_dispositivos_emp_usr_canal_disp"),
        {"schema": "seguridad", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    usuario_id = Column(UUID(as_uuid=True), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), nullable=True)
    canal = Column(String(12), nullable=False)  # 'PWA', 'FLUTTER'
    dispositivo_id = Column(UUID(as_uuid=True), nullable=False)
    push_destino_cifrado = Column(LargeBinary, nullable=True)
    push_destino_hash = Column(String(64), nullable=True)
    estado = Column(String(16), nullable=False, default="ACTIVO")  # 'ACTIVO', 'REVOCADO'
    revision = Column(Integer, nullable=False, default=1)
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    revocado_en = Column(DateTime(timezone=True), nullable=True)


class EventoOutbox(Base):
    __tablename__ = "eventos_outbox"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_eventos_outbox_id_empresa"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    recurso_tipo = Column(String(50), nullable=False)
    recurso_id = Column(UUID(as_uuid=True), nullable=False)
    transicion = Column(String(60), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    dispositivo_id = Column(UUID(as_uuid=True), nullable=True)
    payload = Column(JSONB, nullable=False)
    estado = Column(String(20), nullable=False, default="PENDIENTE")  # PENDIENTE, ENVIADO, REINTENTO, FALLIDO
    intentos = Column(Integer, nullable=False, default=0)
    proximo_intento_en = Column(DateTime(timezone=True), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    entregado_en = Column(DateTime(timezone=True), nullable=True)


class Notificacion(Base):
    __tablename__ = "notificaciones"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_notificaciones_id_empresa"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    usuario_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    outbox_id = Column(UUID(as_uuid=True), nullable=True)
    tipo = Column(String(50), nullable=False)
    titulo = Column(String(180), nullable=False)
    cuerpo = Column(Text, nullable=False)
    recurso_tipo = Column(String(50), nullable=True)
    recurso_id = Column(UUID(as_uuid=True), nullable=True)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    leida_en = Column(DateTime(timezone=True), nullable=True)
