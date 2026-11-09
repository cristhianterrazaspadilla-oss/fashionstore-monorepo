"""Modelos de Dominio: Ventas, Pagos, Carrito y Entregas (CU11, CU13, CU14, CU15, CU16, CU23)."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Boolean,
    Numeric,
    SmallInteger,
    ForeignKey,
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


EstadoVenta = ENUM(
    "PENDIENTE_PAGO",
    "PAGADA",
    "CANCELADA",
    "PARCIALMENTE_DEVUELTA",
    "DEVUELTA",
    name="estado_venta",
    schema="comercial",
    create_type=False,
)


class Venta(Base):
    __tablename__ = "ventas"
    __table_args__ = (
        CheckConstraint(
            "canal IN ('PRESENCIAL','WEB','MOVIL')",
            name="ck_ventas_canal",
        ),
        CheckConstraint("subtotal >= 0", name="ck_ventas_subtotal_nneg"),
        CheckConstraint("descuento >= 0", name="ck_ventas_descuento_nneg"),
        CheckConstraint("costo_entrega >= 0", name="ck_ventas_costo_entrega_nneg"),
        CheckConstraint("total >= 0", name="ck_ventas_total_nneg"),
        CheckConstraint("adelanto_descontado >= 0", name="ck_ventas_adelanto_desc_nneg"),
        UniqueConstraint("id", "empresa_id", name="uq_ventas_id_empresa"),
        Index("uq_ventas_empresa_numero", "empresa_id", "numero", unique=True),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    numero = Column(String(50), nullable=False)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.clientes.usuario_id"), nullable=True)
    reserva_id = Column(UUID(as_uuid=True), ForeignKey("comercial.reservas.id"), nullable=True)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    cajero_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    canal = Column(String(20), nullable=False, default="PRESENCIAL")
    estado = Column(EstadoVenta, nullable=False, default="PAGADA")
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    descuento = Column(Numeric(12, 2), nullable=False, default=0)
    costo_entrega = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    confirmada_en = Column(DateTime(timezone=True), nullable=True)
    expira_en = Column(DateTime(timezone=True), nullable=True)
    adelanto_descontado = Column(Numeric(12, 2), nullable=False, default=0)
    clave_idempotencia = Column(UUID(as_uuid=True), nullable=True, unique=True)
    hash_solicitud = Column(Text, nullable=True)
    pedido_compra_id = Column(UUID(as_uuid=True), nullable=True)
    turno_caja_id = Column(UUID(as_uuid=True), ForeignKey("comercial.turnos_caja.id"), nullable=True)
    vendida_local_en = Column(DateTime(timezone=True), nullable=True)
    recibida_central_en = Column(DateTime(timezone=True), nullable=True)
    entregada_en = Column(DateTime(timezone=True), nullable=True)

    detalles = relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")


class DetalleVenta(Base):
    __tablename__ = "detalles_venta"
    __table_args__ = (
        UniqueConstraint("venta_id", "variante_id", name="uq_detalles_venta_venta_variante"),
        CheckConstraint("cantidad > 0", name="ck_detalle_venta_cantidad_pos"),
        CheckConstraint("precio_unitario >= 0", name="ck_detalle_venta_precio_nneg"),
        CheckConstraint("descuento >= 0", name="ck_detalle_venta_descuento_nneg"),
        CheckConstraint("costo_promedio >= 0", name="ck_detalle_venta_costo_nneg"),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    venta_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comercial.ventas.id", ondelete="CASCADE"),
        nullable=False,
    )
    detalle_reserva_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comercial.detalles_reserva.id"),
        nullable=True,
    )
    variante_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Numeric(12, 2), nullable=False)
    descuento = Column(Numeric(12, 2), nullable=False, default=0)
    promocion_id = Column(
        UUID(as_uuid=True),
        ForeignKey("catalogo.promociones.id"),
        nullable=True,
    )
    costo_promedio = Column(Numeric(12, 2), nullable=False, default=0)

    venta = relationship("Venta", back_populates="detalles")


class Pago(Base):
    __tablename__ = "pagos"
    __table_args__ = (
        CheckConstraint(
            "contexto IN ('RESERVA','VENTA')",
            name="ck_pagos_contexto",
        ),
        CheckConstraint(
            "(contexto = 'RESERVA' AND reserva_id IS NOT NULL) OR "
            "(contexto = 'VENTA' AND venta_id IS NOT NULL)",
            name="ck_pagos_contexto_referencia",
        ),
        CheckConstraint(
            "(contexto = 'RESERVA' AND reserva_id IS NOT NULL AND venta_id IS NULL) OR "
            "(contexto = 'VENTA' AND venta_id IS NOT NULL AND reserva_id IS NULL)",
            name="ck_pagos_un_solo_recurso",
        ),
        CheckConstraint(
            "metodo IN ('EFECTIVO','TARJETA_CAJA','QR_CAJA','TRANSFERENCIA','STRIPE_TEST')",
            name="ck_pagos_metodo",
        ),
        CheckConstraint("monto > 0", name="ck_pagos_monto_pos"),
        Index(
            "uq_pagos_empresa_prov_ref",
            "empresa_id", "proveedor_pago", "referencia_externa",
            unique=True,
            postgresql_where=text("referencia_externa IS NOT NULL"),
        ),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    contexto = Column(String(20), nullable=False)
    reserva_id = Column(UUID(as_uuid=True), ForeignKey("comercial.reservas.id"), nullable=True)
    venta_id = Column(UUID(as_uuid=True), ForeignKey("comercial.ventas.id"), nullable=True)
    metodo = Column(String(30), nullable=False)
    tipo_pago = Column(String(20), nullable=True)
    modalidad_adelanto = Column(String(20), nullable=True)
    monto = Column(Numeric(12, 2), nullable=False)
    no_reembolsable = Column(Boolean, nullable=False, default=False)
    estado = Column(String(20), nullable=False, default="PENDIENTE")
    referencia_externa = Column(String(160), nullable=True)
    proveedor_pago = Column(String(40), nullable=True)
    pagado_en = Column(DateTime(timezone=True), nullable=True)
    clave_idempotencia = Column(UUID(as_uuid=True), nullable=True, unique=True)
    hash_solicitud = Column(Text, nullable=True)
    efectivo_recibido_bob = Column(Numeric(14, 2), nullable=True)
    cambio_entregado_bob = Column(Numeric(14, 2), nullable=True)


class Carrito(Base):
    __tablename__ = "carritos"
    __table_args__ = (
        CheckConstraint(
            "canal IN ('WEB','MOVIL')",
            name="ck_carritos_canal",
        ),
        CheckConstraint(
            "estado IN ('ACTIVO','CONVERTIDO','ABANDONADO')",
            name="ck_carritos_estado",
        ),
        Index(
            "uq_carritos_activo_por_cliente_canal",
            "cliente_id", "canal",
            unique=True,
            postgresql_where="estado = 'ACTIVO'",
        ),
        Index("idx_carritos_cliente_estado", "cliente_id", "estado"),
        UniqueConstraint("id", "empresa_id", name="uq_carritos_id_empresa"),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    cliente_id = Column(
        UUID(as_uuid=True), ForeignKey("seguridad.clientes.usuario_id"), nullable=False
    )
    canal = Column(String(10), nullable=False, default="WEB")
    estado = Column(String(20), nullable=False, default="ACTIVO")
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    actualizada_en = Column(
        DateTime(timezone=True), default=_ahora_utc, onupdate=_ahora_utc, nullable=False
    )
    convertida_en = Column(DateTime(timezone=True), nullable=True)
    venta_id = Column(UUID(as_uuid=True), ForeignKey("comercial.ventas.id"), nullable=True)

    lineas = relationship(
        "DetalleCarrito", back_populates="carrito", cascade="all, delete-orphan"
    )


class DetalleCarrito(Base):
    __tablename__ = "detalles_carrito"
    __table_args__ = (
        UniqueConstraint("carrito_id", "variante_id", name="uq_detalle_carrito_carrito_variante"),
        CheckConstraint("cantidad > 0", name="ck_detalle_carrito_cantidad_pos"),
        Index("idx_detalle_carrito_carrito", "carrito_id"),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carrito_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comercial.carritos.id", ondelete="CASCADE"),
        nullable=False,
    )
    variante_id = Column(
        UUID(as_uuid=True),
        ForeignKey("catalogo.variantes_producto.id"),
        nullable=False,
    )
    cantidad = Column(Integer, nullable=False)
    agregado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    actualizado_en = Column(
        DateTime(timezone=True), default=_ahora_utc, onupdate=_ahora_utc, nullable=False
    )

    carrito = relationship("Carrito", back_populates="lineas")


class PedidoEntrega(Base):
    __tablename__ = "pedidos_entrega"
    __table_args__ = (
        CheckConstraint(
            "modalidad IN ('RECOJO','DELIVERY')",
            name="ck_pedidos_modalidad",
        ),
        CheckConstraint(
            "(modalidad = 'RECOJO') OR (direccion IS NOT NULL AND anillo_destino IS NOT NULL)",
            name="ck_pedidos_delivery_requiere_datos",
        ),
        CheckConstraint(
            "(modalidad = 'DELIVERY') OR (costo_entrega = 0)",
            name="ck_pedidos_recojo_sin_tarifa",
        ),
        CheckConstraint("costo_entrega >= 0", name="ck_pedidos_costo_nneg"),
        CheckConstraint("tarifa_base >= 0", name="ck_pedidos_tarifa_nneg"),
        CheckConstraint("incremento_anillo >= 0", name="ck_pedidos_incremento_nneg"),
        Index("idx_pedidos_sucursal_estado", "sucursal_id", "estado"),
        Index("idx_pedidos_venta", "venta_id"),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(
        UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True
    )
    venta_id = Column(
        UUID(as_uuid=True), ForeignKey("comercial.ventas.id", ondelete="CASCADE"),
        nullable=True, unique=True,
    )
    cambio_id = Column(UUID(as_uuid=True), ForeignKey("comercial.cambios.id"), nullable=True)
    sucursal_id = Column(
        UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False
    )
    cliente_id = Column(
        UUID(as_uuid=True), ForeignKey("seguridad.clientes.usuario_id"), nullable=False
    )
    modalidad = Column(String(20), nullable=False)
    estado = Column(String(20), nullable=False, default="SOLICITADO")
    anillo_sucursal = Column(SmallInteger, nullable=True)
    anillo_destino = Column(SmallInteger, nullable=True)
    anillo_minimo = Column(SmallInteger, nullable=True)
    anillo_maximo = Column(SmallInteger, nullable=True)
    direccion = Column(Text, nullable=True)
    tarifa_base = Column(Numeric(12, 2), nullable=False, default=0)
    incremento_anillo = Column(Numeric(12, 2), nullable=False, default=0)
    costo_entrega = Column(Numeric(12, 2), nullable=False, default=0)
    codigo_recojo = Column(String(20), nullable=True)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    actualizada_en = Column(
        DateTime(timezone=True), default=_ahora_utc, onupdate=_ahora_utc, nullable=False
    )


class RegistroIdempotencia(Base):
    __tablename__ = "registros_idempotencia"
    __table_args__ = (
        Index("idx_idempotencia_expira", "expira_en"),
        Index("idx_idempotencia_usuario_expira", "usuario_id", "expira_en"),
        {"schema": "comercial"},
    )

    clave = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    recurso_tipo = Column(String(40), primary_key=True, nullable=False)
    operacion = Column(String(80), primary_key=True, nullable=False)
    hash_solicitud = Column(Text, nullable=False)
    recurso_id = Column(UUID(as_uuid=True), nullable=True)
    respuesta = Column(JSONB, nullable=False, default=dict)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    expira_en = Column(DateTime(timezone=True), nullable=True)




class TurnoCaja(Base):
    __tablename__ = "turnos_caja"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_turnos_caja_id_empresa"),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    cajero_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    dispositivo_id = Column(UUID(as_uuid=True), nullable=False)
    caja_codigo = Column(String(80), nullable=False)
    estado = Column(String(20), nullable=False, default="ABIERTO")
    inicio_en = Column(DateTime(timezone=True), nullable=False)
    vence_en = Column(DateTime(timezone=True), nullable=False)
    version_precios = Column(String(80), nullable=False)
    cupos_hash = Column(String(64), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    cerrado_en = Column(DateTime(timezone=True), nullable=True)
    cerrado_por_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    motivo_supervision = Column(Text, nullable=True)
    supervision_forzada = Column(Boolean, nullable=False, default=False)
    arqueo_declarado_bob = Column(Numeric(14, 2), nullable=True)
    evidencia_cierre = Column(JSONB, nullable=True)
    ajustes_inventario = Column(JSONB, nullable=True)


class TurnoCajaEvento(Base):
    """Rastro append-only de cierres y decisiones de supervisiÃ³n de caja."""
    __tablename__ = "turnos_caja_eventos"
    __table_args__ = (
        UniqueConstraint("turno_id", "revision", name="uq_turnos_caja_eventos_turno_revision"),
        {"schema": "comercial"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turno_id = Column(UUID(as_uuid=True), ForeignKey("comercial.turnos_caja.id"), nullable=False, index=True)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    revision = Column(Integer, nullable=False)
    tipo = Column(String(40), nullable=False)
    datos = Column(JSONB, nullable=False, default=dict)
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)


__all__ = [
    "EstadoVenta",
    "Venta",
    "DetalleVenta",
    "Pago",
    "Carrito",
    "DetalleCarrito",
    "PedidoEntrega",
    "RegistroIdempotencia",
    "TurnoCaja",
    "TurnoCajaEvento",
]
