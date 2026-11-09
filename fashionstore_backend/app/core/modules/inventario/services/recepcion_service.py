import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import List
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.core.modules.inventario.models import LoteRecepcion, DetalleLoteRecepcion, MovimientoInventario
from backend.app.core.modules.inventario.schemas import LoteRecepcionCrearDTO, LoteRecepcionDTO, DetalleLoteDTO
from backend.app.core.modules.inventario.repositories.lote_repository import LoteRepository
from backend.app.core.modules.inventario.repositories.proveedor_repository import ProveedorRepository
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.identidad_empresas.repositories.usuario_repository import UsuarioRepository
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository

class RecepcionService:
    """
    Controller RecepcionService.registrarLote() -> Datos LoteRepository.crear(),
    VarianteRepository.actualizarCostos(), InventarioRepository.ingresar(),
    MovimientoRepository.registrar(tipo=RECEPCION_PROVEEDOR)
    Aplica RN-09 en transacción única.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.lote_repo = LoteRepository(db)
        self.proveedor_repo = ProveedorRepository(db)
        self.sucursal_repo = SucursalRepository(db)
        self.usuario_repo = UsuarioRepository(db)
        self.variante_repo = VarianteRepository(db)
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)

    async def registrarLote(self, dto: LoteRecepcionCrearDTO) -> LoteRecepcionDTO:
        proveedor = await self.proveedor_repo.buscarPorId(dto.proveedor_id)
        if not proveedor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado")
        if not proveedor.activo:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Proveedor inactivo")

        sucursal = await self.sucursal_repo.buscarPorId(dto.sucursal_id)
        if not sucursal:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")

        responsable = await self.usuario_repo.buscarPorId(dto.recibido_por_id)
        if not responsable:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario receptor no encontrado")

        if dto.temporada_id:
            from backend.app.core.modules.catalogo.models import Temporada
            res = await self.db.execute(select(Temporada).where(Temporada.id == dto.temporada_id))
            if not res.scalars().first():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temporada no encontrada")
        if dto.coleccion_id:
            from backend.app.core.modules.catalogo.models import Coleccion
            res = await self.db.execute(select(Coleccion).where(Coleccion.id == dto.coleccion_id))
            if not res.scalars().first():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Colección no encontrada")

        variante_ids = [d.variante_id for d in dto.detalles]
        if len(variante_ids) != len(set(variante_ids)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Detalles duplicados: misma variante repetida en el lote")

        variantes_info = {}
        for detalle in dto.detalles:
            variante = await self.variante_repo.buscarPorId(detalle.variante_id)
            if not variante:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variante {detalle.variante_id} no encontrada")
            if not variante.activa:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Variante {variante.sku} inactiva")
            variantes_info[detalle.variante_id] = variante

        try:
            lote = LoteRecepcion(
                empresa_id=sucursal.empresa_id,
                proveedor_id=dto.proveedor_id,
                sucursal_id=dto.sucursal_id,
                temporada_id=dto.temporada_id,
                coleccion_id=dto.coleccion_id,
                recibido_por_id=dto.recibido_por_id,
                numero_documento=dto.numero_documento.strip() if dto.numero_documento else None,
                observacion=dto.observacion.strip() if dto.observacion else None,
            )
            await self.lote_repo.crear(lote)

            for detalle_dto in dto.detalles:
                detalle = DetalleLoteRecepcion(
                    lote_id=lote.id,
                    variante_id=detalle_dto.variante_id,
                    cantidad=detalle_dto.cantidad,
                    costo_unitario=detalle_dto.costo_unitario,
                )
                self.db.add(detalle)
            await self.db.flush()

            for detalle_dto in dto.detalles:
                variante = variantes_info[detalle_dto.variante_id]
                costo_previo = Decimal(str(variante.costo_promedio)) if variante.costo_promedio is not None else Decimal("0")
                existencia_previa = await self.inventario_repo.existenciaTotalPorVariante(detalle_dto.variante_id)
                cantidad_recibida = detalle_dto.cantidad
                costo_compra = Decimal(str(detalle_dto.costo_unitario))

                if existencia_previa == 0:
                    nuevo_promedio = costo_compra
                else:
                    nuevo_promedio = (
                        (Decimal(existencia_previa) * costo_previo + Decimal(cantidad_recibida) * costo_compra)
                        / (Decimal(existencia_previa) + Decimal(cantidad_recibida))
                    )
                nuevo_promedio = nuevo_promedio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                await self.variante_repo.actualizarCostos(
                    variante_id=detalle_dto.variante_id,
                    costo_promedio=nuevo_promedio,
                    costo_ultimo=costo_compra,
                )

                await self.inventario_repo.ingresar(
                    variante_id=detalle_dto.variante_id,
                    sucursal_id=dto.sucursal_id,
                    cantidad=cantidad_recibida,
                )

                movimiento = MovimientoInventario(
                    variante_id=detalle_dto.variante_id,
                    sucursal_origen_id=None,
                    sucursal_destino_id=dto.sucursal_id,
                    responsable_id=dto.recibido_por_id,
                    tipo="RECEPCION_PROVEEDOR",
                    cantidad=cantidad_recibida,
                    costo_unitario=costo_compra,
                    referencia_tipo="LOTE_RECEPCION",
                    referencia_id=lote.id,
                    observacion=f"Recepción lote {lote.numero_documento or str(lote.id)}",
                )
                await self.movimiento_repo.registrar(movimiento)

            await self.db.commit()
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al registrar lote: {str(e)}")

        lote_completo = await self.lote_repo.buscarPorId(lote.id)
        detalles_dto = [
            DetalleLoteDTO.model_validate(d) for d in lote_completo.detalles
        ]
        return LoteRecepcionDTO(
            id=lote_completo.id,
            proveedor_id=lote_completo.proveedor_id,
            sucursal_id=lote_completo.sucursal_id,
            temporada_id=lote_completo.temporada_id,
            coleccion_id=lote_completo.coleccion_id,
            recibido_por_id=lote_completo.recibido_por_id,
            numero_documento=lote_completo.numero_documento,
            fecha_recepcion=lote_completo.fecha_recepcion,
            observacion=lote_completo.observacion,
            detalles=detalles_dto,
        )

    async def obtenerPorId(self, lote_id: uuid.UUID) -> LoteRecepcionDTO:
        lote = await self.lote_repo.buscarPorId(lote_id)
        if not lote:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado")
        return LoteRecepcionDTO(
            id=lote.id,
            proveedor_id=lote.proveedor_id,
            sucursal_id=lote.sucursal_id,
            temporada_id=lote.temporada_id,
            coleccion_id=lote.coleccion_id,
            recibido_por_id=lote.recibido_por_id,
            numero_documento=lote.numero_documento,
            fecha_recepcion=lote.fecha_recepcion,
            observacion=lote.observacion,
            detalles=[DetalleLoteDTO.model_validate(d) for d in lote.detalles],
        )

    async def listar(self, limit: int = 50, offset: int = 0) -> List[LoteRecepcionDTO]:
        lotes = await self.lote_repo.listar(limit=limit, offset=offset)
        result = []
        for lote in lotes:
            result.append(
                LoteRecepcionDTO(
                    id=lote.id,
                    proveedor_id=lote.proveedor_id,
                    sucursal_id=lote.sucursal_id,
                    temporada_id=lote.temporada_id,
                    coleccion_id=lote.coleccion_id,
                    recibido_por_id=lote.recibido_por_id,
                    numero_documento=lote.numero_documento,
                    fecha_recepcion=lote.fecha_recepcion,
                    observacion=lote.observacion,
                    detalles=[DetalleLoteDTO.model_validate(d) for d in lote.detalles],
                )
            )
        return result
