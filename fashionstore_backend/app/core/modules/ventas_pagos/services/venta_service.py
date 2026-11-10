"""Controller VentaService — CU11 (RF17, RF18, RF20)."""
import secrets
import string
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.app.core.ambito_comercial import empresa_comercial, exigir_empresa_recurso, sucursal_autorizada
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.idempotencia import hash_payload, resolver_idempotencia
from backend.app.core.permisos import es_admin, exigir_sucursal
from backend.app.core.reloj import RelojSistema
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, Pago, Venta
from backend.app.core.modules.inventario.models import MovimientoInventario
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.ventas_pagos.repositories.pago_repository import PagoRepository
from backend.app.core.modules.reservas_traslados.repositories.reserva_repository import ReservaRepository
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.modules.ventas_pagos.repositories.venta_repository import DetalleVentaRepository, VentaRepository
from backend.app.core.modules.ventas_pagos.schemas import (
    ComprobanteDTO,
    DetalleVentaDTO,
    PagoDTO,
    VentaDTO,
    VentaPresencialCrearDTO,
)

NUMERO_ALFABETO = string.ascii_uppercase + string.digits


class VentaService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.venta_repo = VentaRepository(db)
        self.detalle_repo = DetalleVentaRepository(db)
        self.pago_repo = PagoRepository(db)
        self.reserva_repo = ReservaRepository(db)
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)
        self.sucursal_repo = SucursalRepository(db)
        self.variante_repo = VarianteRepository(db)

    # ---------------- utilidades ----------------
    def _autorizar_caja(self, usuario: Usuario, sucursal_id: uuid.UUID) -> None:
        empresa_comercial(usuario)
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CAJERO":
            exigir_sucursal(usuario, sucursal_id)
            return
        if es_admin(usuario):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Cajero o Administrador")

    async def _numero_unico(self) -> str:
        for _ in range(5):
            numero = "VTA-" + "".join(secrets.choice(NUMERO_ALFABETO) for _ in range(10))
            if not await self.venta_repo.existeNumero(numero):
                return numero
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo generar un numero de venta unico",
        )

    def _con_costos(self, usuario: Usuario) -> bool:
        return (usuario.rol.nombre if usuario.rol else "").upper() in ("ADMINISTRADOR", "ENCARGADO") or es_admin(usuario)

    async def _a_dto(self, venta_id: uuid.UUID, con_costos: bool, empresa_id) -> VentaDTO:
        venta = await self.venta_repo.buscarPorId(venta_id, empresa_id=empresa_id)
        if venta is None:  # pragma: no cover
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada")
        return VentaDTO(
            id=venta.id, numero=venta.numero, cliente_id=venta.cliente_id,
            reserva_id=venta.reserva_id, sucursal_id=venta.sucursal_id, cajero_id=venta.cajero_id,
            canal=venta.canal if isinstance(venta.canal, str) else str(venta.canal),
            estado=venta.estado if isinstance(venta.estado, str) else venta.estado.name,
            subtotal=venta.subtotal, descuento=venta.descuento,
            adelanto_descontado=venta.adelanto_descontado, costo_entrega=venta.costo_entrega,
            total=venta.total, creada_en=venta.creada_en, confirmada_en=venta.confirmada_en,
            expira_en=getattr(venta, "expira_en", None),
            detalles=[
                DetalleVentaDTO(
                    id=d.id, detalle_reserva_id=d.detalle_reserva_id, variante_id=d.variante_id,
                    cantidad=d.cantidad, precio_unitario=d.precio_unitario, descuento=d.descuento,
                    promocion_id=getattr(d, "promocion_id", None),
                    costo_promedio=d.costo_promedio if con_costos else None,
                )
                for d in venta.detalles
            ],
        )

    async def _a_comprobante(self, venta_id: uuid.UUID, con_costos: bool, empresa_id) -> ComprobanteDTO:
        base = await self._a_dto(venta_id, con_costos, empresa_id)
        venta = await self.venta_repo.buscarPorId(venta_id, empresa_id=empresa_id)
        pagos = await self.pago_repo.pagosDeVenta(venta_id, empresa_id=venta.empresa_id)
        comp = ComprobanteDTO(**base.model_dump())
        if venta.reserva_id is not None:
            reserva = await self.reserva_repo.buscarPorId(venta.reserva_id)
            comp.reserva_codigo = reserva.codigo if reserva and reserva.empresa_id == venta.empresa_id else None
        sucursal = await self.sucursal_repo.buscarPorId(venta.sucursal_id)
        comp.sucursal_nombre = sucursal.nombre if sucursal and sucursal.empresa_id == venta.empresa_id else None
        if venta.cajero_id is not None:
            from backend.app.core.modules.identidad_empresas.models import Usuario as ModeloUsuario

            cajero = await self.db.get(ModeloUsuario, venta.cajero_id)
            comp.cajero_nombre = cajero.nombre_completo if cajero and cajero.empresa_id == venta.empresa_id else None
        comp.pagos = [PagoDTO.model_validate(p) for p in pagos]
        return comp

    def _autorizar_lectura_venta(self, usuario: Usuario, venta: Venta) -> None:
        exigir_empresa_recurso(usuario, venta)
        if es_admin(usuario):
            return
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE":
            if venta.cliente_id != usuario.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Comprobante de otro cliente")
            return
        if rol in ("CAJERO", "ENCARGADO"):
            exigir_sucursal(usuario, venta.sucursal_id)
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado")

    async def _resolver_venta(self, identificador: Any, empresa_id) -> Optional[Venta]:
        if isinstance(identificador, uuid.UUID):
            return await self.venta_repo.buscarPorId(identificador, empresa_id=empresa_id)
        if isinstance(identificador, str):
            texto = identificador.strip()
            try:
                uid = uuid.UUID(texto)
                return await self.venta_repo.buscarPorId(uid, empresa_id=empresa_id)
            except ValueError:
                return await self.venta_repo.buscarPorNumero(texto, empresa_id=empresa_id)
        return None

    async def obtener(self, usuario: Usuario, venta_id: Any) -> VentaDTO:
        venta = await self._resolver_venta(venta_id, empresa_comercial(usuario))
        if venta is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada")
        self._autorizar_lectura_venta(usuario, venta)
        await sucursal_autorizada(self.db, usuario, venta.sucursal_id)
        return await self._a_dto(venta.id, self._con_costos(usuario), usuario.empresa_id)

    async def obtenerComprobante(self, usuario: Usuario, venta_id: Any) -> ComprobanteDTO:
        venta = await self._resolver_venta(venta_id, empresa_comercial(usuario))
        if venta is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada")
        self._autorizar_lectura_venta(usuario, venta)
        await sucursal_autorizada(self.db, usuario, venta.sucursal_id)
        return await self._a_comprobante(venta.id, self._con_costos(usuario), usuario.empresa_id)

    # ---------------- historial CU13 (Entrega 7) ----------------
    async def historialCliente(
        self,
        usuario: Usuario,
        cliente_id: uuid.UUID,
        desde=None,
        hasta=None,
        limit: int = 50,
        offset: int = 0,
    ):
        """Historial paginado del cliente (propietario o administrador).

        Costos congelados solo para ADMIN; el cliente ve precios e importes.
        """
        from backend.app.core.modules.identidad_empresas.models import Cliente

        empresa_id = empresa_comercial(usuario)
        if usuario.id != cliente_id and not es_admin(usuario):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el propietario o el Administrador")
        existe = (await self.db.execute(select(Cliente).join(Usuario, Usuario.id == Cliente.usuario_id).where(Cliente.usuario_id == cliente_id, Usuario.empresa_id == empresa_id))).scalars().first()
        if existe is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
        from backend.app.core.reloj import entrada_local_a_utc
        desde = entrada_local_a_utc(desde) if desde is not None else None
        hasta = entrada_local_a_utc(hasta) if hasta is not None else None
        ventas, total = await self.venta_repo.porCliente(
            cliente_id, desde=desde, hasta=hasta, limit=limit, offset=offset, empresa_id=empresa_id
        )
        con_costos = es_admin(usuario)
        return {
            "total": total, "limit": limit, "offset": offset,
            "items": [await self._a_dto(v.id, con_costos, empresa_id) for v in ventas],
        }

    # ---------------- venta presencial ----------------
    async def registrarPresencial(
        self, usuario: Usuario, dto: VentaPresencialCrearDTO, clave: uuid.UUID
    ) -> Tuple[ComprobanteDTO, bool]:
        self._autorizar_caja(usuario, dto.sucursal_id)
        await sucursal_autorizada(self.db, usuario, dto.sucursal_id)
        digest = hash_payload(dto.model_dump(mode="json"))
        try:
            reintento = await resolver_idempotencia(self.db, Venta, clave, digest)
            if reintento is not None:
                self._autorizar_lectura_venta(usuario, reintento)
                return await self._a_comprobante(reintento.id, self._con_costos(usuario), usuario.empresa_id), False
            capacidad = await PlanService(self.db).validar_capacidad(
                usuario.empresa_id, fecha_referencia=self.reloj.ahora()
            )
            if not capacidad.habilitado:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=capacidad.motivo_rechazo or "La suscripción no habilita nuevas ventas",
                )
            venta = await self._venta_en_tx(usuario, dto, clave, digest)
            salida = await self._a_comprobante(venta.id, self._con_costos(usuario), usuario.empresa_id)
            await self.db.commit()
            return salida, True
        except IntegrityError as e:
            await self.db.rollback()
            if "clave_idempotencia" in str(getattr(e, "orig", e)):
                existente = await self.venta_repo.buscarPorClave(clave)
                if existente is not None:
                    self._autorizar_lectura_venta(usuario, existente)
                    if existente.hash_solicitud != digest:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key ya usada con otra solicitud")
                    return await self._a_comprobante(existente.id, self._con_costos(usuario), usuario.empresa_id), False
            raise
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def _venta_en_tx(
        self, usuario: Usuario, dto: VentaPresencialCrearDTO, clave: uuid.UUID, digest: str
    ) -> Venta:
        self._autorizar_caja(usuario, dto.sucursal_id)
        if not usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )
        if not dto.items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La venta requiere al menos un item")
        vistos_variante, vistos_linea = set(), set()
        for item in dto.items:
            if item.cantidad <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cantidad vendida debe ser mayor a cero")
            if item.variante_id in vistos_variante:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variante duplicada en la venta")
            vistos_variante.add(item.variante_id)
            if item.detalle_reserva_id is not None:
                if item.detalle_reserva_id in vistos_linea:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Linea de reserva duplicada en la venta")
                vistos_linea.add(item.detalle_reserva_id)
        sucursal = await self.sucursal_repo.buscarPorId(dto.sucursal_id)
        if sucursal is None or sucursal.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada en la empresa")
        if not sucursal.activa:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sucursal inactiva")

        if dto.cliente_id is not None:
            from backend.app.core.modules.identidad_empresas.models import Cliente
            cliente = (await self.db.execute(
                select(Cliente.usuario_id).join(Usuario, Usuario.id == Cliente.usuario_id).where(
                    Cliente.usuario_id == dto.cliente_id, Usuario.empresa_id == usuario.empresa_id
                )
            )).scalar()
            if cliente is None:
                raise HTTPException(status_code=404, detail="Cliente no encontrado")

        reserva = None
        if dto.reserva_id is not None:
            reserva = await self.reserva_repo.buscarPorId(dto.reserva_id)
            if reserva is None or reserva.empresa_id != usuario.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
            if reserva.sucursal_destino_id != dto.sucursal_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La reserva pertenece a otra sucursal")
            if reserva.estado != "ATENDIDA":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Solo reservas ATENDIDA pueden venderse (estado {reserva.estado})",
                )
            if reserva.vence_en is not None and reserva.vence_en <= self.reloj.ahora():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reserva vencida")
            for item in dto.items:
                if item.detalle_reserva_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="En venta desde reserva cada item debe referenciar su linea (detalle_reserva_id)",
                    )
        elif any(i.detalle_reserva_id is not None for i in dto.items):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="detalle_reserva_id exige reserva_id (venta directa usa variante_id)",
            )

        lineas_reserva: Dict[uuid.UUID, object] = {}
        if reserva is not None:
            for det in reserva.detalles:
                lineas_reserva[det.id] = det
            for item in dto.items:
                linea = lineas_reserva.get(item.detalle_reserva_id)
                if linea is None:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Linea de reserva ajena a la reserva indicada")
                if linea.variante_id != item.variante_id:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La variante no corresponde a la linea de reserva")
                if linea.estado_linea not in ("RESERVADA", "VENDIDA_PARCIAL"):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Linea no vendible (estado {linea.estado_linea})",
                    )
                if item.cantidad > linea.cantidad_reservada:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cantidad mayor a la reservada disponible")

        variantes: Dict[uuid.UUID, object] = {}
        for item in dto.items:
            variante = await self.variante_repo.buscarPorId(item.variante_id)
            if variante is None or variante.empresa_id != usuario.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variante {item.variante_id} no encontrada")
            variantes[item.variante_id] = variante

        claves = sorted({(dto.sucursal_id, i.variante_id) for i in dto.items}, key=lambda c: (str(c[0]), str(c[1])))
        filas = await self.inventario_repo.bloquearFilas(claves)

        ahora = self.reloj.ahora()
        subtotal = Decimal("0")
        planes = []  # (item, precio, costo)
        for item in dto.items:
            fila = filas.get((dto.sucursal_id, item.variante_id))
            variante = variantes[item.variante_id]
            precio = Decimal(str(variante.precio or 0))
            costo = Decimal(str(variante.costo_promedio or 0))
            if reserva is not None:
                linea = lineas_reserva[item.detalle_reserva_id]
                if fila is None or fila.reservado < item.cantidad:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stock reservado insuficiente")
                if item.cantidad > linea.cantidad_reservada:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cantidad mayor a la reservada disponible")
            else:
                if fila is None or fila.disponible < item.cantidad:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sin stock disponible en sucursal")
            subtotal += precio * item.cantidad
            planes.append((item, precio, costo))

        adelanto_desc = Decimal("0")
        if reserva is not None and reserva.adelanto_monto:
            if not await self.venta_repo.adelantoYaDescontado(reserva.id):
                adelanto_desc = min(Decimal(str(reserva.adelanto_monto)), subtotal)
        total = subtotal - adelanto_desc

        venta = Venta(
            empresa_id=usuario.empresa_id,
            numero=await self._numero_unico(),
            cliente_id=dto.cliente_id or (reserva.cliente_id if reserva else None),
            reserva_id=reserva.id if reserva else None,
            sucursal_id=dto.sucursal_id,
            cajero_id=usuario.id,
            canal="PRESENCIAL",
            estado="PAGADA",
            subtotal=subtotal,
            descuento=Decimal("0"),
            costo_entrega=Decimal("0"),
            adelanto_descontado=adelanto_desc,
            total=total,
            creada_en=ahora,
            confirmada_en=ahora,
            entregada_en=ahora,
            clave_idempotencia=clave,
            hash_solicitud=digest,
        )
        await self.venta_repo.crear(venta)

        for item, precio, costo in planes:
            linea = lineas_reserva.get(item.detalle_reserva_id) if reserva is not None else None
            det_venta = DetalleVenta(
                venta_id=venta.id,
                detalle_reserva_id=linea.id if linea is not None else None,
                variante_id=item.variante_id,
                cantidad=item.cantidad,
                precio_unitario=precio,
                descuento=Decimal("0"),
                costo_promedio=costo,
            )
            await self.detalle_repo.crear(det_venta)
            fila = filas[(dto.sucursal_id, item.variante_id)]
            if reserva is not None:
                fila.reservado -= item.cantidad
                linea.cantidad_reservada -= item.cantidad
                linea.cantidad_vendida += item.cantidad
            else:
                fila.disponible -= item.cantidad
            await self.db.flush()
            await self.movimiento_repo.registrar(
                MovimientoInventario(
                    variante_id=item.variante_id,
                    sucursal_origen_id=dto.sucursal_id if reserva is None else None,
                    sucursal_destino_id=dto.sucursal_id,
                    tipo="VENTA_PRESENCIAL",
                    cantidad=item.cantidad,
                    costo_unitario=costo,
                    referencia_tipo="VENTA",
                    referencia_id=venta.id,
                    linea_referencia_id=det_venta.id,
                    observacion=f"Venta presencial {venta.numero}",
                )
            )
            if linea is not None:
                linea.estado_linea = (
                    "VENDIDA" if linea.cantidad_vendida >= linea.cantidad_reservada else "VENDIDA_PARCIAL"
                )
                await self.db.flush()

        if total > 0:
            from backend.app.core.modules.ventas_pagos.services.pago_service import PagoService

            await PagoService(self.db, self.reloj).registrarCaja(
                venta_id=venta.id, metodo=dto.metodo, monto=total,
                pagado_en=ahora, clave=clave, digest=digest,
                empresa_id=venta.empresa_id,
            )

        if reserva is not None:
            for det in reserva.detalles:
                if det.estado_linea in ("RESERVADA", "VENDIDA_PARCIAL"):
                    resto = det.cantidad_reservada
                    if resto > 0:
                        fila = filas.get((dto.sucursal_id, det.variante_id))
                        if fila is None:  # pragma: no cover (defensivo)
                            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Inconsistencia de inventario al liberar")
                        fila.reservado -= resto
                        fila.disponible += resto
                        await self.db.flush()
                        await self.movimiento_repo.registrar(
                            MovimientoInventario(
                                variante_id=det.variante_id,
                                sucursal_destino_id=dto.sucursal_id,
                                tipo="LIBERACION_RESERVA",
                                cantidad=resto,
                                costo_unitario=Decimal("0"),
                                referencia_tipo="VENTA",
                                referencia_id=venta.id,
                                linea_referencia_id=det.id,
                                observacion=f"Liberacion de no comprado ({venta.numero})",
                            )
                        )
                    det.cantidad_liberada += resto
                    det.cantidad_reservada = 0
                    if det.cantidad_vendida <= 0:
                        det.estado_linea = "LIBERADA"
                    elif det.cantidad_liberada <= 0:
                        det.estado_linea = "VENDIDA"
                    else:
                        det.estado_linea = "VENDIDA_PARCIAL"
                    await self.db.flush()
            await self.reserva_repo.actualizarEstado(reserva, "COMPLETADA")
        return venta
