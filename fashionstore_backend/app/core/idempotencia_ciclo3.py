"""Idempotencia genérica Ciclo 3 sobre comercial.registros_idempotencia.

Ámbito aislado por (clave, usuario, tipo de recurso, operación concreta,
payload canónico): una respuesta idempotente nunca atraviesa propietarios.
Ventas/pagos conservan su propia clave_idempotencia (Ciclo 2) y verifican
propiedad en servicio. Misma clave + mismo usuario + misma operación +
mismo hash -> respuesta original; distinta -> 409. Otro usuario con la misma
clave obtiene su propio ámbito (nunca datos ajenos). Respuestas expiradas no
se reutilizan. Concurrencia sobre la misma clave no duplica recursos.
"""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.modules.ventas_pagos.models import RegistroIdempotencia


def hash_payload(payload: Any) -> str:
    canonico = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


async def _buscar(
    db: AsyncSession,
    clave: uuid.UUID,
    usuario_id: uuid.UUID,
    recurso_tipo: str,
    operacion: str,
) -> Optional[RegistroIdempotencia]:
    resultado = await db.execute(
        select(RegistroIdempotencia).where(
            RegistroIdempotencia.clave == clave,
            RegistroIdempotencia.usuario_id == usuario_id,
            RegistroIdempotencia.recurso_tipo == recurso_tipo,
            RegistroIdempotencia.operacion == operacion,
        )
    )
    return resultado.scalars().first()


def _expirado(registro: RegistroIdempotencia) -> bool:
    expira = registro.expira_en
    if expira is None:
        return False
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    return expira <= _ahora()


async def reclamar(
    db: AsyncSession,
    clave: uuid.UUID,
    hash_solicitud: str,
    recurso_tipo: str,
    operacion: str = "MUTAR",
    usuario_id: Optional[uuid.UUID] = None,
    ttl_horas: int = 24,
) -> Optional[RegistroIdempotencia]:
    """Reserva la clave en su ámbito o devuelve el registro previo vigente.

    - Sin registro en el ámbito -> crea marcador con respuesta {} y retorna
      None (el servicio continúa y luego guarda con `guardar_respuesta`).
    - Mismo ámbito + mismo hash vigente -> retorna el registro (reintento).
    - Mismo ámbito + distinto hash -> 409.
    - Registro expirado -> se elimina y se trata como primer intento.
    - Carrera sobre la misma clave/ámbito -> un solo marcador gana; el otro
      re-lee y reutiliza sin duplicar recursos.
    - Otro usuario nunca ve este ámbito (búsqueda siempre filtrada por
      usuario_id); la PK compuesta permite reutilizar el mismo UUID externo.
    """
    if usuario_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ámbito idempotente exige usuario autenticado",
        )
    operacion = (operacion or "MUTAR").upper()
    recurso_tipo = (recurso_tipo or "GENERICO").upper()
    existente = await _buscar(db, clave, usuario_id, recurso_tipo, operacion)
    if existente is not None:
        if _expirado(existente):
            await db.delete(existente)
            await db.flush()
        elif existente.hash_solicitud != hash_solicitud:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "codigo": "IDEMPOTENCIA_CONFLICTO",
                    "mensaje": "Idempotency-Key ya usada con otra solicitud",
                },
            )
        else:
            return existente
    marcador = RegistroIdempotencia(
        clave=clave,
        usuario_id=usuario_id,
        recurso_tipo=recurso_tipo,
        operacion=operacion,
        hash_solicitud=hash_solicitud,
        respuesta={},
        expira_en=_ahora() + timedelta(hours=ttl_horas),
    )
    db.add(marcador)
    try:
        await db.flush()
        return None
    except IntegrityError:
        # Carrera: otro flujo ganó el marcador en el mismo ámbito. La
        # sesión queda en estado fallido tras el flush: revertir solo lo
        # pendiente (el marcador es la primera escritura de la operación)
        # y re-leer al ganador sin duplicar recursos.
        await db.rollback()
        ganador = await _buscar(db, clave, usuario_id, recurso_tipo, operacion)
        if ganador is None:
            raise
        if _expirado(ganador):
            await db.delete(ganador)
            await db.flush()
            segundo = RegistroIdempotencia(
                clave=clave,
                usuario_id=usuario_id,
                recurso_tipo=recurso_tipo,
                operacion=operacion,
                hash_solicitud=hash_solicitud,
                respuesta={},
                expira_en=_ahora() + timedelta(hours=ttl_horas),
            )
            db.add(segundo)
            await db.flush()
            return None
        if ganador.hash_solicitud != hash_solicitud:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "codigo": "IDEMPOTENCIA_CONFLICTO",
                    "mensaje": "Idempotency-Key ya usada con otra solicitud",
                },
            )
        if not ganador.respuesta:
            import asyncio
            for _ in range(40):
                await asyncio.sleep(0.05)
                db.expire_all()
                ganador = await _buscar(db, clave, usuario_id, recurso_tipo, operacion)
                if ganador and ganador.respuesta:
                    break
        return ganador


async def guardar_respuesta(
    db: AsyncSession,
    clave: uuid.UUID,
    respuesta: dict,
    recurso_id: Optional[uuid.UUID] = None,
    *,
    usuario_id: uuid.UUID,
    recurso_tipo: str,
    operacion: str,
) -> None:
    """Guarda la respuesta en el ámbito exacto (usuario, recurso, operación).

    El ámbito es obligatorio: falla explícitamente si un llamador lo omite.
    Nunca busca únicamente por `clave` ni selecciona entre ámbitos distintos:
    una respuesta solo puede guardarse/recuperarse dentro de su propio ámbito.
    """
    if usuario_id is None or recurso_tipo is None or operacion is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ámbito idempotente exige usuario, recurso y operación",
        )
    registro = await _buscar(
        db, clave, usuario_id, recurso_tipo.upper(), operacion.upper()
    )
    if registro is not None:
        if _expirado(registro):
            return
        registro.respuesta = respuesta
        if recurso_id is not None:
            registro.recurso_id = recurso_id
        await db.flush()
