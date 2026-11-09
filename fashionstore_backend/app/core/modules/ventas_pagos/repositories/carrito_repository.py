"""Repositorio CarritoRepository — CU14."""
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.modules.ventas_pagos.models import Carrito, DetalleCarrito


class CarritoRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def activoDe(self, cliente_id: uuid.UUID, canal: str) -> Optional[Carrito]:
        r = await self.db.execute(
            select(Carrito).where(
                Carrito.cliente_id == cliente_id,
                Carrito.canal == canal,
                Carrito.estado == "ACTIVO",
            )
        )
        return r.scalars().first()

    async def buscarPorId(self, carrito_id: uuid.UUID) -> Optional[Carrito]:
        return await self.db.get(Carrito, carrito_id)

    async def crear(self, carrito: Carrito) -> Carrito:
        self.db.add(carrito)
        await self.db.flush()
        return carrito

    async def lineasDe(self, carrito_id: uuid.UUID) -> List[DetalleCarrito]:
        r = await self.db.execute(
            select(DetalleCarrito).where(DetalleCarrito.carrito_id == carrito_id)
        )
        return list(r.scalars().all())

    async def lineaPorVariante(self, carrito_id: uuid.UUID, variante_id: uuid.UUID) -> Optional[DetalleCarrito]:
        r = await self.db.execute(
            select(DetalleCarrito).where(
                DetalleCarrito.carrito_id == carrito_id,
                DetalleCarrito.variante_id == variante_id,
            )
        )
        return r.scalars().first()

    async def agregarLinea(self, linea: DetalleCarrito) -> DetalleCarrito:
        self.db.add(linea)
        await self.db.flush()
        return linea

    async def eliminarLinea(self, linea: DetalleCarrito) -> None:
        await self.db.delete(linea)
        await self.db.flush()
