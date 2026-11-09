"""Controller PromocionService — CU22 (RF23).

CRUD administrativo con RBAC (solo ADMINISTRADOR muta), asociación de
variantes, vigencia en UTC, no acumulables: mayor descuento con desempate
determinista por ID; descuento topado al subtotal de línea; promoción y
descuento congelados en la venta (detalles_venta.promocion_id + descuento).
"""
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.permisos import es_admin
from backend.app.core.reloj import RelojSistema, entrada_local_a_utc
from backend.app.core.modules.catalogo.models import Promocion
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.catalogo.repositories.promocion_repository import PromocionRepository
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.modules.catalogo.schemas import (
    AsociarVariantesDTO, PromocionActualizarDTO, PromocionCrearDTO, PromocionDTO,
)


class PromocionService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.repo = PromocionRepository(db)
        self.variante_repo = VarianteRepository(db)

    def _exigir_admin(self, usuario: Usuario) -> None:
        if not es_admin(usuario) or usuario.empresa_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el Administrador gestiona promociones",
            )

    async def _a_dto(self, promo_id: uuid.UUID, empresa_id: uuid.UUID) -> PromocionDTO:
        promo = await self.repo.buscarPorId(promo_id, empresa_id=empresa_id)
        if promo is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoción no encontrada")
        variantes = await self.repo.variantesDe(promo.id)
        return PromocionDTO(
            id=promo.id, codigo=promo.codigo, nombre=promo.nombre,
            descripcion=promo.descripcion, tipo=promo.tipo, valor=promo.valor,
            activa=promo.activa, vigencia_inicio=promo.vigencia_inicio,
            vigencia_fin=promo.vigencia_fin, creada_en=promo.creada_en,
            variante_ids=variantes,
        )

    def _validar_vigencia(self, inicio, fin) -> None:
        if inicio is not None and fin is not None and inicio > fin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="vigencia_inicio no puede ser posterior a vigencia_fin",
            )

    def _validar_valor(self, tipo: str, valor: Decimal) -> None:
        if valor < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El valor no puede ser negativo")
        if tipo == "PORCENTAJE" and valor > 100:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El porcentaje no supera 100")

    async def crear(self, usuario: Usuario, dto: PromocionCrearDTO) -> PromocionDTO:
        self._exigir_admin(usuario)
        inicio = entrada_local_a_utc(dto.vigencia_inicio) if dto.vigencia_inicio else None
        fin = entrada_local_a_utc(dto.vigencia_fin) if dto.vigencia_fin else None
        self._validar_vigencia(inicio, fin)
        self._validar_valor(dto.tipo, dto.valor)
        if await self.repo.buscarPorCodigo(dto.codigo, empresa_id=usuario.empresa_id) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Código de promoción duplicado")
        for vid in dto.variante_ids:
            variante = await self.variante_repo.buscarPorId(vid)
            if variante is None or variante.empresa_id != usuario.empresa_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variante {vid} no encontrada")
        try:
            promo = Promocion(
                empresa_id=usuario.empresa_id,
                codigo=dto.codigo, nombre=dto.nombre, descripcion=dto.descripcion,
                tipo=dto.tipo, valor=dto.valor, activa=dto.activa,
                vigencia_inicio=inicio, vigencia_fin=fin,
                creada_por=usuario.id,
            )
            await self.repo.crear(promo)
            for vid in dto.variante_ids:
                await self.repo.asociar(promo.id, vid)
            await self.db.commit()
            return await self._a_dto(promo.id, usuario.empresa_id)
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Promoción duplicada")

    async def actualizar(self, usuario: Usuario, promo_id: uuid.UUID, dto: PromocionActualizarDTO) -> PromocionDTO:
        self._exigir_admin(usuario)
        promo = await self.repo.buscarPorId(promo_id, empresa_id=usuario.empresa_id)
        if promo is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoción no encontrada")
        try:
            if "nombre" in dto.model_fields_set and dto.nombre is not None:
                promo.nombre = dto.nombre
            if "descripcion" in dto.model_fields_set:
                promo.descripcion = dto.descripcion.strip() if dto.descripcion and dto.descripcion.strip() else None
            if "tipo" in dto.model_fields_set and dto.tipo is not None:
                promo.tipo = dto.tipo
            if "valor" in dto.model_fields_set and dto.valor is not None:
                promo.valor = dto.valor
            if "activa" in dto.model_fields_set and dto.activa is not None:
                promo.activa = dto.activa
            if "vigencia_inicio" in dto.model_fields_set:
                promo.vigencia_inicio = entrada_local_a_utc(dto.vigencia_inicio) if dto.vigencia_inicio else None
            if "vigencia_fin" in dto.model_fields_set:
                promo.vigencia_fin = entrada_local_a_utc(dto.vigencia_fin) if dto.vigencia_fin else None
            self._validar_vigencia(promo.vigencia_inicio, promo.vigencia_fin)
            self._validar_valor(promo.tipo, Decimal(str(promo.valor)))
            await self.db.flush()
            await self.db.commit()
            return await self._a_dto(promo.id, usuario.empresa_id)
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def eliminar(self, usuario: Usuario, promo_id: uuid.UUID) -> None:
        self._exigir_admin(usuario)
        promo = await self.repo.buscarPorId(promo_id, empresa_id=usuario.empresa_id)
        if promo is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoción no encontrada")
        await self.db.delete(promo)
        await self.db.commit()

    async def listar(self, usuario: Usuario, solo_activas=False, limit=50, offset=0):
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol not in ("ADMINISTRADOR", "ENCARGADO"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Administración")
        if usuario.empresa_id is None:
            raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
        items, total = await self.repo.listar(solo_activas=solo_activas, limit=limit, offset=offset, empresa_id=usuario.empresa_id)
        return {
            "total": total, "limit": limit, "offset": offset,
            "items": [await self._a_dto(p.id, usuario.empresa_id) for p in items],
        }

    async def obtener(self, usuario: Usuario, promo_id: uuid.UUID) -> PromocionDTO:
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol not in ("ADMINISTRADOR", "ENCARGADO"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Administración")
        if usuario.empresa_id is None:
            raise HTTPException(status_code=400, detail="Usuario sin empresa asignada")
        return await self._a_dto(promo_id, usuario.empresa_id)

    async def asociar(self, usuario: Usuario, promo_id: uuid.UUID, dto: AsociarVariantesDTO) -> PromocionDTO:
        self._exigir_admin(usuario)
        promo = await self.repo.buscarPorId(promo_id, empresa_id=usuario.empresa_id)
        if promo is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promoción no encontrada")
        try:
            for vid in dto.variante_ids:
                variante = await self.variante_repo.buscarPorId(vid)
                if variante is None or variante.empresa_id != usuario.empresa_id:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variante {vid} no encontrada")
                existentes = await self.repo.variantesDe(promo.id)
                if vid not in existentes:
                    await self.repo.asociar(promo.id, vid)
            await self.db.commit()
            return await self._a_dto(promo.id, usuario.empresa_id)
        except HTTPException:
            await self.db.rollback()
            raise
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asociación duplicada")

    async def desasociar(self, usuario: Usuario, promo_id: uuid.UUID, variante_id: uuid.UUID) -> PromocionDTO:
        self._exigir_admin(usuario)
        if await self.repo.buscarPorId(promo_id, empresa_id=usuario.empresa_id) is None:
            raise HTTPException(status_code=404, detail="Promoción no encontrada")
        if not await self.repo.desasociar(promo_id, variante_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asociación no encontrada")
        await self.db.commit()
        return await self._a_dto(promo_id, usuario.empresa_id)

    # ---------- motor de descuentos (usado por checkout CU14) ----------
    async def mejorDescuento(
        self, variante_id: uuid.UUID, precio_unitario: Decimal, cantidad: int,
        ahora: Optional[datetime] = None,
    ) -> Tuple[Decimal, Optional[uuid.UUID]]:
        ahora = ahora or self.reloj.ahora()
        subtotal = (Decimal(str(precio_unitario)) * cantidad).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        vigentes = await self.repo.vigentesPorVariante(variante_id, ahora)
        mejor: Decimal = Decimal("0")
        ganadora: Optional[uuid.UUID] = None
        for promo in sorted(vigentes, key=lambda p: str(p.id)):
            valor = Decimal(str(promo.valor))
            if promo.tipo == "PORCENTAJE":
                desc = (subtotal * valor / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                desc = min(valor * cantidad, subtotal)
            desc = min(desc, subtotal)
            if desc > mejor:
                mejor, ganadora = desc, promo.id
        return mejor, ganadora
