import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.inventario.models import MovimientoInventario

class MovimientoRepository:
    """
    Datos MovimientoRepository.listar() para CU07 (RF22)
    Kardex inmutable: cada cambio genera movimiento con tipo, cantidad, costo_unitario, responsable, referencia.
    Solo lectura + exposición de movimientos ya creados por CU04.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def registrar(self, movimiento: MovimientoInventario) -> MovimientoInventario:
        self.db.add(movimiento)
        await self.db.flush()
        return movimiento

    async def buscarPorClaveIdempotencia(self, clave: uuid.UUID) -> Optional[MovimientoInventario]:
        query = select(MovimientoInventario).where(MovimientoInventario.clave_idempotencia == clave)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def buscarPorEfecto(
        self,
        referencia_tipo: str,
        referencia_id: uuid.UUID,
        tipo: str,
        variante_id: uuid.UUID,
        sucursal_origen_id: Optional[uuid.UUID] = None,
        sucursal_destino_id: Optional[uuid.UUID] = None,
        linea_referencia_id: Optional[uuid.UUID] = None,
    ) -> Optional[MovimientoInventario]:
        query = select(MovimientoInventario).where(
            MovimientoInventario.referencia_tipo == referencia_tipo,
            MovimientoInventario.referencia_id == referencia_id,
            MovimientoInventario.tipo == tipo,
            MovimientoInventario.variante_id == variante_id,
        )
        if sucursal_origen_id is None:
            query = query.where(MovimientoInventario.sucursal_origen_id.is_(None))
        else:
            query = query.where(MovimientoInventario.sucursal_origen_id == sucursal_origen_id)
        if sucursal_destino_id is None:
            query = query.where(MovimientoInventario.sucursal_destino_id.is_(None))
        else:
            query = query.where(MovimientoInventario.sucursal_destino_id == sucursal_destino_id)
        if linea_referencia_id is None:
            query = query.where(MovimientoInventario.linea_referencia_id.is_(None))
        else:
            query = query.where(MovimientoInventario.linea_referencia_id == linea_referencia_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def registrarUnico(
        self, movimiento: MovimientoInventario
    ) -> Tuple[MovimientoInventario, bool]:
        try:
            async with self.db.begin_nested():
                self.db.add(movimiento)
                await self.db.flush()
            return movimiento, True
        except IntegrityError as e:
            mensaje = str(getattr(e, "orig", e))
            if "uq_movimientos_efecto_logico" not in mensaje and "clave_idempotencia" not in mensaje:
                raise
            existente = await self.buscarPorEfecto(
                referencia_tipo=movimiento.referencia_tipo,
                referencia_id=movimiento.referencia_id,
                tipo=movimiento.tipo,
                variante_id=movimiento.variante_id,
                sucursal_origen_id=movimiento.sucursal_origen_id,
                sucursal_destino_id=movimiento.sucursal_destino_id,
                linea_referencia_id=movimiento.linea_referencia_id,
            )
            if existente is None and movimiento.clave_idempotencia is not None:
                existente = await self.buscarPorClaveIdempotencia(movimiento.clave_idempotencia)
            if existente is None:
                raise
            return existente, False

    async def listar(
        self,
        variante_id: Optional[uuid.UUID] = None,
        sucursal_id: Optional[uuid.UUID] = None,
        tipo: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        empresa_id: Optional[uuid.UUID] = None,
        orden_asc: bool = False,
    ) -> List[MovimientoInventario]:
        orden = MovimientoInventario.fecha_hora.asc() if orden_asc else MovimientoInventario.fecha_hora.desc()
        query = select(MovimientoInventario).order_by(orden)
        if empresa_id:
            from backend.app.core.modules.catalogo.models import VarianteProducto
            query = query.join(VarianteProducto, VarianteProducto.id == MovimientoInventario.variante_id).where(
                VarianteProducto.empresa_id == empresa_id
            )
        if variante_id:
            query = query.where(MovimientoInventario.variante_id == variante_id)
        if sucursal_id:
            query = query.where(
                (MovimientoInventario.sucursal_origen_id == sucursal_id)
                | (MovimientoInventario.sucursal_destino_id == sucursal_id)
            )
        if tipo:
            query = query.where(MovimientoInventario.tipo == tipo)
        if desde:
            query = query.where(MovimientoInventario.fecha_hora >= desde)
        if hasta:
            query = query.where(MovimientoInventario.fecha_hora <= hasta)
        if limit is not None:
            query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def listarPaginado(
        self,
        variante_id: Optional[uuid.UUID] = None,
        sucursal_id: Optional[uuid.UUID] = None,
        tipo: Optional[str] = None,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        count_q = select(func.count()).select_from(MovimientoInventario)
        if variante_id:
            count_q = count_q.where(MovimientoInventario.variante_id == variante_id)
        if sucursal_id:
            count_q = count_q.where(
                (MovimientoInventario.sucursal_origen_id == sucursal_id)
                | (MovimientoInventario.sucursal_destino_id == sucursal_id)
            )
        if tipo:
            count_q = count_q.where(MovimientoInventario.tipo == tipo)
        if desde:
            count_q = count_q.where(MovimientoInventario.fecha_hora >= desde)
        if hasta:
            count_q = count_q.where(MovimientoInventario.fecha_hora <= hasta)
        total_res = await self.db.execute(count_q)
        total = int(total_res.scalar() or 0)

        items = await self.listar(
            variante_id=variante_id,
            sucursal_id=sucursal_id,
            tipo=tipo,
            desde=desde,
            hasta=hasta,
            limit=limit,
            offset=offset,
        )
        return {"total": total, "items": items, "limit": limit, "offset": offset}

    async def buscarPorId(self, movimiento_id: uuid.UUID) -> Optional[MovimientoInventario]:
        query = select(MovimientoInventario).where(MovimientoInventario.id == movimiento_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def listarPorReferencia(self, referencia_tipo: str, referencia_id: uuid.UUID) -> List[MovimientoInventario]:
        query = select(MovimientoInventario).where(
            MovimientoInventario.referencia_tipo == referencia_tipo,
            MovimientoInventario.referencia_id == referencia_id,
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())
