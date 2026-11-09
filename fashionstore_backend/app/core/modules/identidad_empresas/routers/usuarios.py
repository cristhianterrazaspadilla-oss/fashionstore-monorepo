"""Router Usuarios — CU14: Gestionar usuarios y roles de la empresa."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import require_roles
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.schemas import (
    UsuarioCrearDTO,
    UsuarioActualizarDTO,
    UsuarioListadoDTO,
    AsignarRolDTO,
    ActualizarEstadoDTO,
)
from backend.app.core.modules.identidad_empresas.services.usuario_service import UsuarioService

router = APIRouter()

ROLES_ADMIN = ["ADMINISTRADOR", "ADMINISTRADOR_SISTEMA", "SUPERADMIN"]


@router.post(
    "",
    response_model=UsuarioListadoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario interno con rol único (CU14)",
    description="Permite al Administrador registrar un usuario acotado a su empresa, asignándole exactamente un rol.",
)
async def crearUsuario(
    datos_usuario: UsuarioCrearDTO,
    db: AsyncSession = Depends(get_db),
    admin: Usuario = Depends(require_roles(*ROLES_ADMIN)),
) -> UsuarioListadoDTO:
    servicio = UsuarioService(db)
    return await servicio.crear(datos_usuario, admin=admin)


@router.get(
    "",
    response_model=List[UsuarioListadoDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar usuarios de la empresa (CU14)",
    description="Lista los usuarios propios de la empresa autenticada con filtros opcionales de rol y estado.",
)
async def gestionarUsuarios(
    rol_id: Optional[uuid.UUID] = Query(None, description="Filtrar por rol"),
    estado: Optional[str] = Query(None, description="Filtrar por estado ACTIVO o INACTIVO"),
    db: AsyncSession = Depends(get_db),
    admin: Usuario = Depends(require_roles(*ROLES_ADMIN)),
) -> List[UsuarioListadoDTO]:
    servicio = UsuarioService(db)
    return await servicio.listar(admin=admin, rol_id=rol_id, estado=estado)


@router.patch(
    "/{usuario_id}",
    response_model=UsuarioListadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar usuario de la empresa (CU14)",
    description="Edita datos de usuario, rol o estado. Impide desactivar al último administrador activo.",
)
async def actualizarUsuario(
    usuario_id: uuid.UUID,
    datos: UsuarioActualizarDTO,
    db: AsyncSession = Depends(get_db),
    admin: Usuario = Depends(require_roles(*ROLES_ADMIN)),
) -> UsuarioListadoDTO:
    servicio = UsuarioService(db)
    return await servicio.actualizar(usuario_id, datos, admin=admin)


@router.patch(
    "/{usuario_id}/rol",
    response_model=UsuarioListadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Asignar o cambiar rol a un usuario (CU14 - compatibilidad)",
    description="Modifica el rol asignado al usuario respetando la regla de rol único y último admin activo.",
)
async def asignarRol(
    usuario_id: uuid.UUID,
    datos_rol: AsignarRolDTO,
    db: AsyncSession = Depends(get_db),
    admin: Usuario = Depends(require_roles(*ROLES_ADMIN)),
) -> UsuarioListadoDTO:
    servicio = UsuarioService(db)
    return await servicio.asignarRol(usuario_id, datos_rol.rol_id, admin=admin, revision=datos_rol.revision)


@router.patch(
    "/{usuario_id}/estado",
    response_model=UsuarioListadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar estado de usuario (CU14 - compatibilidad)",
    description="Cambia el estado del usuario entre ACTIVO e INACTIVO.",
)
async def actualizarEstadoUsuario(
    usuario_id: uuid.UUID,
    datos_estado: ActualizarEstadoDTO,
    db: AsyncSession = Depends(get_db),
    admin: Usuario = Depends(require_roles(*ROLES_ADMIN)),
) -> UsuarioListadoDTO:
    servicio = UsuarioService(db)
    return await servicio.actualizarEstado(usuario_id, datos_estado.estado, admin=admin, revision=datos_estado.revision)


@router.patch(
    "/{usuario_id}/desactivar",
    response_model=UsuarioListadoDTO,
    status_code=status.HTTP_200_OK,
    summary="Desactivar usuario de la empresa (CU14 - compatibilidad)",
    description="Pasa el estado a INACTIVO impidiendo el login; valida que no sea el último admin.",
)
async def desactivarUsuario(
    usuario_id: uuid.UUID,
    revision: Optional[int] = Query(None, description="Revisión opcional para adaptador de compatibilidad"),
    db: AsyncSession = Depends(get_db),
    admin: Usuario = Depends(require_roles(*ROLES_ADMIN)),
) -> UsuarioListadoDTO:
    servicio = UsuarioService(db)
    return await servicio.desactivar(usuario_id, admin=admin, revision=revision)
