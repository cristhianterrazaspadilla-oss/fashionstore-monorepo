import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import require_roles, get_usuario_actual, get_sucursal_del_usuario
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.inventario.services.inventario_service import InventarioService

router = APIRouter()


async def _validar_sucursal_empresa(db: AsyncSession, sucursal_id: uuid.UUID, empresa_id: Optional[uuid.UUID]):
    if empresa_id is None:
        return
    q = select(Sucursal).where(Sucursal.id == sucursal_id, Sucursal.empresa_id == empresa_id)
    res = await db.execute(q)
    suc = res.scalars().first()
    if not suc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sucursal no pertenece a la empresa autorizada",
        )


@router.get(
    "/kardex",
    status_code=status.HTTP_200_OK,
    summary="Consultar Kardex por variante (CU07 / CU17 / RF22)",
    description="Auditoría inmutable con ID, fecha_hora, variante, sucursal origen/destino, tipo, cantidad, costo_unitario, saldo_fisico, valoracion_saldo, responsable, referencia.",
)
async def consultarKardex(
    variante_id: Optional[uuid.UUID] = Query(None, description="ID de variante a consultar"),
    sucursal_id: Optional[uuid.UUID] = Query(None, description="Filtrar por sucursal origen/destino"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo (RECEPCION_PROVEEDOR, VENTA, etc.)"),
    desde: Optional[datetime] = Query(None, description="Rango desde (fecha_hora >=)"),
    hasta: Optional[datetime] = Query(None, description="Rango hasta (fecha_hora <=)"),
    limit: int = Query(100, ge=1, le=200, description="Límite resultados"),
    offset: int = Query(0, ge=0, description="Offset paginación"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMINISTRADOR", "ENCARGADO", "CAJERO")),
) -> List[Dict[str, Any]]:
    rol = (usuario.rol.nombre if usuario.rol else "").upper()
    if rol in ("ENCARGADO", "CAJERO"):
        propia = get_sucursal_del_usuario(usuario)
        if propia and sucursal_id and sucursal_id != propia:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Encargado solo puede consultar Kardex de su sucursal asignada",
            )
        if propia:
            sucursal_id = propia

    if sucursal_id and usuario.empresa_id:
        await _validar_sucursal_empresa(db, sucursal_id, usuario.empresa_id)

    servicio = InventarioService(db)
    return await servicio.kardexPorVariante(
        variante_id=variante_id,
        sucursal_id=sucursal_id,
        tipo=tipo,
        desde=desde,
        hasta=hasta,
        limit=limit,
        offset=offset,
        empresa_id=usuario.empresa_id,
    )


@router.get(
    "/kardex/{movimiento_id}",
    status_code=status.HTTP_200_OK,
    summary="Obtener movimiento Kardex por ID (CU07 / CU17)",
    description="Retorna detalle de movimiento individual con costo_unitario, saldo y referencia.",
)
async def obtenerKardexPorId(
    movimiento_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Usuario = Depends(require_roles("ADMINISTRADOR", "ENCARGADO", "CAJERO")),
) -> Dict[str, Any]:
    servicio = InventarioService(db)
    return await servicio.kardexPorId(movimiento_id)


@router.get(
    "/existencias",
    status_code=status.HTTP_200_OK,
    summary="Consultar existencias por sucursal (CU07 / CU17 / RF21)",
    description="Existencias detalladas con físico, reservado, cupo offline y libre, valorización al costo ponderado.",
)
async def consultarExistencias(
    sucursal_id: Optional[uuid.UUID] = Query(None, description="ID sucursal a consultar, si no se provee retorna todas"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMINISTRADOR", "ENCARGADO", "CAJERO")),
) -> List[Dict[str, Any]]:
    rol = (usuario.rol.nombre if usuario.rol else "").upper()
    if rol in ("ENCARGADO", "CAJERO"):
        propia = get_sucursal_del_usuario(usuario)
        if propia:
            sucursal_id = propia
        elif not sucursal_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Encargado sin sucursal asignada")
        elif sucursal_id != propia:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Encargado solo puede consultar su sucursal")

    if sucursal_id and usuario.empresa_id:
        await _validar_sucursal_empresa(db, sucursal_id, usuario.empresa_id)

    servicio = InventarioService(db)
    return await servicio.consultarExistencias(sucursal_id=sucursal_id, empresa_id=usuario.empresa_id)


@router.get(
    "/valorizacion",
    status_code=status.HTTP_200_OK,
    summary="Consultar valorización por sucursal y global (CU07 / CU17 / RF26)",
    description="Valorización: Σ existencia×costo_promedio por sucursal y global, margen bruto precio - costo_promedio.",
)
async def consultarValorizacion(
    sucursal_id: Optional[uuid.UUID] = Query(None, description="Filtrar valorización por sucursal"),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(require_roles("ADMINISTRADOR", "ENCARGADO", "CAJERO")),
) -> Dict[str, Any]:
    rol = (usuario.rol.nombre if usuario.rol else "").upper()
    if rol in ("ENCARGADO", "CAJERO"):
        propia = get_sucursal_del_usuario(usuario)
        if propia:
            sucursal_id = propia

    if sucursal_id and usuario.empresa_id:
        await _validar_sucursal_empresa(db, sucursal_id, usuario.empresa_id)

    servicio = InventarioService(db)
    return await servicio.consultarValorizacion(sucursal_id=sucursal_id, empresa_id=usuario.empresa_id)
