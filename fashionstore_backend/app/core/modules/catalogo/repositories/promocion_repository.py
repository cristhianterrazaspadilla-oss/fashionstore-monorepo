import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.catalogo.models import Promocion, PromocionVariante


class PromocionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear(self, promo: Promocion) -> Promocion:
        self.db.add(promo)
        await self.db.flush()
        return promo

    async def buscarPorId(self, promo_id: uuid.UUID, empresa_id: Optional[uuid.UUID] = None) -> Optional[Promocion]:
        consulta = select(Promocion).where(Promocion.id == promo_id)
        if empresa_id is not None:
            consulta = consulta.where(Promocion.empresa_id == empresa_id)
        return (await self.db.execute(consulta)).scalars().first()

    async def buscarPorCodigo(self, codigo: str, empresa_id: Optional[uuid.UUID] = None) -> Optional[Promocion]:
        consulta = select(Promocion).where(Promocion.codigo == codigo)
        if empresa_id is not None:
            consulta = consulta.where(Promocion.empresa_id == empresa_id)
        r = await self.db.execute(consulta)
        return r.scalars().first()

    async def listar(self, solo_activas: bool = False, limit: int = 50, offset: int = 0, empresa_id: Optional[uuid.UUID] = None):
        base = select(Promocion).order_by(Promocion.creada_en.desc())
        conteo = select(func.count()).select_from(Promocion)
        if empresa_id is not None:
            base = base.where(Promocion.empresa_id == empresa_id)
            conteo = conteo.where(Promocion.empresa_id == empresa_id)
        if solo_activas:
            base = base.where(Promocion.activa.is_(True))
            conteo = conteo.where(Promocion.activa.is_(True))
        total = int((await self.db.execute(conteo)).scalar() or 0)
        items = list((await self.db.execute(base.limit(limit).offset(offset))).scalars().all())
        return items, total

    async def variantesDe(self, promo_id: uuid.UUID) -> List[uuid.UUID]:
        r = await self.db.execute(
            select(PromocionVariante.variante_id).where(PromocionVariante.promocion_id == promo_id)
        )
        return list(r.scalars().all())

    async def asociar(self, promo_id: uuid.UUID, variante_id: uuid.UUID) -> None:
        self.db.add(PromocionVariante(promocion_id=promo_id, variante_id=variante_id))
        await self.db.flush()

    async def desasociar(self, promo_id: uuid.UUID, variante_id: uuid.UUID) -> bool:
        r = await self.db.execute(
            select(PromocionVariante).where(
                PromocionVariante.promocion_id == promo_id,
                PromocionVariante.variante_id == variante_id,
            )
        )
        fila = r.scalars().first()
        if fila is None:
            return False
        await self.db.delete(fila)
        await self.db.flush()
        return True

    async def vigentesPorVariante(self, variante_id: uuid.UUID, ahora: datetime) -> List[Promocion]:
        """Promociones activas y vigentes asociadas a la variante."""
        q = (
            select(Promocion)
            .join(PromocionVariante, PromocionVariante.promocion_id == Promocion.id)
            .where(PromocionVariante.variante_id == variante_id)
            .where(Promocion.activa.is_(True))
            .where((Promocion.vigencia_inicio.is_(None)) | (Promocion.vigencia_inicio <= ahora))
            .where((Promocion.vigencia_fin.is_(None)) | (Promocion.vigencia_fin >= ahora))
            .order_by(Promocion.id)
        )
        return list((await self.db.execute(q)).scalars().all())
