import uuid
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.core.dependencias import get_usuario_opcional, require_rol_empresarial
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.catalogo.models import Producto as ProductoModel
from backend.app.core.modules.catalogo.schemas import (
    ProductoCrearDTO,
    ProductoDTO,
    ProductoPublicoDTO,
    ProductoActualizarDTO,
)
from backend.app.core.modules.catalogo.services.catalogo_service import (
    CatalogoService,
    resolver_empresa_lectura_defecto,
)
from backend.app.core.modules.catalogo.services.producto_service import ProductoService

router = APIRouter()

@router.post(
    "",
    response_model=ProductoDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear producto con imágenes y asociaciones (CU05 / RF04, RF05, RF23)",
    description="Presentación gestionarProductos() -> Controller ProductoService.crear() -> Datos ProductoRepository.crear(). Valida categoria_id, proveedor_principal_id, precio_base >=0, imagenes y temporadas/colecciones"
)
async def gestionarProductos(
    datos: ProductoCrearDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> ProductoDTO:
    servicio = ProductoService(db, empresa_id=_admin.empresa_id)
    return await servicio.crear(datos)

@router.get(
    "",
    response_model=Union[List[ProductoDTO], List[ProductoPublicoDTO]],
    status_code=status.HTTP_200_OK,
    summary="Consultar catálogo con filtros avanzados (CU06 / RF05, RF07, RF08)",
    description=(
        "Presentación consultarCatalogo()/filtrarCatalogo() -> Controller CatalogoService.listar()/filtrar() -> Datos ProductoRepository.buscarConFiltros(). "
        "Si se invoca con rol ADMINISTRADOR empresarial, devuelve ProductoDTO (con proveedor_principal_id) acotado a su empresa. "
        "Si se invoca públicamente o sin sesión, devuelve ProductoPublicoDTO sin costos ni campos internos. "
        "Para clientes legacy (Flutter/Angular) sin empresa explícita, resuelve la empresa activa única en modo solo lectura."
    ),
)
async def listarProductos(
    solo_activos: bool = Query(True, description="Filtrar solo activos (default true para catálogo)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    categoria_id: Optional[uuid.UUID] = Query(None, description="Filtrar por categoría"),
    talla_id: Optional[uuid.UUID] = Query(None, description="Filtrar por talla (vía variantes)"),
    color_id: Optional[uuid.UUID] = Query(None, description="Filtrar por color (vía variantes)"),
    temporada_id: Optional[uuid.UUID] = Query(None, description="Filtrar por temporada"),
    coleccion_id: Optional[uuid.UUID] = Query(None, description="Filtrar por colección"),
    marca: Optional[str] = Query(None),
    genero: Optional[str] = Query(None),
    texto: Optional[str] = Query(None, description="Búsqueda por nombre/descripción (alias busqueda)"),
    busqueda: Optional[str] = Query(None, description="Alias de texto"),
    q: Optional[str] = Query(None, description="Alias búsqueda"),
    precio_min: Optional[float] = Query(None, ge=0, description="Precio mínimo"),
    precio_max: Optional[float] = Query(None, ge=0, description="Precio máximo"),
    codigo_hex: Optional[str] = Query(None, description="Filtrar por color hex #RRGGBB"),
    activo: Optional[bool] = Query(None, description="Override activo (si se quiere incluir inactivos)"),
    empresa_id: Optional[uuid.UUID] = Query(None, description="Compatibilidad: identificador de la empresa"),
    empresa_codigo: Optional[str] = Query(None, description="Compatibilidad: código de la empresa"),
    db: AsyncSession = Depends(get_db),
    usuario_opt: Optional[Usuario] = Depends(get_usuario_opcional),
) -> Union[List[ProductoDTO], List[ProductoPublicoDTO]]:
    servicio = CatalogoService(db)
    texto_final = texto or busqueda or q
    if activo is not None:
        solo_activos = activo

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
        empresa_id_final = usuario_opt.empresa_id
        empresa_codigo_final = None

        tiene_filtro = any([
            categoria_id, talla_id, color_id, temporada_id, coleccion_id, marca,
            genero, texto_final, precio_min is not None, precio_max is not None,
            codigo_hex
        ])
        if tiene_filtro:
            return await servicio.filtrar(
                texto=texto_final,
                categoria_id=categoria_id,
                talla_id=talla_id,
                color_id=color_id,
                temporada_id=temporada_id,
                coleccion_id=coleccion_id,
                marca=marca,
                genero=genero,
                precio_min=precio_min,
                precio_max=precio_max,
                codigo_hex=codigo_hex,
                solo_activos=solo_activos,
                limit=limit,
                offset=offset,
                empresa_id=empresa_id_final,
                empresa_codigo=empresa_codigo_final,
            )
        return await servicio.listar(
            solo_activos=solo_activos,
            limit=limit,
            offset=offset,
            empresa_id=empresa_id_final,
            empresa_codigo=empresa_codigo_final,
        )

    # Modo público: no expone proveedores ni costos.
    if usuario_opt is not None and usuario_opt.empresa_id is not None:
        if empresa_id is not None and empresa_id != usuario_opt.empresa_id:
            raise HTTPException(status_code=403, detail="No autorizado para consultar otra empresa")
        empresa_id_final = usuario_opt.empresa_id
        empresa_codigo_final = None
    elif not empresa_id and not empresa_codigo:
        empresa_def = await resolver_empresa_lectura_defecto(db)
        if not empresa_def:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se requiere empresa_id o empresa_codigo para consultar el catálogo",
            )
        empresa_id_final = empresa_def.id
        empresa_codigo_final = None
    else:
        empresa_id_final = empresa_id
        empresa_codigo_final = empresa_codigo

    tiene_filtro = any([
        categoria_id, talla_id, color_id, temporada_id, coleccion_id, marca,
        genero, texto_final, precio_min is not None, precio_max is not None,
        codigo_hex
    ])
    if tiene_filtro:
        return await servicio.filtrarPublico(
            texto=texto_final,
            categoria_id=categoria_id,
            talla_id=talla_id,
            color_id=color_id,
            temporada_id=temporada_id,
            coleccion_id=coleccion_id,
            marca=marca,
            genero=genero,
            precio_min=precio_min,
            precio_max=precio_max,
            codigo_hex=codigo_hex,
            solo_activos=solo_activos,
            limit=limit,
            offset=offset,
            empresa_id=empresa_id_final,
            empresa_codigo=empresa_codigo_final,
        )
    return await servicio.listarPublico(
        solo_activos=solo_activos,
        limit=limit,
        offset=offset,
        empresa_id=empresa_id_final,
        empresa_codigo=empresa_codigo_final,
    )

@router.get(
    "/{producto_id}",
    response_model=Union[ProductoDTO, ProductoPublicoDTO],
    status_code=status.HTTP_200_OK,
    summary="Obtener producto por ID (CU05 / CU16)"
)
async def obtenerProducto(
    producto_id: uuid.UUID,
    empresa_id: Optional[uuid.UUID] = Query(None, description="Compatibilidad: rige la empresa de la sesión"),
    empresa_codigo: Optional[str] = Query(None, description="Código de empresa opcional"),
    db: AsyncSession = Depends(get_db),
    usuario_opt: Optional[Usuario] = Depends(get_usuario_opcional),
) -> Union[ProductoDTO, ProductoPublicoDTO]:
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
        res = await db.execute(
            select(ProductoModel.empresa_id).where(ProductoModel.id == producto_id)
        )
        p_empresa = res.scalar()
        if p_empresa is None or p_empresa != usuario_opt.empresa_id:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        servicio_prod = ProductoService(db)
        return await servicio_prod.obtenerPorId(producto_id)

    # Modo público
    servicio_cat = CatalogoService(db)
    if usuario_opt is not None and usuario_opt.empresa_id is not None:
        if empresa_id is not None and empresa_id != usuario_opt.empresa_id:
            raise HTTPException(status_code=403, detail="No autorizado para consultar otra empresa")
        empresa_id_esperada = usuario_opt.empresa_id
    elif empresa_id or empresa_codigo:
        empresa = await servicio_cat._empresa_publica(empresa_id=empresa_id, empresa_codigo=empresa_codigo)
        empresa_id_esperada = empresa.id
    else:
        empresa_def = await resolver_empresa_lectura_defecto(db)
        if not empresa_def:
            raise HTTPException(status_code=400, detail="Se requiere empresa_id o empresa_codigo")
        empresa_id_esperada = empresa_def.id

    q = select(ProductoModel).where(ProductoModel.id == producto_id)
    if empresa_id_esperada is not None:
        q = q.where(ProductoModel.empresa_id == empresa_id_esperada)
    res = await db.execute(q)
    producto = res.scalars().first()
    if not producto or not producto.activo:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    servicio_prod = ProductoService(db)
    dto_completo = await servicio_prod.obtenerPorId(producto_id)
    return ProductoPublicoDTO.model_validate(dto_completo)

@router.put(
    "/{producto_id}",
    response_model=ProductoDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar producto (CU05 / RF04)",
    description="Controller ProductoService.actualizar() -> Datos ProductoRepository.actualizar()"
)
async def actualizarProducto(
    producto_id: uuid.UUID,
    datos: ProductoActualizarDTO,
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> ProductoDTO:
    servicio = ProductoService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizar(producto_id, datos)

@router.patch(
    "/{producto_id}/activacion",
    response_model=ProductoDTO,
    status_code=status.HTTP_200_OK,
    summary="Activar/desactivar producto (CU05)"
)
async def toggleProducto(
    producto_id: uuid.UUID,
    activo: bool = Query(..., description="Nuevo estado activo"),
    db: AsyncSession = Depends(get_db),
    _admin: Usuario = Depends(require_rol_empresarial("ADMINISTRADOR"))
) -> ProductoDTO:
    servicio = ProductoService(db, empresa_id=_admin.empresa_id)
    return await servicio.actualizar(producto_id, ProductoActualizarDTO(activo=activo))
