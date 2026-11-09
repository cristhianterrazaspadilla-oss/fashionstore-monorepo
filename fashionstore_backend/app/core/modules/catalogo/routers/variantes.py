import uuid
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_opcional, require_rol_empresarial
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.catalogo.models import Producto, VarianteProducto
from backend.app.core.modules.catalogo.schemas import (
    VarianteCrearDTO,
    VarianteDTO,
    VariantePublicaDTO,
    VarianteActualizarDTO,
)
from backend.app.core.modules.inventario.schemas import DisponibilidadSucursalDTO
from backend.app.core.modules.catalogo.services.variante_service import VarianteService
from backend.app.core.modules.catalogo.services.catalogo_service import (
    CatalogoService,
    resolver_empresa_lectura_defecto,
)
from backend.app.core.modules.inventario.services.inventario_service import InventarioService

router = APIRouter()

@router.post(
    "",
    response_model=VarianteDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear variante de producto (CU05 / RF05)",
    description="Presentación gestionarVariantes() -> Controller VarianteService.crear() -> Datos VarianteRepository.crear(). UQ producto+talla+color, sku único, codigo_barras único, precio >=0, activa. 409 Conflict si duplica."
)
async def gestionarVariantes(
    datos: VarianteCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> VarianteDTO:
    servicio = VarianteService(db, empresa_id=_admin.empresa_id)
    return await servicio.crear(datos)

@router.get(
    "",
    response_model=Union[List[VarianteDTO], List[VariantePublicaDTO]],
    status_code=status.HTTP_200_OK,
    summary="Listar variantes (CU05 / CU16)",
    description=(
        "Listar variantes de producto. Si se consulta por un administrador empresarial, "
        "devuelve VarianteDTO con costos acotado a la empresa de su sesión. Si se consulta "
        "públicamente, devuelve VariantePublicaDTO sin costos ni campos internos, acotado a "
        "una sola empresa."
    ),
)
async def listarVariantes(
    producto_id: Optional[uuid.UUID] = Query(None, description="Filtrar por producto"),
    solo_activas: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    empresa_id: Optional[uuid.UUID] = Query(None, description="Filtrar por empresa"),
    empresa_codigo: Optional[str] = Query(None, description="Filtrar por código de empresa"),
    db: AsyncSession = Depends(get_db),
    usuario_opt: Optional[Usuario] = Depends(get_usuario_opcional),
) -> Union[List[VarianteDTO], List[VariantePublicaDTO]]:
    servicio = VarianteService(db)
    rol_nombre = (usuario_opt.rol.nombre if usuario_opt and usuario_opt.rol else "").upper()
    if usuario_opt is not None and rol_nombre in {"ADMINISTRADOR", "SUPERADMIN", "GERENTE", "CAJERO"} and usuario_opt.empresa_id is None:
        raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
    es_admin_empresa = (
        usuario_opt is not None
        and rol_nombre == "ADMINISTRADOR"
    )

    if es_admin_empresa:
        if not usuario_opt.empresa_id:
            raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
        if empresa_id is not None and empresa_id != usuario_opt.empresa_id:
            raise HTTPException(status_code=403, detail="No autorizado para consultar otra empresa")
        return await servicio.listar(
            producto_id=producto_id,
            solo_activas=solo_activas,
            limit=limit,
            offset=offset,
            empresa_id=usuario_opt.empresa_id,
        )

    # Modo público
    if usuario_opt is not None and usuario_opt.empresa_id is not None:
        if empresa_id is not None and empresa_id != usuario_opt.empresa_id:
            raise HTTPException(status_code=403, detail="No autorizado para consultar otra empresa")
        empresa_id_final = usuario_opt.empresa_id
    elif empresa_id or empresa_codigo:
        servicio_cat = CatalogoService(db)
        emp = await servicio_cat._empresa_publica(empresa_id=empresa_id, empresa_codigo=empresa_codigo)
        empresa_id_final = emp.id
    elif producto_id:
        res = await db.execute(select(Producto.empresa_id).where(Producto.id == producto_id))
        p_emp = res.scalar()
        if p_emp is None:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        empresa_id_final = p_emp
    else:
        def_emp = await resolver_empresa_lectura_defecto(db)
        if not def_emp:
            raise HTTPException(status_code=400, detail="Se requiere empresa_id o empresa_codigo")
        empresa_id_final = def_emp.id

    return await servicio.listarPublico(
        producto_id=producto_id,
        solo_activas=solo_activas,
        limit=limit,
        offset=offset,
        empresa_id=empresa_id_final,
    )

@router.get(
    "/{variante_id}",
    response_model=Union[VarianteDTO, VariantePublicaDTO],
    status_code=status.HTTP_200_OK,
    summary="Obtener variante por ID (CU05 / CU16)"
)
async def obtenerVariante(
    variante_id: uuid.UUID,
    empresa_id: Optional[uuid.UUID] = Query(None, description="Filtrar por empresa"),
    empresa_codigo: Optional[str] = Query(None, description="Filtrar por código de empresa"),
    db: AsyncSession = Depends(get_db),
    usuario_opt: Optional[Usuario] = Depends(get_usuario_opcional),
) -> Union[VarianteDTO, VariantePublicaDTO]:
    servicio = VarianteService(db)
    rol_nombre = (usuario_opt.rol.nombre if usuario_opt and usuario_opt.rol else "").upper()
    if usuario_opt is not None and rol_nombre in {"ADMINISTRADOR", "SUPERADMIN", "GERENTE", "CAJERO"} and usuario_opt.empresa_id is None:
        raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
    es_admin_empresa = (
        usuario_opt is not None
        and rol_nombre == "ADMINISTRADOR"
    )

    if es_admin_empresa:
        if not usuario_opt.empresa_id:
            raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
        if empresa_id is not None and empresa_id != usuario_opt.empresa_id:
            raise HTTPException(status_code=403, detail="No autorizado para consultar otra empresa")
        return await servicio.obtenerPorId(variante_id, empresa_id=usuario_opt.empresa_id)

    # Modo público
    if usuario_opt is not None and usuario_opt.empresa_id is not None:
        if empresa_id is not None and empresa_id != usuario_opt.empresa_id:
            raise HTTPException(status_code=403, detail="No autorizado para consultar otra empresa")
        empresa_id_final = usuario_opt.empresa_id
    elif empresa_id or empresa_codigo:
        servicio_cat = CatalogoService(db)
        emp = await servicio_cat._empresa_publica(empresa_id=empresa_id, empresa_codigo=empresa_codigo)
        empresa_id_final = emp.id
    else:
        def_emp = await resolver_empresa_lectura_defecto(db)
        if not def_emp:
            raise HTTPException(status_code=400, detail="Se requiere empresa_id o empresa_codigo")
        empresa_id_final = def_emp.id

    return await servicio.obtenerPublicaPorId(variante_id, empresa_id=empresa_id_final)

@router.put(
    "/{variante_id}",
    response_model=VarianteDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar variante (CU05)"
)
async def actualizarVariante(
    variante_id: uuid.UUID,
    datos: VarianteActualizarDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> VarianteDTO:
    servicio = VarianteService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizar(variante_id, datos)

@router.patch(
    "/{variante_id}/activacion",
    response_model=VarianteDTO,
    status_code=status.HTTP_200_OK,
    summary="Activar/desactivar variante (CU05)"
)
async def toggleVariante(
    variante_id: uuid.UUID,
    activa: bool = Query(..., description="Nuevo estado activo"),
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> VarianteDTO:
    servicio = VarianteService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizar(variante_id, VarianteActualizarDTO(activa=activa))

@router.get(
    "/{variante_id}/disponibilidad",
    response_model=List[DisponibilidadSucursalDTO],
    status_code=status.HTTP_200_OK,
    summary="Consultar disponibilidad por sucursal (CU06 / RF08)",
    description="Presentación consultarDisponibilidad() -> Controller InventarioService.disponibilidadPorSucursal() -> Datos InventarioRepository.porVariante(). Lista sucursales con disponible>0, diferenciando disponible, reservado, comprometido_traslado, en_transito. Por sucursal, no total global. Solo lectura."
)
async def consultarDisponibilidad(
    variante_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> List[DisponibilidadSucursalDTO]:
    servicio = InventarioService(db)
    return await servicio.disponibilidadPorSucursal(variante_id)
