"""Servicio de Caja Offline y Turnos — CU06 y CU07."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select, or_, and_, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.reloj import utcnow, asegurar_utc
from backend.app.core.permisos import exigir_sucursal
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService
from backend.app.core.modules.inventario.models import (
    CupoCaja,
    InventarioSucursal,
    MovimientoInventario,
)
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.modules.catalogo.models import VarianteProducto, Producto
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.ventas_pagos.models import (
    TurnoCaja,
    Venta,
    DetalleVenta,
    Pago,
    TurnoCajaEvento,
)
from backend.app.core.modules.ventas_pagos.schemas import (
    TurnoCrearDTO,
    TurnoHabilitacionDTO,
    CupoRespuestaDTO,
    VentaOfflineCrearDTO,
    VentaOfflineResultadoDTO,
    TurnoCerrarDTO,
    TurnoCerradoDTO,
    TurnoRecuperarDTO,
)
from backend.app.core.idempotencia_ciclo3 import hash_payload, reclamar, guardar_respuesta


class CajaService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)
        self.variante_repo = VarianteRepository(db)

    def _validar_rol_caja(
        self,
        usuario: Usuario,
        permitir_cajero: bool = True,
        turno: Optional[TurnoCaja] = None,
    ) -> None:
        """Valida que el usuario tenga un rol autorizado dentro del ámbito de la empresa."""
        if not usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )
        rol_nombre = (usuario.rol.nombre if usuario.rol else "").upper()
        roles_supervisores = {"ADMINISTRADOR", "PROPIETARIO", "ENCARGADO"}
        if rol_nombre in roles_supervisores:
            if turno is not None and rol_nombre == "ENCARGADO" and turno.cajero_id != usuario.id:
                exigir_sucursal(usuario, turno.sucursal_id)
            return

        if permitir_cajero and rol_nombre == "CAJERO":
            if turno is not None and turno.cajero_id != usuario.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Acceso denegado: el cajero no corresponde al titular de este turno",
                )
            return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado: rol '{rol_nombre}' no autorizado para operaciones de caja",
        )

    async def habilitar_turno(
        self,
        dto: TurnoCrearDTO,
        usuario: Usuario,
        idempotency_key: uuid.UUID,
    ) -> TurnoHabilitacionDTO:
        self._validar_rol_caja(usuario, permitir_cajero=True)

        titular = usuario
        if dto.cajero_id and dto.cajero_id != usuario.id:
            if (usuario.rol.nombre if usuario.rol else "").upper() != "ADMINISTRADOR":
                raise HTTPException(403, detail="Solo el administrador empresarial puede asignar otro cajero")
            titular = (await self.db.execute(select(Usuario).where(
                Usuario.id == dto.cajero_id, Usuario.empresa_id == usuario.empresa_id,
                Usuario.estado == "ACTIVO"
            ).options(selectinload(Usuario.rol), selectinload(Usuario.empleado)))).scalars().first()
            if titular is None or not titular.rol or titular.rol.nombre.upper() != "CAJERO":
                raise HTTPException(403, detail="Cajero activo de la empresa requerido")
            exigir_sucursal(titular, dto.sucursal_id)
        if len({c.variante_id for c in dto.cupos}) != len(dto.cupos):
            raise HTTPException(422, detail="Cada variante debe aparecer una sola vez en la habilitación")

        # 0. Idempotencia durable (CU06)
        payload_dict = dto.model_dump(mode="json") if hasattr(dto, "model_dump") else dto.dict()
        if payload_dict.get("cajero_id") is None:
            payload_dict.pop("cajero_id", None)  # Conserva el hash de habilitaciones anteriores.
        hash_sol = hash_payload(payload_dict)
        previo = await reclamar(
            self.db,
            clave=idempotency_key,
            hash_solicitud=hash_sol,
            recurso_tipo="TURNO_CAJA",
            operacion="HABILITAR_TURNO",
            usuario_id=usuario.id,
        )
        if previo is not None and previo.respuesta:
            habilitacion = TurnoHabilitacionDTO(**previo.respuesta)
            if habilitacion.empresa_id is None or habilitacion.hora_central_en is None:
                # Una respuesta historica puede preceder a estos metadatos.
                # Recuperarlos del turno autorizado, sin inventar origen ni renovar su vigencia.
                return await self.obtener_turno(habilitacion.turno_id, usuario)
            return habilitacion

        # 1. Validar plan operativo activo y capacidad offline de la empresa
        ahora = utcnow()
        plan_service = PlanService(self.db)
        capacidad = await plan_service.validar_capacidad(
            usuario.empresa_id, ahora=ahora, es_offline=True
        )
        if not capacidad.habilitado:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"PLAN_INACTIVO: {capacidad.motivo_rechazo or 'Plan operativo no disponible o vencido'}",
            )

        # 2. Validar sucursal de la empresa
        q_suc = select(Sucursal).where(
            Sucursal.id == dto.sucursal_id,
            Sucursal.empresa_id == usuario.empresa_id,
            Sucursal.activa == True,
        )
        suc = (await self.db.execute(q_suc)).scalars().first()
        if not suc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada o inactiva")
        if (usuario.rol.nombre if usuario.rol else "").upper() in ("CAJERO", "ENCARGADO"):
            exigir_sucursal(usuario, dto.sucursal_id)

        # 3. Validar que la caja o dispositivo no tenga turno incompatible abierto
        q_disp = select(TurnoCaja).where(
            TurnoCaja.empresa_id == usuario.empresa_id,
            TurnoCaja.estado.in_(["ABIERTO", "CONCILIACION", "RECUPERACION"]),
            or_(
                TurnoCaja.dispositivo_id == dto.dispositivo_id,
                and_(TurnoCaja.caja_codigo == dto.caja_id, TurnoCaja.sucursal_id == dto.sucursal_id),
            ),
        )
        turno_existente = (await self.db.execute(q_disp)).scalars().first()
        if turno_existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El dispositivo o caja ya cuenta con un turno activo o pendiente de conciliación",
            )

        # 4. Bloqueo determinista de inventario en sucursal con SELECT ... FOR UPDATE
        claves = [(dto.sucursal_id, c.variante_id) for c in dto.cupos]
        filas = await self.inventario_repo.bloquearFilas(claves)

        # 5. Validar disponibilidad suficiente (todo o nada, sin asignación parcial)
        for c in dto.cupos:
            inv = filas.get((dto.sucursal_id, c.variante_id))
            if inv is None or inv.disponible < c.cantidad:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"CUPO_INSUFICIENTE: Stock libre insuficiente para la variante {c.variante_id}",
                )

        # 6. Crear turno de 8 horas exactas de vigencia
        vence = ahora + timedelta(hours=8)
        turno_id = uuid.uuid4()
        cupos_json = json.dumps(
            [{"v": str(c.variante_id), "c": c.cantidad} for c in sorted(dto.cupos, key=lambda x: str(x.variante_id))],
            sort_keys=True,
        )
        cupos_hash = hashlib.sha256(cupos_json.encode("utf-8")).hexdigest()

        version_precios = f"precios-{suc.empresa_id}-{ahora.strftime('%Y%m%d%H%M')}"

        nuevo_turno = TurnoCaja(
            id=turno_id,
            empresa_id=usuario.empresa_id,
            sucursal_id=dto.sucursal_id,
            cajero_id=titular.id,
            dispositivo_id=dto.dispositivo_id,
            caja_codigo=dto.caja_id,
            estado="ABIERTO",
            inicio_en=ahora,
            vence_en=vence,
            version_precios=version_precios,
            cupos_hash=cupos_hash,
            revision=1,
            creado_en=ahora,
        )
        self.db.add(nuevo_turno)
        await self.db.flush()

        # 7. Asignar cupos exclusivos deduciendo de disponible y sumando a comprometido_caja
        cupos_respuesta = []
        snapshot_productos = []
        for c in dto.cupos:
            inv = filas[(dto.sucursal_id, c.variante_id)]
            inv.disponible -= c.cantidad
            inv.comprometido_caja += c.cantidad

            var_q = (
                select(VarianteProducto, Producto)
                .join(Producto, Producto.id == VarianteProducto.producto_id)
                .options(selectinload(VarianteProducto.talla), selectinload(VarianteProducto.color))
                .where(VarianteProducto.id == c.variante_id,
                       VarianteProducto.empresa_id == usuario.empresa_id,
                       Producto.empresa_id == usuario.empresa_id)
            )
            var_res = (await self.db.execute(var_q)).first()
            if not var_res:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variante no encontrada")
            var, prod = var_res

            precio_aut = var.precio or Decimal("0.00")
            costo_snapshot = Decimal(str(var.costo_promedio or 0))
            cupo_registro = CupoCaja(
                id=uuid.uuid4(),
                empresa_id=usuario.empresa_id,
                turno_id=turno_id,
                variante_id=c.variante_id,
                sucursal_id=dto.sucursal_id,
                otorgado=c.cantidad,
                consumido=0,
                liberado=0,
                mermado=0,
                costo_unitario_snapshot=costo_snapshot,
                precio_autorizado_bob=precio_aut,
                version_precios=version_precios,
                creado_en=ahora,
            )
            self.db.add(cupo_registro)
            await self.db.flush()

            # El cupo cambia libre -> comprometido_caja sin retirar físicamente la prenda.
            # El movimiento queda en Kardex como transición de disponibilidad, con delta físico cero.
            await self.movimiento_repo.registrarUnico(
                MovimientoInventario(
                    variante_id=c.variante_id,
                    sucursal_origen_id=dto.sucursal_id,
                    sucursal_destino_id=dto.sucursal_id,
                    responsable_id=usuario.id,
                    tipo="COMPROMISO_CAJA",
                    cantidad=c.cantidad,
                    costo_unitario=cupo_registro.costo_unitario_snapshot,
                    referencia_tipo="TURNO_CAJA",
                    referencia_id=turno_id,
                    linea_referencia_id=cupo_registro.id,
                    clave_idempotencia=uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"caja:{turno_id}:compromiso:{c.variante_id}",
                    ),
                    fecha_hora=ahora,
                    observacion=f"Cupo exclusivo asignado a la caja {dto.caja_id}",
                )
            )

            cupos_respuesta.append(
                CupoRespuestaDTO(
                    variante_id=c.variante_id,
                    sku=var.sku,
                    producto_nombre=prod.nombre,
                    talla=var.talla.nombre if var.talla and var.talla.empresa_id == var.empresa_id else None,
                    color=var.color.nombre if var.color and var.color.empresa_id == var.empresa_id else None,
                    otorgado=c.cantidad,
                    consumido=0,
                    liberado=0,
                    mermado=0,
                    precio_autorizado_bob=precio_aut,
                )
            )
            snapshot_productos.append({
                "variante_id": str(c.variante_id),
                "sku": var.sku,
                "producto_nombre": prod.nombre,
                "precio_autorizado_bob": str(precio_aut),
            })

        await self.db.flush()

        habilitacion = TurnoHabilitacionDTO(
            empresa_id=usuario.empresa_id,
            hora_central_en=ahora,
            turno_id=turno_id,
            habilitacion_id=turno_id,
            caja_codigo=dto.caja_id,
            dispositivo_id=dto.dispositivo_id,
            sucursal_id=dto.sucursal_id,
            cajero_id=titular.id,
            estado="ABIERTO",
            inicio_en=ahora,
            vence_en=vence,
            version_precios=version_precios,
            revision=1,
            cupos=cupos_respuesta,
            snapshot={"productos": snapshot_productos, "version": version_precios},
        )

        resp_dict = habilitacion.model_dump(mode="json") if hasattr(habilitacion, "model_dump") else habilitacion.dict()
        resp_dict = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in resp_dict.items()}
        await guardar_respuesta(
            self.db,
            clave=idempotency_key,
            respuesta=resp_dict,
            recurso_id=turno_id,
            usuario_id=usuario.id,
            recurso_tipo="TURNO_CAJA",
            operacion="HABILITAR_TURNO",
        )

        await self.db.commit()
        return habilitacion

    async def registrar_venta_offline(
        self,
        turno_id: uuid.UUID,
        dto: VentaOfflineCrearDTO,
        usuario: Usuario,
    ) -> VentaOfflineResultadoDTO:
        self._validar_rol_caja(usuario, permitir_cajero=True)

        # 2. Obtener y validar turno contra la habilitación original y su snapshot
        q_turno = select(TurnoCaja).where(
            TurnoCaja.id == turno_id,
            TurnoCaja.empresa_id == usuario.empresa_id,
        ).with_for_update()
        turno = (await self.db.execute(q_turno)).scalars().first()
        if not turno:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno de caja no encontrado")

        # Validar cajero/actor (el cajero que sincroniza debe ser el cajero del turno o un supervisor empresarial)
        self._validar_rol_caja(usuario, permitir_cajero=True, turno=turno)
        rol_nombre = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol_nombre == "CAJERO" and turno.cajero_id != usuario.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado: el cajero no corresponde al turno habilitado",
            )

        # La serializacion por turno antecede a la recuperacion idempotente.
        # Nunca devolver una operacion de otro turno/actor ni aceptar UUID con otro cuerpo.
        huella = hash_payload({"turno_id": str(turno_id), "venta": dto.model_dump(mode="json")})
        # 1. Idempotencia estricta por operacion_id durable
        q_existente = select(Venta).where(
            Venta.empresa_id == usuario.empresa_id,
            Venta.id == dto.operacion_id,
        )
        venta_existente = (await self.db.execute(q_existente)).scalars().first()
        if venta_existente:
            if venta_existente.turno_caja_id != turno_id or venta_existente.cajero_id != turno.cajero_id:
                raise HTTPException(status_code=409, detail="OPERACION_MODIFICADA: origen incompatible")
            if venta_existente.hash_solicitud != huella:
                raise HTTPException(status_code=409, detail="OPERACION_MODIFICADA: contenido distinto o legado que requiere conciliacion")
            # Reintento idempotente exacto: retornar resultado durable sin duplicar cobro ni kardex
            q_cupos_ex = select(CupoCaja).where(CupoCaja.turno_id == turno_id, CupoCaja.empresa_id == usuario.empresa_id)
            cupos_ex = (await self.db.execute(q_cupos_ex)).scalars().all()
            cupos_restantes_ex = [
                {
                    "variante_id": str(c.variante_id),
                    "otorgado": c.otorgado,
                    "consumido": c.consumido,
                    "disponible_cupo": c.otorgado - c.consumido - c.liberado - c.mermado,
                }
                for c in cupos_ex
            ]
            return VentaOfflineResultadoDTO(
                resultado="REGISTRADA_CENTRAL",
                operacion_id=dto.operacion_id,
                venta_id=venta_existente.id,
                numero=venta_existente.numero,
                total_bob=venta_existente.total,
                comprobante_id=venta_existente.id,
                recibida_central_en=venta_existente.recibida_central_en or utcnow(),
                cupos_restantes=cupos_restantes_ex,
            )

        # Validar estado del turno (admite ABIERTO, CONCILIACION, RECUPERACION o CERRADO con cupos retenidos)
        if turno.estado not in ("ABIERTO", "CONCILIACION", "RECUPERACION", "CERRADO"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El turno está en estado '{turno.estado}', no admite sincronización de ventas offline",
            )

        # Validar vigencia de instantes locales (inicio_en <= fecha <= vence_en)
        vendida_utc = asegurar_utc(dto.vendida_local_en)
        entregada_utc = asegurar_utc(dto.entregada_local_en)
        inicio_utc = asegurar_utc(turno.inicio_en)
        vence_utc = asegurar_utc(turno.vence_en)

        if vendida_utc < inicio_utc or vendida_utc >= vence_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de cobro local ('vendida_local_en') está fuera del período autorizado del turno",
            )
        if entregada_utc < inicio_utc or entregada_utc >= vence_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de entrega local ('entregada_local_en') está fuera del período autorizado del turno",
            )

        # Validar versión de precios congelada en la habilitación
        if dto.version_precios != turno.version_precios:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Versión de precios no coincide con el turno: esperada '{turno.version_precios}', recibida '{dto.version_precios}'",
            )

        # 3. Validar líneas, recalcular importes con Decimal en el servidor y bloquear cupos
        if len({l.variante_id for l in dto.lineas}) != len(dto.lineas):
            raise HTTPException(status_code=400, detail="Variante duplicada en venta de caja")
        if dto.cliente_id is not None:
            cliente = (await self.db.execute(select(Usuario.id).where(
                Usuario.id == dto.cliente_id, Usuario.empresa_id == usuario.empresa_id
            ))).scalar()
            if cliente is None:
                raise HTTPException(status_code=404, detail="Cliente no encontrado en la empresa")
        ahora = utcnow()
        total_recalculado = Decimal("0.00")
        cupos_map = {}

        for linea in dto.lineas:
            q_cupo = (
                select(CupoCaja)
                .where(
                    CupoCaja.turno_id == turno_id,
                    CupoCaja.variante_id == linea.variante_id,
                    CupoCaja.empresa_id == usuario.empresa_id,
                )
                .with_for_update()
            )
            cupo = (await self.db.execute(q_cupo)).scalars().first()
            if not cupo:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"La variante {linea.variante_id} no tiene cupo asignado en este turno",
                )

            # Validar precio congelado por línea según cupo/habilitación original
            precio_autorizado = Decimal(str(cupo.precio_autorizado_bob))
            precio_enviado = Decimal(str(linea.precio_autorizado_bob))
            if precio_enviado != precio_autorizado:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Precio adulterado en variante {linea.variante_id}: esperado {precio_autorizado}, recibido {precio_enviado}",
                )

            disponible_cupo = cupo.otorgado - cupo.consumido - cupo.liberado - cupo.mermado
            if linea.cantidad > disponible_cupo:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"CUPO_LOCAL_EXCEDIDO: Cupo insuficiente en caja para {linea.variante_id}",
                )

            subtotal_linea = precio_autorizado * Decimal(str(linea.cantidad))
            total_recalculado += subtotal_linea
            cupos_map[linea.variante_id] = cupo

        # Validar que total_bob coincida exactamente con la suma recalculada
        total_dto = Decimal(str(dto.total_bob))
        if total_dto != total_recalculado:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Total adulterado: recalculado exacto {total_recalculado}, recibido {total_dto}",
            )

        # Validar que efectivo_recibido_bob >= total_bob y cambio_entregado_bob == efectivo_recibido_bob - total_bob
        efectivo_recibido = Decimal(str(dto.efectivo_recibido_bob))
        cambio_entregado = Decimal(str(dto.cambio_entregado_bob))
        if efectivo_recibido < total_recalculado:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Efectivo recibido ({efectivo_recibido}) menor al total a pagar ({total_recalculado})",
            )
        cambio_esperado = efectivo_recibido - total_recalculado
        if cambio_entregado != cambio_esperado:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cambio entregado inválido: esperado {cambio_esperado}, recibido {cambio_entregado}",
            )

        # 4. Descontar cupo local y actualizar inventario comprometido_caja
        claves = sorted([(turno.sucursal_id, l.variante_id) for l in dto.lineas], key=lambda c: str(c[1]))
        inventario = await self.inventario_repo.bloquearFilas(claves)
        for linea in dto.lineas:
            inv = inventario.get((turno.sucursal_id, linea.variante_id))
            if inv is None or inv.comprometido_caja < linea.cantidad:
                raise HTTPException(status_code=409, detail="CONCILIACION_REQUERIDA: inventario de cupo inconsistente")
        cupos_restantes = []
        for linea in dto.lineas:
            cupo = cupos_map[linea.variante_id]
            cupo.consumido += linea.cantidad

            inv = inventario[(turno.sucursal_id, linea.variante_id)]
            inv.comprometido_caja -= linea.cantidad

            cupos_restantes.append({
                "variante_id": str(linea.variante_id),
                "otorgado": cupo.otorgado,
                "consumido": cupo.consumido,
                "disponible_cupo": cupo.otorgado - cupo.consumido - cupo.liberado - cupo.mermado,
            })

        # 5. Persistir exactamente una Venta, DetalleVenta, MovimientoInventario y Pago
        numero_venta = f"VNT-OFF-{uuid.uuid4().hex[:6].upper()}"
        nueva_venta = Venta(
            id=dto.operacion_id,
            empresa_id=usuario.empresa_id,
            numero=numero_venta,
            cliente_id=dto.cliente_id,
            sucursal_id=turno.sucursal_id,
            cajero_id=turno.cajero_id,
            canal="PRESENCIAL",
            estado="PAGADA",
            subtotal=total_recalculado,
            descuento=Decimal("0.00"),
            costo_entrega=Decimal("0.00"),
            total=total_recalculado,
            adelanto_descontado=Decimal("0.00"),
            turno_caja_id=turno_id,
            hash_solicitud=huella,
            vendida_local_en=vendida_utc,
            recibida_central_en=ahora,
            entregada_en=entregada_utc,
        )
        self.db.add(nueva_venta)
        await self.db.flush()

        for linea in dto.lineas:
            cupo = cupos_map[linea.variante_id]
            var_item = await self.variante_repo.buscarPorId(linea.variante_id)
            costo = (var_item.costo_promedio or Decimal("0.00")) if var_item else Decimal("0.00")
            precio_unit = Decimal(str(cupo.precio_autorizado_bob))

            det = DetalleVenta(
                id=uuid.uuid4(),
                venta_id=nueva_venta.id,
                variante_id=linea.variante_id,
                cantidad=linea.cantidad,
                precio_unitario=precio_unit,
                descuento=Decimal("0.00"),
                costo_promedio=costo,
            )
            self.db.add(det)

            await self.movimiento_repo.registrar(
                MovimientoInventario(
                    variante_id=linea.variante_id,
                    sucursal_origen_id=turno.sucursal_id,
                    responsable_id=turno.cajero_id,
                    tipo="VENTA_PRESENCIAL",
                    cantidad=linea.cantidad,
                    costo_unitario=costo,
                    referencia_tipo="VENTA",
                    referencia_id=nueva_venta.id,
                    linea_referencia_id=det.id,
                    clave_idempotencia=uuid.uuid4(),
                    fecha_hora=ahora,
                    observacion=f"Venta contado sincronizada desde caja {turno.caja_codigo}",
                )
            )

        nuevo_pago = Pago(
            id=uuid.uuid4(),
            empresa_id=usuario.empresa_id,
            contexto="VENTA",
            venta_id=nueva_venta.id,
            metodo="EFECTIVO",
            tipo_pago="TOTAL",
            monto=total_recalculado,
            efectivo_recibido_bob=efectivo_recibido,
            cambio_entregado_bob=cambio_entregado,
            no_reembolsable=False,
            estado="APROBADO",
            referencia_externa=f"CAJA-{turno.caja_codigo}-{nueva_venta.id}",
            pagado_en=vendida_utc,
            clave_idempotencia=dto.operacion_id,
        )
        self.db.add(nuevo_pago)
        await self.db.commit()

        return VentaOfflineResultadoDTO(
            resultado="REGISTRADA_CENTRAL",
            operacion_id=dto.operacion_id,
            venta_id=nueva_venta.id,
            numero=numero_venta,
            total_bob=total_recalculado,
            comprobante_id=nueva_venta.id,
            recibida_central_en=ahora,
            cupos_restantes=cupos_restantes,
        )

    async def cerrar_turno(
        self,
        turno_id: uuid.UUID,
        dto: TurnoCerrarDTO,
        usuario: Usuario,
    ) -> TurnoCerradoDTO:
        q_turno = (
            select(TurnoCaja)
            .where(TurnoCaja.id == turno_id, TurnoCaja.empresa_id == usuario.empresa_id)
            .with_for_update()
        )
        turno = (await self.db.execute(q_turno)).scalars().first()
        if not turno:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno no encontrado")

        self._validar_rol_caja(usuario, permitir_cajero=True, turno=turno)
        rol_nombre = (usuario.rol.nombre if usuario.rol else "").upper()
        es_supervisor = rol_nombre in {"ADMINISTRADOR", "PROPIETARIO", "ENCARGADO"}

        if turno.revision != dto.revision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Conflicto de revisin: esperada {turno.revision}, recibida {dto.revision}",
            )

        estado_anterior = turno.estado
        if turno.estado == "CERRADO":
            if not dto.supervision_forzada or not es_supervisor:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El turno ya se encuentra cerrado")
        elif turno.estado not in ("ABIERTO", "CONCILIACION", "RECUPERACION"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El turno est en estado '{turno.estado}' y no admite cierre",
            )

        if dto.supervision_forzada:
            if not es_supervisor:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo un supervisor puede realizar la conciliacin fsica de caja",
                )
            if not dto.motivo_supervision or len(dto.motivo_supervision.strip()) < 10:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El motivo de supervisin debe tener al menos 10 caracteres",
                )

        q_cupos = (
            select(CupoCaja)
            .where(CupoCaja.turno_id == turno_id, CupoCaja.empresa_id == usuario.empresa_id)
            .order_by(CupoCaja.variante_id)
            .with_for_update()
        )
        cupos = (await self.db.execute(q_cupos)).scalars().all()
        remanentes = {
            c.variante_id: c.otorgado - c.consumido - c.liberado - c.mermado
            for c in cupos
        }
        if any(restante < 0 for restante in remanentes.values()):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El balance de cupos del turno es invlido")
        if estado_anterior == "CERRADO" and not any(remanentes.values()):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El turno cerrado no tiene cupos retenidos para resolver")

        arqueo_declarado = dto.arqueo_declarado_bob
        if arqueo_declarado is None:
            arqueo_declarado = dto.arqueo_efectivo_bob

        # La va ordinaria solo puede cerrar cuando todas las operaciones y cupos
        # estn conciliados. Los remanentes requieren conteo y disposicin supervisada.
        hay_discrepancia = False
        q_conteo = select(func.count(Venta.id)).where(
            Venta.turno_caja_id == turno_id,
            Venta.empresa_id == usuario.empresa_id,
        )
        conteo_central = int((await self.db.execute(q_conteo)).scalar() or 0)

        operaciones_pendientes_no_sincronizadas = []
        if dto.operaciones_pendientes:
            q_sinc = select(Venta.id).where(
                Venta.empresa_id == usuario.empresa_id,
                Venta.turno_caja_id == turno_id,
                Venta.id.in_(dto.operaciones_pendientes),
            )
            sincronizadas = set((await self.db.execute(q_sinc)).scalars().all())
            operaciones_pendientes_no_sincronizadas = [
                op_id for op_id in dto.operaciones_pendientes if op_id not in sincronizadas
            ]

        # Ningún cierre (tampoco el supervisado) puede finalizar mientras el
        # dispositivo declare ventas pendientes que aún no existen en central.
        # No se libera ningún cupo porque la venta tardía podría consumirlo.
        if dto.supervision_forzada and operaciones_pendientes_no_sincronizadas:
            ahora = utcnow()
            turno.estado = "CONCILIACION"
            turno.cerrado_en = None
            turno.revision += 1
            evento_id = uuid.uuid4()
            self.db.add(
                TurnoCajaEvento(
                    id=evento_id,
                    turno_id=turno.id,
                    empresa_id=turno.empresa_id,
                    actor_id=usuario.id,
                    revision=turno.revision,
                    tipo="CIERRE_EN_CONCILIACION",
                    datos={
                        "motivo": "El cierre supervisado espera ventas offline declaradas por el dispositivo",
                        "operaciones_pendientes_no_sincronizadas": [
                            str(x) for x in operaciones_pendientes_no_sincronizadas
                        ],
                        "supervision_forzada_solicitada": True,
                        "motivo_supervision": dto.motivo_supervision,
                        "remanentes": {str(k): v for k, v in remanentes.items()},
                    },
                    creado_en=ahora,
                )
            )
            await self.db.commit()
            cupos_retenidos = [
                {
                    "variante_id": str(c.variante_id),
                    "otorgado": c.otorgado,
                    "consumido": c.consumido,
                    "mermado": c.mermado,
                    "retenido": remanentes[c.variante_id],
                }
                for c in cupos
                if remanentes[c.variante_id] > 0
            ]
            return TurnoCerradoDTO(
                turno_id=turno.id,
                estado="CONCILIACION",
                cerrado_en=None,
                revision=turno.revision,
                cupos_devueltos=[],
                cupos_retenidos=cupos_retenidos,
                evento_id=evento_id,
            )

        if not dto.supervision_forzada:
            if operaciones_pendientes_no_sincronizadas:
                hay_discrepancia = True

            if dto.ultima_secuencia_local is None and dto.total_operaciones_locales is None:
                hay_discrepancia = True
            if dto.ultima_secuencia_local is not None and conteo_central != dto.ultima_secuencia_local:
                hay_discrepancia = True
            if dto.total_operaciones_locales is not None and conteo_central != dto.total_operaciones_locales:
                hay_discrepancia = True
            if any(remanentes.values()):
                hay_discrepancia = True

            if arqueo_declarado is not None:
                q_efectivo = (
                    select(func.coalesce(func.sum(Pago.monto), Decimal("0.00")))
                    .join(Venta, Venta.id == Pago.venta_id)
                    .where(
                        Venta.turno_caja_id == turno_id,
                        Venta.empresa_id == usuario.empresa_id,
                        Pago.metodo == "EFECTIVO",
                        Pago.estado == "APROBADO",
                    )
                )
                total_efectivo = Decimal(str((await self.db.execute(q_efectivo)).scalar() or 0))
                if arqueo_declarado != total_efectivo:
                    hay_discrepancia = True

        # Validar el acta y todos los conteos antes de tocar existencias.
        conteo_por_variante = {}
        resolucion_por_variante = {}
        if dto.supervision_forzada:
            evidencia = dto.evidencia_cierre or {}
            referencia_acta = str(evidencia.get("referencia_acta", "")).strip()
            entradas = evidencia.get("conteo_fisico_por_variante")
            if len(referencia_acta) < 3 or not isinstance(entradas, list):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La conciliacin supervisada requiere referencia de acta y conteo fsico por variante",
                )

            ids_cupos = {c.variante_id for c in cupos}
            for item in entradas:
                if not isinstance(item, dict):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Entrada de conteo invlida")
                try:
                    variante_id = uuid.UUID(str(item.get("variante_id")))
                except (ValueError, TypeError, AttributeError):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variante invlida en conteo fsico")
                cantidad = item.get("cantidad_encontrada")
                if type(cantidad) is not int or cantidad < 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cantidad_encontrada debe ser un entero no negativo")
                if variante_id not in ids_cupos or variante_id in conteo_por_variante:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El conteo contiene variantes ajenas o duplicadas")
                if cantidad > remanentes[variante_id]:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El conteo fsico excede el cupo remanente")
                conteo_por_variante[variante_id] = cantidad

            if set(conteo_por_variante) != ids_cupos:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El conteo debe incluir exactamente todas las variantes del turno")

            ajustes = dto.ajustes_inventario or {}
            resoluciones = ajustes.get("resoluciones_por_variante", [])
            if not isinstance(resoluciones, list):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="resoluciones_por_variante debe ser una lista")
            for item in resoluciones:
                if not isinstance(item, dict):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resolucin de inventario invlida")
                try:
                    variante_id = uuid.UUID(str(item.get("variante_id")))
                except (ValueError, TypeError, AttributeError):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variante invlida en resolucin de faltante")
                if variante_id not in ids_cupos or variante_id in resolucion_por_variante:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La resolucin contiene variantes ajenas o duplicadas")
                resolucion = item.get("resolucion")
                motivo = str(item.get("motivo", "")).strip()
                if resolucion not in ("PENDIENTE_SINCRONIZACION", "MERMA"):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resolucin debe ser PENDIENTE_SINCRONIZACION o MERMA")
                if resolucion == "MERMA" and len(motivo) < 10:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La merma requiere un motivo de al menos 10 caracteres")
                resolucion_por_variante[variante_id] = {"resolucion": resolucion, "motivo": motivo}

            for variante_id, remanente in remanentes.items():
                faltante = remanente - conteo_por_variante[variante_id]
                if faltante > 0 and variante_id not in resolucion_por_variante:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"El faltante de la variante {variante_id} requiere disposicin explcita",
                    )
                if faltante == 0 and variante_id in resolucion_por_variante:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"La variante {variante_id} no tiene faltante que resolver",
                    )

            if arqueo_declarado is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El arqueo de efectivo es obligatorio en cierre supervisado")

        # Un cierre ordinario con pendientes o remanente solo congela inventario.
        if hay_discrepancia:
            ahora = utcnow()
            turno.estado = "CONCILIACION"
            turno.cerrado_en = None
            turno.revision += 1
            self.db.add(
                TurnoCajaEvento(
                    id=uuid.uuid4(),
                    turno_id=turno.id,
                    empresa_id=turno.empresa_id,
                    actor_id=usuario.id,
                    revision=turno.revision,
                    tipo="CIERRE_EN_CONCILIACION",
                    datos={
                        "motivo": "Hay ventas pendientes, faltan datos de conciliacin o existen cupos sin conteo fsico",
                        "operaciones_pendientes": [str(x) for x in (dto.operaciones_pendientes or [])],
                        "ultima_secuencia_local": dto.ultima_secuencia_local,
                        "total_operaciones_locales": dto.total_operaciones_locales,
                        "conteo_central": conteo_central,
                        "remanentes": {str(k): v for k, v in remanentes.items()},
                    },
                    creado_en=ahora,
                )
            )
            await self.db.commit()
            cupos_retenidos = [
                {"variante_id": str(c.variante_id), "otorgado": c.otorgado, "consumido": c.consumido,
                 "mermado": c.mermado, "retenido": remanentes[c.variante_id]}
                for c in cupos if remanentes[c.variante_id] > 0
            ]
            return TurnoCerradoDTO(
                turno_id=turno.id,
                estado="CONCILIACION",
                cerrado_en=turno.cerrado_en,
                revision=turno.revision,
                cupos_devueltos=[],
                cupos_retenidos=cupos_retenidos,
            )

        ahora = utcnow()
        evento_id = uuid.uuid4()
        devueltos = []
        retenidos = []
        mermas = []
        resoluciones_auditadas = []
        if dto.supervision_forzada:
            for c in cupos:
                remanente = remanentes[c.variante_id]
                encontrado = conteo_por_variante[c.variante_id]
                faltante = remanente - encontrado
                if encontrado > 0:
                    inv = await self.inventario_repo.buscarPorVarianteYSucursal(c.variante_id, turno.sucursal_id)
                    if inv is None or inv.comprometido_caja < encontrado:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Compromiso de caja inconsistente con el inventario")
                    inv.comprometido_caja -= encontrado
                    inv.disponible += encontrado
                    c.liberado += encontrado
                    await self.movimiento_repo.registrarUnico(
                        MovimientoInventario(
                            variante_id=c.variante_id,
                            sucursal_origen_id=turno.sucursal_id,
                            sucursal_destino_id=turno.sucursal_id,
                            responsable_id=usuario.id,
                            tipo="LIBERACION_CUPO_CAJA",
                            cantidad=encontrado,
                            costo_unitario=c.costo_unitario_snapshot,
                            referencia_tipo="TURNO_CAJA_EVENTO",
                            referencia_id=evento_id,
                            linea_referencia_id=c.id,
                            clave_idempotencia=uuid.uuid5(uuid.NAMESPACE_URL, f"caja:{evento_id}:{c.id}:liberacion"),
                            fecha_hora=ahora,
                            observacion=f"Devolucin supervisada de cupo para caja {turno.caja_codigo}",
                        )
                    )

                if faltante > 0:
                    resolucion = resolucion_por_variante[c.variante_id]
                    resoluciones_auditadas.append({
                        "variante_id": str(c.variante_id),
                        "resolucion": resolucion["resolucion"],
                        "motivo": resolucion["motivo"],
                    })
                    if resolucion["resolucion"] == "PENDIENTE_SINCRONIZACION":
                        retenidos.append({
                            "variante_id": str(c.variante_id), "otorgado": c.otorgado,
                            "consumido": c.consumido, "mermado": c.mermado, "retenido": faltante,
                        })
                    else:
                        inv = await self.inventario_repo.buscarPorVarianteYSucursal(c.variante_id, turno.sucursal_id)
                        if inv is None or inv.comprometido_caja < faltante:
                            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Compromiso de caja inconsistente con el inventario")
                        inv.comprometido_caja -= faltante
                        c.mermado += faltante
                        motivo = resolucion["motivo"]
                        await self.movimiento_repo.registrarUnico(
                            MovimientoInventario(
                                variante_id=c.variante_id,
                                sucursal_origen_id=turno.sucursal_id,
                                responsable_id=usuario.id,
                                tipo="MERMA",
                                cantidad=faltante,
                                costo_unitario=c.costo_unitario_snapshot,
                                referencia_tipo="TURNO_CAJA_EVENTO",
                                referencia_id=evento_id,
                                linea_referencia_id=c.id,
                                clave_idempotencia=uuid.uuid5(uuid.NAMESPACE_URL, f"caja:{evento_id}:{c.id}:merma"),
                                fecha_hora=ahora,
                                observacion=f"Merma supervisada de caja {turno.caja_codigo}: {motivo}",
                            )
                        )
                        mermas.append({
                            "variante_id": str(c.variante_id), "cantidad": faltante, "motivo": motivo,
                        })
                cantidad_mermada = (
                    faltante
                    if faltante > 0
                    and resolucion_por_variante[c.variante_id]["resolucion"] == "MERMA"
                    else 0
                )
                if encontrado > 0 or cantidad_mermada > 0:
                    devueltos.append({
                        "variante_id": str(c.variante_id),
                        "otorgado": c.otorgado,
                        "consumido": c.consumido,
                        "devuelto": encontrado,
                        "mermado": cantidad_mermada,
                    })

        total_retenido = sum(x["retenido"] for x in retenidos)
        turno.estado = "CONCILIACION" if total_retenido > 0 else "CERRADO"
        turno.cerrado_en = ahora if total_retenido == 0 else None
        turno.cerrado_por_id = usuario.id
        turno.motivo_supervision = dto.motivo_supervision if dto.supervision_forzada else None
        turno.supervision_forzada = bool(dto.supervision_forzada)
        turno.arqueo_declarado_bob = arqueo_declarado
        turno.evidencia_cierre = dto.evidencia_cierre if dto.supervision_forzada else None
        turno.ajustes_inventario = {
            "resoluciones_por_variante": resoluciones_auditadas,
            "mermas": mermas,
        } if dto.supervision_forzada else None
        turno.revision += 1
        self.db.add(
            TurnoCajaEvento(
                id=evento_id,
                turno_id=turno.id,
                empresa_id=turno.empresa_id,
                actor_id=usuario.id,
                revision=turno.revision,
                tipo="CONCILIACION_SUPERVISADA" if dto.supervision_forzada else "CIERRE_CONCILIADO",
                datos={
                    "estado_anterior": estado_anterior,
                    "estado_resultado": "CONCILIACION" if total_retenido > 0 else "CERRADO",
                    "motivo_supervision": dto.motivo_supervision,
                    "supervision_forzada": bool(dto.supervision_forzada),
                    "arqueo_declarado_bob": str(arqueo_declarado) if arqueo_declarado is not None else None,
                    "evidencia_cierre": dto.evidencia_cierre if dto.supervision_forzada else None,
                    "ajustes_inventario": {
                        "resoluciones_por_variante": resoluciones_auditadas,
                        "mermas": mermas,
                    },
                    "cupos_devueltos": devueltos,
                    "cupos_retenidos": retenidos,
                },
                creado_en=ahora,
            )
        )
        await self.db.commit()

        return TurnoCerradoDTO(
            turno_id=turno.id,
            estado=turno.estado,
            cerrado_en=turno.cerrado_en,
            revision=turno.revision,
            cupos_devueltos=devueltos,
            cupos_retenidos=retenidos,
            cerrado_por_id=turno.cerrado_por_id,
            motivo_supervision=turno.motivo_supervision,
            supervision_forzada=turno.supervision_forzada,
            arqueo_declarado_bob=turno.arqueo_declarado_bob,
            evidencia_cierre=turno.evidencia_cierre,
            ajustes_inventario=turno.ajustes_inventario,
            evento_id=evento_id,
        )

    async def recuperar_turno(
        self,
        turno_id: uuid.UUID,
        dto: TurnoRecuperarDTO,
        usuario: Usuario,
    ) -> dict:
        self._validar_rol_caja(usuario, permitir_cajero=False)

        q_turno = (
            select(TurnoCaja)
            .where(
                TurnoCaja.id == turno_id,
                TurnoCaja.empresa_id == usuario.empresa_id,
            )
            .with_for_update()
        )
        turno = (await self.db.execute(q_turno)).scalars().first()
        if not turno:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno no encontrado")

        if turno.estado not in ("ABIERTO", "CONCILIACION"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No se puede enviar a recuperacion un turno en estado '{turno.estado}'",
            )

        if turno.revision != dto.revision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Conflicto de revisión: esperada {turno.revision}, recibida {dto.revision}",
            )

        # Marca RECUPERACION y congela cupos hasta resolución manual supervisada
        # (Caja perdida no libera stock por simple timeout)
        turno.estado = "RECUPERACION"
        turno.motivo_supervision = dto.motivo
        turno.supervision_forzada = True
        turno.cerrado_por_id = usuario.id
        if dto.evidencia:
            turno.evidencia_cierre = {"evidencia": dto.evidencia}
        turno.revision += 1
        evento = TurnoCajaEvento(
            id=uuid.uuid4(),
            turno_id=turno.id,
            empresa_id=turno.empresa_id,
            actor_id=usuario.id,
            revision=turno.revision,
            tipo="TURNO_EN_RECUPERACION",
            datos={"motivo": dto.motivo, "evidencia": dto.evidencia},
            creado_en=utcnow(),
        )
        self.db.add(evento)
        await self.db.commit()
        return {
            "turno_id": str(turno.id),
            "estado": "RECUPERACION",
            "motivo": dto.motivo,
            "revision": turno.revision,
            "evento_id": str(evento.id),
        }

    async def _serializar_turno(self, turno: TurnoCaja) -> TurnoHabilitacionDTO:
        q_cupos = (
            select(CupoCaja, VarianteProducto, Producto)
            .join(VarianteProducto, VarianteProducto.id == CupoCaja.variante_id)
            .join(Producto, Producto.id == VarianteProducto.producto_id)
            .options(selectinload(VarianteProducto.talla), selectinload(VarianteProducto.color))
            .where(CupoCaja.turno_id == turno.id, CupoCaja.empresa_id == turno.empresa_id,
                   VarianteProducto.empresa_id == turno.empresa_id, Producto.empresa_id == turno.empresa_id)
        )
        filas = (await self.db.execute(q_cupos)).all()
        cupos_resp = []
        snapshot_prods = []
        for cupo, var, prod in filas:
            cupos_resp.append(
                CupoRespuestaDTO(
                    variante_id=cupo.variante_id,
                    sku=var.sku,
                    producto_nombre=prod.nombre,
                    talla=var.talla.nombre if var.talla and var.talla.empresa_id == var.empresa_id else None,
                    color=var.color.nombre if var.color and var.color.empresa_id == var.empresa_id else None,
                    otorgado=cupo.otorgado,
                    consumido=cupo.consumido,
                    liberado=cupo.liberado,
                    mermado=cupo.mermado,
                    precio_autorizado_bob=cupo.precio_autorizado_bob,
                )
            )
            snapshot_prods.append({
                "variante_id": str(cupo.variante_id),
                "sku": var.sku,
                "producto_nombre": prod.nombre,
                "precio_autorizado_bob": str(cupo.precio_autorizado_bob),
            })
        return TurnoHabilitacionDTO(
            empresa_id=turno.empresa_id,
            hora_central_en=utcnow(),
            turno_id=turno.id,
            habilitacion_id=turno.id,
            caja_codigo=turno.caja_codigo,
            dispositivo_id=turno.dispositivo_id,
            sucursal_id=turno.sucursal_id,
            cajero_id=turno.cajero_id,
            estado=turno.estado,
            inicio_en=asegurar_utc(turno.inicio_en),
            vence_en=asegurar_utc(turno.vence_en),
            version_precios=turno.version_precios,
            revision=turno.revision,
            cupos=cupos_resp,
            snapshot={"productos": snapshot_prods, "version": turno.version_precios},
        )

    async def obtener_turno(self, turno_id: uuid.UUID, usuario: Usuario) -> TurnoHabilitacionDTO:
        self._validar_rol_caja(usuario, permitir_cajero=True)
        q = select(TurnoCaja).where(
            TurnoCaja.id == turno_id,
            TurnoCaja.empresa_id == usuario.empresa_id,
        )
        turno = (await self.db.execute(q)).scalars().first()
        if not turno:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turno de caja no encontrado")
        self._validar_rol_caja(usuario, permitir_cajero=True, turno=turno)
        return await self._serializar_turno(turno)

    async def listar_conciliacion(self, usuario: Usuario) -> List[TurnoHabilitacionDTO]:
        self._validar_rol_caja(usuario, permitir_cajero=False)
        q = select(TurnoCaja).where(TurnoCaja.empresa_id == usuario.empresa_id,
                                   TurnoCaja.estado == "CONCILIACION")
        if usuario.rol.nombre.upper() == "ENCARGADO":
            sucursal_id = usuario.empleado.sucursal_id if usuario.empleado else None
            exigir_sucursal(usuario, sucursal_id)
            q = q.where(TurnoCaja.sucursal_id == sucursal_id)
        turnos = (await self.db.execute(q.order_by(TurnoCaja.inicio_en.desc()))).scalars().all()
        return [await self._serializar_turno(t) for t in turnos]

    async def obtener_turno_activo(
        self, usuario: Usuario, dispositivo_id: Optional[uuid.UUID] = None
    ) -> Optional[TurnoHabilitacionDTO]:
        self._validar_rol_caja(usuario, permitir_cajero=True)
        conditions = [
            TurnoCaja.empresa_id == usuario.empresa_id,
            TurnoCaja.estado.in_(["ABIERTO", "CONCILIACION", "RECUPERACION"]),
        ]
        if (usuario.rol.nombre if usuario.rol else "").upper() == "CAJERO":
            conditions.append(TurnoCaja.cajero_id == usuario.id)
        if dispositivo_id:
            conditions.append(TurnoCaja.dispositivo_id == dispositivo_id)
        else:
            conditions.append(TurnoCaja.cajero_id == usuario.id)
        q = select(TurnoCaja).where(*conditions).order_by(TurnoCaja.inicio_en.desc())
        turno = (await self.db.execute(q)).scalars().first()
        if not turno:
            return None
        self._validar_rol_caja(usuario, permitir_cajero=True, turno=turno)
        return await self._serializar_turno(turno)
