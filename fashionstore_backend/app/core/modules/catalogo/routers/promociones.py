"""Presentación Promociones — CU22 (RF23)."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.catalogo.schemas import (
    AsociarVariantesDTO, PromocionActualizarDTO, PromocionCrearDTO,
    PromocionDTO, PromocionListaDTO,
)
from backend.app.core.modules.catalogo.services.promocion_service import PromocionService
from backend.app.core.errores import E400, E401, E403, E404, E409_NEGOCIO

router = APIRouter()


@router.post(
    "", response_model=PromocionDTO, status_code=status.HTTP_201_CREATED,
    summary="Crear promoción (CU22)",
    description="Solo ADMINISTRADOR. Tipo PORCENTAJE (0-100) o MONTO_FIJO, vigencia coherente en UTC, "
    "código único. No acumulables: el checkout aplica el mayor descuento con desempate por ID.",
    responses={400: E400, 401: E401, 403: E403, 409: E409_NEGOCIO, 422: E400},
)
async def crearPromocion(
    datos: PromocionCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PromocionDTO:
    return await PromocionService(db).crear(usuario, datos)


@router.get(
    "", response_model=PromocionListaDTO, summary="Listar promociones (CU22)",
    description="ADMINISTRADOR o ENCARGADO. Paginado con total/limit/offset.",
)
async def listarPromociones(
    solo_activas: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return await PromocionService(db).listar(usuario, solo_activas=solo_activas, limit=limit, offset=offset)


@router.get(
    "/{promocion_id}", response_model=PromocionDTO, summary="Obtener promoción (CU22)",
)
async def obtenerPromocion(
    promocion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PromocionDTO:
    return await PromocionService(db).obtener(usuario, promocion_id)


@router.patch(
    "/{promocion_id}", response_model=PromocionDTO, summary="Actualizar promoción (CU22)",
)
async def actualizarPromocion(
    promocion_id: uuid.UUID,
    datos: PromocionActualizarDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PromocionDTO:
    return await PromocionService(db).actualizar(usuario, promocion_id, datos)


@router.delete(
    "/{promocion_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar promoción (CU22)",
)
async def eliminarPromocion(
    promocion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    await PromocionService(db).eliminar(usuario, promocion_id)
    return None


@router.post(
    "/{promocion_id}/variantes", response_model=PromocionDTO, summary="Asociar variantes (CU22)",
)
async def asociarVariantes(
    promocion_id: uuid.UUID,
    datos: AsociarVariantesDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PromocionDTO:
    return await PromocionService(db).asociar(usuario, promocion_id, datos)


@router.delete(
    "/{promocion_id}/variantes/{variante_id}", response_model=PromocionDTO,
    summary="Desasociar variante (CU22)",
)
async def desasociarVariante(
    promocion_id: uuid.UUID,
    variante_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PromocionDTO:
    return await PromocionService(db).desasociar(usuario, promocion_id, variante_id)
