import uuid
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.seguridad import decodificar_token
from backend.app.core.modules.identidad_empresas.models import Usuario

security = HTTPBearer(auto_error=False)

async def get_usuario_actual(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Usuario:
    from backend.app.main import app
    import inspect
    if get_usuario_actual in app.dependency_overrides:
        override = app.dependency_overrides[get_usuario_actual]
        res = override()
        if inspect.isawaitable(res):
            res = await res
        return res
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no proporcionado",
            headers={"WWW-Authenticate": "Bearer"}
        )
    token = credentials.credentials
    try:
        payload = decodificar_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
                headers={"WWW-Authenticate": "Bearer"}
            )
        user_id = uuid.UUID(user_id_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"}
        )
    query = (
        select(Usuario)
        .options(selectinload(Usuario.rol), selectinload(Usuario.cliente), selectinload(Usuario.empleado))
        .where(Usuario.id == user_id)
    )
    result = await db.execute(query)
    usuario = result.scalars().first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario del token no existe")
    if usuario.estado != "ACTIVO":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta inactiva")
    return usuario

def require_roles(*roles_permitidos: str):
    roles_upper = [r.upper() for r in roles_permitidos]
    async def _check(usuario: Usuario = Depends(get_usuario_actual)) -> Usuario:
        rol_actual = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol_actual not in roles_upper:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: se requiere uno de los roles {roles_upper} (tu rol: {rol_actual})"
            )
        return usuario
    return _check

def require_rol_empresarial(*roles_permitidos: str):
    """Exige empresa en la sesión antes de validar el rol.

    Un usuario sin empresa no debe recibir datos de negocio aunque su rol sea
    administrativo. Se responde 400 (falta de contexto) para no confundir la
    ausencia de empresa con un problema de permisos.
    """
    verificar_rol = require_roles(*roles_permitidos)

    async def _check(usuario: Usuario = Depends(get_usuario_actual)) -> Usuario:
        if usuario.empresa_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )
        return await verificar_rol(usuario)

    return _check


def require_administrador_plataforma():
    """Exige autoridad de plataforma: rol de plataforma Y ámbito global (empresa_id nulo).
    Impide que un usuario empresarial con roles como ADMINISTRADOR_SISTEMA o ADMINISTRADOR opere sobre plataforma."""
    async def _check(usuario: Usuario = Depends(get_usuario_actual)) -> Usuario:
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        es_plataforma = (
            rol in ["SUPERADMIN", "ADMINISTRADOR_SISTEMA", "ADMINISTRADOR_PLATAFORMA", "ADMINISTRADOR"]
            and usuario.empresa_id is None
        )
        if not es_plataforma:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere autoridad de administrador de plataforma con ámbito global (empresa_id nulo)",
            )
        return usuario
    return _check


async def get_usuario_opcional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[Usuario]:
    from backend.app.main import app
    import inspect
    if get_usuario_opcional in app.dependency_overrides:
        override = app.dependency_overrides[get_usuario_opcional]
        res = override()
        if inspect.isawaitable(res):
            res = await res
        return res
    if get_usuario_actual in app.dependency_overrides:
        override = app.dependency_overrides[get_usuario_actual]
        res = override()
        if inspect.isawaitable(res):
            res = await res
        return res
    if credentials is None:
        return None
    try:
        return await get_usuario_actual(credentials, db)
    except HTTPException:
        return None

def get_sucursal_del_usuario(usuario: Usuario) -> Optional[uuid.UUID]:
    if usuario.empleado and usuario.empleado.sucursal_id:
        return usuario.empleado.sucursal_id
    return None
