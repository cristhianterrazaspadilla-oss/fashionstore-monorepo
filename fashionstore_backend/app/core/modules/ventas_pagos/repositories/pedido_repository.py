"""Repositorio PedidoRepository — CU16."""
import uuid
from typing import List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.modules.ventas_pagos.models import PedidoEntrega


class PedidoRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, pedido: PedidoEntrega) -> PedidoEntrega:
        self.db.add(pedido)
        await self.db.flush()
        return pedido

    async def buscarPorId(self, pedido_id: uuid.UUID, empresa_id=None) -> Optional[PedidoEntrega]:
        query = select(PedidoEntrega).where(PedidoEntrega.id == pedido_id)
        if empresa_id is not None:
            query = query.where(PedidoEntrega.empresa_id == empresa_id)
        return (await self.db.execute(query)).scalars().first()

    async def buscarPorVenta(self, venta_id: uuid.UUID) -> Optional[PedidoEntrega]:
        r = await self.db.execute(select(PedidoEntrega).where(PedidoEntrega.venta_id == venta_id))
        return r.scalars().first()

    async def cola(
        self,
        sucursal_id: Optional[uuid.UUID] = None,
        estado: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        empresa_id=None,
    ) -> Tuple[List[PedidoEntrega], int]:
        base = select(PedidoEntrega).order_by(PedidoEntrega.creada_en.desc())
        conteo = select(func.count()).select_from(PedidoEntrega)
        if empresa_id is not None:
            base = base.where(PedidoEntrega.empresa_id == empresa_id)
            conteo = conteo.where(PedidoEntrega.empresa_id == empresa_id)
        if sucursal_id is not None:
            base = base.where(PedidoEntrega.sucursal_id == sucursal_id)
            conteo = conteo.where(PedidoEntrega.sucursal_id == sucursal_id)
        if estado is not None:
            base = base.where(PedidoEntrega.estado == estado)
            conteo = conteo.where(PedidoEntrega.estado == estado)
        total = int((await self.db.execute(conteo)).scalar() or 0)
        items = list((await self.db.execute(base.limit(limit).offset(offset))).scalars().all())
        return items, total

    async def pedidosDeCliente(
        self,
        cliente_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        empresa_id=None,
    ) -> Tuple[List[PedidoEntrega], int]:
        base = (
            select(PedidoEntrega).where(PedidoEntrega.cliente_id == cliente_id)
            .order_by(PedidoEntrega.creada_en.desc())
        )
        conteo = select(func.count()).select_from(PedidoEntrega).where(
            PedidoEntrega.cliente_id == cliente_id
        )
        if empresa_id is not None:
            base = base.where(PedidoEntrega.empresa_id == empresa_id)
            conteo = conteo.where(PedidoEntrega.empresa_id == empresa_id)
        total = int((await self.db.execute(conteo)).scalar() or 0)
        items = list((await self.db.execute(base.limit(limit).offset(offset))).scalars().all())
        return items, total
