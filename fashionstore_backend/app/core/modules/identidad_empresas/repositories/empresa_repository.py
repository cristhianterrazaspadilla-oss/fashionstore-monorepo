"""Repositorio EmpresaRepository — CU01."""
import uuid
from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.identidad_empresas.models import Empresa


class EmpresaRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, empresa: Empresa) -> Empresa:
        self.db.add(empresa)
        await self.db.flush()
        return empresa

    async def buscarPorId(self, empresa_id: uuid.UUID) -> Optional[Empresa]:
        result = await self.db.execute(select(Empresa).where(Empresa.id == empresa_id))
        return result.scalars().first()

    async def buscarPorCodigo(self, codigo: str) -> Optional[Empresa]:
        norm = codigo.strip().lower()
        result = await self.db.execute(
            select(Empresa).where(func.lower(Empresa.codigo) == norm)
        )
        return result.scalars().first()

    async def listar(self, solo_activas: bool = False) -> List[Empresa]:
        query = select(Empresa)
        if solo_activas:
            query = query.where(Empresa.estado == "ACTIVA")
        query = query.order_by(Empresa.nombre)
        result = await self.db.execute(query)
        return list(result.scalars().all())
