import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.catalogo.models import (
    Producto, ImagenProducto, ProductoTemporada, ProductoColeccion, VarianteProducto, Color,
)


class ProductoRepository:
    """
    Datos ProductoRepository.* para CU05 (y base buscarConFiltros para CU06)
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def buscarPorId(
        self, producto_id: uuid.UUID, empresa_id: Optional[uuid.UUID] = None
    ) -> Optional[Producto]:
        q = select(Producto).options(selectinload(Producto.imagenes)).where(Producto.id == producto_id)
        if empresa_id is not None:
            q = q.where(Producto.empresa_id == empresa_id)
        result = await self.db.execute(q)
        return result.scalars().first()

    async def buscarPorNombre(
        self, nombre: str, empresa_id: Optional[uuid.UUID] = None
    ) -> Optional[Producto]:
        q = select(Producto).where(Producto.nombre.ilike(nombre.strip()))
        if empresa_id is not None:
            q = q.where(Producto.empresa_id == empresa_id)
        result = await self.db.execute(q)
        return result.scalars().first()

    async def listar(
        self,
        solo_activos: bool = False,
        limit: int = 50,
        offset: int = 0,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> List[Producto]:
        q = select(Producto).options(selectinload(Producto.imagenes))
        if empresa_id is not None:
            q = q.where(Producto.empresa_id == empresa_id)
        if solo_activos:
            q = q.where(Producto.activo == True)
        q = q.order_by(Producto.nombre).limit(limit).offset(offset)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def crear(self, producto: Producto) -> Producto:
        self.db.add(producto)
        await self.db.flush()
        return producto

    async def actualizar(self, producto: Producto) -> Producto:
        await self.db.flush()
        return producto

    async def buscarConFiltros(
        self,
        texto: Optional[str] = None,
        categoria_id: Optional[uuid.UUID] = None,
        genero: Optional[str] = None,
        marca: Optional[str] = None,
        precio_min: Optional[float] = None,
        precio_max: Optional[float] = None,
        solo_activos: bool = True,
        limit: int = 50,
        offset: int = 0,
        talla_id: Optional[uuid.UUID] = None,
        color_id: Optional[uuid.UUID] = None,
        temporada_id: Optional[uuid.UUID] = None,
        coleccion_id: Optional[uuid.UUID] = None,
        busqueda: Optional[str] = None,
        codigo_hex: Optional[str] = None,
        filtros: Optional[Dict[str, Any]] = None,
        empresa_id: Optional[uuid.UUID] = None,
    ) -> List[Producto]:
        """
        CU06 - buscarConFiltros completo: filtra productos por categoria, talla, color, temporada, coleccion, precio, texto, genero, marca.
        """
        if filtros is not None and isinstance(filtros, dict):
            texto = filtros.get("texto", filtros.get("busqueda", filtros.get("q", texto)))
            busqueda = filtros.get("busqueda", busqueda)
            categoria_id = filtros.get("categoria_id", categoria_id)
            talla_id = filtros.get("talla_id", talla_id)
            color_id = filtros.get("color_id", color_id)
            temporada_id = filtros.get("temporada_id", temporada_id)
            coleccion_id = filtros.get("coleccion_id", coleccion_id)
            genero = filtros.get("genero", genero)
            marca = filtros.get("marca", marca)
            precio_min = filtros.get("precio_min", precio_min)
            precio_max = filtros.get("precio_max", precio_max)
            if "activo" in filtros:
                solo_activos = filtros["activo"] is True or filtros["activo"] == "true"
                if filtros["activo"] is False or filtros["activo"] == "false":
                    solo_activos = False
            codigo_hex = filtros.get("codigo_hex", filtros.get("color_hex", codigo_hex))
            if texto is None and busqueda:
                texto = busqueda

        if busqueda and not texto:
            texto = busqueda

        q = select(Producto).options(selectinload(Producto.imagenes)).distinct()

        necesita_variante = talla_id is not None or color_id is not None or codigo_hex is not None
        if necesita_variante:
            q = q.join(VarianteProducto, VarianteProducto.producto_id == Producto.id)
            if talla_id:
                if isinstance(talla_id, str):
                    try:
                        talla_id = uuid.UUID(talla_id)
                    except Exception:
                        pass
                q = q.where(VarianteProducto.talla_id == talla_id)
            if color_id:
                if isinstance(color_id, str):
                    try:
                        color_id = uuid.UUID(color_id)
                    except Exception:
                        pass
                q = q.where(VarianteProducto.color_id == color_id)
            if codigo_hex:
                q = q.join(Color, Color.id == VarianteProducto.color_id)
                hex_norm = codigo_hex.strip().upper()
                if not hex_norm.startswith("#"):
                    hex_norm = f"#{hex_norm}"
                q = q.where(Color.codigo_hex.ilike(hex_norm))

        if temporada_id:
            if isinstance(temporada_id, str):
                try:
                    temporada_id = uuid.UUID(temporada_id)
                except Exception:
                    pass
            q = q.join(ProductoTemporada, ProductoTemporada.producto_id == Producto.id)
            q = q.where(ProductoTemporada.temporada_id == temporada_id)

        if coleccion_id:
            if isinstance(coleccion_id, str):
                try:
                    coleccion_id = uuid.UUID(coleccion_id)
                except Exception:
                    pass
            q = q.join(ProductoColeccion, ProductoColeccion.producto_id == Producto.id)
            q = q.where(ProductoColeccion.coleccion_id == coleccion_id)

        if filtros and "empresa_id" in filtros and empresa_id is None:
            empresa_id = filtros.get("empresa_id")

        if empresa_id:
            if isinstance(empresa_id, str):
                try:
                    empresa_id = uuid.UUID(empresa_id)
                except Exception:
                    pass
            q = q.where(Producto.empresa_id == empresa_id)

        if solo_activos:
            q = q.where(Producto.activo == True)
        if texto:
            like = f"%{texto.strip()}%"
            q = q.where(or_(Producto.nombre.ilike(like), Producto.descripcion.ilike(like), Producto.marca.ilike(like)))
        if categoria_id:
            if isinstance(categoria_id, str):
                try:
                    categoria_id = uuid.UUID(categoria_id)
                except Exception:
                    pass
            q = q.where(Producto.categoria_id == categoria_id)
        if genero:
            q = q.where(Producto.genero.ilike(genero.strip()))
        if marca:
            q = q.where(Producto.marca.ilike(marca.strip()))
        if precio_min is not None:
            q = q.where(Producto.precio_base >= precio_min)
        if precio_max is not None:
            q = q.where(Producto.precio_base <= precio_max)
        q = q.order_by(Producto.nombre).limit(limit).offset(offset)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def obtenerInstantaneaDescarga(
        self, empresa_id: uuid.UUID
    ) -> List[Producto]:
        q = (
            select(Producto)
            .options(
                selectinload(Producto.imagenes),
                selectinload(Producto.categoria),
                selectinload(Producto.variantes).selectinload(VarianteProducto.talla),
                selectinload(Producto.variantes).selectinload(VarianteProducto.color),
            )
            .where(Producto.empresa_id == empresa_id, Producto.activo == True)
            .order_by(Producto.nombre)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def listarImagenesPorProducto(self, producto_id: uuid.UUID) -> List[ImagenProducto]:
        q = select(ImagenProducto).where(ImagenProducto.producto_id == producto_id).order_by(ImagenProducto.orden)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def crearImagen(self, imagen: ImagenProducto) -> ImagenProducto:
        self.db.add(imagen)
        await self.db.flush()
        return imagen

    async def listarTemporadaIds(self, producto_id: uuid.UUID) -> List[uuid.UUID]:
        q = select(ProductoTemporada.temporada_id).where(ProductoTemporada.producto_id == producto_id)
        result = await self.db.execute(q)
        return [row[0] for row in result.all()]

    async def listarColeccionIds(self, producto_id: uuid.UUID) -> List[uuid.UUID]:
        q = select(ProductoColeccion.coleccion_id).where(ProductoColeccion.producto_id == producto_id)
        result = await self.db.execute(q)
        return [row[0] for row in result.all()]

    async def asociarTemporadas(self, producto_id: uuid.UUID, temporada_ids: List[uuid.UUID]):
        for tid in temporada_ids:
            assoc = ProductoTemporada(producto_id=producto_id, temporada_id=tid)
            self.db.add(assoc)
        await self.db.flush()

    async def asociarColecciones(self, producto_id: uuid.UUID, coleccion_ids: List[uuid.UUID]):
        for cid in coleccion_ids:
            assoc = ProductoColeccion(producto_id=producto_id, coleccion_id=cid)
            self.db.add(assoc)
        await self.db.flush()

    async def limpiarTemporadas(self, producto_id: uuid.UUID):
        from sqlalchemy import delete
        await self.db.execute(delete(ProductoTemporada).where(ProductoTemporada.producto_id == producto_id))
        await self.db.flush()

    async def limpiarColecciones(self, producto_id: uuid.UUID):
        from sqlalchemy import delete
        await self.db.execute(delete(ProductoColeccion).where(ProductoColeccion.producto_id == producto_id))
        await self.db.flush()

    async def limpiarImagenes(self, producto_id: uuid.UUID):
        from sqlalchemy import delete
        await self.db.execute(delete(ImagenProducto).where(ImagenProducto.producto_id == producto_id))
        await self.db.flush()
