import uuid
from typing import List
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import require_rol_empresarial
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.catalogo.schemas import (
    TallaCrearDTO, TallaDTO, TallaActualizarDTO,
    ColorCrearDTO, ColorDTO, ColorActualizarDTO,
    CategoriaCrearDTO, CategoriaDTO, CategoriaActualizarDTO,
    TemporadaCrearDTO, TemporadaDTO, TemporadaActualizarDTO,
    ColeccionCrearDTO, ColeccionDTO, ColeccionActualizarDTO
)
from backend.app.core.modules.catalogo.services.maestro_service import MaestroService

# Routers separados para cada maestro (se montan con prefix en api.py)
router_tallas = APIRouter()
router_colores = APIRouter()
router_categorias = APIRouter()
router_temporadas = APIRouter()
router_colecciones = APIRouter()

# ---------- TALLAS ----------
@router_tallas.post(
    "",
    response_model=TallaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear talla (CU05 / RF05)",
    description="Presentación gestionarMaestros() -> Controller MaestroService.crearTalla() -> Datos MaestroRepository.crearTalla()"
)
async def crearTalla(
    datos: TallaCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> TallaDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.crearTalla(datos)

@router_tallas.get(
    "",
    response_model=List[TallaDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar tallas (CU05)",
)
async def listarTallas(
    solo_activas: bool = Query(False, description="Filtrar solo activas"),
    db: AsyncSession = Depends(get_db)
) -> List[TallaDTO]:
    servicio = MaestroService(db)
    return await servicio.listarTallas(solo_activas=solo_activas)

@router_tallas.get(
    "/{talla_id}",
    response_model=TallaDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener talla por ID (CU05)"
)
async def obtenerTalla(
    talla_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> TallaDTO:
    servicio = MaestroService(db)
    return await servicio.obtenerTallaPorId(talla_id)

@router_tallas.put(
    "/{talla_id}",
    response_model=TallaDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar talla (CU05)"
)
async def actualizarTalla(
    talla_id: uuid.UUID,
    datos: TallaActualizarDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> TallaDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarTalla(talla_id, datos)

@router_tallas.patch(
    "/{talla_id}/activacion",
    response_model=TallaDTO,
    status_code=status.HTTP_200_OK,
    summary="Activar/desactivar talla (CU05)"
)
async def toggleTalla(
    talla_id: uuid.UUID,
    activo: bool = Query(..., description="Nuevo estado activo"),
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR")),
) -> TallaDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarTalla(talla_id, TallaActualizarDTO(activo=activo))

# ---------- COLORES ----------
@router_colores.post(
    "",
    response_model=ColorDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear color (CU05 / RF05)",
    description="Presentación gestionarMaestros() -> Controller MaestroService.crearColor() -> Datos MaestroRepository.crearColor(). Valida codigo_hex #RRGGBB"
)
async def crearColor(
    datos: ColorCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> ColorDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.crearColor(datos)

@router_colores.get(
    "",
    response_model=List[ColorDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar colores (CU05)",
)
async def listarColores(
    solo_activos: bool = Query(False),
    db: AsyncSession = Depends(get_db)
) -> List[ColorDTO]:
    servicio = MaestroService(db)
    return await servicio.listarColores(solo_activos=solo_activos)

@router_colores.get(
    "/{color_id}",
    response_model=ColorDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener color por ID (CU05)"
)
async def obtenerColor(
    color_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> ColorDTO:
    servicio = MaestroService(db)
    return await servicio.obtenerColorPorId(color_id)

@router_colores.put(
    "/{color_id}",
    response_model=ColorDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar color (CU05)"
)
async def actualizarColor(
    color_id: uuid.UUID,
    datos: ColorActualizarDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> ColorDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarColor(color_id, datos)

@router_colores.patch(
    "/{color_id}/activacion",
    response_model=ColorDTO,
    status_code=status.HTTP_200_OK,
    summary="Activar/desactivar color (CU05)"
)
async def toggleColor(
    color_id: uuid.UUID,
    activo: bool = Query(...),
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR")),
) -> ColorDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarColor(color_id, ColorActualizarDTO(activo=activo))

# ---------- CATEGORIAS ----------
@router_categorias.post(
    "",
    response_model=CategoriaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear categoría (CU05 / RF05)",
    description="Presentación gestionarMaestros() -> Controller MaestroService.crearCategoria() -> Datos MaestroRepository.crearCategoria(). Soporta jerarquía categoria_padre_id, UQ (padre+nombre)"
)
async def crearCategoria(
    datos: CategoriaCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> CategoriaDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.crearCategoria(datos)

@router_categorias.get(
    "",
    response_model=List[CategoriaDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar categorías (CU05)",
)
async def listarCategorias(
    solo_activas: bool = Query(False),
    db: AsyncSession = Depends(get_db)
) -> List[CategoriaDTO]:
    servicio = MaestroService(db)
    return await servicio.listarCategorias(solo_activas=solo_activas)

@router_categorias.get(
    "/{categoria_id}",
    response_model=CategoriaDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener categoría por ID (CU05)"
)
async def obtenerCategoria(
    categoria_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> CategoriaDTO:
    servicio = MaestroService(db)
    return await servicio.obtenerCategoriaPorId(categoria_id)

@router_categorias.put(
    "/{categoria_id}",
    response_model=CategoriaDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar categoría (CU05)"
)
async def actualizarCategoria(
    categoria_id: uuid.UUID,
    datos: CategoriaActualizarDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> CategoriaDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarCategoria(categoria_id, datos)

@router_categorias.patch(
    "/{categoria_id}/activacion",
    response_model=CategoriaDTO,
    status_code=status.HTTP_200_OK,
    summary="Activar/desactivar categoría (CU05)"
)
async def toggleCategoria(
    categoria_id: uuid.UUID,
    activo: bool = Query(...),
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR")),
) -> CategoriaDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarCategoria(categoria_id, CategoriaActualizarDTO(activo=activo))

# ---------- TEMPORADAS ----------
@router_temporadas.post(
    "",
    response_model=TemporadaDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear temporada (CU05 / RF23)",
    description="Presentación gestionarMaestros() -> Controller MaestroService.crearTemporada() -> Datos MaestroRepository.crearTemporada(). Único nombre, valida fecha_fin >= fecha_inicio"
)
async def crearTemporada(
    datos: TemporadaCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> TemporadaDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.crearTemporada(datos)

@router_temporadas.get(
    "",
    response_model=List[TemporadaDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar temporadas (CU05)",
)
async def listarTemporadas(
    solo_activas: bool = Query(False),
    db: AsyncSession = Depends(get_db)
) -> List[TemporadaDTO]:
    servicio = MaestroService(db)
    return await servicio.listarTemporadas(solo_activas=solo_activas)

@router_temporadas.get(
    "/{temporada_id}",
    response_model=TemporadaDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener temporada por ID (CU05)"
)
async def obtenerTemporada(
    temporada_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> TemporadaDTO:
    servicio = MaestroService(db)
    return await servicio.obtenerTemporadaPorId(temporada_id)

@router_temporadas.put(
    "/{temporada_id}",
    response_model=TemporadaDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar temporada (CU05)"
)
async def actualizarTemporada(
    temporada_id: uuid.UUID,
    datos: TemporadaActualizarDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> TemporadaDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarTemporada(temporada_id, datos)

@router_temporadas.patch(
    "/{temporada_id}/activacion",
    response_model=TemporadaDTO,
    status_code=status.HTTP_200_OK,
    summary="Activar/desactivar temporada (CU05)"
)
async def toggleTemporada(
    temporada_id: uuid.UUID,
    activa: bool = Query(...),
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR")),
) -> TemporadaDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarTemporada(temporada_id, TemporadaActualizarDTO(activa=activa))

# ---------- COLECCIONES ----------
@router_colecciones.post(
    "",
    response_model=ColeccionDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear colección (CU05 / RF23)",
    description="Presentación gestionarMaestros() -> Controller MaestroService.crearColeccion() -> Datos MaestroRepository.crearColeccion(). Único nombre"
)
async def crearColeccion(
    datos: ColeccionCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> ColeccionDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.crearColeccion(datos)

@router_colecciones.get(
    "",
    response_model=List[ColeccionDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar colecciones (CU05)",
)
async def listarColecciones(
    solo_activas: bool = Query(False),
    db: AsyncSession = Depends(get_db)
) -> List[ColeccionDTO]:
    servicio = MaestroService(db)
    return await servicio.listarColecciones(solo_activas=solo_activas)

@router_colecciones.get(
    "/{coleccion_id}",
    response_model=ColeccionDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener colección por ID (CU05)"
)
async def obtenerColeccion(
    coleccion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> ColeccionDTO:
    servicio = MaestroService(db)
    return await servicio.obtenerColeccionPorId(coleccion_id)

@router_colecciones.put(
    "/{coleccion_id}",
    response_model=ColeccionDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar colección (CU05)"
)
async def actualizarColeccion(
    coleccion_id: uuid.UUID,
    datos: ColeccionActualizarDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> ColeccionDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarColeccion(coleccion_id, datos)

@router_colecciones.patch(
    "/{coleccion_id}/activacion",
    response_model=ColeccionDTO,
    status_code=status.HTTP_200_OK,
    summary="Activar/desactivar colección (CU05)"
)
async def toggleColeccion(
    coleccion_id: uuid.UUID,
    activa: bool = Query(...),
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR")),
) -> ColeccionDTO:
    servicio = MaestroService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizarColeccion(coleccion_id, ColeccionActualizarDTO(activa=activa))

router = APIRouter()
