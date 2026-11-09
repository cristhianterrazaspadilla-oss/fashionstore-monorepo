import uuid
from typing import List
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.modules.catalogo.models import Producto, ImagenProducto
from backend.app.core.modules.catalogo.schemas import ProductoCrearDTO, ProductoDTO, ProductoActualizarDTO, ImagenProductoDTO
from backend.app.core.modules.catalogo.repositories.producto_repository import ProductoRepository
from backend.app.core.modules.catalogo.repositories.maestro_repository import MaestroRepository
from backend.app.core.modules.inventario.repositories.proveedor_repository import ProveedorRepository

class ProductoService:
    """
    Controller ProductoService.crear()/actualizar() para CU05
    Presentación gestionarProductos() -> Controller ProductoService.* -> Datos ProductoRepository.*
    """
    def __init__(self, db: AsyncSession, empresa_id: uuid.UUID | None = None):
        self.db = db
        self.empresa_id = empresa_id
        self.producto_repo = ProductoRepository(db)
        self.maestro_repo = MaestroRepository(db)
        self.proveedor_repo = ProveedorRepository(db)

    async def _validar_referencias(self, dto: ProductoCrearDTO):
        if dto.categoria_id:
            cat = await self.maestro_repo.buscarCategoriaPorId(dto.categoria_id)
            if not cat or cat.empresa_id != self.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
            if not cat.activo:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Categoría inactiva")
        if dto.proveedor_principal_id:
            prov = await self.proveedor_repo.buscarPorId(dto.proveedor_principal_id)
            if not prov or prov.empresa_id != self.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor principal no encontrado")
            if not prov.activo:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proveedor inactivo")
        for tid in dto.temporada_ids:
            temp = await self.maestro_repo.buscarTemporadaPorId(tid)
            if not temp or temp.empresa_id != self.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Temporada {tid} no encontrada")
            if not temp.activa:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Temporada {temp.nombre} inactiva")
        for cid in dto.coleccion_ids:
            col = await self.maestro_repo.buscarColeccionPorId(cid)
            if not col or col.empresa_id != self.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Colección {cid} no encontrada")
            if not col.activa:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Colección {col.nombre} inactiva")
        if dto.imagenes:
            principales = [i for i in dto.imagenes if i.es_principal]
            if len(principales) > 1:
                first = True
                for img in dto.imagenes:
                    if img.es_principal:
                        if first:
                            first = False
                        else:
                            img.es_principal = False

    async def crear(self, dto: ProductoCrearDTO) -> ProductoDTO:
        if self.empresa_id is None:
            raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
        await self._validar_referencias(dto)
        try:
            producto = Producto(
                empresa_id=self.empresa_id,
                nombre=dto.nombre.strip(),
                descripcion=dto.descripcion.strip() if dto.descripcion else None,
                categoria_id=dto.categoria_id,
                proveedor_principal_id=dto.proveedor_principal_id,
                genero=dto.genero.strip() if dto.genero else None,
                marca=dto.marca.strip() if dto.marca else None,
                precio_base=dto.precio_base,
                activo=dto.activo,
            )
            await self.producto_repo.crear(producto)
            await self.db.flush()

            for img_dto in dto.imagenes:
                imagen = ImagenProducto(
                    producto_id=producto.id,
                    enlace_imagen=img_dto.enlace_imagen.strip(),
                    texto_alternativo=img_dto.texto_alternativo.strip() if img_dto.texto_alternativo else None,
                    orden=img_dto.orden,
                    es_principal=img_dto.es_principal
                )
                await self.producto_repo.crearImagen(imagen)

            if dto.temporada_ids:
                await self.producto_repo.asociarTemporadas(producto.id, dto.temporada_ids)
            if dto.coleccion_ids:
                await self.producto_repo.asociarColecciones(producto.id, dto.coleccion_ids)

            await self.db.commit()
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al crear producto: {str(e)}")

        producto_completo = await self.producto_repo.buscarPorId(producto.id)
        imagenes = await self.producto_repo.listarImagenesPorProducto(producto.id)
        temporada_ids = await self.producto_repo.listarTemporadaIds(producto.id)
        coleccion_ids = await self.producto_repo.listarColeccionIds(producto.id)

        return ProductoDTO(
            id=producto_completo.id,
            categoria_id=producto_completo.categoria_id,
            proveedor_principal_id=producto_completo.proveedor_principal_id,
            nombre=producto_completo.nombre,
            descripcion=producto_completo.descripcion,
            genero=producto_completo.genero,
            marca=producto_completo.marca,
            precio_base=producto_completo.precio_base,
            activo=producto_completo.activo,
            creado_en=producto_completo.creado_en,
            actualizado_en=producto_completo.actualizado_en,
            imagenes=[ImagenProductoDTO.model_validate(i) for i in imagenes],
            temporada_ids=temporada_ids,
            coleccion_ids=coleccion_ids
        )

    async def actualizar(self, producto_id: uuid.UUID, dto: ProductoActualizarDTO) -> ProductoDTO:
        if self.empresa_id is None:
            raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
        producto = await self.producto_repo.buscarPorId(producto_id, empresa_id=self.empresa_id)
        if not producto:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")

        if "categoria_id" in dto.model_fields_set:
            if dto.categoria_id:
                cat = await self.maestro_repo.buscarCategoriaPorId(dto.categoria_id)
                if not cat or cat.empresa_id != self.empresa_id:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
                if not cat.activo:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Categoría inactiva")
                producto.categoria_id = dto.categoria_id
            else:
                producto.categoria_id = None

        if "proveedor_principal_id" in dto.model_fields_set:
            if dto.proveedor_principal_id:
                prov = await self.proveedor_repo.buscarPorId(dto.proveedor_principal_id)
                if not prov or prov.empresa_id != self.empresa_id:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor principal no encontrado")
                producto.proveedor_principal_id = dto.proveedor_principal_id
            else:
                producto.proveedor_principal_id = None

        if "nombre" in dto.model_fields_set and dto.nombre is not None:
            producto.nombre = dto.nombre.strip()

        if "descripcion" in dto.model_fields_set:
            producto.descripcion = dto.descripcion.strip() if dto.descripcion and dto.descripcion.strip() else None

        if "genero" in dto.model_fields_set:
            producto.genero = dto.genero.strip() if dto.genero and dto.genero.strip() else None

        if "marca" in dto.model_fields_set:
            producto.marca = dto.marca.strip() if dto.marca and dto.marca.strip() else None

        if "precio_base" in dto.model_fields_set and dto.precio_base is not None:
            producto.precio_base = dto.precio_base

        if "activo" in dto.model_fields_set and dto.activo is not None:
            producto.activo = dto.activo

        try:
            await self.producto_repo.actualizar(producto)
            if dto.imagenes is not None:
                await self.producto_repo.limpiarImagenes(producto.id)
                principales = [i for i in dto.imagenes if i.es_principal]
                if len(principales) > 1:
                    first = True
                    for img in dto.imagenes:
                        if img.es_principal:
                            if first:
                                first = False
                            else:
                                img.es_principal = False
                for img_dto in dto.imagenes:
                    imagen = ImagenProducto(
                        producto_id=producto.id,
                        enlace_imagen=img_dto.enlace_imagen.strip(),
                        texto_alternativo=img_dto.texto_alternativo.strip() if img_dto.texto_alternativo else None,
                        orden=img_dto.orden,
                        es_principal=img_dto.es_principal
                    )
                    await self.producto_repo.crearImagen(imagen)

            if dto.temporada_ids is not None:
                await self.producto_repo.limpiarTemporadas(producto.id)
                if dto.temporada_ids:
                    for tid in dto.temporada_ids:
                        temp = await self.maestro_repo.buscarTemporadaPorId(tid)
                        if not temp or temp.empresa_id != self.empresa_id:
                            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Temporada {tid} no encontrada")
                    await self.producto_repo.asociarTemporadas(producto.id, dto.temporada_ids)

            if dto.coleccion_ids is not None:
                await self.producto_repo.limpiarColecciones(producto.id)
                if dto.coleccion_ids:
                    for cid in dto.coleccion_ids:
                        col = await self.maestro_repo.buscarColeccionPorId(cid)
                        if not col or col.empresa_id != self.empresa_id:
                            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Colección {cid} no encontrada")
                    await self.producto_repo.asociarColecciones(producto.id, dto.coleccion_ids)

            await self.db.commit()
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al actualizar producto: {str(e)}")

        await self.db.refresh(producto)
        imagenes = await self.producto_repo.listarImagenesPorProducto(producto.id)
        temporada_ids = await self.producto_repo.listarTemporadaIds(producto.id)
        coleccion_ids = await self.producto_repo.listarColeccionIds(producto.id)

        return ProductoDTO(
            id=producto.id,
            categoria_id=producto.categoria_id,
            proveedor_principal_id=producto.proveedor_principal_id,
            nombre=producto.nombre,
            descripcion=producto.descripcion,
            genero=producto.genero,
            marca=producto.marca,
            precio_base=producto.precio_base,
            activo=producto.activo,
            creado_en=producto.creado_en,
            actualizado_en=producto.actualizado_en,
            imagenes=[ImagenProductoDTO.model_validate(i) for i in imagenes],
            temporada_ids=temporada_ids,
            coleccion_ids=coleccion_ids
        )

    async def listar(self, solo_activos: bool = False, limit: int = 50, offset: int = 0) -> List[ProductoDTO]:
        productos = await self.producto_repo.listar(solo_activos=solo_activos, limit=limit, offset=offset)
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

    async def obtenerPorId(self, producto_id: uuid.UUID) -> ProductoDTO:
        producto = await self.producto_repo.buscarPorId(producto_id)
        if not producto:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
        imagenes = await self.producto_repo.listarImagenesPorProducto(producto.id)
        temporada_ids = await self.producto_repo.listarTemporadaIds(producto.id)
        coleccion_ids = await self.producto_repo.listarColeccionIds(producto.id)
        return ProductoDTO(
            id=producto.id,
            categoria_id=producto.categoria_id,
            proveedor_principal_id=producto.proveedor_principal_id,
            nombre=producto.nombre,
            descripcion=producto.descripcion,
            genero=producto.genero,
            marca=producto.marca,
            precio_base=producto.precio_base,
            activo=producto.activo,
            creado_en=producto.creado_en,
            actualizado_en=producto.actualizado_en,
            imagenes=[ImagenProductoDTO.model_validate(i) for i in imagenes],
            temporada_ids=temporada_ids,
            coleccion_ids=coleccion_ids
        )

    async def buscarConFiltros(self, **kwargs) -> List[ProductoDTO]:
        productos = await self.producto_repo.buscarConFiltros(**kwargs)
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
