"""Idempotencia Ciclo 2 (Entrega 1).

Protocolo (plan-implementacion-ciclo-2-backend.md):
  - Header `Idempotency-Key` obligatorio en: crear reserva, registrar venta
    presencial, registrar pago/adelanto, registrar devolucion, registrar merma.
  - Misma clave + mismo hash de payload  -> devolver el recurso original.
  - Misma clave + payload distinto        -> 409 CONFLICT.
  - Transicion ya aplicada               -> estado actual sin efectos.
  - Transicion incompatible              -> 409 CONFLICT.

Toda mutacion de inventario corre en una unica transaccion de servicio;
los repositorios hacen flush y solo el servicio confirma o revierte.
"""
import hashlib
import json
import uuid
from typing import Any, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


def hash_payload(payload: Any) -> str:
    """Hash SHA-256 canonico (JSON ordenado) del payload de la solicitud."""
    canonico = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def validar_clave_idempotencia(clave: Optional[str]) -> uuid.UUID:
    """Valida el header Idempotency-Key obligatorio. 400 si falta o es invalido."""
    if not clave:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header Idempotency-Key obligatorio",
        )
    try:
        return uuid.UUID(str(clave))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key invalido: debe ser UUID",
        )


async def buscar_por_clave(db: AsyncSession, modelo: Any, clave: uuid.UUID) -> Optional[Any]:
    """Devuelve el recurso ya creado con esa clave, o None si es primer intento."""
    resultado = await db.execute(select(modelo).where(modelo.clave_idempotencia == clave))
    return resultado.scalars().first()


async def resolver_idempotencia(
    db: AsyncSession,
    modelo: Any,
    clave: uuid.UUID,
    hash_solicitud: str,
) -> Optional[Any]:
    """Aplica el protocolo de reintento:

    - Sin registro previo -> None (el servicio continua y crea).
    - Mismo hash         -> recurso original (reintento seguro, sin efectos).
    - Distinto hash      -> 409 (clave reutilizada con otro payload).
    """
    previo = await buscar_por_clave(db, modelo, clave)
    if previo is None:
        return None
    if previo.hash_solicitud != hash_solicitud:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key ya usada con otra solicitud",
        )
    return previo


def es_conflicto_integridad_por_clave(error: IntegrityError) -> bool:
    """True si el IntegrityError corresponde a clave_idempotencia duplicada."""
    mensaje = str(getattr(error, "orig", error)).lower()
    return "clave_idempotencia" in mensaje
