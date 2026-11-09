import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy import select, func, distinct, text, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.reloj import utcnow
from backend.app.core.modules.catalogo.repositories.producto_repository import ProductoRepository
from backend.app.core.modules.catalogo.schemas import (
    ProductoDTO,
    ProductoPublicoDTO,
    ImagenProductoDTO,
    CatalogoDescargaDTO,
    CatalogoDescargaProductoDTO,
    CatalogoDescargaVarianteDTO,
    FiltrosOpcionesDTO,
    FiltroOpcionItemDTO,
    TallaOpcionDTO,
    ColorOpcionDTO,
    SucursalPublicaDTO,
    ColorCompuestoDTO,
    ComponenteColorDTO,
    PromocionDescargaDTO,
    DisponibilidadSucursalItemDTO,
    PromocionAplicableDTO,
    VariantePublicaDTO,
    CatalogoProductosPaginadoDTO,
)
from backend.app.core.modules.identidad_empresas.models import Empresa
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.inventario.models import InventarioSucursal
from backend.app.core.modules.catalogo.models import (
    Temporada, Coleccion, Categoria, Talla, Color, Producto,
    Promocion, ColorComponente, VarianteProducto, ProductoTemporada, ProductoColeccion,
)

async def resolver_empresa_lectura_defecto(db: AsyncSession) -> Optional[Empresa]:
    """Resuelve la empresa heredada o la única activa para compatibilidad de lectura.

    Permite atender llamadas antiguas (como Flutter o Angular) que aún no envían
    empresa_id o empresa_codigo, sin mezclar catálogos ni usar un contexto implícito
    para escrituras.
    """
    q_fs = select(Empresa).where(func.lower(Empresa.codigo) == "fashionstore", Empresa.estado == "ACTIVA")
    emp = (await db.execute(q_fs)).scalars().first()
    if emp:
        return emp
    # Compatibilidad legacy únicamente si hay exactamente una empresa activa.
    # En multitenencia el cliente debe proporcionar su empresa explícitamente.
    activas = (
        await db.execute(select(Empresa).where(Empresa.estado == "ACTIVA").limit(2))
    ).scalars().all()
    return activas[0] if len(activas) == 1 else None


class CatalogoService:
    """
    Controller CatalogoService.listar()/filtrar() para CU06 / CU16 y descargarCatalogo() para CU03.
    Solo lectura, aisla por empresa/sucursal, no expone costos ni aparta stock.
    """
    def __init__(self, db: AsyncSession, fabrica_sesion=None):
        self.db = db
        self.producto_repo = ProductoRepository(db)
        # Fabrica opcional para la instantanea REPEATABLE READ (inyectable en pruebas).
        self.fabrica_sesion = fabrica_sesion

    async def _resolver_empresa(
        self,
        empresa_id: Optional[uuid.UUID] = None,
        empresa_codigo: Optional[str] = None,
    ) -> Optional[Empresa]:
        if empresa_codigo:
            q = select(Empresa).where(func.lower(Empresa.codigo) == empresa_codigo.strip().lower())
            res = await self.db.execute(q)
            return res.scalars().first()
        if empresa_id:
            q = select(Empresa).where(Empresa.id == empresa_id)
            res = await self.db.execute(q)
            return res.scalars().first()
        return None

    async def _empresa_publica(
        self,
        empresa_id: Optional[uuid.UUID] = None,
        empresa_codigo: Optional[str] = None,
    ) -> Empresa:
        """Exige contexto de empresa válido; nunca mezcla ni lista todas.

        El catálogo público puede consultarse sin sesión, pero siempre con
        `empresa_id` o `empresa_codigo` explícitos del ámbito publicado.
        """
        if not empresa_id and not empresa_codigo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe proporcionar empresa_id o empresa_codigo",
            )
        empresa = await self._resolver_empresa(
            empresa_id=empresa_id, empresa_codigo=empresa_codigo
        )
        if empresa is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa no encontrada",
            )
        if empresa.estado != "ACTIVA":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Empresa '{empresa.codigo}' no tiene catalogo activo",
            )
        return empresa

    async def obtenerOpcionesFiltros(
        self,
        empresa_id: Optional[uuid.UUID] = None,
        empresa_codigo: Optional[str] = None,
    ) -> FiltrosOpcionesDTO:
        empresa = await self._empresa_publica(
            empresa_id=empresa_id, empresa_codigo=empresa_codigo
        )
        resolved_empresa_id = empresa.id

        q_cat = select(Categoria).where(Categoria.activo == True)
        q_tal = select(Talla).where(Talla.activo == True).order_by(Talla.orden)
        q_col = select(Color).where(Color.activo == True).order_by(Color.nombre)
        q_tem = select(Temporada).where(Temporada.activa == True).order_by(Temporada.nombre)
        q_clc = select(Coleccion).where(Coleccion.activa == True).order_by(Coleccion.nombre)
        q_genero = select(distinct(Producto.genero)).where(Producto.activo == True, Producto.genero.is_not(None))
        q_marca = select(distinct(Producto.marca)).where(Producto.activo == True, Producto.marca.is_not(None))

        if resolved_empresa_id is not None:
            q_cat = q_cat.where(Categoria.empresa_id == resolved_empresa_id)
            q_tal = q_tal.where(Talla.empresa_id == resolved_empresa_id)
            q_col = q_col.where(Color.empresa_id == resolved_empresa_id)
            q_tem = q_tem.where(Temporada.empresa_id == resolved_empresa_id)
            q_clc = q_clc.where(Coleccion.empresa_id == resolved_empresa_id)
            q_genero = q_genero.where(Producto.empresa_id == resolved_empresa_id)
            q_marca = q_marca.where(Producto.empresa_id == resolved_empresa_id)

        categorias = (await self.db.execute(q_cat)).scalars().all()
        tallas = (await self.db.execute(q_tal)).scalars().all()
        colores = (await self.db.execute(q_col)).scalars().all()
        temporadas = (await self.db.execute(q_tem)).scalars().all()
        colecciones = (await self.db.execute(q_clc)).scalars().all()
        generos = [row[0] for row in (await self.db.execute(q_genero)).all() if row[0]]
        marcas = [row[0] for row in (await self.db.execute(q_marca)).all() if row[0]]

        return FiltrosOpcionesDTO(
            categorias=[FiltroOpcionItemDTO(id=c.id, nombre=c.nombre) for c in categorias],
            tallas=[TallaOpcionDTO(id=t.id, nombre=t.nombre, orden=t.orden) for t in tallas],
            colores=[ColorOpcionDTO(id=c.id, nombre=c.nombre, codigo_hex=c.codigo_hex) for c in colores],
            temporadas=[FiltroOpcionItemDTO(id=t.id, nombre=t.nombre) for t in temporadas],
            colecciones=[FiltroOpcionItemDTO(id=c.id, nombre=c.nombre) for c in colecciones],
            generos=generos,
            marcas=marcas,
        )

    async def listar(
        self,
        solo_activos: bool = True,
        limit: int = 50,
        offset: int = 0,
        empresa_id: Optional[uuid.UUID] = None,
        empresa_codigo: Optional[str] = None,
        **filtros_extra,
    ) -> List[ProductoDTO]:
        empresa = await self._empresa_publica(
            empresa_id=empresa_id, empresa_codigo=empresa_codigo
        )
        empresa_id = empresa.id
        if filtros_extra:
            return await self.filtrar(
                filtros=filtros_extra,
                solo_activos=solo_activos,
                limit=limit,
                offset=offset,
                empresa_id=empresa_id,
            )
        productos = await self.producto_repo.listar(
            solo_activos=solo_activos, limit=limit, offset=offset, empresa_id=empresa_id
        )
        result = []
        for p in productos:
            imagenes = await self.producto_repo.listarImagenesPorProducto(p.id)
            temporada_ids = await self.producto_repo.listarTemporadaIds(p.id)
            coleccion_ids = await self.producto_repo.listarColeccionIds(p.id)
            result.append(ProductoDTO(
                id=p.id,
                categoria_id=p.categoria_id,
                proveedor_principal_id=p.proveedor_principal_id,
                nombre=p.nombre,
                descripcion=p.descripcion,
                genero=p.genero,
                marca=p.marca,
                precio_base=p.precio_base,
                activo=p.activo,
                creado_en=p.creado_en,
                actualizado_en=p.actualizado_en,
                imagenes=[ImagenProductoDTO.model_validate(i) for i in imagenes],
                temporada_ids=temporada_ids,
                coleccion_ids=coleccion_ids
            ))
        return result

    async def filtrar(
        self,
        filtros: Optional[Dict[str, Any]] = None,
        texto: Optional[str] = None,
        busqueda: Optional[str] = None,
        categoria_id: Optional[uuid.UUID] = None,
        talla_id: Optional[uuid.UUID] = None,
        color_id: Optional[uuid.UUID] = None,
        temporada_id: Optional[uuid.UUID] = None,
        coleccion_id: Optional[uuid.UUID] = None,
        genero: Optional[str] = None,
        marca: Optional[str] = None,
        precio_min: Optional[float] = None,
        precio_max: Optional[float] = None,
        codigo_hex: Optional[str] = None,
        solo_activos: bool = True,
        limit: int = 50,
        offset: int = 0,
        activo: Optional[bool] = None,
        empresa_id: Optional[uuid.UUID] = None,
        empresa_codigo: Optional[str] = None,
    ) -> List[ProductoDTO]:
        empresa = await self._empresa_publica(
            empresa_id=empresa_id, empresa_codigo=empresa_codigo
        )
        empresa_id = empresa.id

        if filtros is not None:
            if isinstance(filtros, dict):
                if texto is None and "texto" in filtros:
                    texto = filtros.get("texto")
                if busqueda is None and "busqueda" in filtros:
                    busqueda = filtros.get("busqueda")
                if categoria_id is None and "categoria_id" in filtros:
                    categoria_id = filtros.get("categoria_id")
                if talla_id is None and "talla_id" in filtros:
                    talla_id = filtros.get("talla_id")
                if color_id is None and "color_id" in filtros:
                    color_id = filtros.get("color_id")
                if temporada_id is None and "temporada_id" in filtros:
                    temporada_id = filtros.get("temporada_id")
                if coleccion_id is None and "coleccion_id" in filtros:
                    coleccion_id = filtros.get("coleccion_id")
                if genero is None and "genero" in filtros:
                    genero = filtros.get("genero")
                if marca is None and "marca" in filtros:
                    marca = filtros.get("marca")
                if precio_min is None and "precio_min" in filtros:
                    precio_min = filtros.get("precio_min")
                if precio_max is None and "precio_max" in filtros:
                    precio_max = filtros.get("precio_max")
                if codigo_hex is None and ("codigo_hex" in filtros or "color_hex" in filtros):
                    codigo_hex = filtros.get("codigo_hex", filtros.get("color_hex"))
                if empresa_id is None and "empresa_id" in filtros:
                    empresa_id = filtros.get("empresa_id")
                if activo is not None:
                    solo_activos = activo
                elif "activo" in filtros:
                    solo_activos = filtros["activo"] not in [False, "false", "False", 0]
                    if filtros["activo"] is False or str(filtros["activo"]).lower() == "false":
                        solo_activos = False
            else:
                texto = filtros

        if busqueda and not texto:
            texto = busqueda

        if precio_min is not None and precio_max is not None:
            if float(precio_min) > float(precio_max):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="precio_min no puede ser mayor que precio_max")

        productos = await self.producto_repo.buscarConFiltros(
            texto=texto,
            categoria_id=categoria_id,
            talla_id=talla_id,
            color_id=color_id,
            temporada_id=temporada_id,
            coleccion_id=coleccion_id,
            genero=genero,
            marca=marca,
            precio_min=precio_min,
            precio_max=precio_max,
            solo_activos=solo_activos,
            limit=limit,
            offset=offset,
            codigo_hex=codigo_hex,
            empresa_id=empresa_id,
        )
        result = []
        for p in productos:
            imagenes = await self.producto_repo.listarImagenesPorProducto(p.id)
            temporada_ids = await self.producto_repo.listarTemporadaIds(p.id)
            coleccion_ids = await self.producto_repo.listarColeccionIds(p.id)
            result.append(ProductoDTO(
                id=p.id,
                categoria_id=p.categoria_id,
                proveedor_principal_id=p.proveedor_principal_id,
                nombre=p.nombre,
                descripcion=p.descripcion,
                genero=p.genero,
                marca=p.marca,
                precio_base=p.precio_base,
                activo=p.activo,
                creado_en=p.creado_en,
                actualizado_en=p.actualizado_en,
                imagenes=[ImagenProductoDTO.model_validate(i) for i in imagenes],
                temporada_ids=temporada_ids,
                coleccion_ids=coleccion_ids
            ))
        return result

    async def listarPublico(
        self,
        solo_activos: bool = True,
        limit: int = 50,
        offset: int = 0,
        empresa_id: Optional[uuid.UUID] = None,
        empresa_codigo: Optional[str] = None,
        **filtros_extra,
    ) -> List[ProductoPublicoDTO]:
        productos = await self.listar(
            solo_activos=solo_activos,
            limit=limit,
            offset=offset,
            empresa_id=empresa_id,
            empresa_codigo=empresa_codigo,
            **filtros_extra,
        )
        return [ProductoPublicoDTO.model_validate(p) for p in productos]

    async def filtrarPublico(self, **kwargs) -> List[ProductoPublicoDTO]:
        productos = await self.filtrar(**kwargs)
        return [ProductoPublicoDTO.model_validate(p) for p in productos]

    @asynccontextmanager
    async def _sesion_instantanea(self):
        """Sesión dedicada en REPEATABLE READ para una instantánea coherente.

        Todas las lecturas de la descarga ven el mismo corte de datos aunque
        otro proceso publique catálogo o mueva inventario durante la descarga.
        En pruebas puede inyectarse `fabrica_sesion`.
        """
        if self.fabrica_sesion is not None:
            sesion = self.fabrica_sesion()
        elif self.db.bind is not None:
            sesion = AsyncSession(bind=self.db.bind, expire_on_commit=False)
        else:  # pragma: no cover (defensivo)
            yield self.db
            return
        try:
            await sesion.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            yield sesion
        finally:
            await sesion.rollback()
            await sesion.close()

    async def descargarCatalogo(
        self,
        empresa_id: Optional[uuid.UUID] = None,
        empresa_codigo: Optional[str] = None,
        sucursal_id: Optional[uuid.UUID] = None,
    ) -> CatalogoDescargaDTO:
        async with self._sesion_instantanea() as db:
            servicio = self if db is self.db else CatalogoService(db)
            return await servicio._descargarCatalogo_en_sesion(
                empresa_id=empresa_id,
                empresa_codigo=empresa_codigo,
                sucursal_id=sucursal_id,
            )

    async def _descargarCatalogo_en_sesion(
        self,
        empresa_id: Optional[uuid.UUID] = None,
        empresa_codigo: Optional[str] = None,
        sucursal_id: Optional[uuid.UUID] = None,
    ) -> CatalogoDescargaDTO:
        """
        CU03 / CU16: Instantánea coherente y tipada del catálogo público de una empresa.
        Filtra por empresa y sucursal. No expone costos, márgenes ni proveedores privados.
        Consultar o descargar no aparta inventario.
        """
        empresa = await self._empresa_publica(
            empresa_id=empresa_id, empresa_codigo=empresa_codigo
        )
        ahora_instante = utcnow()

        # 1. Ámbito de sucursales
        ambito_sucursal = "TODAS"
        if sucursal_id is not None:
            q_suc = select(Sucursal).options(selectinload(Sucursal.ciudad)).where(
                Sucursal.id == sucursal_id,
                Sucursal.empresa_id == empresa.id,
            )
            res_suc = await self.db.execute(q_suc)
            sucursal = res_suc.scalars().first()
            if not sucursal:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Sucursal no encontrada o no pertenece a la empresa especificada",
                )
            if not sucursal.activa:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La sucursal solicitada está inactiva",
                )
            ambito_sucursal = sucursal.nombre
            ambito_sucursales = [sucursal.id]
            sucursales_dto = [
                SucursalPublicaDTO(
                    id=sucursal.id,
                    nombre=sucursal.nombre,
                    ciudad_nombre=sucursal.ciudad.nombre if sucursal.ciudad else None,
                )
            ]
        else:
            q_suc = select(Sucursal).options(selectinload(Sucursal.ciudad)).where(
                Sucursal.empresa_id == empresa.id,
                Sucursal.activa == True,
            ).order_by(Sucursal.nombre)
            res_suc = await self.db.execute(q_suc)
            sucursales_activas = list(res_suc.scalars().all())
            ambito_sucursales = [s.id for s in sucursales_activas]
            sucursales_dto = [
                SucursalPublicaDTO(
                    id=s.id,
                    nombre=s.nombre,
                    ciudad_nombre=s.ciudad.nombre if s.ciudad else None,
                )
                for s in sucursales_activas
            ]

        # 2. Colores y componentes
        q_colores = (
            select(Color)
            .options(selectinload(Color.componentes))
            .where(Color.empresa_id == empresa.id, Color.activo == True)
            .order_by(Color.nombre)
        )
        res_colores = await self.db.execute(q_colores)
        colores_dto = [
            ColorCompuestoDTO(
                id=c.id,
                nombre=c.nombre,
                componentes=[
                    ComponenteColorDTO(color_id=comp.componente_id, orden=comp.orden)
                    for comp in c.componentes
                ],
            )
            for c in res_colores.scalars().all()
        ]

        # 3. Promociones
        q_promos = (
            select(Promocion)
            .options(selectinload(Promocion.variantes))
            .where(Promocion.empresa_id == empresa.id, Promocion.activa == True)
            .order_by(Promocion.codigo)
        )
        res_promos = await self.db.execute(q_promos)
        promociones_dto = [
            PromocionDescargaDTO(
                id=pr.id,
                tipo=pr.tipo,
                valor=f"{Decimal(str(pr.valor)):.2f}",
                cantidad_minima=getattr(pr, "cantidad_minima", 1) or 1,
                vigente_desde=pr.vigencia_inicio,
                vigente_hasta=pr.vigencia_fin,
                variante_ids=[v.variante_id for v in pr.variantes],
            )
            for pr in res_promos.scalars().all()
        ]

        # 4. Obtener productos activos con sus variantes activas
        productos = await self.producto_repo.obtenerInstantaneaDescarga(empresa.id)

        # 5. Disponibilidad por sucursal
        disponibilidad_map: Dict[uuid.UUID, int] = {}
        disponibilidad_suc_map: Dict[tuple, int] = {}
        if ambito_sucursales:
            q_disp = select(
                InventarioSucursal.variante_id,
                InventarioSucursal.sucursal_id,
                InventarioSucursal.disponible,
            ).where(
                InventarioSucursal.sucursal_id.in_(ambito_sucursales)
            )
            res_disp = await self.db.execute(q_disp)
            for row in res_disp.all():
                v_id, s_id, d_cant = row[0], row[1], max(0, int(row[2] or 0))
                disponibilidad_suc_map[(v_id, s_id)] = d_cant
                disponibilidad_map[v_id] = disponibilidad_map.get(v_id, 0) + d_cant

        # 6. Mapear temporadas y colecciones para enriquecer la instantánea
        q_temp = select(Temporada.id, Temporada.nombre).where(Temporada.empresa_id == empresa.id)
        res_temp = await self.db.execute(q_temp)
        mapa_temporadas = {row[0]: row[1] for row in res_temp.all()}

        q_col = select(Coleccion.id, Coleccion.nombre).where(Coleccion.empresa_id == empresa.id)
        res_col = await self.db.execute(q_col)
        mapa_colecciones = {row[0]: row[1] for row in res_col.all()}

        productos_dto: List[CatalogoDescargaProductoDTO] = []
        total_variantes = 0

        for p in productos:
            temporada_ids = await self.producto_repo.listarTemporadaIds(p.id)
            coleccion_ids = await self.producto_repo.listarColeccionIds(p.id)
            nombres_temporadas = [mapa_temporadas[tid] for tid in temporada_ids if tid in mapa_temporadas]
            nombres_colecciones = [mapa_colecciones[cid] for cid in coleccion_ids if cid in mapa_colecciones]

            variantes_dto: List[CatalogoDescargaVarianteDTO] = []
            for v in p.variantes:
                if not v.activa:
                    continue
                disp = disponibilidad_map.get(v.id, 0)
                disp_por_sucursal = [
                    DisponibilidadSucursalItemDTO(
                        sucursal_id=s_id,
                        disponible_conocido=disponibilidad_suc_map.get((v.id, s_id), 0),
                        actualizado_en=empresa.catalogo_actualizado_en or ahora_instante,
                    )
                    for s_id in ambito_sucursales
                ]
                precio_decimal = Decimal(str(v.precio or 0)).quantize(Decimal("0.01"))
                variantes_dto.append(
                    CatalogoDescargaVarianteDTO(
                        id=v.id,
                        sku=v.sku,
                        codigo_barras=v.codigo_barras,
                        talla_id=v.talla_id,
                        talla=v.talla.nombre if v.talla else "",
                        color_id=v.color_id,
                        color=v.color.nombre if v.color else "",
                        codigo_hex=v.color.codigo_hex if v.color else None,
                        precio_bob=f"{precio_decimal:.2f}",
                        disponibilidad=disp,
                        disponibilidad_por_sucursal=disp_por_sucursal,
                    )
                )

            total_variantes += len(variantes_dto)
            precio_base_decimal = Decimal(str(p.precio_base or 0)).quantize(Decimal("0.01"))

            productos_dto.append(
                CatalogoDescargaProductoDTO(
                    id=p.id,
                    categoria_id=p.categoria_id,
                    categoria=p.categoria.nombre if p.categoria else None,
                    nombre=p.nombre,
                    descripcion=p.descripcion,
                    genero=p.genero,
                    marca=p.marca,
                    precio_base_bob=f"{precio_base_decimal:.2f}",
                    imagenes=[ImagenProductoDTO.model_validate(img) for img in p.imagenes],
                    temporadas=nombres_temporadas,
                    colecciones=nombres_colecciones,
                    variantes=variantes_dto,
                )
            )

        return CatalogoDescargaDTO(
            empresa_id=empresa.id,
            empresa_codigo=empresa.codigo,
            empresa_nombre=empresa.nombre,
            sucursal_id=sucursal_id,
            ambito_sucursal=ambito_sucursal,
            catalogo_version=int(empresa.catalogo_version or 1),
            generado_en=ahora_instante,
            descargado_en=ahora_instante,
            ambito_sucursales=ambito_sucursales,
            sucursales=sucursales_dto,
            colores=colores_dto,
            promociones=promociones_dto,
            total_productos=len(productos_dto),
            total_variantes=total_variantes,
            productos=productos_dto,
        )


    async def consultarCatalogoPublico(
        self,
        empresa_id: Optional[uuid.UUID] = None,
        empresa_codigo: Optional[str] = None,
        texto: Optional[str] = None,
        categoria_id: Optional[uuid.UUID] = None,
        talla_id: Optional[uuid.UUID] = None,
        color_id: Optional[uuid.UUID] = None,
        componentes_color: Optional[List[uuid.UUID]] = None,
        modo_color: str = "EXACTO",
        temporada_id: Optional[uuid.UUID] = None,
        coleccion_id: Optional[uuid.UUID] = None,
        marca: Optional[str] = None,
        genero: Optional[str] = None,
        precio_min: Optional[float] = None,
        precio_max: Optional[float] = None,
        precio_min_bob: Optional[Decimal] = None,
        precio_max_bob: Optional[Decimal] = None,
        sucursal_id: Optional[uuid.UUID] = None,
        codigo_hex: Optional[str] = None,
        solo_activos: bool = True,
        limit: int = 50,
        offset: int = 0,
        paginado: bool = False,
    ):
        empresa = await self._empresa_publica(
            empresa_id=empresa_id, empresa_codigo=empresa_codigo
        )
        ahora = utcnow()

        p_min = precio_min_bob if precio_min_bob is not None else (Decimal(str(precio_min)) if precio_min is not None else None)
        p_max = precio_max_bob if precio_max_bob is not None else (Decimal(str(precio_max)) if precio_max is not None else None)
        if p_min is not None and p_max is not None and p_min > p_max:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="precio_min no puede ser mayor que precio_max")

        matching_colors = None
        if modo_color == "TODOS_COMPONENTES" and componentes_color:
            subq = (
                select(ColorComponente.color_id)
                .where(
                    ColorComponente.empresa_id == empresa.id,
                    ColorComponente.componente_id.in_(componentes_color),
                )
                .group_by(ColorComponente.color_id)
                .having(func.count(distinct(ColorComponente.componente_id)) == len(componentes_color))
            )
            matching_colors = list((await self.db.execute(subq)).scalars().all())
            if not matching_colors:
                if paginado:
                    return CatalogoProductosPaginadoDTO(total=0, limit=limit, offset=offset, items=[])
                return []
        elif modo_color == "EXACTO":
            if color_id is not None:
                matching_colors = [color_id]
            elif componentes_color:
                matching_colors = componentes_color

        q = (
            select(Producto)
            .options(
                selectinload(Producto.imagenes),
                selectinload(Producto.categoria),
                selectinload(Producto.variantes).selectinload(VarianteProducto.talla),
                selectinload(Producto.variantes).selectinload(VarianteProducto.color),
            )
            .distinct()
            .where(Producto.empresa_id == empresa.id)
        )
        if solo_activos:
            q = q.where(Producto.activo == True)
        if categoria_id:
            q = q.where(Producto.categoria_id == categoria_id)
        if genero:
            q = q.where(Producto.genero.ilike(genero.strip()))
        if marca:
            q = q.where(Producto.marca.ilike(marca.strip()))
        if texto:
            like = f"%{texto.strip()}%"
            q = q.where(or_(Producto.nombre.ilike(like), Producto.descripcion.ilike(like), Producto.marca.ilike(like)))
        if temporada_id:
            q = q.join(ProductoTemporada, ProductoTemporada.producto_id == Producto.id).where(ProductoTemporada.temporada_id == temporada_id)
        if coleccion_id:
            q = q.join(ProductoColeccion, ProductoColeccion.producto_id == Producto.id).where(ProductoColeccion.coleccion_id == coleccion_id)

        needs_variant_filter = (
            matching_colors is not None
            or talla_id is not None
            or p_min is not None
            or p_max is not None
            or codigo_hex is not None
            or sucursal_id is not None
        )
        if needs_variant_filter:
            q = q.join(VarianteProducto, VarianteProducto.producto_id == Producto.id)
            if solo_activos:
                q = q.where(VarianteProducto.activa == True)
            if matching_colors is not None:
                q = q.where(VarianteProducto.color_id.in_(matching_colors))
            if talla_id:
                q = q.where(VarianteProducto.talla_id == talla_id)
            if p_min is not None:
                q = q.where(VarianteProducto.precio >= p_min)
            if p_max is not None:
                q = q.where(VarianteProducto.precio <= p_max)
            if codigo_hex:
                q = q.join(Color, Color.id == VarianteProducto.color_id)
                hex_norm = f"#{codigo_hex.strip().upper().lstrip('#')}"
                q = q.where(Color.codigo_hex.ilike(hex_norm))
            if sucursal_id:
                q = q.join(
                    InventarioSucursal,
                    (InventarioSucursal.variante_id == VarianteProducto.id)
                    & (InventarioSucursal.sucursal_id == sucursal_id),
                ).where(InventarioSucursal.disponible > 0)

        sub = q.subquery()
        conteo_q = select(func.count(distinct(sub.c.id))).select_from(sub)
        total = int((await self.db.execute(conteo_q)).scalar() or 0)

        q = q.order_by(Producto.nombre).limit(limit).offset(offset)
        productos = list((await self.db.execute(q)).scalars().all())

        todas_variantes = [v for p in productos for v in p.variantes if v.activa]
        variante_ids = [v.id for v in todas_variantes]

        promociones_por_var: Dict[uuid.UUID, List[PromocionAplicableDTO]] = {}
        if variante_ids:
            from backend.app.core.modules.catalogo.models import Promocion, PromocionVariante
            q_pr = (
                select(Promocion, PromocionVariante.variante_id)
                .join(PromocionVariante, PromocionVariante.promocion_id == Promocion.id)
                .where(
                    PromocionVariante.variante_id.in_(variante_ids),
                    Promocion.activa == True,
                    (Promocion.vigencia_inicio.is_(None)) | (Promocion.vigencia_inicio <= ahora),
                    (Promocion.vigencia_fin.is_(None)) | (Promocion.vigencia_fin >= ahora),
                )
                .order_by(Promocion.codigo)
            )
            res_pr = await self.db.execute(q_pr)
            for row in res_pr.all():
                pr_model, v_id = row[0], row[1]
                dto_pr = PromocionAplicableDTO(
                    id=pr_model.id,
                    codigo=pr_model.codigo,
                    nombre=pr_model.nombre,
                    tipo=pr_model.tipo,
                    valor=f"{Decimal(str(pr_model.valor)):.2f}",
                    cantidad_minima=getattr(pr_model, "cantidad_minima", 1) or 1,
                    vigente_desde=pr_model.vigencia_inicio,
                    vigente_hasta=pr_model.vigencia_fin,
                )
                promociones_por_var.setdefault(v_id, []).append(dto_pr)

        disp_por_var_map: Dict[uuid.UUID, int] = {}
        if variante_ids:
            q_inv = (
                select(
                    InventarioSucursal.variante_id,
                    func.sum(InventarioSucursal.disponible).label("total_disp"),
                )
                .join(Sucursal, Sucursal.id == InventarioSucursal.sucursal_id)
                .where(
                    InventarioSucursal.variante_id.in_(variante_ids),
                    Sucursal.empresa_id == empresa.id,
                    Sucursal.activa == True,
                )
            )
            if sucursal_id is not None:
                q_inv = q_inv.where(InventarioSucursal.sucursal_id == sucursal_id)
            q_inv = q_inv.group_by(InventarioSucursal.variante_id)
            res_inv = await self.db.execute(q_inv)
            for row in res_inv.all():
                disp_por_var_map[row[0]] = max(0, int(row[1] or 0))

        productos_dto: List[ProductoPublicoDTO] = []
        for p in productos:
            temporada_ids = await self.producto_repo.listarTemporadaIds(p.id)
            coleccion_ids = await self.producto_repo.listarColeccionIds(p.id)
            imagenes = await self.producto_repo.listarImagenesPorProducto(p.id)

            variantes_pub: List[VariantePublicaDTO] = []
            for v in p.variantes:
                if not v.activa:
                    continue
                if matching_colors is not None and v.color_id not in matching_colors:
                    continue
                if talla_id is not None and v.talla_id != talla_id:
                    continue
                if p_min is not None and v.precio < p_min:
                    continue
                if p_max is not None and v.precio > p_max:
                    continue

                disp = disp_por_var_map.get(v.id, 0)
                precio_dec = Decimal(str(v.precio or 0)).quantize(Decimal("0.01"))
                promos = promociones_por_var.get(v.id, [])
                variantes_pub.append(
                    VariantePublicaDTO(
                        id=v.id,
                        producto_id=v.producto_id,
                        talla_id=v.talla_id,
                        color_id=v.color_id,
                        sku=v.sku,
                        codigo_barras=v.codigo_barras,
                        precio=v.precio,
                        peso_gramos=v.peso_gramos,
                        recurso_prueba_virtual=v.recurso_prueba_virtual,
                        activa=v.activa,
                        precio_bob=f"{precio_dec:.2f}",
                        disponibilidad=disp,
                        promociones=promos,
                    )
                )

            productos_dto.append(
                ProductoPublicoDTO(
                    id=p.id,
                    categoria_id=p.categoria_id,
                    nombre=p.nombre,
                    descripcion=p.descripcion,
                    genero=p.genero,
                    marca=p.marca,
                    precio_base=p.precio_base,
                    imagenes=[ImagenProductoDTO.model_validate(i) for i in imagenes],
                    temporada_ids=temporada_ids,
                    coleccion_ids=coleccion_ids,
                    variantes=variantes_pub,
                )
            )

        if paginado:
            return CatalogoProductosPaginadoDTO(
                total=total,
                limit=limit,
                offset=offset,
                items=productos_dto,
            )
        return productos_dto
