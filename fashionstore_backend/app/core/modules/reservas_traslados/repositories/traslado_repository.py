"""Datos TrasladoRepository — CU09.

Solo flush; el servicio confirma o revierte (transaccion unica).
"""
import uuid
from typing import List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.reservas_traslados.models import Traslado, DetalleTraslado


class TrasladoRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, traslado: Traslado) -> Traslado:
        self.db.add(traslado)
        await self.db.flush()
        return traslado

    async def buscarPorId(self, traslado_id: uuid.UUID) -> Optional[Traslado]:
        result = await self.db.execute(select(Traslado).where(Traslado.id == traslado_id))
        return result.scalars().first()

    async def buscarPorClave(self, clave: uuid.UUID) -> Optional[Traslado]:
        result = await self.db.execute(select(Traslado).where(Traslado.clave_idempotencia == clave))
        return result.scalars().first()

    async def listarPorReserva(self, reserva_id: uuid.UUID) -> List[Traslado]:
        result = await self.db.execute(
            select(Traslado)
            .where(Traslado.reserva_id == reserva_id)
            .order_by(Traslado.fecha_solicitud)
        )
        return list(result.scalars().all())

    async def listar(
        self,
        estado: Optional[str] = None,
        sucursal_origen_id: Optional[uuid.UUID] = None,
        sucursal_destino_id: Optional[uuid.UUID] = None,
        reserva_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> Tuple[List[Traslado], int]:
        filtros = []
        if empresa_id is not None:
            filtros.append(Traslado.empresa_id == empresa_id)
        if estado is not None:
            filtros.append(Traslado.estado == estado)
        if sucursal_origen_id is not None:
            filtros.append(Traslado.sucursal_origen_id == sucursal_origen_id)
        if sucursal_destino_id is not None:
            filtros.append(Traslado.sucursal_destino_id == sucursal_destino_id)
        if reserva_id is not None:
            filtros.append(Traslado.reserva_id == reserva_id)
        conteo = select(func.count()).select_from(Traslado)
        if filtros:
            conteo = conteo.where(*filtros)
        total = int((await self.db.execute(conteo)).scalar() or 0)
        query = select(Traslado).order_by(Traslado.fecha_solicitud.desc())
        if filtros:
            query = query.where(*filtros)
        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def detallesDeTraslado(self, traslado_id: uuid.UUID) -> List[DetalleTraslado]:
        result = await self.db.execute(
            select(DetalleTraslado).where(DetalleTraslado.traslado_id == traslado_id)
        )
        return list(result.scalars().all())

    async def buscarActivoPorLinea(self, detalle_reserva_id: uuid.UUID) -> Optional[Traslado]:
        result = await self.db.execute(
            select(Traslado)
            .join(DetalleTraslado, DetalleTraslado.traslado_id == Traslado.id)
            .where(
                DetalleTraslado.detalle_reserva_id == detalle_reserva_id,
                Traslado.estado.in_(("SOLICITADO", "APROBADO", "DESPACHADO")),
            )
            .order_by(Traslado.fecha_solicitud.desc())
        )
        return result.scalars().first()
