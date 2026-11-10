"""Repositorio VentaRepository / DetalleVentaRepository — CU11, CU13, CU23."""
import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Venta


class VentaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, venta: Venta) -> Venta:
        self.db.add(venta)
        await self.db.flush()
        return venta

    async def buscarPorId(self, venta_id: uuid.UUID, empresa_id=None) -> Optional[Venta]:
        query = (
            select(Venta)
            .options(selectinload(Venta.detalles))
            .where(Venta.id == venta_id)
        )
        if empresa_id is not None:
            query = query.where(Venta.empresa_id == empresa_id)
        return (await self.db.execute(query)).scalars().first()

    async def buscarPorClave(self, clave: uuid.UUID) -> Optional[Venta]:
        query = (
            select(Venta)
            .options(selectinload(Venta.detalles))
            .where(Venta.clave_idempotencia == clave)
        )
        return (await self.db.execute(query)).scalars().first()

    async def existeNumero(self, numero: str) -> bool:
        result = await self.db.execute(select(Venta.id).where(Venta.numero == numero))
        return result.scalars().first() is not None

    async def buscarPorNumero(self, numero: str, empresa_id=None) -> Optional[Venta]:
        query = (
            select(Venta)
            .options(selectinload(Venta.detalles))
            .where(Venta.numero == numero)
        )
        if empresa_id is not None:
            query = query.where(Venta.empresa_id == empresa_id)
        return (await self.db.execute(query)).scalars().first()

    async def adelantoYaDescontado(self, reserva_id: uuid.UUID) -> bool:
        """True si alguna venta de la reserva ya desconto adelanto (una sola vez)."""
        result = await self.db.execute(
            select(Venta.id).where(
                Venta.reserva_id == reserva_id,
                Venta.adelanto_descontado > 0,
            )
        )
        return result.scalars().first() is not None

    async def porCliente(
        self,
        cliente_id: uuid.UUID,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
        empresa_id=None,
    ) -> Tuple[List[Venta], int]:
        base = select(Venta).where(Venta.cliente_id == cliente_id)
        conteo = select(func.count()).select_from(Venta).where(Venta.cliente_id == cliente_id)
        if empresa_id is not None:
            base = base.where(Venta.empresa_id == empresa_id)
            conteo = conteo.where(Venta.empresa_id == empresa_id)
        if desde is not None:
            base = base.where(Venta.creada_en >= desde)
            conteo = conteo.where(Venta.creada_en >= desde)
        if hasta is not None:
            base = base.where(Venta.creada_en <= hasta)
            conteo = conteo.where(Venta.creada_en <= hasta)
        total = int((await self.db.execute(conteo)).scalar() or 0)
        base = (
            base.options(selectinload(Venta.detalles))
            .order_by(Venta.creada_en.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.db.execute(base)).scalars().all()), total

    async def porSucursal(
        self,
        sucursal_id: uuid.UUID,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
        empresa_id=None,
    ) -> Tuple[List[Venta], int]:
        estados = ("PAGADA", "PARCIALMENTE_DEVUELTA", "DEVUELTA")
        base = select(Venta).where(Venta.sucursal_id == sucursal_id, Venta.estado.in_(estados))
        conteo = select(func.count()).select_from(Venta).where(Venta.sucursal_id == sucursal_id, Venta.estado.in_(estados))
        if empresa_id is not None:
            base = base.where(Venta.empresa_id == empresa_id)
            conteo = conteo.where(Venta.empresa_id == empresa_id)
        if desde is not None:
            base = base.where(Venta.creada_en >= desde)
            conteo = conteo.where(Venta.creada_en >= desde)
        if hasta is not None:
            base = base.where(Venta.creada_en <= hasta)
            conteo = conteo.where(Venta.creada_en <= hasta)
        total = int((await self.db.execute(conteo)).scalar() or 0)
        base = (
            base.options(selectinload(Venta.detalles))
            .order_by(Venta.creada_en.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.db.execute(base)).scalars().all()), total


class DetalleVentaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, detalle: DetalleVenta) -> DetalleVenta:
        self.db.add(detalle)
        await self.db.flush()
        return detalle

    async def porVenta(self, venta_id: uuid.UUID) -> List[DetalleVenta]:
        result = await self.db.execute(
            select(DetalleVenta).where(DetalleVenta.venta_id == venta_id)
        )
        return list(result.scalars().all())

    async def cantidadDevueltaAcumulada(self, detalle_venta_id: uuid.UUID) -> int:
        """Suma de DEVOLUCION en Kardex referenciando este detalle (sin tabla extra)."""
        from backend.app.core.modules.inventario.models import MovimientoInventario

        result = await self.db.execute(
            select(func.coalesce(func.sum(MovimientoInventario.cantidad), 0)).where(
                MovimientoInventario.tipo == "DEVOLUCION",
                MovimientoInventario.referencia_tipo == "DETALLE_VENTA",
                MovimientoInventario.referencia_id == detalle_venta_id,
            )
        )
        return int(result.scalar() or 0)

    async def cantidadesPosventaComprometidas(self, detalle_venta_id: uuid.UUID) -> Tuple[int, int]:
        """Devueltas/comprometidas y cambiadas, sin contar dos veces su Kardex.

        El llamador bloquea DetalleVenta antes de consultar y mantiene el
        bloqueo hasta confirmar la solicitud o devolución física.
        """
        from backend.app.core.modules.inventario.models import MovimientoInventario
        from backend.app.core.modules.posventa.services.devolucion_service import Devolucion, DetalleDevolucion
        from backend.app.core.modules.posventa.services.cambio_service import Cambio, DetalleCambio

        devueltas = await self.db.execute(
            select(func.coalesce(func.sum(DetalleDevolucion.cantidad_solicitada), 0))
            .join(Devolucion, Devolucion.id == DetalleDevolucion.devolucion_id)
            .where(DetalleDevolucion.detalle_venta_id == detalle_venta_id, Devolucion.estado != "RECHAZADA")
        )
        cambiadas = await self.db.execute(
            select(func.coalesce(func.sum(DetalleCambio.cantidad), 0))
            .join(Cambio, Cambio.id == DetalleCambio.cambio_id)
            .where(
                DetalleCambio.detalle_venta_id == detalle_venta_id,
                DetalleCambio.tipo_linea == "ORIGINAL", Cambio.estado != "RECHAZADO",
            )
        )
        # La inspección CU20 ya está contabilizada en DetalleDevolucion.
        # Solo añadir aquí las devoluciones físicas del adaptador heredado.
        tiene_detalle = select(DetalleDevolucion.id).where(
            DetalleDevolucion.id == MovimientoInventario.linea_referencia_id,
            DetalleDevolucion.detalle_venta_id == detalle_venta_id,
        ).exists()
        heredadas = await self.db.execute(
            select(func.coalesce(func.sum(MovimientoInventario.cantidad), 0)).where(
                MovimientoInventario.tipo == "DEVOLUCION",
                MovimientoInventario.referencia_tipo == "DETALLE_VENTA",
                MovimientoInventario.referencia_id == detalle_venta_id,
                ~tiene_detalle,
            )
        )
        return int(devueltas.scalar() or 0) + int(heredadas.scalar() or 0), int(cambiadas.scalar() or 0)
