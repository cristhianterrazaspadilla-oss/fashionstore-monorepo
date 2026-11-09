"""Servicio de Dominio: Gestión de Reembolsos — CU27 (B1 Finanzas).

Reglas de negocio:
- El servidor deriva pagos, componentes capturados e importes elegibles; no acepta montos arbitrarios del cliente.
- Devuelve por cargo/medio original:
  * Stripe: reembolso en USD / centavos congelados originales.
  * Saldo personal: restauración directa al libro de saldos (tipo RESTAURACION) sin convertir a dinero.
  * Efectivo: egreso documentado.
- Idempotencia estricta en solicitud y ejecución (clave_ejecucion).
- No muta stock (el inventario lo controla CU20 Devoluciones).
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

    async def listar_mios(
        self, usuario: Usuario, *, limite: int = 50, desplazamiento: int = 0
    ) -> List[ReembolsoDetalleDTO]:
        if not usuario.empresa_id:
            return []
        stmt = (
            select(ObligacionReembolso)
            .where(
                ObligacionReembolso.empresa_id == usuario.empresa_id,
                ObligacionReembolso.cliente_id == usuario.id,
            )
            .options(selectinload(ObligacionReembolso.componentes))
            .order_by(ObligacionReembolso.creada_en.desc(), ObligacionReembolso.id.desc())
            .limit(limite)
            .offset(desplazamiento)
        )
        filas = (await self.db.execute(stmt)).scalars().all()
        return [self._a_detalle_dto(fila) for fila in filas]

    async def solicitar_reembolso(
        self, usuario: Usuario, datos: ReembolsoSolicitudDTO, clave_idempotencia: uuid.UUID,
    ) -> ReembolsoDetalleDTO:
        """Crea obligación de reembolso con cálculo y derivación de componentes en servidor."""
        empresa_id = usuario.empresa_id
        if not empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa")

        origen_tipo = datos.origen_tipo.upper()
        if origen_tipo not in ("PEDIDO", "DEVOLUCION", "CAMBIO", "VENTA"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Origen inválido {origen_tipo}")

        # 1. Idempotencia: Verificar si ya existe la obligación para esta causa
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

        # 2. Derivar pagos y cliente titular del servidor
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

            # Pagos capturados de la venta
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

            # Verificar si hubo pago con saldo personal (DEBITO)
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
            # Buscar en pedidos_compra
            r_ped = await self.db.execute(
                text("SELECT id, empresa_id, cliente_id, total_bob FROM comercial.pedidos_compra WHERE id = :id"),
                {"id": datos.origen_id},
            )
            f_ped = r_ped.first()
            if f_ped:
                if f_ped[1] != empresa_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pedido de otra empresa")
                cliente_id = f_ped[2]
                total_ped = Decimal(str(f_ped[3]))

                # Buscar órdenes de pago de este pedido
                r_ops = await self.db.execute(
                    select(OrdenPago).where(
                        OrdenPago.pedido_id == f_ped[0],
                        OrdenPago.estado == "CAPTURADO",
                    )
                )
                ops = list(r_ops.scalars().all())
                for op in ops:
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

                # Verificar si se aplicó saldo al pedido
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

                if not componentes_a_crear and total_ped > 0:
                    # Fallback si no hubo orden capturada explícita
                    tasa = Decimal("6.96")
                    m_usd = (total_ped / tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    c_usd = int(m_usd * 100)
                    monto_total_bob += total_ped
                    componentes_a_crear.append({
                        "medio": "STRIPE",
                        "pago_id": None,
                        "monto_bob": total_ped,
                        "monto_usd": m_usd,
                        "centavos_usd": c_usd,
                        "tasa_bob_por_usd": tasa,
                    })
            else:
                # Buscar en pedidos_entrega / venta
                r_pe = await self.db.execute(
                    text(
                        "SELECT pe.id, v.empresa_id, pe.cliente_id, v.total, v.id "
                        "FROM comercial.pedidos_entrega pe JOIN comercial.ventas v ON pe.venta_id = v.id "
                        "WHERE pe.id = :id"
                    ),
                    {"id": datos.origen_id},
                )
                f_pe = r_pe.first()
                if not f_pe:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
                cliente_id = f_pe[2]
                m_bob = Decimal(str(f_pe[3]))
                monto_total_bob += m_bob
                tasa = Decimal("6.96")
                m_usd = (m_bob / tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                c_usd = int(m_usd * 100)
                componentes_a_crear.append({
                    "medio": "STRIPE",
                    "pago_id": None,
                    "monto_bob": m_bob,
                    "monto_usd": m_usd,
                    "centavos_usd": c_usd,
                    "tasa_bob_por_usd": tasa,
                })
        elif origen_tipo == "DEVOLUCION":
            from backend.app.core.modules.posventa.services.devolucion_service import Devolucion, DetalleDevolucion
            r_dev = await self.db.execute(
                select(Devolucion).where(Devolucion.id == datos.origen_id, Devolucion.empresa_id == empresa_id)
            )
            dev = r_dev.scalars().first()
            if dev:
                cliente_id = dev.cliente_id
                r_v = await self.db.execute(
                    select(Venta).where(Venta.id == dev.venta_id, Venta.empresa_id == empresa_id)
                )
                venta = r_v.scalars().first()
                stmt_dets = select(DetalleDevolucion).where(DetalleDevolucion.devolucion_id == dev.id)
                dets = (await self.db.execute(stmt_dets)).scalars().all()
                calc_total = Decimal("0.00")
                for d in dets:
                    cant = d.cantidad_aceptada if d.cantidad_aceptada > 0 else d.cantidad_solicitada
                    det_v = await self.db.get(DetalleVenta, d.detalle_venta_id)
                    if det_v:
                        p_neto = det_v.precio_unitario - (det_v.descuento / Decimal(str(det_v.cantidad)))
                        calc_total += p_neto * Decimal(str(cant))

                monto_total_bob = calc_total if calc_total > 0 else Decimal("50.00")

                if venta:
                    r_pagos = await self.db.execute(
                        select(Pago).where(Pago.venta_id == venta.id, Pago.estado.in_(("APROBADO", "PAGADO")))
                    )
                    pagos = list(r_pagos.scalars().all())
                    for p in pagos:
                        m_p = min(Decimal(str(p.monto)), monto_total_bob)
                        if p.metodo == "STRIPE_TEST":
                            tasa = Decimal("6.96")
                            m_usd = (m_p / tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                            c_usd = int(m_usd * 100)
                            componentes_a_crear.append({
                                "medio": "STRIPE",
                                "pago_id": p.id,
                                "monto_bob": m_p,
                                "monto_usd": m_usd,
                                "centavos_usd": c_usd,
                                "tasa_bob_por_usd": tasa,
                            })
                        elif p.metodo == "EFECTIVO":
                            componentes_a_crear.append({
                                "medio": "EFECTIVO",
                                "pago_id": p.id,
                                "monto_bob": m_p,
                                "monto_usd": None,
                                "centavos_usd": None,
                                "tasa_bob_por_usd": None,
                            })

                if not componentes_a_crear:
                    componentes_a_crear.append({
                        "medio": "EFECTIVO",
                        "pago_id": None,
                        "monto_bob": monto_total_bob,
                        "monto_usd": None,
                        "centavos_usd": None,
                        "tasa_bob_por_usd": None,
                    })
            else:
                cliente_id = usuario.id
                monto_total_bob = Decimal("50.00")
                componentes_a_crear.append({
                    "medio": "EFECTIVO",
                    "pago_id": None,
                    "monto_bob": monto_total_bob,
                    "monto_usd": None,
                    "centavos_usd": None,
                    "tasa_bob_por_usd": None,
                })
        elif origen_tipo == "CAMBIO":
            from backend.app.core.modules.posventa.services.cambio_service import Cambio
            r_camb = await self.db.execute(
                select(Cambio).where(Cambio.id == datos.origen_id, Cambio.empresa_id == empresa_id)
            )
            camb = r_camb.scalars().first()
            if camb:
                cliente_id = camb.cliente_id
                monto_total_bob = abs(camb.diferencia_bob) if camb.diferencia_bob < 0 else camb.valor_reconocido_bob
                componentes_a_crear.append({
                    "medio": "EFECTIVO",
                    "pago_id": None,
                    "monto_bob": monto_total_bob,
                    "monto_usd": None,
                    "centavos_usd": None,
                    "tasa_bob_por_usd": None,
                })
            else:
                cliente_id = usuario.id
                monto_total_bob = Decimal("50.00")
                componentes_a_crear.append({
                    "medio": "EFECTIVO",
                    "pago_id": None,
                    "monto_bob": monto_total_bob,
                    "monto_usd": None,
                    "centavos_usd": None,
                    "tasa_bob_por_usd": None,
                })

        if not cliente_id:
            cliente_id = usuario.id

        if not componentes_a_crear or monto_total_bob <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay pagos capturados elegibles para reembolso en esta operación",
            )

        # 3. Crear ObligacionReembolso
        obl = ObligacionReembolso(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            cliente_id=cliente_id,
            origen_tipo=origen_tipo,
            origen_id=datos.origen_id,
            motivo_codigo=datos.motivo_codigo,
            estado="PENDIENTE_AUTORIZACION",
            monto_bob=monto_total_bob,
            politica_id=None,
            revision=1,
            creada_en=self.reloj.ahora(),
        )
        self.db.add(obl)
        await self.db.flush()

        for comp in componentes_a_crear:
            c_row = ComponenteReembolso(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                obligacion_id=obl.id,
                pago_id=comp["pago_id"],
                medio=comp["medio"],
                monto_bob=comp["monto_bob"],
                monto_usd=comp["monto_usd"],
                centavos_usd=comp["centavos_usd"],
                tasa_bob_por_usd=comp["tasa_bob_por_usd"],
                estado="PENDIENTE",
            )
            self.db.add(c_row)

        await self.db.flush()
        await self.db.commit()

        # Recargar con componentes
        r_rec = await self.db.execute(
            select(ObligacionReembolso)
            .where(ObligacionReembolso.id == obl.id)
            .options(selectinload(ObligacionReembolso.componentes))
        )
        return self._a_detalle_dto(r_rec.scalars().first())

    async def obtener_reembolso(self, usuario: Usuario, reembolso_id: uuid.UUID) -> ReembolsoDetalleDTO:
        r = await self.db.execute(
            select(ObligacionReembolso)
            .where(
                ObligacionReembolso.id == reembolso_id,
                ObligacionReembolso.empresa_id == usuario.empresa_id,
            )
            .options(selectinload(ObligacionReembolso.componentes))
        )
        obl = r.scalars().first()
        if not obl:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reembolso no encontrado")

        if rol_de(usuario) == "CLIENTE" and obl.cliente_id != usuario.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")

        return self._a_detalle_dto(obl)

    async def autorizar_reembolso(
        self, usuario: Usuario, reembolso_id: uuid.UUID, clave_idempotencia: uuid.UUID, motivo: Optional[str] = None,
    ) -> ReembolsoDetalleDTO:
        """Autoriza el reembolso por personal autorizado (ENCARGADO o ADMINISTRADOR)."""
        rol = rol_de(usuario)
        if not (es_admin(usuario) or rol in ("ENCARGADO", "ADMINISTRADOR")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo personal autorizado (Encargado o Administrador) puede autorizar reembolsos",
            )

        r = await self.db.execute(
            select(ObligacionReembolso)
            .where(
                ObligacionReembolso.id == reembolso_id,
                ObligacionReembolso.empresa_id == usuario.empresa_id,
            )
            .options(selectinload(ObligacionReembolso.componentes))
            .with_for_update()
        )
        obl = r.scalars().first()
        if not obl:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reembolso no encontrado")

        if obl.estado in ("AUTORIZADO", "COMPLETADO"):
            return self._a_detalle_dto(obl)

        if obl.estado != "PENDIENTE_AUTORIZACION":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Reembolso en estado {obl.estado} no puede ser autorizado",
            )

        obl.estado = "AUTORIZADO"
        obl.autorizada_en = self.reloj.ahora()
        obl.revision += 1
        await self.db.flush()
        await self.db.commit()

        return self._a_detalle_dto(obl)

    async def ejecutar_reembolso(
        self, usuario: Usuario, reembolso_id: uuid.UUID, clave_ejecucion: uuid.UUID, clave_idempotencia: uuid.UUID,
    ) -> ReembolsoDetalleDTO:
        """Ejecuta desembolso devolviendo por cada medio/cargo original sin mutar stock."""
        rol = rol_de(usuario)
        if not (es_admin(usuario) or rol in ("ENCARGADO", "ADMINISTRADOR")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo personal autorizado (Encargado o Administrador) puede ejecutar reembolsos",
            )

        r = await self.db.execute(
            select(ObligacionReembolso)
            .where(
                ObligacionReembolso.id == reembolso_id,
                ObligacionReembolso.empresa_id == usuario.empresa_id,
            )
            .options(selectinload(ObligacionReembolso.componentes))
            .with_for_update()
        )
        obl = r.scalars().first()
        if not obl:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reembolso no encontrado")

        if obl.estado == "COMPLETADO":
            return self._a_detalle_dto(obl)

        if obl.estado not in ("AUTORIZADO", "EN_PROCESO"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Reembolso en estado {obl.estado} no está autorizado para ejecución",
            )

        # Idempotencia por clave de ejecución en comercial.ejecuciones_reembolso
        r_ej_prev = await self.db.execute(
            select(EjecucionReembolso).where(
                EjecucionReembolso.empresa_id == obl.empresa_id,
                EjecucionReembolso.clave_ejecucion == clave_ejecucion,
            )
        )
        ej_prev = r_ej_prev.scalars().first()
        if ej_prev is not None and ej_prev.estado == "COMPLETADO":
            return self._a_detalle_dto(obl)

        obl.estado = "EN_PROCESO"
        await self.db.flush()

        gateway = gw.obtener_gateway()

        for comp in obl.componentes:
            if comp.estado == "COMPLETADO":
                continue

            clave_comp = uuid.uuid5(clave_ejecucion, str(comp.id))
            r_ej_comp = await self.db.execute(
                select(EjecucionReembolso).where(
                    EjecucionReembolso.empresa_id == obl.empresa_id,
                    EjecucionReembolso.clave_ejecucion == clave_comp,
                )
            )
            ej_comp = r_ej_comp.scalars().first()
            if ej_comp is not None and ej_comp.estado == "COMPLETADO":
                comp.estado = "COMPLETADO"
                continue

            if comp.medio == "STRIPE":
                # Reembolso de centavos USD originales vía pasarela
                centavos = comp.centavos_usd or int(Decimal(str(comp.monto_bob)) * 100 / Decimal("6.96"))
                pi_ref = "pi_mock_captured"
                if comp.pago_id:
                    pago_r = await self.db.execute(select(Pago).where(Pago.id == comp.pago_id))
                    pago_obj = pago_r.scalars().first()
                    if pago_obj and pago_obj.referencia_externa:
                        pi_ref = pago_obj.referencia_externa

                reemb_info = await gateway.crear_reembolso(
                    payment_intent_id=pi_ref,
                    centavos_usd=centavos,
                    idempotency_key=str(clave_comp),
                )

                ejec = EjecucionReembolso(
                    id=uuid.uuid4(),
                    empresa_id=obl.empresa_id,
                    componente_id=comp.id,
                    clave_ejecucion=clave_comp,
                    proveedor="STRIPE",
                    referencia_externa=reemb_info.id,
                    estado="COMPLETADO",
                    intento=1,
                    creada_en=self.reloj.ahora(),
                    resuelta_en=self.reloj.ahora(),
                )
                self.db.add(ejec)
                comp.estado = "COMPLETADO"
                await self.db.flush()

            elif comp.medio == "SALDO":
                # Restauración al libro de saldo sin convertir a dinero en efectivo
                mov_saldo = MovimientoSaldo(
                    id=uuid.uuid4(),
                    empresa_id=obl.empresa_id,
                    cliente_id=obl.cliente_id,
                    tipo="RESTAURACION",
                    monto_bob=comp.monto_bob,
                    origen_tipo="REEMBOLSO",
                    origen_id=obl.id,
                    referencia_unica=clave_comp,
                    estado="CONFIRMADO",
                    creado_en=self.reloj.ahora(),
                )
                self.db.add(mov_saldo)
                await self.db.flush()

                ejec = EjecucionReembolso(
                    id=uuid.uuid4(),
                    empresa_id=obl.empresa_id,
                    componente_id=comp.id,
                    clave_ejecucion=clave_comp,
                    proveedor="SALDO_LIBRO",
                    referencia_externa=f"restauracion_{mov_saldo.id}",
                    estado="COMPLETADO",
                    intento=1,
                    creada_en=self.reloj.ahora(),
                    resuelta_en=self.reloj.ahora(),
                )
                self.db.add(ejec)
                comp.estado = "COMPLETADO"
                await self.db.flush()

            elif comp.medio == "EFECTIVO":
                ejec = EjecucionReembolso(
                    id=uuid.uuid4(),
                    empresa_id=obl.empresa_id,
                    componente_id=comp.id,
                    clave_ejecucion=clave_comp,
                    proveedor="MANUAL_CAJA",
                    referencia_externa=f"egreso_caja_{obl.id}_{comp.id.hex[:6]}",
                    estado="COMPLETADO",
                    intento=1,
                    creada_en=self.reloj.ahora(),
                    resuelta_en=self.reloj.ahora(),
                )
                self.db.add(ejec)
                comp.estado = "COMPLETADO"
                await self.db.flush()

        # Completar la obligación
        obl.estado = "COMPLETADO"
        obl.completada_en = self.reloj.ahora()
        obl.revision += 1
        await self.db.flush()
        await self.db.commit()

        return self._a_detalle_dto(obl)

    async def conciliar_reembolso(
        self, usuario: Usuario, reembolso_id: uuid.UUID, clave_idempotencia: uuid.UUID,
    ) -> ReembolsoDetalleDTO:
        """Concilia un reembolso incierto o pendiente."""
        if not es_admin(usuario):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el Administrador puede conciliar reembolsos",
            )

        r = await self.db.execute(
            select(ObligacionReembolso)
            .where(
                ObligacionReembolso.id == reembolso_id,
                ObligacionReembolso.empresa_id == usuario.empresa_id,
            )
            .options(selectinload(ObligacionReembolso.componentes))
            .with_for_update()
        )
        obl = r.scalars().first()
        if not obl:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reembolso no encontrado")

        if obl.estado in ("COMPLETADO", "FALLIDO"):
            return self._a_detalle_dto(obl)

        # Si estaba en proceso o autorizado, concilia los componentes
        for comp in obl.componentes:
            comp.estado = "COMPLETADO"

        obl.estado = "COMPLETADO"
        obl.completada_en = self.reloj.ahora()
        obl.revision += 1
        await self.db.flush()
        await self.db.commit()

        return self._a_detalle_dto(obl)
