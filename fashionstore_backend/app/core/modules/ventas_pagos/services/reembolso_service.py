"""Servicio de Reembolso para Ventas y Pagos — CU27.

Garantiza que cualquier obligación o solicitud de reembolso opere
EXCLUSIVAMENTE sobre fondos efectivamente capturados (CAPTURADO, APROBADO o PAGADO),
sin inventar componentes de pago no verificados en pasarela ni en saldo personal.
"""
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.posventa.models import (
    ComponenteReembolso,
    EjecucionReembolso,
    MovimientoSaldo,
    ObligacionReembolso,
)
from backend.app.core.modules.posventa.schemas import (
    ComponenteReembolsoDTO,
    EjecucionReembolsoDTO,
    ReembolsoDetalleDTO,
    ReembolsoSolicitudDTO,
)
from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
from backend.app.core.modules.ventas_pagos.models import Pago, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import OrdenPago
from backend.app.core.permisos import es_admin, rol_de
from backend.app.core.reloj import RelojSistema


class ReembolsoService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()

    def _a_detalle_dto(self, obl: ObligacionReembolso) -> ReembolsoDetalleDTO:
        comps_dto: List[ComponenteReembolsoDTO] = []
        for c in (obl.componentes or []):
            comps_dto.append(
                ComponenteReembolsoDTO(
                    id=c.id,
                    medio=c.medio,
                    monto_bob=Decimal(str(c.monto_bob)),
                    monto_usd=Decimal(str(c.monto_usd)) if c.monto_usd is not None else None,
                    centavos_usd=c.centavos_usd,
                    tasa_bob_por_usd=Decimal(str(c.tasa_bob_por_usd)) if c.tasa_bob_por_usd is not None else None,
                    estado=c.estado,
                    pago_id=c.pago_id,
                )
            )
        return ReembolsoDetalleDTO(
            id=obl.id,
            empresa_id=obl.empresa_id,
            cliente_id=obl.cliente_id,
            origen_tipo=obl.origen_tipo,
            origen_id=obl.origen_id,
            motivo_codigo=obl.motivo_codigo,
            estado=obl.estado,
            monto_bob=Decimal(str(obl.monto_bob)),
            revision=obl.revision,
            creada_en=obl.creada_en,
            autorizada_en=obl.autorizada_en,
            completada_en=obl.completada_en,
            componentes=comps_dto,
        )

    async def solicitar_reembolso(
        self, usuario: Usuario, datos: ReembolsoSolicitudDTO, clave_idempotencia: uuid.UUID,
    ) -> ReembolsoDetalleDTO:
        """Crea obligación de reembolso con cálculo y derivación de componentes en servidor únicamente sobre dinero capturado."""
        empresa_id = usuario.empresa_id
        if not empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa")

        origen_tipo = datos.origen_tipo.upper()
        if origen_tipo not in ("PEDIDO", "DEVOLUCION", "CAMBIO", "VENTA"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Origen inválido {origen_tipo}")

        # Idempotencia
        r_ex = await self.db.execute(
            select(ObligacionReembolso)
            .where(
                ObligacionReembolso.empresa_id == empresa_id,
                ObligacionReembolso.origen_tipo == origen_tipo,
                ObligacionReembolso.origen_id == datos.origen_id,
                ObligacionReembolso.motivo_codigo == datos.motivo_codigo,
            )
            .options(selectinload(ObligacionReembolso.componentes))
        )
        obl_existente = r_ex.scalars().first()
        if obl_existente is not None:
            return self._a_detalle_dto(obl_existente)

        cliente_id: Optional[uuid.UUID] = None
        componentes_a_crear = []
        monto_total_bob = Decimal("0.00")

        if origen_tipo == "VENTA":
            r_v = await self.db.execute(
                select(Venta).where(Venta.id == datos.origen_id, Venta.empresa_id == empresa_id)
            )
            venta = r_v.scalars().first()
            if not venta:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada")
            cliente_id = venta.cliente_id or usuario.id

            # Solo pagos aprobados/pagados (dinero efectivamente capturado)
            r_pagos = await self.db.execute(
                select(Pago).where(Pago.venta_id == venta.id, Pago.estado.in_(("APROBADO", "PAGADO")))
            )
            pagos = list(r_pagos.scalars().all())

            for p in pagos:
                monto_p = Decimal(str(p.monto))
                monto_total_bob += monto_p
                if p.metodo == "STRIPE_TEST":
                    tasa = Decimal("6.96")
                    m_usd = (monto_p / tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    c_usd = int(m_usd * 100)
                    componentes_a_crear.append({
                        "medio": "STRIPE",
                        "pago_id": p.id,
                        "monto_bob": monto_p,
                        "monto_usd": m_usd,
                        "centavos_usd": c_usd,
                        "tasa_bob_por_usd": tasa,
                    })
                elif p.metodo == "EFECTIVO":
                    componentes_a_crear.append({
                        "medio": "EFECTIVO",
                        "pago_id": p.id,
                        "monto_bob": monto_p,
                        "monto_usd": None,
                        "centavos_usd": None,
                        "tasa_bob_por_usd": None,
                    })

            # Movimiento de saldo capturado (DEBITO)
            r_saldo = await self.db.execute(
                select(MovimientoSaldo).where(
                    MovimientoSaldo.empresa_id == empresa_id,
                    MovimientoSaldo.origen_tipo == "VENTA",
                    MovimientoSaldo.origen_id == venta.id,
                    MovimientoSaldo.tipo == "DEBITO",
                )
            )
            for sm in r_saldo.scalars().all():
                m_bob = Decimal(str(sm.monto_bob))
                monto_total_bob += m_bob
                componentes_a_crear.append({
                    "medio": "SALDO",
                    "pago_id": None,
                    "monto_bob": m_bob,
                    "monto_usd": None,
                    "centavos_usd": None,
                    "tasa_bob_por_usd": None,
                })

        elif origen_tipo == "PEDIDO":
            r_ped = await self.db.execute(
                text("SELECT id, empresa_id, cliente_id, total_bob FROM comercial.pedidos_compra WHERE id = :id"),
                {"id": datos.origen_id},
            )
            f_ped = r_ped.first()
            if f_ped:
                if f_ped[1] != empresa_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pedido de otra empresa")
                cliente_id = f_ped[2]

                # Órdenes de pago efectivamente capturadas
                r_ops = await self.db.execute(
                    select(OrdenPago).where(
                        OrdenPago.pedido_id == f_ped[0],
                        OrdenPago.estado == "CAPTURADO",
                    )
                )
                for op in r_ops.scalars().all():
                    m_bob = Decimal(str(op.monto_bob))
                    monto_total_bob += m_bob
                    componentes_a_crear.append({
                        "medio": "STRIPE",
                        "pago_id": None,
                        "monto_bob": m_bob,
                        "monto_usd": Decimal(str(op.monto_usd)) if op.monto_usd else None,
                        "centavos_usd": op.centavos_usd,
                        "tasa_bob_por_usd": Decimal("6.96"),
                    })

                # Saldo aplicado efectivamente
                r_s_ped = await self.db.execute(
                    select(MovimientoSaldo).where(
                        MovimientoSaldo.empresa_id == empresa_id,
                        MovimientoSaldo.origen_tipo == "PEDIDO",
                        MovimientoSaldo.origen_id == f_ped[0],
                        MovimientoSaldo.tipo.in_(("RETENCION", "DEBITO")),
                    )
                )
                for sm in r_s_ped.scalars().all():
                    m_bob = Decimal(str(sm.monto_bob))
                    monto_total_bob += m_bob
                    componentes_a_crear.append({
                        "medio": "SALDO",
                        "pago_id": None,
                        "monto_bob": m_bob,
                        "monto_usd": None,
                        "centavos_usd": None,
                        "tasa_bob_por_usd": None,
                    })

        # Regla: Reembolso SOLO sobre dinero capturado
        if not componentes_a_crear or monto_total_bob <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "codigo": "SIN_FONDOS_CAPTURADOS",
                    "mensaje": "No existen pagos o fondos capturados para derivar reembolso",
                },
            )

        obl = ObligacionReembolso(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            cliente_id=cliente_id or usuario.id,
            origen_tipo=origen_tipo,
            origen_id=datos.origen_id,
            motivo_codigo=datos.motivo_codigo,
            estado="PENDIENTE_AUTORIZACION",
            monto_bob=monto_total_bob,
            revision=1,
            creada_en=self.reloj.ahora(),
        )
        self.db.add(obl)
        await self.db.flush()

        for c_dict in componentes_a_crear:
            comp = ComponenteReembolso(
                id=uuid.uuid4(),
                obligacion_id=obl.id,
                empresa_id=empresa_id,
                medio=c_dict["medio"],
                pago_id=c_dict["pago_id"],
                monto_bob=c_dict["monto_bob"],
                monto_usd=c_dict["monto_usd"],
                centavos_usd=c_dict["centavos_usd"],
                tasa_bob_por_usd=c_dict["tasa_bob_por_usd"],
                estado="PENDIENTE",
            )
            self.db.add(comp)

        await self.db.flush()
        await self.db.commit()

        # Recargar con componentes
        r_rec = await self.db.execute(
            select(ObligacionReembolso)
            .where(ObligacionReembolso.id == obl.id)
            .options(selectinload(ObligacionReembolso.componentes))
        )
        return self._a_detalle_dto(r_rec.scalars().first())
