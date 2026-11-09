import uuid
from typing import List
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import require_roles, get_usuario_actual
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.inventario.schemas import LoteRecepcionCrearDTO, LoteRecepcionDTO
from backend.app.core.modules.inventario.services.recepcion_service import RecepcionService

router = APIRouter()

@router.post(
    "",
    response_model=LoteRecepcionDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar lote de recepción con costos (CU04 / RF06,RN-09)",
    description="Presentación registrarLoteRecepcion() -> Controller RecepcionService.registrarLote() -> LoteRepository.crear(), VarianteRepository.actualizarCostos(), InventarioRepository.ingresar(), MovimientoRepository.registrar(RECEPCION_PROVEEDOR). Transacción única con recálculo promedio ponderado."
)
async def registrarLoteRecepcion(
    datos: LoteRecepcionCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_roles("ADMINISTRADOR"))
) -> LoteRecepcionDTO:
    servicio = RecepcionService(db)
    return await servicio.registrarLote(datos)

@router.get(
    "/{lote_id}",
    response_model=LoteRecepcionDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener detalle de lote de recepción (CU04)"
)
async def obtenerLotePorId(
    lote_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(get_usuario_actual)
) -> LoteRecepcionDTO:
    servicio = RecepcionService(db)
    return await servicio.obtenerPorId(lote_id)

@router.get(
    "",
    response_model=List[LoteRecepcionDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar lotes de recepción (CU04)"
)
async def listarLotes(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(get_usuario_actual)
) -> List[LoteRecepcionDTO]:
    servicio = RecepcionService(db)
    return await servicio.listar(limit=limit, offset=offset)
