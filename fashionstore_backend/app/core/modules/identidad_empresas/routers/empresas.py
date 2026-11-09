"""Router Empresas — CU01: Registrar empresa contratante y consulta."""
import uuid
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_actual, get_usuario_opcional, require_administrador_plataforma
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.schemas import (
    EmpresaCrearDTO,
    EmpresaRespuestaDTO,
    EmpresaDetalleDTO,
    EmpresaPublicaDTO,
)
from backend.app.core.modules.identidad_empresas.services.empresa_service import EmpresaService

router = APIRouter()


@router.post(
    "",
    response_model=EmpresaRespuestaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar empresa contratante (CU01)",
    description="Alta atómica de empresa y administrador inicial realizada por un Administrador de Plataforma.",
)
async def registrarEmpresa(
    datos_empresa: EmpresaCrearDTO,
    idempotency_key: uuid.UUID = Header(..., alias="Idempotency-Key", description="Clave de idempotencia obligatoria UUID v4"),
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_administrador_plataforma()),
) -> EmpresaRespuestaDTO:
    servicio = EmpresaService(db)
    return await servicio.registrarEmpresa(
        datos_empresa,
        idempotency_key=idempotency_key,
        usuario_autenticado=_admin,
    )


@router.get(
    "/{empresa_id}",
    response_model=EmpresaDetalleDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar detalle de empresa (CU01)",
    description="Devuelve el detalle de la empresa. Aísla el acceso entre empresas.",
)
async def obtenerEmpresa(
    empresa_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_actual),
) -> EmpresaDetalleDTO:
    # Si el usuario es de empresa, sólo puede consultar la suya propia
    if usuario.empresa_id is not None and usuario.empresa_id != empresa_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene autorización para consultar otra empresa contratante",
        )
    servicio = EmpresaService(db)
    return await servicio.obtenerPorId(empresa_id)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Listar empresas (CU01)",
    description="Lista empresas registradas. Plataforma lista todas; consulta abierta solo lista activas.",
)
async def listarEmpresas(
    solo_activas: bool = False,
    db: AsyncSession = Depends(get_db),
    usuario_opcional: Optional[Usuario] = Depends(get_usuario_opcional),
) -> List[Any]:
    servicio = EmpresaService(db)
    es_admin_plat = False
    if usuario_opcional:
        rol = (usuario_opcional.rol.nombre if usuario_opcional.rol else "").upper()
        es_admin_plat = (
            rol in ["SUPERADMIN", "ADMINISTRADOR_SISTEMA", "ADMINISTRADOR_PLATAFORMA", "ADMINISTRADOR"]
            and usuario_opcional.empresa_id is None
        )

    if es_admin_plat:
        return await servicio.listar(solo_activas=solo_activas)
    else:
        # Consulta pública o no plataforma: solo empresas activas sin revelar datos administrativos
        return await servicio.listarPublicas()
