"""Controller CarritoService + Checkout digital — CU14 (RF14, RF15, RF16)."""
import secrets
import string
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core import idempotencia_ciclo3 as idem3
from backend.app.core.idempotencia import hash_payload, resolver_idempotencia
from backend.app.core.permisos import es_admin, rol_de
from backend.app.core.reloj import RelojSistema
from backend.app.core.modules.ventas_pagos.models import Carrito, DetalleCarrito, PedidoEntrega
from backend.app.core.modules.experiencia_cliente.models import HistorialNavegacion
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Venta
from backend.app.core.modules.inventario.models import MovimientoInventario
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.repositories.carrito_repository import CarritoRepository
from backend.app.core.modules.ventas_pagos.repositories.pedido_repository import PedidoRepository
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.modules.ventas_pagos.repositories.venta_repository import DetalleVentaRepository, VentaRepository
from backend.app.core.modules.ventas_pagos.schemas import (
    CarritoDTO,
    CheckoutCrearDTO,
    CheckoutRespuestaDTO,
    CoberturaDTO,
    CoberturaSucursalDTO,
    LineaActualizarDTO,
    LineaAgregarDTO,
    LineaCarritoDTO,
)
from backend.app.core.modules.catalogo.services.promocion_service import PromocionService

VENTANA_COMPROMISO = timedelta(minutes=60)
NUMERO_ALFABETO = string.ascii_uppercase + string.digits


def _exigir_cliente(usuario: Usuario) -> uuid.UUID:
    if rol_de(usuario) != "CLIENTE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el Cliente opera su carrito",
        )
    return usuario.id


class CarritoService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.repo = CarritoRepository(db)
        self.pedido_repo = PedidoRepository(db)
        self.venta_repo = VentaRepository(db)
        self.detalle_venta_repo = DetalleVentaRepository(db)
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)
        self.sucursal_repo = SucursalRepository(db)
        self.variante_repo = VarianteRepository(db)
        self.promo = PromocionService(db, self.reloj)

    # ---------------- carrito ----------------
    async def _obtener_o_crear(self, cliente_id: uuid.UUID, canal: str) -> Carrito:
        carrito = await self.repo.activoDe(cliente_id, canal)
        if carrito is None:
            try:
                carrito = Carrito(cliente_id=cliente_id, canal=canal, estado="ACTIVO")
                await self.repo.crear(carrito)
                await self.db.commit()
            except IntegrityError:
                await self.db.rollback()
                carrito = await self.repo.activoDe(cliente_id, canal)
                if carrito is None:
                    raise
        return carrito

    async def _armar_dto(self, carrito: Carrito) -> CarritoDTO:
        lineas = await self.repo.lineasDe(carrito.id)
        items: List[LineaCarritoDTO] = []
        subtotal = Decimal("0")
        dto_desc = Decimal("0")
        for lin in lineas:
            variante = await self.variante_repo.buscarPorId(lin.variante_id)
            precio = Decimal(str(variante.precio or 0)) if variante else Decimal("0")
            desc, promo_id = await self.promo.mejorDescuento(lin.variante_id, precio, lin.cantidad)
            sub = (precio * lin.cantidad).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            subtotal += sub
            dto_desc += desc
            items.append(
                LineaCarritoDTO(
                    id=lin.id, variante_id=lin.variante_id, cantidad=lin.cantidad,
                    precio_unitario=precio, descuento_unitario=(
                        (desc / lin.cantidad).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        if lin.cantidad else Decimal("0")
                    ),
                    promocion_id=promo_id, subtotal=(sub - desc),
                )
            )
        total = subtotal - dto_desc
        return CarritoDTO(
            id=carrito.id, cliente_id=carrito.cliente_id, canal=carrito.canal,
            estado=carrito.estado, creada_en=carrito.creada_en,
            actualizada_en=carrito.actualizada_en, lineas=items,
            subtotal=subtotal, descuento_total=dto_desc, total=total,
        )

    async def _mutar_con_idempotencia(
        self, usuario: Usuario, canal: str, clave: uuid.UUID, payload: dict, operacion,
        nombre_operacion: str = "MUTAR",
    ) -> Tuple[CarritoDTO, bool]:
        cliente_id = _exigir_cliente(usuario)
        digest = hash_payload(payload)
        ambito_op = (nombre_operacion or "MUTAR").upper()
        try:
            previo = await idem3.reclamar(
                self.db, clave, digest, recurso_tipo="CARRITO",
                operacion=ambito_op, usuario_id=usuario.id,
            )
            if previo is not None and previo.respuesta:
                duenio = str((previo.respuesta or {}).get("cliente_id") or "")
                if duenio and duenio != str(cliente_id):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "codigo": "IDEMPOTENCIA_AMBITO",
                            "mensaje": "Idempotency-Key en uso por otro propietario",
                        },
                    )
                dto = CarritoDTO(**previo.respuesta)
                return dto, False
            dto = await operacion(cliente_id, canal)
            await idem3.guardar_respuesta(
                self.db, clave, dto.model_dump(mode="json"),
                usuario_id=usuario.id, recurso_tipo="CARRITO",
                operacion=ambito_op,
            )
            await self.db.commit()
            return dto, True
        except HTTPException:
            await self.db.rollback()
            raise
        except IntegrityError as e:
            await self.db.rollback()
            if "uq_detalle_carrito_carrito_variante" in str(getattr(e, "orig", e)):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Variante ya en el carrito")
            raise

    async def obtener_mio(self, usuario: Usuario, canal: str = "WEB") -> CarritoDTO:
        cliente_id = _exigir_cliente(usuario)
        carrito = await self._obtener_o_crear(cliente_id, canal)
        return await self._armar_dto(carrito)

    async def _op_agregar(self, dto: LineaAgregarDTO):
        async def _op(cliente_id: uuid.UUID, canal: str) -> CarritoDTO:
            variante = await self.variante_repo.buscarPorId(dto.variante_id)
            if variante is None or not variante.activa:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variante no disponible")
            carrito = await self._obtener_o_crear(cliente_id, canal)
            existente = await self.repo.lineaPorVariante(carrito.id, dto.variante_id)
            if existente is not None:
                existente.cantidad = min(existente.cantidad + dto.cantidad, 99)
                await self.db.flush()
            else:
                await self.repo.agregarLinea(
                    DetalleCarrito(carrito_id=carrito.id, variante_id=dto.variante_id, cantidad=dto.cantidad)
                )
            return await self._armar_dto(carrito)
        return _op

    async def agregar(self, usuario, dto: LineaAgregarDTO, canal="WEB", clave=None) -> Tuple[CarritoDTO, bool]:
        return await self._mutar_con_idempotencia(
            usuario, canal, clave,
            {"op": "agregar", "canal": canal, **dto.model_dump(mode="json")},
            await self._op_agregar(dto),
            "AGREGAR",
        )

    async def modificar(
        self, usuario, variante_id: uuid.UUID, dto: LineaActualizarDTO, canal="WEB", clave=None,
    ) -> Tuple[CarritoDTO, bool]:
        async def _op(cliente_id: uuid.UUID, canal: str) -> CarritoDTO:
            carrito = await self._obtener_o_crear(cliente_id, canal)
            linea = await self.repo.lineaPorVariante(carrito.id, variante_id)
            if linea is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
            linea.cantidad = dto.cantidad
            await self.db.flush()
            return await self._armar_dto(carrito)

        return await self._mutar_con_idempotencia(
            usuario, canal, clave,
            {"op": "modificar", "canal": canal, "variante_id": str(variante_id), **dto.model_dump(mode="json")},
            _op,
            "MODIFICAR",
        )

    async def quitar(self, usuario, variante_id: uuid.UUID, canal="WEB", clave=None) -> Tuple[CarritoDTO, bool]:
        async def _op(cliente_id: uuid.UUID, canal: str) -> CarritoDTO:
            carrito = await self._obtener_o_crear(cliente_id, canal)
            linea = await self.repo.lineaPorVariante(carrito.id, variante_id)
            if linea is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
            await self.repo.eliminarLinea(linea)
            return await self._armar_dto(carrito)

        return await self._mutar_con_idempotencia(
            usuario, canal, clave,
            {"op": "quitar", "canal": canal, "variante_id": str(variante_id)},
            _op,
            "QUITAR",
        )

    async def vaciar(self, usuario, canal="WEB", clave=None) -> Tuple[CarritoDTO, bool]:
        async def _op(cliente_id: uuid.UUID, canal: str) -> CarritoDTO:
            carrito = await self._obtener_o_crear(cliente_id, canal)
            for lin in await self.repo.lineasDe(carrito.id):
                await self.repo.eliminarLinea(lin)
            return await self._armar_dto(carrito)

        return await self._mutar_con_idempotencia(
            usuario, canal, clave, {"op": "vaciar", "canal": canal}, _op,
            "VACIAR",
        )

    # ---------------- cobertura ----------------
    async def cobertura(self, usuario: Usuario, canal: str = "WEB") -> CoberturaDTO:
        cliente_id = _exigir_cliente(usuario)
        carrito = await self.repo.activoDe(cliente_id, canal)
        lineas = await self.repo.lineasDe(carrito.id) if carrito else []
        sucursales = await self.sucursal_repo.listar(solo_activas=True)
        salida: List[CoberturaSucursalDTO] = []
        for suc in sucursales:
            faltantes: List[uuid.UUID] = []
            for lin in lineas:
                fila = await self.inventario_repo.buscarPorVarianteYSucursal(lin.variante_id, suc.id)
                if fila is None or fila.disponible < lin.cantidad:
                    faltantes.append(lin.variante_id)
            salida.append(
                CoberturaSucursalDTO(
                    sucursal_id=suc.id, sucursal_nombre=suc.nombre,
                    cubre_todo=(not faltantes and bool(lineas)), faltantes=faltantes,
                )
            )
        salida.sort(key=lambda s: (not s.cubre_todo, s.sucursal_nombre))
        return CoberturaDTO(sucursales=salida)

    # ---------------- checkout ----------------
    async def _numero_venta(self) -> str:
        for _ in range(5):
            numero = "VTA-" + "".join(secrets.choice(NUMERO_ALFABETO) for _ in range(10))
            if not await self.venta_repo.existeNumero(numero):
                return numero
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo generar un número de venta único",
        )

    async def checkout(
        self, usuario: Usuario, dto: CheckoutCrearDTO, canal: str, clave: uuid.UUID,
    ) -> Tuple[CheckoutRespuestaDTO, bool]:
        cliente_id = _exigir_cliente(usuario)
        digest = hash_payload({**dto.model_dump(mode="json"), "canal": canal})
        try:
            reintento = await resolver_idempotencia(self.db, Venta, clave, digest)
            if reintento is not None:
                if str(reintento.cliente_id or "") != str(cliente_id):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "codigo": "IDEMPOTENCIA_AMBITO",
                            "mensaje": "Idempotency-Key en uso por otro propietario",
                        },
                    )
                pedido = await self.pedido_repo.buscarPorVenta(reintento.id)
                return CheckoutRespuestaDTO(
                    venta_id=reintento.id, numero=reintento.numero,
                    estado=reintento.estado if isinstance(reintento.estado, str) else reintento.estado.name,
                    total=reintento.total, expira_en=reintento.expira_en,
                    pedido_entrega_id=pedido.id if pedido else reintento.id,
                ), False
            salida = await self._checkout_en_tx(usuario, cliente_id, dto, canal, clave, digest)
            await self.db.commit()
            return salida, True
        except IntegrityError as e:
            await self.db.rollback()
            if "clave_idempotencia" in str(getattr(e, "orig", e)).lower():
                existente = await self.venta_repo.buscarPorClave(clave)
                if existente is not None:
                    if str(existente.cliente_id or "") != str(cliente_id):
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail={
                                "codigo": "IDEMPOTENCIA_AMBITO",
                                "mensaje": "Idempotency-Key en uso por otro propietario",
                            },
                        )
                    if existente.hash_solicitud != digest:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail={
                                "codigo": "IDEMPOTENCIA_CONFLICTO",
                                "mensaje": "Idempotency-Key ya usada con otra solicitud",
                            },
                        )
                    pedido = await self.pedido_repo.buscarPorVenta(existente.id)
                    return CheckoutRespuestaDTO(
                        venta_id=existente.id, numero=existente.numero,
                        estado=existente.estado if isinstance(existente.estado, str) else existente.estado.name,
                        total=existente.total, expira_en=existente.expira_en,
                        pedido_entrega_id=pedido.id if pedido else existente.id,
                    ), False
            raise
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al confirmar la compra: transacción revertida sin efectos",
            )

    async def _checkout_en_tx(
        self, usuario: Usuario, cliente_id: uuid.UUID, dto: CheckoutCrearDTO,
        canal: str, clave: uuid.UUID, digest: str,
    ) -> CheckoutRespuestaDTO:
        if dto.canal != canal:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El canal del cuerpo debe coincidir con el del carrito",
            )
        carrito = await self.repo.activoDe(cliente_id, canal)
        lineas = await self.repo.lineasDe(carrito.id) if carrito else []
        if not lineas:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Carrito vacío: nada que confirmar")
        sucursal = await self.sucursal_repo.buscarPorId(dto.sucursal_id)
        if sucursal is None or sucursal.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada en la empresa")
        if not sucursal.activa:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sucursal inactiva")

        ahora = self.reloj.ahora()
        planes = []
        for lin in lineas:
            variante = await self.variante_repo.buscarPorId(lin.variante_id)
            if variante is None or not variante.activa:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Variante {lin.variante_id} ya no disponible",
                )
            precio = Decimal(str(variante.precio or 0))
            if precio <= 0:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Precio inválido al confirmar")
            desc, promo_id = await self.promo.mejorDescuento(lin.variante_id, precio, lin.cantidad, ahora)
            costo = Decimal(str(variante.costo_promedio or 0))
            planes.append((lin, precio, desc, promo_id, costo))

        claves = sorted(
            {(dto.sucursal_id, lin.variante_id) for lin in lineas},
            key=lambda c: (str(c[0]), str(c[1])),
        )
        filas = await self.inventario_repo.bloquearFilas(claves)
        for lin, _, _, _, _ in planes:
            fila = filas.get((dto.sucursal_id, lin.variante_id))
            if fila is None or fila.disponible < lin.cantidad:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ninguna sucursal cubre el carrito completo con esta sucursal",
                )

        subtotal = sum(
            (p * l.cantidad for l, p, _, _, _ in planes), Decimal("0")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        descuento = sum((d for _, _, d, _, _ in planes), Decimal("0"))
        if dto.modalidad == "DELIVERY":
            if not dto.direccion or dto.anillo_destino is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Delivery exige dirección y anillo_destino",
                )
            if not sucursal.delivery_activo:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sucursal sin delivery activo")
            minimo = int(sucursal.anillo_minimo_delivery or 1)
            maximo = int(sucursal.anillo_maximo_delivery or 10)
            if not (minimo <= dto.anillo_destino <= maximo):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Anillo fuera de rango [{minimo}, {maximo}]",
                )
            base = Decimal(str(sucursal.tarifa_base_delivery or 0))
            incr = Decimal(str(sucursal.incremento_anillo_delivery or 0))
            anillo_suc = int(sucursal.numero_anillo or minimo)
            costo_entrega = (base + abs(dto.anillo_destino - anillo_suc) * incr).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            if dto.anillo_destino is not None or dto.direccion:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Recojo no admite dirección ni anillo de delivery",
                )
            base = incr = Decimal("0")
            anillo_suc = int(sucursal.numero_anillo or 1)
            costo_entrega = Decimal("0")
        total = (subtotal - descuento + costo_entrega).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        venta = Venta(
            empresa_id=usuario.empresa_id,
            numero=await self._numero_venta(),
            cliente_id=cliente_id,
            reserva_id=None,
            sucursal_id=dto.sucursal_id,
            cajero_id=None,
            canal=dto.canal,
            estado="PENDIENTE_PAGO",
            subtotal=subtotal,
            descuento=descuento,
            costo_entrega=costo_entrega,
            total=total,
            creada_en=ahora,
            confirmada_en=None,
            expira_en=ahora + VENTANA_COMPROMISO,
            clave_idempotencia=clave,
            hash_solicitud=digest,
        )
        await self.venta_repo.crear(venta)

        for lin, precio, desc, promo_id, costo in planes:
            detalle = DetalleVenta(
                venta_id=venta.id,
                detalle_reserva_id=None,
                variante_id=lin.variante_id,
                cantidad=lin.cantidad,
                precio_unitario=precio,
                descuento=desc,
                costo_promedio=costo,
                promocion_id=promo_id,
            )
            await self.detalle_venta_repo.crear(detalle)
            fila = filas[(dto.sucursal_id, lin.variante_id)]
            fila.disponible -= lin.cantidad
            fila.reservado += lin.cantidad
            await self.db.flush()
            await self.movimiento_repo.registrar(
                MovimientoInventario(
                    variante_id=lin.variante_id,
                    sucursal_destino_id=dto.sucursal_id,
                    tipo="COMPROMISO_DIGITAL",
                    cantidad=lin.cantidad,
                    costo_unitario=costo,
                    referencia_tipo="VENTA",
                    referencia_id=venta.id,
                    linea_referencia_id=detalle.id,
                    observacion=f"Compromiso digital {venta.numero} (60 min)",
                )
            )

        if dto.modalidad == "RECOJO":
            codigo = "RCG-" + "".join(secrets.choice(NUMERO_ALFABETO) for _ in range(6))
        else:
            codigo = None
        pedido = PedidoEntrega(
            empresa_id=usuario.empresa_id,
            venta_id=venta.id,
            sucursal_id=dto.sucursal_id,
            cliente_id=cliente_id,
            modalidad=dto.modalidad,
            estado="SOLICITADO",
            anillo_sucursal=anillo_suc,
            anillo_destino=dto.anillo_destino,
            anillo_minimo=int(sucursal.anillo_minimo_delivery or 1),
            anillo_maximo=int(sucursal.anillo_maximo_delivery or 10),
            direccion=dto.direccion,
            tarifa_base=base,
            incremento_anillo=incr,
            costo_entrega=costo_entrega,
            codigo_recojo=codigo,
        )
        await self.pedido_repo.crear(pedido)
        carrito.estado = "CONVERTIDO"
        carrito.convertida_en = ahora
        carrito.venta_id = venta.id
        await self.db.flush()
        try:
            async with self.db.begin_nested():
                self.db.add(
                    HistorialNavegacion(
                        empresa_id=usuario.empresa_id,
                        cliente_id=cliente_id, usuario_id=usuario.id, evento="COMPRA",
                        metadatos={"venta_id": str(venta.id), "canal": dto.canal},
                    )
                )
                await self.db.flush()
        except Exception:
            pass
        return CheckoutRespuestaDTO(
            venta_id=venta.id, numero=venta.numero, estado="PENDIENTE_PAGO",
            total=total, expira_en=venta.expira_en, pedido_entrega_id=pedido.id,
        )
