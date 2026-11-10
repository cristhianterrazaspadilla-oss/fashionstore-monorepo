"""Controller StripeService — CU15 y CU22 (E2 Stripe Test Mode).

Capacidades:
- Flujo interactivo legado CU15 (/stripe/intenciones, /stripe/intenciones/reintento, /stripe/estado, /stripe/webhook).
- Capacidades E2 CU22:
  - SetupIntent / método preparado online (POST /metodos/preparar, GET /metodos/{id}).
  - Órdenes de pago unificadas con cálculo de deuda por servidor, tasa congelada y centavos USD (POST /ordenes, GET /ordenes/{id}).
  - Continuación de acción 3DS / SCA (POST /ordenes/{id}/continuar-accion).
"""
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.ambito_comercial import exigir_empresa_recurso
from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
from backend.app.core.config import settings
from backend.app.core.idempotencia import hash_payload
from backend.app.core.permisos import es_admin, rol_de
from backend.app.core.reloj import RelojSistema
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, Venta
from backend.app.core.modules.inventario.models import MovimientoInventario
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.organizacion.services.tasa_cambio_service import TasaCambioService
from backend.app.core.modules.ventas_pagos.models_ordenes import (
    ContinuarAccionDTO,
    EventoProveedor,
    LineaRecuperadaCajaDTO,
    MetodoPreparado,
    MetodoPreparadoDTO,
    OrdenActivaCajaDTO,
    OrdenPago,
    OrdenPagoCrearDTO,
    OrdenPagoDTO,
)
from backend.app.core.modules.ventas_pagos.repositories.pedido_repository import PedidoRepository
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.ventas_pagos.repositories.pago_repository import PagoRepository
from backend.app.core.modules.ventas_pagos.repositories.venta_repository import DetalleVentaRepository, VentaRepository
from backend.app.core.modules.ventas_pagos.schemas import EstadoPagoDTO, IntencionDTO


def _centavos(monto: Decimal) -> int:
    return int((Decimal(str(monto)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class StripeService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.venta_repo = VentaRepository(db)
        self.pago_repo = PagoRepository(db)
        self.detalle_repo = DetalleVentaRepository(db)
        self.pedido_repo = PedidoRepository(db)
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)

    async def _venta_digital(self, venta_id: uuid.UUID) -> Venta:
        venta = await self.venta_repo.buscarPorId(venta_id)
        if venta is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada")
        if venta.canal not in ("WEB", "MOVIL"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Solo ventas digitales usan Stripe")
        return venta

    def _autorizar_intencion(self, usuario: Usuario, venta: Venta) -> None:
        exigir_empresa_recurso(usuario, venta)
        if es_admin(usuario):
            return
        if rol_de(usuario) == "CLIENTE" and venta.cliente_id == usuario.id:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el propietario o el Administrador")

    async def crearIntencion(
        self, usuario: Usuario, venta_id: uuid.UUID, clave: uuid.UUID,
    ) -> Tuple[IntencionDTO, bool]:
        venta = await self._venta_digital(venta_id)
        self._autorizar_intencion(usuario, venta)
        estado = venta.estado if isinstance(venta.estado, str) else venta.estado.name
        if estado == "CANCELADA":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Venta cancelada: sin reintento")
        if estado == "PAGADA":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Venta ya pagada")
        if venta.expira_en is not None and venta.expira_en <= self.reloj.ahora():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ventana de pago vencida")
        if not settings.STRIPE_ENABLED or not settings.STRIPE_SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "codigo": "STRIPE_DESHABILITADO",
                    "mensaje": "Pasarela en modo prueba no configurada.",
                },
            )
        gw.exigir_test_mode()
        digest = hash_payload({"venta_id": str(venta_id)})
        try:
            existente = await self.pago_repo.buscarPorClave(clave)
            if existente is not None:
                if existente.hash_solicitud != digest:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "codigo": "IDEMPOTENCIA_CONFLICTO",
                            "mensaje": "Idempotency-Key ya usada con otra solicitud",
                        },
                    )
                if existente.venta_id != venta.id:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key pertenece a otra venta")
            cotizacion = await TasaCambioService(self.db).cotizar(Decimal(str(venta.total)))
            if cotizacion.centavos_usd <= 0:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El importe convertido no permite crear un pago Stripe")
            pago_previo = await self._pago_stripe_de_venta(venta.id)
            gateway = gw.obtener_gateway()
            referencia: Optional[str] = pago_previo.referencia_externa if pago_previo else None
            monto_usd = cotizacion.monto_usd
            if referencia:
                pi_vigente = await gateway.consultar_intencion(referencia)
                if pi_vigente.estado == "CANCELED":
                    referencia = None
                else:
                    try:
                        monto_usd = await self._validar_intencion_venta(venta, pi_vigente)
                    except HTTPException:
                        if pi_vigente.estado == "SUCCEEDED":
                            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El pago capturado requiere conciliación del importe")
                        await gateway.cancelar_intencion(referencia)
                        referencia = None
            inten = await gateway.crear_o_reutilizar_intencion(
                venta_id=str(venta.id),
                monto_centavos=cotizacion.centavos_usd,
                moneda="usd",
                idempotency_key=f"{clave}-bob-usd-{cotizacion.tasa_id}",
                referencia_existente=referencia,
                empresa_id=str(venta.empresa_id),
                metadata={
                    "tasa_id": str(cotizacion.tasa_id),
                    "monto_bob": str(Decimal(str(venta.total)).quantize(Decimal("0.01"))),
                    "centavos_usd": str(cotizacion.centavos_usd),
                },
            )
            await self._validar_intencion_venta(venta, inten)
            if referencia is None:
                monto_usd = cotizacion.monto_usd
            if pago_previo is not None:
                pago = pago_previo
                if pago.referencia_externa != inten.id:
                    pago.referencia_externa = inten.id
                    pago.estado = "PENDIENTE"
                    pago.pagado_en = None
                    await self.db.flush()
                elif pago.estado == "RECHAZADO":
                    pago.estado = "PENDIENTE"
                    await self.db.flush()
            else:
                pago = Pago(
                    contexto="VENTA", empresa_id=venta.empresa_id, reserva_id=None, venta_id=venta.id,
                    metodo="STRIPE_TEST", tipo_pago="PAGO",
                    monto=venta.total, no_reembolsable=False, estado="PENDIENTE",
                    referencia_externa=inten.id, proveedor_pago="STRIPE_TEST",
                    clave_idempotencia=clave, hash_solicitud=digest,
                )
                await self.pago_repo.crear(pago)
            await self.db.commit()
            return self._a_intencion(venta, pago, monto_usd, client_secret=inten.client_secret), pago_previo is None
        except HTTPException:
            await self.db.rollback()
            raise
        except IntegrityError as e:
            await self.db.rollback()
            msg = str(getattr(e, "orig", e)).lower()
            if "clave_idempotencia" in msg or "uq_pagos_referencia_externa" in msg:
                pago = await self.pago_repo.buscarPorClave(clave) or await self._pago_stripe_de_venta(venta_id)
                if pago is not None:
                    if pago.hash_solicitud != digest and "clave_idempotencia" in msg:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Idempotency-Key ya usada con otra solicitud",
                        )
                    venta_fresca = await self.venta_repo.buscarPorId(venta_id)
                    inten = await gw.obtener_gateway().consultar_intencion(pago.referencia_externa)
                    monto_usd = await self._validar_intencion_venta(venta_fresca, inten)
                    return self._a_intencion(venta_fresca, pago, monto_usd, client_secret=inten.client_secret), False
            raise

    def _a_intencion(self, venta: Venta, pago: Pago, monto_usd: Decimal, client_secret: Optional[str] = None) -> IntencionDTO:
        return IntencionDTO(
            payment_intent_id=pago.referencia_externa or "",
            venta_id=venta.id, monto=monto_usd,
            moneda="usd",
            estado=pago.estado, client_secret=client_secret,
        )

    async def _pago_stripe_de_venta(self, venta_id: uuid.UUID) -> Optional[Pago]:
        pagos = await self.pago_repo.pagosDeVenta(venta_id)
        for p in pagos:
            if p.metodo == "STRIPE_TEST":
                return p
        return None

    async def _validar_intencion_venta(self, venta: Venta, inten) -> Decimal:
        """Comprueba el cargo USD y la cotización congelada en Stripe Test."""
        meta = inten.metadata or {}
        if inten.venta_id != str(venta.id) or inten.moneda.lower() != "usd":
            raise HTTPException(status_code=409, detail="La intención no corresponde a la venta o moneda USD")
        if meta.get("tasa_id"):
            tasa = await self.db.execute(
                text("SELECT tasa_bob_por_usd FROM plataforma.tasas_cambio WHERE id = :id"),
                {"id": uuid.UUID(str(meta["tasa_id"]))},
            )
            tasa_val = tasa.scalar_one_or_none()
            if tasa_val is None or Decimal(str(tasa_val)) <= 0:
                raise HTTPException(status_code=409, detail="La tasa congelada no existe")
            esperado = _centavos(Decimal(str(venta.total)) / Decimal(str(tasa_val)))
            if (str(meta.get("empresa_id")) != str(venta.empresa_id)
                    or Decimal(str(meta.get("monto_bob", "0"))) != Decimal(str(venta.total))
                    or int(meta.get("centavos_usd", 0)) != esperado):
                raise HTTPException(status_code=409, detail="La cotización congelada no coincide con la venta")
        else:
            raise HTTPException(409, detail="CONCILIACION_REQUERIDA: cargo antiguo sin cotizacion original verificable")
        if inten.monto_centavos != esperado:
            raise HTTPException(status_code=409, detail="El importe Stripe no coincide con el total convertido")
        # Guardar la cotizacion original en la tabla existente, tambien para CU15.
        # El reembolso nunca reconstruye un cargo usando la tasa vigente.
        orden = (await self.db.execute(select(OrdenPago).where(
            OrdenPago.empresa_id == venta.empresa_id,
            OrdenPago.proveedor == "STRIPE", OrdenPago.referencia_externa == inten.id,
        ))).scalars().first()
        if orden is not None:
            if (orden.venta_id != venta.id or orden.monto_bob != venta.total or
                    orden.centavos_usd != esperado or str(orden.tasa_id) != str(meta["tasa_id"])):
                raise HTTPException(409, detail="CONCILIACION_REQUERIDA: cotizacion guardada contradictoria")
        else:
            orden = OrdenPago(
                empresa_id=venta.empresa_id, contexto="VENTA", venta_id=venta.id,
                proveedor="STRIPE", clave_externa="cu15:" + inten.id,
                referencia_externa=inten.id, estado="PENDIENTE", monto_bob=venta.total,
                tasa_id=uuid.UUID(str(meta["tasa_id"])),
                monto_usd=Decimal(esperado) / 100, centavos_usd=esperado,
            )
            self.db.add(orden)
        if inten.estado == "SUCCEEDED":
            if inten.capturado_centavos != esperado:
                raise HTTPException(409, detail="CONCILIACION_REQUERIDA: captura distinta del importe original")
            orden.estado = "CAPTURADO"
        await self.db.flush()
        return Decimal(esperado) / Decimal("100")

    async def estado(self, usuario: Usuario, venta_id: uuid.UUID) -> EstadoPagoDTO:
        venta = await self._venta_digital(venta_id)
        self._autorizar_intencion(usuario, venta)
        pago = await self._pago_stripe_de_venta(venta.id)
        if pago and pago.estado == "PENDIENTE" and pago.referencia_externa and venta.estado == "PENDIENTE_PAGO":
            inten = await gw.obtener_gateway().consultar_intencion(pago.referencia_externa)
            if inten.estado == "SUCCEEDED":
                await self._validar_intencion_venta(venta, inten)
                await self._aplicar_aprobado(venta.id, inten.id)
                await self.db.commit()
                await self.db.refresh(venta)
                await self.db.refresh(pago)
            elif inten.estado == "CANCELED":
                await self._aplicar_rechazo(venta.id, inten.id, "payment_intent.canceled")
                await self.db.commit()
                await self.db.refresh(pago)
        return EstadoPagoDTO(
            venta_id=venta.id,
            estado_venta=venta.estado if isinstance(venta.estado, str) else venta.estado.name,
            estado_pago=pago.estado if pago else "SIN_INTENCION",
            payment_intent_id=pago.referencia_externa if pago else None,
            monto=venta.total, expira_en=venta.expira_en,
        )

    async def confirmarWebhook(self, cuerpo_crudo: bytes, firma: Optional[str], evento: dict) -> dict:
        import hashlib

        try:
            gw.verificar_firma_stripe(cuerpo_crudo, firma, settings.STRIPE_WEBHOOK_SECRET or "")
        except gw.FirmaStripeInvalida as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Firma inválida: {e}")
        if evento.get("livemode") is True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "codigo": "STRIPE_MODO_NO_PERMITIDO",
                    "mensaje": "Evento live rechazado; solo Test Mode",
                },
            )
        tipo = str(evento.get("type", ""))
        tipos_soportados = {
            "payment_intent.succeeded",
            "payment_intent.payment_failed",
            "payment_intent.canceled",
            "setup_intent.succeeded",
        }
        if tipo not in tipos_soportados:
            return {"evento": tipo, "estado": "IGNORADO"}

        evt_id = str(evento.get("id", ""))
        if evt_id:
            stmt_evt = select(EventoProveedor).where(
                EventoProveedor.proveedor == "STRIPE",
                EventoProveedor.evento_externo_id == evt_id,
            )
            evt_prev = (await self.db.execute(stmt_evt)).scalars().first()
            if evt_prev is not None and evt_prev.estado == "PROCESADO":
                return {"evento": tipo, "estado": "APROBADO", "duplicado": True}

        objeto = evento.get("data", {}).get("object", {}) if isinstance(evento.get("data"), dict) else {}

        if tipo == "setup_intent.succeeded":
            seti_id = str(objeto.get("id", ""))
            if not seti_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Evento sin setup_intent")
            stmt_mp = select(MetodoPreparado).where(
                MetodoPreparado.proveedor == "STRIPE",
                MetodoPreparado.preparacion_proveedor_cifrado == seti_id.encode("utf-8"),
            )
            mp = (await self.db.execute(stmt_mp)).scalars().first()
            if mp is not None:
                cus = str(objeto.get("customer") or "")
                pm = str(objeto.get("payment_method") or "")
                if cus.startswith("cus_") and pm.startswith("pm_") and pm != "pm_no_adjunto":
                    mp.cliente_proveedor_cifrado = cus.encode("utf-8")
                    mp.metodo_proveedor_cifrado = pm.encode("utf-8")
                    mp.estado = "LISTO"
                    await self.db.flush()
                else:
                    return {"setup_intent": seti_id, "estado": "IGNORADO", "motivo": "DATOS_INCOMPLETOS"}

                if evt_id:
                    reg_evt = EventoProveedor(
                        id=uuid.uuid4(),
                        empresa_id=mp.empresa_id,
                        proveedor="STRIPE",
                        evento_externo_id=evt_id,
                        tipo=tipo,
                        payload_hash=hashlib.sha256(cuerpo_crudo).hexdigest(),
                        estado="PROCESADO",
                        recibido_en=self.reloj.ahora(),
                        procesado_en=self.reloj.ahora(),
                    )
                    self.db.add(reg_evt)
                await self.db.commit()
                return {"setup_intent": seti_id, "estado": "LISTO"}
            return {"setup_intent": seti_id, "estado": "IGNORADO"}

        pi_id = str(objeto.get("id", ""))
        if not pi_id:
            rel = evento.get("related_object", {}) if isinstance(evento.get("related_object"), dict) else {}
            pi_id = str(rel.get("id", ""))
        if not pi_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Evento sin payment_intent")
        try:
            pago = await self._pago_por_referencia(pi_id)
            if pago is None:
                # Buscar en comercial.ordenes_pago (CU22)
                stmt_op = select(OrdenPago).where(
                    OrdenPago.proveedor == "STRIPE",
                    OrdenPago.referencia_externa == pi_id,
                )
                op = (await self.db.execute(stmt_op)).scalars().first()
                if op is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intención no registrada")

                if tipo in ("payment_intent.succeeded",):
                    self._validar_intencion_con_orden(objeto, op)
                    await self._aplicar_aprobado_orden(op, pi_id)
                    if evt_id:
                        reg_evt = EventoProveedor(
                            id=uuid.uuid4(),
                            empresa_id=op.empresa_id,
                            orden_pago_id=op.id,
                            proveedor="STRIPE",
                            evento_externo_id=evt_id,
                            tipo=tipo,
                            payload_hash=hashlib.sha256(cuerpo_crudo).hexdigest(),
                            estado="PROCESADO",
                            recibido_en=self.reloj.ahora(),
                            procesado_en=self.reloj.ahora(),
                        )
                        self.db.add(reg_evt)
                    await self.db.commit()
                    return {"payment_intent": pi_id, "estado": "APROBADO"}
                if tipo in ("payment_intent.payment_failed", "payment_intent.canceled"):
                    await self._aplicar_rechazo_orden(op, pi_id, tipo)
                    if evt_id:
                        reg_evt = EventoProveedor(
                            id=uuid.uuid4(),
                            empresa_id=op.empresa_id,
                            orden_pago_id=op.id,
                            proveedor="STRIPE",
                            evento_externo_id=evt_id,
                            tipo=tipo,
                            payload_hash=hashlib.sha256(cuerpo_crudo).hexdigest(),
                            estado="PROCESADO",
                            recibido_en=self.reloj.ahora(),
                            procesado_en=self.reloj.ahora(),
                        )
                        self.db.add(reg_evt)
                    await self.db.commit()
                    return {"payment_intent": pi_id, "estado": "RECHAZADO"}
                return {"payment_intent": pi_id, "estado": "IGNORADO"}

            if (pago.referencia_externa or "") != pi_id:
                return {"payment_intent": pi_id, "estado": "IGNORADO"}
            if tipo in ("payment_intent.succeeded",):
                venta_webhook = await self._venta_digital(pago.venta_id)
                inten_webhook = await gw.obtener_gateway().consultar_intencion(pi_id)
                await self._validar_intencion_venta(venta_webhook, inten_webhook)
                await self._aplicar_aprobado(pago.venta_id, pi_id)
                if evt_id:
                    reg_evt = EventoProveedor(
                        id=uuid.uuid4(),
                        empresa_id=pago.empresa_id,
                        proveedor="STRIPE",
                        evento_externo_id=evt_id,
                        tipo=tipo,
                        payload_hash=hashlib.sha256(cuerpo_crudo).hexdigest(),
                        estado="PROCESADO",
                        recibido_en=self.reloj.ahora(),
                        procesado_en=self.reloj.ahora(),
                    )
                    self.db.add(reg_evt)
                await self.db.commit()
                return {"payment_intent": pi_id, "estado": "APROBADO"}
            if tipo in ("payment_intent.payment_failed", "payment_intent.canceled"):
                await self._aplicar_rechazo(pago.venta_id, pi_id, tipo)
                if evt_id:
                    reg_evt = EventoProveedor(
                        id=uuid.uuid4(),
                        empresa_id=pago.empresa_id,
                        proveedor="STRIPE",
                        evento_externo_id=evt_id,
                        tipo=tipo,
                        payload_hash=hashlib.sha256(cuerpo_crudo).hexdigest(),
                        estado="PROCESADO",
                        recibido_en=self.reloj.ahora(),
                        procesado_en=self.reloj.ahora(),
                    )
                    self.db.add(reg_evt)
                await self.db.commit()
                return {"payment_intent": pi_id, "estado": "RECHAZADO"}
            return {"payment_intent": pi_id, "estado": "IGNORADO"}
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def _pago_por_referencia(self, pi_id: str) -> Optional[Pago]:
        r = await self.db.execute(
            select(Pago).where(Pago.referencia_externa == pi_id, Pago.metodo == "STRIPE_TEST")
        )
        return r.scalars().first()

    async def _bloquear_venta(self, venta_id: uuid.UUID) -> Venta:
        await self.db.execute(
            select(Venta.id).where(Venta.id == venta_id).with_for_update()
        )
        venta = await self.venta_repo.buscarPorId(venta_id)
        if venta is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada")
        return venta

    @staticmethod
    def _estado(venta: Venta) -> str:
        return venta.estado if isinstance(venta.estado, str) else venta.estado.name

    async def _aplicar_aprobado(self, venta_id: uuid.UUID, pi_id: str) -> None:
        venta = await self._bloquear_venta(venta_id)
        estado = self._estado(venta)
        pago = await self._pago_por_referencia(pi_id)
        if pago is None:
            return
        if pago.estado == "APROBADO" and estado == "PAGADA":
            return
        if estado in ("CANCELADA", "DEVUELTA"):
            return
        if venta.expira_en is not None and venta.expira_en <= self.reloj.ahora() and estado != "PAGADA":
            return
        ahora = self.reloj.ahora()
        pago.estado = "APROBADO"
        pago.pagado_en = ahora
        await self.db.flush()
        detalles = await self.detalle_repo.porVenta(venta.id)
        claves = sorted(
            {(venta.sucursal_id, d.variante_id) for d in detalles},
            key=lambda c: (str(c[0]), str(c[1])),
        )
        filas = await self.inventario_repo.bloquearFilas(claves)
        for det in detalles:
            fila = filas.get((venta.sucursal_id, det.variante_id))
            if fila is None or fila.reservado < det.cantidad:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Compromiso insuficiente al confirmar el pago",
                )
            fila.reservado -= det.cantidad
            await self.db.flush()
            mov, _ = await self.movimiento_repo.registrarUnico(
                MovimientoInventario(
                    variante_id=det.variante_id,
                    sucursal_destino_id=venta.sucursal_id,
                    tipo="VENTA_DIGITAL",
                    cantidad=det.cantidad,
                    costo_unitario=det.costo_promedio,
                    referencia_tipo="VENTA",
                    referencia_id=venta.id,
                    linea_referencia_id=det.id,
                    observacion=f"Venta digital {venta.numero} aprobada ({pi_id})",
                )
            )
        venta.estado = "PAGADA"
        venta.confirmada_en = ahora
        await self.db.flush()
        pedido = await self.pedido_repo.buscarPorVenta(venta.id)
        if pedido is not None and pedido.estado == "SOLICITADO":
            pedido.estado = "PREPARADO"
            await self.db.flush()

    async def _aplicar_rechazo(self, venta_id: uuid.UUID, pi_id: str, tipo: str = "") -> None:
        venta = await self._bloquear_venta(venta_id)
        estado = self._estado(venta)
        pago = await self._pago_por_referencia(pi_id)
        if pago is None:
            return
        if pago.estado in ("APROBADO",):
            return
        if estado in ("PAGADA", "CANCELADA", "DEVUELTA"):
            return
        pago.estado = "RECHAZADO"
        await self.db.flush()

    async def _aplicar_aprobado_orden(self, op: OrdenPago, pi_id: str) -> None:
        ahora = self.reloj.ahora()
        if op.estado != "CAPTURADO":
            op.estado = "CAPTURADO"
            op.actualizada_en = ahora
            await self.db.flush()

        if op.contexto == "PEDIDO" and op.pedido_id:
            await self.confirmar_captura_pedido(op.pedido_id)
        elif op.contexto == "VENTA" and op.venta_id:
            r_c = await self.db.execute(
                text("SELECT canal FROM comercial.ventas WHERE id = :id"),
                {"id": op.venta_id},
            )
            if r_c.scalar() != "PRESENCIAL":
                await self._aplicar_aprobado(op.venta_id, pi_id)

    async def _aplicar_rechazo_orden(self, op: OrdenPago, pi_id: str, tipo: str = "") -> None:
        ahora = self.reloj.ahora()
        if op.estado != "FALLIDO":
            op.estado = "FALLIDO"
            op.actualizada_en = ahora
            await self.db.flush()

        if op.contexto == "PEDIDO" and op.pedido_id:
            from backend.app.core.modules.ventas_pagos.services.pedido_service import PedidoCompra
            pedido = await self.db.get(PedidoCompra, op.pedido_id)
            if pedido and pedido.estado_pago != "PAGADO":
                pedido.estado_pago = "FALLIDO"
                pedido.actualizado_en = ahora
                await self.db.flush()
        elif op.contexto == "VENTA" and op.venta_id:
            await self._aplicar_rechazo(op.venta_id, pi_id, tipo)

    async def confirmar_captura_pedido(self, pedido_id: uuid.UUID):
        from backend.app.core.modules.ventas_pagos.services.pedido_service import PedidoService
        svc = PedidoService(self.db, reloj=self.reloj)
        return await svc.confirmar_captura_pedido(pedido_id)

    async def cancelar_ventas_stripe_vencidas(
        self,
        lote: int = 100,
        ahora_param: Optional[datetime] = None,
        empresa_id: Optional[uuid.UUID] = None,
        venta_id: Optional[uuid.UUID] = None,
    ) -> dict:
        import asyncio

        try:
            lock = await self.db.execute(select(text("pg_try_advisory_lock(9100315)")))
            tiene = bool(lock.scalar())
        except Exception:
            tiene = True
        if not tiene:
            return {"procesadas": 0, "canceladas": [], "omitidas": [], "bloqueo_activo": False}
        ahora = ahora_param or self.reloj.ahora()
        canceladas, omitidas, errores = [], [], []
        procesadas = 0

        where_extra = ""
        params_base: dict = {"ahora": ahora, "lote": lote}
        if venta_id:
            where_extra += "AND id = :venta_id "
            params_base["venta_id"] = venta_id
        if empresa_id:
            where_extra += "AND empresa_id = :empresa_id "
            params_base["empresa_id"] = empresa_id

        for intento in range(5):
            r = await self.db.execute(
                text(
                    "SELECT id FROM comercial.ventas WHERE estado = 'PENDIENTE_PAGO' "
                    f"AND expira_en IS NOT NULL AND expira_en <= :ahora {where_extra}"
                    "ORDER BY expira_en LIMIT :lote FOR UPDATE SKIP LOCKED"
                ),
                params_base,
            )
            ids = [row[0] for row in r.all()]
            if not ids:
                restantes = await self.db.execute(
                    text(
                        "SELECT count(*) FROM comercial.ventas WHERE estado = 'PENDIENTE_PAGO' "
                        f"AND expira_en IS NOT NULL AND expira_en <= :ahora {where_extra}"
                    ),
                    params_base,
                )
                if int(restantes.scalar() or 0) == 0:
                    break
                await asyncio.sleep(0.05 * (intento + 1))
                continue
            procesadas += len(ids)
            break
        for vid in ids:
            try:
                venta = await self._bloquear_venta(uuid.UUID(str(vid)))
                if self._estado(venta) != "PENDIENTE_PAGO":
                    omitidas.append(str(vid))
                    continue

                # 1. Consultar Stripe si hay OrdenPago o Pago asociado
                stmt_op = select(OrdenPago).where(
                    OrdenPago.venta_id == venta.id,
                    OrdenPago.proveedor == "STRIPE",
                ).with_for_update()
                op = (await self.db.execute(stmt_op)).scalars().first()
                pago = await self._pago_stripe_de_venta(venta.id)

                ref_pi = (op.referencia_externa or op.clave_externa) if op else (pago.referencia_externa if pago else None)
                if ref_pi:
                    try:
                        gateway = gw.obtener_gateway()
                        inten = await gateway.consultar_intencion(ref_pi)
                        estado_pi = (inten.estado or "").upper()
                        if estado_pi in ("SUCCEEDED", "CAPTURADO"):
                            # El cobro fue capturado: validar rigurosamente con _validar_intencion_con_orden
                            try:
                                if op:
                                    self._validar_intencion_con_orden(inten, op)
                                    if op.estado != "CAPTURADO":
                                        op.estado = "CAPTURADO"
                                        op.actualizada_en = ahora
                                elif pago:
                                    await self._validar_intencion_venta(venta, inten)
                                if pago and pago.estado != "APROBADO":
                                    pago.estado = "APROBADO"
                                    pago.pagado_en = ahora
                                await self.db.flush()
                                await self.db.commit()
                            except Exception as val_err:
                                await self.db.rollback()
                                errores.append({"venta_id": str(vid), "error": f"Validacion intencion capturada fallida: {str(val_err)[:200]}"})
                            omitidas.append(str(vid))
                            continue

                        if estado_pi != "CANCELED":
                            try:
                                inten_canc = await gateway.cancelar_intencion(ref_pi)
                                estado_canc = (inten_canc.estado or "").upper()
                                if estado_canc != "CANCELED":
                                    if estado_canc in ("SUCCEEDED", "CAPTURADO"):
                                        try:
                                            if op:
                                                self._validar_intencion_con_orden(inten_canc, op)
                                                if op.estado != "CAPTURADO":
                                                    op.estado = "CAPTURADO"
                                                    op.actualizada_en = ahora
                                            elif pago:
                                                await self._validar_intencion_venta(venta, inten_canc)
                                            if pago and pago.estado != "APROBADO":
                                                pago.estado = "APROBADO"
                                                pago.pagado_en = ahora
                                            await self.db.flush()
                                            await self.db.commit()
                                        except Exception as val_err2:
                                            await self.db.rollback()
                                            errores.append({"venta_id": str(vid), "error": f"Validacion intencion fallida tras cancelar: {str(val_err2)[:200]}"})
                                    else:
                                        await self.db.rollback()
                                    omitidas.append(str(vid))
                                    continue
                            except HTTPException as he_canc:
                                if he_canc.status_code == 404:
                                    pass
                                elif he_canc.status_code == 400:
                                    try:
                                        inten_re = await gateway.consultar_intencion(ref_pi)
                                        if (inten_re.estado or "").upper() in ("SUCCEEDED", "CAPTURADO"):
                                            if op:
                                                self._validar_intencion_con_orden(inten_re, op)
                                                if op.estado != "CAPTURADO":
                                                    op.estado = "CAPTURADO"
                                                    op.actualizada_en = ahora
                                            elif pago:
                                                await self._validar_intencion_venta(venta, inten_re)
                                            if pago and pago.estado != "APROBADO":
                                                pago.estado = "APROBADO"
                                                pago.pagado_en = ahora
                                            await self.db.flush()
                                            await self.db.commit()
                                            omitidas.append(str(vid))
                                            continue
                                    except Exception as re_err:
                                        errores.append({"venta_id": str(vid), "error": f"Error reconsultando tras Stripe 400: {str(re_err)[:200]}"})
                                    await self.db.rollback()
                                    omitidas.append(str(vid))
                                    continue
                                else:
                                    await self.db.rollback()
                                    omitidas.append(str(vid))
                                    errores.append({"venta_id": str(vid), "error": f"HTTP {he_canc.status_code} al cancelar intencion"})
                                    continue
                            except Exception as ex_canc:
                                await self.db.rollback()
                                omitidas.append(str(vid))
                                errores.append({"venta_id": str(vid), "error": f"Excepcion al cancelar intencion: {str(ex_canc)[:200]}"})
                                continue

                    except HTTPException as he:
                        if he.status_code == 404:
                            pass
                        else:
                            await self.db.rollback()
                            omitidas.append(str(vid))
                            errores.append({"venta_id": str(vid), "error": f"HTTP {he.status_code} al consultar intencion"})
                            continue
                    except Exception as ex_cons:
                        await self.db.rollback()
                        omitidas.append(str(vid))
                        errores.append({"venta_id": str(vid), "error": f"Excepcion al consultar intencion: {str(ex_cons)[:200]}"})
                        continue

                # 2. Liberar inventario comprometido (digital o reservado)
                detalles = await self.detalle_repo.porVenta(venta.id)
                claves = sorted(
                    {(venta.sucursal_id, d.variante_id) for d in detalles},
                    key=lambda c: (str(c[0]), str(c[1])),
                )
                filas = await self.inventario_repo.bloquearFilas(claves)
                for det in detalles:
                    fila = filas.get((venta.sucursal_id, det.variante_id))
                    if fila is not None:
                        if fila.comprometido_digital >= det.cantidad:
                            fila.comprometido_digital -= det.cantidad
                            fila.disponible += det.cantidad
                        elif fila.reservado >= det.cantidad:
                            fila.reservado -= det.cantidad
                            fila.disponible += det.cantidad
                        await self.db.flush()
                    await self.movimiento_repo.registrarUnico(
                        MovimientoInventario(
                            variante_id=det.variante_id,
                            sucursal_destino_id=venta.sucursal_id,
                            tipo="LIBERACION_DIGITAL",
                            cantidad=det.cantidad,
                            costo_unitario=det.costo_promedio,
                            referencia_tipo="VENTA",
                            referencia_id=venta.id,
                            linea_referencia_id=det.id,
                            observacion=f"Liberación por vencimiento {venta.numero}",
                        )
                    )
                venta.estado = "CANCELADA"
                await self.db.flush()

                if op and op.estado not in ("CANCELADO", "FALLIDO"):
                    op.estado = "CANCELADO"
                    op.actualizada_en = ahora
                    await self.db.flush()

                if pago is not None and pago.estado == "PENDIENTE":
                    pago.estado = "ANULADO"
                    await self.db.flush()

                pedido = await self.pedido_repo.buscarPorVenta(venta.id)
                if pedido is not None and pedido.estado == "SOLICITADO":
                    pedido.estado = "CANCELADO"
                    await self.db.flush()

                await self.db.commit()
                canceladas.append(str(vid))
            except Exception as e:
                await self.db.rollback()
                errores.append({"venta_id": str(vid), "error": str(e)[:200]})
        try:
            await self.db.execute(select(text("pg_advisory_unlock(9100315)")))
        except Exception:
            pass
        return {
            "procesadas": procesadas, "canceladas": canceladas,
            "omitidas": omitidas, "errores": errores, "bloqueo_activo": True,
        }

    cancelarVencidas = cancelar_ventas_stripe_vencidas

    # =========================================================================
    # Capacidades E2 — CU22: SetupIntents, Órdenes y 3DS
    # =========================================================================

    async def preparar_metodo(
        self, usuario: Usuario, clave_idempotencia: uuid.UUID, huella_dispositivo: Optional[str] = None,
    ) -> MetodoPreparadoDTO:
        """Crea SetupIntent en pasarela y registra método preparado en comercial.metodos_preparados en estado PENDIENTE."""
        if not usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )
        gateway = gw.obtener_gateway()
        seti = await gateway.crear_setup_intent(
            cliente_id=str(usuario.id),
            idempotency_key=str(clave_idempotencia),
            empresa_id=str(usuario.empresa_id) if usuario.empresa_id else None,
        )

        p_cifrado = seti.id.encode("utf-8")
        c_cifrado = (seti.customer or "").encode("utf-8")
        m_cifrado = (seti.payment_method or "").encode("utf-8")

        mp = MetodoPreparado(
            id=uuid.uuid4(),
            empresa_id=usuario.empresa_id,
            cliente_id=usuario.id,
            proveedor="STRIPE",
            cliente_proveedor_cifrado=c_cifrado,
            metodo_proveedor_cifrado=m_cifrado,
            preparacion_proveedor_cifrado=p_cifrado,
            estado="PENDIENTE",
            creado_en=self.reloj.ahora(),
        )
        self.db.add(mp)
        await self.db.flush()
        await self.db.commit()

        return MetodoPreparadoDTO(
            preparacion_pago_id=mp.id,
            client_secret=seti.client_secret,
            estado="PENDIENTE",
            proveedor="STRIPE",
        )

    async def confirmar_metodo_preparado(
        self, usuario: Usuario, preparacion_pago_id: uuid.UUID, payment_method_id: Optional[str] = None,
    ) -> MetodoPreparadoDTO:
        """Consulta o confirma el SetupIntent en la pasarela; si está succeeded, almacena customer/payment_method y pasa a LISTO."""
        r = await self.db.execute(
            select(MetodoPreparado).where(
                MetodoPreparado.id == preparacion_pago_id,
            )
        )
        mp = r.scalars().first()
        if mp is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Método preparado no encontrado",
            )
        if mp.empresa_id != usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para confirmar método de otra empresa",
            )
        if rol_de(usuario) == "CLIENTE" and mp.cliente_id != usuario.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para confirmar este método preparado",
            )

        if mp.estado == "LISTO":
            return MetodoPreparadoDTO(
                preparacion_pago_id=mp.id,
                client_secret=None,
                estado="LISTO",
                proveedor=mp.proveedor,
            )

        gateway = gw.obtener_gateway()
        seti_id = mp.preparacion_proveedor_cifrado.decode("utf-8") if mp.preparacion_proveedor_cifrado else ""
        if not seti_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Método preparado carece de referencia SetupIntent",
            )

        # Confirmar en pasarela (o consultar si ya fue confirmado en frontend)
        if hasattr(gateway, "confirmar_setup_intent"):
            seti = await gateway.confirmar_setup_intent(seti_id, payment_method_id=payment_method_id)
        else:
            seti = await gateway.consultar_setup_intent(seti_id)

        # Validaciones de pertenencia del recurso
        if seti.cliente_id and str(seti.cliente_id) != str(mp.cliente_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El SetupIntent pertenece a otro cliente",
            )
        if seti.empresa_id and str(seti.empresa_id) != str(mp.empresa_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El SetupIntent pertenece a otra empresa",
            )
        cus_esperado = mp.cliente_proveedor_cifrado.decode("utf-8") if mp.cliente_proveedor_cifrado else ""
        if cus_esperado and seti.customer and seti.customer != cus_esperado:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El customer de Stripe pertenece a otro usuario o no coincide con el cliente esperado",
            )

        if seti.estado != "succeeded":
            return MetodoPreparadoDTO(
                preparacion_pago_id=mp.id,
                client_secret=seti.client_secret,
                estado="PENDIENTE",
                proveedor=mp.proveedor,
            )

        cus = seti.customer or ""
        pm = seti.payment_method or ""

        if not cus or not cus.startswith("cus_"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El SetupIntent confirmado no tiene un Customer de Stripe válido (cus_...)",
            )
        if cus_esperado and cus != cus_esperado:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El customer de Stripe pertenece a otro usuario o no coincide con el cliente esperado",
            )
        if not pm or not pm.startswith("pm_") or pm == "pm_no_adjunto":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El SetupIntent confirmado no tiene un PaymentMethod de Stripe válido o adjunto (pm_...)",
            )

        # Verificar que el PaymentMethod pertenece efectivamente a ese Customer en Stripe
        if hasattr(gateway, "consultar_payment_method"):
            pm_info = await gateway.consultar_payment_method(pm)
            pm_customer = pm_info.get("customer") if isinstance(pm_info, dict) else getattr(pm_info, "customer", None)
            if not pm_customer or pm_customer != cus:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El PaymentMethod no pertenece al Customer de Stripe o no está adjunto",
                )

        mp.cliente_proveedor_cifrado = cus.encode("utf-8")
        mp.metodo_proveedor_cifrado = pm.encode("utf-8")
        mp.estado = "LISTO"
        await self.db.flush()
        await self.db.commit()

        return MetodoPreparadoDTO(
            preparacion_pago_id=mp.id,
            client_secret=seti.client_secret,
            estado=mp.estado,
            proveedor=mp.proveedor,
        )

    async def obtener_metodo_preparado(
        self, usuario: Usuario, preparacion_pago_id: uuid.UUID,
    ) -> MetodoPreparadoDTO:
        r = await self.db.execute(
            select(MetodoPreparado).where(
                MetodoPreparado.id == preparacion_pago_id,
            )
        )
        mp = r.scalars().first()
        if mp is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Método preparado no encontrado",
            )
        if mp.empresa_id != usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para consultar método de otra empresa",
            )
        if rol_de(usuario) == "CLIENTE" and mp.cliente_id != usuario.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para consultar este método preparado",
            )
        return MetodoPreparadoDTO(
            preparacion_pago_id=mp.id,
            client_secret=None,
            estado=mp.estado,
            proveedor=mp.proveedor,
        )

    async def crear_orden_pago(
        self, usuario: Usuario, datos: OrdenPagoCrearDTO, clave_idempotencia: uuid.UUID, autocommit: bool = True,
    ) -> OrdenPagoDTO:
        """Crea orden de pago unificada calculando deuda en servidor y congelando tasa y USD."""
        if not usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )
        empresa_id = usuario.empresa_id

        # 1. Idempotencia: por proveedor y clave_externa
        r_ord = await self.db.execute(
            select(OrdenPago).where(
                OrdenPago.proveedor == "STRIPE",
                OrdenPago.clave_externa == str(clave_idempotencia),
            )
        )
        ord_existente = r_ord.scalars().first()
        if ord_existente is not None:
            return OrdenPagoDTO(
                orden_pago_id=ord_existente.id,
                estado=ord_existente.estado,
                monto_bob=Decimal(str(ord_existente.monto_bob)),
                monto_usd=Decimal(str(ord_existente.monto_usd)) if ord_existente.monto_usd else None,
                centavos_usd=ord_existente.centavos_usd,
                tasa_id=ord_existente.tasa_id,
                client_secret=None,
                referencia_externa=ord_existente.referencia_externa,
            )

        # 2. Derivar recurso y calcular deuda exacta por servidor (no confiar en cliente)
        contexto = datos.contexto.upper()
        pedido_id, reserva_id, venta_id, cambio_id = None, None, None, None
        monto_bob = Decimal("0.00")

        if contexto == "VENTA":
            r_v = await self.db.execute(
                text("SELECT id, empresa_id, cliente_id, total, estado, canal FROM comercial.ventas WHERE id = :id"),
                {"id": datos.recurso_id},
            )
            f_v = r_v.first()
            if not f_v:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada")
            if f_v[1] != empresa_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Venta de otra empresa")
            if rol_de(usuario) == "CLIENTE" and f_v[2] and f_v[2] != usuario.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")
            if f_v[4] != "PENDIENTE_PAGO":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La venta no está pendiente de pago",
                )
            monto_bob = Decimal(str(f_v[3]))
            venta_id = f_v[0]
        elif contexto == "PEDIDO":
            r_p = await self.db.execute(
                text("SELECT id, empresa_id, cliente_id, total_bob FROM comercial.pedidos_compra WHERE id = :id"),
                {"id": datos.recurso_id},
            )
            f_p = r_p.first()
            if f_p:
                if f_p[1] != empresa_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pedido de otra empresa")
                if rol_de(usuario) == "CLIENTE" and f_p[2] != usuario.id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")
                monto_bob = Decimal(str(f_p[3]))
                pedido_id = f_p[0]
            else:
                # Buscar en pedidos_entrega / venta asociada
                r_pe = await self.db.execute(
                    text(
                        "SELECT pe.id, v.empresa_id, pe.cliente_id, v.total, v.id "
                        "FROM comercial.pedidos_entrega pe JOIN comercial.ventas v ON pe.venta_id = v.id "
                        "WHERE pe.id = :id"
                    ),
                    {"id": datos.recurso_id},
                )
                f_pe = r_pe.first()
                if not f_pe:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
                if f_pe[1] != empresa_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pedido de otra empresa")
                monto_bob = Decimal(str(f_pe[3]))
                venta_id = f_pe[4]
                contexto = "VENTA"
        elif contexto == "RESERVA":
            r_r = await self.db.execute(
                text("SELECT id, empresa_id, cliente_id, total FROM comercial.reservas WHERE id = :id"),
                {"id": datos.recurso_id},
            )
            f_r = r_r.first()
            if not f_r:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
            if f_r[1] != empresa_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reserva de otra empresa")
            monto_bob = Decimal(str(f_r[3]))
            reserva_id = f_r[0]
        elif contexto == "CAMBIO":
            r_c = await self.db.execute(
                text("SELECT id, empresa_id, cliente_id, diferencia_bob FROM comercial.cambios WHERE id = :id"),
                {"id": datos.recurso_id},
            )
            f_c = r_c.first()
            if not f_c:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cambio no encontrado")
            if f_c[1] != empresa_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cambio de otra empresa")
            monto_bob = Decimal(str(f_c[3]))
            cambio_id = f_c[0]
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Contexto inválido {contexto}")

        # 3. Tasa de cambio BOB/USD congelada
        r_tasa = await self.db.execute(
            text("SELECT id, tasa_bob_por_usd FROM plataforma.tasas_cambio ORDER BY vigente_desde DESC LIMIT 1")
        )
        f_tasa = r_tasa.first()
        if not f_tasa or f_tasa[1] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No existe tasa de cambio vigente en el sistema para cotizar el pago",
            )
        tasa_id = f_tasa[0]
        tasa_val = Decimal(str(f_tasa[1]))

        monto_usd = (monto_bob / tasa_val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        centavos_usd = int(monto_usd * 100)

        # 4. Llamada a pasarela
        gateway = gw.obtener_gateway()
        off_session = bool(datos.metodo_preparado_id)
        customer_id: Optional[str] = None
        payment_method_id: Optional[str] = None

        if off_session and datos.metodo_preparado_id:
            stmt_mp = select(MetodoPreparado).where(
                MetodoPreparado.id == datos.metodo_preparado_id,
                MetodoPreparado.empresa_id == empresa_id,
            )
            mp = (await self.db.execute(stmt_mp)).scalars().first()
            if mp is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Método preparado no encontrado",
                )
            if mp.estado != "LISTO":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "codigo": "METODO_NO_LISTO",
                        "mensaje": "El método de pago preparado no está listo ni confirmado",
                    },
                )
            customer_id = mp.cliente_proveedor_cifrado.decode("utf-8") if mp.cliente_proveedor_cifrado else None
            payment_method_id = mp.metodo_proveedor_cifrado.decode("utf-8") if mp.metodo_proveedor_cifrado else None
            if not customer_id or not payment_method_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "codigo": "METODO_INCOMPLETO",
                        "mensaje": "El método de pago preparado carece de customer o payment_method real",
                    },
                )

        inten = await gateway.crear_pago_conectado(
            recurso_id=str(datos.recurso_id),
            monto_centavos=centavos_usd,
            moneda="usd",
            idempotency_key=str(clave_idempotencia),
            metodo_preparado_id=str(datos.metodo_preparado_id) if datos.metodo_preparado_id else None,
            off_session=off_session,
            customer_id=customer_id,
            payment_method_id=payment_method_id,
            metadata={
                "empresa_id": str(empresa_id),
                **(
                    {"venta_id": str(venta_id)} if contexto == "VENTA" and venta_id else
                    {"pedido_id": str(pedido_id)} if contexto == "PEDIDO" and pedido_id else
                    {"reserva_id": str(reserva_id)} if contexto == "RESERVA" and reserva_id else
                    {"cambio_id": str(cambio_id)} if contexto == "CAMBIO" and cambio_id else {}
                ),
            },
        )

        estado_orden = "PENDIENTE"
        if inten.estado == "REQUIRES_ACTION":
            estado_orden = "REQUIERE_ACCION_CLIENTE"
        elif inten.estado == "SUCCEEDED":
            estado_orden = "CAPTURADO"

        nueva_orden = OrdenPago(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            contexto=contexto,
            pedido_id=pedido_id,
            reserva_id=reserva_id,
            venta_id=venta_id,
            cambio_id=cambio_id,
            proveedor="STRIPE",
            clave_externa=str(clave_idempotencia),
            referencia_externa=inten.id,
            estado=estado_orden,
            monto_bob=monto_bob,
            tasa_id=tasa_id,
            monto_usd=monto_usd,
            centavos_usd=centavos_usd,
            revision=1,
            creada_en=self.reloj.ahora(),
            actualizada_en=self.reloj.ahora(),
        )
        self.db.add(nueva_orden)
        await self.db.flush()

        try:
            self._validar_intencion_con_orden(inten, nueva_orden)
        except HTTPException as exc:
            # Stripe ya devolviÃ³ una referencia. Conservarla en estado
            # pendiente para conciliaciÃ³n, sin declarar el cobro exitoso.
            nueva_orden.estado = "PENDIENTE"
            await self.db.flush()
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Stripe devolviÃ³ una intenciÃ³n que no pudo vincularse de forma segura con la orden; queda pendiente de conciliaciÃ³n.",
            ) from exc

        if estado_orden == "CAPTURADO":
            if contexto == "PEDIDO" and pedido_id:
                await self.confirmar_captura_pedido(pedido_id)
            elif contexto == "VENTA" and venta_id:
                r_c = await self.db.execute(
                    text("SELECT canal FROM comercial.ventas WHERE id = :id"),
                    {"id": venta_id},
                )
                if r_c.scalar() != "PRESENCIAL":
                    await self._aplicar_aprobado(venta_id, inten.id)

        if autocommit:
            await self.db.commit()

        return OrdenPagoDTO(
            orden_pago_id=nueva_orden.id,
            estado=nueva_orden.estado,
            monto_bob=monto_bob,
            monto_usd=monto_usd,
            centavos_usd=centavos_usd,
            tasa_id=tasa_id,
            client_secret=inten.client_secret,
            referencia_externa=nueva_orden.referencia_externa,
        )

    async def _validar_propiedad_orden(self, usuario: Usuario, op: OrdenPago) -> None:
        if op.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Orden de pago pertenece a otra empresa")
        if rol_de(usuario) == "CLIENTE":
            cliente_id_orden = None
            if op.contexto == "VENTA" and op.venta_id:
                v = await self.venta_repo.buscarPorId(op.venta_id)
                if v:
                    cliente_id_orden = v.cliente_id
            elif op.contexto == "PEDIDO" and op.pedido_id:
                from backend.app.core.modules.ventas_pagos.services.pedido_service import PedidoCompra
                p = await self.db.get(PedidoCompra, op.pedido_id)
                if p:
                    cliente_id_orden = p.cliente_id
            elif op.contexto == "RESERVA" and op.reserva_id:
                from backend.app.core.modules.reservas_traslados.models import Reserva
                res = await self.db.get(Reserva, op.reserva_id)
                if res:
                    cliente_id_orden = res.cliente_id
            elif op.contexto == "CAMBIO" and op.cambio_id:
                from backend.app.core.modules.posventa.services.cambio_service import Cambio
                c = await self.db.get(Cambio, op.cambio_id)
                if c:
                    cliente_id_orden = c.cliente_id

            if cliente_id_orden is not None and cliente_id_orden != usuario.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado para acceder a esta orden de pago")

    def _validar_intencion_con_orden(
        self, inten, op: OrdenPago, referencia_esperada: Optional[str] = None
    ) -> None:
        """Rutina compartida de validación financiera rigurosa (P0-3 / Auditoría 39 y 42).

        Valida:
        1. ID de intención coincide con referencia_externa o clave_externa de la orden.
        2. Moneda es 'usd'.
        3. Monto en centavos coincide con centavos_usd si está definido.
        4. Metadata empresa_id coincide con op.empresa_id.
        5. Metadata de recurso (venta_id / pedido_id) coincide con el recurso de la orden.
        Lanza HTTPException(400) si hay discrepancia.
        """
        ref_esperada = [
            r
            for r in (op.referencia_externa, op.clave_externa, referencia_esperada)
            if r and not str(r).startswith("PENDIENTE_")
        ]

        if isinstance(inten, dict):
            inten_id = inten.get("id")
            moneda = inten.get("currency") if "currency" in inten else inten.get("moneda")
            centavos = inten.get("amount") if "amount" in inten else inten.get("monto_centavos")
            meta = inten.get("metadata")
        else:
            inten_id = getattr(inten, "id", None)
            moneda = getattr(inten, "moneda", None)
            if moneda is None:
                moneda = getattr(inten, "currency", None)
            centavos = getattr(inten, "monto_centavos", None) if hasattr(inten, "monto_centavos") and getattr(inten, "monto_centavos") is not None else getattr(inten, "amount", None)
            meta = getattr(inten, "metadata", None)

        if not inten_id or str(inten_id) not in {str(r) for r in ref_esperada}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Datos del PaymentIntent no coinciden con la orden: ID no coincide",
            )
        if not moneda or str(moneda).lower() != "usd":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Datos del PaymentIntent no coinciden con la orden: Moneda no coincide (requiere USD)",
            )
        if (
            op.centavos_usd is None
            or not isinstance(centavos, int)
            or isinstance(centavos, bool)
            or centavos <= 0
            or op.centavos_usd <= 0
            or centavos != op.centavos_usd
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Datos del PaymentIntent no coinciden con la orden: Monto en centavos ({centavos}) no coincide ({op.centavos_usd})",
            )

        if not isinstance(meta, dict):
            meta = {}
        inten_empresa = meta.get("empresa_id")
        if not inten_empresa or str(inten_empresa) != str(op.empresa_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Datos del PaymentIntent no coinciden con la orden: Metadata empresa_id falta o no coincide",
            )

        campos_recurso = {
            "VENTA": ("venta_id",),
            "PEDIDO": ("pedido_id", "recurso_id"),
            "RESERVA": ("reserva_id", "recurso_id"),
            "CAMBIO": ("cambio_id", "recurso_id"),
        }
        campo_esperado = {
            "VENTA": op.venta_id,
            "PEDIDO": op.pedido_id,
            "RESERVA": op.reserva_id,
            "CAMBIO": op.cambio_id,
        }.get(op.contexto)
        campos = campos_recurso.get(op.contexto)
        if not campos or campo_esperado is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La orden no tiene un contexto y recurso válidos para verificar el PaymentIntent",
            )
        valores_recurso = [meta.get(campo) for campo in campos if meta.get(campo)]
        if not valores_recurso or any(str(valor) != str(campo_esperado) for valor in valores_recurso):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Datos del PaymentIntent no coinciden con la orden: metadata "
                    f"{'/'.join(campos)} falta o no coincide"
                ),
            )

    async def obtener_orden_pago(self, usuario: Usuario, orden_pago_id: uuid.UUID) -> OrdenPagoDTO:
        r = await self.db.execute(
            select(OrdenPago).where(
                OrdenPago.id == orden_pago_id,
            )
        )
        op = r.scalars().first()
        if op is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de pago no encontrada")
        await self._validar_propiedad_orden(usuario, op)
        return OrdenPagoDTO(
            orden_pago_id=op.id,
            estado=op.estado,
            monto_bob=Decimal(str(op.monto_bob)),
            monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd else None,
            centavos_usd=op.centavos_usd,
            tasa_id=op.tasa_id,
            client_secret=None,
            referencia_externa=op.referencia_externa,
        )

    async def obtener_orden_activa_caja(
        self,
        usuario: Usuario,
        sucursal_id: uuid.UUID,
        turno_caja_id: Optional[uuid.UUID] = None,
    ) -> Optional[OrdenActivaCajaDTO]:
        """Recupera la orden de pago activa (PENDIENTE o CAPTURADO) del cajero en esa sucursal/turno (H4 / P0-2).
        Deriva procedencia, líneas recuperadas y tasa congelada, y verifica contra la pasarela Stripe.
        """
        stmt = (
            select(OrdenPago, Venta)
            .join(Venta, OrdenPago.venta_id == Venta.id)
            .where(
                OrdenPago.empresa_id == usuario.empresa_id,
                Venta.empresa_id == usuario.empresa_id,
                OrdenPago.proveedor == "STRIPE",
                OrdenPago.estado.in_(["PENDIENTE", "CAPTURADO", "REQUIERE_ACCION_CLIENTE"]),
                Venta.sucursal_id == sucursal_id,
                Venta.estado == "PENDIENTE_PAGO",
            )
        )
        if not es_admin(usuario):
            stmt = stmt.where(Venta.cajero_id == usuario.id)
        if turno_caja_id:
            stmt = stmt.where(Venta.turno_caja_id == turno_caja_id)
        stmt = stmt.order_by(OrdenPago.creada_en.desc(), OrdenPago.id.desc()).limit(1)

        r = await self.db.execute(stmt)
        fila = r.first()
        if fila is None:
            return None

        op, venta = fila[0], fila[1]

        procedencia = "TURNO_OFFLINE" if venta.turno_caja_id is not None else "PRESENCIAL"

        # Recuperar líneas de la venta
        lineas_dto: list[LineaRecuperadaCajaDTO] = []
        try:
            from backend.app.core.modules.catalogo.models import Producto, VarianteProducto
            stmt_det = (
                select(
                    DetalleVenta.variante_id,
                    DetalleVenta.cantidad,
                    DetalleVenta.precio_unitario,
                    DetalleVenta.descuento,
                    VarianteProducto.sku,
                    Producto.nombre,
                )
                .select_from(DetalleVenta)
                .outerjoin(VarianteProducto, DetalleVenta.variante_id == VarianteProducto.id)
                .outerjoin(Producto, VarianteProducto.producto_id == Producto.id)
                .where(DetalleVenta.venta_id == venta.id)
            )
            res_det = await self.db.execute(stmt_det)
            for f_det in res_det.all():
                lineas_dto.append(
                    LineaRecuperadaCajaDTO(
                        variante_id=f_det[0],
                        cantidad=int(f_det[1]),
                        precio_unitario_bob=Decimal(str(f_det[2])),
                        descuento_bob=Decimal(str(f_det[3] or 0)),
                        sku=f_det[4],
                        nombre_producto=f_det[5],
                    )
                )
        except Exception:
            detalles = await self.detalle_repo.porVenta(venta.id)
            for d in detalles:
                lineas_dto.append(
                    LineaRecuperadaCajaDTO(
                        variante_id=d.variante_id,
                        cantidad=int(d.cantidad),
                        precio_unitario_bob=Decimal(str(d.precio_unitario)),
                        descuento_bob=Decimal(str(d.descuento or 0)),
                    )
                )

        # Recuperar tasa de cambio congelada
        tasa_bob_por_usd: Optional[Decimal] = None
        if op.tasa_id:
            from backend.app.core.modules.organizacion.models import TasaCambio
            tasa = await self.db.get(TasaCambio, op.tasa_id)
            if tasa and tasa.tasa_bob_por_usd is not None:
                tasa_bob_por_usd = Decimal(str(tasa.tasa_bob_por_usd))
        if tasa_bob_por_usd is None and op.monto_usd and op.monto_usd > 0 and op.monto_bob:
            tasa_bob_por_usd = (Decimal(str(op.monto_bob)) / Decimal(str(op.monto_usd))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        es_provisional = bool(
            (op.clave_externa and op.clave_externa.startswith("PENDIENTE_"))
            or (op.referencia_externa and op.referencia_externa.startswith("PENDIENTE_"))
        )
        client_secret = None
        stripe_pi_id = None if es_provisional else (op.referencia_externa or op.clave_externa)

        if es_provisional:
            estado_verificacion = "PROVISIONAL_PENDIENTE_INTENTO"
        else:
            estado_verificacion = "VERIFICADO"
            ref_pi = stripe_pi_id
            if ref_pi:
                try:
                    gateway = gw.obtener_gateway()
                    inten = await gateway.consultar_intencion(ref_pi)
                    estado_pi = (inten.estado or "").upper()

                    if estado_pi in ("SUCCEEDED", "CAPTURADO"):
                        self._validar_intencion_con_orden(inten, op)
                        if op.estado != "CAPTURADO":
                            op.estado = "CAPTURADO"
                            op.actualizada_en = self.reloj.ahora()
                            await self.db.flush()
                            await self.db.commit()
                    else:
                        if op.estado != "CAPTURADO":
                            client_secret = inten.client_secret
                except HTTPException as he:
                    if he.status_code == status.HTTP_400_BAD_REQUEST:
                        raise
                    estado_verificacion = "NO_VERIFICADO_ERROR_PASARELA"
                except Exception:
                    estado_verificacion = "NO_VERIFICADO_ERROR_PASARELA"

        return OrdenActivaCajaDTO(
            orden_pago_id=op.id,
            venta_id=venta.id,
            stripe_payment_intent_id=stripe_pi_id,
            client_secret=client_secret,
            monto_bob=Decimal(str(op.monto_bob)),
            monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd is not None else None,
            centavos_usd=op.centavos_usd,
            tasa_bob_por_usd=tasa_bob_por_usd,
            estado_orden=op.estado,
            estado=op.estado,
            sucursal_id=venta.sucursal_id,
            turno_caja_id=venta.turno_caja_id,
            cliente_id=venta.cliente_id,
            procedencia=procedencia,
            lineas=lineas_dto,
            estado_verificacion=estado_verificacion,
            provisional=es_provisional,
        )

    async def confirmar_orden_pago(
        self, usuario: Usuario, orden_pago_id: uuid.UUID
    ) -> OrdenPagoDTO:
        """Sincroniza y confirma una OrdenPago PENDIENTE o REQUIERE_ACCION_CLIENTE consultando la pasarela Stripe."""
        r = await self.db.execute(
            select(OrdenPago).where(
                OrdenPago.id == orden_pago_id,
            ).with_for_update()
        )
        op = r.scalars().first()
        if op is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de pago no encontrada")
        await self._validar_propiedad_orden(usuario, op)

        if op.estado == "CAPTURADO":
            return OrdenPagoDTO(
                orden_pago_id=op.id,
                estado=op.estado,
                monto_bob=Decimal(str(op.monto_bob)),
                monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd else None,
                centavos_usd=op.centavos_usd,
                tasa_id=op.tasa_id,
                client_secret=None,
                referencia_externa=op.referencia_externa,
            )

        ref_pi = op.referencia_externa or op.clave_externa
        if not ref_pi:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Falta referencia de PaymentIntent en la orden")

        gateway = gw.obtener_gateway()
        try:
            inten = await gateway.consultar_intencion(ref_pi)
        except Exception:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No se pudo consultar el estado de la intención en Stripe")

        ahora = self.reloj.ahora()
        if inten.estado.upper() in ("SUCCEEDED", "CAPTURADO"):
            # Validaciones rigurosas antes de transicionar a CAPTURADO (Auditoría 33 / P0-3)
            self._validar_intencion_con_orden(inten, op)

            op.estado = "CAPTURADO"
            op.actualizada_en = ahora
            await self.db.flush()

            if op.contexto == "PEDIDO" and op.pedido_id:
                await self.confirmar_captura_pedido(op.pedido_id)
            elif op.contexto == "VENTA" and op.venta_id:
                r_c = await self.db.execute(
                    text("SELECT canal FROM comercial.ventas WHERE id = :id"),
                    {"id": op.venta_id},
                )
                if r_c.scalar() != "PRESENCIAL":
                    await self._aplicar_aprobado(op.venta_id, ref_pi)
        elif inten.estado.upper() == "REQUIRES_ACTION":
            op.estado = "REQUIERE_ACCION_CLIENTE"
            op.actualizada_en = ahora
            await self.db.flush()
        elif inten.estado.upper() in ("CANCELED", "FAILED"):
            op.estado = "FALLIDO"
            op.actualizada_en = ahora
            await self.db.flush()

        await self.db.commit()

        return OrdenPagoDTO(
            orden_pago_id=op.id,
            estado=op.estado,
            monto_bob=Decimal(str(op.monto_bob)),
            monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd else None,
            centavos_usd=op.centavos_usd,
            tasa_id=op.tasa_id,
            client_secret=inten.client_secret,
            referencia_externa=op.referencia_externa,
        )

    async def _consultar_intencion_orden_sin_bloqueos(self, op, venta_snapshot=None):
        """Recupera y valida el PaymentIntent real sin mantener bloqueos DB."""
        es_provisional = bool(
            (op.clave_externa and str(op.clave_externa).startswith("PENDIENTE_"))
            or (op.referencia_externa and str(op.referencia_externa).startswith("PENDIENTE_"))
        )
        gateway = gw.obtener_gateway()
        if es_provisional:
            if op.contexto != "VENTA" or not op.venta_id or not venta_snapshot:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La orden provisional no tiene una venta durable que permita conciliar Stripe.",
                )
            clave = venta_snapshot.get("clave_idempotencia")
            if not clave:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La venta provisional no conserva una clave idempotente; no se puede liberar inventario con seguridad.",
                )
            metadata = {
                "empresa_id": str(op.empresa_id),
                "venta_id": str(op.venta_id),
                "cliente_id": str(venta_snapshot.get("cliente_id") or ""),
            }
            try:
                creada = await gateway.crear_o_reutilizar_intencion(
                    venta_id=str(op.venta_id),
                    monto_centavos=op.centavos_usd or 0,
                    moneda="usd",
                    idempotency_key=str(clave),
                    empresa_id=str(op.empresa_id),
                    metadata=metadata,
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="No se pudo recuperar el PaymentIntent de la orden provisional; se conserva venta e inventario para reintento.",
                ) from exc
            ref_pi = str(getattr(creada, "id", "") or "")
        else:
            ref_pi = str(op.referencia_externa or "")
            if not ref_pi or ref_pi.startswith("PENDIENTE_"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La orden no tiene un PaymentIntent identificable; se conserva pendiente para conciliacion.",
                )

        if not ref_pi.startswith("pi_"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="La pasarela no devolvio un identificador PaymentIntent valido; se conserva el inventario pendiente.",
            )
        try:
            inten = await gateway.consultar_intencion(ref_pi)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No se pudo consultar Stripe; se conserva la orden y el inventario para reintento.",
            ) from exc
        if not inten or str(getattr(inten, "id", "")) != ref_pi:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Stripe devolvio una intencion distinta a la solicitada; se conserva la orden pendiente.",
            )
        try:
            self._validar_intencion_con_orden(inten, op, referencia_esperada=ref_pi)
        except HTTPException as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Stripe devolvio datos que no corresponden a la orden; se conserva para conciliacion.",
            ) from exc
        return inten, ref_pi, es_provisional

    async def cancelar_orden_pago(
        self, usuario: Usuario, orden_pago_id: uuid.UUID
    ) -> OrdenPagoDTO:
        """Cancela una orden solo con evidencia terminal de Stripe.

        La consulta/creacion/cancelacion remota ocurre sin bloqueos de fila.
        La transicion local y eventual liberacion de stock se aplican bajo
        bloqueos solo despues de confirmar el PI correcto en estado CANCELED.
        """
        r = await self.db.execute(select(OrdenPago).where(OrdenPago.id == orden_pago_id))
        op = r.scalars().first()
        if op is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de pago no encontrada")
        await self._validar_propiedad_orden(usuario, op)
        if op.estado == "CAPTURADO":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se puede cancelar una orden con fondos capturados; liquide la venta o tramite reembolso CU27",
            )
        if op.estado == "CANCELADO":
            return OrdenPagoDTO(
                orden_pago_id=op.id,
                estado=op.estado,
                monto_bob=Decimal(str(op.monto_bob)),
                monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd else None,
                centavos_usd=op.centavos_usd,
                tasa_id=op.tasa_id,
                client_secret=None,
                referencia_externa=op.referencia_externa,
            )

        venta_snapshot = None
        if op.contexto == "VENTA" and op.venta_id:
            venta = await self.db.get(Venta, op.venta_id)
            if venta is not None:
                venta_snapshot = {
                    "id": venta.id,
                    "clave_idempotencia": venta.clave_idempotencia,
                    "cliente_id": venta.cliente_id,
                }
        op_snapshot = SimpleNamespace(
            id=op.id,
            contexto=op.contexto,
            empresa_id=op.empresa_id,
            referencia_externa=op.referencia_externa,
            clave_externa=op.clave_externa,
            centavos_usd=op.centavos_usd,
            venta_id=op.venta_id,
            pedido_id=op.pedido_id,
            reserva_id=op.reserva_id,
            cambio_id=op.cambio_id,
        )
        # El SELECT anterior no bloquea filas; cerrar su transaccion antes de
        # esperar al proveedor evita retener conexion durante la llamada remota.
        await self.db.rollback()
        inten, ref_pi, es_provisional = await self._consultar_intencion_orden_sin_bloqueos(op_snapshot, venta_snapshot)
        estado = str(inten.estado or "").upper()

        if estado in ("SUCCEEDED", "CAPTURADO"):
            inten_final = inten
        elif estado == "CANCELED":
            inten_final = inten
        else:
            gateway = gw.obtener_gateway()
            try:
                inten_final = await gateway.cancelar_intencion(ref_pi)
            except Exception as exc:
                # Resolver carreras: si la cancelacion choco con una captura,
                # consultar el estado final antes de decidir la transicion.
                try:
                    inten_final = await gateway.consultar_intencion(ref_pi)
                except Exception as consulta_exc:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Stripe no confirmo la cancelacion; venta e inventario permanecen pendientes.",
                    ) from consulta_exc
            if str(getattr(inten_final, "id", "")) != ref_pi:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Stripe devolvio un PaymentIntent distinto; venta e inventario permanecen pendientes.",
                )
            try:
                self._validar_intencion_con_orden(inten_final, op_snapshot, referencia_esperada=ref_pi)
            except HTTPException as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Stripe devolvio datos que no corresponden a la orden durante la cancelacion; se conserva pendiente.",
                ) from exc
        estado_final = str(inten_final.estado or "").upper()
        if estado_final not in ("CANCELED", "SUCCEEDED", "CAPTURADO"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Stripe no confirmo un estado terminal seguro ({estado_final}); venta e inventario permanecen pendientes.",
            )

        # Releer bajo bloqueo y comprobar que la orden no cambio durante la
        # llamada remota. Una cancelacion/captura concurrente no duplica Kardex.
        r = await self.db.execute(
            select(OrdenPago).where(OrdenPago.id == orden_pago_id).with_for_update()
        )
        op = r.scalars().first()
        if op is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de pago no encontrada")
        await self._validar_propiedad_orden(usuario, op)
        if op.estado == "CANCELADO":
            if estado_final in ("SUCCEEDED", "CAPTURADO"):
                op.estado = "CAPTURADO"
                if es_provisional:
                    op.clave_externa = ref_pi
                    op.referencia_externa = ref_pi
                op.actualizada_en = self.reloj.ahora()
                await self.db.commit()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Stripe confirma captura despues de cancelacion local; la orden queda capturada y el inventario se conserva.",
                )
            return OrdenPagoDTO(
                orden_pago_id=op.id,
                estado=op.estado,
                monto_bob=Decimal(str(op.monto_bob)),
                monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd else None,
                centavos_usd=op.centavos_usd,
                tasa_id=op.tasa_id,
                client_secret=None,
                referencia_externa=op.referencia_externa,
            )
        if op.estado == "CAPTURADO" and estado_final not in ("SUCCEEDED", "CAPTURADO"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La orden ya fue capturada; no se libera inventario")
        ref_actual = op.referencia_externa or op.clave_externa
        if not es_provisional and ref_actual != ref_pi:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La orden cambio durante la conciliacion; reintente")
        if es_provisional and ref_actual and not ref_actual.startswith("PENDIENTE_") and ref_actual != ref_pi:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Otra reanudacion vinculo un PaymentIntent distinto")

        if es_provisional:
            op.clave_externa = ref_pi
            op.referencia_externa = ref_pi
        op.actualizada_en = self.reloj.ahora()

        if estado_final in ("SUCCEEDED", "CAPTURADO"):
            op.estado = "CAPTURADO"
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stripe confirma fondos capturados; liquide la venta o tramite reembolso CU27.",
            )

        op.estado = "CANCELADO"
        await self.db.flush()
        if op.contexto == "VENTA" and op.venta_id:
            stmt_v = select(Venta).where(Venta.id == op.venta_id).with_for_update()
            v = (await self.db.execute(stmt_v)).scalars().first()
            if v and v.estado == "PENDIENTE_PAGO":
                v.estado = "CANCELADA"
                await self.db.flush()
                detalles = await self.detalle_repo.porVenta(v.id)
                claves = sorted(
                    {(v.sucursal_id, d.variante_id) for d in detalles},
                    key=lambda c: (str(c[0]), str(c[1])),
                )
                filas = await self.inventario_repo.bloquearFilas(claves)
                for det in detalles:
                    fila = filas.get((v.sucursal_id, det.variante_id))
                    if fila is not None:
                        if fila.comprometido_digital >= det.cantidad:
                            fila.comprometido_digital -= det.cantidad
                            fila.disponible += det.cantidad
                        elif fila.reservado >= det.cantidad:
                            fila.reservado -= det.cantidad
                            fila.disponible += det.cantidad
                        await self.db.flush()
                    await self.movimiento_repo.registrarUnico(
                        MovimientoInventario(
                            variante_id=det.variante_id,
                            sucursal_destino_id=v.sucursal_id,
                            tipo="LIBERACION_DIGITAL",
                            cantidad=det.cantidad,
                            costo_unitario=det.costo_promedio,
                            referencia_tipo="VENTA",
                            referencia_id=v.id,
                            linea_referencia_id=det.id,
                            observacion=f"Liberaci?n por cancelacion orden de pago {op.id} ({v.numero})",
                        )
                    )
        await self.db.commit()
        return OrdenPagoDTO(
            orden_pago_id=op.id,
            estado=op.estado,
            monto_bob=Decimal(str(op.monto_bob)),
            monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd else None,
            centavos_usd=op.centavos_usd,
            tasa_id=op.tasa_id,
            client_secret=None,
            referencia_externa=op.referencia_externa,
        )

    async def continuar_accion(
        self, usuario: Usuario, orden_pago_id: uuid.UUID, clave_idempotencia: uuid.UUID, payment_intent_id: Optional[str] = None,
    ) -> OrdenPagoDTO:
        """Continúa una orden de pago tras autenticación 3DS / SCA requerida."""
        r = await self.db.execute(
            select(OrdenPago).where(
                OrdenPago.id == orden_pago_id,
            ).with_for_update()
        )
        op = r.scalars().first()
        if op is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de pago no encontrada")
        await self._validar_propiedad_orden(usuario, op)

        if op.estado == "CAPTURADO":
            return OrdenPagoDTO(
                orden_pago_id=op.id,
                estado=op.estado,
                monto_bob=Decimal(str(op.monto_bob)),
                monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd else None,
                centavos_usd=op.centavos_usd,
                tasa_id=op.tasa_id,
                client_secret=None,
                referencia_externa=op.referencia_externa,
            )

        if op.estado != "REQUIERE_ACCION_CLIENTE":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La orden se encuentra en estado {op.estado}, no requiere acción del cliente",
            )

        if not op.referencia_externa:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Falta referencia de PaymentIntent en la orden")

        if payment_intent_id and payment_intent_id != op.referencia_externa:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="payment_intent_id no coincide con la referencia de la orden de pago",
            )

        ref_pi = op.referencia_externa
        gateway = gw.obtener_gateway()
        inten = await gateway.confirmar_intencion(ref_pi)

        # Validación financiera unificada (ID, moneda, centavos y metadata)
        self._validar_intencion_con_orden(inten, op)

        if inten.estado == "SUCCEEDED":
            op.estado = "CAPTURADO"
            op.actualizada_en = self.reloj.ahora()
            await self.db.flush()

            if op.contexto == "PEDIDO" and op.pedido_id:
                await self.confirmar_captura_pedido(op.pedido_id)
            elif op.contexto == "VENTA" and op.venta_id:
                r_c = await self.db.execute(
                    text("SELECT canal FROM comercial.ventas WHERE id = :id"),
                    {"id": op.venta_id},
                )
                if r_c.scalar() != "PRESENCIAL":
                    await self._aplicar_aprobado(op.venta_id, ref_pi)
        elif inten.estado == "REQUIRES_ACTION":
            op.estado = "REQUIERE_ACCION_CLIENTE"
            op.actualizada_en = self.reloj.ahora()
            await self.db.flush()
        else:
            op.estado = "FALLIDO"
            op.actualizada_en = self.reloj.ahora()
            await self.db.flush()

        await self.db.commit()

        return OrdenPagoDTO(
            orden_pago_id=op.id,
            estado=op.estado,
            monto_bob=Decimal(str(op.monto_bob)),
            monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd else None,
            centavos_usd=op.centavos_usd,
            tasa_id=op.tasa_id,
            client_secret=None,
            referencia_externa=op.referencia_externa,
        )

    async def reanudar_orden_pago(
        self, usuario: Usuario, orden_pago_id: uuid.UUID
    ) -> OrdenPagoDTO:
        """Consulta/reconcilia Stripe fuera de bloqueos y persiste la transicion bajo bloqueo."""
        r = await self.db.execute(select(OrdenPago).where(OrdenPago.id == orden_pago_id))
        orden = r.scalars().first()
        if orden is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de pago no encontrada")
        await self._validar_propiedad_orden(usuario, orden)
        if orden.estado == "CAPTURADO":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La orden ya se encuentra capturada o liquidada")
        if orden.estado == "CANCELADO":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La orden ya se encuentra cancelada")

        venta_snapshot = None
        if orden.contexto == "VENTA" and orden.venta_id:
            venta = await self.db.get(Venta, orden.venta_id)
            if venta is not None:
                if venta.estado == "PAGADA":
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La venta ya se encuentra pagada")
                if venta.estado == "CANCELADA":
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La venta ya se encuentra cancelada")
                if rol_de(usuario) == "CAJERO" and not es_admin(usuario):
                    if venta.cajero_id != usuario.id:
                        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado para reanudar venta de otro cajero")
                    from backend.app.core.permisos import exigir_sucursal
                    exigir_sucursal(usuario, venta.sucursal_id)
                venta_snapshot = {
                    "id": venta.id,
                    "clave_idempotencia": venta.clave_idempotencia,
                    "cliente_id": venta.cliente_id,
                }

        op_snapshot = SimpleNamespace(
            id=orden.id,
            contexto=orden.contexto,
            empresa_id=orden.empresa_id,
            referencia_externa=orden.referencia_externa,
            clave_externa=orden.clave_externa,
            centavos_usd=orden.centavos_usd,
            venta_id=orden.venta_id,
            pedido_id=orden.pedido_id,
            reserva_id=orden.reserva_id,
            cambio_id=orden.cambio_id,
        )

        # Solo se leyeron datos sin bloqueo; cerrar la transaccion antes del
        # viaje a Stripe. El estado se vuelve a comprobar al adquirir locks.
        await self.db.rollback()
        inten, ref_pi, es_provisional = await self._consultar_intencion_orden_sin_bloqueos(op_snapshot, venta_snapshot)
        estado = str(inten.estado or "").upper()

        r = await self.db.execute(
            select(OrdenPago).where(OrdenPago.id == orden_pago_id).with_for_update()
        )
        op = r.scalars().first()
        if op is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden de pago no encontrada")
        await self._validar_propiedad_orden(usuario, op)
        if op.estado in ("CAPTURADO", "CANCELADO"):
            if op.estado == "CANCELADO" and estado in ("SUCCEEDED", "CAPTURADO"):
                op.estado = "CAPTURADO"
                if es_provisional:
                    op.clave_externa = ref_pi
                    op.referencia_externa = ref_pi
                op.actualizada_en = self.reloj.ahora()
                await self.db.commit()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Stripe confirma captura despues de cancelacion local; la orden se reconcilio como capturada.",
                )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"La orden ya esta en estado {op.estado}")
        ref_actual = op.referencia_externa or op.clave_externa
        if not es_provisional and ref_actual != ref_pi:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La referencia de la orden cambio durante la reanudacion")
        if es_provisional and ref_actual and not ref_actual.startswith("PENDIENTE_") and ref_actual != ref_pi:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Otra reanudacion vinculo un PaymentIntent distinto")

        if op.contexto == "VENTA" and op.venta_id:
            stmt_v = select(Venta).where(Venta.id == op.venta_id).with_for_update()
            venta_bloqueada = (await self.db.execute(stmt_v)).scalars().first()
            if venta_bloqueada is None or venta_bloqueada.estado in ("PAGADA", "CANCELADA"):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La venta cambio durante la reanudacion")

        self._validar_intencion_con_orden(inten, op, referencia_esperada=ref_pi)
        if es_provisional:
            op.clave_externa = ref_pi
            op.referencia_externa = ref_pi
        if estado in ("SUCCEEDED", "CAPTURADO"):
            op.estado = "CAPTURADO"
        elif estado == "REQUIRES_ACTION":
            op.estado = "REQUIERE_ACCION_CLIENTE"
        elif estado == "CANCELED":
            op.estado = "FALLIDO"
        elif estado in ("REQUIRES_PAYMENT", "PROCESSING"):
            op.estado = "PENDIENTE"
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Estado Stripe no reanudable: {estado}")
        op.actualizada_en = self.reloj.ahora()
        await self.db.commit()
        return OrdenPagoDTO(
            orden_pago_id=op.id,
            estado=op.estado,
            monto_bob=Decimal(str(op.monto_bob)),
            monto_usd=Decimal(str(op.monto_usd)) if op.monto_usd else None,
            centavos_usd=op.centavos_usd,
            tasa_id=op.tasa_id,
            client_secret=inten.client_secret if estado not in ("SUCCEEDED", "CAPTURADO", "CANCELED") else None,
            referencia_externa=op.referencia_externa,
        )
