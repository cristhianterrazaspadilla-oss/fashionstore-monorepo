"""Servicio de consulta y validación de planes y suscripciones (CU02 / C12 / C28).

Diseñado para ser reutilizado por el Bloque A (gestión de empresas y planes)
y por el Bloque B (capacidad para reservas online y offline).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.reloj import utcnow, asegurar_utc
from backend.app.core.modules.identidad_empresas.models import Empresa, Plan, Suscripcion


@dataclass
class EstadoCapacidadPlan:
    empresa_id: uuid.UUID
    habilitado: bool
    estado_suscripcion: str  # "VIGENTE", "EN_GRACIA", "VENCIDA_FUERA_DE_GRACIA", "SIN_SUSCRIPCION", "PLAN_INACTIVO", "EMPRESA_NO_ACTIVA", "FUTURA", "PLAN_NO_HABILITADO"
    en_gracia: bool
    plan_codigo: Optional[str] = None
    plan_nombre: Optional[str] = None
    max_sucursales_activas: int = 0
    permite_operacion_offline: bool = False
    inicia_en: Optional[datetime] = None
    vence_en: Optional[datetime] = None
    gracia_hasta: Optional[datetime] = None
    motivo_rechazo: Optional[str] = None
    reportes_generativos: bool = False
    modelos_ml: bool = False


class PlanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def exigir_capacidad_analitica(self, empresa_id, capacidad, fecha_referencia=None):
        """Autoriza nueva generación/entrenamiento, no consultas convencionales.

        Reutiliza suscripción efectiva y gracia de 72 h. Las capacidades son
        configurables en Plan; no se infieren del nombre Básico/Profesional.
        """
        if capacidad not in ("reportes_generativos", "modelos_ml"):
            raise ValueError("Capacidad analítica desconocida")
        estado = await self.validar_capacidad(empresa_id, fecha_referencia=fecha_referencia)
        if not estado.habilitado or not getattr(estado, capacidad):
            raise HTTPException(status_code=403, detail="La suscripción no habilita esta capacidad analítica")
        return estado

    async def consultar_suscripcion_efectiva(
        self,
        empresa_id: uuid.UUID,
        fecha_referencia: Optional[datetime] = None,
    ) -> Optional[Tuple[Suscripcion, Plan]]:
        """Prioriza la versión iniciada aplicable; una renovación futura no desplaza la actual."""
        referencia = asegurar_utc(fecha_referencia or utcnow())
        query = (
            select(Suscripcion, Plan)
            .join(Plan, Plan.id == Suscripcion.plan_id)
            .where(Suscripcion.empresa_id == empresa_id, Suscripcion.inicia_en <= referencia)
            .order_by(Suscripcion.inicia_en.desc(), Suscripcion.version.desc())
        )
        result = await self.db.execute(query)
        fila = result.first()
        if not fila:
            # Si solo hay asignaciones futuras, conservar el estado FUTURA.
            futura = await self.db.execute(
                select(Suscripcion, Plan)
                .join(Plan, Plan.id == Suscripcion.plan_id)
                .where(Suscripcion.empresa_id == empresa_id)
                .order_by(Suscripcion.inicia_en.asc(), Suscripcion.version.asc())
                .limit(1)
            )
            fila = futura.first()
            if not fila:
                return None
        return (fila[0], fila[1])

    async def validar_capacidad(
        self,
        empresa_id: uuid.UUID,
        fecha_referencia: Optional[datetime] = None,
        es_offline: bool = False,
        ahora: Optional[datetime] = None,
    ) -> EstadoCapacidadPlan:
        """Valida si la empresa cuenta con plan y suscripción vigentes o en gracia (3 días).

        Reglas C12 y C28:
        - Fechas manuales en UTC.
        - Durante los 3 días (72 h) continuos de gracia desde vence_en, el servicio continúa.
        - Tras la gracia, se bloquean nuevas reservas, ventas y turnos.
        - Si no hay suscripción o el plan está inactivo, se bloquea.
        - Si es_offline=True y el plan no permite operación offline, se bloquea.
        """
        ref = ahora or fecha_referencia
        ahora = asegurar_utc(ref or utcnow())

        # 1. Verificar existencia y estado de la empresa
        empresa = await self.db.get(Empresa, empresa_id)
        if not empresa or empresa.estado != "ACTIVA":
            return EstadoCapacidadPlan(
                empresa_id=empresa_id,
                habilitado=False,
                estado_suscripcion="EMPRESA_NO_ACTIVA",
                en_gracia=False,
                motivo_rechazo="La empresa no existe o no se encuentra activa",
            )

        # 2. Consultar suscripción y plan
        par = await self.consultar_suscripcion_efectiva(empresa_id, ahora)
        if not par:
            return EstadoCapacidadPlan(
                empresa_id=empresa_id,
                habilitado=False,
                estado_suscripcion="SIN_SUSCRIPCION",
                en_gracia=False,
                motivo_rechazo="La empresa no cuenta con una suscripción registrada",
            )

        suscripcion, plan = par
        if not plan.activo:
            return EstadoCapacidadPlan(
                empresa_id=empresa_id,
                habilitado=False,
                estado_suscripcion="PLAN_INACTIVO",
                en_gracia=False,
                plan_codigo=plan.codigo,
                plan_nombre=plan.nombre,
                motivo_rechazo="El plan asignado a la empresa está inactivo",
            )

        inicia_en = asegurar_utc(suscripcion.inicia_en)
        vence_en = asegurar_utc(suscripcion.vence_en)
        gracia_hasta = vence_en + timedelta(days=3)

        if ahora < inicia_en:
            return EstadoCapacidadPlan(
                empresa_id=empresa_id,
                habilitado=False,
                estado_suscripcion="FUTURA",
                en_gracia=False,
                plan_codigo=plan.codigo,
                plan_nombre=plan.nombre,
                inicia_en=inicia_en,
                vence_en=vence_en,
                gracia_hasta=gracia_hasta,
                motivo_rechazo="La suscripción de la empresa aún no ha iniciado",
            )

        if es_offline and not plan.permite_operacion_offline:
            return EstadoCapacidadPlan(
                empresa_id=empresa_id,
                habilitado=False,
                estado_suscripcion="PLAN_NO_HABILITADO",
                en_gracia=False,
                plan_codigo=plan.codigo,
                plan_nombre=plan.nombre,
                inicia_en=inicia_en,
                vence_en=vence_en,
                gracia_hasta=gracia_hasta,
                motivo_rechazo="El plan asignado no permite operaciones fuera de línea",
            )

        if ahora < vence_en:
            # Vigente normal
            return EstadoCapacidadPlan(
                empresa_id=empresa_id,
                habilitado=True,
                estado_suscripcion="VIGENTE",
                reportes_generativos=plan.reportes_generativos,
                modelos_ml=plan.modelos_ml,
                en_gracia=False,
                plan_codigo=plan.codigo,
                plan_nombre=plan.nombre,
                max_sucursales_activas=plan.max_sucursales_activas,
                permite_operacion_offline=plan.permite_operacion_offline,
                inicia_en=inicia_en,
                vence_en=vence_en,
                gracia_hasta=gracia_hasta,
            )

        if ahora < gracia_hasta:
            # En período de gracia de 3 días (72 h): el servicio continúa
            return EstadoCapacidadPlan(
                empresa_id=empresa_id,
                habilitado=True,
                estado_suscripcion="EN_GRACIA",
                reportes_generativos=plan.reportes_generativos,
                modelos_ml=plan.modelos_ml,
                en_gracia=True,
                plan_codigo=plan.codigo,
                plan_nombre=plan.nombre,
                max_sucursales_activas=plan.max_sucursales_activas,
                permite_operacion_offline=plan.permite_operacion_offline,
                inicia_en=inicia_en,
                vence_en=vence_en,
                gracia_hasta=gracia_hasta,
            )

        # Vencida fuera de gracia: se bloquean nuevas reservas
        return EstadoCapacidadPlan(
            empresa_id=empresa_id,
            habilitado=False,
            estado_suscripcion="VENCIDA_FUERA_DE_GRACIA",
            en_gracia=False,
            plan_codigo=plan.codigo,
            plan_nombre=plan.nombre,
            max_sucursales_activas=plan.max_sucursales_activas,
            permite_operacion_offline=plan.permite_operacion_offline,
            inicia_en=inicia_en,
            vence_en=vence_en,
            gracia_hasta=gracia_hasta,
            motivo_rechazo="La suscripción de la empresa ha vencido y superó el período de gracia de 3 días",
        )
