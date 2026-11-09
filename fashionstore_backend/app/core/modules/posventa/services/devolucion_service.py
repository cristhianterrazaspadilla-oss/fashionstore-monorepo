"""Servicio y Modelos de Dominio: Posventa — Devoluciones y Mermas (CU20 y CU12).

Separa:
1. Solicitud de devolución física (cliente o encargado, plazo voluntario 15 días).
2. Recepción e inspección técnica (custodia no vendible, dictamen técnico).
3. Registro de merma auditada con reducción de inventario disponible y Kardex.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.core.idempotencia import hash_payload, resolver_idempotencia
from backend.app.core.modules.catalogo.models import VarianteProducto
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.inventario.models import MovimientoInventario
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, RegistroIdempotencia, Venta
from backend.app.core.modules.ventas_pagos.repositories.venta_repository import DetalleVentaRepository, VentaRepository
from backend.app.core.permisos import es_admin, exigir_sucursal, rol_de
from backend.app.core.reloj import RelojSistema


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# MODELOS SQLALCHEMY (comercial.devoluciones y comercial.detalles_devolucion)
# ============================================================================

class Devolucion(Base):
    __tablename__ = "devoluciones"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_devoluciones_id_empresa"),
        UniqueConstraint("id", "venta_id", name="uq_devoluciones_id_venta"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    venta_id = Column(UUID(as_uuid=True), ForeignKey("comercial.ventas.id"), nullable=False)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    estado = Column(String(32), nullable=False, default="SOLICITADA")
    motivo_codigo = Column(String(60), nullable=False)
    motivo_descripcion = Column(Text, nullable=True)
    responsabilidad_tienda = Column(Boolean, nullable=True)
    politica_id = Column(UUID(as_uuid=True), nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    solicitada_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    recibida_en = Column(DateTime(timezone=True), nullable=True)
    inspeccionada_en = Column(DateTime(timezone=True), nullable=True)
    resuelta_en = Column(DateTime(timezone=True), nullable=True)

    detalles = relationship("DetalleDevolucion", back_populates="devolucion", cascade="all, delete-orphan")


class DetalleDevolucion(Base):
    __tablename__ = "detalles_devolucion"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_detalles_devolucion_id_empresa"),
        UniqueConstraint("devolucion_id", "detalle_venta_id", name="uq_detalles_devolucion_dev_detventa"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    devolucion_id = Column(UUID(as_uuid=True), ForeignKey("comercial.devoluciones.id"), nullable=False)
    venta_id = Column(UUID(as_uuid=True), nullable=False)
    detalle_venta_id = Column(UUID(as_uuid=True), ForeignKey("comercial.detalles_venta.id"), nullable=False)
    cantidad_solicitada = Column(Integer, nullable=False)
    cantidad_recibida = Column(Integer, nullable=False, default=0)
    cantidad_aceptada = Column(Integer, nullable=False, default=0)
    cantidad_rechazada = Column(Integer, nullable=False, default=0)
    condicion_fisica = Column(String(40), nullable=True)
    responsabilidad_tienda = Column(Boolean, nullable=True)
    inspeccionado_por = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=True)
    evidencia_refs = Column(JSONB, nullable=False, default=list)

    devolucion = relationship("Devolucion", back_populates="detalles")


# ============================================================================
# DTOs PYDANTIC
# ============================================================================

class LineaDevolucionSolicitudDTO(BaseModel):
    detalle_venta_id: uuid.UUID
    cantidad: int = Field(gt=0, description="Cantidad a devolver mayor a cero")


class DevolucionSolicitudDTO(BaseModel):
    venta_id: uuid.UUID
    lineas: List[LineaDevolucionSolicitudDTO] = Field(min_length=1)
    motivo_codigo: Literal["TALLA", "COLOR", "DEFECTO_FABRICACION", "PRODUCTO_INCORRECTO", "OTRO"]
    motivo_descripcion: Optional[str] = None
    evidencia_refs: Optional[List[str]] = Field(default_factory=list)


class InspeccionDTO(BaseModel):
    condicion_fisica: Literal["EXCELENTE", "BUENA", "DEFECTUOSA", "DANADA", "USADA"]
    responsabilidad_tienda: bool
    dictamen: Literal["APROBADA_REPOSICION", "APROBADA_REEMBOLSO", "RECHAZADA"]
    observaciones: Optional[str] = None


class DetalleDevolucionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    detalle_venta_id: uuid.UUID
    cantidad_solicitada: int
    cantidad_recibida: int
    cantidad_aceptada: int
    cantidad_rechazada: int
    condicion_fisica: Optional[str] = None
    responsabilidad_tienda: Optional[bool] = None


class DevolucionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    venta_id: uuid.UUID
    cliente_id: uuid.UUID
    sucursal_id: uuid.UUID
    estado: str
    motivo_codigo: str
    motivo_descripcion: Optional[str] = None
    responsabilidad_tienda: Optional[bool] = None
    solicitada_en: datetime
    recibida_en: Optional[datetime] = None
    inspeccionada_en: Optional[datetime] = None
    resuelta_en: Optional[datetime] = None
    detalles: List[DetalleDevolucionDTO] = Field(default_factory=list)


class MermaCrearDTO(BaseModel):
    sucursal_id: uuid.UUID
    variante_id: uuid.UUID
    cantidad: int = Field(gt=0, description="Cantidad mayor a cero")
    motivo_codigo: Optional[str] = None
    causa: Optional[str] = None
    descripcion: Optional[str] = None


class MermaDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    variante_id: uuid.UUID
    sucursal_id: uuid.UUID
    cantidad: int
    costo_unitario: Decimal
    motivo_codigo: Optional[str] = None
    causa: Optional[str] = None
    responsable_id: Optional[uuid.UUID] = None
    fecha_hora: datetime


# DTO heredado CU12 para compatibilidad
class DevolucionCrearDTO(BaseModel):
    detalle_venta_id: uuid.UUID
    cantidad: int = Field(gt=0)
    motivo: Optional[str] = "Devolucion presencial"


# ============================================================================
# SERVICIOS: DevolucionService y MermaService
# ============================================================================

class DevolucionService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.detalle_repo = DetalleVentaRepository(db)
        self.venta_repo = VentaRepository(db)
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)

    async def listar_mias(
        self, usuario: Usuario, *, limite: int = 50, desplazamiento: int = 0
    ) -> List[DevolucionDTO]:
        if not usuario.empresa_id:
            return []
        stmt = (
            select(Devolucion)
            .where(
                Devolucion.empresa_id == usuario.empresa_id,
                Devolucion.cliente_id == usuario.id,
            )
            .order_by(Devolucion.solicitada_en.desc(), Devolucion.id.desc())
            .limit(limite)
            .offset(desplazamiento)
        )
        filas = (await self.db.execute(stmt)).scalars().all()
        return [await self.obtener_por_id(usuario, fila.id) for fila in filas]

    def _autorizar_personal(self, usuario: Usuario, sucursal_id: uuid.UUID) -> None:
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "ENCARGADO":
            exigir_sucursal(usuario, sucursal_id)
            return
        if es_admin(usuario):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Encargado o Administrador")

    async def solicitar(
        self, usuario: Usuario, dto: DevolucionSolicitudDTO, clave: uuid.UUID
    ) -> DevolucionDTO:
        digest = hash_payload(dto.model_dump(mode="json"))

        # Idempotencia previa con comercial.registros_idempotencia
        if clave:
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:clave, 0))"),
                {"clave": str(clave)},
            )
            stmt_idm = select(RegistroIdempotencia).where(
                RegistroIdempotencia.clave == clave,
                RegistroIdempotencia.recurso_tipo == "DEVOLUCION",
            )
            prev = (await self.db.execute(stmt_idm)).scalars().first()
            if prev is not None:
                if prev.hash_solicitud != digest:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency-Key ya usada con otra solicitud",
                    )
                return await self.obtener_por_id(usuario, prev.recurso_id)

        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")

        venta = await self.db.get(Venta, dto.venta_id)
        if venta is None or venta.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada en la empresa")

        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE" and venta.cliente_id != usuario.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La venta pertenece a otro cliente")

        if dto.motivo_codigo == "OTRO" and not (dto.motivo_descripcion and dto.motivo_descripcion.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El motivo OTRO requiere motivo_descripcion obligatorio",
            )

        # Regla de plazo voluntario: 15 días desde la ENTREGA REAL (venta.entregada_en)
        ahora = self.reloj.ahora()
        es_caso_excepcional = dto.motivo_codigo in ("DEFECTO_FABRICACION", "PRODUCTO_INCORRECTO")

        if venta.entregada_en is None:
            if not es_caso_excepcional:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La venta no ha sido entregada aún; el plazo voluntario cuenta desde la entrega real",
                )
            estado_inicial = "PENDIENTE_EVALUACION"
        else:
            dias_pasados = (ahora - venta.entregada_en).total_seconds() / 86400.0
            if dias_pasados > 15:
                if not es_caso_excepcional:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="El plazo de devolución voluntaria (15 días desde la entrega) ha vencido. Casos posteriores por defecto de fabricación o producto incorrecto pasan a evaluación autorizada.",
                    )
                estado_inicial = "PENDIENTE_EVALUACION"
            else:
                estado_inicial = "SOLICITADA"

        from backend.app.core.modules.posventa.services.cambio_service import Cambio, DetalleCambio

        # Validar cantidades disponibles para devolución (excluyendo ya devueltas o cambiadas)
        for item in dto.lineas:
            stmt_det = (
                select(DetalleVenta)
                .where(DetalleVenta.id == item.detalle_venta_id)
                .with_for_update()
            )
            det = (await self.db.execute(stmt_det)).scalars().first()
            if det is None or det.venta_id != venta.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Línea de venta {item.detalle_venta_id} no pertenece a la venta {venta.id}",
                )

            # Sumar devoluciones previas no rechazadas
            stmt_acum = (
                select(DetalleDevolucion.cantidad_solicitada)
                .join(Devolucion, DetalleDevolucion.devolucion_id == Devolucion.id)
                .where(
                    DetalleDevolucion.detalle_venta_id == det.id,
                    Devolucion.estado != "RECHAZADA",
                )
            )
            cant_devuelta = sum((await self.db.execute(stmt_acum)).scalars().all(), 0)

            # Sumar cambios previos no rechazados para esta misma unidad
            stmt_camb = (
                select(DetalleCambio.cantidad)
                .join(Cambio, DetalleCambio.cambio_id == Cambio.id)
                .where(
                    DetalleCambio.detalle_venta_id == det.id,
                    DetalleCambio.tipo_linea == "ORIGINAL",
                    Cambio.estado != "RECHAZADO",
                )
            )
            cant_cambiada = sum((await self.db.execute(stmt_camb)).scalars().all(), 0)

            if cant_devuelta + cant_cambiada + item.cantidad > det.cantidad:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Excede lo vendido en línea {det.id} (vendido: {det.cantidad}, ya solicitado/devuelto: {cant_devuelta}, ya cambiado: {cant_cambiada})",
                )

        devolucion_id = uuid.uuid4()
        dev = Devolucion(
            id=devolucion_id,
            empresa_id=usuario.empresa_id,
            venta_id=venta.id,
            cliente_id=venta.cliente_id or usuario.id,
            sucursal_id=venta.sucursal_id,
            estado=estado_inicial,
            motivo_codigo=dto.motivo_codigo,
            motivo_descripcion=dto.motivo_descripcion,
            revision=1,
            solicitada_en=ahora,
        )
        self.db.add(dev)

        detalles_dto: List[DetalleDevolucionDTO] = []
        for item in dto.lineas:
            det_dev = DetalleDevolucion(
                id=uuid.uuid4(),
                empresa_id=usuario.empresa_id,
                devolucion_id=devolucion_id,
                venta_id=venta.id,
                detalle_venta_id=item.detalle_venta_id,
                cantidad_solicitada=item.cantidad,
                cantidad_recibida=0,
                cantidad_aceptada=0,
                cantidad_rechazada=0,
                evidencia_refs=dto.evidencia_refs or [],
            )
            self.db.add(det_dev)
            detalles_dto.append(
                DetalleDevolucionDTO(
                    id=det_dev.id,
                    detalle_venta_id=det_dev.detalle_venta_id,
                    cantidad_solicitada=det_dev.cantidad_solicitada,
                    cantidad_recibida=0,
                    cantidad_aceptada=0,
                    cantidad_rechazada=0,
                )
            )

        salida = DevolucionDTO(
            id=dev.id,
            venta_id=dev.venta_id,
            cliente_id=dev.cliente_id,
            sucursal_id=dev.sucursal_id,
            estado=dev.estado,
            motivo_codigo=dev.motivo_codigo,
            motivo_descripcion=dev.motivo_descripcion,
            solicitada_en=dev.solicitada_en,
            detalles=detalles_dto,
        )

        reg_idem = RegistroIdempotencia(
            clave=clave,
            usuario_id=usuario.id,
            recurso_tipo="DEVOLUCION",
            operacion="SOLICITAR_DEVOLUCION",
            hash_solicitud=digest,
            recurso_id=dev.id,
            respuesta=salida.model_dump(mode="json"),
            creada_en=ahora,
        )
        self.db.add(reg_idem)

        await self.db.commit()
        return salida

    async def inspeccionar(
        self, usuario: Usuario, devolucion_id: uuid.UUID, dto: InspeccionDTO, clave: uuid.UUID
    ) -> DevolucionDTO:
        digest = hash_payload(
            {"devolucion_id": str(devolucion_id), **dto.model_dump(mode="json")}
        )

        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:clave, 0))"),
            {"clave": str(clave)},
        )

        stmt_idem = select(RegistroIdempotencia).where(
            RegistroIdempotencia.clave == clave,
            RegistroIdempotencia.usuario_id == usuario.id,
            RegistroIdempotencia.recurso_tipo == "DEVOLUCION",
            RegistroIdempotencia.operacion == "INSPECCIONAR_DEVOLUCION",
        )
        previo = (await self.db.execute(stmt_idem)).scalars().first()
        if previo is not None:
            if previo.hash_solicitud != digest:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key ya usada con otra solicitud",
                )
            return await self.obtener_por_id(usuario, previo.recurso_id)

        stmt_dev = (
            select(Devolucion)
            .where(Devolucion.id == devolucion_id)
            .with_for_update()
        )
        dev = (await self.db.execute(stmt_dev)).scalars().first()
        if dev is None or dev.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Devolución no encontrada")

        self._autorizar_personal(usuario, dev.sucursal_id)

        if dev.estado not in ("SOLICITADA", "RECIBIDA", "PENDIENTE_EVALUACION"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"La devolución ya fue procesada (estado {dev.estado})",
            )

        ahora = self.reloj.ahora()
        dev.recibida_en = dev.recibida_en or ahora
        dev.inspeccionada_en = ahora
        dev.resuelta_en = ahora
        dev.responsabilidad_tienda = dto.responsabilidad_tienda

        stmt_detalles = select(DetalleDevolucion).where(DetalleDevolucion.devolucion_id == dev.id)
        detalles = (await self.db.execute(stmt_detalles)).scalars().all()

        for det in detalles:
            det.cantidad_recibida = det.cantidad_solicitada
            det.condicion_fisica = dto.condicion_fisica
            det.responsabilidad_tienda = dto.responsabilidad_tienda
            det.inspeccionado_por = usuario.id

            det_venta = await self.db.get(DetalleVenta, det.detalle_venta_id)

            if dto.dictamen == "APROBADA_REPOSICION":
                det.cantidad_aceptada = det.cantidad_recibida
                det.cantidad_rechazada = 0

                # Reingreso de stock a disponible
                filas = await self.inventario_repo.bloquearFilas([(dev.sucursal_id, det_venta.variante_id)])
                fila = filas.get((dev.sucursal_id, det_venta.variante_id))
                if fila:
                    fila.disponible += det.cantidad_aceptada
                    await self.db.flush()

                # Kardex DEVOLUCION
                mov = MovimientoInventario(
                    id=uuid.uuid4(),
                    variante_id=det_venta.variante_id,
                    sucursal_destino_id=dev.sucursal_id,
                    responsable_id=usuario.id,
                    tipo="DEVOLUCION",
                    cantidad=det.cantidad_aceptada,
                    costo_unitario=Decimal(str(det_venta.costo_promedio or 0)),
                    referencia_tipo="DETALLE_VENTA",
                    referencia_id=det_venta.id,
                    linea_referencia_id=det.id,
                    observacion=f"Devolución técnica {dev.id}: {dto.dictamen}",
                    fecha_hora=ahora,
                )
                self.db.add(mov)

            elif dto.dictamen == "APROBADA_REEMBOLSO":
                det.cantidad_aceptada = det.cantidad_recibida
                det.cantidad_rechazada = 0
                # Custodia / merma: no reingresa como disponible para venta inmediata

            elif dto.dictamen == "RECHAZADA":
                det.cantidad_aceptada = 0
                det.cantidad_rechazada = det.cantidad_recibida

        dev.estado = dto.dictamen
        salida = await self.obtener_por_id(usuario, dev.id)
        self.db.add(
            RegistroIdempotencia(
                clave=clave,
                usuario_id=usuario.id,
                recurso_tipo="DEVOLUCION",
                operacion="INSPECCIONAR_DEVOLUCION",
                hash_solicitud=digest,
                recurso_id=dev.id,
                respuesta=salida.model_dump(mode="json"),
                creada_en=ahora,
            )
        )
        await self.db.commit()
        return salida

    async def obtener_por_id(self, usuario: Usuario, devolucion_id: uuid.UUID) -> DevolucionDTO:
        dev = await self.db.get(Devolucion, devolucion_id)
        if dev is None or dev.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Devolución no encontrada")
        if rol_de(usuario) == "CLIENTE" and dev.cliente_id != usuario.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Devolución no encontrada")

        stmt_det = select(DetalleDevolucion).where(DetalleDevolucion.devolucion_id == dev.id)
        detalles = (await self.db.execute(stmt_det)).scalars().all()

        return DevolucionDTO(
            id=dev.id,
            venta_id=dev.venta_id,
            cliente_id=dev.cliente_id,
            sucursal_id=dev.sucursal_id,
            estado=dev.estado,
            motivo_codigo=dev.motivo_codigo,
            motivo_descripcion=dev.motivo_descripcion,
            responsabilidad_tienda=dev.responsabilidad_tienda,
            solicitada_en=dev.solicitada_en,
            recibida_en=dev.recibida_en,
            inspeccionada_en=dev.inspeccionada_en,
            resuelta_en=dev.resuelta_en,
            detalles=[
                DetalleDevolucionDTO(
                    id=d.id,
                    detalle_venta_id=d.detalle_venta_id,
                    cantidad_solicitada=d.cantidad_solicitada,
                    cantidad_recibida=d.cantidad_recibida,
                    cantidad_aceptada=d.cantidad_aceptada,
                    cantidad_rechazada=d.cantidad_rechazada,
                    condicion_fisica=d.condicion_fisica,
                    responsabilidad_tienda=d.responsabilidad_tienda,
                )
                for d in detalles
            ],
        )

    # ---------------- Compatibilidad con CU12 heredado ----------------
    async def registrar(
        self, usuario: Usuario, dto: DevolucionCrearDTO, clave: uuid.UUID
    ) -> Tuple[Any, bool]:
        """Adaptador heredado para CU12."""
        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")

        # Serializa reintentos con la misma clave, incluso si llegan en
        # paralelo o apuntan a líneas distintas de venta.
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:clave, 0))"),
            {"clave": str(clave)},
        )
        stmt_detalle = (
            select(DetalleVenta)
            .where(DetalleVenta.id == dto.detalle_venta_id)
            .with_for_update()
        )
        detalle = (await self.db.execute(stmt_detalle)).scalars().first()
        if detalle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detalle de venta no encontrado")
        venta = await self.db.get(Venta, detalle.venta_id)
        if venta is None or venta.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venta no encontrada en la empresa")

        self._autorizar_personal(usuario, venta.sucursal_id)

        movimiento_previo = await self.movimiento_repo.buscarPorClaveIdempotencia(clave)
        if movimiento_previo is not None:
            mismo_payload = (
                movimiento_previo.tipo == "DEVOLUCION"
                and movimiento_previo.referencia_tipo == "DETALLE_VENTA"
                and movimiento_previo.referencia_id == detalle.id
                and movimiento_previo.variante_id == detalle.variante_id
                and movimiento_previo.sucursal_destino_id == venta.sucursal_id
                and movimiento_previo.cantidad == dto.cantidad
                and movimiento_previo.observacion == dto.motivo
                and movimiento_previo.responsable_id == usuario.id
            )
            if not mismo_payload:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key ya usada con otra solicitud",
                )
            await self.db.commit()
            return movimiento_previo, False

        devuelta = await self.detalle_repo.cantidadDevueltaAcumulada(detalle.id)
        if devuelta + dto.cantidad > detalle.cantidad:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"La devolución acumulada excede lo vendido "
                    f"(vendido: {detalle.cantidad}, devuelto: {devuelta})"
                ),
            )

        filas = await self.inventario_repo.bloquearFilas([(venta.sucursal_id, detalle.variante_id)])
        fila = filas.get((venta.sucursal_id, detalle.variante_id))
        if fila:
            fila.disponible += dto.cantidad
            await self.db.flush()

        mov = MovimientoInventario(
            variante_id=detalle.variante_id,
            sucursal_destino_id=venta.sucursal_id,
            responsable_id=usuario.id,
            tipo="DEVOLUCION",
            cantidad=dto.cantidad,
            costo_unitario=Decimal(str(detalle.costo_promedio or 0)),
            referencia_tipo="DETALLE_VENTA",
            referencia_id=detalle.id,
            linea_referencia_id=uuid.uuid4(),
            clave_idempotencia=clave,
            observacion=dto.motivo,
        )
        creado = await self.movimiento_repo.registrar(mov)
        lineas_venta = (
            await self.db.execute(
                select(DetalleVenta).where(DetalleVenta.venta_id == venta.id)
            )
        ).scalars().all()
        cantidades_devuelta = {
            linea.id: await self.detalle_repo.cantidadDevueltaAcumulada(linea.id)
            for linea in lineas_venta
        }
        total_vendido = sum(linea.cantidad for linea in lineas_venta)
        total_devuelto = sum(cantidades_devuelta.values())
        if total_devuelto >= total_vendido:
            venta.estado = "DEVUELTA"
        elif total_devuelto > 0:
            venta.estado = "PARCIALMENTE_DEVUELTA"
        await self.db.commit()
        return creado, True


class MermaService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)
        self.variante_repo = VarianteRepository(db)

    def _autorizar(self, usuario: Usuario, sucursal_id: uuid.UUID) -> None:
        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "ENCARGADO":
            exigir_sucursal(usuario, sucursal_id)
            return
        if es_admin(usuario):
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo Encargado o Administrador")

    async def registrar(
        self, usuario: Usuario, dto: MermaCrearDTO, clave: uuid.UUID
    ) -> MermaDTO:
        self._autorizar(usuario, dto.sucursal_id)

        causa = dto.causa or dto.motivo_codigo or dto.descripcion
        if not causa or not causa.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La causa de la merma es obligatoria")

        if not usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario sin empresa asignada")

        # La clave se bloquea antes de tocar stock para que los reintentos
        # concurrentes no apliquen dos veces la misma merma.
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:clave, 0))"),
            {"clave": str(clave)},
        )
        movimiento_previo = await self.movimiento_repo.buscarPorClaveIdempotencia(clave)
        if movimiento_previo is not None:
            mismo_payload = (
                movimiento_previo.tipo == "MERMA"
                and movimiento_previo.variante_id == dto.variante_id
                and movimiento_previo.sucursal_origen_id == dto.sucursal_id
                and movimiento_previo.sucursal_destino_id == dto.sucursal_id
                and movimiento_previo.cantidad == dto.cantidad
                and movimiento_previo.observacion == causa
                and movimiento_previo.responsable_id == usuario.id
            )
            if not mismo_payload:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key ya usada con otra solicitud",
                )
            await self.db.commit()
            return MermaDTO(
                id=movimiento_previo.id,
                variante_id=movimiento_previo.variante_id,
                sucursal_id=dto.sucursal_id,
                cantidad=movimiento_previo.cantidad,
                costo_unitario=movimiento_previo.costo_unitario,
                motivo_codigo=dto.motivo_codigo or causa,
                causa=causa,
                responsable_id=movimiento_previo.responsable_id,
                fecha_hora=movimiento_previo.fecha_hora,
            )

        from backend.app.core.modules.organizacion.models import Sucursal

        sucursal = await self.db.get(Sucursal, dto.sucursal_id)
        if sucursal is None or sucursal.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada en la empresa")

        var = await self.db.get(VarianteProducto, dto.variante_id)
        if var is None or var.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variante no encontrada en la empresa")

        filas = await self.inventario_repo.bloquearFilas([(dto.sucursal_id, dto.variante_id)])
        fila = filas.get((dto.sucursal_id, dto.variante_id))
        if fila is None or fila.disponible < dto.cantidad:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stock disponible insuficiente para merma")

        fila.disponible -= dto.cantidad
        await self.db.flush()

        ahora = self.reloj.ahora()
        costo = Decimal(str(var.costo_promedio or 0))

        mov = MovimientoInventario(
            id=uuid.uuid4(),
            variante_id=dto.variante_id,
            sucursal_origen_id=dto.sucursal_id,
            sucursal_destino_id=dto.sucursal_id,
            responsable_id=usuario.id,
            tipo="MERMA",
            cantidad=dto.cantidad,
            costo_unitario=costo,
            referencia_tipo="MERMA_AUDITADA",
            referencia_id=uuid.uuid4(),
            clave_idempotencia=clave,
            observacion=causa,
            fecha_hora=ahora,
        )
        self.db.add(mov)
        await self.db.flush()
        await self.db.commit()

        return MermaDTO(
            id=mov.id,
            variante_id=dto.variante_id,
            sucursal_id=dto.sucursal_id,
            cantidad=dto.cantidad,
            costo_unitario=costo,
            motivo_codigo=dto.motivo_codigo or causa,
            causa=causa,
            responsable_id=usuario.id,
            fecha_hora=ahora,
        )
