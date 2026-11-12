"""Router IA Analítica — CU24 (reportes interpretados tipados)."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.errores import E400, E401, E403, E404, E422
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.analitica.schemas import (
    DecisionPedirDTO,
    DecisionRespuestaDTO,
    ReportePedirDTO,
    ReporteRespuestaDTO,
    ReporteInterpretadoPeticionDTO,
    ReporteInterpretadoResultadoDTO,
)
from backend.app.core.modules.analitica.services.ia_analitica_service import IAAnaliticaService

router = APIRouter()


@router.post(
    "/reportes-interpretados",
    response_model=ReporteInterpretadoResultadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Reporte tipado interpretado (CU24)",
    description="Solo Administrador empresarial con capacidad de reportes generativos. Interpreta consultas a 5 tipos permitidos, "
    "ejecuta consultas tipadas parametrizadas (nunca SQL generado por IA) y persiste snapshot.",
    responses={400: E400, 401: E401, 403: E403, 404: E404, 422: E422},
)
async def solicitarReporteInterpretado(
    datos: ReporteInterpretadoPeticionDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReporteInterpretadoResultadoDTO:
    return await IAAnaliticaService(db).generarReporteInterpretado(usuario, datos)


# Compatibilidad legada
@router.post(
    "/reportes",
    response_model=ReporteRespuestaDTO,
    summary="Reporte generativo por voz/texto (CU21 legado)",
    responses={401: E401, 403: E403, 422: E422, 404: E404},
)
async def solicitarReporte(
    datos: ReportePedirDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> ReporteRespuestaDTO:
    return await IAAnaliticaService(db).generarReporte(usuario, datos.consulta)


@router.post(
    "/decisiones-inventario",
    response_model=DecisionRespuestaDTO,
    summary="Asistente IA de decisiones de inventario (CU25 legado)",
    responses={401: E401, 403: E403, 422: E422},
)
async def sugerirDecisiones(
    datos: DecisionPedirDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> DecisionRespuestaDTO:
    return await IAAnaliticaService(db).decisionesInventario(
        usuario, dias_ventana=datos.dias_ventana, umbral_rotacion=datos.umbral_rotacion
    )
