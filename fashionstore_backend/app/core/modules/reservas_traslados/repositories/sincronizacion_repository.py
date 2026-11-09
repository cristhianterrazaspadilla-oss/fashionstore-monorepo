"""Repositorio para referencias horarias y operaciones de sincronización (CU04 / C34)."""
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.reservas_traslados.models import (
    ReferenciaHoraria,
    OperacionSincronizacion,
)


class SincronizacionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crearReferencia(self, referencia: ReferenciaHoraria) -> ReferenciaHoraria:
        self.db.add(referencia)
        await self.db.flush()
        return referencia

    async def buscarReferencia(
        self,
        referencia_id: uuid.UUID,
        empresa_id: Optional[uuid.UUID] = None,
        usuario_id: Optional[uuid.UUID] = None,
        dispositivo_id: Optional[uuid.UUID] = None,
    ) -> Optional[ReferenciaHoraria]:
        query = select(ReferenciaHoraria).where(ReferenciaHoraria.id == referencia_id)
        if empresa_id is not None:
            query = query.where(ReferenciaHoraria.empresa_id == empresa_id)
        if usuario_id is not None:
            query = query.where(ReferenciaHoraria.usuario_id == usuario_id)
        if dispositivo_id is not None:
            query = query.where(ReferenciaHoraria.dispositivo_id == dispositivo_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def crearOperacion(
        self, operacion: OperacionSincronizacion
    ) -> OperacionSincronizacion:
        self.db.add(operacion)
        await self.db.flush()
        return operacion

    async def buscarOperacionPorUuid(
        self, operacion_id: uuid.UUID, empresa_id: Optional[uuid.UUID] = None
    ) -> Optional[OperacionSincronizacion]:
        query = select(OperacionSincronizacion).where(
            OperacionSincronizacion.operacion_id == operacion_id
        )
        if empresa_id is not None:
            query = query.where(OperacionSincronizacion.empresa_id == empresa_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarOperacionPorActor(
        self, operacion_id: uuid.UUID, usuario_id: uuid.UUID, empresa_id: uuid.UUID
    ) -> Optional[OperacionSincronizacion]:
        query = select(OperacionSincronizacion).where(
            OperacionSincronizacion.operacion_id == operacion_id,
            OperacionSincronizacion.usuario_id == usuario_id,
            OperacionSincronizacion.empresa_id == empresa_id,
        )
        result = await self.db.execute(query)
        return result.scalars().first()
    async def buscarReferenciaPorIdempotencia(
        self, clave: uuid.UUID, empresa_id: uuid.UUID
    ) -> Optional[ReferenciaHoraria]:
        query = select(ReferenciaHoraria).where(
            ReferenciaHoraria.empresa_id == empresa_id,
            ReferenciaHoraria.clave_idempotencia == clave,
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarUltimaReferenciaVerificable(
        self, empresa_id: uuid.UUID, usuario_id: uuid.UUID, dispositivo_id: uuid.UUID
    ) -> Optional[ReferenciaHoraria]:
        query = (
            select(ReferenciaHoraria)
            .where(
                ReferenciaHoraria.empresa_id == empresa_id,
                ReferenciaHoraria.usuario_id == usuario_id,
                ReferenciaHoraria.dispositivo_id == dispositivo_id,
            )
            .order_by(ReferenciaHoraria.emitida_en.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalars().first()
