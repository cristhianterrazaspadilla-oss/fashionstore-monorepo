"""Modelos de Dominio: Reservas y Traslados (CU08, CU09, CU10, CU24)."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    BigInteger,
    Numeric,
    ForeignKey,
    ForeignKeyConstraint,
    DateTime,
    UniqueConstraint,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ENUM, JSONB
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


def _ahora_utc():
    return datetime.now(timezone.utc)


EstadoReserva = ENUM(
    "PENDIENTE_TRASLADO",
    "PENDIENTE",
    "PREPARADA",
    "ATENDIDA",
    "COMPLETADA",
    "CANCELADA",
    "VENCIDA",
    name="estado_reserva",
    schema="comercial",
    create_type=False,
)

ESTADOS_LINEA_RESERVA = (
    "PENDIENTE_TRASLADO",
    "RESERVADA",
    "RECHAZADA",
    "VENDIDA_PARCIAL",
    "VENDIDA",
    "LIBERADA",
)

EstadoTraslado = ENUM(
    "SOLICITADO",
    "APROBADO",
    "RECHAZADO",
    "DESPACHADO",
    "RECIBIDO",
    "CANCELADO",
    name="estado_traslado",
    schema="inventario",
    create_type=False,
)


class Reserva(Base):
    __tablename__ = "reservas"
    __table_args__ = (
        CheckConstraint(
            "codigo LIKE 'FS-%'",
            name="ck_reservas_codigo_formato",
        ),
        CheckConstraint("revision >= 1", name="ck_reservas_revision"),
        CheckConstraint(
            "origen_plazo_en IS NULL OR vence_en >= origen_plazo_en",
            name="ck_reservas_origen_plazo",
        ),
        CheckConstraint(
            "operacion_sincronizacion_id IS NULL OR origen_plazo_en IS NOT NULL",
            name="ck_reservas_operacion_origen",
        ),
        UniqueConstraint("id", "empresa_id", name="uq_reservas_id_empresa"),
        UniqueConstraint(
            "operacion_sincronizacion_id", name="uq_reservas_operacion_sincronizacion"
        ),
        ForeignKeyConstraint(
            ["operacion_sincronizacion_id", "empresa_id"],
            ["comercial.operaciones_sincronizacion.id", "comercial.operaciones_sincronizacion.empresa_id"],
            name="fk_reservas_operacion_empresa",
        ),
        Index("uq_reservas_empresa_codigo", "empresa_id", "codigo", unique=True),
        Index("ix_reservas_empresa_estado_vence", "empresa_id", "estado", "vence_en"),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.clientes.usuario_id"), nullable=False)
    sucursal_destino_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    codigo = Column(String(50), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    estado = Column(EstadoReserva, nullable=False, default="PENDIENTE")
    fecha_creacion = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    fecha_visita = Column(DateTime(timezone=True), nullable=True)
    vence_en = Column(DateTime(timezone=True), nullable=False)
    origen_plazo_en = Column(DateTime(timezone=True), nullable=True)
    operacion_sincronizacion_id = Column(
        UUID(as_uuid=True), nullable=True,
    )
    observacion = Column(Text, nullable=True)
    adelanto_modalidad = Column(String(20), nullable=True)
    adelanto_valor = Column(Numeric(12, 2), nullable=True)
    adelanto_monto = Column(Numeric(12, 2), nullable=True)
    preparada_en = Column(DateTime(timezone=True), nullable=True)
    atendida_en = Column(DateTime(timezone=True), nullable=True)
    preparada_por = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    atendida_por = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    clave_idempotencia = Column(UUID(as_uuid=True), nullable=True, unique=True)
    hash_solicitud = Column(Text, nullable=True)

    detalles = relationship("DetalleReserva", back_populates="reserva", cascade="all, delete-orphan")


class DetalleReserva(Base):
    __tablename__ = "detalles_reserva"
    __table_args__ = (
        UniqueConstraint("reserva_id", "variante_id", name="uq_detalles_reserva_reserva_variante"),
        CheckConstraint("cantidad_solicitada > 0", name="ck_detalle_reserva_solicitada_pos"),
        CheckConstraint("cantidad_reservada >= 0", name="ck_detalle_reserva_reservada_nneg"),
        CheckConstraint("cantidad_pendiente_traslado >= 0", name="ck_detalle_reserva_pendtras_nneg"),
        CheckConstraint("cantidad_vendida >= 0", name="ck_detalle_reserva_vendida_nneg"),
        CheckConstraint("cantidad_liberada >= 0", name="ck_detalle_reserva_liberada_nneg"),
        CheckConstraint(
            "cantidad_reservada + cantidad_pendiente_traslado + cantidad_vendida + cantidad_liberada <= cantidad_solicitada",
            name="ck_detalle_reserva_cantidades_consistentes",
        ),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reserva_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comercial.reservas.id", ondelete="CASCADE"),
        nullable=False,
    )
    variante_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=False)
    cantidad_solicitada = Column(Integer, nullable=False)
    cantidad_reservada = Column(Integer, nullable=False, default=0)
    cantidad_pendiente_traslado = Column(Integer, nullable=False, default=0)
    cantidad_vendida = Column(Integer, nullable=False, default=0)
    cantidad_liberada = Column(Integer, nullable=False, default=0)
    estado_linea = Column(String(30), nullable=False, default="RESERVADA")

    reserva = relationship("Reserva", back_populates="detalles")


class ReferenciaHoraria(Base):
    __tablename__ = "referencias_horarias"
    __table_args__ = (
        CheckConstraint("emitida_en < vence_en", name="ck_referencias_horarias_vigencia"),
        UniqueConstraint(
            "id", "empresa_id", "usuario_id", "dispositivo_id",
            name="uq_referencias_ambito",
        ),
        ForeignKeyConstraint(
            ["usuario_id", "empresa_id"],
            ["seguridad.usuarios.id", "seguridad.usuarios.empresa_id"],
            name="fk_referencias_usuario_empresa",
        ),
        Index(
            "uq_referencias_empresa_idempotencia",
            "empresa_id",
            "clave_idempotencia",
            unique=True,
            postgresql_where=text("clave_idempotencia IS NOT NULL"),
        ),
        Index(
            "ix_referencias_usuario_dispositivo_vence",
            "empresa_id", "usuario_id", "dispositivo_id", "vence_en",
        ),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    dispositivo_id = Column(UUID(as_uuid=True), nullable=False)
    emitida_en = Column(DateTime(timezone=True), nullable=False)
    vence_en = Column(DateTime(timezone=True), nullable=False)
    hora_local_en = Column(DateTime(timezone=True), nullable=True)
    tolerancia_segundos = Column(Integer, nullable=False, default=300)
    politica_version = Column(Integer, nullable=False, default=1)
    desfase_segundos = Column(Integer, nullable=True)
    clave_idempotencia = Column(UUID(as_uuid=True), nullable=True)
    hash_solicitud = Column(String(64), nullable=True)


class OperacionSincronizacion(Base):
    __tablename__ = "operaciones_sincronizacion"
    __table_args__ = (
        CheckConstraint("version_esquema > 0", name="ck_operaciones_version"),
        CheckConstraint("secuencia_local > 0", name="ck_operaciones_secuencia"),
        CheckConstraint("revision > 0", name="ck_operaciones_revision"),
        CheckConstraint(
            "hash_solicitud ~ '^[0-9a-f]{64}$'", name="ck_operaciones_hash"
        ),
        CheckConstraint(
            "tipo IN ('SOLICITAR_RESERVA','SOLICITAR_COMPRA','REGISTRAR_VENTA_CAJA')",
            name="ck_operaciones_tipo",
        ),
        CheckConstraint(
            "estado IN ('ACEPTADA','RECHAZADA','REQUIERE_ACEPTACION_PRECIO',"
            "'PENDIENTE_PAGO','REGISTRADA_CENTRAL','CONCILIACION_REQUERIDA','CONFLICTO')",
            name="ck_operaciones_estado",
        ),
        CheckConstraint(
            "estado <> 'ACEPTADA' OR (aceptada_en IS NOT NULL AND recurso_id IS NOT NULL)",
            name="ck_operaciones_aceptacion",
        ),
        UniqueConstraint("empresa_id", "usuario_id", "operacion_id", name="uq_operaciones_actor_uuid"),
        UniqueConstraint("id", "empresa_id", name="uq_operaciones_id_empresa"),
        ForeignKeyConstraint(
            ["usuario_id", "empresa_id"],
            ["seguridad.usuarios.id", "seguridad.usuarios.empresa_id"],
            name="fk_operaciones_usuario_empresa",
        ),
        ForeignKeyConstraint(
            ["referencia_horaria_id", "empresa_id", "usuario_id", "dispositivo_id"],
            ["comercial.referencias_horarias.id", "comercial.referencias_horarias.empresa_id",
             "comercial.referencias_horarias.usuario_id", "comercial.referencias_horarias.dispositivo_id"],
            name="fk_operaciones_referencia",
        ),
        Index("ix_operaciones_actor_recibida", "empresa_id", "usuario_id", "recibida_en"),
        Index("ix_operaciones_recurso", "tipo", "recurso_id", postgresql_where="recurso_id IS NOT NULL"),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    operacion_id = Column(UUID(as_uuid=True), nullable=False)
    tipo = Column(String(40), nullable=False)
    version_esquema = Column(Integer, nullable=False)
    dispositivo_id = Column(UUID(as_uuid=True), nullable=False)
    secuencia_local = Column(BigInteger, nullable=False)
    creada_local_en = Column(DateTime(timezone=True), nullable=False)
    recibida_en = Column(DateTime(timezone=True), nullable=False)
    aceptada_en = Column(DateTime(timezone=True), nullable=True)
    referencia_horaria_id = Column(UUID(as_uuid=True), nullable=True)
    hash_solicitud = Column(String(64), nullable=False)
    solicitud = Column(JSONB, nullable=False)
    estado = Column(String(40), nullable=False)
    codigo = Column(String(40), nullable=False)
    detalle = Column(Text, nullable=False)
    resultado = Column(JSONB, nullable=False)
    recurso_id = Column(UUID(as_uuid=True), nullable=True)
    revision = Column(Integer, nullable=False, default=1)


class Traslado(Base):
    __tablename__ = "traslados"
    __table_args__ = (
        CheckConstraint(
            "sucursal_origen_id <> sucursal_destino_id",
            name="ck_traslados_origen_destino_distintos",
        ),
        UniqueConstraint("id", "empresa_id", name="uq_traslados_id_empresa"),
        {"schema": "inventario"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    reserva_id = Column(UUID(as_uuid=True), ForeignKey("comercial.reservas.id"), nullable=True)
    sucursal_origen_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    sucursal_destino_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    estado = Column(EstadoTraslado, nullable=False, default="SOLICITADO")
    solicitado_por_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    aprobado_por_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    fecha_solicitud = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    fecha_aprobacion = Column(DateTime(timezone=True), nullable=True)
    fecha_despacho = Column(DateTime(timezone=True), nullable=True)
    fecha_recepcion = Column(DateTime(timezone=True), nullable=True)
    motivo_rechazo = Column(Text, nullable=True)
    clave_idempotencia = Column(UUID(as_uuid=True), nullable=True, unique=True)
    hash_solicitud = Column(Text, nullable=True)

    detalles = relationship("DetalleTraslado", back_populates="traslado", cascade="all, delete-orphan")


class DetalleTraslado(Base):
    __tablename__ = "detalles_traslado"
    __table_args__ = (
        UniqueConstraint("traslado_id", "variante_id", name="uq_detalles_traslado_traslado_variante"),
        CheckConstraint("cantidad > 0", name="ck_detalle_traslado_cantidad_pos"),
        {"schema": "inventario"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    traslado_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inventario.traslados.id", ondelete="CASCADE"),
        nullable=False,
    )
    detalle_reserva_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comercial.detalles_reserva.id"),
        nullable=True,
    )
    variante_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)

    traslado = relationship("Traslado", back_populates="detalles")
