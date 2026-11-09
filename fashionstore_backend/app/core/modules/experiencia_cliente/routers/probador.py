"""Router Probador Decart — CU17 (RF13)."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual
from backend.app.core.idempotencia import validar_clave_idempotencia
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.experiencia_cliente.schemas import (
    AutorizacionCrearDTO,
    AutorizacionDTO,
    PruebaVirtualDTO,
)
from backend.app.core.modules.experiencia_cliente.services.probador_service import ProbadorService
from backend.app.core.errores import (
    E401, E403, E404, E409_IDEM, E409_NEGOCIO, E422, E429, E502, E503_DECART,
)

router = APIRouter()


@router.get(
    "/variantes/{variante_id}/prueba-virtual", response_model=PruebaVirtualDTO,
    summary="Compatibilidad y recurso de prueba virtual (CU17)",
    description="Cliente autenticado. Valida variante activa y compatible (solo prendas superiores), "
    "imagen HTTPS de origen permitido DECART_ORIGENES_PERMITIDOS (JPEG/PNG/WebP real, 512×512, "
    "sin destinos internos ni redirecciones inseguras) y prompt controlado por catálogo. "
    "Variante incompatible 409; origen no permitido 422. Nunca garantiza talla.",
    responses={401: E401, 403: E403, 404: E404, 409: E409_NEGOCIO, 422: E422, 503: E503_DECART},
)
async def recursoPruebaVirtual(
    variante_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> PruebaVirtualDTO:
    return await ProbadorService(db).recursoPrueba(usuario, variante_id)


@router.post(
    "/probador/autorizaciones", response_model=AutorizacionDTO, status_code=status.HTTP_201_CREATED,
    summary="Autorizar sesión Decart Lucy 2.5 (CU17)",
    description="Token cliente de 60 s (expires_at real del proveedor), allowedModels=['lucy-2.5'], "
    "maxSessionDuration=120, sin allowedOrigins (Android). Requiere consentimiento 'decart-v1', "
    "Idempotency-Key con ámbito por usuario (nunca devuelve a otro usuario un token almacenado; "
    "mismo payload devuelve el vigente, distinto 409) y respeta rate limit (429). Sin clave o "
    "deshabilitado responde 503 DECART_DESHABILITADO; sin allowlist 503 DECART_ORIGENES_NO_CONFIGURADOS; "
    "rechazo del proveedor 502. Nunca devuelve la API key permanente ni registra token, Base64, "
    "video, frames, rostro, SDP ni contenido audiovisual.",
    responses={
        401: E401, 403: E403, 404: E404, 409: E409_IDEM, 422: E422,
        429: E429, 502: E502, 503: E503_DECART,
    },
)
async def crearAutorizacion(
    datos: AutorizacionCrearDTO,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
    clave_idempotencia: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> AutorizacionDTO:
    clave = validar_clave_idempotencia(clave_idempotencia)
    dto, _ = await ProbadorService(db).autorizar(usuario, datos, clave)
    return dto
