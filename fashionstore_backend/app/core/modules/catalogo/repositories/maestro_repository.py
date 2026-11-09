import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.catalogo.models import Talla, Color, ColorComponente, Categoria, Temporada, Coleccion
from sqlalchemy.orm import selectinload
from sqlalchemy import delete


class MaestroRepository:
    """
    Datos MaestroRepository.* para CU05
    Maneja Tallas, Colores, Categorias, Temporadas, Colecciones
    """
    def __init__(self, db: AsyncSession, empresa_id: Optional[uuid.UUID] = None):
        self.db = db
        self.empresa_id = empresa_id

    def _ambito(self, consulta, modelo):
        return consulta.where(modelo.empresa_id == self.empresa_id) if self.empresa_id else consulta

    # ---------- Talla ----------
    async def buscarTallaPorId(self, talla_id: uuid.UUID) -> Optional[Talla]:
        result = await self.db.execute(self._ambito(select(Talla).where(Talla.id == talla_id), Talla))
        return result.scalars().first()

    async def buscarTallaPorNombre(self, nombre: str) -> Optional[Talla]:
        result = await self.db.execute(self._ambito(select(Talla).where(Talla.nombre.ilike(nombre.strip())), Talla))
        return result.scalars().first()

    async def listarTallas(self, solo_activas: bool = False) -> List[Talla]:
        q = self._ambito(select(Talla), Talla)
        if solo_activas:
            q = q.where(Talla.activo == True)
        q = q.order_by(Talla.orden, Talla.nombre)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def crearTalla(self, talla: Talla) -> Talla:
        self.db.add(talla)
        await self.db.flush()
        return talla

    async def actualizarTalla(self, talla: Talla) -> Talla:
        await self.db.flush()
        return talla

    # ---------- Color ----------
    async def buscarColorPorId(self, color_id: uuid.UUID) -> Optional[Color]:
        result = await self.db.execute(self._ambito(select(Color).where(Color.id == color_id), Color))
        return result.scalars().first()

    async def buscarColorPorNombre(self, nombre: str) -> Optional[Color]:
        result = await self.db.execute(self._ambito(select(Color).where(Color.nombre.ilike(nombre.strip())), Color))
        return result.scalars().first()

    async def listarColores(self, solo_activos: bool = False) -> List[Color]:
        q = self._ambito(select(Color), Color)
        if solo_activos:
            q = q.where(Color.activo == True)
        q = q.order_by(Color.nombre)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def crearColor(self, color: Color) -> Color:
        self.db.add(color)
        await self.db.flush()
        return color

    async def actualizarColor(self, color: Color) -> Color:
        await self.db.flush()
        return color
    async def buscarColorConComponentes(self, color_id: uuid.UUID) -> Optional[Color]:
        q = self._ambito(
            select(Color).options(selectinload(Color.componentes)).where(Color.id == color_id),
            Color,
        )
        result = await self.db.execute(q)
        return result.scalars().first()

    async def asociarComponentes(
        self, color_id: uuid.UUID, componente_ids: List[uuid.UUID]
    ) -> List[ColorComponente]:
        await self.db.execute(
            delete(ColorComponente).where(ColorComponente.color_id == color_id)
        )
        componentes = []
        for orden, comp_id in enumerate(componente_ids):
            cc = ColorComponente(
                id=uuid.uuid4(),
                empresa_id=self.empresa_id,
                color_id=color_id,
                componente_id=comp_id,
                orden=orden,
            )
            self.db.add(cc)
            componentes.append(cc)
        await self.db.flush()
        return componentes

    async def listarColoresConComponentes(self, solo_activos: bool = False) -> List[Color]:
        q = self._ambito(select(Color).options(selectinload(Color.componentes)), Color)
        if solo_activos:
            q = q.where(Color.activo == True)
        q = q.order_by(Color.nombre)
        result = await self.db.execute(q)
        return list(result.scalars().all())


    # ---------- Categoria ----------
    async def buscarCategoriaPorId(self, categoria_id: uuid.UUID) -> Optional[Categoria]:
        result = await self.db.execute(self._ambito(select(Categoria).where(Categoria.id == categoria_id), Categoria))
        return result.scalars().first()

    async def buscarCategoriaPorNombreYPadre(self, nombre: str, categoria_padre_id: Optional[uuid.UUID]) -> Optional[Categoria]:
        if categoria_padre_id is None:
            q = select(Categoria).where(Categoria.categoria_padre_id.is_(None), Categoria.nombre.ilike(nombre.strip()))
        else:
            q = select(Categoria).where(Categoria.categoria_padre_id == categoria_padre_id, Categoria.nombre.ilike(nombre.strip()))
        result = await self.db.execute(self._ambito(q, Categoria))
        return result.scalars().first()

    async def listarCategorias(self, solo_activas: bool = False) -> List[Categoria]:
        q = self._ambito(select(Categoria), Categoria)
        if solo_activas:
            q = q.where(Categoria.activo == True)
        q = q.order_by(Categoria.nombre)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def crearCategoria(self, categoria: Categoria) -> Categoria:
        self.db.add(categoria)
        await self.db.flush()
        return categoria

    async def actualizarCategoria(self, categoria: Categoria) -> Categoria:
        await self.db.flush()
        return categoria

    # ---------- Temporada ----------
    async def buscarTemporadaPorId(self, temporada_id: uuid.UUID) -> Optional[Temporada]:
        result = await self.db.execute(self._ambito(select(Temporada).where(Temporada.id == temporada_id), Temporada))
        return result.scalars().first()

    async def buscarTemporadaPorNombre(self, nombre: str) -> Optional[Temporada]:
        result = await self.db.execute(self._ambito(select(Temporada).where(Temporada.nombre.ilike(nombre.strip())), Temporada))
        return result.scalars().first()

    async def listarTemporadas(self, solo_activas: bool = False) -> List[Temporada]:
        q = self._ambito(select(Temporada), Temporada)
        if solo_activas:
            q = q.where(Temporada.activa == True)
        q = q.order_by(Temporada.nombre)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def crearTemporada(self, temporada: Temporada) -> Temporada:
        self.db.add(temporada)
        await self.db.flush()
        return temporada

    async def actualizarTemporada(self, temporada: Temporada) -> Temporada:
        await self.db.flush()
        return temporada

    # ---------- Coleccion ----------
    async def buscarColeccionPorId(self, coleccion_id: uuid.UUID) -> Optional[Coleccion]:
        result = await self.db.execute(self._ambito(select(Coleccion).where(Coleccion.id == coleccion_id), Coleccion))
        return result.scalars().first()

    async def buscarColeccionPorNombre(self, nombre: str) -> Optional[Coleccion]:
        result = await self.db.execute(self._ambito(select(Coleccion).where(Coleccion.nombre.ilike(nombre.strip())), Coleccion))
        return result.scalars().first()

    async def listarColecciones(self, solo_activas: bool = False) -> List[Coleccion]:
        q = self._ambito(select(Coleccion), Coleccion)
        if solo_activas:
            q = q.where(Coleccion.activa == True)
        q = q.order_by(Coleccion.nombre)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def crearColeccion(self, coleccion: Coleccion) -> Coleccion:
        self.db.add(coleccion)
        await self.db.flush()
        return coleccion

    async def actualizarColeccion(self, coleccion: Coleccion) -> Coleccion:
        await self.db.flush()
        return coleccion
