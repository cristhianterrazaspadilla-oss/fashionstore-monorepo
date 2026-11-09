"""Controller ReporteService — CU25 (Ventas por Sucursal con fecha central y física Bolivia)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from backend.app.core.ambito_comercial import empresa_comercial, sucursal_autorizada
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.permisos import es_admin, exigir_sucursal
from backend.app.core.reloj import a_hora_bolivia, entrada_local_a_utc
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.ventas_pagos.repositories.venta_repository import VentaRepository
from backend.app.core.modules.analitica.schemas import (
    VentaSucursalItemDTO,
    VentasSucursalDTO,
    VentasSucursalResumenDTO,
)


class ReporteService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.venta_repo = VentaRepository(db)
        self.sucursal_repo = SucursalRepository(db)

    async def ventasPorSucursal(
        self,
        usuario: Usuario,
        sucursal_id: uuid.UUID,
        desde: Optional[datetime] = None,
        hasta: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> VentasSucursalDTO:
        empresa_id = empresa_comercial(usuario)
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "ENCARGADO":
            exigir_sucursal(usuario, sucursal_id)
        elif not es_admin(usuario):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Encargado o Administrador")
        sucursal = await sucursal_autorizada(self.db, usuario, sucursal_id)
        if sucursal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")
        con_costos = rol in ("ADMINISTRADOR", "ENCARGADO")
        desde = entrada_local_a_utc(desde) if desde is not None else None
        hasta = entrada_local_a_utc(hasta) if hasta is not None else None
        ventas, total = await self.venta_repo.porSucursal(
            sucursal_id, desde=desde, hasta=hasta, limit=limit, offset=offset, empresa_id=empresa_id
        )
        items = []
        unidades = 0
        monto = Decimal("0")
        subtotal_bruto = Decimal("0")
        total_descuentos = Decimal("0")
        costo = Decimal("0")
        for v in ventas:
            uds = sum(d.cantidad for d in v.detalles)
            cto = sum(Decimal(str(d.costo_promedio or 0)) * d.cantidad for d in v.detalles)
            unidades += uds
            monto += Decimal(str(v.total or 0))
            subtotal_bruto += Decimal(str(v.subtotal or v.total or 0))
            total_descuentos += Decimal(str(v.descuento or 0))
            costo += cto
            fecha_central = getattr(v, "recibida_central_en", None) or v.creada_en
            fecha_local = getattr(v, "vendida_local_en", None) or v.creada_en
            items.append(
                VentaSucursalItemDTO(
                    id=v.id,
                    numero=v.numero,
                    creada_en=v.creada_en,
                    fecha_central=fecha_central,
                    fecha_fisica_local=a_hora_bolivia(fecha_local),
                    cliente_id=v.cliente_id,
                    reserva_id=v.reserva_id,
                    canal=v.canal if isinstance(v.canal, str) else str(v.canal),
                    estado=v.estado if isinstance(v.estado, str) else v.estado.name,
                    unidades=uds,
                    subtotal=v.subtotal,
                    descuento=v.descuento,
                    adelanto_descontado=v.adelanto_descontado,
                    total=v.total,
                    costo_total=cto if con_costos else None,
                    margen_bruto=(Decimal(str(v.total or 0)) - cto) if con_costos else None,
                )
            )

        total_devoluciones = Decimal("0.00")
        total_reembolsos = Decimal("0.00")
        if ventas:
            v_ids = [v.id for v in ventas]
            try:
                from backend.app.core.modules.posventa.services.devolucion_service import Devolucion, DetalleDevolucion
                from backend.app.core.modules.ventas_pagos.models import DetalleVenta
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
                        Devolucion.venta_id.in_(v_ids),
                        Devolucion.empresa_id == empresa_id,
                        Devolucion.estado != "RECHAZADA",
                        DetalleDevolucion.cantidad_aceptada > 0,
                    )
                )
                total_devoluciones = Decimal(str((await self.db.execute(dev_q)).scalar() or 0)).quantize(Decimal("0.01"))
            except Exception:
                total_devoluciones = Decimal("0.00")

            try:
                from backend.app.core.modules.posventa.models import ObligacionReembolso
                reemb_q = select(func.coalesce(func.sum(ObligacionReembolso.monto_bob), 0)).where(
                    ObligacionReembolso.empresa_id == empresa_id,
                    ObligacionReembolso.origen_id.in_(v_ids),
                    ObligacionReembolso.estado.in_(["AUTORIZADA", "COMPLETADA"]),
                )
                total_reembolsos = Decimal(str((await self.db.execute(reemb_q)).scalar() or 0)).quantize(Decimal("0.01"))
            except Exception:
                total_reembolsos = Decimal("0.00")

        neto_comercial = max(Decimal("0.00"), subtotal_bruto - total_descuentos - total_devoluciones)
        resumen = VentasSucursalResumenDTO(
            total_ventas=total,
            unidades=unidades,
            monto_total=monto,
            ticket_promedio=(monto / total).quantize(Decimal("0.01")) if total else Decimal("0.00"),
            costo_total=costo if con_costos else None,
            margen_bruto_total=(monto - costo) if con_costos else None,
            ventas_brutas=subtotal_bruto,
            total_descuentos=total_descuentos,
            total_devoluciones=total_devoluciones,
            total_reembolsos=total_reembolsos,
            neto_comercial=neto_comercial,
        )
        return VentasSucursalDTO(total=total, limit=limit, offset=offset, resumen=resumen, items=items)
