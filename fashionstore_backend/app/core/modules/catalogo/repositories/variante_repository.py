import uuid
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.catalogo.models import VarianteProducto


class VarianteRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def buscarPorId(self, variante_id: uuid.UUID) -> Optional[VarianteProducto]:
        query = select(VarianteProducto).where(VarianteProducto.id == variante_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorSku(self, sku: str) -> Optional[VarianteProducto]:
        query = select(VarianteProducto).where(VarianteProducto.sku == sku.strip())
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorCodigoBarras(self, codigo: str) -> Optional[VarianteProducto]:
        if not codigo:
            return None
        query = select(VarianteProducto).where(VarianteProducto.codigo_barras == codigo.strip())
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorProductoTallaColor(self, producto_id: uuid.UUID, talla_id: uuid.UUID, color_id: uuid.UUID) -> Optional[VarianteProducto]:
        query = select(VarianteProducto).where(
            VarianteProducto.producto_id == producto_id,
            VarianteProducto.talla_id == talla_id,
            VarianteProducto.color_id == color_id
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def listar(
        self,
        producto_id: Optional[uuid.UUID] = None,
        solo_activas: bool = False,
        limit: int = 50,
        offset: int = 0,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> List[VarianteProducto]:
        q = select(VarianteProducto)
        if empresa_id:
            q = q.where(VarianteProducto.empresa_id == empresa_id)
        if producto_id:
            q = q.where(VarianteProducto.producto_id == producto_id)
        if solo_activas:
            q = q.where(VarianteProducto.activa == True)
        q = q.order_by(VarianteProducto.sku).limit(limit).offset(offset)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def crear(self, variante: VarianteProducto) -> VarianteProducto:
        """Datos VarianteRepository.crear() para CU05"""
        self.db.add(variante)
        await self.db.flush()
        return variante

    async def actualizar(self, variante: VarianteProducto) -> VarianteProducto:
        await self.db.flush()
        return variante

    async def actualizarCostos(self, variante_id: uuid.UUID, costo_promedio: Decimal, costo_ultimo: Decimal) -> Optional[VarianteProducto]:
        q = (
            update(VarianteProducto)
            .where(VarianteProducto.id == variante_id)
            .values(costo_promedio=costo_promedio, costo_ultimo=costo_ultimo)
        )
        await self.db.execute(q)
        return await self.buscarPorId(variante_id)
