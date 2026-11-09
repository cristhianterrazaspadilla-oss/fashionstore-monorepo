"""Tareas programadas Ciclo 2 — job de expiracion CU24.

La logica vive en ReservaService.expirarVencidas() (testeable con reloj
inyectado, advisory lock PostgreSQL y SKIP LOCKED). Este modulo solo
programa su ejecucion periodica con APScheduler cuando el ajuste
EXPIRACION_JOB_ACTIVO esta activo (produccion). En pruebas permanece
apagado y se usa el endpoint manual.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
_scheduler = None


async def expirar_ventas_stripe_segura(
    db: Optional[AsyncSession] = None,
    ahora: Optional[datetime] = None,
    lote: int = 100,
    empresa_id: Optional[uuid.UUID] = None,
    venta_id: Optional[uuid.UUID] = None,
) -> dict:
    """Tarea de Expiración Segura (H4).

    Expira ventas PENDIENTE_PAGO donde expira_en <= ahora.
    Consulta Stripe primero: si está SUCCEEDED, marca CAPTURADO y NO libera stock.
    Si está CANCELED o pendiente, cancela en pasarela y libera stock (comprometido_digital -> disponible, LIBERACION_DIGITAL).
    """
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService

    if db is not None:
        servicio = StripeService(db)
        return await servicio.cancelar_ventas_stripe_vencidas(
            lote=lote, ahora_param=ahora, empresa_id=empresa_id, venta_id=venta_id,
        )

    async with AsyncSessionLocal() as session:
        servicio = StripeService(session)
        return await servicio.cancelar_ventas_stripe_vencidas(
            lote=lote, ahora_param=ahora, empresa_id=empresa_id, venta_id=venta_id,
        )


async def ejecutar_expiracion_programada() -> None:
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.core.modules.reservas_traslados.services.expiracion_service import ExpiracionService

    async with AsyncSessionLocal() as db:
        servicio = ExpiracionService(db)
        try:
            resultado = await servicio.expirar_reservas_vencidas()
            logger.info(
                "Expiracion CU26/CU24: procesadas=%s expiradas=%s omitidas=%s errores=%s bloqueo=%s",
                resultado.procesadas, len(resultado.expiradas),
                len(resultado.omitidas), len(resultado.errores), resultado.bloqueo_activo,
            )
        except Exception:
            logger.exception("Fallo el job de expiracion CU26/CU24")
    # Ciclo 3 (CU15/H4): expiración segura de ventas Stripe vencidas con verificación en pasarela.
    async with AsyncSessionLocal() as db:
        try:
            resumen = await expirar_ventas_stripe_segura(db=db)
            logger.info(
                "Expiracion segura ventas Stripe: procesadas=%s canceladas=%s omitidas=%s",
                resumen.get("procesadas"), len(resumen.get("canceladas", [])), len(resumen.get("omitidas", [])),
            )
        except Exception:
            logger.exception("Fallo el job de expiracion segura de ventas Stripe")


async def ejecutar_outbox_programado() -> None:
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.core.modules.identidad_empresas.services.notificacion_service import (
        ejecutar_ciclo_worker_outbox,
    )

    try:
        resultado = await ejecutar_ciclo_worker_outbox(AsyncSessionLocal, limite=50)
        if resultado.get("procesados", 0) > 0:
            logger.info(
                "Worker Outbox E2: procesados=%s enviados=%s reintentos=%s fallidos=%s",
                resultado.get("procesados"),
                resultado.get("enviados"),
                resultado.get("reintentos"),
                resultado.get("fallidos"),
            )
    except Exception:
        logger.exception("Fallo el worker programado de notificaciones outbox")


def iniciar_scheduler(intervalo_minutos: int = 10):
    """Inicia APScheduler con una sola instancia (max_instances=1, coalesce)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:  # pragma: no cover (apscheduler en requirements)
        logger.warning("APScheduler no instalado: job CU24 solo manual")
        return None
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        ejecutar_expiracion_programada,
        "interval",
        minutes=intervalo_minutos,
        id="cu24_expirar_vencidas",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        ejecutar_outbox_programado,
        "interval",
        seconds=30,
        id="worker_outbox_notificaciones",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("Scheduler iniciado: CU24 cada %s min, Outbox Worker cada 30s", intervalo_minutos)
    return _scheduler


def detener_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
