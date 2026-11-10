"""Controller DashboardService — CU23 (Dashboard e indicadores consolidados multitenant)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.permisos import es_admin, exigir_sucursal, rol_de
from backend.app.core.ambito_comercial import empresa_comercial, sucursal_autorizada
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto
from backend.app.core.modules.ventas_pagos.models import PedidoEntrega, DetalleVenta, Venta, Pago
from backend.app.core.modules.reservas_traslados.models import Reserva
from backend.app.core.modules.inventario.models import InventarioSucursal
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.analitica.schemas import DashboardDTO


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.sucursal_repo = SucursalRepository(db)

    async def indicadores(
        self,
        usuario: Usuario,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        sucursal_id: Optional[uuid.UUID] = None,
    ) -> DashboardDTO:
        from backend.app.core.reloj import entrada_local_a_utc

        def _utc(dt: Optional[datetime]) -> Optional[datetime]:
            if dt is None:
                return None
            return entrada_local_a_utc(dt)

        empresa_id = empresa_comercial(usuario)
        desde = _utc(desde)
        hasta = _utc(hasta)
        if desde is not None and hasta is not None and desde > hasta:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rango inválido: desde debe ser <= hasta (UTC)",
            )
        rol = rol_de(usuario)
        if rol == "ENCARGADO":
            if sucursal_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Indique la sucursal de su ámbito",
                )
            exigir_sucursal(usuario, sucursal_id)
        elif not es_admin(usuario):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo Encargado o Administrador",
            )
        if sucursal_id is not None:
            sucursal = await sucursal_autorizada(self.db, usuario, sucursal_id)
            if sucursal is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")

        base = select(Venta).where(
            Venta.empresa_id == empresa_id,
            Venta.estado.in_(["PAGADA", "PARCIALMENTE_DEVUELTA", "DEVUELTA"]),
        )
        if desde is not None:
            base = base.where(Venta.creada_en >= desde)
        if hasta is not None:
            base = base.where(Venta.creada_en <= hasta)
        if sucursal_id is not None:
            base = base.where(Venta.sucursal_id == sucursal_id)
        ventas = list((await self.db.execute(base)).scalars().all())

        ingresos = sum((Decimal(str(v.total or 0)) for v in ventas), Decimal("0"))
        subtotal_bruto = sum((Decimal(str(v.subtotal or v.total or 0)) for v in ventas), Decimal("0"))
        total_descuentos = sum((Decimal(str(v.descuento or 0)) for v in ventas), Decimal("0"))
        n = len(ventas)
        ticket = (ingresos / n).quantize(Decimal("0.01")) if n else Decimal("0.00")

        margen = Decimal("0")
        if ventas:
            ids = [v.id for v in ventas]
            dets = (await self.db.execute(
                select(DetalleVenta).where(DetalleVenta.venta_id.in_(ids))
            )).scalars().all()
            for d in dets:
                linea_total = Decimal(str(d.precio_unitario or 0)) * d.cantidad - Decimal(str(d.descuento or 0))
                margen += linea_total - Decimal(str(d.costo_promedio or 0)) * d.cantidad

        por_sucursal = []
        if ventas:
            agg = (await self.db.execute(
                select(Venta.sucursal_id, func.count(Venta.id), func.coalesce(func.sum(Venta.total), 0))
                .where(Venta.id.in_([v.id for v in ventas]))
                .group_by(Venta.sucursal_id)
            )).all()
            for sid, c, t in agg:
                suc = await self.sucursal_repo.buscarPorId(sid)
                por_sucursal.append({
                    "sucursal_id": str(sid),
                    "sucursal_nombre": suc.nombre if suc else "?",
                    "ventas": int(c),
                    "ingresos": str(t),
                })
            por_sucursal.sort(key=lambda x: x["sucursal_nombre"])

        top = []
        if ventas:
            filas = (await self.db.execute(
                select(Producto.nombre, func.sum(DetalleVenta.cantidad))
                .join(VarianteProducto, VarianteProducto.producto_id == Producto.id)
                .join(DetalleVenta, DetalleVenta.variante_id == VarianteProducto.id)
                .where(DetalleVenta.venta_id.in_([v.id for v in ventas]))
                .where(Producto.empresa_id == empresa_id, VarianteProducto.empresa_id == empresa_id)
                .group_by(Producto.id, Producto.nombre)
                .order_by(func.sum(DetalleVenta.cantidad).desc())
                .limit(10)
            )).all()
            top = [{"producto": nombre, "unidades": int(uds)} for nombre, uds in filas]

        inv_q = select(InventarioSucursal, VarianteProducto.sku).join(
            VarianteProducto, VarianteProducto.id == InventarioSucursal.variante_id
        ).join(Sucursal, Sucursal.id == InventarioSucursal.sucursal_id).where(
            Sucursal.empresa_id == empresa_id, VarianteProducto.empresa_id == empresa_id
        )
        if sucursal_id is not None:
            inv_q = inv_q.where(InventarioSucursal.sucursal_id == sucursal_id)
        inv = (await self.db.execute(inv_q)).all()
        critico, valorizacion = [], Decimal("0")
        for fila, sku in inv:
            existencia = (fila.disponible + fila.reservado + fila.comprometido_traslado + fila.en_transito
                          + fila.comprometido_caja + fila.comprometido_digital + fila.comprometido_cambio)
            variante = await self.db.get(VarianteProducto, fila.variante_id)
            costo = Decimal(str(variante.costo_promedio or 0)) if variante else Decimal("0")
            valorizacion += existencia * costo
            if fila.disponible <= 5:
                critico.append({
                    "sku": sku,
                    "sucursal_id": str(fila.sucursal_id),
                    "disponible": fila.disponible,
                    "existencia": existencia,
                })
        critico.sort(key=lambda x: x["disponible"])

        res_q = select(func.count()).select_from(Reserva)
        comp_q = select(func.count()).select_from(Reserva).where(Reserva.estado == "COMPLETADA")
        res_q = res_q.where(Reserva.empresa_id == empresa_id)
        comp_q = comp_q.where(Reserva.empresa_id == empresa_id)
        if desde is not None:
            res_q = res_q.where(Reserva.fecha_creacion >= desde)
            comp_q = comp_q.where(Reserva.fecha_creacion >= desde)
        if hasta is not None:
            res_q = res_q.where(Reserva.fecha_creacion <= hasta)
            comp_q = comp_q.where(Reserva.fecha_creacion <= hasta)
        if sucursal_id is not None:
            res_q = res_q.where(Reserva.sucursal_destino_id == sucursal_id)
            comp_q = comp_q.where(Reserva.sucursal_destino_id == sucursal_id)
        total_res = int((await self.db.execute(res_q)).scalar() or 0)
        comp_res = int((await self.db.execute(comp_q)).scalar() or 0)

        ped_q = select(PedidoEntrega.estado, func.count()).where(
            PedidoEntrega.empresa_id == empresa_id
        ).group_by(PedidoEntrega.estado)
        if desde is not None:
            ped_q = ped_q.where(PedidoEntrega.creada_en >= desde)
        if hasta is not None:
            ped_q = ped_q.where(PedidoEntrega.creada_en <= hasta)
        if sucursal_id is not None:
            ped_q = ped_q.where(PedidoEntrega.sucursal_id == sucursal_id)
        estados = {e: int(c) for e, c in (await self.db.execute(ped_q)).all()}

        con_promo = sin_promo = 0
        dto_promo = Decimal("0")
        for v in ventas:
            dets = (await self.db.execute(
                select(DetalleVenta).where(DetalleVenta.venta_id == v.id)
            )).scalars().all()
            tiene = any(d.promocion_id is not None for d in dets)
            if tiene:
                con_promo += 1
                dto_promo += sum((Decimal(str(d.descuento or 0)) for d in dets), Decimal("0"))
            else:
                sin_promo += 1

        # Dinero capturado (Pagos confirmados / APROBADO)
        pago_q = select(func.coalesce(func.sum(Pago.monto), 0)).where(Pago.estado.in_(["APROBADO", "PAGADO"]))
        pago_q = pago_q.where(Pago.empresa_id == empresa_id)
        if desde is not None:
            pago_q = pago_q.where(Pago.pagado_en >= desde)
        if hasta is not None:
            pago_q = pago_q.where(Pago.pagado_en <= hasta)
        if sucursal_id is not None:
            pago_q = pago_q.join(Venta, Pago.venta_id == Venta.id).where(Venta.sucursal_id == sucursal_id)
        dinero_capturado = Decimal(str((await self.db.execute(pago_q)).scalar() or 0))

        # Devoluciones y Reembolsos para métricas consistentes
        total_devoluciones = Decimal("0.00")
        total_reembolsos = Decimal("0.00")
        if ventas:
            ids = [v.id for v in ventas]
            try:
                from backend.app.core.modules.posventa.services.devolucion_service import Devolucion, DetalleDevolucion
                dev_q = (
                    select(
                        func.coalesce(
                            func.sum(
                                DetalleDevolucion.cantidad_aceptada * (
                                    DetalleVenta.precio_unitario - (DetalleVenta.descuento / func.nullif(DetalleVenta.cantidad, 0))
                                )
                            ),
                            0,
                        )
                    )
                    .join(DetalleVenta, DetalleVenta.id == DetalleDevolucion.detalle_venta_id)
                    .join(Devolucion, Devolucion.id == DetalleDevolucion.devolucion_id)
                    .where(
                        Devolucion.venta_id.in_(ids),
                        Devolucion.empresa_id == empresa_id,
                        DetalleDevolucion.empresa_id == empresa_id,
                        Devolucion.estado != "RECHAZADA",
                        DetalleDevolucion.cantidad_aceptada > 0,
                    )
                )
                total_devoluciones = Decimal(str((await self.db.execute(dev_q)).scalar() or 0)).quantize(Decimal("0.01"))
            except Exception:
                raise

            try:
                from backend.app.core.modules.posventa.models import ObligacionReembolso
                from backend.app.core.modules.posventa.services.cambio_service import Cambio
                reemb_q = select(func.coalesce(func.sum(ObligacionReembolso.monto_bob), 0)).where(
                    ObligacionReembolso.empresa_id == empresa_id,
                    or_(
                        (ObligacionReembolso.origen_tipo == "VENTA") & ObligacionReembolso.origen_id.in_(ids),
                        (ObligacionReembolso.origen_tipo == "DEVOLUCION") & ObligacionReembolso.origen_id.in_(
                            select(Devolucion.id).where(Devolucion.empresa_id == empresa_id, Devolucion.venta_id.in_(ids))
                        ),
                        (ObligacionReembolso.origen_tipo == "CAMBIO") & ObligacionReembolso.origen_id.in_(
                            select(Cambio.id).where(Cambio.empresa_id == empresa_id, Cambio.venta_id.in_(ids))
                        ),
                    ),
                    ObligacionReembolso.estado.in_(("COMPLETADO", "COMPLETADA")),
                )
                total_reembolsos = Decimal(str((await self.db.execute(reemb_q)).scalar() or 0)).quantize(Decimal("0.01"))
            except Exception:
                raise

        neto_comercial = max(Decimal("0.00"), subtotal_bruto - total_descuentos - total_devoluciones)

        # Pedidos pendientes de cumplimiento
        ped_pend_q = select(func.count(PedidoEntrega.id), func.coalesce(func.sum(PedidoEntrega.costo_entrega), 0)).where(
            PedidoEntrega.empresa_id == empresa_id,
            PedidoEntrega.estado.in_(["SOLICITADO", "PREPARADO", "LISTO_RECOJO", "EN_REPARTO"])
        )
        if desde is not None:
            ped_pend_q = ped_pend_q.where(PedidoEntrega.creada_en >= desde)
        if hasta is not None:
            ped_pend_q = ped_pend_q.where(PedidoEntrega.creada_en <= hasta)
        if sucursal_id is not None:
            ped_pend_q = ped_pend_q.where(PedidoEntrega.sucursal_id == sucursal_id)
        ped_pend_row = (await self.db.execute(ped_pend_q)).one()
        ped_pend_count = int(ped_pend_row[0] or 0)
        ped_pend_monto = Decimal(str(ped_pend_row[1] or 0))

        return DashboardDTO(
            desde=desde,
            hasta=hasta,
            ventas_total=n,
            ingresos_total=ingresos,
            margen_bruto_total=margen,
            ticket_promedio=ticket,
            ventas_brutas=subtotal_bruto,
            descuentos=total_descuentos,
            devoluciones=total_devoluciones,
            reembolsos=total_reembolsos,
            neto_comercial=neto_comercial,
            dinero_capturado=dinero_capturado,
            pedidos_pendientes_cumplimiento=ped_pend_count,
            monto_pedidos_pendientes=ped_pend_monto,
            por_sucursal=por_sucursal,
            top_productos=top,
            stock_critico=critico[:50],
            valorizacion_total=valorizacion,
            conversion_reservas={
                "total": total_res,
                "completadas": comp_res,
                "tasa": round(comp_res / total_res, 4) if total_res else 0.0,
            },
            estados_pedidos=estados,
            efectividad_promociones={
                "con_promocion": con_promo,
                "sin_promocion": sin_promo,
                "descuento_total": str(dto_promo),
            },
        )
