import uuid
from typing import List
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.catalogo.models import Talla, Color, Categoria, Temporada, Coleccion
from backend.app.core.modules.catalogo.schemas import (
    TallaCrearDTO, TallaDTO, TallaActualizarDTO,
    ColorCrearDTO, ColorDTO, ColorActualizarDTO,
    CategoriaCrearDTO, CategoriaDTO, CategoriaActualizarDTO,
    TemporadaCrearDTO, TemporadaDTO, TemporadaActualizarDTO,
    ColeccionCrearDTO, ColeccionDTO, ColeccionActualizarDTO,
)
from backend.app.core.modules.catalogo.repositories.maestro_repository import MaestroRepository


class MaestroService:
    """
    Controller MaestroService.* para CU05
    Presentación gestionarMaestros() -> Controller MaestroService.crearTalla()/crearColor()/crearCategoria()/crearTemporada()/crearColeccion()
    -> Datos MaestroRepository.*
    """
    def __init__(self, db: AsyncSession, empresa_id: uuid.UUID | None = None):
        self.db = db
        self.empresa_id = empresa_id
        self.repo = MaestroRepository(db, empresa_id=empresa_id)

    def _exigir_empresa(self) -> uuid.UUID:
        if self.empresa_id is None:
            raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
        return self.empresa_id

    # ---------- Talla ----------
    async def crearTalla(self, dto: TallaCrearDTO) -> TallaDTO:
        existente = await self.repo.buscarTallaPorNombre(dto.nombre)
        if existente:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una talla con nombre '{dto.nombre.strip()}'")
        talla = Talla(empresa_id=self._exigir_empresa(), nombre=dto.nombre.strip(), orden=dto.orden, activo=dto.activo)
        await self.repo.crearTalla(talla)
        await self.db.commit()
        await self.db.refresh(talla)
        return TallaDTO.model_validate(talla)

    async def listarTallas(self, solo_activas: bool = False) -> List[TallaDTO]:
        tallas = await self.repo.listarTallas(solo_activas=solo_activas)
        return [TallaDTO.model_validate(t) for t in tallas]

    async def obtenerTallaPorId(self, talla_id: uuid.UUID) -> TallaDTO:
        talla = await self.repo.buscarTallaPorId(talla_id)
        if not talla:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Talla no encontrada")
        return TallaDTO.model_validate(talla)

    async def actualizarTalla(self, talla_id: uuid.UUID, dto: TallaActualizarDTO) -> TallaDTO:
        talla = await self.repo.buscarTallaPorId(talla_id)
        if not talla:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Talla no encontrada")
        if dto.nombre is not None:
            existente = await self.repo.buscarTallaPorNombre(dto.nombre)
            if existente and existente.id != talla_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una talla con nombre '{dto.nombre.strip()}'")
            talla.nombre = dto.nombre.strip()
        if dto.orden is not None:
            talla.orden = dto.orden
        if dto.activo is not None:
            talla.activo = dto.activo
        await self.repo.actualizarTalla(talla)
        await self.db.commit()
        await self.db.refresh(talla)
        return TallaDTO.model_validate(talla)

    # ---------- Color ----------
    async def crearColor(self, dto: ColorCrearDTO) -> ColorDTO:
        existente = await self.repo.buscarColorPorNombre(dto.nombre)
        if existente:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe un color con nombre '{dto.nombre.strip()}'")
        color = Color(empresa_id=self._exigir_empresa(), nombre=dto.nombre.strip(), codigo_hex=dto.codigo_hex, activo=dto.activo)
        await self.repo.crearColor(color)
        await self.db.commit()
        await self.db.refresh(color)
        return ColorDTO.model_validate(color)

    async def listarColores(self, solo_activos: bool = False) -> List[ColorDTO]:
        colores = await self.repo.listarColores(solo_activos=solo_activos)
        return [ColorDTO.model_validate(c) for c in colores]

    async def obtenerColorPorId(self, color_id: uuid.UUID) -> ColorDTO:
        color = await self.repo.buscarColorPorId(color_id)
        if not color:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Color no encontrado")
        return ColorDTO.model_validate(color)

    async def actualizarColor(self, color_id: uuid.UUID, dto: ColorActualizarDTO) -> ColorDTO:
        color = await self.repo.buscarColorPorId(color_id)
        if not color:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Color no encontrado")
        if dto.nombre is not None:
            existente = await self.repo.buscarColorPorNombre(dto.nombre)
            if existente and existente.id != color_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe un color con nombre '{dto.nombre.strip()}'")
            color.nombre = dto.nombre.strip()
        if dto.codigo_hex is not None:
            color.codigo_hex = dto.codigo_hex
        if dto.activo is not None:
            color.activo = dto.activo
        await self.repo.actualizarColor(color)
        await self.db.commit()
        await self.db.refresh(color)
        return ColorDTO.model_validate(color)

    # ---------- Categoria ----------
    async def crearCategoria(self, dto: CategoriaCrearDTO) -> CategoriaDTO:
        if dto.categoria_padre_id:
            padre = await self.repo.buscarCategoriaPorId(dto.categoria_padre_id)
            if not padre:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría padre no encontrada")
        existente = await self.repo.buscarCategoriaPorNombreYPadre(dto.nombre, dto.categoria_padre_id)
        if existente:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una categoría con nombre '{dto.nombre.strip()}' bajo el mismo padre")
        categoria = Categoria(empresa_id=self._exigir_empresa(), nombre=dto.nombre.strip(), descripcion=dto.descripcion.strip() if dto.descripcion else None, categoria_padre_id=dto.categoria_padre_id, activo=dto.activo)
        await self.repo.crearCategoria(categoria)
        await self.db.commit()
        await self.db.refresh(categoria)
        return CategoriaDTO.model_validate(categoria)

    async def listarCategorias(self, solo_activas: bool = False) -> List[CategoriaDTO]:
        cats = await self.repo.listarCategorias(solo_activas=solo_activas)
        return [CategoriaDTO.model_validate(c) for c in cats]

    async def obtenerCategoriaPorId(self, categoria_id: uuid.UUID) -> CategoriaDTO:
        cat = await self.repo.buscarCategoriaPorId(categoria_id)
        if not cat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
        return CategoriaDTO.model_validate(cat)

    async def actualizarCategoria(self, categoria_id: uuid.UUID, dto: CategoriaActualizarDTO) -> CategoriaDTO:
        cat = await self.repo.buscarCategoriaPorId(categoria_id)
        if not cat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
        nuevo_padre = dto.categoria_padre_id if dto.categoria_padre_id is not None else cat.categoria_padre_id
        nuevo_nombre = dto.nombre.strip() if dto.nombre else cat.nombre
        if dto.categoria_padre_id is not None:
            if dto.categoria_padre_id == categoria_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Una categoría no puede ser su propio padre")
            padre = await self.repo.buscarCategoriaPorId(dto.categoria_padre_id)
            if not padre:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría padre no encontrada")
        if dto.nombre is not None or dto.categoria_padre_id is not None:
            existente = await self.repo.buscarCategoriaPorNombreYPadre(nuevo_nombre, nuevo_padre)
            if existente and existente.id != categoria_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una categoría con nombre '{nuevo_nombre}' bajo el mismo padre")
        if dto.nombre is not None:
            cat.nombre = dto.nombre.strip()
        if dto.descripcion is not None:
            cat.descripcion = dto.descripcion.strip() if dto.descripcion else None
        if dto.categoria_padre_id is not None:
            cat.categoria_padre_id = dto.categoria_padre_id
        if dto.activo is not None:
            cat.activo = dto.activo
        await self.repo.actualizarCategoria(cat)
        await self.db.commit()
        await self.db.refresh(cat)
        return CategoriaDTO.model_validate(cat)

    # ---------- Temporada ----------
    async def crearTemporada(self, dto: TemporadaCrearDTO) -> TemporadaDTO:
        existente = await self.repo.buscarTemporadaPorNombre(dto.nombre)
        if existente:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una temporada con nombre '{dto.nombre.strip()}'")
        temporada = Temporada(empresa_id=self._exigir_empresa(), nombre=dto.nombre.strip(), fecha_inicio=dto.fecha_inicio, fecha_fin=dto.fecha_fin, activa=dto.activa)
        await self.repo.crearTemporada(temporada)
        await self.db.commit()
        await self.db.refresh(temporada)
        return TemporadaDTO.model_validate(temporada)

    async def listarTemporadas(self, solo_activas: bool = False) -> List[TemporadaDTO]:
        temps = await self.repo.listarTemporadas(solo_activas=solo_activas)
        return [TemporadaDTO.model_validate(t) for t in temps]

    async def obtenerTemporadaPorId(self, temporada_id: uuid.UUID) -> TemporadaDTO:
        temp = await self.repo.buscarTemporadaPorId(temporada_id)
        if not temp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporada no encontrada")
        return TemporadaDTO.model_validate(temp)

    async def actualizarTemporada(self, temporada_id: uuid.UUID, dto: TemporadaActualizarDTO) -> TemporadaDTO:
        temp = await self.repo.buscarTemporadaPorId(temporada_id)
        if not temp:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporada no encontrada")
        if dto.nombre is not None:
            existente = await self.repo.buscarTemporadaPorNombre(dto.nombre)
            if existente and existente.id != temporada_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una temporada con nombre '{dto.nombre.strip()}'")
            temp.nombre = dto.nombre.strip()
        if dto.fecha_inicio is not None:
            temp.fecha_inicio = dto.fecha_inicio
        if dto.fecha_fin is not None:
            temp.fecha_fin = dto.fecha_fin
        if temp.fecha_inicio and temp.fecha_fin and temp.fecha_fin < temp.fecha_inicio:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fecha_fin no puede ser anterior a fecha_inicio")
        if dto.activa is not None:
            temp.activa = dto.activa
        await self.repo.actualizarTemporada(temp)
        await self.db.commit()
        await self.db.refresh(temp)
        return TemporadaDTO.model_validate(temp)

    # ---------- Coleccion ----------
    async def crearColeccion(self, dto: ColeccionCrearDTO) -> ColeccionDTO:
        existente = await self.repo.buscarColeccionPorNombre(dto.nombre)
        if existente:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una colección con nombre '{dto.nombre.strip()}'")
        coleccion = Coleccion(empresa_id=self._exigir_empresa(), nombre=dto.nombre.strip(), descripcion=dto.descripcion.strip() if dto.descripcion else None, activa=dto.activa)
        await self.repo.crearColeccion(coleccion)
        await self.db.commit()
        await self.db.refresh(coleccion)
        return ColeccionDTO.model_validate(coleccion)

    async def listarColecciones(self, solo_activas: bool = False) -> List[ColeccionDTO]:
        cols = await self.repo.listarColecciones(solo_activas=solo_activas)
        return [ColeccionDTO.model_validate(c) for c in cols]

    async def obtenerColeccionPorId(self, coleccion_id: uuid.UUID) -> ColeccionDTO:
        col = await self.repo.buscarColeccionPorId(coleccion_id)
        if not col:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colección no encontrada")
        return ColeccionDTO.model_validate(col)

    async def actualizarColeccion(self, coleccion_id: uuid.UUID, dto: ColeccionActualizarDTO) -> ColeccionDTO:
        col = await self.repo.buscarColeccionPorId(coleccion_id)
        if not col:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colección no encontrada")
        if dto.nombre is not None:
            existente = await self.repo.buscarColeccionPorNombre(dto.nombre)
            if existente and existente.id != coleccion_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe una colección con nombre '{dto.nombre.strip()}'")
            col.nombre = dto.nombre.strip()
        if dto.descripcion is not None:
            col.descripcion = dto.descripcion.strip() if dto.descripcion else None
        if dto.activa is not None:
            col.activa = dto.activa
        await self.repo.actualizarColeccion(col)
        await self.db.commit()
        await self.db.refresh(col)
        return ColeccionDTO.model_validate(col)
