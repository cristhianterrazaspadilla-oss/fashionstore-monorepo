"""Servicio SucursalService — CU15 / CU03: Gestionar sucursales, límites y tarifas."""
import json
import uuid
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.modules.identidad_empresas.models import Empresa, Usuario
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService
from backend.app.core.modules.organizacion.models import Ciudad, Sucursal
from backend.app.core.modules.organizacion.schemas import (
    SucursalCrearDTO,
    SucursalActualizarDTO,
    SucursalDTO,
    ConfigurarTarifasDeliveryDTO,
    ConfigurarAdelantoDTO,
)
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.organizacion.repositories.ciudad_repository import CiudadRepository
from backend.app.core.modules.reservas_traslados.models import Reserva, Traslado


class SucursalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.sucursal_repo = SucursalRepository(db)
        self.ciudad_repo = CiudadRepository(db)
        self.plan_service = PlanService(db)

    async def _construir_dto(self, s: Sucursal) -> SucursalDTO:
        ciudad_nombre = None
        if s.ciudad_id:
            c = await self.ciudad_repo.buscarPorId(s.ciudad_id)
            if c:
                ciudad_nombre = c.nombre

        return SucursalDTO(
            id=s.id,
            empresa_id=s.empresa_id,
            ciudad_id=s.ciudad_id,
            ciudad_nombre=ciudad_nombre,
            nombre=s.nombre,
            direccion=s.direccion,
            telefono=s.telefono,
            numero_anillo=s.numero_anillo,
            tarifa_base_delivery=s.tarifa_base_delivery,
            incremento_anillo_delivery=s.incremento_anillo_delivery,
            anillo_minimo_delivery=s.anillo_minimo_delivery,
            anillo_maximo_delivery=s.anillo_maximo_delivery,
            delivery_activo=s.delivery_activo,
            activa=s.activa,
            revision=s.revision,
            adelanto_activo=s.adelanto_activo,
            modalidad_adelanto=s.modalidad_adelanto,
            valor_adelanto=s.valor_adelanto,
        )

    async def crear(self, dto: SucursalCrearDTO, usuario: Usuario) -> SucursalDTO:
        empresa_id = usuario.empresa_id or dto.empresa_id
        if not empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="empresa_id es requerido para registrar la sucursal",
            )

        # 1. Validar que la ciudad exista
        ciudad = await self.ciudad_repo.buscarPorId(dto.ciudad_id)
        if not ciudad:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La ciudad especificada no existe",
            )

        # 2. Bloquear empresa para serializar creación y comprobación de límites
        await self.db.execute(select(Empresa.id).where(Empresa.id == empresa_id).with_for_update())

        # 3. Validar suscripción activa y límite de sucursales activas (CU02 / CU15)
        par = await self.plan_service.consultar_suscripcion_efectiva(empresa_id)
        if not par:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La empresa no cuenta con una suscripción activa para operar sucursales",
            )
        _, plan = par

        q_activas = select(func.count(Sucursal.id)).where(
            Sucursal.empresa_id == empresa_id,
            Sucursal.activa == True,
        )
        res_activas = await self.db.execute(q_activas)
        activas_actuales = res_activas.scalar() or 0

        if activas_actuales >= plan.max_sucursales_activas:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Límite de sucursales activas alcanzado para el plan '{plan.nombre}' "
                    f"(máximo {plan.max_sucursales_activas}). Actualmente cuenta con {activas_actuales} activas."
                ),
            )

        # 4. Validar unicidad de nombre en la misma ciudad y empresa
        existente = await self.sucursal_repo.buscarPorCiudadYNombre(dto.ciudad_id, dto.nombre, empresa_id)
        if existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una sucursal con el nombre '{dto.nombre.strip()}' en {ciudad.nombre} para esta empresa",
            )

        nueva_sucursal = Sucursal(
            empresa_id=empresa_id,
            ciudad_id=dto.ciudad_id,
            nombre=dto.nombre.strip(),
            direccion=dto.direccion.strip(),
            telefono=dto.telefono.strip() if dto.telefono else None,
            numero_anillo=dto.numero_anillo,
            tarifa_base_delivery=dto.tarifa_base_delivery,
            incremento_anillo_delivery=dto.incremento_anillo_delivery,
            anillo_minimo_delivery=dto.anillo_minimo_delivery,
            anillo_maximo_delivery=dto.anillo_maximo_delivery,
            delivery_activo=dto.delivery_activo,
            activa=True,
            revision=1,
        )
        await self.sucursal_repo.crear(nueva_sucursal)

        # 5. Outbox en la misma transacción (sin silenciar errores)
        await self.db.execute(
            text("""
                INSERT INTO comercial.eventos_outbox (
                    id, empresa_id, recurso_tipo, recurso_id, transicion, revision, payload, estado, intentos, creado_en
                ) VALUES (
                    :id, :empresa_id, 'SUCURSAL', :recurso_id, 'CREADA', 1, cast(:payload as jsonb), 'PENDIENTE', 0, now()
                )
            """),
            {
                "id": uuid.uuid4(),
                "empresa_id": empresa_id,
                "recurso_id": nueva_sucursal.id,
                "payload": json.dumps({
                    "sucursal_id": str(nueva_sucursal.id),
                    "nombre": nueva_sucursal.nombre,
                    "ciudad_id": str(nueva_sucursal.ciudad_id),
                }),
            },
        )

        await self.db.commit()
        await self.db.refresh(nueva_sucursal)
        return await self._construir_dto(nueva_sucursal)

    async def actualizar(self, sucursal_id: uuid.UUID, dto: SucursalActualizarDTO, usuario: Usuario) -> SucursalDTO:
        # 1. Obtener con bloqueo de fila
        q = select(Sucursal).options(selectinload(Sucursal.ciudad)).where(Sucursal.id == sucursal_id).with_for_update()
        res = await self.db.execute(q)
        sucursal = res.scalars().first()
        if not sucursal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sucursal no encontrada",
            )

        # 2. Control de ámbito multiempresa
        if usuario.empresa_id is not None and sucursal.empresa_id != usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para modificar sucursales de otra empresa",
            )

        # 3. Control optimista de concurrencia (CU15 / CU14)
        if dto.revision != sucursal.revision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Revisión obsoleta: enviada {dto.revision}, actual {sucursal.revision}",
            )

        # 4. Si se activa, verificar límite contra plan bajo bloqueo
        if dto.activa is True and not sucursal.activa:
            await self.db.execute(select(Empresa.id).where(Empresa.id == sucursal.empresa_id).with_for_update())
            par = await self.plan_service.consultar_suscripcion_efectiva(sucursal.empresa_id)
            if not par:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La empresa no cuenta con una suscripción activa",
                )
            _, plan = par
            q_activas = select(func.count(Sucursal.id)).where(
                Sucursal.empresa_id == sucursal.empresa_id,
                Sucursal.activa == True,
            )
            res_activas = await self.db.execute(q_activas)
            activas_actuales = res_activas.scalar() or 0
            if activas_actuales >= plan.max_sucursales_activas:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Límite de sucursales activas alcanzado para el plan '{plan.nombre}' "
                        f"(máximo {plan.max_sucursales_activas})."
                    ),
                )

        # 5. Si se desactiva, comprobar compromisos pendientes bloqueantes (CU15)
        if dto.activa is False and sucursal.activa:
            # a) Reservas activas pendientes o en preparación
            q_res = select(func.count(Reserva.id)).where(
                Reserva.sucursal_destino_id == sucursal_id,
                Reserva.estado.in_(["PENDIENTE", "PENDIENTE_TRASLADO", "PREPARADA"]),
            )
            res_res = await self.db.execute(q_res)
            reservas_pendientes = res_res.scalar() or 0

            # b) Turnos de caja abiertos
            q_turnos = text("""
                SELECT count(id) FROM comercial.turnos_caja
                WHERE sucursal_id = :sid AND estado IN ('ABIERTO', 'CONCILIACION', 'RECUPERACION')
            """)
            res_turnos = await self.db.execute(q_turnos, {"sid": sucursal_id})
            turnos_abiertos = res_turnos.scalar() or 0

            # c) Traslados pendientes en curso
            q_tras = select(func.count(Traslado.id)).where(
                (Traslado.sucursal_origen_id == sucursal_id) | (Traslado.sucursal_destino_id == sucursal_id),
                Traslado.estado.in_(["SOLICITADO", "APROBADO", "DESPACHADO"]),
            )
            res_tras = await self.db.execute(q_tras)
            traslados_pendientes = res_tras.scalar() or 0

            if reservas_pendientes > 0 or turnos_abiertos > 0 or traslados_pendientes > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"No se puede desactivar la sucursal por compromisos pendientes: "
                        f"{reservas_pendientes} reservas activas, "
                        f"{turnos_abiertos} turnos de caja abiertos, "
                        f"{traslados_pendientes} traslados en curso."
                    ),
                )

        # 6. Aplicar cambios
        if dto.nombre is not None:
            sucursal.nombre = dto.nombre.strip()
        if dto.ciudad_id is not None:
            sucursal.ciudad_id = dto.ciudad_id
        if dto.direccion is not None:
            sucursal.direccion = dto.direccion.strip()
        if dto.telefono is not None:
            sucursal.telefono = dto.telefono.strip()
        if dto.numero_anillo is not None:
            sucursal.numero_anillo = dto.numero_anillo
        if dto.tarifa_base_delivery is not None:
            sucursal.tarifa_base_delivery = dto.tarifa_base_delivery
        if dto.incremento_anillo_delivery is not None:
            sucursal.incremento_anillo_delivery = dto.incremento_anillo_delivery
        if dto.anillo_minimo_delivery is not None:
            sucursal.anillo_minimo_delivery = dto.anillo_minimo_delivery
        if dto.anillo_maximo_delivery is not None:
            sucursal.anillo_maximo_delivery = dto.anillo_maximo_delivery
        if dto.delivery_activo is not None:
            sucursal.delivery_activo = dto.delivery_activo
        if dto.activa is not None:
            sucursal.activa = dto.activa

        nueva_revision = sucursal.revision + 1
        sucursal.revision = nueva_revision

        # 7. Outbox en la misma transacción (sin silenciar errores)
        transicion = "ACTUALIZADA"
        if dto.activa is not None and dto.activa != sucursal.activa:
            transicion = "ACTIVADA" if dto.activa else "DESACTIVADA"

        await self.db.execute(
            text("""
                INSERT INTO comercial.eventos_outbox (
                    id, empresa_id, recurso_tipo, recurso_id, transicion, revision, payload, estado, intentos, creado_en
                ) VALUES (
                    :id, :empresa_id, 'SUCURSAL', :recurso_id, :transicion, :revision, cast(:payload as jsonb), 'PENDIENTE', 0, now()
                )
            """),
            {
                "id": uuid.uuid4(),
                "empresa_id": sucursal.empresa_id,
                "recurso_id": sucursal.id,
                "transicion": transicion,
                "revision": nueva_revision,
                "payload": json.dumps({
                    "sucursal_id": str(sucursal.id),
                    "nombre": sucursal.nombre,
                    "activa": sucursal.activa,
                    "revision": nueva_revision,
                }),
            },
        )

        await self.db.commit()
        await self.db.refresh(sucursal)
        return await self._construir_dto(sucursal)

    async def listar(
        self,
        usuario: Usuario,
        ciudad_id: Optional[uuid.UUID] = None,
        empresa_id: Optional[uuid.UUID] = None,
        solo_activas: bool = True,
    ) -> List[SucursalDTO]:
        eid = usuario.empresa_id or empresa_id
        sucursales = await self.sucursal_repo.listar(ciudad_id=ciudad_id, empresa_id=eid, solo_activas=solo_activas)
        return [await self._construir_dto(s) for s in sucursales]

    async def obtenerPorId(self, sucursal_id: uuid.UUID, usuario: Usuario) -> SucursalDTO:
        s = await self.sucursal_repo.buscarPorId(sucursal_id)
        if not s:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sucursal no encontrada",
            )
        if usuario.empresa_id is not None and s.empresa_id != usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para consultar sucursales de otra empresa",
            )
        return await self._construir_dto(s)

    async def actualizarTarifas(
        self, sucursal_id: uuid.UUID, dto: ConfigurarTarifasDeliveryDTO, usuario: Usuario
    ) -> SucursalDTO:
        q = select(Sucursal).where(Sucursal.id == sucursal_id).with_for_update()
        res = await self.db.execute(q)
        sucursal = res.scalars().first()
        if not sucursal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")
        if usuario.empresa_id is not None and sucursal.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")

        if dto.revision is not None and dto.revision != sucursal.revision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Revisión obsoleta: enviada {dto.revision}, actual {sucursal.revision}",
            )

        actualizada = await self.sucursal_repo.actualizarTarifas(
            sucursal_id=sucursal_id,
            tarifa_base_delivery=dto.tarifa_base_delivery,
            incremento_anillo_delivery=dto.incremento_anillo_delivery,
            anillo_minimo_delivery=dto.anillo_minimo_delivery,
            anillo_maximo_delivery=dto.anillo_maximo_delivery,
            delivery_activo=dto.delivery_activo,
        )
        actualizada.revision += 1
        await self.db.commit()
        await self.db.refresh(actualizada)
        return await self._construir_dto(actualizada)

    async def actualizarAdelanto(
        self, sucursal_id: uuid.UUID, dto: ConfigurarAdelantoDTO, usuario: Usuario
    ) -> SucursalDTO:
        q = select(Sucursal).where(Sucursal.id == sucursal_id).with_for_update()
        res = await self.db.execute(q)
        sucursal = res.scalars().first()
        if not sucursal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")
        if usuario.empresa_id is not None and sucursal.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")

        if dto.revision is not None and dto.revision != sucursal.revision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Revisión obsoleta: enviada {dto.revision}, actual {sucursal.revision}",
            )

        modalidad = (dto.modalidad_adelanto or "").upper() if dto.modalidad_adelanto else None
        if dto.adelanto_activo:
            if modalidad not in ("MONTO_FIJO", "PORCENTAJE"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="modalidad_adelanto debe ser MONTO_FIJO o PORCENTAJE cuando el adelanto esta activo",
                )
            if dto.valor_adelanto is None or dto.valor_adelanto <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="valor_adelanto debe ser positivo cuando el adelanto esta activo",
                )
            if modalidad == "PORCENTAJE" and dto.valor_adelanto > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="valor_adelanto no puede superar 100 en modalidad PORCENTAJE",
                )

        actualizada = await self.sucursal_repo.actualizarAdelanto(
            sucursal_id=sucursal_id,
            adelanto_activo=dto.adelanto_activo,
            modalidad_adelanto=modalidad,
            valor_adelanto=dto.valor_adelanto,
        )
        actualizada.revision += 1
        await self.db.commit()
        await self.db.refresh(actualizada)
        return await self._construir_dto(actualizada)
