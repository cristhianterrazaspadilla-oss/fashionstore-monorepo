"""Servicio TasaCambioService — CU12: Configurar tasa de conversión BOB/USD."""
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.reloj import utcnow, asegurar_utc
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.organizacion.models import TasaCambio
from backend.app.core.modules.organizacion.schemas import (
    TasaCambioCrearDTO,
    TasaCambioDTO,
    CotizacionMonedaDTO,
)
from backend.app.core.idempotencia_ciclo3 import hash_payload, reclamar, guardar_respuesta


class TasaCambioService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def crear_tasa(
        self,
        dto: TasaCambioCrearDTO,
        admin_plataforma: Usuario,
        idempotency_key: uuid.UUID,
    ) -> TasaCambioDTO:
        # 0. Idempotencia durable (CU12)
        payload_dict = dto.model_dump(mode="json") if hasattr(dto, "model_dump") else dto.dict()
        hash_sol = hash_payload(payload_dict)
        registro_previo = await reclamar(
            self.db,
            clave=idempotency_key,
            hash_solicitud=hash_sol,
            recurso_tipo="TASA_CAMBIO",
            operacion="CREAR_TASA",
            usuario_id=admin_plataforma.id,
        )
        if registro_previo is not None and registro_previo.respuesta:
            return TasaCambioDTO(**registro_previo.respuesta)

        # 1. Validar fechas
        desde_utc = asegurar_utc(dto.vigente_desde)
        hasta_utc = asegurar_utc(dto.vigente_hasta) if dto.vigente_hasta else None
        if hasta_utc and hasta_utc <= desde_utc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="vigente_hasta debe ser estrictamente posterior a vigente_desde",
            )

        if dto.tasa_bob_por_usd <= Decimal("0"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="tasa_bob_por_usd debe ser estrictamente positiva",
            )

        # 2. Concurrencia segura y ajuste de vigencias sin DELETE destructivo
        await self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext('plataforma.tasas_cambio'))"))

        # 2.1 Cerrar la tasa previa activa en `desde_utc`
        await self.db.execute(
            text("""
                UPDATE plataforma.tasas_cambio
                SET vigente_hasta = :desde_utc
                WHERE (vigente_hasta IS NULL OR vigente_hasta > :desde_utc)
                  AND vigente_desde < :desde_utc
            """),
            {"desde_utc": desde_utc},
        )

        # 2.2 Reubicar tasas futuras solapadas preservando historial y duración sin DELETE
        q_futuras = (
            select(TasaCambio)
            .where(TasaCambio.vigente_desde >= desde_utc)
            .order_by(TasaCambio.vigente_desde.asc(), TasaCambio.version.asc())
        )
        futuras_res = await self.db.execute(q_futuras)
        futuras = list(futuras_res.scalars().all())

        if hasta_utc is None:
            estrictamente_posteriores = [f for f in futuras if f.vigente_desde > desde_utc]
            if estrictamente_posteriores:
                min_posterior = min(f.vigente_desde for f in estrictamente_posteriores)
                hasta_utc = min_posterior
            elif futuras:
                desplazamiento = timedelta(days=365)
                hasta_utc = desde_utc + desplazamiento

        if hasta_utc is not None and futuras:
            cursor = hasta_utc
            cambios = []
            for fut in futuras:
                duracion = (fut.vigente_hasta - fut.vigente_desde) if fut.vigente_hasta else None
                if fut.vigente_desde < cursor:
                    nuevo_desde = cursor
                    nuevo_hasta = (cursor + duracion) if duracion else None
                    cambios.append((fut, nuevo_desde, nuevo_hasta))
                    cursor = nuevo_hasta if nuevo_hasta else (cursor + timedelta(days=365))
                else:
                    cursor = fut.vigente_hasta if fut.vigente_hasta else (fut.vigente_desde + timedelta(days=365))

            for fut, nuevo_desde, nuevo_hasta in reversed(cambios):
                await self.db.execute(
                    text("""
                        UPDATE plataforma.tasas_cambio
                        SET vigente_desde = :nd, vigente_hasta = :nh
                        WHERE id = :id
                    """),
                    {"nd": nuevo_desde, "nh": nuevo_hasta, "id": fut.id},
                )
                fut.vigente_desde = nuevo_desde
                fut.vigente_hasta = nuevo_hasta

        # 3. Obtener siguiente versión
        q_ver = select(func.max(TasaCambio.version))
        res_ver = await self.db.execute(q_ver)
        max_ver = res_ver.scalar() or 0
        nueva_version = max_ver + 1

        nueva_tasa = TasaCambio(
            id=uuid.uuid4(),
            version=nueva_version,
            tasa_bob_por_usd=dto.tasa_bob_por_usd,
            vigente_desde=desde_utc,
            vigente_hasta=hasta_utc,
            motivo=dto.motivo.strip(),
            creada_por=admin_plataforma.id,
            creada_en=utcnow(),
        )
        self.db.add(nueva_tasa)
        await self.db.flush()

        # TasaCambio es global de plataforma (sin empresa_id)

        respuesta = TasaCambioDTO(
            id=nueva_tasa.id,
            version=nueva_tasa.version,
            tasa_bob_por_usd=nueva_tasa.tasa_bob_por_usd,
            vigente_desde=nueva_tasa.vigente_desde,
            vigente_hasta=nueva_tasa.vigente_hasta,
            motivo=nueva_tasa.motivo,
            creada_por=nueva_tasa.creada_por,
            creada_en=nueva_tasa.creada_en,
        )

        resp_dict = respuesta.model_dump(mode="json") if hasattr(respuesta, "model_dump") else respuesta.dict()
        resp_dict = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in resp_dict.items()}
        await guardar_respuesta(
            self.db,
            clave=idempotency_key,
            respuesta=resp_dict,
            recurso_id=nueva_tasa.id,
            usuario_id=admin_plataforma.id,
            recurso_tipo="TASA_CAMBIO",
            operacion="CREAR_TASA",
        )

        await self.db.commit()
        return respuesta

    async def obtener_tasa_vigente(self, momento: Optional[datetime] = None) -> TasaCambioDTO:
        instante = asegurar_utc(momento) if momento else utcnow()
        q = (
            select(TasaCambio)
            .where(
                TasaCambio.vigente_desde <= instante,
                (TasaCambio.vigente_hasta == None) | (TasaCambio.vigente_hasta > instante),  # noqa: E711
            )
            .order_by(TasaCambio.version.desc())
        )
        res = await self.db.execute(q)
        tasa = res.scalars().first()
        if not tasa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No existe tasa de cambio BOB/USD vigente configurada en la plataforma",
            )
        return TasaCambioDTO(
            id=tasa.id,
            version=tasa.version,
            tasa_bob_por_usd=tasa.tasa_bob_por_usd,
            vigente_desde=tasa.vigente_desde,
            vigente_hasta=tasa.vigente_hasta,
            motivo=tasa.motivo,
            creada_por=tasa.creada_por,
            creada_en=tasa.creada_en,
        )

    async def cotizar(self, monto_bob: Decimal, momento: Optional[datetime] = None) -> CotizacionMonedaDTO:
        if monto_bob < Decimal("0"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="monto_bob no puede ser negativo",
            )
        tasa = await self.obtener_tasa_vigente(momento)
        # Cálculo exacto con Decimal y ROUND_HALF_UP a centavos (CU12)
        usd_decimal = (monto_bob / tasa.tasa_bob_por_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        centavos = int(usd_decimal * 100)

        return CotizacionMonedaDTO(
            monto_bob=monto_bob,
            monto_usd=usd_decimal,
            centavos_usd=centavos,
            tasa_id=tasa.id,
            tasa_bob_por_usd=tasa.tasa_bob_por_usd,
            version_tasa=tasa.version,
            fecha_cotizacion=utcnow(),
        )

    async def listar_historial(self) -> List[TasaCambioDTO]:
        q = select(TasaCambio).order_by(TasaCambio.version.desc())
        res = await self.db.execute(q)
        tasas = res.scalars().all()
        return [
            TasaCambioDTO(
                id=t.id,
                version=t.version,
                tasa_bob_por_usd=t.tasa_bob_por_usd,
                vigente_desde=t.vigente_desde,
                vigente_hasta=t.vigente_hasta,
                motivo=t.motivo,
                creada_por=t.creada_por,
                creada_en=t.creada_en,
            )
            for t in tasas
        ]
