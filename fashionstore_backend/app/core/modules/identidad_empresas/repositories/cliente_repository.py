import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.identidad_empresas.models import Cliente, Usuario


class ClienteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, cliente: Cliente) -> Cliente:
        self.db.add(cliente)
        await self.db.flush()
        return cliente

    async def buscarPorUsuarioId(self, usuario_id: uuid.UUID) -> Optional[Cliente]:
        query = (
            select(Cliente)
            .options(selectinload(Cliente.usuario).selectinload(Usuario.rol))
            .where(Cliente.usuario_id == usuario_id)
        )
        result = await self.db.execute(query)
        return result.scalars().first()
