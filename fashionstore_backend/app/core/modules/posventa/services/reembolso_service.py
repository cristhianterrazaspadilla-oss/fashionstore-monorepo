"""Servicio de Dominio: Gestión de Reembolsos — CU27 (B1 Finanzas).

Reglas de negocio:
- El servidor deriva pagos, componentes capturados e importes elegibles; no acepta montos arbitrarios del cliente.
- Ejecución C/D: totales Stripe verificados, con reserva y clave durable antes del envío.
- B sigue parcial: parciales, pedidos, cambios, saldo y efectivo no se ejecutan por esta vía.
- No muta stock (el inventario lo controla CU20 Devoluciones).
"""
import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import or_, select
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
    ReembolsoDetalleDTO,
    ReembolsoSolicitudDTO,
)
from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw
from backend.app.core.modules.ventas_pagos.models import Pago, Venta
from backend.app.core.modules.ventas_pagos.models_ordenes import OrdenPago
from backend.app.core.modules.organizacion.models import TasaCambio
from backend.app.core.permisos import es_admin, rol_de
from backend.app.core.permisos import exigir_sucursal
from backend.app.core.ambito_comercial import empresa_comercial, sucursal_autorizada
from backend.app.core.modules.posventa.services.reembolso_monetario import conciliar, dinero, distribuir, centavos_acumulados
from backend.app.core.reloj import RelojSistema

logger = logging.getLogger(__name__)


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

    async def _cargo_original_total(self, pago: Pago, venta: Venta):
        """Cargo original verificado; los parciales se calculan sobre esta instantánea."""
        def rechazar(motivo):
            raise HTTPException(409, detail="CONCILIACION_REQUERIDA: " + motivo)

        if (pago.empresa_id != venta.empresa_id or pago.venta_id != venta.id or
                pago.contexto != "VENTA" or pago.metodo != "STRIPE_TEST" or
                pago.estado not in ("APROBADO", "PAGADO") or
                not pago.referencia_externa or not pago.referencia_externa.startswith("pi_")):
            rechazar("pago sin referencia o recurso original verificables")
        ordenes = (await self.db.execute(select(OrdenPago).where(
            OrdenPago.empresa_id == pago.empresa_id,
            OrdenPago.referencia_externa == pago.referencia_externa
        ).execution_options(populate_existing=True))).scalars().all()
        if len(ordenes) != 1:
            rechazar("asociacion Pago/OrdenPago ausente o ambigua")
        pagos_asociados = (await self.db.execute(select(Pago.id).where(
            Pago.empresa_id == pago.empresa_id, Pago.referencia_externa == pago.referencia_externa,
            Pago.metodo == "STRIPE_TEST"))).scalars().all()
        if len(pagos_asociados) != 1 or pagos_asociados[0] != pago.id:
            rechazar("varios pagos asociados a la misma referencia Stripe")
        orden = ordenes[0]
        if (orden.proveedor != "STRIPE" or orden.contexto != "VENTA" or
                orden.venta_id != venta.id or orden.pedido_id is not None or
                orden.reserva_id is not None or orden.cambio_id is not None or
                orden.estado != "CAPTURADO"):
            rechazar("la orden no corresponde al cargo capturado de esta venta")
        tasa_original = await self.db.get(TasaCambio, orden.tasa_id, populate_existing=True) if orden.tasa_id else None
        if tasa_original is None or type(orden.centavos_usd) is not int or orden.centavos_usd <= 0:
            rechazar("faltan cotizacion historica o unidades minimas originales")
        try:
            monto_pago = Decimal(str(pago.monto))
            monto_bob = Decimal(str(orden.monto_bob))
            monto_usd = Decimal(str(orden.monto_usd))
            tasa = Decimal(str(tasa_original.tasa_bob_por_usd))
            total_venta = Decimal(str(venta.total))
            if not all(d.is_finite() and d > 0 for d in (monto_pago, monto_bob, monto_usd, tasa, total_venta)):
                rechazar("importes originales ausentes o invalidos")
            if (monto_pago != monto_bob or monto_bob > total_venta or
                    monto_bob != monto_bob.quantize(Decimal("0.01")) or
                    monto_usd * 100 != orden.centavos_usd or
                    (monto_bob / tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != monto_usd):
                rechazar("importes del pago y de la cotizacion guardada contradictorios")
        except (InvalidOperation, ValueError, TypeError, ArithmeticError):
            rechazar("importes originales no verificables")
        return tasa, monto_usd, orden.centavos_usd

    async def _venta_origen(self, usuario, tipo, origen_id):
        """Resuelve relaciones declaradas; nunca asocia cargos por parecido de importes."""
        from backend.app.core.modules.posventa.services.devolucion_service import Devolucion
        from backend.app.core.modules.posventa.services.cambio_service import Cambio
        from backend.app.core.modules.ventas_pagos.models import PedidoEntrega
        empresa_id = empresa_comercial(usuario)
        if usuario.estado != "ACTIVO":
            raise HTTPException(403, detail="Cuenta inactiva")
        origen = None
        venta_id = origen_id
        if tipo in ("DEVOLUCION", "CAMBIO"):
            modelo = Devolucion if tipo == "DEVOLUCION" else Cambio
            origen = (await self.db.execute(select(modelo).where(
                modelo.id == origen_id, modelo.empresa_id == empresa_id
            ).execution_options(populate_existing=True))).scalars().first()
            if origen is None:
                raise HTTPException(404, detail="Origen no encontrado")
            venta_id = origen.venta_id
        elif tipo == "PEDIDO":
            origen = (await self.db.execute(select(PedidoEntrega).where(
                PedidoEntrega.id == origen_id, PedidoEntrega.empresa_id == empresa_id
            ).execution_options(populate_existing=True))).scalars().first()
            if origen is None or origen.venta_id is None:
                conciliar("PedidoCompra requiere un vínculo durable entre su OrdenPago capturada y un Pago; pago_id no admite UUID de OrdenPago")
            venta_id = origen.venta_id
        elif tipo != "VENTA":
            raise HTTPException(400, detail="Origen de reembolso inválido")
        venta = (await self.db.execute(select(Venta).where(
            Venta.id == venta_id, Venta.empresa_id == empresa_id
        ).with_for_update().execution_options(populate_existing=True))).scalars().first()
        if venta is None:
            raise HTTPException(404, detail="Venta original no encontrada")
        if venta.cliente_id is None:
            conciliar("la venta no identifica un titular verificable; no se asigna el administrador como beneficiario")
        titular = (await self.db.execute(select(Usuario.id).where(
            Usuario.id == venta.cliente_id, Usuario.empresa_id == empresa_id
        ))).scalar_one_or_none()
        if titular is None:
            conciliar("el titular de la venta no pertenece a la empresa autorizada")
        await sucursal_autorizada(self.db, usuario, venta.sucursal_id)
        if origen is not None and (origen.cliente_id != venta.cliente_id or origen.sucursal_id != venta.sucursal_id):
            conciliar("el titular o la sucursal del origen no corresponden a la venta original")
        rol = rol_de(usuario)
        if rol == "CLIENTE":
            if venta.cliente_id != usuario.id:
                raise HTTPException(403, detail="La venta pertenece a otro cliente")
        elif rol == "ENCARGADO":
            exigir_sucursal(usuario, venta.sucursal_id)
        elif not es_admin(usuario):
            raise HTTPException(403, detail="Rol no autorizado para reembolsos")
        return venta, origen

    async def _importe_devolucion(self, venta, dev, unidades=None):
        from backend.app.core.modules.posventa.services.devolucion_service import DetalleDevolucion
        from backend.app.core.modules.ventas_pagos.models import DetalleVenta
        if dev.estado != "APROBADA_REEMBOLSO":
            conciliar("la devolución no tiene dictamen autorizado de reembolso")
        detalles = (await self.db.execute(select(DetalleDevolucion).where(
            DetalleDevolucion.devolucion_id == dev.id, DetalleDevolucion.empresa_id == venta.empresa_id
        ).order_by(DetalleDevolucion.id))).scalars().all()
        total, cantidad = Decimal("0"), 0
        vistos = set()
        for d in detalles:
            if d.detalle_venta_id in vistos:
                conciliar("líneas originales duplicadas en la devolución histórica")
            vistos.add(d.detalle_venta_id)
            original = await self.db.get(DetalleVenta, d.detalle_venta_id)
            if (original is None or original.venta_id != venta.id or d.venta_id != venta.id or
                    d.cantidad_aceptada <= 0 or d.cantidad_aceptada > d.cantidad_recibida or
                    d.cantidad_aceptada > original.cantidad):
                conciliar("cantidades o venta original de la devolución inconsistentes")
            neto = dinero(original.precio_unitario) - dinero(original.descuento) / Decimal(original.cantidad)
            if neto < 0:
                conciliar("descuento original inconsistente")
            total += neto * d.cantidad_aceptada
            cantidad += d.cantidad_aceptada
        if not detalles or (unidades is not None and unidades != cantidad):
            conciliar("las unidades declaradas no corresponden a las unidades aceptadas")
        return dinero(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    async def _fondos_y_reservas(self, venta):
        """Bloqueo ordenado de pagos; obligaciones pendientes/inciertas conservan su reserva."""
        from backend.app.core.modules.posventa.services.devolucion_service import Devolucion
        from backend.app.core.modules.posventa.services.cambio_service import Cambio
        from backend.app.core.modules.ventas_pagos.models import PedidoEntrega
        pagos = (await self.db.execute(select(Pago).where(
            Pago.empresa_id == venta.empresa_id, Pago.venta_id == venta.id,
            Pago.estado.in_(("APROBADO", "PAGADO"))
        ).order_by(Pago.id).with_for_update().execution_options(populate_existing=True))).scalars().all()
        fondos = []
        for pago in pagos:
            if pago.no_reembolsable:
                continue
            if pago.contexto != "VENTA" or pago.metodo not in ("STRIPE_TEST", "EFECTIVO"):
                conciliar("el medio original requiere un mecanismo de reintegro verificable")
            fondo = dict(pago_id=pago.id, medio="STRIPE" if pago.metodo == "STRIPE_TEST" else "EFECTIVO",
                         original=dinero(pago.monto), utilizado=Decimal("0"), centavos_utilizados=0,
                         tasa=None, centavos=None, referencia=pago.referencia_externa)
            if fondo["medio"] == "STRIPE":
                tasa, _, centavos = await self._cargo_original_total(pago, venta)
                fondo.update(tasa=tasa, centavos=centavos)
            fondos.append(fondo)
        debitos = (await self.db.execute(select(MovimientoSaldo).where(
            MovimientoSaldo.empresa_id == venta.empresa_id, MovimientoSaldo.cliente_id == venta.cliente_id,
            MovimientoSaldo.origen_tipo == "VENTA", MovimientoSaldo.origen_id == venta.id,
            MovimientoSaldo.tipo == "DEBITO", MovimientoSaldo.estado == "CONFIRMADO"
        ).order_by(MovimientoSaldo.id))).scalars().all()
        if debitos:
            fondos.append(dict(pago_id=None, medio="SALDO", original=sum((dinero(d.monto_bob) for d in debitos), Decimal("0")),
                               utilizado=Decimal("0"), centavos_utilizados=0, tasa=None, centavos=None, referencia=None))
        if not fondos or sum((f["original"] for f in fondos), Decimal("0")) > dinero(venta.total):
            conciliar("capturas ausentes o superiores al total original")
        por_medio = {(f["pago_id"], f["medio"]): f for f in fondos}
        fuentes = or_(
            (ObligacionReembolso.origen_tipo == "VENTA") & (ObligacionReembolso.origen_id == venta.id),
            (ObligacionReembolso.origen_tipo == "DEVOLUCION") & ObligacionReembolso.origen_id.in_(
                select(Devolucion.id).where(Devolucion.empresa_id == venta.empresa_id, Devolucion.venta_id == venta.id)),
            (ObligacionReembolso.origen_tipo == "CAMBIO") & ObligacionReembolso.origen_id.in_(
                select(Cambio.id).where(Cambio.empresa_id == venta.empresa_id, Cambio.venta_id == venta.id)),
            (ObligacionReembolso.origen_tipo == "PEDIDO") & ObligacionReembolso.origen_id.in_(
                select(PedidoEntrega.id).where(PedidoEntrega.empresa_id == venta.empresa_id, PedidoEntrega.venta_id == venta.id)),
            ObligacionReembolso.id.in_(select(ComponenteReembolso.obligacion_id).where(
                ComponenteReembolso.empresa_id == venta.empresa_id,
                ComponenteReembolso.pago_id.in_([p.id for p in pagos]))),
        )
        obligaciones = (await self.db.execute(select(ObligacionReembolso).where(
            ObligacionReembolso.empresa_id == venta.empresa_id, fuentes
        ).options(selectinload(ObligacionReembolso.componentes))
          .order_by(ObligacionReembolso.creada_en, ObligacionReembolso.id)
          .execution_options(populate_existing=True))).scalars().all()
        for obligacion in obligaciones:
            if obligacion.cliente_id != venta.cliente_id:
                conciliar("el beneficiario de una obligación no corresponde al titular de la venta")
            componentes = obligacion.componentes
            if not componentes or sum((dinero(c.monto_bob) for c in componentes), Decimal("0")) != dinero(obligacion.monto_bob):
                conciliar("obligación histórica sin componentes completos; no se recalcula automáticamente")
            if obligacion.estado not in ("PENDIENTE_AUTORIZACION", "AUTORIZADO", "AUTORIZADA", "EN_PROCESO",
                                         "COMPLETADO", "COMPLETADA", "FALLIDO", "FALLIDA"):
                conciliar("el estado de una obligación anterior requiere conciliación de su reserva")
            vistos = set()
            for c in sorted(componentes, key=lambda c: str(c.id)):
                clave = (c.pago_id, c.medio)
                if clave in vistos or clave not in por_medio or c.empresa_id != venta.empresa_id:
                    conciliar("componentes históricos duplicados o sin un medio original verificable")
                vistos.add(clave)
                fondo = por_medio[clave]
                monto = dinero(c.monto_bob)
                if monto <= 0 or fondo["utilizado"] + monto > fondo["original"]:
                    conciliar("obligaciones acumuladas superiores al pago original")
                if c.medio == "STRIPE":
                    esperado = centavos_acumulados(fondo["original"], fondo["centavos"],
                                                  fondo["utilizado"], fondo["centavos_utilizados"], monto)
                    if (c.centavos_usd != esperado or dinero(c.monto_usd) * 100 != esperado or
                            c.tasa_bob_por_usd != fondo["tasa"]):
                        conciliar("parciales históricos contradictorios con el cargo y cotización originales")
                    fondo["centavos_utilizados"] += esperado
                elif c.monto_usd is not None or c.centavos_usd is not None or c.tasa_bob_por_usd is not None:
                    conciliar("componente no Stripe con importes de otro medio")
                fondo["utilizado"] += monto
        return fondos, obligaciones

    async def solicitar_reembolso(
        self, usuario: Usuario, datos: ReembolsoSolicitudDTO, clave_idempotencia: uuid.UUID,
    ) -> ReembolsoDetalleDTO:
        from backend.app.core import idempotencia_ciclo3 as idem
        empresa_comercial(usuario)
        tipo = datos.origen_tipo.upper()
        previo = await idem.reclamar(self.db, clave_idempotencia, idem.hash_payload(datos.model_dump(mode="json")),
                                    recurso_tipo="REEMBOLSO", operacion="SOLICITAR", usuario_id=usuario.id)
        if previo is not None and not previo.respuesta:
            raise HTTPException(409, detail="La solicitud de reembolso sigue en proceso")
        venta, origen = await self._venta_origen(usuario, tipo, datos.origen_id)
        fondos, obligaciones = await self._fondos_y_reservas(venta)
        existente = next((o for o in obligaciones if o.origen_tipo == tipo and o.origen_id == datos.origen_id
                          and o.motivo_codigo == datos.motivo_codigo), None)
        if existente is not None:
            if tipo == "DEVOLUCION" and dinero(existente.monto_bob) != await self._importe_devolucion(venta, origen, datos.unidades):
                conciliar("la obligación histórica no coincide con la devolución aceptada")
            salida = self._a_detalle_dto(existente)
        else:
            if tipo == "CAMBIO":
                conciliar("falta una resolución monetaria de cambio vinculada y componentes originales verificables")
            if tipo in ("VENTA", "PEDIDO"):
                from backend.app.core.modules.posventa.services.devolucion_service import Devolucion
                from backend.app.core.modules.posventa.services.cambio_service import Cambio
                dev = (await self.db.execute(select(Devolucion.id).where(
                    Devolucion.empresa_id == venta.empresa_id, Devolucion.venta_id == venta.id,
                    Devolucion.estado != "RECHAZADA").limit(1))).scalar()
                cambio = (await self.db.execute(select(Cambio.id).where(
                    Cambio.empresa_id == venta.empresa_id, Cambio.venta_id == venta.id,
                    Cambio.estado != "RECHAZADO").limit(1))).scalar()
                if dev is not None or cambio is not None:
                    conciliar("la venta tiene unidades comprometidas en posventa; el reintegro debe tramitarse por su origen autorizado")
            if tipo == "DEVOLUCION" and any(o.origen_tipo == tipo and o.origen_id == datos.origen_id for o in obligaciones):
                conciliar("las mismas unidades ya tienen otra obligación; no se duplican por motivo")
            disponibles = [f["original"] - f["utilizado"] for f in fondos]
            if tipo == "DEVOLUCION":
                importe = await self._importe_devolucion(venta, origen, datos.unidades)
            else:
                if datos.unidades is not None:
                    conciliar("un parcial por unidades requiere una devolución inspeccionada y sus líneas originales")
                importe = sum(disponibles, Decimal("0"))
            partes = distribuir(importe, disponibles)
            obligacion = ObligacionReembolso(
                id=uuid.uuid4(), empresa_id=venta.empresa_id, cliente_id=venta.cliente_id,
                origen_tipo=tipo, origen_id=datos.origen_id, motivo_codigo=datos.motivo_codigo,
                estado="PENDIENTE_AUTORIZACION", monto_bob=importe, revision=1, creada_en=self.reloj.ahora(),
            )
            self.db.add(obligacion)
            await self.db.flush()
            componentes = []
            for fondo, monto in zip(fondos, partes):
                if monto <= 0:
                    continue
                centavos = (centavos_acumulados(fondo["original"], fondo["centavos"], fondo["utilizado"],
                                              fondo["centavos_utilizados"], monto)
                            if fondo["medio"] == "STRIPE" else None)
                c = ComponenteReembolso(
                    id=uuid.uuid4(), empresa_id=venta.empresa_id, obligacion_id=obligacion.id,
                    pago_id=fondo["pago_id"], medio=fondo["medio"], monto_bob=monto,
                    centavos_usd=centavos, monto_usd=Decimal(centavos) / 100 if centavos is not None else None,
                    tasa_bob_por_usd=fondo["tasa"], estado="PENDIENTE",
                )
                self.db.add(c)
                componentes.append(c)
            # Recargar la relación por consulta evita IO implícito con AsyncSession.
            await self.db.flush()
            obligacion = (await self.db.execute(select(ObligacionReembolso).where(
                ObligacionReembolso.id == obligacion.id
            ).options(selectinload(ObligacionReembolso.componentes)))).scalars().one()
            salida = self._a_detalle_dto(obligacion)
        await idem.guardar_respuesta(self.db, clave_idempotencia, salida.model_dump(mode="json"),
                                    recurso_id=salida.id, usuario_id=usuario.id,
                                    recurso_tipo="REEMBOLSO", operacion="SOLICITAR")
        await self.db.commit()
        return salida

    async def _cargar_validado(self, usuario_id, reembolso_id, *, fondos=False, personal=False):
        # La sesión autentica el ID; permisos y empresa se vuelven a leer del servidor
        # en cada transacción, también después de una respuesta del proveedor.
        usuario = (await self.db.execute(select(Usuario).where(Usuario.id == usuario_id)
            .options(selectinload(Usuario.rol), selectinload(Usuario.empleado))
            .execution_options(populate_existing=True))).scalars().first()
        if usuario is None or usuario.estado != "ACTIVO":
            raise HTTPException(403, detail="Usuario no autorizado")
        empresa_id = empresa_comercial(usuario)
        rol = rol_de(usuario)
        if personal and (rol not in ("ADMINISTRADOR", "ENCARGADO") or
                         (personal == "ADMIN" and rol != "ADMINISTRADOR")):
            raise HTTPException(403, detail="Personal no autorizado para esta operación")
        inicial = (await self.db.execute(select(ObligacionReembolso).where(
            ObligacionReembolso.id == reembolso_id, ObligacionReembolso.empresa_id == empresa_id
        ))).scalars().first()
        if inicial is None:
            raise HTTPException(404, detail="Reembolso no encontrado")
        origen = (inicial.origen_tipo, inicial.origen_id)
        venta, _ = await self._venta_origen(usuario, *origen)
        # Orden de bloqueo compartido con solicitud: venta -> pagos -> obligación -> ejecución.
        disponibles, obligaciones = await self._fondos_y_reservas(venta) if fondos else ([], [])
        obl = (await self.db.execute(select(ObligacionReembolso).where(
            ObligacionReembolso.id == reembolso_id, ObligacionReembolso.empresa_id == empresa_id
        ).options(selectinload(ObligacionReembolso.componentes)).with_for_update()
          .execution_options(populate_existing=True))).scalars().one()
        if (origen != (obl.origen_tipo, obl.origen_id) or obl.cliente_id != venta.cliente_id):
            conciliar("el origen o beneficiario no corresponde a la venta verificada")
        if fondos and not any(o.id == obl.id for o in obligaciones):
            conciliar("la obligación no está vinculada a los fondos de la venta")
        return obl, venta, disponibles, obligaciones

    @staticmethod
    def _cobertura_c_d(obl, venta, fondos, obligaciones):
        # B sigue parcial. No habilitar parciales, cambios, pedidos ni reintegros
        # mixtos sin garantías de imputación y de ejecución de TODOS sus medios.
        if obl.origen_tipo != "VENTA":
            conciliar("ejecución pendiente para parciales/devoluciones, cambios y pedidos; B no cubre aún su imputación completa")
        if (not fondos or any(f["medio"] != "STRIPE" for f in fondos) or
                sum((f["original"] for f in fondos), Decimal("0")) != dinero(venta.total)):
            conciliar("solo está habilitado el total íntegramente capturado por Stripe; efectivo, saldo y medios mixtos siguen pendientes")
        if len(obligaciones) != 1 or obligaciones[0].id != obl.id:
            conciliar("la ejecución parcial o con obligaciones anteriores requiere completar B")
        por_pago = {f["pago_id"]: f for f in fondos}
        if len(obl.componentes) != len(por_pago) or dinero(obl.monto_bob) != dinero(venta.total):
            conciliar("el reembolso no comprende exactamente los cargos originales completos")
        for c in obl.componentes:
            f = por_pago.get(c.pago_id)
            if (f is None or c.medio != "STRIPE" or dinero(c.monto_bob) != f["original"] or
                    c.centavos_usd != f["centavos"]):
                conciliar("un componente parcial o de otro medio no está habilitado para ejecución")
        return por_pago

    async def _ejecuciones(self, obl):
        filas = (await self.db.execute(select(EjecucionReembolso).where(
            EjecucionReembolso.empresa_id == obl.empresa_id,
            EjecucionReembolso.componente_id.in_([c.id for c in obl.componentes])
        ).order_by(EjecucionReembolso.id).with_for_update()
          .execution_options(populate_existing=True))).scalars().all()
        por_componente = {}
        for e in filas:
            if e.componente_id in por_componente:
                conciliar("varias ejecuciones históricas para el mismo componente")
            por_componente[e.componente_id] = e
        for c in obl.componentes:
            e = por_componente.get(c.id)
            if e is None:
                if c.estado != "PENDIENTE":
                    conciliar("componente procesado sin ejecución durable; no se vuelve a enviar")
                continue
            if (e.proveedor != "STRIPE" or not e.clave_ejecucion or e.intento != 1 or
                    e.estado not in ("PREPARADA", "EN_PROCESO", "COMPLETADO", "FALLIDO") or
                    c.estado != ("EN_PROCESO" if e.estado == "PREPARADA" else e.estado) or
                    (e.referencia_externa is not None and not e.referencia_externa.startswith("re_")) or
                    (e.estado in ("COMPLETADO", "FALLIDO") and
                     (not e.referencia_externa or e.resuelta_en is None)) or
                    (e.estado == "PREPARADA" and e.referencia_externa is not None)):
                conciliar("ejecución histórica contradictoria o sin prueba de resolución")
        if por_componente and len(por_componente) != len(obl.componentes):
            conciliar("ejecución histórica incompleta; no se crean nuevos intentos para compensarla")
        return por_componente

    @staticmethod
    def _clave_durable(obl, venta, comp, fondo):
        from backend.app.core.idempotencia_ciclo3 import hash_payload
        # La clave persistida también fija el cuerpo/cargo de un envío preparado.
        # Si cambia su fuente entre solicitudes, no reutilizar esa ejecución para
        # otro cargo ni fabricar una clave nueva para el mismo componente.
        huella = hash_payload(dict(
            empresa_id=str(obl.empresa_id), cliente_id=str(obl.cliente_id), venta_id=str(venta.id),
            reembolso_id=str(obl.id), pago_id=str(comp.pago_id), referencia=fondo["referencia"],
            centavos=comp.centavos_usd, moneda="usd",
            monto_bob=str(dinero(comp.monto_bob).quantize(Decimal("0.01"))),
            tasa=str(comp.tasa_bob_por_usd.quantize(Decimal("0.00000001"))),
        ))
        return uuid.uuid5(comp.id, "REEMBOLSO_STRIPE:" + huella)

    @staticmethod
    def _instantanea(obl, venta, comp, ejec, fondo):
        # Solo campos verificados y persistidos, nunca identificadores del cuerpo HTTP
        # como prueba de propiedad. El componente congelado es el payload monetario.
        if ejec.estado == "PREPARADA" and ejec.clave_ejecucion != ReembolsoService._clave_durable(obl, venta, comp, fondo):
            conciliar("el cuerpo o cargo de la ejecución preparada cambió desde su persistencia")
        return dict(reembolso_id=obl.id, empresa_id=obl.empresa_id, cliente_id=obl.cliente_id,
                    venta_id=venta.id, componente_id=comp.id, pago_id=comp.pago_id,
                    ejecucion_id=ejec.id, clave=ejec.clave_ejecucion,
                    referencia_pago=fondo["referencia"], centavos=comp.centavos_usd,
                    monto_bob=dinero(comp.monto_bob), tasa=comp.tasa_bob_por_usd,
                    referencia=ejec.referencia_externa, estado=ejec.estado)

    @staticmethod
    def _verificar_instantanea(anterior, actual):
        for campo in ("reembolso_id", "empresa_id", "cliente_id", "venta_id", "componente_id",
                      "pago_id", "ejecucion_id", "clave", "referencia_pago", "centavos", "monto_bob", "tasa"):
            if anterior[campo] != actual[campo]:
                conciliar("la ejecución o su cargo original cambiaron; no se envía ni se acredita otro importe")
        if anterior["referencia"] and anterior["referencia"] != actual["referencia"]:
            conciliar("la referencia del reintegro guardado cambió")

    async def obtener_reembolso(self, usuario: Usuario, reembolso_id: uuid.UUID) -> ReembolsoDetalleDTO:
        obl, _, _, _ = await self._cargar_validado(usuario.id, reembolso_id)
        return self._a_detalle_dto(obl)

    async def autorizar_reembolso(
        self, usuario: Usuario, reembolso_id: uuid.UUID, clave_idempotencia: uuid.UUID, motivo: Optional[str] = None,
    ) -> ReembolsoDetalleDTO:
        obl, venta, fondos, obligaciones = await self._cargar_validado(
            usuario.id, reembolso_id, fondos=True, personal=True)
        self._cobertura_c_d(obl, venta, fondos, obligaciones)
        if obl.estado in ("AUTORIZADO", "EN_PROCESO", "COMPLETADO", "FALLIDO"):
            return self._a_detalle_dto(obl)
        if obl.estado != "PENDIENTE_AUTORIZACION" or any(c.estado != "PENDIENTE" for c in obl.componentes):
            conciliar("la obligación no está pendiente de autorización")
        obl.estado = "AUTORIZADO"
        obl.autorizada_en = self.reloj.ahora()
        obl.revision += 1
        salida = self._a_detalle_dto(obl)
        await self.db.commit()
        return salida

    async def ejecutar_reembolso(
        self, usuario: Usuario, reembolso_id: uuid.UUID, clave_ejecucion: uuid.UUID, clave_idempotencia: uuid.UUID,
    ) -> ReembolsoDetalleDTO:
        from backend.app.core import idempotencia_ciclo3 as idem
        usuario_id = usuario.id
        empresa_comercial(usuario)
        # Las claves HTTP detectan reutilización de otra petición, pero NO deciden
        # qué ejecución financiera crear. Esta pertenece al componente en servidor.
        await idem.reclamar(self.db, clave_idempotencia,
            idem.hash_payload(dict(reembolso_id=str(reembolso_id), clave_ejecucion=str(clave_ejecucion))),
            recurso_tipo="REEMBOLSO", operacion="EJECUTAR", usuario_id=usuario_id)
        await idem.reclamar(self.db, clave_ejecucion, idem.hash_payload(dict(reembolso_id=str(reembolso_id))),
            recurso_tipo="REEMBOLSO", operacion="CLAVE_EJECUCION", usuario_id=usuario_id)
        obl, venta, fondos, obligaciones = await self._cargar_validado(
            usuario_id, reembolso_id, fondos=True, personal=True)
        por_pago = self._cobertura_c_d(obl, venta, fondos, obligaciones)
        ejecuciones = await self._ejecuciones(obl)
        if obl.estado not in ("AUTORIZADO", "EN_PROCESO", "COMPLETADO", "FALLIDO") or not obl.autorizada_en:
            conciliar("la obligación no tiene autorización vigente para ejecución")
        if not ejecuciones:
            if obl.estado != "AUTORIZADO":
                conciliar("falta la ejecución durable de una obligación ya procesada")
            # Revalidar compromisos físicos creados después de la solicitud.
            from backend.app.core.modules.posventa.services.devolucion_service import Devolucion
            from backend.app.core.modules.posventa.services.cambio_service import Cambio
            for modelo, rechazado in ((Devolucion, "RECHAZADA"), (Cambio, "RECHAZADO")):
                pendiente = (await self.db.execute(select(modelo.id).where(
                    modelo.empresa_id == venta.empresa_id, modelo.venta_id == venta.id,
                    modelo.estado != rechazado).limit(1))).scalar_one_or_none()
                if pendiente is not None:
                    conciliar("la venta tiene un compromiso de posventa; el total no puede ejecutarse por esta vía")
            for comp in obl.componentes:
                # Una sola ejecución lógica por componente, incluso si cambia la
                # clave del cliente. PREPARADA todavía permite reclamar un envío.
                ejec = EjecucionReembolso(
                    id=uuid.uuid4(), empresa_id=obl.empresa_id, componente_id=comp.id,
                    clave_ejecucion=self._clave_durable(obl, venta, comp, por_pago[comp.pago_id]),
                    proveedor="STRIPE", estado="PREPARADA", intento=1, creada_en=self.reloj.ahora())
                self.db.add(ejec)
                ejecuciones[comp.id] = ejec
                comp.estado = "EN_PROCESO"
            obl.estado = "EN_PROCESO"
            obl.revision += 1
        planes = [self._instantanea(obl, venta, c, ejecuciones[c.id], por_pago[c.pago_id])
                  for c in sorted(obl.componentes, key=lambda c: str(c.id))]
        salida = self._a_detalle_dto(obl)
        for clave, operacion in ((clave_idempotencia, "EJECUTAR"), (clave_ejecucion, "CLAVE_EJECUCION")):
            await idem.guardar_respuesta(self.db, clave, salida.model_dump(mode="json"), recurso_id=salida.id,
                                        usuario_id=usuario_id, recurso_tipo="REEMBOLSO", operacion=operacion)
        # Reserva, componentes y claves confirmados ANTES de cualquier envío.
        await self.db.commit()
        return await self._procesar_planes(usuario_id, reembolso_id, planes, iniciar=True)

    async def _tomar_ejecucion(self, usuario_id, anterior, *, iniciar):
        obl, venta, fondos, obligaciones = await self._cargar_validado(
            usuario_id, anterior["reembolso_id"], fondos=True, personal=True if iniciar else "ADMIN")
        por_pago = self._cobertura_c_d(obl, venta, fondos, obligaciones)
        if not obl.autorizada_en or obl.estado not in ("AUTORIZADO", "EN_PROCESO", "COMPLETADO", "FALLIDO"):
            conciliar("falta la autorización original")
        ejecuciones = await self._ejecuciones(obl)
        comp = next((c for c in obl.componentes if c.id == anterior["componente_id"]), None)
        if comp is None or comp.id not in ejecuciones:
            conciliar("falta la ejecución original")
        ejec = ejecuciones[comp.id]
        actual = self._instantanea(obl, venta, comp, ejec, por_pago[comp.pago_id])
        self._verificar_instantanea(anterior, actual)
        enviar = iniciar and ejec.estado == "PREPARADA"
        if enviar:
            # Solo comprueba configuración local; no contacta al proveedor.
            # Si está deshabilitado, permanece PREPARADA y puede retomarse.
            gw.obtener_gateway()
            # Solo quien obtiene este bloqueo puede pasar de PREPARADA a envío.
            # Un EN_PROCESO sin referencia es incierto: jamás se reenvía a ciegas.
            ejec.estado = actual["estado"] = "EN_PROCESO"
        actual["enviar"] = enviar
        await self.db.commit()
        return actual

    @staticmethod
    def _validar_cargo_proveedor(plan, cargo):
        meta = cargo.metadata or {}
        if not isinstance(meta, dict):
            conciliar("el cargo no contiene metadata verificable; no se envía el reintegro")
        if (cargo.id != plan["referencia_pago"] or cargo.estado != "SUCCEEDED" or cargo.moneda != "usd" or
                cargo.venta_id != str(plan["venta_id"]) or str(cargo.empresa_id) != str(plan["empresa_id"]) or
                (cargo.cliente_id and str(cargo.cliente_id) != str(plan["cliente_id"])) or
                (meta.get("cliente_id") and str(meta["cliente_id"]) != str(plan["cliente_id"])) or
                type(cargo.capturado_centavos) is not int or type(cargo.reembolsado_centavos) is not int or
                cargo.monto_centavos != plan["centavos"] or cargo.capturado_centavos != plan["centavos"] or
                cargo.reembolsado_centavos != 0):
            conciliar("el proveedor no confirma el cargo completo disponible de esta empresa y venta; no se envía el reintegro")

    async def _consultar_o_enviar(self, plan):
        try:
            gateway = gw.obtener_gateway()
            if plan["enviar"]:
                cargo = await gateway.consultar_intencion(plan["referencia_pago"])
            elif plan["referencia"]:
                return await gateway.consultar_reembolso(plan["referencia"])
            else:
                return await gateway.buscar_reembolso(plan["referencia_pago"], str(plan["clave"]))
        except Exception:
            # No registrar excepciones/respuestas que puedan contener secretos o PII.
            logger.warning("Reembolso sin confirmación del proveedor; ejecución=%s", plan["ejecucion_id"])
            raise HTTPException(409, detail="RESULTADO_REEMBOLSO_INCIERTO: ejecución conservada; reintente la consulta o conciliación, no se crea otro reintegro") from None
        self._validar_cargo_proveedor(plan, cargo)
        try:
            return await gateway.crear_reembolso(payment_intent_id=plan["referencia_pago"],
                centavos_usd=plan["centavos"], idempotency_key=str(plan["clave"]))
        except Exception:
            logger.warning("Envío de reembolso sin confirmación; ejecución=%s", plan["ejecucion_id"])
            raise HTTPException(409, detail="RESULTADO_REEMBOLSO_INCIERTO: ejecución y reserva conservadas; se requiere consulta o conciliación") from None

    async def _guardar_resultado(self, usuario_id, plan, resultado, *, personal):
        if (resultado is None or not isinstance(resultado.id, str) or not resultado.id.startswith("re_") or
                resultado.moneda != "usd" or resultado.payment_intent_id != plan["referencia_pago"] or
                type(resultado.centavos_usd) is not int or resultado.centavos_usd != plan["centavos"] or
                (plan["referencia"] and resultado.id != plan["referencia"])):
            conciliar("el resultado no prueba el reintegro original; se conserva pendiente sin nuevo envío")
        obl, venta, fondos, obligaciones = await self._cargar_validado(
            usuario_id, plan["reembolso_id"], fondos=True, personal=personal)
        por_pago = self._cobertura_c_d(obl, venta, fondos, obligaciones)
        ejecuciones = await self._ejecuciones(obl)
        comp = next((c for c in obl.componentes if c.id == plan["componente_id"]), None)
        if comp is None or comp.id not in ejecuciones:
            conciliar("la ejecución durable no existe al conciliar")
        ejec = ejecuciones[comp.id]
        self._verificar_instantanea(plan, self._instantanea(obl, venta, comp, ejec, por_pago[comp.pago_id]))
        if ejec.referencia_externa and ejec.referencia_externa != resultado.id:
            conciliar("el proveedor identifica otro reintegro para la misma ejecución")
        estado = self._estado_stripe(resultado.estado)
        if ejec.estado in ("COMPLETADO", "FALLIDO") and estado != ejec.estado:
            # Respuesta tardía no degrada un estado terminal previamente verificado.
            if estado != "EN_PROCESO":
                conciliar("resultados terminales contradictorios; se mantiene la resolución guardada")
        else:
            ejec.referencia_externa = resultado.id
            ejec.estado = comp.estado = estado
            ejec.resuelta_en = (ejec.resuelta_en or self.reloj.ahora()) if estado != "EN_PROCESO" else None
        self._actualizar_estado(obl)
        obl.revision += 1
        await self.db.commit()

    async def _procesar_planes(self, usuario_id, reembolso_id, planes, *, iniciar):
        for anterior in planes:
            plan = await self._tomar_ejecucion(usuario_id, anterior, iniciar=iniciar)
            if plan["estado"] in ("PREPARADA", "COMPLETADO"):
                continue
            resultado = await self._consultar_o_enviar(plan)
            # Sin coincidencia por metadata no prueba que nunca se recibió el POST.
            # Incluye la caída entre marcar EN_PROCESO y enviar: requiere conciliación,
            # no una repetición que dependa de la retención temporal de Stripe.
            await self._guardar_resultado(usuario_id, plan, resultado, personal=True if iniciar else "ADMIN")
        obl, _, _, _ = await self._cargar_validado(
            usuario_id, reembolso_id, fondos=True, personal=True if iniciar else "ADMIN")
        await self._ejecuciones(obl)
        self._actualizar_estado(obl)
        salida = self._a_detalle_dto(obl)
        await self.db.commit()
        return salida

    @staticmethod
    def _estado_stripe(estado):
        if estado == "succeeded":
            return "COMPLETADO"
        if estado in ("failed", "canceled"):
            return "FALLIDO"
        return "EN_PROCESO"

    def _actualizar_estado(self, obl):
        estados = [c.estado for c in obl.componentes]
        obl.estado = ("COMPLETADO" if estados and all(e == "COMPLETADO" for e in estados)
                      else "EN_PROCESO" if any(e in ("PENDIENTE", "EN_PROCESO") for e in estados)
                      else "FALLIDO")
        obl.completada_en = (obl.completada_en or self.reloj.ahora()) if obl.estado == "COMPLETADO" else None

    async def conciliar_reembolso(
        self, usuario: Usuario, reembolso_id: uuid.UUID, clave_idempotencia: uuid.UUID,
    ) -> ReembolsoDetalleDTO:
        usuario_id = usuario.id
        obl, venta, fondos, obligaciones = await self._cargar_validado(
            usuario_id, reembolso_id, fondos=True, personal="ADMIN")
        por_pago = self._cobertura_c_d(obl, venta, fondos, obligaciones)
        ejecuciones = await self._ejecuciones(obl)
        if not ejecuciones or not obl.autorizada_en:
            conciliar("no existe ejecución durable autorizada; conciliación no crea ni envía reintegros")
        planes = [self._instantanea(obl, venta, c, ejecuciones[c.id], por_pago[c.pago_id])
                  for c in sorted(obl.componentes, key=lambda c: str(c.id))]
        await self.db.commit()
        return await self._procesar_planes(usuario_id, reembolso_id, planes, iniciar=False)
