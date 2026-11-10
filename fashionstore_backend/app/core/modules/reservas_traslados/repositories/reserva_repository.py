"""Datos ReservaRepository — CU08/CU10/CU24.

Solo flush; el servicio confirma o revierte (transaccion unica).
"""
import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.reservas_traslados.models import Reserva, DetalleReserva, Traslado

ESTADOS_NO_TERMINALES_RESERVA = ("PENDIENTE_TRASLADO", "PENDIENTE", "PREPARADA", "ATENDIDA")
ESTADOS_TERMINALES_RESERVA = ("COMPLETADA", "CANCELADA", "VENCIDA")


class ReservaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, reserva: Reserva) -> Reserva:
        self.db.add(reserva)
        await self.db.flush()
        return reserva

    async def buscarPorId(
        self, reserva_id: uuid.UUID, empresa_id: Optional[uuid.UUID] = None,
        bloquear: bool = False,
    ) -> Optional[Reserva]:
        query = (
            select(Reserva)
            .options(selectinload(Reserva.detalles))
            .where(Reserva.id == reserva_id)
        )
        if empresa_id is not None:
            query = query.where(Reserva.empresa_id == empresa_id)
        if bloquear:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorCodigo(
        self, codigo: str, empresa_id: Optional[uuid.UUID] = None
    ) -> Optional[Reserva]:
        query = (
            select(Reserva)
            .options(selectinload(Reserva.detalles))
            .where(Reserva.codigo == codigo)
        )
        if empresa_id is not None:
            query = query.where(Reserva.empresa_id == empresa_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorClave(
        self, clave: uuid.UUID, empresa_id: Optional[uuid.UUID] = None
    ) -> Optional[Reserva]:
        query = (
            select(Reserva)
            .options(selectinload(Reserva.detalles))
            .where(Reserva.clave_idempotencia == clave)
        )
        if empresa_id is not None:
            query = query.where(Reserva.empresa_id == empresa_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def existeCodigo(
        self, codigo: str, empresa_id: Optional[uuid.UUID] = None
    ) -> bool:
        query = select(Reserva.id).where(Reserva.codigo == codigo)
        if empresa_id is not None:
            query = query.where(Reserva.empresa_id == empresa_id)
        result = await self.db.execute(query)
        return result.scalars().first() is not None

    async def trasladosDeReserva(self, reserva_id: uuid.UUID, bloquear: bool = False) -> List[Traslado]:
        query = select(Traslado).where(Traslado.reserva_id == reserva_id)
        if bloquear:
            query = query.order_by(Traslado.id).with_for_update().execution_options(populate_existing=True)
        else:
            query = query.order_by(Traslado.fecha_solicitud)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def listar(
        self,
        cliente_id: Optional[uuid.UUID] = None,
        sucursal_id: Optional[uuid.UUID] = None,
        estado: Optional[str] = None,
        codigo: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> Tuple[List[Reserva], int]:
        base = select(Reserva)
        conteo = select(func.count()).select_from(Reserva)
        if empresa_id is not None:
            base = base.where(Reserva.empresa_id == empresa_id)
            conteo = conteo.where(Reserva.empresa_id == empresa_id)
        if cliente_id is not None:
            base = base.where(Reserva.cliente_id == cliente_id)
            conteo = conteo.where(Reserva.cliente_id == cliente_id)
        if sucursal_id is not None:
            base = base.where(Reserva.sucursal_destino_id == sucursal_id)
            conteo = conteo.where(Reserva.sucursal_destino_id == sucursal_id)
        if estado is not None:
            base = base.where(Reserva.estado == estado)
            conteo = conteo.where(Reserva.estado == estado)
        if codigo is not None:
            base = base.where(Reserva.codigo == codigo)
            conteo = conteo.where(Reserva.codigo == codigo)
        total = int((await self.db.execute(conteo)).scalar() or 0)
        base = (
            base.options(selectinload(Reserva.detalles))
            .order_by(Reserva.fecha_creacion.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list((await self.db.execute(base)).scalars().all())
        return items, total

    async def buscarVencidas(
        self, ahora: datetime, limite: int = 100, empresa_id: Optional[uuid.UUID] = None
    ) -> List[Reserva]:
        query = (
            select(Reserva)
            .options(selectinload(Reserva.detalles))
            .where(
                Reserva.vence_en <= ahora,
                Reserva.estado.in_(ESTADOS_NO_TERMINALES_RESERVA),
            )
        )
        if empresa_id is not None:
            query = query.where(Reserva.empresa_id == empresa_id)
        query = query.order_by(Reserva.vence_en, Reserva.id).limit(limite).with_for_update(skip_locked=True).execution_options(populate_existing=True)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def actualizarEstado(self, reserva: Reserva, estado: str) -> Reserva:
        reserva.estado = estado
        await self.db.flush()
        return reserva
