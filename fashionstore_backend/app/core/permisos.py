"""Permisos Ciclo 2: aislamiento por rol, propietario y sucursal.

  - 401 ausencia de sesion: lo produce get_usuario_actual (dependencia).
  - 403 rol / propietario / sucursal no autorizada: estas ayudas.
  - ADMINISTRADOR es global (sin sucursal); ENCARGADO/CAJERO operan solo
    en la sucursal de su empleado; CLIENTE solo sobre lo propio.
"""
import uuid
from fastapi import HTTPException, status
from backend.app.core.modules.identidad_empresas.models import Usuario


def es_admin(usuario: Usuario) -> bool:
    return rol_de(usuario) == "ADMINISTRADOR"


def rol_de(usuario: Usuario) -> str:
    try:
        rol = usuario.rol
    except Exception:
        rol = getattr(usuario, "__dict__", {}).get("rol")
    return (rol.nombre if rol else "").upper()


def exigir_roles(usuario: Usuario, *roles: str) -> None:
    if rol_de(usuario) not in [r.upper() for r in roles]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado para el rol {rol_de(usuario)}",
        )


def exigir_sucursal(usuario: Usuario, sucursal_id: uuid.UUID) -> None:
    """403 si el personal intenta operar fuera de su sucursal.

    El administrador es global. Los clientes no tienen sucursal asignada:
    esta ayuda solo se usa en endpoints de personal.
    """
    if es_admin(usuario):
        return
    propia = None
    if usuario.empleado is not None:
        propia = usuario.empleado.sucursal_id
    if propia is None or propia != sucursal_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sucursal no autorizada para este usuario",
        )


def exigir_propietario_o_personal(
    usuario: Usuario, propietario_id: uuid.UUID, *roles_personal: str
) -> None:
    """403 si no es el propietario ni personal autorizado."""
    if usuario.id == propietario_id:
        return
    if rol_de(usuario) in [r.upper() for r in roles_personal] or es_admin(usuario):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No autorizado: recurso de otro propietario",
    )
