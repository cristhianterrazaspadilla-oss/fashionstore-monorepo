"""Servicio SuscripcionService — CU02: Administrar suscripción de empresa."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.reloj import utcnow, asegurar_utc
from backend.app.core.modules.identidad_empresas.models import Empresa, Plan, Suscripcion, Usuario
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.identidad_empresas.schemas import (
    AsignarSuscripcionDTO,
    SuscripcionRespuestaDTO,
    PlanDetalleDTO,
)
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService
from backend.app.core.idempotencia_ciclo3 import hash_payload, reclamar, guardar_respuesta


class SuscripcionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.plan_service = PlanService(db)

    async def listar_planes(self) -> List[PlanDetalleDTO]:
        q = select(Plan).where(Plan.activo == True).order_by(Plan.max_sucursales_activas.asc())
        res = await self.db.execute(q)
        planes = res.scalars().all()
        return [
            PlanDetalleDTO(
                id=p.id,
                codigo=p.codigo,
                nombre=p.nombre,
                max_sucursales_activas=p.max_sucursales_activas,
                reportes_generativos=p.reportes_generativos,
                modelos_ml=p.modelos_ml,
                permite_operacion_offline=p.permite_operacion_offline,
                activo=p.activo,
            )
            for p in planes
        ]

    async def asignar_o_renovar(
        self,
        empresa_id: uuid.UUID,
        dto: AsignarSuscripcionDTO,
        admin_plataforma: Usuario,
        idempotency_key: uuid.UUID,
    ) -> SuscripcionRespuestaDTO:
        # 0. Idempotencia durable (CU02)
        payload_dict = dto.model_dump(mode="json") if hasattr(dto, "model_dump") else dto.dict()
        hash_sol = hash_payload(payload_dict)
        registro_previo = await reclamar(
            self.db,
            clave=idempotency_key,
            hash_solicitud=hash_sol,
            recurso_tipo="SUSCRIPCION",
            operacion="ASIGNAR_SUSCRIPCION",
            usuario_id=admin_plataforma.id,
        )
        if registro_previo is not None and registro_previo.respuesta:
            if str(registro_previo.respuesta.get("empresa_id")) != str(empresa_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La clave de idempotencia ya pertenece a otra empresa",
                )
            return SuscripcionRespuestaDTO(**registro_previo.respuesta)
        if registro_previo is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La asignación con esta clave sigue pendiente de confirmación",
            )

        # 1. Validar fechas
        inicio_utc = asegurar_utc(dto.inicio_en)
        vence_utc = asegurar_utc(dto.vence_en)
        if vence_utc <= inicio_utc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="vence_en debe ser estrictamente posterior a inicio_en",
            )

        # 2. Validar existencia de la empresa
        empresa = await self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Empresa con ID {empresa_id} no encontrada",
            )

        # 3. Validar existencia del plan
        plan = await self.db.get(Plan, dto.plan_id)
        if not plan or not plan.activo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan con ID {dto.plan_id} no encontrado o inactivo",
            )

        # 4. Bloquear empresa para serializar asignaciones/cambios de plan
        await self.db.execute(select(Empresa.id).where(Empresa.id == empresa_id).with_for_update())

        # 5. Obtener versión previa para control optimista
        q_max_ver = select(func.max(Suscripcion.version)).where(Suscripcion.empresa_id == empresa_id)
        res_ver = await self.db.execute(q_max_ver)
        version_anterior = res_ver.scalar()

        if dto.revision is not None and version_anterior is not None and dto.revision != version_anterior:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Revisión obsoleta: la versión previa ({dto.revision}) no coincide con la versión actual ({version_anterior})",
            )

        nueva_version = (version_anterior or 0) + 1

        # 6. Comprobar reducción de plan contra sucursales activas actuales
        q_activas = select(func.count(Sucursal.id)).where(
            Sucursal.empresa_id == empresa_id,
            Sucursal.activa == True,
        )
        res_activas = await self.db.execute(q_activas)
        sucursales_activas = res_activas.scalar() or 0

        if sucursales_activas > plan.max_sucursales_activas:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Reducción incompatible: la empresa cuenta con {sucursales_activas} sucursales activas "
                    f"y el plan '{plan.nombre}' solo admite un máximo de {plan.max_sucursales_activas}. "
                    "Desactive sucursales antes de reducir el plan."
                ),
            )

        # 6.1 Ajustar vigencias previas y futuras sin DELETE destructivo (preservando historial)
        # 6.1.1 Truncar la suscripción que inició antes de inicio_utc y vencía después
        await self.db.execute(
            text("""
                UPDATE organizacion.suscripciones
                SET vence_en = :inicio_utc
                WHERE empresa_id = :empresa_id
                  AND inicia_en < :inicio_utc
                  AND vence_en > :inicio_utc
            """),
            {"empresa_id": empresa_id, "inicio_utc": inicio_utc},
        )

        # 6.1.2 Reubicar suscripciones futuras solapadas preservando historial y duración sin DELETE
        q_futuras = (
            select(Suscripcion)
            .where(
                Suscripcion.empresa_id == empresa_id,
                Suscripcion.inicia_en >= inicio_utc,
            )
            .order_by(Suscripcion.inicia_en.asc(), Suscripcion.version.asc())
        )
        futuras_res = await self.db.execute(q_futuras)
        futuras = list(futuras_res.scalars().all())

        if futuras:
            cursor = vence_utc
            cambios = []
            for fut in futuras:
                duracion = fut.vence_en - fut.inicia_en
                if fut.inicia_en < cursor:
                    nuevo_inicio = cursor
                    nuevo_vence = cursor + duracion
                    cambios.append((fut, nuevo_inicio, nuevo_vence))
                    cursor = nuevo_vence
                else:
                    cursor = max(cursor, fut.vence_en)

            # Actualizar en orden descendente para no violar ex_suscripciones_vigencias
            for fut, nuevo_inicio, nuevo_vence in reversed(cambios):
                fut.inicia_en = nuevo_inicio
                fut.vence_en = nuevo_vence
            await self.db.flush()

        # 7. Crear nueva suscripción versionada
        nueva_suscripcion = Suscripcion(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            plan_id=plan.id,
            version=nueva_version,
            inicia_en=inicio_utc,
            vence_en=vence_utc,
            creada_por=admin_plataforma.id,
            motivo=dto.motivo.strip(),
        )
        self.db.add(nueva_suscripcion)
        await self.db.flush()

        # Si estaba pendiente de plan, pasa a activa
        if empresa.estado == "PENDIENTE_PLAN":
            empresa.estado = "ACTIVA"

        # 8. Evento outbox en la misma transacción (sin silenciar errores)
        await self.db.execute(
            text("""
                INSERT INTO comercial.eventos_outbox (
                    id, empresa_id, recurso_tipo, recurso_id, transicion, revision, payload, estado, intentos, creado_en
                ) VALUES (
                    :id, :empresa_id, 'SUSCRIPCION', :recurso_id, 'ASIGNACION', :revision, cast(:payload as jsonb), 'PENDIENTE', 0, now()
                )
            """),
            {
                "id": uuid.uuid4(),
                "empresa_id": empresa_id,
                "recurso_id": nueva_suscripcion.id,
                "revision": nueva_version,
                "payload": json.dumps({
                    "suscripcion_id": str(nueva_suscripcion.id),
                    "plan_id": str(plan.id),
                    "plan_codigo": plan.codigo,
                    "version": nueva_version,
                    "inicia_en": inicio_utc.isoformat(),
                    "vence_en": vence_utc.isoformat(),
                    "motivo": dto.motivo.strip(),
                }),
            },
        )

        gracia_hasta = vence_utc + timedelta(days=3)
        ahora = utcnow()
        if ahora < inicio_utc:
            estado_efectivo = "FUTURA"
        elif ahora < vence_utc:
            estado_efectivo = "VIGENTE"
        elif ahora < gracia_hasta:
            estado_efectivo = "EN_GRACIA"
        else:
            estado_efectivo = "VENCIDA_FUERA_DE_GRACIA"

        capacidades = ["VENTAS_ONLINE", "RESERVAS"]
        if plan.permite_operacion_offline:
            capacidades.append("OFFLINE")
        if plan.reportes_generativos:
            capacidades.append("REPORTES_GENERATIVOS")
        if plan.modelos_ml:
            capacidades.append("MODELOS_ML")

        respuesta = SuscripcionRespuestaDTO(
            suscripcion_id=nueva_suscripcion.id,
            empresa_id=empresa_id,
            plan_id=plan.id,
            plan_codigo=plan.codigo,
            plan_nombre=plan.nombre,
            version=nueva_version,
            revision=nueva_version,
            inicio_en=inicio_utc,
            vence_en=vence_utc,
            gracia_hasta=gracia_hasta,
            estado_efectivo=estado_efectivo,
            capacidades=capacidades,
            sucursales_activas=sucursales_activas,
            limite_sucursales=plan.max_sucursales_activas,
            permite_offline=plan.permite_operacion_offline,
            creada_en=nueva_suscripcion.creada_en,
            motivo=nueva_suscripcion.motivo,
        )

        resp_dict = respuesta.model_dump(mode="json") if hasattr(respuesta, "model_dump") else respuesta.dict()
        resp_dict = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in resp_dict.items()}
        await guardar_respuesta(
            self.db,
            clave=idempotency_key,
            respuesta=resp_dict,
            recurso_id=nueva_suscripcion.id,
            usuario_id=admin_plataforma.id,
            recurso_tipo="SUSCRIPCION",
            operacion="ASIGNAR_SUSCRIPCION",
        )

        await self.db.commit()
        return respuesta

    async def consultar_plan_empresa(self, empresa_id: uuid.UUID) -> SuscripcionRespuestaDTO:
        empresa = await self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")

        ahora = utcnow()
        capacidad = await self.plan_service.validar_capacidad(empresa_id, ahora=ahora)
        par = await self.plan_service.consultar_suscripcion_efectiva(empresa_id, ahora)
        if not par:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La empresa no cuenta con una suscripción registrada",
            )
        suscripcion, plan = par

        q_activas = select(func.count(Sucursal.id)).where(
            Sucursal.empresa_id == empresa_id,
            Sucursal.activa == True,
        )
        res_activas = await self.db.execute(q_activas)
        sucursales_activas = res_activas.scalar() or 0

        capacidades = ["VENTAS_ONLINE", "RESERVAS"]
        if plan.permite_operacion_offline:
            capacidades.append("OFFLINE")
        if plan.reportes_generativos:
            capacidades.append("REPORTES_GENERATIVOS")
        if plan.modelos_ml:
            capacidades.append("MODELOS_ML")

        vence_utc = asegurar_utc(suscripcion.vence_en)
        gracia_hasta = vence_utc + timedelta(days=3)

        return SuscripcionRespuestaDTO(
            suscripcion_id=suscripcion.id,
            empresa_id=empresa_id,
            plan_id=plan.id,
            plan_codigo=plan.codigo,
            plan_nombre=plan.nombre,
            version=suscripcion.version,
            revision=suscripcion.version,
            inicio_en=asegurar_utc(suscripcion.inicia_en),
            vence_en=vence_utc,
            gracia_hasta=gracia_hasta,
            estado_efectivo=capacidad.estado_suscripcion,
            capacidades=capacidades,
            sucursales_activas=sucursales_activas,
            limite_sucursales=plan.max_sucursales_activas,
            permite_offline=plan.permite_operacion_offline,
            creada_en=suscripcion.creada_en,
            motivo=suscripcion.motivo,
        )

    async def listar_historial(self, empresa_id: uuid.UUID) -> List[SuscripcionRespuestaDTO]:
        q = (
            select(Suscripcion, Plan)
            .join(Plan, Plan.id == Suscripcion.plan_id)
            .where(Suscripcion.empresa_id == empresa_id)
            .order_by(Suscripcion.version.desc())
        )
        res = await self.db.execute(q)
        filas = res.all()

        q_activas = select(func.count(Sucursal.id)).where(
            Sucursal.empresa_id == empresa_id,
            Sucursal.activa == True,
        )
        res_act = await self.db.execute(q_activas)
        sucursales_activas = res_act.scalar() or 0
        ahora = utcnow()

        resultados = []
        for suscripcion, plan in filas:
            inicio_utc = asegurar_utc(suscripcion.inicia_en)
            vence_utc = asegurar_utc(suscripcion.vence_en)
            gracia_hasta = vence_utc + timedelta(days=3)

            if ahora < inicio_utc:
                est = "FUTURA"
            elif ahora < vence_utc:
                est = "VIGENTE"
            elif ahora < gracia_hasta:
                est = "EN_GRACIA"
            else:
                est = "VENCIDA_FUERA_DE_GRACIA"

            capacidades = ["VENTAS_ONLINE", "RESERVAS"]
            if plan.permite_operacion_offline:
                capacidades.append("OFFLINE")
            if plan.reportes_generativos:
                capacidades.append("REPORTES_GENERATIVOS")
            if plan.modelos_ml:
                capacidades.append("MODELOS_ML")

            resultados.append(
                SuscripcionRespuestaDTO(
                    suscripcion_id=suscripcion.id,
                    empresa_id=empresa_id,
                    plan_id=plan.id,
                    plan_codigo=plan.codigo,
                    plan_nombre=plan.nombre,
                    version=suscripcion.version,
                    revision=suscripcion.version,
                    inicio_en=inicio_utc,
                    vence_en=vence_utc,
                    gracia_hasta=gracia_hasta,
                    estado_efectivo=est,
                    capacidades=capacidades,
                    sucursales_activas=sucursales_activas,
                    limite_sucursales=plan.max_sucursales_activas,
                    permite_offline=plan.permite_operacion_offline,
                    creada_en=suscripcion.creada_en,
                    motivo=suscripcion.motivo,
                )
            )
        return resultados
