"""Modelos de Dominio: Inventario y Abastecimiento (CU04, CU07, CU17)"""
import uuid
from backend.app.core.reloj import utcnow
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Numeric,
    ForeignKey,
    DateTime,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class LoteRecepcion(Base):
    __tablename__ = "lotes_recepcion"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_lotes_recepcion_id_empresa"),
        {"schema": "inventario"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    proveedor_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.proveedores.id"), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    temporada_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.temporadas.id"), nullable=True)
    coleccion_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.colecciones.id"), nullable=True)
    recibido_por_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    numero_documento = Column(String(100), nullable=True)
    fecha_recepcion = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    observacion = Column(Text, nullable=True)

    detalles = relationship("DetalleLoteRecepcion", back_populates="lote", cascade="all, delete-orphan")


class DetalleLoteRecepcion(Base):
    __tablename__ = "detalles_lote_recepcion"
    __table_args__ = (
        UniqueConstraint("lote_id", "variante_id", name="uq_detalles_lote_variante"),
        {"schema": "inventario"}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lote_id = Column(UUID(as_uuid=True), ForeignKey("inventario.lotes_recepcion.id", ondelete="CASCADE"), nullable=False)
    variante_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    costo_unitario = Column(Numeric(12, 2), nullable=False)

    lote = relationship("LoteRecepcion", back_populates="detalles")


class InventarioSucursal(Base):
    __tablename__ = "inventario_sucursal"
    __table_args__ = (
        UniqueConstraint("variante_id", "sucursal_id", name="uq_inventario_variante_sucursal"),
        CheckConstraint("disponible >= 0", name="ck_inventario_disponible_nneg"),
        CheckConstraint("reservado >= 0", name="ck_inventario_reservado_nneg"),
        CheckConstraint("comprometido_traslado >= 0", name="ck_inventario_comprometido_nneg"),
        CheckConstraint("en_transito >= 0", name="ck_inventario_en_transito_nneg"),
        CheckConstraint("comprometido_caja >= 0", name="ck_inventario_comprometido_caja_nneg"),
        CheckConstraint("comprometido_digital >= 0", name="ck_inventario_comprometido_digital_nneg"),
        CheckConstraint("comprometido_cambio >= 0", name="ck_inventario_comprometido_cambio_nneg"),
        {"schema": "inventario"}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variante_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    disponible = Column(Integer, nullable=False, default=0)
    reservado = Column(Integer, nullable=False, default=0)
    comprometido_traslado = Column(Integer, nullable=False, default=0)
    en_transito = Column(Integer, nullable=False, default=0)
    comprometido_caja = Column(Integer, nullable=False, default=0)
    comprometido_digital = Column(Integer, nullable=False, default=0)
    comprometido_cambio = Column(Integer, nullable=False, default=0)
    actualizado_en = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class CupoCaja(Base):
    __tablename__ = "cupos_caja"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_cupos_caja_id_empresa"),
        UniqueConstraint("turno_id", "variante_id", name="uq_cupos_caja_turno_variante"),
        CheckConstraint("otorgado > 0", name="ck_cupos_caja_otorgado_pos"),
        CheckConstraint("consumido >= 0", name="ck_cupos_caja_consumido_nneg"),
        CheckConstraint("liberado >= 0", name="ck_cupos_caja_liberado_nneg"),
        CheckConstraint("mermado >= 0", name="ck_cupos_caja_mermado_nneg"),
        CheckConstraint("precio_autorizado_bob >= 0", name="ck_cupos_caja_precio_nneg"),
        CheckConstraint("costo_unitario_snapshot >= 0", name="ck_cupos_caja_costo_snapshot_nneg"),
        {"schema": "inventario"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    turno_id = Column(UUID(as_uuid=True), ForeignKey("comercial.turnos_caja.id"), nullable=False)
    variante_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    otorgado = Column(Integer, nullable=False)
    consumido = Column(Integer, nullable=False, default=0)
    liberado = Column(Integer, nullable=False, default=0)
    mermado = Column(Integer, nullable=False, default=0)
    costo_unitario_snapshot = Column(Numeric(12, 2), nullable=False, default=0)
    precio_autorizado_bob = Column(Numeric(14, 2), nullable=False)
    version_precios = Column(String(80), nullable=False)
    creado_en = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"
    __table_args__ = (
        UniqueConstraint("clave_idempotencia", name="uq_movimientos_clave_idempotencia"),
        CheckConstraint(
            "tipo IN ('RECEPCION_PROVEEDOR','RESERVA','LIBERACION_RESERVA',"
            "'COMPROMISO_TRASLADO','DESPACHO_TRASLADO','RECEPCION_TRASLADO',"
            "'VENTA_PRESENCIAL','VENTA_DIGITAL','DEVOLUCION','MERMA','AJUSTE',"
            "'COMPROMISO_DIGITAL','LIBERACION_DIGITAL','COMPROMISO_CAJA',"
            "'LIBERACION_CUPO_CAJA')",
            name="movimientos_inventario_tipo_check",
        ),
        Index(
            "uq_movimientos_efecto_logico",
            "referencia_tipo", "referencia_id", "tipo", "variante_id",
            "sucursal_origen_id", "sucursal_destino_id", "linea_referencia_id",
            unique=True,
            postgresql_where=(
                "referencia_tipo IS NOT NULL AND referencia_id IS NOT NULL"
            ),
        ),
        {"schema": "inventario"}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variante_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=False)
    sucursal_origen_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=True)
    sucursal_destino_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=True)
    responsable_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    tipo = Column(String(40), nullable=False)
    cantidad = Column(Integer, nullable=False)
    costo_unitario = Column(Numeric(12, 2), nullable=False, default=0)
    referencia_tipo = Column(String(40), nullable=True)
    referencia_id = Column(UUID(as_uuid=True), nullable=True)
    linea_referencia_id = Column(UUID(as_uuid=True), nullable=True)
    clave_idempotencia = Column(UUID(as_uuid=True), nullable=True)
    fecha_hora = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    observacion = Column(Text, nullable=True)
