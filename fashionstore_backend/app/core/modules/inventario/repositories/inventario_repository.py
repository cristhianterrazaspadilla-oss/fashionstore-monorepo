import uuid
from typing import Optional, List, Dict, Any, Tuple
from fastapi import HTTPException, status
from sqlalchemy import select, func, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.inventario.models import InventarioSucursal
from backend.app.core.modules.organizacion.models import Sucursal, Ciudad

class InventarioRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def existenciaTotalPorVariante(self, variante_id: uuid.UUID) -> int:
        query = select(
            func.coalesce(
                func.sum(
                    InventarioSucursal.disponible
                    + InventarioSucursal.reservado
                    + InventarioSucursal.comprometido_traslado
                    + InventarioSucursal.en_transito
                    + InventarioSucursal.comprometido_caja
                    + InventarioSucursal.comprometido_digital
                ),
                0,
            )
        ).where(InventarioSucursal.variante_id == variante_id)
        result = await self.db.execute(query)
        return int(result.scalar() or 0)

    async def buscarPorVarianteYSucursal(self, variante_id: uuid.UUID, sucursal_id: uuid.UUID) -> Optional[InventarioSucursal]:
        query = select(InventarioSucursal).where(
            InventarioSucursal.variante_id == variante_id,
            InventarioSucursal.sucursal_id == sucursal_id,
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    @staticmethod
    def ordenarClavesBloqueo(
        claves: List[Tuple[uuid.UUID, uuid.UUID]],
    ) -> List[Tuple[uuid.UUID, uuid.UUID]]:
        return sorted(claves, key=lambda c: (str(c[0]), str(c[1])))

    async def bloquearFilas(
        self, claves: List[Tuple[uuid.UUID, uuid.UUID]]
    ) -> Dict[Tuple[uuid.UUID, uuid.UUID], Optional[InventarioSucursal]]:
        ordenadas = self.ordenarClavesBloqueo(list(dict.fromkeys(claves)))
        if not ordenadas:
            return {}
        query = (
            select(InventarioSucursal)
            .where(
                tuple_(InventarioSucursal.sucursal_id, InventarioSucursal.variante_id).in_(ordenadas)
            )
            .order_by(InventarioSucursal.sucursal_id, InventarioSucursal.variante_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(query)
        filas = {(r.sucursal_id, r.variante_id): r for r in result.scalars().all()}
        return {clave: filas.get(clave) for clave in ordenadas}

    async def moverDisponibleAReservado(
        self, variante_id: uuid.UUID, sucursal_id: uuid.UUID, cantidad: int
    ) -> InventarioSucursal:
        if cantidad <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cantidad a reservar debe ser mayor a cero",
            )
        filas = await self.bloquearFilas([(sucursal_id, variante_id)])
        registro = filas[(sucursal_id, variante_id)]
        if registro is None or registro.disponible < cantidad:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stock insuficiente en sucursal destino",
            )
        registro.disponible -= cantidad
        registro.reservado += cantidad
        await self.db.flush()
        return registro

    async def liberarReservado(
        self, variante_id: uuid.UUID, sucursal_id: uuid.UUID, cantidad: int
    ) -> InventarioSucursal:
        if cantidad <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cantidad a liberar debe ser mayor a cero",
            )
        filas = await self.bloquearFilas([(sucursal_id, variante_id)])
        registro = filas[(sucursal_id, variante_id)]
        if registro is None or registro.reservado < cantidad:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No hay suficiente stock reservado para liberar",
            )
        registro.reservado -= cantidad
        registro.disponible += cantidad
        await self.db.flush()
        return registro

    async def ingresar(self, variante_id: uuid.UUID, sucursal_id: uuid.UUID, cantidad: int) -> InventarioSucursal:
        registro = await self.buscarPorVarianteYSucursal(variante_id, sucursal_id)
        if registro is None:
            registro = InventarioSucursal(
                variante_id=variante_id,
                sucursal_id=sucursal_id,
                disponible=cantidad,
                reservado=0,
                comprometido_traslado=0,
                en_transito=0,
            )
            self.db.add(registro)
            await self.db.flush()
        else:
            registro.disponible = registro.disponible + cantidad
            await self.db.flush()
        return registro

    async def porVariante(self, variante_id: uuid.UUID) -> List[InventarioSucursal]:
        query = select(InventarioSucursal).where(
            InventarioSucursal.variante_id == variante_id,
            InventarioSucursal.disponible > 0
        ).order_by(InventarioSucursal.sucursal_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def porVarianteEnriquecido(self, variante_id: uuid.UUID) -> List[Dict[str, Any]]:
        from backend.app.core.modules.catalogo.models import VarianteProducto
        query = (
            select(InventarioSucursal, Sucursal, Ciudad)
            .join(Sucursal, Sucursal.id == InventarioSucursal.sucursal_id)
            .join(Ciudad, Ciudad.id == Sucursal.ciudad_id)
            .join(VarianteProducto, VarianteProducto.id == InventarioSucursal.variante_id)
            .where(
                InventarioSucursal.variante_id == variante_id,
                Sucursal.empresa_id == VarianteProducto.empresa_id,
                Sucursal.activa == True,
                InventarioSucursal.disponible > 0
            )
            .order_by(Sucursal.nombre)
        )
        result = await self.db.execute(query)
        rows = result.all()
        enriched = []
        for inv, suc, ciu in rows:
            enriched.append({
                "inventario_id": inv.id,
                "variante_id": inv.variante_id,
                "sucursal_id": suc.id,
                "sucursal_nombre": suc.nombre,
                "ciudad_id": ciu.id,
                "ciudad_nombre": ciu.nombre,
                "direccion": suc.direccion,
                "telefono": suc.telefono,
                "disponible": inv.disponible,
                "reservado": inv.reservado,
                "comprometido_traslado": inv.comprometido_traslado,
                "en_transito": inv.en_transito,
                "actualizado_en": inv.actualizado_en,
            })
        return enriched

    async def disponibilidadPorSucursal(self, variante_id: uuid.UUID) -> List[Dict[str, Any]]:
        return await self.porVarianteEnriquecido(variante_id)

    async def existencias(
        self,
        sucursal_id: Optional[uuid.UUID] = None,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> List[InventarioSucursal]:
        query = select(InventarioSucursal)
        if sucursal_id:
            query = query.where(InventarioSucursal.sucursal_id == sucursal_id)
        if empresa_id:
            query = query.join(Sucursal, Sucursal.id == InventarioSucursal.sucursal_id)
            query = query.where(Sucursal.empresa_id == empresa_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def existenciasEnriquecidas(
        self,
        sucursal_id: Optional[uuid.UUID] = None,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        from backend.app.core.modules.catalogo.models import VarianteProducto, Producto
        query = (
            select(InventarioSucursal, VarianteProducto, Producto, Sucursal, Ciudad)
            .join(VarianteProducto, VarianteProducto.id == InventarioSucursal.variante_id)
            .join(Producto, Producto.id == VarianteProducto.producto_id)
            .join(Sucursal, Sucursal.id == InventarioSucursal.sucursal_id)
            .join(Ciudad, Ciudad.id == Sucursal.ciudad_id)
        )
        if sucursal_id:
            query = query.where(InventarioSucursal.sucursal_id == sucursal_id)
        if empresa_id:
            query = query.where(Sucursal.empresa_id == empresa_id)
        query = query.order_by(Sucursal.nombre, Producto.nombre)
        result = await self.db.execute(query)
        rows = result.all()
        lista: List[Dict[str, Any]] = []
        for inv, var, prod, suc, ciu in rows:
            cupo_off = int(inv.comprometido_caja or 0)
            comp_dig = int(inv.comprometido_digital or 0)
            comp_cam = int(inv.comprometido_cambio or 0)
            fisico = inv.disponible + inv.reservado + inv.comprometido_traslado + cupo_off + comp_dig + comp_cam
            existencia_total = fisico + inv.en_transito
            costo_prom = float(var.costo_promedio or 0)
            valorizado = fisico * costo_prom
            margen_unit = float(var.precio or 0) - costo_prom
            lista.append({
                "inventario_id": inv.id,
                "variante_id": var.id,
                "sku": var.sku,
                "producto_id": prod.id,
                "producto_nombre": prod.nombre,
                "sucursal_id": suc.id,
                "sucursal_nombre": suc.nombre,
                "ciudad_nombre": ciu.nombre,
                "disponible": inv.disponible,
                "reservado": inv.reservado,
                "comprometido_traslado": inv.comprometido_traslado,
                "en_transito": inv.en_transito,
                "comprometido_caja": cupo_off,
                "comprometido_digital": comp_dig,
                "comprometido_cambio": comp_cam,
                "fisico": fisico,
                "libre": inv.disponible,
                "cupo_offline": cupo_off,
                "existencia_total": existencia_total,
                "costo_promedio": costo_prom,
                "costo_ultimo": float(var.costo_ultimo or 0),
                "precio": float(var.precio or 0),
                "valorizacion": round(valorizado, 2),
                "margen_bruto_unitario": round(margen_unit, 2),
                "margen_bruto_total": round(margen_unit * fisico, 2),
                "actualizado_en": inv.actualizado_en,
            })
        return lista

    async def valorizacionPorSucursal(
        self,
        sucursal_id: Optional[uuid.UUID] = None,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        from backend.app.core.modules.catalogo.models import VarianteProducto
        existencia_total_expr = (
            InventarioSucursal.disponible
            + InventarioSucursal.reservado
            + InventarioSucursal.comprometido_traslado
            + InventarioSucursal.en_transito
            + InventarioSucursal.comprometido_caja
            + InventarioSucursal.comprometido_digital
        )
        valorizacion_expr = existencia_total_expr * VarianteProducto.costo_promedio
        margen_expr = (VarianteProducto.precio - VarianteProducto.costo_promedio) * existencia_total_expr

        query = (
            select(
                InventarioSucursal.sucursal_id,
                Sucursal.nombre.label("sucursal_nombre"),
                Ciudad.nombre.label("ciudad_nombre"),
                func.sum(existencia_total_expr).label("total_unidades"),
                func.sum(InventarioSucursal.disponible).label("total_disponible"),
                func.sum(InventarioSucursal.reservado).label("total_reservado"),
                func.sum(InventarioSucursal.comprometido_traslado).label("total_comprometido"),
                func.sum(InventarioSucursal.en_transito).label("total_en_transito"),
                func.sum(valorizacion_expr).label("valorizacion"),
                func.sum(margen_expr).label("margen_bruto_total"),
            )
            .join(VarianteProducto, VarianteProducto.id == InventarioSucursal.variante_id)
            .join(Sucursal, Sucursal.id == InventarioSucursal.sucursal_id)
            .join(Ciudad, Ciudad.id == Sucursal.ciudad_id)
            .group_by(InventarioSucursal.sucursal_id, Sucursal.nombre, Ciudad.nombre)
            .order_by(Sucursal.nombre)
        )
        if sucursal_id:
            query = query.where(InventarioSucursal.sucursal_id == sucursal_id)
        if empresa_id:
            query = query.where(Sucursal.empresa_id == empresa_id)

        result = await self.db.execute(query)
        rows = result.all()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "sucursal_id": r.sucursal_id,
                "sucursal_nombre": r.sucursal_nombre,
                "ciudad_nombre": r.ciudad_nombre,
                "total_unidades": int(r.total_unidades or 0),
                "total_disponible": int(r.total_disponible or 0),
                "total_reservado": int(r.total_reservado or 0),
                "total_comprometido": int(r.total_comprometido or 0),
                "total_en_transito": int(r.total_en_transito or 0),
                "valorizacion": float(round(r.valorizacion or 0, 2)),
                "margen_bruto_total": float(round(r.margen_bruto_total or 0, 2)),
            })
        return out

    async def valorizacionGlobal(self, empresa_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        por_sucursal = await self.valorizacionPorSucursal(empresa_id=empresa_id)
        total_unidades = sum(s["total_unidades"] for s in por_sucursal)
        total_val = sum(s["valorizacion"] for s in por_sucursal)
        total_margen = sum(s["margen_bruto_total"] for s in por_sucursal)
        return {
            "por_sucursal": por_sucursal,
            "global": {
                "total_unidades": total_unidades,
                "valorizacion": round(total_val, 2),
                "margen_bruto_total": round(total_margen, 2),
                "sucursales": len(por_sucursal),
            }
        }
