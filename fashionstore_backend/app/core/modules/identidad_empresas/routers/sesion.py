from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.modules.identidad_empresas.schemas import LoginDTO, TokenRespuestaDTO
from backend.app.core.modules.identidad_empresas.services.autenticacion_service import AutenticacionService

router = APIRouter()


@router.post(
    "",
    response_model=TokenRespuestaDTO,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión (CU01 / RF01)",
    description="Autentica las credenciales del usuario y retorna el token JWT junto a su información de perfil y rol."
)
async def iniciarSesion(
    credenciales: LoginDTO,
    db: AsyncSession = Depends(get_db)
) -> TokenRespuestaDTO:
    servicio = AutenticacionService(db)
    return await servicio.iniciarSesion(credenciales)
