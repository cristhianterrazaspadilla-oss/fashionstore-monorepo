"""Servicio y Modelos de Dominio: Carrito y Pedido de Compra Durable — CU21.

Implementa:
- Gestión de carrito sin comprometer stock (GET, POST, PATCH, DELETE líneas).
- Checkout durable con oferta versionada y estados independientes de pago y cumplimiento (A-PAGO-01).
- Mapeo de tablas comercial.pedidos_compra, comercial.detalles_pedido, comercial.ofertas_compra, comercial.comprobantes.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship, selectinload

from backend.app.core.database import Base
from backend.app.core.idempotencia_ciclo3 import (
    guardar_respuesta,
    hash_payload,
    reclamar,
)
from backend.app.core.modules.catalogo.models import VarianteProducto
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.inventario.models import MovimientoInventario
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.ventas_pagos.models import Carrito, DetalleCarrito
from backend.app.core.reloj import RelojSistema


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# MODELOS SQLALCHEMY (Tablas existentes en esquema 0009 / 0013)
# ============================================================================

class PedidoCompra(Base):
    __tablename__ = "pedidos_compra"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_pedidos_compra_id_empresa"),
        UniqueConstraint("empresa_id", "operacion_id", name="uq_pedidos_compra_empresa_operacion"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    operacion_id = Column(UUID(as_uuid=True), nullable=True)
    metodo_preparado_id = Column(UUID(as_uuid=True), nullable=True)
    estado = Column(String(36), nullable=False, default="BORRADOR")
    estado_pago = Column(String(36), nullable=False, default="SIN_PAGO")
    estado_cumplimiento = Column(String(36), nullable=False, default="SIN_ASIGNACION")
    modalidad = Column(String(12), nullable=False)
    direccion = Column(Text, nullable=True)
    subtotal_bob = Column(Numeric(14, 2), nullable=False, default=0)
    descuento_bob = Column(Numeric(14, 2), nullable=False, default=0)
    envio_bob = Column(Numeric(14, 2), nullable=False, default=0)
    total_bob = Column(Numeric(14, 2), nullable=False, default=0)
    consentimiento_hash = Column(String(64), nullable=True)
    condiciones_version = Column(String(80), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    actualizado_en = Column(DateTime(timezone=True), default=_ahora_utc, onupdate=_ahora_utc, nullable=False)

    detalles = relationship("DetallePedido", back_populates="pedido", cascade="all, delete-orphan")
    ofertas = relationship("OfertaCompra", back_populates="pedido", cascade="all, delete-orphan")


class DetallePedido(Base):
    __tablename__ = "detalles_pedido"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_detalles_pedido_id_empresa"),
        UniqueConstraint("pedido_id", "variante_id", name="uq_detalles_pedido_pedido_variante"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    pedido_id = Column(UUID(as_uuid=True), ForeignKey("comercial.pedidos_compra.id"), nullable=False)
    variante_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario_bob = Column(Numeric(14, 2), nullable=False)
    descuento_bob = Column(Numeric(14, 2), nullable=False, default=0)
    total_bob = Column(Numeric(14, 2), nullable=False)
    oferta_revision = Column(Integer, nullable=True)

    pedido = relationship("PedidoCompra", back_populates="detalles")


class OfertaCompra(Base):
    __tablename__ = "ofertas_compra"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_ofertas_compra_id_empresa"),
        UniqueConstraint("pedido_id", "revision", name="uq_ofertas_compra_pedido_revision"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    pedido_id = Column(UUID(as_uuid=True), ForeignKey("comercial.pedidos_compra.id"), nullable=False)
    revision = Column(Integer, nullable=False)
    documento = Column(JSONB, nullable=False)
    documento_hash = Column(String(64), nullable=False)
    subtotal_bob = Column(Numeric(14, 2), nullable=False)
    descuento_bob = Column(Numeric(14, 2), nullable=False, default=0)
    envio_bob = Column(Numeric(14, 2), nullable=False, default=0)
    total_bob = Column(Numeric(14, 2), nullable=False)
    tasa_id = Column(UUID(as_uuid=True), nullable=True)
    total_usd = Column(Numeric(14, 2), nullable=True)
    vigente_hasta = Column(DateTime(timezone=True), nullable=False)
    aceptada_en = Column(DateTime(timezone=True), nullable=True)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)

    pedido = relationship("PedidoCompra", back_populates="ofertas")


class Comprobante(Base):
    __tablename__ = "comprobantes"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_comprobantes_id_empresa"),
        UniqueConstraint("empresa_id", "recurso_tipo", "recurso_id", "tipo", "version", name="uq_comprobantes_recurso_version"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    tipo = Column(String(40), nullable=False)
    recurso_tipo = Column(String(40), nullable=False)
    recurso_id = Column(UUID(as_uuid=True), nullable=False)
    version = Column(Integer, nullable=False)
    documento = Column(JSONB, nullable=False)
    documento_hash = Column(String(64), nullable=False)
    uri_archivo = Column(Text, nullable=True)
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)


class ObligacionReembolso(Base):
    __tablename__ = "obligaciones_reembolso"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_obligaciones_reembolso_id_empresa"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    cliente_id = Column(UUID(as_uuid=True), nullable=False)
    origen_tipo = Column(String(40), nullable=False)
    origen_id = Column(UUID(as_uuid=True), nullable=False)
    motivo_codigo = Column(String(60), nullable=False)
    estado = Column(String(36), nullable=False, default="PENDIENTE_AUTORIZACION")
    monto_bob = Column(Numeric(14, 2), nullable=False)
    politica_id = Column(UUID(as_uuid=True), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    creada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    autorizada_en = Column(DateTime(timezone=True), nullable=True)
    completada_en = Column(DateTime(timezone=True), nullable=True)



# ============================================================================
# DTOs PYDANTIC
# ============================================================================

class LineaCarritoItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    variante_id: uuid.UUID
    cantidad: int
    precio_unitario_bob: Decimal = Field(default=Decimal("0.00"))
    subtotal_bob: Decimal = Field(default=Decimal("0.00"))
    producto_nombre: Optional[str] = None
    talla: Optional[str] = None
    color: Optional[str] = None


class CarritoDurableDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    cliente_id: uuid.UUID
    canal: str
    estado: str
    total_estimado_bob: Decimal
    lineas: List[LineaCarritoItemDTO]


class LineaCarritoCrearDTO(BaseModel):
    variante_id: uuid.UUID
    cantidad: int = Field(gt=0, description="Cantidad mayor a cero")


class LineaCarritoModificarDTO(BaseModel):
    cantidad: int = Field(gt=0, description="Nueva cantidad mayor a cero")


class CheckoutCarritoDTO(BaseModel):
    sucursal_id: uuid.UUID
    modalidad: str = Field(pattern="^(RECOJO|DELIVERY)$")
    direccion: Optional[str] = None
    anillo_destino: Optional[int] = None
    saldo_solicitado: Optional[Decimal] = None
    autorizacion_cobro: Optional[Dict[str, Any]] = None


class DetallePedidoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    variante_id: uuid.UUID
    cantidad: int
    precio_unitario_bob: Decimal
    descuento_bob: Decimal
    total_bob: Decimal


class PedidoCompraDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pedido_id: uuid.UUID
    empresa_id: uuid.UUID
    cliente_id: uuid.UUID
    sucursal_id: uuid.UUID
    modalidad: str
    direccion: Optional[str] = None
    subtotal_bob: Decimal
    descuento_bob: Decimal
    envio_bob: Decimal
    total_bob: Decimal
    oferta_revision: int
    estado: str
    estado_pago: str
    estado_cumplimiento: str
    vigente_hasta: Optional[datetime] = None
    lineas: List[DetallePedidoDTO]


# ============================================================================
# SERVICIO PEDIDO / CARRITO DURABLE
# ============================================================================

class PedidoService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.inventario_repo = InventarioRepository(db)

    async def obtener_o_crear_carrito(self, usuario: Usuario, canal: str = "WEB") -> Carrito:
        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")
        stmt = (
            select(Carrito)
            .where(
                Carrito.empresa_id == usuario.empresa_id,
                Carrito.cliente_id == usuario.id,
                Carrito.canal == canal,
                Carrito.estado == "ACTIVO",
            )
        )
        res = await self.db.execute(stmt)
        carrito = res.scalars().first()
        if carrito is None:
            carrito = Carrito(
                id=uuid.uuid4(),
                empresa_id=usuario.empresa_id,
                cliente_id=usuario.id,
                canal=canal,
                estado="ACTIVO",
                creada_en=self.reloj.ahora(),
                actualizada_en=self.reloj.ahora(),
            )
            self.db.add(carrito)
            await self.db.flush()
        return carrito

    async def consultar_carrito(self, usuario: Usuario, canal: str = "WEB") -> CarritoDurableDTO:
        carrito = await self.obtener_o_crear_carrito(usuario, canal)
        return await self._a_carrito_dto(carrito)

    async def _a_carrito_dto(self, carrito: Carrito) -> CarritoDurableDTO:
        stmt_lineas = (
            select(DetalleCarrito)
            .where(DetalleCarrito.carrito_id == carrito.id)
            .order_by(DetalleCarrito.agregado_en)
        )
        res_lineas = await self.db.execute(stmt_lineas)
        lineas_db = res_lineas.scalars().all()

        lineas_dto: List[LineaCarritoItemDTO] = []
        total_estimado = Decimal("0.00")

        for l in lineas_db:
            stmt_v = (
                select(VarianteProducto)
                .options(
                    selectinload(VarianteProducto.producto),
                    selectinload(VarianteProducto.talla),
                    selectinload(VarianteProducto.color),
                )
                .where(VarianteProducto.id == l.variante_id, VarianteProducto.empresa_id == carrito.empresa_id)
            )
            var = (await self.db.execute(stmt_v)).scalars().first()
            if var is None or var.precio is None:
                raise HTTPException(status_code=409, detail="PRECIO_NO_DISPONIBLE: no se pudo recuperar el precio autorizado de una prenda del carrito")
            try:
                precio = Decimal(str(var.precio))
            except (InvalidOperation, ValueError, TypeError):
                raise HTTPException(status_code=409, detail="PRECIO_NO_DISPONIBLE: precio de catálogo inválido")
            if not precio.is_finite() or precio < 0 or l.cantidad <= 0:
                raise HTTPException(status_code=409, detail="PRECIO_NO_DISPONIBLE: precio o cantidad inválidos")
            subtotal = precio * l.cantidad
            total_estimado += subtotal

            p_nombre = var.producto.nombre if var and var.producto else None
            talla_nombre = var.talla.nombre if var and var.talla else None
            color_nombre = var.color.nombre if var and var.color else None

            lineas_dto.append(
                LineaCarritoItemDTO(
                    id=l.id,
                    variante_id=l.variante_id,
                    cantidad=l.cantidad,
                    precio_unitario_bob=precio,
                    subtotal_bob=subtotal,
                    producto_nombre=p_nombre,
                    talla=talla_nombre,
                    color=color_nombre,
                )
            )

        return CarritoDurableDTO(
            id=carrito.id,
            cliente_id=carrito.cliente_id,
            canal=carrito.canal,
            estado=carrito.estado,
            total_estimado_bob=total_estimado,
            lineas=lineas_dto,
        )

    async def _reclamar_mutacion_carrito(
        self, usuario: Usuario, clave: Optional[uuid.UUID], operacion: str, payload: dict
    ) -> Optional[CarritoDurableDTO]:
        if clave is None:
            return None
        previo = await reclamar(
            self.db,
            clave=clave,
            hash_solicitud=hash_payload(payload),
            recurso_tipo="CARRITO",
            operacion=operacion,
            usuario_id=usuario.id,
        )
        if previo is None:
            return None
        if previo.respuesta:
            return CarritoDurableDTO.model_validate(previo.respuesta)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La operación con esta Idempotency-Key sigue en proceso",
        )

    async def _confirmar_mutacion_carrito(
        self, usuario: Usuario, carrito: Carrito, clave: Optional[uuid.UUID], operacion: str
    ) -> CarritoDurableDTO:
        await self.db.flush()
        salida = await self._a_carrito_dto(carrito)
        if clave is not None:
            await guardar_respuesta(
                self.db,
                clave,
                salida.model_dump(mode="json"),
                recurso_id=carrito.id,
                usuario_id=usuario.id,
                recurso_tipo="CARRITO",
                operacion=operacion,
            )
        await self.db.commit()
        return salida

    async def agregar_linea(
        self, usuario: Usuario, dto: LineaCarritoCrearDTO, canal: str, clave: Optional[uuid.UUID]
    ) -> CarritoDurableDTO:
        operacion = "AGREGAR_LINEA_CU21"
        previo = await self._reclamar_mutacion_carrito(
            usuario, clave, operacion,
            {"canal": canal, **dto.model_dump(mode="json")},
        )
        if previo is not None:
            return previo
        if dto.cantidad <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cantidad debe ser mayor a cero")

        var = await self.db.get(VarianteProducto, dto.variante_id)
        if var is None or var.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variante no encontrada en la empresa")

        carrito = await self.obtener_o_crear_carrito(usuario, canal)

        stmt_det = select(DetalleCarrito).where(
            DetalleCarrito.carrito_id == carrito.id,
            DetalleCarrito.variante_id == dto.variante_id,
        )
        det = (await self.db.execute(stmt_det)).scalars().first()

        if det is not None:
            det.cantidad += dto.cantidad
            det.actualizado_en = self.reloj.ahora()
        else:
            det = DetalleCarrito(
                id=uuid.uuid4(),
                carrito_id=carrito.id,
                variante_id=dto.variante_id,
                cantidad=dto.cantidad,
                agregado_en=self.reloj.ahora(),
                actualizado_en=self.reloj.ahora(),
            )
            self.db.add(det)

        carrito.actualizada_en = self.reloj.ahora()
        return await self._confirmar_mutacion_carrito(usuario, carrito, clave, operacion)

    async def modificar_linea(
        self, usuario: Usuario, linea_id: uuid.UUID, dto: LineaCarritoModificarDTO, canal: str, clave: Optional[uuid.UUID]
    ) -> CarritoDurableDTO:
        operacion = "MODIFICAR_LINEA_CU21"
        previo = await self._reclamar_mutacion_carrito(
            usuario, clave, operacion,
            {"canal": canal, "linea_id": str(linea_id), **dto.model_dump(mode="json")},
        )
        if previo is not None:
            return previo
        if dto.cantidad <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cantidad debe ser mayor a cero")

        carrito = await self.obtener_o_crear_carrito(usuario, canal)

        # Puede buscarse por detalle_carrito.id o por variante_id
        stmt = select(DetalleCarrito).where(
            DetalleCarrito.carrito_id == carrito.id,
            (DetalleCarrito.id == linea_id) | (DetalleCarrito.variante_id == linea_id),
        )
        det = (await self.db.execute(stmt)).scalars().first()
        if det is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada en el carrito")

        det.cantidad = dto.cantidad
        det.actualizado_en = self.reloj.ahora()
        carrito.actualizada_en = self.reloj.ahora()
        return await self._confirmar_mutacion_carrito(usuario, carrito, clave, operacion)

    async def quitar_linea(
        self, usuario: Usuario, linea_id: uuid.UUID, canal: str, clave: Optional[uuid.UUID]
    ) -> CarritoDurableDTO:
        operacion = "QUITAR_LINEA_CU21"
        previo = await self._reclamar_mutacion_carrito(
            usuario, clave, operacion,
            {"canal": canal, "linea_id": str(linea_id)},
        )
        if previo is not None:
            return previo
        carrito = await self.obtener_o_crear_carrito(usuario, canal)
        stmt = select(DetalleCarrito).where(
            DetalleCarrito.carrito_id == carrito.id,
            (DetalleCarrito.id == linea_id) | (DetalleCarrito.variante_id == linea_id),
        )
        det = (await self.db.execute(stmt)).scalars().first()
        if det is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada en el carrito")

        await self.db.delete(det)
        carrito.actualizada_en = self.reloj.ahora()
        return await self._confirmar_mutacion_carrito(usuario, carrito, clave, operacion)

    async def checkout(
        self, usuario: Usuario, dto: CheckoutCarritoDTO, canal: str, clave: uuid.UUID
    ) -> PedidoCompraDTO:
        digest = hash_payload({**dto.model_dump(mode="json"), "canal": canal})

        # Reclamar la clave antes de crear el pedido. El marcador y el pedido
        # se confirman en la misma transacciÃ³n; ante una peticiÃ³n concurrente,
        # reclamar() espera el resultado ganador y evita el INSERT duplicado.
        previo = await reclamar(
            self.db,
            clave=clave,
            hash_solicitud=digest,
            recurso_tipo="PEDIDO_COMPRA",
            operacion="CHECKOUT_CARRO",
            usuario_id=usuario.id,
        )
        if previo is not None:
            if previo.respuesta:
                return PedidoCompraDTO.model_validate(previo.respuesta)
            if previo.recurso_id is not None:
                return await self.obtener_pedido(usuario, previo.recurso_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El checkout con esta Idempotency-Key sigue en proceso",
            )

        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")

        if dto.modalidad == "DELIVERY" and not (dto.direccion and dto.direccion.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La modalidad DELIVERY requiere dirección de entrega",
            )

        # Validar sucursal
        sucursal = await self.db.get(Sucursal, dto.sucursal_id)
        if sucursal is None or sucursal.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada en la empresa")
        if not sucursal.activa:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sucursal inactiva")

        # Carrito
        carrito = await self.obtener_o_crear_carrito(usuario, canal)
        # Serializa checkouts distintos sobre el mismo carrito. populate_existing
        # actualiza su estado tras esperar el bloqueo de una transacciÃ³n anterior.
        stmt_carrito = (
            select(Carrito)
            .where(Carrito.id == carrito.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        carrito_bloqueado = (await self.db.execute(stmt_carrito)).scalars().first()
        if carrito_bloqueado is None or carrito_bloqueado.estado != "ACTIVO":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El carrito ya fue convertido en un pedido",
            )
        carrito = carrito_bloqueado
        stmt_lineas = select(DetalleCarrito).where(DetalleCarrito.carrito_id == carrito.id)
        lineas = (await self.db.execute(stmt_lineas)).scalars().all()
        if not lineas:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El carrito está vacío")

        ahora = self.reloj.ahora()
        subtotal = Decimal("0.00")
        items_pedido = []

        for l in lineas:
            var = await self.db.get(VarianteProducto, l.variante_id)
            if var is None or var.empresa_id != usuario.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variante {l.variante_id} no válida")
            precio = Decimal(str(var.precio or 0))
            tot_linea = precio * l.cantidad
            subtotal += tot_linea
            items_pedido.append((var, l.cantidad, precio, tot_linea))

        descuento = Decimal("0.00")
        envio = Decimal("15.00") if dto.modalidad == "DELIVERY" else Decimal("0.00")
        total = subtotal - descuento + envio

        pedido_id = uuid.uuid4()
        pedido = PedidoCompra(
            id=pedido_id,
            empresa_id=usuario.empresa_id,
            cliente_id=usuario.id,
            sucursal_id=dto.sucursal_id,
            modalidad=dto.modalidad,
            direccion=dto.direccion if dto.modalidad == "DELIVERY" else None,
            subtotal_bob=subtotal,
            descuento_bob=descuento,
            envio_bob=envio,
            total_bob=total,
            estado="BORRADOR",
            estado_pago="SIN_PAGO",
            estado_cumplimiento="SIN_ASIGNACION",
            revision=1,
            creado_en=ahora,
            actualizado_en=ahora,
        )
        self.db.add(pedido)

        detalles_dto: List[DetallePedidoDTO] = []
        doc_lineas = []
        for var, cant, precio, tot in items_pedido:
            det = DetallePedido(
                id=uuid.uuid4(),
                empresa_id=usuario.empresa_id,
                pedido_id=pedido_id,
                variante_id=var.id,
                cantidad=cant,
                precio_unitario_bob=precio,
                descuento_bob=Decimal("0.00"),
                total_bob=tot,
                oferta_revision=1,
            )
            self.db.add(det)
            detalles_dto.append(
                DetallePedidoDTO(
                    id=det.id,
                    variante_id=var.id,
                    cantidad=cant,
                    precio_unitario_bob=precio,
                    descuento_bob=Decimal("0.00"),
                    total_bob=tot,
                )
            )
            doc_lineas.append(
                {
                    "variante_id": str(var.id),
                    "cantidad": cant,
                    "precio_unitario_bob": str(precio),
                    "total_bob": str(tot),
                }
            )

        # Oferta versionada 1
        doc_oferta = {
            "pedido_id": str(pedido_id),
            "revision": 1,
            "lineas": doc_lineas,
            "subtotal_bob": str(subtotal),
            "descuento_bob": str(descuento),
            "envio_bob": str(envio),
            "total_bob": str(total),
        }
        doc_hash = hashlib.sha256(json.dumps(doc_oferta, sort_keys=True).encode("utf-8")).hexdigest()
        vigente_hasta = ahora + timedelta(minutes=30)

        oferta = OfertaCompra(
            id=uuid.uuid4(),
            empresa_id=usuario.empresa_id,
            pedido_id=pedido_id,
            revision=1,
            documento=doc_oferta,
            documento_hash=doc_hash,
            subtotal_bob=subtotal,
            descuento_bob=descuento,
            envio_bob=envio,
            total_bob=total,
            vigente_hasta=vigente_hasta,
            creada_en=ahora,
        )
        self.db.add(oferta)

        # Vaciar carrito activo y marcarlo convertido
        for l in lineas:
            await self.db.delete(l)
        carrito.estado = "CONVERTIDO"
        carrito.actualizada_en = ahora

        salida_dto = PedidoCompraDTO(
            pedido_id=pedido.id,
            empresa_id=pedido.empresa_id,
            cliente_id=pedido.cliente_id,
            sucursal_id=pedido.sucursal_id,
            modalidad=pedido.modalidad,
            direccion=pedido.direccion,
            subtotal_bob=pedido.subtotal_bob,
            descuento_bob=pedido.descuento_bob,
            envio_bob=pedido.envio_bob,
            total_bob=pedido.total_bob,
            oferta_revision=1,
            estado=pedido.estado,
            estado_pago=pedido.estado_pago,
            estado_cumplimiento=pedido.estado_cumplimiento,
            vigente_hasta=vigente_hasta,
            lineas=detalles_dto,
        )

        await guardar_respuesta(
            self.db,
            clave,
            salida_dto.model_dump(mode="json"),
            recurso_id=pedido.id,
            usuario_id=usuario.id,
            recurso_tipo="PEDIDO_COMPRA",
            operacion="CHECKOUT_CARRO",
        )

        await self.db.commit()
        return salida_dto

    async def obtener_pedido(self, usuario: Usuario, pedido_id: uuid.UUID) -> PedidoCompraDTO:
        pedido = await self.db.get(PedidoCompra, pedido_id)
        if pedido is None or pedido.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")

        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE" and pedido.cliente_id != usuario.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pedido ajeno al cliente")

        stmt_det = select(DetallePedido).where(DetallePedido.pedido_id == pedido.id)
        detalles = (await self.db.execute(stmt_det)).scalars().all()

        stmt_of = (
            select(OfertaCompra)
            .where(OfertaCompra.pedido_id == pedido.id)
            .order_by(OfertaCompra.revision.desc())
        )
        ultima_oferta = (await self.db.execute(stmt_of)).scalars().first()

        return PedidoCompraDTO(
            pedido_id=pedido.id,
            empresa_id=pedido.empresa_id,
            cliente_id=pedido.cliente_id,
            sucursal_id=pedido.sucursal_id,
            modalidad=pedido.modalidad,
            direccion=pedido.direccion,
            subtotal_bob=pedido.subtotal_bob,
            descuento_bob=pedido.descuento_bob,
            envio_bob=pedido.envio_bob,
            total_bob=pedido.total_bob,
            oferta_revision=pedido.revision,
            estado=pedido.estado,
            estado_pago=pedido.estado_pago,
            estado_cumplimiento=pedido.estado_cumplimiento,
            vigente_hasta=ultima_oferta.vigente_hasta if ultima_oferta else None,
            lineas=[
                DetallePedidoDTO(
                    id=d.id,
                    variante_id=d.variante_id,
                    cantidad=d.cantidad,
                    precio_unitario_bob=d.precio_unitario_bob,
                    descuento_bob=d.descuento_bob,
                    total_bob=d.total_bob,
                )
                for d in detalles
            ],
        )

    async def aceptar_oferta(
        self, usuario: Usuario, pedido_id: uuid.UUID, clave: Optional[uuid.UUID] = None
    ) -> PedidoCompraDTO:
        pedido = await self.db.get(PedidoCompra, pedido_id)
        if pedido is None or pedido.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
        if pedido.cliente_id != usuario.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el cliente puede aceptar la oferta")

        stmt_of = (
            select(OfertaCompra)
            .where(OfertaCompra.pedido_id == pedido.id, OfertaCompra.revision == pedido.revision)
        )
        oferta = (await self.db.execute(stmt_of)).scalars().first()
        if oferta is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Oferta vigente no encontrada")

        ahora = self.reloj.ahora()
        if oferta.vigente_hasta < ahora:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La oferta ha expirado")

        oferta.aceptada_en = ahora
        pedido.estado = "CONFIRMADO"
        pedido.actualizado_en = ahora
        await self.db.commit()
        return await self.obtener_pedido(usuario, pedido_id)

    async def confirmar_captura_pedido(self, pedido_id: uuid.UUID) -> PedidoCompra:
        """Confirma la captura de pago de un pedido y realiza la asignación completa y atómica de stock libre.

        Si no hay stock disponible, el pedido queda NO_CUMPLIBLE y se crea UNA obligación CU27
        por el dinero capturado, sin saldo negativo.
        Es estrictamente idempotente: llamadas repetidas (ej. webhook duplicado o reintento) no
        duplican cargo, asignación ni reembolso.
        """
        stmt = select(PedidoCompra).where(PedidoCompra.id == pedido_id).with_for_update()
        r = await self.db.execute(stmt)
        pedido = r.scalars().first()
        if pedido is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")

        # Idempotencia: si ya fue procesado como PAGADO, no duplicar asignación ni reembolso
        if pedido.estado_pago == "PAGADO":
            return pedido

        ahora = self.reloj.ahora()
        pedido.estado_pago = "PAGADO"
        pedido.actualizado_en = ahora

        # Obtener líneas del pedido
        stmt_det = (
            select(DetallePedido)
            .where(DetallePedido.pedido_id == pedido.id)
            .order_by(DetallePedido.variante_id)
        )
        lineas = (await self.db.execute(stmt_det)).scalars().all()

        # Bloqueo atómico de inventario en sucursal
        claves_ordenadas = sorted([(pedido.sucursal_id, det.variante_id) for det in lineas], key=lambda x: str(x[1]))
        filas = await self.inventario_repo.bloquearFilas(claves_ordenadas)

        hay_stock = True
        for det in lineas:
            fila = filas.get((pedido.sucursal_id, det.variante_id))
            if fila is None or fila.disponible < det.cantidad:
                hay_stock = False
                break

        if hay_stock:
            for det in lineas:
                fila = filas[(pedido.sucursal_id, det.variante_id)]
                fila.disponible -= det.cantidad
                fila.reservado += det.cantidad

                var = await self.db.get(VarianteProducto, det.variante_id)
                costo = Decimal(str(var.costo_promedio or 0)) if var else Decimal("0.00")
                mov = MovimientoInventario(
                    id=uuid.uuid4(),
                    variante_id=det.variante_id,
                    sucursal_origen_id=pedido.sucursal_id,
                    sucursal_destino_id=pedido.sucursal_id,
                    responsable_id=pedido.cliente_id,
                    tipo="COMPROMISO_DIGITAL",
                    cantidad=det.cantidad,
                    costo_unitario=costo,
                    referencia_tipo="PEDIDO",
                    referencia_id=pedido.id,
                    observacion=f"Compromiso digital pedido {pedido.id}",
                    fecha_hora=ahora,
                )
                self.db.add(mov)

            pedido.estado = "CONFIRMADO"
            pedido.estado_cumplimiento = "COMPROMETIDO"
            from backend.app.core.modules.identidad_empresas.services.notificacion_service import NotificacionService
            notif_svc = NotificacionService(self.db)
            await notif_svc.emitir_notificacion(
                empresa_id=pedido.empresa_id,
                usuario_id=pedido.cliente_id,
                tipo="COMPRA_EXITOSA",
                titulo="Compra exitosa confirmada",
                cuerpo=f"Tu compra por {pedido.total_bob} BOB ha sido confirmada y tus prendas estan reservadas.",
                recurso_tipo="PEDIDO",
                recurso_id=pedido.id,
                payload={
                    "pedido_id": str(pedido.id),
                    "total_bob": str(pedido.total_bob),
                    "estado": "CONFIRMADO",
                },
            )
        else:
            pedido.estado = "NO_CUMPLIBLE"
            pedido.estado_cumplimiento = "NO_CUMPLIBLE"

            # Verificar si ya existe obligación de reembolso (idempotencia estricta)
            stmt_reemb = select(ObligacionReembolso).where(
                ObligacionReembolso.origen_tipo == "PEDIDO",
                ObligacionReembolso.origen_id == pedido.id,
            )
            reemb_prev = (await self.db.execute(stmt_reemb)).scalars().first()
            if reemb_prev is None:
                reembolso = ObligacionReembolso(
                    id=uuid.uuid4(),
                    empresa_id=pedido.empresa_id,
                    cliente_id=pedido.cliente_id,
                    origen_tipo="PEDIDO",
                    origen_id=pedido.id,
                    motivo_codigo="SIN_STOCK",
                    estado="PENDIENTE_AUTORIZACION",
                    monto_bob=pedido.total_bob,
                    revision=1,
                    creada_en=ahora,
                )
                self.db.add(reembolso)

            from backend.app.core.modules.identidad_empresas.services.notificacion_service import NotificacionService
            notif_svc = NotificacionService(self.db)
            await notif_svc.emitir_notificacion(
                empresa_id=pedido.empresa_id,
                usuario_id=pedido.cliente_id,
                tipo="COMPRA_NO_CUMPLIBLE",
                titulo="Stock insuficiente tras cobro",
                cuerpo=f"Tu pedido #{pedido.id} no pudo asignarse por falta de stock. Se inicio un reembolso integro (CU27).",
                recurso_tipo="PEDIDO",
                recurso_id=pedido.id,
                payload={
                    "pedido_id": str(pedido.id),
                    "total_bob": str(pedido.total_bob),
                    "reembolso_id": str(reembolso.id) if 'reembolso' in locals() and reembolso else None,
                    "estado": "NO_CUMPLIBLE",
                },
            )

        # Actualizar resultado consultable en la operación de sincronización si proviene de CU05
        if pedido.operacion_id:
            from backend.app.core.modules.reservas_traslados.models import OperacionSincronizacion
            stmt_op = select(OperacionSincronizacion).where(
                OperacionSincronizacion.operacion_id == pedido.operacion_id,
                OperacionSincronizacion.empresa_id == pedido.empresa_id,
            )
            op = (await self.db.execute(stmt_op)).scalars().first()
            if op is not None:
                if hay_stock:
                    op.estado = "ACEPTADA"
                    op.codigo = "OK"
                    op.detalle = "Compra offline sincronizada y stock asignado exitosamente"
                else:
                    op.estado = "ACEPTADA"
                    op.codigo = "SIN_STOCK"
                    op.detalle = "Pedido cobrado pero sin stock disponible; derivado a reembolso íntegro CU27"
                op.recurso_id = pedido.id
                if op.aceptada_en is None:
                    op.aceptada_en = self.reloj.ahora()
                if isinstance(op.resultado, dict):
                    op.resultado["estado"] = op.estado
                    op.resultado["codigo"] = op.codigo
                    op.resultado["detalle"] = op.detalle
                    op.resultado["recurso_id"] = str(pedido.id)

        await self.db.flush()
        return pedido
