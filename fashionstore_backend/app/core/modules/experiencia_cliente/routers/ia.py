"""Router IA Experiencia Cliente — CU17/CU18/CU20 (RF25, RF07) + navegación sanitizada."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.errores import E401, E403, E404, E422
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.experiencia_cliente.schemas import (
    BusquedaRespuestaDTO,
    BusquedaVozDTO,
    NavegacionCrearDTO,
    RecomendacionPedirDTO,
    RecomendacionRespuestaDTO,
)
from backend.app.core.modules.experiencia_cliente.services.ia_service import IAService
from backend.app.core.modules.analitica.routers.ia_analitica import (
    solicitarReporte,
    sugerirDecisiones,
)

router = APIRouter()


@router.post(
    "/navegacion", status_code=status.HTTP_201_CREATED, response_model=dict,
    summary="Registrar navegación/uso sanitizado (CU17/CU18)",
    description="Eventos cerrados (VISTA, PRUEBA_VIRTUAL, CARRITO, COMPRA, BUSQUEDA). "
    "Nunca recibe ni guarda token, Base64, video, frames, rostro ni SDP.",
    responses={401: E401, 403: E403, 422: E422},
)
async def registrarNavegacion(
    datos: NavegacionCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
):
    return await IAService(db).registrarNavegacion(
        usuario, datos.evento, datos.variante_id, datos.producto_id
    )


@router.post(
    "/recomendaciones", response_model=RecomendacionRespuestaDTO,
    summary="Sugerencias IA para el cliente (CU18)",
    description="Motor determinista primero: preferencias, navegación, temporada y disponibilidad. "
    "Solo productos reales y disponibles; sin IDs, stock ni atributos inventados. Importes y "
    "filtros con Decimal. Auditoría en solicitudes_ia.",
    responses={401: E401, 403: E403, 422: E422},
)
async def pedirSugerencias(
    datos: RecomendacionPedirDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> RecomendacionRespuestaDTO:
    return await IAService(db).recomendar(
        usuario, limite=datos.limite, categoria=datos.categoria, talla=datos.talla
    )


@router.post(
    "/busqueda", response_model=BusquedaRespuestaDTO,
    summary="Buscar prendas por texto/voz (CU20)",
    description="El cliente dicta o escribe; el backend interpreta a un DTO cerrado de filtros "
    "(categoría, talla, color, temporada, precio con Decimal). Gemini detrás de interfaz "
    "reemplazable; sin clave rige el fallback determinista. Caída a texto simple si no interpreta.",
    responses={401: E401, 403: E403, 422: E422},
)
async def buscarPorVoz(
    datos: BusquedaVozDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> BusquedaRespuestaDTO:
    return await IAService(db).interpretarBusqueda(usuario, datos.texto)


__all__ = [
    "router",
    "registrarNavegacion",
    "pedirSugerencias",
    "buscarPorVoz",
    "solicitarReporte",
    "sugerirDecisiones",
]
