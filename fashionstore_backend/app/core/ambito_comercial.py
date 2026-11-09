"""Ámbito comercial explícito; la autoridad de plataforma no concede acceso empresarial."""
from fastapi import HTTPException
from sqlalchemy import select

from backend.app.core.permisos import exigir_sucursal, rol_de


def empresa_comercial(usuario):
    empresa_id = usuario.empresa_id
    if not empresa_id or rol_de(usuario) not in (
        "ADMINISTRADOR", "ENCARGADO", "CAJERO", "CLIENTE"
    ):
        raise HTTPException(status_code=403, detail="Se requiere un usuario empresarial autorizado")
    return empresa_id


def exigir_empresa_recurso(usuario, recurso):
    if recurso.empresa_id != empresa_comercial(usuario):
        raise HTTPException(status_code=404, detail="Recurso no encontrado")


async def sucursal_autorizada(db, usuario, sucursal_id):
    from backend.app.core.modules.organizacion.models import Sucursal

    empresa_id = empresa_comercial(usuario)
    sucursal = (await db.execute(select(Sucursal).where(
        Sucursal.id == sucursal_id, Sucursal.empresa_id == empresa_id
    ))).scalars().first()
    if sucursal is None:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    if rol_de(usuario) in ("ENCARGADO", "CAJERO"):
        exigir_sucursal(usuario, sucursal_id)
    return sucursal
