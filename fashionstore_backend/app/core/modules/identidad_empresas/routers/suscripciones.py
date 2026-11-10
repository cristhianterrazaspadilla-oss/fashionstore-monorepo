"""Router de Suscripciones y Planes — CU02: Administrar suscripción de empresa."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import (
    get_usuario_actual,
    require_administrador_plataforma,
)
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.schemas import (
    AsignarSuscripcionDTO,
    SuscripcionRespuestaDTO,
    PlanDetalleDTO,
)
from backend.app.core.modules.identidad_empresas.services.suscripcion_service import SuscripcionService

router = APIRouter()


@router.get(
    "/planes",
    response_model=List[PlanDetalleDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar planes activos del catálogo de la plataforma (CU02)",
)
async def listar_planes(
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(get_usuario_actual),
) -> List[PlanDetalleDTO]:
    servicio = SuscripcionService(db)
    return await servicio.listar_planes()


@router.post(
    "/empresas/{empresa_id}/suscripciones",
    response_model=SuscripcionRespuestaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Asignar o renovar suscripción de empresa (CU02)",
    description="Solo el Administrador de Plataforma puede asignar o modificar suscripciones.",
)
async def asignar_suscripcion(
    empresa_id: uuid.UUID,
    dto: AsignarSuscripcionDTO,
    idempotency_key: uuid.UUID = Header(..., alias="Idempotency-Key", description="Clave de idempotencia obligatoria"),
    db: AsyncSession = Depends(get_db),
    admin_plataforma: Usuario = Depends(require_administrador_plataforma()),
) -> SuscripcionRespuestaDTO:
    servicio = SuscripcionService(db)
    return await servicio.asignar_o_renovar(
        empresa_id=empresa_id,
        dto=dto,
        admin_plataforma=admin_plataforma,
        idempotency_key=idempotency_key,
    )


@router.get(
    "/empresas/mi-plan",
    response_model=SuscripcionRespuestaDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar suscripción y capacidades de la empresa actual (CU02)",
)
async def consultar_mi_plan(
    empresa_id: Optional[uuid.UUID] = Query(None, description="Requerido si el usuario es administrador de plataforma"),
    db: AsyncSession = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual),
) -> SuscripcionRespuestaDTO:
    if usuario_actual.empresa_id is None:
        await require_administrador_plataforma()(usuario_actual)
    elif empresa_id is not None and empresa_id != usuario_actual.empresa_id:
        raise HTTPException(status_code=403, detail="No autorizado para consultar el plan de otra empresa")
    eid = usuario_actual.empresa_id or empresa_id
    if not eid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe especificar empresa_id si opera con usuario global de plataforma",
        )
    # Si el usuario pertenece a una empresa, no puede consultar el plan de otra empresa
    if usuario_actual.empresa_id is not None and usuario_actual.empresa_id != eid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para consultar el plan de otra empresa",
        )
    servicio = SuscripcionService(db)
    return await servicio.consultar_plan_empresa(eid)


@router.get(
    "/empresas/{empresa_id}/suscripciones",
    response_model=List[SuscripcionRespuestaDTO],
    status_code=status.HTTP_200_OK,
    summary="Consultar historial de suscripciones de una empresa (CU02)",
)
async def listar_historial_suscripciones(
    empresa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario_actual: Usuario = Depends(get_usuario_actual),
) -> List[SuscripcionRespuestaDTO]:
    if usuario_actual.empresa_id is None:
        await require_administrador_plataforma()(usuario_actual)
    if usuario_actual.empresa_id is not None and usuario_actual.empresa_id != empresa_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para consultar el historial de otra empresa",
        )
    servicio = SuscripcionService(db)
    return await servicio.listar_historial(empresa_id)
