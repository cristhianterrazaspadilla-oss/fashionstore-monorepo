"""Repositorio SolicitudIaRepository — CU18, CU20, CU21, CU25."""
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.experiencia_cliente.models import SolicitudIA


class SolicitudIaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, solicitud: SolicitudIA) -> SolicitudIA:
        self.db.add(solicitud)
        await self.db.flush()
        return solicitud
