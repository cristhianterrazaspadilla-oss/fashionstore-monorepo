"""Servicio de Venta Presencial Conectada en Caja — CU19.

Liquida pagos en EFECTIVO, SALDO o STRIPE_TEST, bloquea stock de forma atómica
y emite Kardex VENTA_PRESENCIAL único por ítem con emisión de comprobante.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.idempotencia import hash_payload, resolver_idempotencia
from backend.app.core.modules.catalogo.models import VarianteProducto
from backend.app.core.modules.catalogo.services.promocion_service import PromocionService
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.inventario.models import CupoCaja, InventarioSucursal, MovimientoInventario
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.organizacion.models import Sucursal, TasaCambio
from backend.app.core.modules.posventa.services.saldo_service import SaldoService
from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, TurnoCaja, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import OrdenPago
from backend.app.core.modules.ventas_pagos.services.pedido_service import Comprobante
from backend.app.core.permisos import es_admin, exigir_sucursal
from backend.app.core.reloj import RelojSistema

NUMERO_ALFABETO = string.ascii_uppercase + string.digits


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# DTOs PYDANTIC
# ============================================================================

class LineaVentaPresencialDTO(BaseModel):
    variante_id: uuid.UUID
    cantidad: int = Field(gt=0, description="Cantidad mayor a cero")
    precio_unitario_bob: Optional[Decimal] = None
    descuento_bob: Optional[Decimal] = Field(default=Decimal("0.00"))


class VentaPresencialIniciarStripeDTO(BaseModel):
    sucursal_id: uuid.UUID
    lineas: List[LineaVentaPresencialDTO] = Field(min_length=1, description="Al menos un ítem a vender")
    cliente_id: Optional[uuid.UUID] = None
    turno_caja_id: Optional[uuid.UUID] = None


class VentaPresencialStripeIniciadaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    venta_id: uuid.UUID
    orden_pago_id: uuid.UUID
    stripe_payment_intent_id: str
    client_secret: Optional[str] = None
    monto_bob: Decimal
    monto_usd: Decimal
    centavos_usd: int
    tasa_bob_por_usd: Decimal
    estado_orden: str = "PENDIENTE"


class VentaPresencialLiquidarDTO(BaseModel):
    venta_id: Optional[uuid.UUID] = None
    sucursal_id: uuid.UUID
    lineas: List[LineaVentaPresencialDTO] = Field(min_length=1, description="Al menos un ítem a vender")
    medio_pago: Literal["EFECTIVO", "SALDO", "STRIPE_TEST"]
    cliente_id: Optional[uuid.UUID] = None
    efectivo_recibido_bob: Optional[Decimal] = None
    saldo_aplicado_bob: Optional[Decimal] = None
    orden_pago_id: Optional[uuid.UUID] = None
    stripe_payment_intent_id: Optional[str] = None
    turno_caja_id: Optional[uuid.UUID] = None


class VentaLiquidadaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    venta_id: uuid.UUID
    numero: str
    total_bob: Decimal
    comprobante_id: uuid.UUID
    kardex_ids: List[uuid.UUID]
    cambio_entregado_bob: Decimal = Field(default=Decimal("0.00"))
    estado_pago: str = "PAGADA"
    estado_entrega: str = "ENTREGADA"
    fecha_hora: datetime


# ============================================================================
# SERVICIO VENTA PRESENCIAL
# ============================================================================

class VentaPresencialService:
    def __init__(self, db: AsyncSession, reloj=None, gateway=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self._gateway = gateway
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)

    @property
    def gateway(self):
        if self._gateway is not None:
            return self._gateway
        return gw.obtener_gateway()

    def _autorizar_caja(self, usuario: Usuario, sucursal_id: uuid.UUID) -> None:
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CAJERO":
            exigir_sucursal(usuario, sucursal_id)
            return
        if es_admin(usuario):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo Cajero asignado a la sucursal o Administrador pueden liquidar ventas presenciales",
        )

    async def _generar_numero_venta(self) -> str:
        for _ in range(5):
            num = "VTA-" + "".join(secrets.choice(NUMERO_ALFABETO) for _ in range(8))
            stmt = select(Venta.id).where(Venta.numero == num)
            if (await self.db.execute(stmt)).scalars().first() is None:
                return num
        raise HTTPException(status_code=500, detail="No se pudo generar un número de venta único")

    async def _construir_dto_iniciada(
        self, venta: Venta, ord_existente: OrdenPago
    ) -> VentaPresencialStripeIniciadaDTO:
        ref_pi = ord_existente.referencia_externa or ord_existente.clave_externa
        client_secret = None
        if ref_pi:
            try:
                intencion_real = await self.gateway.consultar_intencion(ref_pi)
                if intencion_real:
                    client_secret = intencion_real.client_secret
            except Exception:
                client_secret = None

        tasa_val: Optional[Decimal] = None
        if ord_existente.tasa_id:
            t_obj = await self.db.get(TasaCambio, ord_existente.tasa_id)
            if t_obj and t_obj.tasa_bob_por_usd:
                tasa_val = Decimal(str(t_obj.tasa_bob_por_usd))

        if tasa_val is None:
            if ord_existente.monto_usd and ord_existente.monto_usd > Decimal("0.00"):
                tasa_val = (Decimal(str(ord_existente.monto_bob)) / Decimal(str(ord_existente.monto_usd))).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
            else:
                stmt_tasa = (
                    select(TasaCambio)
                    .where(TasaCambio.vigente_hasta.is_(None))
                    .order_by(TasaCambio.vigente_desde.desc())
                )
                tasa_row = (await self.db.execute(stmt_tasa)).scalars().first()
                if tasa_row and tasa_row.tasa_bob_por_usd:
                    tasa_val = Decimal(str(tasa_row.tasa_bob_por_usd))
                else:
                    tasa_val = Decimal("1.00")

        return VentaPresencialStripeIniciadaDTO(
            venta_id=venta.id,
            orden_pago_id=ord_existente.id,
            stripe_payment_intent_id=ref_pi,
            client_secret=client_secret,
            monto_bob=Decimal(str(ord_existente.monto_bob)),
            monto_usd=Decimal(str(ord_existente.monto_usd)) if ord_existente.monto_usd is not None else Decimal("0.00"),
            centavos_usd=ord_existente.centavos_usd or 0,
            tasa_bob_por_usd=tasa_val,
            estado_orden=ord_existente.estado,
        )

    async def iniciar_stripe(
        self, usuario: Usuario, dto: VentaPresencialIniciarStripeDTO, clave: uuid.UUID
    ) -> VentaPresencialStripeIniciadaDTO:
        digest = hash_payload(dto.model_dump(mode="json"))

        # Idempotencia previa
        reintento = await resolver_idempotencia(self.db, Venta, clave, digest)
        if reintento is not None:
            stmt_ord = select(OrdenPago).where(OrdenPago.venta_id == reintento.id)
            ord_existente = (await self.db.execute(stmt_ord)).scalars().first()
            if ord_existente is not None:
                if ord_existente.clave_externa.startswith("PENDIENTE_"):
                    gateway = self.gateway
                    intencion = await gateway.crear_o_reutilizar_intencion(
                        venta_id=str(reintento.id),
                        monto_centavos=ord_existente.centavos_usd,
                        moneda="usd",
                        idempotency_key=str(clave),
                        empresa_id=str(usuario.empresa_id),
                        metadata={
                            "empresa_id": str(usuario.empresa_id),
                            "venta_id": str(reintento.id),
                            "cliente_id": str(reintento.cliente_id) if reintento.cliente_id else "",
                        },
                    )
                    ord_existente.clave_externa = intencion.id
                    ord_existente.referencia_externa = intencion.id
                    ord_existente.actualizada_en = self.reloj.ahora()
                    await self.db.commit()
                return await self._construir_dto_iniciada(reintento, ord_existente)

        self._autorizar_caja(usuario, dto.sucursal_id)

        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")

        sucursal = await self.db.get(Sucursal, dto.sucursal_id)
        if sucursal is None or sucursal.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada en la empresa")
        if not sucursal.activa:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sucursal inactiva")

        variantes_solicitadas = set()
        for item in dto.lineas:
            if item.variante_id in variantes_solicitadas:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variante duplicada en la venta")
            variantes_solicitadas.add(item.variante_id)

        ahora = self.reloj.ahora()

        turno = None
        if dto.turno_caja_id is not None:
            turno = await self.db.get(TurnoCaja, dto.turno_caja_id)
            if turno is None or turno.empresa_id != usuario.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno de caja no encontrado")
            if turno.sucursal_id != dto.sucursal_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Turno de caja no pertenece a la sucursal")
            if turno.estado != "ABIERTO":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Turno de caja no está abierto (estado: {turno.estado})")
            if turno.vence_en and turno.vence_en <= ahora:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Turno de caja vencido")

        subtotal = Decimal("0.00")
        descuento_total = Decimal("0.00")
        planes_items = []

        promocion_service = PromocionService(self.db, self.reloj)

        # Bloqueo determinista de inventario ordenado por (sucursal_id, variante_id)
        claves_ordenadas = self.inventario_repo.ordenarClavesBloqueo(
            [(dto.sucursal_id, vid) for vid in variantes_solicitadas]
        )
        filas_inv = await self.inventario_repo.bloquearFilas(claves_ordenadas)

        for item in dto.lineas:
            var = await self.db.get(VarianteProducto, item.variante_id)
            if var is None or var.empresa_id != usuario.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variante {item.variante_id} no encontrada")

            # CU19: Las ventas Stripe usan SIEMPRE stock libre disponible.
            # Que el cajero tenga turno abierto no autoriza consumir cupos offline para Stripe.
            fila_stock = filas_inv.get((dto.sucursal_id, item.variante_id))
            disponible_actual = fila_stock.disponible if fila_stock else 0

            if fila_stock is None or disponible_actual < item.cantidad:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Stock libre insuficiente para venta conectada Stripe (prenda asignada a caja offline o agotada)",
                )

            # Trasladar stock libre durablemente a comprometido_digital
            fila_stock.disponible -= item.cantidad
            fila_stock.comprometido_digital = (fila_stock.comprometido_digital or 0) + item.cantidad
            fila_stock.actualizado_en = ahora

            precio_servidor = Decimal(str(var.precio or 0))
            desc_servidor, promo_id = await promocion_service.mejorDescuento(
                var.id, precio_servidor, item.cantidad, ahora
            )

            if item.precio_unitario_bob is not None:
                precio_cliente = Decimal(str(item.precio_unitario_bob))
                if abs(precio_cliente - precio_servidor) > Decimal("0.01"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Precio unitario adulterado o desactualizado para la variante {item.variante_id}: enviado {item.precio_unitario_bob}, servidor {precio_servidor}",
                    )

            if item.descuento_bob is not None:
                desc_cliente = Decimal(str(item.descuento_bob))
                if abs(desc_cliente - desc_servidor) > Decimal("0.01"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Descuento adulterado o desactualizado para la variante {item.variante_id}: enviado {item.descuento_bob}, servidor {desc_servidor}",
                    )

            precio = precio_servidor
            desc = desc_servidor
            costo = Decimal(str(var.costo_promedio or 0))

            tot_item = (precio * item.cantidad) - desc
            subtotal += precio * item.cantidad
            descuento_total += desc
            planes_items.append((var, item.cantidad, precio, desc, tot_item, costo, promo_id))

        total = subtotal - descuento_total
        if total < Decimal("0.00"):
            total = Decimal("0.00")

        stmt_tasa = (
            select(TasaCambio)
            .where(TasaCambio.vigente_hasta.is_(None))
            .order_by(TasaCambio.vigente_desde.desc())
        )
        tasa = (await self.db.execute(stmt_tasa)).scalars().first()
        if tasa is None:
            stmt_tasa = select(TasaCambio).order_by(TasaCambio.vigente_desde.desc())
            tasa = (await self.db.execute(stmt_tasa)).scalars().first()

        if tasa is None or not tasa.tasa_bob_por_usd:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No existe tasa de cambio vigente en el sistema para cotizar el pago",
            )

        factor = Decimal(str(tasa.tasa_bob_por_usd))
        monto_usd = (total / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        centavos_usd = int(monto_usd * 100)

        numero_venta = await self._generar_numero_venta()
        expira_en = ahora + timedelta(minutes=15)
        venta = Venta(
            id=uuid.uuid4(),
            empresa_id=usuario.empresa_id,
            numero=numero_venta,
            cliente_id=dto.cliente_id,
            sucursal_id=dto.sucursal_id,
            cajero_id=usuario.id,
            canal="PRESENCIAL",
            estado="PENDIENTE_PAGO",
            subtotal=subtotal,
            descuento=descuento_total,
            costo_entrega=Decimal("0.00"),
            total=total,
            creada_en=ahora,
            expira_en=expira_en,
            clave_idempotencia=clave,
            hash_solicitud=digest,
            turno_caja_id=dto.turno_caja_id,
        )
        self.db.add(venta)
        await self.db.flush()

        for var, cant, precio, desc, tot_item, costo, promo_id in planes_items:
            det = DetalleVenta(
                id=uuid.uuid4(),
                venta_id=venta.id,
                variante_id=var.id,
                cantidad=cant,
                precio_unitario=precio,
                descuento=desc,
                costo_promedio=costo,
                promocion_id=promo_id,
            )
            self.db.add(det)
            await self.db.flush()

            # Kardex COMPROMISO_DIGITAL referenciado a VENTA
            kardex_comp = MovimientoInventario(
                id=uuid.uuid4(),
                variante_id=var.id,
                sucursal_origen_id=dto.sucursal_id,
                sucursal_destino_id=dto.sucursal_id,
                responsable_id=usuario.id,
                tipo="COMPROMISO_DIGITAL",
                cantidad=cant,
                costo_unitario=costo,
                referencia_tipo="VENTA",
                referencia_id=venta.id,
                linea_referencia_id=det.id,
                observacion=f"Compromiso digital venta presencial {numero_venta}",
                fecha_hora=ahora,
            )
            self.db.add(kardex_comp)

        clave_provisional = f"PENDIENTE_{clave}"
        nueva_orden = OrdenPago(
            id=uuid.uuid4(),
            empresa_id=usuario.empresa_id,
            contexto="VENTA",
            pedido_id=None,
            reserva_id=None,
            venta_id=venta.id,
            cambio_id=None,
            proveedor="STRIPE",
            clave_externa=clave_provisional,
            referencia_externa=clave_provisional,
            estado="PENDIENTE",
            monto_bob=total,
            tasa_id=tasa.id,
            monto_usd=monto_usd,
            centavos_usd=centavos_usd,
            revision=1,
            creada_en=ahora,
            actualizada_en=ahora,
        )
        self.db.add(nueva_orden)

        # Transacción 1: Commit para LIBERAR LOS LOCKS de inventario antes de llamar al gateway por red
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            reintento = await resolver_idempotencia(self.db, Venta, clave, digest)
            if reintento is not None:
                stmt_ord = select(OrdenPago).where(OrdenPago.venta_id == reintento.id)
                ord_existente = (await self.db.execute(stmt_ord)).scalars().first()
                if ord_existente:
                    return await self._construir_dto_iniciada(reintento, ord_existente)
            raise
        except Exception:
            await self.db.rollback()
            raise

        # Fuera de locks: Llamar a pasarela externa
        gateway = self.gateway
        intencion = await gateway.crear_o_reutilizar_intencion(
            venta_id=str(venta.id),
            monto_centavos=centavos_usd,
            moneda="usd",
            idempotency_key=str(clave),
            empresa_id=str(usuario.empresa_id),
            metadata={
                "empresa_id": str(usuario.empresa_id),
                "venta_id": str(venta.id),
                "cliente_id": str(dto.cliente_id) if dto.cliente_id else "",
            },
        )
        if dto.cliente_id and hasattr(intencion, "cliente_id"):
            intencion.cliente_id = str(dto.cliente_id)

        # Transacción 2: En nueva transacción actualizar OrdenPago con el ID devuelto por el gateway
        stmt_ord_upd = select(OrdenPago).where(OrdenPago.id == nueva_orden.id).with_for_update()
        ord_act = (await self.db.execute(stmt_ord_upd)).scalars().first()
        if ord_act:
            ord_act.clave_externa = intencion.id
            ord_act.referencia_externa = intencion.id
            ord_act.actualizada_en = self.reloj.ahora()
            await self.db.commit()

        return VentaPresencialStripeIniciadaDTO(
            venta_id=venta.id,
            orden_pago_id=nueva_orden.id,
            stripe_payment_intent_id=intencion.id,
            client_secret=intencion.client_secret,
            monto_bob=total,
            monto_usd=monto_usd,
            centavos_usd=centavos_usd,
            tasa_bob_por_usd=factor,
            estado_orden=nueva_orden.estado,
        )

    async def liquidar(
        self, usuario: Usuario, dto: VentaPresencialLiquidarDTO, clave: uuid.UUID
    ) -> VentaLiquidadaDTO:
        digest = hash_payload(dto.model_dump(mode="json"))

        # Idempotencia previa
        reintento = await resolver_idempotencia(self.db, Venta, clave, digest)
        if reintento is not None and reintento.estado == "PAGADA":
            return await self._a_venta_liquidada_dto(reintento)

        self._autorizar_caja(usuario, dto.sucursal_id)

        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")

        sucursal = await self.db.get(Sucursal, dto.sucursal_id)
        if sucursal is None or sucursal.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada en la empresa")
        if not sucursal.activa:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sucursal inactiva")

        # Validar variantes únicas en solicitud
        variantes_solicitadas = set()
        for item in dto.lineas:
            if item.variante_id in variantes_solicitadas:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variante duplicada en la venta")
            variantes_solicitadas.add(item.variante_id)

        ahora = self.reloj.ahora()
        promocion_service = PromocionService(self.db, self.reloj)
        saldo_service = SaldoService(self.db, self.reloj)

        es_venta_previa = (dto.medio_pago in ("STRIPE_TEST", "STRIPE") or dto.venta_id is not None)

        cambio_entregado = Decimal("0.00")
        orden_stripe: Optional[OrdenPago] = None
        venta_existente: Optional[Venta] = None
        intencion_stripe_verificada = None
        orden_stripe_previa_id: Optional[uuid.UUID] = None
        turno_id_efectivo: Optional[uuid.UUID] = None
        cupos_map = {}
        planes_items = []
        detalles_map = {}
        ref_pi: Optional[str] = dto.stripe_payment_intent_id

        # Consultar Stripe antes de adquirir bloqueos de inventario/venta/orden.
        # Luego se vuelven a bloquear y comparar los agregados antes de mutar.
        if dto.medio_pago in ("STRIPE_TEST", "STRIPE"):
            orden_previa = None
            if dto.orden_pago_id:
                orden_previa = await self.db.get(OrdenPago, dto.orden_pago_id)
            elif ref_pi:
                orden_previa = (
                    await self.db.execute(
                        select(OrdenPago).where(
                            OrdenPago.proveedor == "STRIPE",
                            or_(
                                OrdenPago.referencia_externa == ref_pi,
                                OrdenPago.clave_externa == ref_pi,
                            ),
                        )
                    )
                ).scalars().first()
            elif dto.venta_id:
                orden_previa = (
                    await self.db.execute(
                        select(OrdenPago).where(
                            OrdenPago.proveedor == "STRIPE",
                            OrdenPago.venta_id == dto.venta_id,
                        ).order_by(OrdenPago.creada_en.desc())
                    )
                ).scalars().first()

            if orden_previa is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Liquidación Stripe requiere una orden de pago interna vinculada a la venta.",
                )
            if orden_previa.empresa_id != usuario.empresa_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El cargo de Stripe pertenece a otra empresa")
            if orden_previa.contexto != "VENTA" or orden_previa.venta_id is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La orden Stripe no corresponde a una venta presencial")
            if dto.venta_id is not None and orden_previa.venta_id != dto.venta_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El cargo de Stripe pertenece a otra venta")
            if ref_pi and ref_pi != orden_previa.referencia_externa:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PaymentIntent no coincide con la orden de pago")

            ref_previa = orden_previa.referencia_externa
            if not ref_previa or ref_previa.startswith("PENDIENTE_"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La orden Stripe aún no tiene un PaymentIntent confirmado; reanude el cobro antes de liquidar.",
                )

            orden_stripe_previa_id = orden_previa.id
            orden_previa_snapshot = SimpleNamespace(
                id=orden_previa.id,
                contexto=orden_previa.contexto,
                empresa_id=orden_previa.empresa_id,
                referencia_externa=orden_previa.referencia_externa,
                clave_externa=orden_previa.clave_externa,
                centavos_usd=orden_previa.centavos_usd,
                venta_id=orden_previa.venta_id,
                pedido_id=orden_previa.pedido_id,
                reserva_id=orden_previa.reserva_id,
                cambio_id=orden_previa.cambio_id,
            )
            ref_pi = ref_previa
            # Estos SELECT no han tomado bloqueos ni cambiado datos. Cerrar su
            # transacción permite esperar a la pasarela sin retener conexiones.
            await self.db.rollback()
            try:
                intencion_stripe_verificada = await self.gateway.consultar_intencion(ref_previa)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="No se pudo verificar el estado del pago en Stripe; la venta y el inventario permanecen pendientes.",
                ) from exc
            if not intencion_stripe_verificada or intencion_stripe_verificada.estado.upper() not in ("SUCCEEDED", "CAPTURADO"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Stripe todavía no confirma la captura; la venta y el inventario permanecen pendientes.",
                )
            from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService

            StripeService(self.db, self.reloj)._validar_intencion_con_orden(
                intencion_stripe_verificada, orden_previa_snapshot, referencia_esperada=ref_previa
            )

        # 1. Bloqueo determinista de inventario ordenado por (sucursal_id, variante_id)
        claves_ordenadas = sorted([(dto.sucursal_id, vid) for vid in variantes_solicitadas], key=lambda x: str(x[1]))
        filas_inv = await self.inventario_repo.bloquearFilas(claves_ordenadas)

        if es_venta_previa:
            # Recuperar venta_existente y orden_stripe previa
            if dto.medio_pago in ("STRIPE_TEST", "STRIPE"):
                condiciones_orden = []
                if ref_pi:
                    condiciones_orden.extend([
                        OrdenPago.referencia_externa == ref_pi,
                        OrdenPago.clave_externa == ref_pi,
                    ])
                if dto.orden_pago_id:
                    condiciones_orden.append(OrdenPago.id == dto.orden_pago_id)
                if not condiciones_orden and dto.venta_id:
                    condiciones_orden.append(OrdenPago.venta_id == dto.venta_id)
                if not condiciones_orden:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Liquidación con STRIPE_TEST requiere stripe_payment_intent_id u orden_pago_id",
                    )
                stmt_ord_pre = select(OrdenPago).where(or_(*condiciones_orden)).with_for_update()
                orden_stripe = (await self.db.execute(stmt_ord_pre)).scalars().first()
                if orden_stripe is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Liquidación con STRIPE_TEST requiere una orden de pago interna previa creada por FashionStore vinculada a la venta",
                    )
                if orden_stripe.empresa_id != usuario.empresa_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El cargo de Stripe pertenece a otra empresa")
                if orden_stripe.venta_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="El cargo de Stripe no está vinculado a ninguna venta previa",
                    )
                if dto.venta_id is not None and orden_stripe.venta_id != dto.venta_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="El cargo de Stripe pertenece a otra venta",
                    )
                venta_id_objetivo = orden_stripe.venta_id
            else:
                venta_id_objetivo = dto.venta_id

            # Bloquear la Venta objetivo
            stmt_v = select(Venta).where(Venta.id == venta_id_objetivo).with_for_update()
            venta_existente = (await self.db.execute(stmt_v)).scalars().first()
            if venta_existente is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada")
            if venta_existente.empresa_id != usuario.empresa_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Venta de otra empresa")
            if venta_existente.sucursal_id != dto.sucursal_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Venta pertenece a otra sucursal")
            if not es_admin(usuario) and venta_existente.cajero_id and venta_existente.cajero_id != usuario.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Venta iniciada por otro cajero")
            if venta_existente.estado in ("PAGADA", "ENTREGADA", "CONFIRMADA", "COMPLETADA"):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La venta ya fue liquidada")
            if venta_existente.estado != "PENDIENTE_PAGO":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"La venta no está pendiente de pago (estado: {venta_existente.estado})")

            # Validar turno
            turno_id_efectivo = dto.turno_caja_id or venta_existente.turno_caja_id
            if venta_existente.turno_caja_id is not None and dto.turno_caja_id is not None:
                if venta_existente.turno_caja_id != dto.turno_caja_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Turno de caja no coincide con el turno de la venta")

            if turno_id_efectivo is not None:
                turno = await self.db.get(TurnoCaja, turno_id_efectivo)
                if turno is None or turno.empresa_id != usuario.empresa_id:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno de caja no encontrado")
                if turno.sucursal_id != dto.sucursal_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Turno de caja no pertenece a la sucursal")
                if turno.estado != "ABIERTO":
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Turno de caja no está abierto (estado: {turno.estado})")
                if turno.vence_en and turno.vence_en <= ahora:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Turno de caja vencido")

            # Comparar dto.lineas con los DetalleVenta persistidos (mismas variantes y cantidades)
            stmt_det = select(DetalleVenta).where(DetalleVenta.venta_id == venta_existente.id)
            detalles_existentes = (await self.db.execute(stmt_det)).scalars().all()
            detalles_map = {d.variante_id: d for d in detalles_existentes}

            if len(detalles_existentes) > 0:
                if len(dto.lineas) != len(detalles_existentes) or set(variantes_solicitadas) != set(detalles_map.keys()):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Las líneas de la venta no coinciden exactamente con las registradas previamente",
                    )

                for item in dto.lineas:
                    det_prev = detalles_map.get(item.variante_id)
                    if det_prev is None or det_prev.cantidad != item.cantidad:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Cantidad enviada ({item.cantidad}) no coincide exactamente con la venta iniciada ({det_prev.cantidad if det_prev else 0}) para la variante {item.variante_id}",
                        )
                    if item.precio_unitario_bob is not None:
                        if abs(Decimal(str(item.precio_unitario_bob)) - Decimal(str(det_prev.precio_unitario))) > Decimal("0.01"):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Precio unitario adulterado o desactualizado para la variante {item.variante_id}: enviado {item.precio_unitario_bob}, venta iniciada {det_prev.precio_unitario}",
                            )
                    if item.descuento_bob is not None:
                        if abs(Decimal(str(item.descuento_bob)) - Decimal(str(det_prev.descuento))) > Decimal("0.01"):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Descuento adulterado o desactualizado para la variante {item.variante_id}: enviado {item.descuento_bob}, venta iniciada {det_prev.descuento}",
                            )

            # J3: NO recalcular con catálogo ni promociones: Usar importes congelados de DetalleVenta y venta_existente.total
            subtotal = Decimal(str(venta_existente.subtotal))
            descuento_total = Decimal(str(venta_existente.descuento))
            total = Decimal(str(venta_existente.total))

            if len(detalles_existentes) > 0:
                for item in dto.lineas:
                    var = await self.db.get(VarianteProducto, item.variante_id)
                    if var is None or var.empresa_id != usuario.empresa_id:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variante {item.variante_id} no encontrada")

                    fila_stock = filas_inv.get((dto.sucursal_id, item.variante_id))
                    det_prev = detalles_map[item.variante_id]
                    cant = det_prev.cantidad

                    if dto.medio_pago in ("STRIPE_TEST", "STRIPE"):
                        comp_dig = fila_stock.comprometido_digital if fila_stock else 0
                        if comp_dig < cant and (fila_stock is None or fila_stock.disponible < cant):
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=f"Stock insuficiente para liquidar venta Stripe: comprometido {comp_dig}, requerido {cant}",
                            )

                    precio = Decimal(str(det_prev.precio_unitario))
                    desc = Decimal(str(det_prev.descuento))
                    costo = Decimal(str(det_prev.costo_promedio))
                    tot_item = (precio * cant) - desc
                    planes_items.append((var, cant, precio, desc, tot_item, costo, fila_stock, det_prev.promocion_id, None))
            else:
                for item in dto.lineas:
                    var = await self.db.get(VarianteProducto, item.variante_id)
                    if var is None or var.empresa_id != usuario.empresa_id:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variante {item.variante_id} no encontrada")

                    fila_stock = filas_inv.get((dto.sucursal_id, item.variante_id))
                    cant = item.cantidad

                    if dto.medio_pago in ("STRIPE_TEST", "STRIPE"):
                        comp_dig = fila_stock.comprometido_digital if fila_stock else 0
                        if comp_dig < cant and (fila_stock is None or fila_stock.disponible < cant):
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=f"Stock insuficiente para liquidar venta Stripe: comprometido {comp_dig}, requerido {cant}",
                            )

                    precio = Decimal(str(item.precio_unitario_bob or var.precio or 0))
                    desc = Decimal(str(item.descuento_bob or 0))
                    costo = Decimal(str(var.costo_promedio or 0))
                    tot_item = (precio * cant) - desc
                    planes_items.append((var, cant, precio, desc, tot_item, costo, fila_stock, None, None))

            # Liquidación del medio de pago
            if dto.medio_pago in ("STRIPE_TEST", "STRIPE"):
                if orden_stripe is None:
                    condiciones_orden = [OrdenPago.venta_id == venta_existente.id]
                    if ref_pi:
                        condiciones_orden.extend([
                            OrdenPago.referencia_externa == ref_pi,
                            OrdenPago.clave_externa == ref_pi,
                        ])
                    if dto.orden_pago_id:
                        condiciones_orden.append(OrdenPago.id == dto.orden_pago_id)
                    stmt_orden = select(OrdenPago).where(or_(*condiciones_orden)).with_for_update()
                    orden_stripe = (await self.db.execute(stmt_orden)).scalars().first()

                if orden_stripe is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Liquidación con STRIPE_TEST requiere una orden de pago interna previa creada por FashionStore vinculada a la venta",
                    )
                if orden_stripe.empresa_id != usuario.empresa_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El cargo de Stripe pertenece a otra empresa")
                if orden_stripe.contexto != "VENTA":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"La orden de pago fue creada para contexto {orden_stripe.contexto}, requiere contexto VENTA")
                if orden_stripe.venta_id != venta_existente.id:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El cargo de Stripe pertenece a otra venta")

                ref_pi = ref_pi or orden_stripe.referencia_externa or orden_stripe.clave_externa
                if not ref_pi or not ref_pi.strip():
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Venta con STRIPE_TEST requiere stripe_payment_intent_id")
                if orden_stripe.id != orden_stripe_previa_id:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La orden Stripe cambió durante la verificación; reintente la liquidación")
                if ref_pi != orden_stripe.referencia_externa or intencion_stripe_verificada is None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La referencia Stripe cambió durante la verificación; reintente la liquidación")

                # Verificar que el pago no haya sido consumido previamente
                stmt_pago_consumido = select(Pago).where(
                    Pago.referencia_externa == ref_pi,
                    Pago.estado == "APROBADO",
                )
                pago_existente = (await self.db.execute(stmt_pago_consumido)).scalars().first()
                if pago_existente is not None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El cargo de Stripe ya fue aplicado a otra venta")

                # Validar orden_stripe.monto_bob == venta_existente.total
                if Decimal(str(orden_stripe.monto_bob)) != venta_existente.total:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Monto de orden Stripe ({orden_stripe.monto_bob} BOB) no coincide exactamente con el total adeudado ({venta_existente.total} BOB)",
                    )

                cliente_orden = getattr(orden_stripe, "cliente_id", None) or venta_existente.cliente_id

                # Validación con Stripe Gateway (J2)
                try:
                    intencion = intencion_stripe_verificada
                    if intencion is None:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="No se pudo verificar el estado del pago en Stripe por indisponibilidad de la pasarela; el cobro y el inventario se conservan pendientes para reintento.",
                        )
                    from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService

                    StripeService(self.db, self.reloj)._validar_intencion_con_orden(
                        intencion, orden_stripe, referencia_esperada=ref_pi
                    )
                    if intencion.id not in (ref_pi, orden_stripe.referencia_externa, orden_stripe.clave_externa):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"ID de PaymentIntent '{intencion.id}' no coincide con la orden",
                        )
                    if intencion.estado.upper() not in ("SUCCEEDED", "CAPTURADO"):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"El PaymentIntent de Stripe no está capturado (estado: {intencion.estado})",
                        )
                    int_moneda = (getattr(intencion, "moneda", "") or "").lower()
                    if int_moneda not in ("usd", "bob"):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Moneda de intención Stripe '{getattr(intencion, 'moneda', '')}' incongruente o no admitida (requiere BOB o USD)",
                        )
                    if orden_stripe.centavos_usd is not None and getattr(intencion, "monto_centavos", None) is not None:
                        if int(intencion.monto_centavos) != orden_stripe.centavos_usd:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Centavos USD del PaymentIntent ({intencion.monto_centavos}) no coinciden con la orden ({orden_stripe.centavos_usd})",
                            )
                    if getattr(intencion, "metadata", None):
                        int_empresa = intencion.metadata.get("empresa_id")
                        if int_empresa and str(int_empresa) != str(orden_stripe.empresa_id):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Metadata de empresa en PaymentIntent no coincide con la orden",
                            )
                        int_venta = intencion.metadata.get("venta_id")
                        if int_venta and str(int_venta) != str(orden_stripe.venta_id):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Metadata de venta en PaymentIntent no coincide con la orden",
                            )

                    int_cliente = getattr(intencion, "cliente_id", None)
                    if not int_cliente and getattr(intencion, "metadata", None):
                        int_cliente = intencion.metadata.get("cliente_id")
                    if int_cliente and cliente_orden is None:
                        try:
                            cliente_orden = uuid.UUID(str(int_cliente))
                        except ValueError:
                            pass

                    if orden_stripe.estado != "CAPTURADO":
                        orden_stripe.estado = "CAPTURADO"
                        orden_stripe.actualizada_en = ahora

                except HTTPException as http_exc:
                    if http_exc.status_code in (502, 503, 504):
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="No se pudo verificar el estado del pago en Stripe por indisponibilidad de la pasarela; el cobro y el inventario se conservan pendientes para reintento.",
                        ) from http_exc
                    raise
                except Exception as exc:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="No se pudo verificar el estado del pago en Stripe por indisponibilidad de la pasarela; el cobro y el inventario se conservan pendientes para reintento.",
                    ) from exc

                if cliente_orden is not None:
                    if dto.cliente_id is None or str(cliente_orden) != str(dto.cliente_id):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="El cargo de Stripe pertenece a otro cliente",
                        )

                # Validar centavos exactos en USD cotizado
                if orden_stripe.centavos_usd is not None:
                    if orden_stripe.centavos_usd <= 0:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Los centavos de la orden Stripe deben ser mayores a cero",
                        )
                    if orden_stripe.tasa_id:
                        tasa = await self.db.get(TasaCambio, orden_stripe.tasa_id)
                    else:
                        stmt_tasa = (
                            select(TasaCambio)
                            .where(TasaCambio.vigente_hasta.is_(None))
                            .order_by(TasaCambio.vigente_desde.desc())
                        )
                        tasa = (await self.db.execute(stmt_tasa)).scalars().first()
                        if tasa is None:
                            stmt_tasa = select(TasaCambio).order_by(TasaCambio.vigente_desde.desc())
                            tasa = (await self.db.execute(stmt_tasa)).scalars().first()
                    if tasa is None or not tasa.tasa_bob_por_usd:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No existe tasa de cambio vigente en el sistema para cotizar el pago",
                        )
                    factor = Decimal(str(tasa.tasa_bob_por_usd))
                    usd_req = (total / factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    centavos_req = int(usd_req * 100)
                    if orden_stripe.centavos_usd != centavos_req:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Centavos USD de la orden Stripe ({orden_stripe.centavos_usd}) no coinciden exactamente con la cotización ({centavos_req} centavos para {total} BOB)",
                        )

            elif dto.medio_pago == "EFECTIVO":
                recibido = dto.efectivo_recibido_bob or Decimal("0.00")
                if recibido < total:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Efectivo recibido ({recibido} BOB) es menor al total adeudado ({total} BOB)",
                    )
                cambio_entregado = recibido - total
            elif dto.medio_pago == "SALDO":
                if not dto.cliente_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Venta con saldo requiere cliente_id")
                disp, _, _ = await saldo_service.calcular_totales(
                    cliente_id=dto.cliente_id, empresa_id=usuario.empresa_id, con_bloqueo=True
                )
                if total > disp:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Saldo insuficiente: disponible {disp} BOB, requerido {total} BOB",
                    )

        else:
            # Venta presencial nueva en EFECTIVO o SALDO (sin venta previa iniciada)
            turno_id_efectivo = dto.turno_caja_id
            if turno_id_efectivo is not None:
                turno = await self.db.get(TurnoCaja, turno_id_efectivo)
                if turno is None or turno.empresa_id != usuario.empresa_id:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno de caja no encontrado")
                if turno.sucursal_id != dto.sucursal_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Turno de caja no pertenece a la sucursal")
                if turno.estado != "ABIERTO":
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Turno de caja no está abierto (estado: {turno.estado})")
                if turno.vence_en and turno.vence_en <= ahora:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Turno de caja vencido")

                stmt_cupos = (
                    select(CupoCaja)
                    .where(
                        CupoCaja.turno_id == turno_id_efectivo,
                        CupoCaja.variante_id.in_(variantes_solicitadas),
                        CupoCaja.empresa_id == usuario.empresa_id,
                    )
                    .order_by(CupoCaja.variante_id)
                    .with_for_update()
                )
                cupos_map = {c.variante_id: c for c in (await self.db.execute(stmt_cupos)).scalars().all()}

            subtotal = Decimal("0.00")
            descuento_total = Decimal("0.00")

            for item in dto.lineas:
                var = await self.db.get(VarianteProducto, item.variante_id)
                if var is None or var.empresa_id != usuario.empresa_id:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variante {item.variante_id} no encontrada")

                fila_stock = filas_inv.get((dto.sucursal_id, item.variante_id))
                cupo = cupos_map.get(item.variante_id) if turno_id_efectivo is not None else None

                if turno_id_efectivo is not None:
                    if cupo is None:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"Variante {item.variante_id} sin cupo asignado en el turno de caja",
                        )
                    disp_cupo = cupo.otorgado - cupo.consumido - cupo.liberado - cupo.mermado
                    if disp_cupo < item.cantidad:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"Cupo insuficiente en caja para variante {item.variante_id}: disponible {disp_cupo}, requerido {item.cantidad}",
                        )
                else:
                    if fila_stock is None or fila_stock.disponible < item.cantidad:
                        disponible_actual = fila_stock.disponible if fila_stock else 0
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"Stock insuficiente para variante {item.variante_id}: disponible {disponible_actual}, requerido {item.cantidad}",
                        )

                # Precios y promociones calculados EXCLUSIVAMENTE por el servidor
                precio_servidor = Decimal(str(var.precio or 0))
                desc_servidor, promo_id = await promocion_service.mejorDescuento(
                    var.id, precio_servidor, item.cantidad, ahora
                )

                # Rechazo explícito si el cliente/caja envió precio adulterado
                if item.precio_unitario_bob is not None:
                    precio_cliente = Decimal(str(item.precio_unitario_bob))
                    if abs(precio_cliente - precio_servidor) > Decimal("0.01"):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Precio unitario adulterado o desactualizado para la variante {item.variante_id}: enviado {item.precio_unitario_bob}, servidor {precio_servidor}",
                        )

                # Rechazo explícito si el cliente/caja envió descuento adulterado
                if item.descuento_bob is not None:
                    desc_cliente = Decimal(str(item.descuento_bob))
                    if abs(desc_cliente - desc_servidor) > Decimal("0.01"):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Descuento adulterado o desactualizado para la variante {item.variante_id}: enviado {item.descuento_bob}, servidor {desc_servidor}",
                        )

                precio = precio_servidor
                desc = desc_servidor
                costo = Decimal(str(var.costo_promedio or 0))

                tot_item = (precio * item.cantidad) - desc
                subtotal += precio * item.cantidad
                descuento_total += desc
                planes_items.append((var, item.cantidad, precio, desc, tot_item, costo, fila_stock, promo_id, cupo))

            total = subtotal - descuento_total
            if total < Decimal("0.00"):
                total = Decimal("0.00")

            if dto.medio_pago == "EFECTIVO":
                recibido = dto.efectivo_recibido_bob or Decimal("0.00")
                if recibido < total:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Efectivo recibido ({recibido} BOB) es menor al total adeudado ({total} BOB)",
                    )
                cambio_entregado = recibido - total
            elif dto.medio_pago == "SALDO":
                if not dto.cliente_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Venta con saldo requiere cliente_id")
                disp, _, _ = await saldo_service.calcular_totales(
                    cliente_id=dto.cliente_id, empresa_id=usuario.empresa_id, con_bloqueo=True
                )
                if total > disp:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Saldo insuficiente: disponible {disp} BOB, requerido {total} BOB",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Venta presencial directa solo admite EFECTIVO o SALDO; pagos con STRIPE_TEST requieren iniciar-stripe previamente",
                )

        # 3. Descontar stock disponible o consumir cupo atómicamente SOLO TRAS LIQUIDACIÓN VERIFICADA
        for var, cant, precio, desc, tot_item, costo, fila_stock, promo_id, cupo in planes_items:
            if dto.medio_pago in ("STRIPE_TEST", "STRIPE"):
                if fila_stock is not None:
                    if (fila_stock.comprometido_digital or 0) >= cant:
                        fila_stock.comprometido_digital -= cant
                    else:
                        fila_stock.disponible -= cant
                    fila_stock.actualizado_en = ahora
            elif turno_id_efectivo is not None and cupo is not None:
                cupo.consumido += cant
                if fila_stock is not None:
                    fila_stock.comprometido_caja = max(0, (fila_stock.comprometido_caja or 0) - cant)
                    fila_stock.actualizado_en = ahora
            else:
                if fila_stock is not None:
                    fila_stock.disponible -= cant
                    fila_stock.actualizado_en = ahora
            await self.db.flush()

        # 4. Actualizar Venta iniciada o Crear Venta directa
        if venta_existente is not None:
            venta = venta_existente
            venta.estado = "PAGADA"
            venta.cajero_id = usuario.id
            venta.confirmada_en = ahora
            venta.entregada_en = ahora
            venta.clave_idempotencia = clave
            venta.hash_solicitud = digest
            if turno_id_efectivo:
                venta.turno_caja_id = turno_id_efectivo
            numero_venta = venta.numero
            await self.db.flush()
        else:
            numero_venta = await self._generar_numero_venta()
            venta = Venta(
                id=uuid.uuid4(),
                empresa_id=usuario.empresa_id,
                numero=numero_venta,
                cliente_id=dto.cliente_id,
                sucursal_id=dto.sucursal_id,
                cajero_id=usuario.id,
                canal="PRESENCIAL",
                estado="PAGADA",
                subtotal=subtotal,
                descuento=descuento_total,
                costo_entrega=Decimal("0.00"),
                total=total,
                creada_en=ahora,
                confirmada_en=ahora,
                entregada_en=ahora,
                clave_idempotencia=clave,
                hash_solicitud=digest,
                turno_caja_id=turno_id_efectivo,
            )
            self.db.add(venta)
            await self.db.flush()

        # Si el medio de pago es SALDO, debitar formalmente del cliente
        if dto.medio_pago == "SALDO":
            await saldo_service.debitar_saldo(
                cliente_id=dto.cliente_id,
                empresa_id=usuario.empresa_id,
                monto_bob=total,
                origen_tipo="VENTA",
                origen_id=venta.id,
                referencia_unica=clave,
            )

        if orden_stripe is not None:
            orden_stripe.actualizada_en = ahora
            await self.db.flush()

        # 5. Detalles de Venta y Movimientos Kardex
        kardex_ids: List[uuid.UUID] = []
        detalles_comprobante = []

        stmt_det_existentes = select(DetalleVenta).where(DetalleVenta.venta_id == venta.id)
        detalles_map = {
            d.variante_id: d for d in (await self.db.execute(stmt_det_existentes)).scalars().all()
        }

        for var, cant, precio, desc, tot_item, costo, fila_stock, promo_id, cupo in planes_items:
            det = detalles_map.get(var.id)
            if det is None:
                det = DetalleVenta(
                    id=uuid.uuid4(),
                    venta_id=venta.id,
                    variante_id=var.id,
                    cantidad=cant,
                    precio_unitario=precio,
                    descuento=desc,
                    costo_promedio=costo,
                    promocion_id=promo_id,
                )
                self.db.add(det)
                await self.db.flush()
                detalles_map[var.id] = det

            # Kardex VENTA_PRESENCIAL único
            kardex_mov = MovimientoInventario(
                id=uuid.uuid4(),
                variante_id=var.id,
                sucursal_origen_id=dto.sucursal_id,
                sucursal_destino_id=dto.sucursal_id,
                responsable_id=usuario.id,
                tipo="VENTA_PRESENCIAL",
                cantidad=cant,
                costo_unitario=costo,
                referencia_tipo="VENTA",
                referencia_id=venta.id,
                linea_referencia_id=det.id,
                observacion=f"Venta presencial {numero_venta}",
                fecha_hora=ahora,
            )
            self.db.add(kardex_mov)
            await self.db.flush()
            kardex_ids.append(kardex_mov.id)

            detalles_comprobante.append(
                {
                    "variante_id": str(var.id),
                    "cantidad": cant,
                    "precio_unitario": str(precio),
                    "descuento": str(desc),
                    "subtotal": str(tot_item),
                }
            )

        # 6. Registrar Pago si aplica (para medios de pago financieros en comercial.pagos)
        if dto.medio_pago in ("EFECTIVO", "STRIPE_TEST", "STRIPE"):
            pago = Pago(
                id=uuid.uuid4(),
                empresa_id=usuario.empresa_id,
                contexto="VENTA",
                venta_id=venta.id,
                metodo=dto.medio_pago,
                tipo_pago="TOTAL",
                monto=total,
                estado="APROBADO",
                efectivo_recibido_bob=dto.efectivo_recibido_bob if dto.medio_pago == "EFECTIVO" else None,
                cambio_entregado_bob=cambio_entregado if dto.medio_pago == "EFECTIVO" else None,
                referencia_externa=ref_pi if dto.medio_pago in ("STRIPE_TEST", "STRIPE") else None,
                proveedor_pago="STRIPE_TEST" if dto.medio_pago in ("STRIPE_TEST", "STRIPE") else None,
                pagado_en=ahora,
                clave_idempotencia=None,
                hash_solicitud=digest,
            )
            self.db.add(pago)

        # 7. Registrar Comprobante
        doc_comprobante = {
            "venta_id": str(venta.id),
            "numero": numero_venta,
            "sucursal_id": str(dto.sucursal_id),
            "cajero_id": str(usuario.id),
            "cliente_id": str(dto.cliente_id) if dto.cliente_id else None,
            "lineas": detalles_comprobante,
            "total_bob": str(total),
            "medio_pago": dto.medio_pago,
            "efectivo_recibido_bob": str(dto.efectivo_recibido_bob or 0),
            "cambio_entregado_bob": str(cambio_entregado),
            "fecha_hora": ahora.isoformat(),
        }
        comprobante = Comprobante(
            id=uuid.uuid4(),
            empresa_id=usuario.empresa_id,
            tipo="VENTA_PRESENCIAL",
            recurso_tipo="VENTA",
            recurso_id=venta.id,
            version=1,
            documento=doc_comprobante,
            documento_hash=hashlib.sha256(json.dumps(doc_comprobante, sort_keys=True).encode("utf-8")).hexdigest(),
            creado_en=ahora,
        )
        self.db.add(comprobante)

        try:
            await self.db.commit()
        except IntegrityError as e:
            await self.db.rollback()
            msg = str(getattr(e, "orig", e)).lower()
            if (
                "referencia_externa" in msg
                or "uq_pagos_referencia_externa" in msg
                or "orden" in msg
                or "venta_id" in msg
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="El cargo de Stripe ya fue aplicado a otra venta",
                )
            if "clave_idempotencia" in msg:
                reintento = await resolver_idempotencia(self.db, Venta, clave, digest)
                if reintento is not None:
                    return await self._a_venta_liquidada_dto(reintento)
            raise
        except Exception:
            await self.db.rollback()
            raise

        return VentaLiquidadaDTO(
            venta_id=venta.id,
            numero=venta.numero,
            total_bob=venta.total,
            comprobante_id=comprobante.id,
            kardex_ids=kardex_ids,
            cambio_entregado_bob=cambio_entregado,
            estado_pago=venta.estado if isinstance(venta.estado, str) else venta.estado.name,
            estado_entrega="ENTREGADA",
            fecha_hora=ahora,
        )

    async def _a_venta_liquidada_dto(self, venta: Venta) -> VentaLiquidadaDTO:
        stmt_comp = select(Comprobante).where(
            Comprobante.recurso_tipo == "VENTA",
            Comprobante.recurso_id == venta.id,
        )
        comp = (await self.db.execute(stmt_comp)).scalars().first()
        comp_id = comp.id if comp else venta.id

        stmt_k = select(MovimientoInventario.id).where(
            MovimientoInventario.referencia_tipo == "VENTA",
            MovimientoInventario.referencia_id == venta.id,
        )
        kardex_ids = list((await self.db.execute(stmt_k)).scalars().all())

        stmt_pago = select(Pago).where(Pago.venta_id == venta.id)
        pago = (await self.db.execute(stmt_pago)).scalars().first()
        cambio = pago.cambio_entregado_bob if pago and pago.cambio_entregado_bob is not None else Decimal("0.00")

        return VentaLiquidadaDTO(
            venta_id=venta.id,
            numero=venta.numero,
            total_bob=venta.total,
            comprobante_id=comp_id,
            kardex_ids=kardex_ids,
            cambio_entregado_bob=cambio,
            estado_pago=venta.estado if isinstance(venta.estado, str) else venta.estado.name,
            estado_entrega="ENTREGADA",
            fecha_hora=venta.confirmada_en or venta.creada_en,
        )
