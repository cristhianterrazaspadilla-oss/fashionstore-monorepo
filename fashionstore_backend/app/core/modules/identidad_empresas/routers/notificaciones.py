"""Router de Notificaciones, Dispositivos y Bandeja (E2 Avisos Push)."""
from __future__ import annotations

import json
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.services.notificacion_service import (
    DispositivoDTO,
    NotificacionDTO,
    NotificacionService,
    RegistroDispositivoDTO,
)

router = APIRouter()


class WebPushConfigDTO(BaseModel):
    public_key: str = Field(..., description="Clave pública VAPID en base64url para PushManager.subscribe")


class WebPushKeysDTO(BaseModel):
    p256dh: str = Field(..., description="Clave pública P-256 del cliente en base64url")
    auth: str = Field(..., description="Secret de autenticación en base64url")


class WebPushSubscripcionDTO(BaseModel):
    endpoint: str = Field(..., description="Endpoint HTTPS de recepción Web Push")
    keys: WebPushKeysDTO
    dispositivo_id: Optional[uuid.UUID] = Field(None, description="UUID local de dispositivo si ya existe")


@router.get(
    "/web-push/config",
    response_model=WebPushConfigDTO,
    summary="Obtener clave pública VAPID para suscripción Web Push",
)
async def obtener_config_web_push():
    return WebPushConfigDTO(public_key=NotificacionService.obtener_clave_publica_vapid())


@router.post(
    "/web-push/subscripcion",
    response_model=DispositivoDTO,
    status_code=status.HTTP_200_OK,
    summary="Registrar o actualizar suscripción Web Push desde la PWA",
)
async def registrar_suscripcion_web_push(
    dto: WebPushSubscripcionDTO,
    usuario: Usuario = Depends(get_usuario_actual),
    db: AsyncSession = Depends(get_db),
):
    srv = NotificacionService(db)
    disp_id = dto.dispositivo_id or uuid.uuid4()
    push_token = json.dumps({
        "endpoint": dto.endpoint,
        "keys": {
            "p256dh": dto.keys.p256dh,
            "auth": dto.keys.auth,
        },
    })
    reg = RegistroDispositivoDTO(
        dispositivo_id=disp_id,
        canal="PWA",
        push_token=push_token,
    )
    res = await srv.registrar_dispositivo(usuario, reg)
    await db.commit()
    return res


@router.post(
    "/dispositivos",
    response_model=DispositivoDTO,
    status_code=status.HTTP_200_OK,
    summary="Registrar o actualizar token de dispositivo (PWA o Flutter)",
)
async def registrar_dispositivo(
    dto: RegistroDispositivoDTO,
    usuario: Usuario = Depends(get_usuario_actual),
    db: AsyncSession = Depends(get_db),
):
    srv = NotificacionService(db)
    res = await srv.registrar_dispositivo(usuario, dto)
    await db.commit()
    return res


@router.delete(
    "/dispositivos/{dispositivo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revocar registro de dispositivo",
)
async def revocar_dispositivo(
    dispositivo_id: uuid.UUID,
    usuario: Usuario = Depends(get_usuario_actual),
    db: AsyncSession = Depends(get_db),
):
    srv = NotificacionService(db)
    await srv.revocar_dispositivo(usuario, dispositivo_id)
    await db.commit()
    return None


@router.get(
    "/bandeja",
    response_model=List[NotificacionDTO],
    summary="Consultar bandeja de notificaciones propia",
)
async def consultar_bandeja(
    limite: int = 50,
    usuario: Usuario = Depends(get_usuario_actual),
    db: AsyncSession = Depends(get_db),
):
    srv = NotificacionService(db)
    return await srv.listar_bandeja(usuario, limite=limite)


@router.patch(
    "/bandeja/{notificacion_id}/leer",
    response_model=NotificacionDTO,
    summary="Marcar notificación como leída",
)
async def marcar_notificacion_leida(
    notificacion_id: uuid.UUID,
    usuario: Usuario = Depends(get_usuario_actual),
    db: AsyncSession = Depends(get_db),
):
    srv = NotificacionService(db)
    res = await srv.marcar_leida(usuario, notificacion_id)
    await db.commit()
    return res


@router.post(
    "/procesar-outbox",
    status_code=status.HTTP_200_OK,
    summary="Procesar eventos pendientes de outbox (Worker E2)",
)
async def procesar_eventos_outbox(
    limite: int = 20,
    usuario: Usuario = Depends(get_usuario_actual),
    db: AsyncSession = Depends(get_db),
):
    srv = NotificacionService(db)
    res = await srv.procesar_outbox(empresa_id=usuario.empresa_id, limite=limite)
    await db.commit()
    return res
