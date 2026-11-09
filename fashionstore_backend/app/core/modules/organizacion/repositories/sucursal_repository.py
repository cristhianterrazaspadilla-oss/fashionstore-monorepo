import uuid
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.organizacion.models import Sucursal


class SucursalRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def buscarPorId(self, sucursal_id: uuid.UUID) -> Optional[Sucursal]:
        query = (
            select(Sucursal)
            .options(selectinload(Sucursal.ciudad))
            .where(Sucursal.id == sucursal_id)
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorCiudadYNombre(
        self, ciudad_id: uuid.UUID, nombre: str, empresa_id: Optional[uuid.UUID] = None
    ) -> Optional[Sucursal]:
        query = select(Sucursal).where(
            Sucursal.ciudad_id == ciudad_id,
            Sucursal.nombre.ilike(nombre.strip()),
        )
        if empresa_id is not None:
            query = query.where(Sucursal.empresa_id == empresa_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def listar(
        self,
        ciudad_id: Optional[uuid.UUID] = None,
        empresa_id: Optional[uuid.UUID] = None,
        solo_activas: bool = True,
    ) -> List[Sucursal]:
        query = select(Sucursal).options(selectinload(Sucursal.ciudad))
        if ciudad_id:
            query = query.where(Sucursal.ciudad_id == ciudad_id)
        if empresa_id:
            query = query.where(Sucursal.empresa_id == empresa_id)
        if solo_activas:
            query = query.where(Sucursal.activa == True)
        query = query.order_by(Sucursal.nombre)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def crear(self, sucursal: Sucursal) -> Sucursal:
        self.db.add(sucursal)
        await self.db.flush()
        return sucursal

    async def actualizarTarifas(
        self,
        sucursal_id: uuid.UUID,
        tarifa_base_delivery: Decimal,
        incremento_anillo_delivery: Decimal,
        anillo_minimo_delivery: Optional[int] = None,
        anillo_maximo_delivery: Optional[int] = None,
        delivery_activo: Optional[bool] = None,
    ) -> Optional[Sucursal]:
        valores = {
            "tarifa_base_delivery": tarifa_base_delivery,
            "incremento_anillo_delivery": incremento_anillo_delivery,
        }
        if anillo_minimo_delivery is not None:
            valores["anillo_minimo_delivery"] = anillo_minimo_delivery
        if anillo_maximo_delivery is not None:
            valores["anillo_maximo_delivery"] = anillo_maximo_delivery
        if delivery_activo is not None:
            valores["delivery_activo"] = delivery_activo

        query = (
            update(Sucursal)
            .where(Sucursal.id == sucursal_id)
            .values(**valores)
        )
        await self.db.execute(query)
        return await self.buscarPorId(sucursal_id)

    async def actualizarAdelanto(
        self,
        sucursal_id: uuid.UUID,
        adelanto_activo: bool,
        modalidad_adelanto: Optional[str] = None,
        valor_adelanto: Optional[Decimal] = None,
    ) -> Optional[Sucursal]:
        valores = {"adelanto_activo": adelanto_activo}
        if modalidad_adelanto is not None:
            valores["modalidad_adelanto"] = modalidad_adelanto
        if valor_adelanto is not None:
            valores["valor_adelanto"] = valor_adelanto
        query = (
            update(Sucursal)
            .where(Sucursal.id == sucursal_id)
            .values(**valores)
        )
        await self.db.execute(query)
        return await self.buscarPorId(sucursal_id)
