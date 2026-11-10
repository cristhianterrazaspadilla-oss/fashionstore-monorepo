"""Controller ReservaService — CU08/CU10/CU24 (RF09-RF12).

Contratos:
  Presentacion confirmarReserva()/cancelarReserva()/consultarReserva()
  Controller crear()/cancelar()/obtener() (+ preparar/atender en Entrega 4,
    expirarVencidas() para el job CU24)
  Datos ReservaRepository.crear()/actualizarEstado(),
    InventarioRepository.moverDisponibleAReservado()/liberarReservado(),
    MovimientoRepository.registrar(tipo=RESERVA/LIBERACION_RESERVA)

Toda mutacion de inventario corre en una unica transaccion de servicio con
SELECT FOR UPDATE en orden determinista y revalidacion posterior.
Los repositorios hacen flush; solo el servicio confirma o revierte.
"""
import secrets
import string
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.idempotencia import hash_payload, resolver_idempotencia
from backend.app.core.permisos import es_admin, exigir_sucursal
from backend.app.core.reloj import RelojSistema, asegurar_utc, calcular_vencimiento, entrada_local_a_utc, a_hora_bolivia
from backend.app.core.modules.reservas_traslados.models import DetalleReserva, Reserva, DetalleTraslado, Traslado
from backend.app.core.modules.inventario.models import MovimientoInventario
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.reservas_traslados.repositories.traslado_repository import TrasladoRepository
from backend.app.core.modules.reservas_traslados.repositories.reserva_repository import (
    ESTADOS_NO_TERMINALES_RESERVA,
    ReservaRepository,
)
from backend.app.core.modules.reservas_traslados.services.reserva_transaccional import (
    ReservaTransaccional,
    validar_lineas_reserva,
    validar_visita_reserva,
)
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService
from backend.app.core.modules.reservas_traslados.schemas import ExpiracionResultadoDTO, ReservaCrearDTO, ReservaDTO

CODIGO_ALFABETO = string.ascii_uppercase + string.digits
ESTADOS_CANCELABLES = ("PENDIENTE_TRASLADO", "PENDIENTE", "PREPARADA")
ADVISORY_LOCK_EXPRIACION = "fashionstore_expiracion_reservas"


class ReservaService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.reserva_repo = ReservaRepository(db)
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)
        self.traslado_repo = TrasladoRepository(db)
        self.sucursal_repo = SucursalRepository(db)
        self.variante_repo = VarianteRepository(db)
        self.transaccional = ReservaTransaccional(db, self.reloj)

    # ---------------- creación (CU08 / CU18) ----------------
    def _generar_codigo(self) -> str:
        return "FS-" + "".join(secrets.choice(CODIGO_ALFABETO) for _ in range(6))

    async def _codigo_unico(self, empresa_id: Optional[uuid.UUID] = None) -> str:
        for _ in range(5):
            codigo = self._generar_codigo()
            if not await self.reserva_repo.existeCodigo(codigo, empresa_id=empresa_id):
                return codigo
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo generar un codigo de reserva unico",
        )

    async def crear(
        self, cliente: Usuario, dto: ReservaCrearDTO, clave: uuid.UUID
    ) -> Tuple[ReservaDTO, bool]:
        """Confirma una bolsa de forma atomica. Retorna (reserva, fue_creada).

        Idempotencia: misma clave + mismo payload -> original (fue_creada=False);
        misma clave + otro payload -> 409. Bajo concurrencia, el UNIQUE de
        clave_idempotencia serializa el intento logico duplicado.
        """
        carga = dto.model_dump(mode="json")
        digest = hash_payload(carga)
        if not cliente.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )
        # La sesion se comparte con get_usuario_actual (SELECT previo con
        # autobegin): no usar begin() explicito; patron commit/rollback
        # como RecepcionService.registrarLote().
        try:
            reintento = await resolver_idempotencia(self.db, Reserva, clave, digest)
            if reintento is not None:
                if cliente.empresa_id is not None and reintento.empresa_id != cliente.empresa_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Reserva no encontrada",
                    )
                self._autorizar_lectura(cliente, reintento)
                return await self._a_dto(reintento.id), False
            reserva = await self._crear_en_tx(cliente, dto, clave, digest)
            salida = await self._a_dto(reserva.id)
            await self.db.commit()
            return salida, True
        except IntegrityError as e:
            await self.db.rollback()
            mensaje = str(getattr(e, "orig", e))
            if "clave_idempotencia" in mensaje:
                existente = await self.reserva_repo.buscarPorClave(clave, empresa_id=cliente.empresa_id)
                if existente is None or (cliente.empresa_id is not None and existente.empresa_id != cliente.empresa_id):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Conflicto concurrente de idempotencia",
                    )
                if existente.hash_solicitud != digest:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency-Key ya usada con otra solicitud",
                    )
                self._autorizar_lectura(cliente, existente)
                return await self._a_dto(existente.id), False
            raise
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def _crear_en_tx(
        self, cliente: Usuario, dto: ReservaCrearDTO, clave: uuid.UUID, digest: str
    ) -> Reserva:
        if not cliente.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )
        # 1. Validaciones de dominio (400/404), sin efectos aun.
        ahora = self.reloj.ahora()
        plan_service = PlanService(self.db)
        capacidad = await plan_service.validar_capacidad(
            cliente.empresa_id, ahora, es_offline=False
        )
        if not capacidad.habilitado:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"PLAN_NO_HABILITADO: {capacidad.motivo_rechazo}",
            )

        validar_lineas_reserva(dto.lineas)
        for linea in dto.lineas:
            if linea.sucursal_origen_id is not None and linea.sucursal_origen_id == dto.sucursal_destino_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La sucursal origen del traslado debe ser distinta del destino",
                )
        await self.transaccional.validar_sucursal_destino(
            dto.sucursal_destino_id, cliente.empresa_id
        )
        variantes = await self.transaccional.validar_variantes(dto.lineas, cliente.empresa_id)
        await self.transaccional.validar_origenes(dto.lineas, cliente.empresa_id)

        # 2. Origen y vigencia del plazo (visita independiente del vencimiento).
        vence_en = ahora + timedelta(hours=24)
        fecha_visita = entrada_local_a_utc(dto.fecha_visita) if dto.fecha_visita else None
        # Se valida antes de bloquear/apartar stock: una visita invalida no
        # debe producir reserva ni movimiento de Kardex.
        validar_visita_reserva(fecha_visita, ahora, vence_en)

        # 3. Bloqueo pesimista en orden determinista (destino + origenes).
        filas = await self.transaccional.bloquear_filas(
            dto.sucursal_destino_id, dto.lineas, incluir_origenes=True
        )
        planes, faltante = self.transaccional.planificar_apartado(
            filas,
            dto.sucursal_destino_id,
            dto.lineas,
            permitir_traslado=True,
            variantes=variantes,
        )
        if faltante is not None:
            detalle = faltante
            if "local" in faltante:
                detalle = f"{faltante}: indique sucursal_origen_id o reduzca la cantidad"
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)

        # 4. Cabecera + lineas + movimientos + traslados en la misma transaccion.
        con_traslado = any(modo == "TRASLADO" for _, modo, _ in planes)
        reserva = Reserva(
            empresa_id=cliente.empresa_id,
            cliente_id=cliente.id,
            sucursal_destino_id=dto.sucursal_destino_id,
            codigo=await self._codigo_unico(cliente.empresa_id),
            estado="PENDIENTE_TRASLADO" if con_traslado else "PENDIENTE",
            revision=1,
            fecha_creacion=ahora,
            origen_plazo_en=ahora,
            vence_en=vence_en,
            fecha_visita=fecha_visita,
            observacion=dto.observacion,
            clave_idempotencia=clave,
            hash_solicitud=digest,
            operacion_sincronizacion_id=None,
        )
        await self.reserva_repo.crear(reserva)
        await self.transaccional.persistir_apartado(
            reserva=reserva,
            planes=planes,
            variantes=variantes,
            filas=filas,
            permitir_traslado=True,
            cliente_id=cliente.id,
        )
        return reserva

    # ---------------- consulta (CU08 / CU18) ----------------
    async def _a_dto(self, reserva_id: uuid.UUID) -> ReservaDTO:
        from backend.app.core.modules.reservas_traslados.schemas import DetalleReservaDTO, TrasladoResumenDTO

        reserva = await self.reserva_repo.buscarPorId(reserva_id)
        if reserva is None:  # pragma: no cover (defensivo)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
        traslados = await self.reserva_repo.trasladosDeReserva(reserva.id)
        estado = reserva.estado
        if not isinstance(estado, str):
            estado = estado.name
        def a_bolivia_opt(dt):
            return a_hora_bolivia(dt) if dt else None

        return ReservaDTO(
            id=reserva.id,
            empresa_id=reserva.empresa_id,
            cliente_id=reserva.cliente_id,
            sucursal_destino_id=reserva.sucursal_destino_id,
            codigo=reserva.codigo,
            estado=estado,
            revision=getattr(reserva, "revision", 1) or 1,
            fecha_creacion=a_hora_bolivia(reserva.fecha_creacion),
            fecha_visita=a_bolivia_opt(reserva.fecha_visita),
            origen_plazo_en=a_bolivia_opt(reserva.origen_plazo_en),
            vence_en=a_hora_bolivia(reserva.vence_en),
            operacion_sincronizacion_id=reserva.operacion_sincronizacion_id,
            observacion=reserva.observacion,
            adelanto_modalidad=reserva.adelanto_modalidad,
            adelanto_valor=(
                f"{Decimal(str(reserva.adelanto_valor)):.2f}"
                if reserva.adelanto_valor is not None
                else None
            ),
            adelanto_monto=(
                f"{Decimal(str(reserva.adelanto_monto)):.2f}"
                if reserva.adelanto_monto is not None
                else None
            ),
            preparada_en=a_bolivia_opt(reserva.preparada_en),
            atendida_en=a_bolivia_opt(reserva.atendida_en),
            preparada_por=reserva.preparada_por,
            atendida_por=reserva.atendida_por,
            detalles=[DetalleReservaDTO.model_validate(d) for d in reserva.detalles],
            traslados=[
                TrasladoResumenDTO(
                    id=t.id,
                    sucursal_origen_id=t.sucursal_origen_id,
                    sucursal_destino_id=t.sucursal_destino_id,
                    estado=t.estado if isinstance(t.estado, str) else t.estado.name,
                )
                for t in traslados
            ],
        )

    def _exigir_empresa(self, usuario: Usuario) -> None:
        """Ninguna sesion opera sin empresa, ni siquiera con rol administrador."""
        if not usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )

    def _autorizar_lectura(self, usuario: Usuario, reserva: Reserva) -> None:
        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")
        if reserva.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
        if es_admin(usuario):
            return
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE":
            if usuario.id != reserva.cliente_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado: reserva de otro cliente")
            return
        if rol in ("ENCARGADO", "CAJERO"):
            exigir_sucursal(usuario, reserva.sucursal_destino_id)
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado para consultar reservas")

    async def obtener(self, usuario: Usuario, reserva_id: uuid.UUID) -> ReservaDTO:
        self._exigir_empresa(usuario)
        reserva = await self.reserva_repo.buscarPorId(reserva_id, empresa_id=usuario.empresa_id)
        if reserva is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
        self._autorizar_lectura(usuario, reserva)
        return await self._a_dto(reserva.id)

    async def obtenerPorCodigo(self, usuario: Usuario, codigo: str) -> ReservaDTO:
        self._exigir_empresa(usuario)
        reserva = await self.reserva_repo.buscarPorCodigo(codigo, empresa_id=usuario.empresa_id)
        if reserva is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
        self._autorizar_lectura(usuario, reserva)
        return await self._a_dto(reserva.id)

    async def listar(
        self,
        usuario: Usuario,
        cliente_id=None,
        sucursal_id=None,
        estado: Optional[str] = None,
        codigo: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ):
        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE":
            if cliente_id is not None and cliente_id != usuario.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo puedes listar tus reservas")
            cliente_id = usuario.id
            if sucursal_id is not None:
                pass  # el cliente puede filtrar sus reservas por sucursal destino
        elif rol in ("ENCARGADO", "CAJERO"):
            if sucursal_id is not None:
                exigir_sucursal(usuario, sucursal_id)
            else:
                propia = usuario.empleado.sucursal_id if usuario.empleado else None
                if propia is None:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Indique sucursal_id o asigne sucursal al empleado",
                    )
                sucursal_id = propia
        elif not es_admin(usuario):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado")
        items, total = await self.reserva_repo.listar(
            cliente_id=cliente_id, sucursal_id=sucursal_id, estado=estado,
            codigo=codigo, limit=limit, offset=offset, empresa_id=usuario.empresa_id,
        )
        return {
            "total": total, "limit": limit, "offset": offset,
            "items": [await self._a_dto(r.id) for r in items],
        }

    # ---------------- cancelación / expiración ----------------
    def _puede_cancelar(self, usuario: Usuario, reserva: Reserva) -> None:
        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")
        if reserva.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
        if reserva.estado not in ESTADOS_CANCELABLES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No se puede cancelar una reserva en estado {reserva.estado}",
            )
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE":
            if usuario.id != reserva.cliente_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el propietario puede cancelar su reserva")
            return
        if rol in ("ENCARGADO", "ADMINISTRADOR"):
            if not es_admin(usuario):
                exigir_sucursal(usuario, reserva.sucursal_destino_id)
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado para cancelar reservas")

    async def cancelar(
        self,
        usuario: Usuario,
        reserva_id: uuid.UUID,
        revision: Optional[int] = None,
        clave_idempotencia: Optional[str] = None,
    ) -> ReservaDTO:
        self._exigir_empresa(usuario)
        try:
            actual = await self.reserva_repo.buscarPorId(reserva_id, empresa_id=usuario.empresa_id, bloquear=True)
            if actual is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
            if actual.estado in ("CANCELADA", "VENCIDA", "COMPLETADA"):
                self._autorizar_lectura(usuario, actual)
                return await self._a_dto(actual.id)  # repeticion idempotente
            self._puede_cancelar(usuario, actual)  # 403/409 tras revalidar estado
            if revision is not None and actual.revision != revision:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Conflicto de revision: esperada {actual.revision}, recibida {revision}",
                )
            await self._liberar_reserva(actual, "CANCELADA", None)
            actual.revision = (actual.revision or 1) + 1
            await self.db.flush()
            salida = await self._a_dto(actual.id)
            await self.db.commit()
            return salida
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def _liberar_reserva(self, reserva: Reserva, estado_final: str, responsable_id) -> None:
        """Libera el inventario segun su ubicacion y cierra la reserva.

        - Linea RESERVADA en destino: reservado -> disponible + LIBERACION_RESERVA.
        - Traslado SOLICITADO: se cancela (sin movimiento de stock).
        - Traslado APROBADO no despachado: libera comprometido en origen + CANCELADO.
        - Traslado DESPACHADO: continua; al recibirse quedara disponible (no reservado).
        - Traslado RECIBIDO: reservado en destino -> disponible + LIBERACION_RESERVA.
        """
        traslados = await self.reserva_repo.trasladosDeReserva(reserva.id, bloquear=True)
        por_detalle: Dict[uuid.UUID, list] = {}
        for t in traslados:
            for d in await self.traslado_repo.detallesDeTraslado(t.id):
                por_detalle.setdefault(d.detalle_reserva_id, []).append((t, d))

        # Bloquea destino + origenes afectados en orden determinista.
        claves = {(reserva.sucursal_destino_id, det.variante_id) for det in reserva.detalles}
        for t, d in [par for pares in por_detalle.values() for par in pares]:
            if t.estado in ("APROBADO", "DESPACHADO"):
                claves.add((t.sucursal_origen_id, d.variante_id))
        filas = await self.inventario_repo.bloquearFilas(list(claves))

        for det in reserva.detalles:
            if det.estado_linea in ("RESERVADA", "VENDIDA_PARCIAL") and det.cantidad_reservada > 0:
                fila = filas.get((reserva.sucursal_destino_id, det.variante_id))
                if fila is None or fila.reservado < det.cantidad_reservada:  # pragma: no cover
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Inconsistencia de stock reservado")
                fila.reservado -= det.cantidad_reservada
                fila.disponible += det.cantidad_reservada
                await self.db.flush()
                await self.movimiento_repo.registrar(
                    MovimientoInventario(
                        variante_id=det.variante_id,
                        sucursal_destino_id=reserva.sucursal_destino_id,
                        tipo="LIBERACION_RESERVA",
                        cantidad=det.cantidad_reservada,
                        costo_unitario=Decimal("0"),
                        referencia_tipo="RESERVA",
                        referencia_id=reserva.id,
                        linea_referencia_id=det.id,
                        observacion=f"Liberacion por {estado_final.lower()} de {reserva.codigo}",
                    )
                )
                det.cantidad_liberada += det.cantidad_reservada
                det.cantidad_reservada = 0
                det.estado_linea = "LIBERADA"
            elif det.estado_linea == "PENDIENTE_TRASLADO":
                det.estado_linea = "RECHAZADA"
            await self.db.flush()

        for t, d in [par for pares in por_detalle.values() for par in pares]:
            if t.estado == "SOLICITADO":
                t.estado = "CANCELADO"
                t.motivo_rechazo = f"Reserva {estado_final.lower()}ada"
            elif t.estado == "APROBADO":
                fila = filas.get((t.sucursal_origen_id, d.variante_id))
                if fila is None or fila.comprometido_traslado < d.cantidad:  # pragma: no cover
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Inconsistencia de stock comprometido")
                fila.comprometido_traslado -= d.cantidad
                fila.disponible += d.cantidad
                await self.db.flush()
                await self.movimiento_repo.registrar(
                    MovimientoInventario(
                        variante_id=d.variante_id,
                        sucursal_origen_id=t.sucursal_origen_id,
                        sucursal_destino_id=t.sucursal_destino_id,
                        tipo="LIBERACION_RESERVA",
                        cantidad=d.cantidad,
                        costo_unitario=Decimal("0"),
                        referencia_tipo="TRASLADO",
                        referencia_id=t.id,
                        linea_referencia_id=d.id,
                        observacion=f"Liberacion de compromiso por {estado_final.lower()} de {reserva.codigo}",
                    )
                )
                t.estado = "CANCELADO"
                t.motivo_rechazo = f"Reserva {estado_final.lower()}ada"
            # DESPACHADO continua hasta destino (queda disponible al recibirse).
            await self.db.flush()
        await self.reserva_repo.actualizarEstado(reserva, estado_final)

    # ---------------- preparación y atención CU10 (Entrega 4) ----------------
    def _autorizar_sucursal_staff(self, usuario: Usuario, reserva: Reserva) -> None:
        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")
        if reserva.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "ENCARGADO":
            exigir_sucursal(usuario, reserva.sucursal_destino_id)
            return
        if es_admin(usuario):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Encargado de la sucursal o Administrador")

    async def preparar(self, usuario: Usuario, reserva_id: uuid.UUID) -> ReservaDTO:
        """PENDIENTE -> PREPARADA. Sin traslados pendientes ni vencimiento."""
        self._exigir_empresa(usuario)
        try:
            reserva = await self.reserva_repo.buscarPorId(reserva_id, empresa_id=usuario.empresa_id, bloquear=True)
            if reserva is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
            self._autorizar_sucursal_staff(usuario, reserva)
            if reserva.estado == "PREPARADA":
                return await self._a_dto(reserva.id)  # repeticion idempotente
            if reserva.estado != "PENDIENTE":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Solo reservas PENDIENTE pueden prepararse (estado {reserva.estado})",
                )
            if reserva.vence_en is not None and reserva.vence_en <= self.reloj.ahora():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reserva vencida")
            if any(d.estado_linea == "PENDIENTE_TRASLADO" for d in reserva.detalles):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No se puede preparar con traslados pendientes",
                )
            reserva.estado = "PREPARADA"
            reserva.preparada_en = self.reloj.ahora()
            reserva.preparada_por = usuario.id
            await self.db.flush()
            salida = await self._a_dto(reserva.id)
            await self.db.commit()
            return salida
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def atender(self, usuario: Usuario, reserva_id: uuid.UUID) -> ReservaDTO:
        """PREPARADA -> ATENDIDA (cliente en vestidor)."""
        self._exigir_empresa(usuario)
        try:
            reserva = await self.reserva_repo.buscarPorId(reserva_id, empresa_id=usuario.empresa_id, bloquear=True)
            if reserva is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reserva no encontrada")
            self._autorizar_sucursal_staff(usuario, reserva)
            if reserva.estado == "ATENDIDA":
                return await self._a_dto(reserva.id)  # repeticion idempotente
            if reserva.estado != "PREPARADA":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Solo reservas PREPARADA pueden atenderse (estado {reserva.estado})",
                )
            if reserva.vence_en is not None and reserva.vence_en <= self.reloj.ahora():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reserva vencida")
            reserva.estado = "ATENDIDA"
            reserva.atendida_en = self.reloj.ahora()
            reserva.atendida_por = usuario.id
            await self.db.flush()
            salida = await self._a_dto(reserva.id)
            await self.db.commit()
            return salida
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def panelSucursal(
        self,
        usuario: Usuario,
        sucursal_id,
        estado: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ):
        """Cola paginada de la sucursal para polling (sin websocket/push)."""
        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "ENCARGADO":
            exigir_sucursal(usuario, sucursal_id)
        elif not es_admin(usuario):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Encargado o Administrador")
        items, total = await self.reserva_repo.listar(
            sucursal_id=sucursal_id, estado=estado, limit=limit, offset=offset,
            empresa_id=usuario.empresa_id,
        )
        return {
            "total": total, "limit": limit, "offset": offset,
            "items": [await self._a_dto(r.id) for r in items],
        }

    # ---------------- expiración CU24 ----------------
    async def expirarVencidas(
        self, ahora: Optional[datetime] = None, limite: int = 100, empresa_id: Optional[uuid.UUID] = None
    ) -> ExpiracionResultadoDTO:
        """Job de vencimiento: idempotente, con advisory lock y SKIP LOCKED.

        Retorna procesadas/expiradas/omitidas/errores. Si otra instancia tiene
        el lock, retorna bloqueo_activo=True sin procesar nada.
        """
        momento = asegurar_utc(ahora) if ahora is not None else self.reloj.ahora()
        resultado = ExpiracionResultadoDTO(procesadas=0)
        try:
            tomada = await self.db.execute(
                text("SELECT pg_try_advisory_lock(hashtext(:nombre))").bindparams(
                    nombre=ADVISORY_LOCK_EXPRIACION
                )
            )
            if not tomada.scalar():
                resultado.bloqueo_activo = True
                await self.db.rollback()
                return resultado
            try:
                candidatas = await self.reserva_repo.buscarVencidas(momento, limite, empresa_id=empresa_id)
                for reserva in candidatas:
                    if reserva.estado not in ESTADOS_NO_TERMINALES_RESERVA:
                        resultado.omitidas.append(str(reserva.id))
                        continue
                    try:
                        async with self.db.begin_nested():
                            actual = await self.reserva_repo.buscarPorId(reserva.id, empresa_id=reserva.empresa_id, bloquear=True)
                            if actual.estado not in ESTADOS_NO_TERMINALES_RESERVA:
                                resultado.omitidas.append(str(reserva.id))
                                continue
                            await self._liberar_reserva(actual, "VENCIDA", None)
                            resultado.expiradas.append(str(reserva.id))
                    except HTTPException as e:
                        resultado.errores.append(f"{reserva.id}: {e.detail}")
                    except Exception as e:  # pragma: no cover (defensivo)
                        resultado.errores.append(f"{reserva.id}: {type(e).__name__}")
                resultado.procesadas = len(resultado.expiradas) + len(resultado.omitidas) + len(resultado.errores)
            finally:
                await self.db.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:nombre))").bindparams(
                        nombre=ADVISORY_LOCK_EXPRIACION
                    )
                )
            await self.db.commit()
            return resultado
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise
