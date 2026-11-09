from decimal import Decimal
from typing import Literal, Union
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy import distinct, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.modules.catalogo.services.catalogo_service import CatalogoService
from backend.app.core.modules.inventario.services.inventario_service import InventarioService
from backend.app.core.modules.catalogo.schemas import ProductoPublicoDTO, CatalogoDescargaDTO, CatalogoProductosPaginadoDTO
from backend.app.core.modules.inventario.schemas import DisponibilidadSucursalDTO, FiltrosOpcionesDTO
from backend.app.core.modules.catalogo.models import (
    Producto, Categoria, Talla, Color, Temporada, Coleccion, VarianteProducto
)
from backend.app.core.modules.identidad_empresas.models import Empresa

router = APIRouter()


@router.get(
    "/descarga",
    response_model=CatalogoDescargaDTO,
    status_code=status.HTTP_200_OK,
    summary="Descargar catálogo para consulta offline (CU03)",
    description=(
        "Obtiene una instantánea coherente y tipada del catálogo público para consulta offline en PWA y Flutter. "
        "Aísla por empresa y sucursal. Incluye productos, variantes activas, precio BOB en formato decimal ('120.00'), "
        "tallas, colores y disponibilidad pública conocida. No expone costos, márgenes ni proveedores privados. "
        "Consultar o descargar no aparta inventario."
    ),
)
async def descargarCatalogo(
    empresa_id: Optional[uuid.UUID] = Query(None, description="Identificador único de la empresa"),
    empresa_codigo: Optional[str] = Query(None, description="Código de la empresa (ej: fashionstore)"),
    sucursal_id: Optional[uuid.UUID] = Query(None, description="Ámbito de sucursal opcional para disponibilidad local"),
    db: AsyncSession = Depends(get_db),
) -> CatalogoDescargaDTO:
    servicio = CatalogoService(db)
    return await servicio.descargarCatalogo(
        empresa_id=empresa_id,
        empresa_codigo=empresa_codigo,
        sucursal_id=sucursal_id,
    )


@router.get(
    "/filtros-opciones",
    response_model=FiltrosOpcionesDTO,
    status_code=status.HTTP_200_OK,
    summary="Opciones de filtros para catálogo (CU06 / CU16)",
    description="Retorna listas de categorías, tallas, colores, temporadas, colecciones, géneros y marcas para construir filtros en tiempo real, aislados por empresa."
)
async def filtrosOpciones(
    empresa_id: Optional[uuid.UUID] = Query(None, description="Filtrar opciones por empresa"),
    empresa_codigo: Optional[str] = Query(None, description="Filtrar opciones por código de empresa"),
    db: AsyncSession = Depends(get_db)
) -> FiltrosOpcionesDTO:
    from backend.app.core.modules.catalogo.services.catalogo_service import resolver_empresa_lectura_defecto
    servicio = CatalogoService(db)
    if not empresa_id and not empresa_codigo:
        emp_def = await resolver_empresa_lectura_defecto(db)
        if emp_def:
            empresa_id = emp_def.id
        else:
            raise HTTPException(status_code=400, detail="Se requiere empresa_id o empresa_codigo")
    return await servicio.obtenerOpcionesFiltros(
        empresa_id=empresa_id,
        empresa_codigo=empresa_codigo,
    )


@router.get(
    "/productos",
    response_model=Union[CatalogoProductosPaginadoDTO, List[ProductoPublicoDTO]],
    status_code=status.HTTP_200_OK,
    summary="Consultar catálogo público (CU16)",
    description="Consulta catálogo público con filtros por texto, categoría, talla, colores simples o compuestos, precio BOB, sucursal y paginación.",
)
async def consultarCatalogoAlias(
    solo_activos: bool = Query(True),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    categoria_id: Optional[uuid.UUID] = Query(None),
    talla_id: Optional[uuid.UUID] = Query(None),
    color_id: Optional[uuid.UUID] = Query(None),
    componentes_color: Optional[List[uuid.UUID]] = Query(None),
    modo_color: Literal["EXACTO", "TODOS_COMPONENTES"] = Query("EXACTO"),
    temporada_id: Optional[uuid.UUID] = Query(None),
    coleccion_id: Optional[uuid.UUID] = Query(None),
    marca: Optional[str] = Query(None),
    genero: Optional[str] = Query(None),
    texto: Optional[str] = Query(None),
    busqueda: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    precio_min: Optional[float] = Query(None, ge=0),
    precio_max: Optional[float] = Query(None, ge=0),
    precio_min_bob: Optional[Decimal] = Query(None, ge=0),
    precio_max_bob: Optional[Decimal] = Query(None, ge=0),
    sucursal_id: Optional[uuid.UUID] = Query(None),
    codigo_hex: Optional[str] = Query(None),
    empresa_id: Optional[uuid.UUID] = Query(None, description="Filtrar por empresa"),
    empresa_codigo: Optional[str] = Query(None, description="Filtrar por código de empresa"),
    paginado: bool = Query(False, description="Si es True retorna {total, limit, offset, items[]}; si es False retorna items[]"),
    db: AsyncSession = Depends(get_db)
) -> Union[CatalogoProductosPaginadoDTO, List[ProductoPublicoDTO]]:
    servicio = CatalogoService(db)
    texto_final = texto or busqueda or q
    return await servicio.consultarCatalogoPublico(
        empresa_id=empresa_id,
        empresa_codigo=empresa_codigo,
        texto=texto_final,
        categoria_id=categoria_id,
        talla_id=talla_id,
        color_id=color_id,
        componentes_color=componentes_color,
        modo_color=modo_color,
        temporada_id=temporada_id,
        coleccion_id=coleccion_id,
        marca=marca,
        genero=genero,
        precio_min=precio_min,
        precio_max=precio_max,
        precio_min_bob=precio_min_bob,
        precio_max_bob=precio_max_bob,
        sucursal_id=sucursal_id,
        codigo_hex=codigo_hex,
        solo_activos=solo_activos,
        limit=limit,
        offset=offset,
        paginado=paginado,
    )


@router.get(
    "/variantes/{variante_id}/disponibilidad",
    response_model=List[DisponibilidadSucursalDTO],
    status_code=status.HTTP_200_OK,
    summary="Disponibilidad por sucursal (alias CU06 / CU16)",
    description="Alias de GET /api/v1/variantes/{id}/disponibilidad para consultarDisponibilidad()"
)
async def consultarDisponibilidadAlias(
    variante_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> List[DisponibilidadSucursalDTO]:
    servicio = InventarioService(db)
    return await servicio.disponibilidadPorSucursal(variante_id)
