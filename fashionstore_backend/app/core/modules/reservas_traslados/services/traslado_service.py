"""Controller TrasladoService — CU09 (RF21, RF22, extension).

  solicitar()/aprobar()/rechazar()/despachar()/recibir()
  Datos TrasladoRepository.*, InventarioRepository.comprometer()/marcarEnTransito()/recibir()
    (implementados aqui como movimientos con revalidacion), MovimientoRepository.registrar(
    tipo=COMPROMISO_TRASLADO/DESPACHO_TRASLADO/RECEPCION_TRASLADO)

Matriz: SOLICITADO -> APROBADO -> DESPACHADO -> RECIBIDO; SOLICITADO -> RECHAZADO
(o CANCELADO al cancelarse/vencer la reserva). Origen invalido -> 409;
repeticion exacta -> recurso actual sin efectos. Sin commit en repositorios.
"""
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.idempotencia import hash_payload, resolver_idempotencia
from backend.app.core.permisos import es_admin, exigir_sucursal
from backend.app.core.reloj import RelojSistema
from backend.app.core.modules.reservas_traslados.models import DetalleReserva
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.reservas_traslados.models import DetalleTraslado, Traslado
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.reservas_traslados.repositories.traslado_repository import TrasladoRepository
from backend.app.core.modules.reservas_traslados.repositories.reserva_repository import (
    ESTADOS_NO_TERMINALES_RESERVA,
    ReservaRepository,
)
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.reservas_traslados.schemas import TrasladoDTO, TrasladoRechazarDTO, TrasladoSolicitarDTO

ESTADOS_ACTIVOS_TRASLADO = ("SOLICITADO", "APROBADO", "DESPACHADO")


class TrasladoService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.traslado_repo = TrasladoRepository(db)
        self.reserva_repo = ReservaRepository(db)
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)
        self.sucursal_repo = SucursalRepository(db)

    # ---------------- helpers ----------------
    async def _a_dto(self, traslado_id: uuid.UUID) -> TrasladoDTO:
        from backend.app.core.modules.reservas_traslados.schemas import DetalleTrasladoDTO

        traslado = await self.traslado_repo.buscarPorId(traslado_id)
        if traslado is None:  # pragma: no cover
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traslado no encontrado")
        detalles = await self.traslado_repo.detallesDeTraslado(traslado.id)
        return TrasladoDTO(
            id=traslado.id,
            reserva_id=traslado.reserva_id,
            sucursal_origen_id=traslado.sucursal_origen_id,
            sucursal_destino_id=traslado.sucursal_destino_id,
            estado=traslado.estado if isinstance(traslado.estado, str) else traslado.estado.name,
            solicitado_por_id=traslado.solicitado_por_id,
            aprobado_por_id=traslado.aprobado_por_id,
            fecha_solicitud=traslado.fecha_solicitud,
            fecha_aprobacion=traslado.fecha_aprobacion,
            fecha_despacho=traslado.fecha_despacho,
            fecha_recepcion=traslado.fecha_recepcion,
            motivo_rechazo=traslado.motivo_rechazo,
            detalles=[DetalleTrasladoDTO.model_validate(d) for d in detalles],
        )

    def _autorizar_origen(self, usuario: Usuario, origen_id: uuid.UUID) -> None:
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "ENCARGADO":
            exigir_sucursal(usuario, origen_id)
            return
        if es_admin(usuario):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Encargado de origen o Administrador")

    def _autorizar_destino(self, usuario: Usuario, destino_id: uuid.UUID) -> None:
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "ENCARGADO":
            exigir_sucursal(usuario, destino_id)
            return
        if es_admin(usuario):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Encargado de destino o Administrador")

    def _autorizar_solicitud(self, usuario: Usuario, reserva) -> None:
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE":
            if usuario.id != reserva.cliente_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el propietario puede reintentar su linea")
            return
        if rol in ("ENCARGADO",) or es_admin(usuario):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado para solicitar traslados")

    async def _derivar_estado_reserva(self, reserva) -> None:
        """Deriva la cabecera desde sus lineas (decision de dominio cerrada)."""
        recargada = await self.reserva_repo.buscarPorId(reserva.id)
        estados = {d.estado_linea for d in recargada.detalles}
        if "PENDIENTE_TRASLADO" in estados:
            nuevo = "PENDIENTE_TRASLADO"
        elif "RESERVADA" in estados:
            nuevo = "PENDIENTE"
        elif estados and estados <= {"RECHAZADA", "LIBERADA"}:
            nuevo = "CANCELADA"
            for det in recargada.detalles:
                if det.estado_linea == "RESERVADA" and det.cantidad_reservada > 0:
                    fila = (
                        await self.db.execute(
                            select(InventarioSucursal).where(
                                InventarioSucursal.variante_id == det.variante_id,
                                InventarioSucursal.sucursal_id == recargada.sucursal_destino_id,
                            )
                        )
                    ).scalars().first()
                    if fila is not None:
                        fila.reservado -= det.cantidad_reservada
                        fila.disponible += det.cantidad_reservada
                        await self.db.flush()
                        await self.movimiento_repo.registrar(
                            MovimientoInventario(
                                variante_id=det.variante_id,
                                sucursal_destino_id=recargada.sucursal_destino_id,
                                tipo="LIBERACION_RESERVA",
                                cantidad=det.cantidad_reservada,
                                costo_unitario=Decimal("0"),
                                referencia_tipo="RESERVA",
                                referencia_id=recargada.id,
                                linea_referencia_id=det.id,
                            )
                        )
                    det.cantidad_liberada += det.cantidad_reservada
                    det.cantidad_reservada = 0
                    det.estado_linea = "LIBERADA"
                    await self.db.flush()
        else:
            return  # estados de atencion/venta: la cabecera la gobierna otro flujo
        if nuevo != recargada.estado:
            await self.reserva_repo.actualizarEstado(recargada, nuevo)

    # ---------------- solicitar (reintento) ----------------
    async def solicitar(
        self, usuario: Usuario, dto: TrasladoSolicitarDTO, clave: uuid.UUID
    ) -> Tuple[TrasladoDTO, bool]:
        digest = hash_payload(dto.model_dump(mode="json"))
        try:
            reintento = await resolver_idempotencia(self.db, Traslado, clave, digest)
            if reintento is not None:
                return await self._a_dto(reintento.id), False
            traslado = await self._solicitar_en_tx(usuario, dto, clave, digest)
            salida = await self._a_dto(traslado.id)
            await self.db.commit()
            return salida, True
        except IntegrityError as e:
            await self.db.rollback()
            if "clave_idempotencia" in str(getattr(e, "orig", e)):
                existente = await self.traslado_repo.buscarPorClave(clave)
                if existente is not None:
                    if existente.hash_solicitud != digest:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key ya usada con otra solicitud")
                    return await self._a_dto(existente.id), False
            raise
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def _solicitar_en_tx(self, usuario, dto, clave, digest) -> Traslado:
        detalle = await self.db.get(DetalleReserva, dto.detalle_reserva_id)
        if detalle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linea de reserva no encontrada")
        reserva = await self.reserva_repo.buscarPorId(detalle.reserva_id)
        if reserva is None:  # pragma: no cover
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
        self._autorizar_solicitud(usuario, reserva)
        if detalle.estado_linea != "RECHAZADA":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Solo lineas RECHAZADAS admiten reintento (linea en {detalle.estado_linea})",
            )
        if reserva.estado not in ESTADOS_NO_TERMINALES_RESERVA:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Reserva no vigente (estado {reserva.estado})")
        if (reserva.vence_en is not None) and (reserva.vence_en <= self.reloj.ahora()):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reserva vencida")
        if await self.traslado_repo.buscarActivoPorLinea(detalle.id) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="La linea ya tiene un traslado activo")
        if dto.sucursal_origen_id == reserva.sucursal_destino_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Origen y destino deben ser distintos")
        origen = await self.sucursal_repo.buscarPorId(dto.sucursal_origen_id)
        if origen is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal origen no encontrada")
        if not origen.activa:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sucursal origen inactiva")
        filas = await self.inventario_repo.bloquearFilas([(dto.sucursal_origen_id, detalle.variante_id)])
        fila = filas[(dto.sucursal_origen_id, detalle.variante_id)]
        if fila is None or fila.disponible < detalle.cantidad_solicitada:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sin stock suficiente en el origen indicado")
        traslado = Traslado(
            empresa_id=reserva.empresa_id,
            reserva_id=reserva.id,
            sucursal_origen_id=dto.sucursal_origen_id,
            sucursal_destino_id=reserva.sucursal_destino_id,
            estado="SOLICITADO",
            solicitado_por_id=usuario.id,
            clave_idempotencia=clave,
            hash_solicitud=digest,
        )
        await self.traslado_repo.crear(traslado)
        self.db.add(
            DetalleTraslado(
                traslado_id=traslado.id,
                detalle_reserva_id=detalle.id,
                variante_id=detalle.variante_id,
                cantidad=detalle.cantidad_solicitada,
            )
        )
        detalle.estado_linea = "PENDIENTE_TRASLADO"
        detalle.cantidad_pendiente_traslado = detalle.cantidad_solicitada
        await self.db.flush()
        await self._derivar_estado_reserva(reserva)
        return traslado

    # ---------------- aprobar ----------------
    async def aprobar(self, usuario: Usuario, traslado_id: uuid.UUID) -> TrasladoDTO:
        try:
            traslado = await self.traslado_repo.buscarPorId(traslado_id)
            if traslado is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traslado no encontrado")
            self._autorizar_origen(usuario, traslado.sucursal_origen_id)
            if traslado.estado == "APROBADO":
                return await self._a_dto(traslado.id)  # repeticion idempotente
            if traslado.estado != "SOLICITADO":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No se puede aprobar un traslado en estado {traslado.estado}",
                )
            detalles = await self.traslado_repo.detallesDeTraslado(traslado.id)
            reserva = await self.reserva_repo.buscarPorId(traslado.reserva_id) if traslado.reserva_id else None
            if reserva is not None and reserva.estado not in ESTADOS_NO_TERMINALES_RESERVA:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Reserva no vigente (estado {reserva.estado})")
            claves = sorted({(traslado.sucursal_origen_id, d.variante_id) for d in detalles},
                            key=lambda c: (str(c[0]), str(c[1])))
            filas = await self.inventario_repo.bloquearFilas(claves)
            for d in detalles:
                fila = filas[(traslado.sucursal_origen_id, d.variante_id)]
                if fila is None or fila.disponible < d.cantidad:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sin stock disponible en origen para aprobar")
            for d in detalles:
                fila = filas[(traslado.sucursal_origen_id, d.variante_id)]
                fila.disponible -= d.cantidad
                fila.comprometido_traslado += d.cantidad
                await self.db.flush()
                await self.movimiento_repo.registrar(
                    MovimientoInventario(
                        variante_id=d.variante_id,
                        sucursal_origen_id=traslado.sucursal_origen_id,
                        sucursal_destino_id=traslado.sucursal_destino_id,
                        tipo="COMPROMISO_TRASLADO",
                        cantidad=d.cantidad,
                        costo_unitario=Decimal("0"),
                        referencia_tipo="TRASLADO",
                        referencia_id=traslado.id,
                        linea_referencia_id=d.id,
                    )
                )
            traslado.estado = "APROBADO"
            traslado.aprobado_por_id = usuario.id
            traslado.fecha_aprobacion = self.reloj.ahora()
            await self.db.flush()
            salida = await self._a_dto(traslado.id)
            await self.db.commit()
            return salida
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    # ---------------- rechazar ----------------
    async def rechazar(self, usuario: Usuario, traslado_id: uuid.UUID, dto: TrasladoRechazarDTO) -> TrasladoDTO:
        try:
            traslado = await self.traslado_repo.buscarPorId(traslado_id)
            if traslado is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traslado no encontrado")
            self._autorizar_origen(usuario, traslado.sucursal_origen_id)
            if traslado.estado == "RECHAZADO":
                return await self._a_dto(traslado.id)  # repeticion idempotente
            if traslado.estado != "SOLICITADO":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No se puede rechazar un traslado en estado {traslado.estado}",
                )
            traslado.estado = "RECHAZADO"
            traslado.motivo_rechazo = dto.motivo
            await self.db.flush()
            detalles = await self.traslado_repo.detallesDeTraslado(traslado.id)
            reserva = await self.reserva_repo.buscarPorId(traslado.reserva_id) if traslado.reserva_id else None
            for d in detalles:
                if d.detalle_reserva_id is None:
                    continue
                linea = await self.db.get(DetalleReserva, d.detalle_reserva_id)
                if linea is not None and linea.estado_linea == "PENDIENTE_TRASLADO":
                    linea.estado_linea = "RECHAZADA"
                    linea.cantidad_pendiente_traslado = 0
                    await self.db.flush()
            if reserva is not None:
                await self._derivar_estado_reserva(reserva)
            salida = await self._a_dto(traslado.id)
            await self.db.commit()
            return salida
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    # ---------------- despachar ----------------
    async def despachar(self, usuario: Usuario, traslado_id: uuid.UUID) -> TrasladoDTO:
        try:
            traslado = await self.traslado_repo.buscarPorId(traslado_id)
            if traslado is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traslado no encontrado")
            self._autorizar_origen(usuario, traslado.sucursal_origen_id)
            if traslado.estado == "DESPACHADO":
                return await self._a_dto(traslado.id)  # repeticion idempotente
            if traslado.estado != "APROBADO":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No se puede despachar un traslado en estado {traslado.estado}",
                )
            detalles = await self.traslado_repo.detallesDeTraslado(traslado.id)
            claves = sorted({(traslado.sucursal_origen_id, d.variante_id) for d in detalles},
                            key=lambda c: (str(c[0]), str(c[1])))
            filas = await self.inventario_repo.bloquearFilas(claves)
            for d in detalles:
                fila = filas[(traslado.sucursal_origen_id, d.variante_id)]
                if fila is None or fila.comprometido_traslado < d.cantidad:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stock comprometido insuficiente para despachar")
            for d in detalles:
                fila = filas[(traslado.sucursal_origen_id, d.variante_id)]
                fila.comprometido_traslado -= d.cantidad
                fila.en_transito += d.cantidad
                await self.db.flush()
                await self.movimiento_repo.registrar(
                    MovimientoInventario(
                        variante_id=d.variante_id,
                        sucursal_origen_id=traslado.sucursal_origen_id,
                        sucursal_destino_id=traslado.sucursal_destino_id,
                        tipo="DESPACHO_TRASLADO",
                        cantidad=d.cantidad,
                        costo_unitario=Decimal("0"),
                        referencia_tipo="TRASLADO",
                        referencia_id=traslado.id,
                        linea_referencia_id=d.id,
                    )
                )
            traslado.estado = "DESPACHADO"
            traslado.fecha_despacho = self.reloj.ahora()
            await self.db.flush()
            salida = await self._a_dto(traslado.id)
            await self.db.commit()
            return salida
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    # ---------------- recibir ----------------
    async def recibir(self, usuario: Usuario, traslado_id: uuid.UUID) -> TrasladoDTO:
        try:
            traslado = await self.traslado_repo.buscarPorId(traslado_id)
            if traslado is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traslado no encontrado")
            self._autorizar_destino(usuario, traslado.sucursal_destino_id)
            if traslado.estado == "RECIBIDO":
                return await self._a_dto(traslado.id)  # repeticion idempotente
            if traslado.estado != "DESPACHADO":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No se puede recibir un traslado en estado {traslado.estado}",
                )
            detalles = await self.traslado_repo.detallesDeTraslado(traslado.id)
            claves = sorted(
                {(traslado.sucursal_origen_id, d.variante_id) for d in detalles}
                | {(traslado.sucursal_destino_id, d.variante_id) for d in detalles},
                key=lambda c: (str(c[0]), str(c[1])),
            )
            filas = await self.inventario_repo.bloquearFilas(claves)
            reserva = await self.reserva_repo.buscarPorId(traslado.reserva_id) if traslado.reserva_id else None
            reserva_viva = reserva is not None and reserva.estado in ESTADOS_NO_TERMINALES_RESERVA
            for d in detalles:
                origen = filas.get((traslado.sucursal_origen_id, d.variante_id))
                if origen is None or origen.en_transito < d.cantidad:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unidades en transito insuficientes")
                origen.en_transito -= d.cantidad
                await self.db.flush()
                linea = await self.db.get(DetalleReserva, d.detalle_reserva_id) if d.detalle_reserva_id else None
                if reserva_viva and linea is not None and linea.estado_linea == "PENDIENTE_TRASLADO":
                    destino = filas.get((traslado.sucursal_destino_id, d.variante_id))
                    if destino is None:
                        destino = InventarioSucursal(
                            variante_id=d.variante_id,
                            sucursal_id=traslado.sucursal_destino_id,
                            disponible=0, reservado=0, comprometido_traslado=0, en_transito=0,
                        )
                        self.db.add(destino)
                        await self.db.flush()
                    destino.reservado += d.cantidad
                    await self.db.flush()
                    linea.estado_linea = "RESERVADA"
                    linea.cantidad_reservada = d.cantidad
                    linea.cantidad_pendiente_traslado = 0
                    await self.db.flush()
                else:
                    destino = filas.get((traslado.sucursal_destino_id, d.variante_id))
                    if destino is None:
                        destino = InventarioSucursal(
                            variante_id=d.variante_id,
                            sucursal_id=traslado.sucursal_destino_id,
                            disponible=0, reservado=0, comprometido_traslado=0, en_transito=0,
                        )
                        self.db.add(destino)
                        await self.db.flush()
                    destino.disponible += d.cantidad
                    await self.db.flush()
                    if linea is not None and linea.estado_linea == "PENDIENTE_TRASLADO":
                        linea.estado_linea = "RECHAZADA"
                        linea.cantidad_pendiente_traslado = 0
                        await self.db.flush()
                await self.movimiento_repo.registrar(
                    MovimientoInventario(
                        variante_id=d.variante_id,
                        sucursal_origen_id=traslado.sucursal_origen_id,
                        sucursal_destino_id=traslado.sucursal_destino_id,
                        tipo="RECEPCION_TRASLADO",
                        cantidad=d.cantidad,
                        costo_unitario=Decimal("0"),
                        referencia_tipo="TRASLADO",
                        referencia_id=traslado.id,
                        linea_referencia_id=d.id,
                    )
                )
            traslado.estado = "RECIBIDO"
            traslado.fecha_recepcion = self.reloj.ahora()
            await self.db.flush()
            if reserva is not None and reserva_viva:
                await self._derivar_estado_reserva(reserva)
            salida = await self._a_dto(traslado.id)
            await self.db.commit()
            return salida
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    # ---------------- consulta ----------------
    async def obtener(self, usuario: Usuario, traslado_id: uuid.UUID) -> TrasladoDTO:
        traslado = await self.traslado_repo.buscarPorId(traslado_id)
        if traslado is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traslado no encontrado")
        self._autorizar_lectura(usuario, traslado)
        return await self._a_dto(traslado.id)

    def _autorizar_lectura(self, usuario: Usuario, traslado: Traslado) -> None:
        if es_admin(usuario):
            return
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE":
            if traslado.reserva_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")
            return  # la propiedad se verifica a nivel de reserva en el endpoint de reservas
        if rol == "ENCARGADO":
            propia = usuario.empleado.sucursal_id if usuario.empleado else None
            if propia not in (traslado.sucursal_origen_id, traslado.sucursal_destino_id):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Traslado fuera de tu sucursal")
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado")

    async def listar(
        self,
        usuario: Usuario,
        estado: Optional[str] = None,
        sucursal_origen_id=None,
        sucursal_destino_id=None,
        reserva_id=None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE":
            if reserva_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Indique reserva_id de una reserva propia")
            reserva = await self.reserva_repo.buscarPorId(reserva_id)
            if reserva is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
            if reserva.cliente_id != usuario.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo traslados de tus reservas")
        elif rol == "ENCARGADO":
            propia = usuario.empleado.sucursal_id if usuario.empleado else None
            if sucursal_origen_id is None and sucursal_destino_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Indique sucursal_origen_id o sucursal_destino_id de tu sucursal")
            if (
                (sucursal_origen_id is not None and sucursal_origen_id != propia)
                and (sucursal_destino_id is not None and sucursal_destino_id != propia)
            ) or (
                sucursal_origen_id is not None and sucursal_origen_id != propia and sucursal_destino_id is None
            ) or (
                sucursal_destino_id is not None and sucursal_destino_id != propia and sucursal_origen_id is None
            ):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo traslados de tu sucursal")
        elif not es_admin(usuario):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado")
        items, total = await self.traslado_repo.listar(
            estado=estado, sucursal_origen_id=sucursal_origen_id,
            sucursal_destino_id=sucursal_destino_id, reserva_id=reserva_id,
            limit=limit, offset=offset,
        )
        return {
            "total": total, "limit": limit, "offset": offset,
            "items": [await self._a_dto(t.id) for t in items],
        }
