"""Servicio y Modelos de Dominio: Posventa — Cambio de Prenda (CU08).

Implementa:
- Solicitud de cambio de prenda (plazo voluntario 15 días, reconocimiento neto por unidad, nota de cambio por 7 días).
- Cotización de reemplazo y cálculo de diferencia.
- Resolución de diferencia financiera: regla estricta de exclusión de reemplazo y saldo/reembolso simultáneos.
- Mapeo de tablas comercial.cambios, comercial.detalles_cambio, comercial.movimientos_saldo, comercial.obligaciones_reembolso.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship

from backend.app.core.database import Base
from backend.app.core.idempotencia import hash_payload, resolver_idempotencia
from backend.app.core.ambito_comercial import exigir_empresa_recurso, sucursal_autorizada
from backend.app.core.modules.catalogo.models import VarianteProducto
from backend.app.core.modules.identidad_empresas.models import Empresa, Usuario
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.posventa.services.devolucion_service import Devolucion
from backend.app.core.modules.ventas_pagos.models import DetalleVenta, RegistroIdempotencia, Venta
from backend.app.core.modules.ventas_pagos.repositories.venta_repository import DetalleVentaRepository
from backend.app.core.modules.ventas_pagos.services.pedido_service import ObligacionReembolso
from backend.app.core.permisos import es_admin, exigir_sucursal, rol_de
from backend.app.core.reloj import RelojSistema


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# MODELOS SQLALCHEMY (comercial.cambios, comercial.detalles_cambio, comercial.movimientos_saldo)
# ============================================================================

class Cambio(Base):
    __tablename__ = "cambios"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_cambios_id_empresa"),
        UniqueConstraint("id", "venta_id", name="uq_cambios_id_venta"),
        UniqueConstraint("empresa_id", "nota_codigo", name="uq_cambios_empresa_nota"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False, index=True)
    venta_id = Column(UUID(as_uuid=True), ForeignKey("comercial.ventas.id"), nullable=False)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("seguridad.usuarios.id"), nullable=False)
    sucursal_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.sucursales.id"), nullable=False)
    nota_codigo = Column(String(80), nullable=False)
    estado = Column(String(32), nullable=False, default="SOLICITADO")
    motivo_codigo = Column(String(60), nullable=False)
    motivo_descripcion = Column(Text, nullable=True)
    politica_id = Column(UUID(as_uuid=True), nullable=True)
    modalidad_reemplazo = Column(String(12), nullable=True)
    direccion = Column(Text, nullable=True)
    valor_reconocido_bob = Column(Numeric(14, 2), nullable=False, default=0)
    diferencia_bob = Column(Numeric(14, 2), nullable=False, default=0)
    vence_espera_en = Column(DateTime(timezone=True), nullable=True)
    oferta_revision = Column(Integer, nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)
    actualizado_en = Column(DateTime(timezone=True), default=_ahora_utc, onupdate=_ahora_utc, nullable=False)

    detalles = relationship("DetalleCambio", back_populates="cambio", cascade="all, delete-orphan")


class DetalleCambio(Base):
    __tablename__ = "detalles_cambio"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_detalles_cambio_id_empresa"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    cambio_id = Column(UUID(as_uuid=True), ForeignKey("comercial.cambios.id"), nullable=False)
    venta_id = Column(UUID(as_uuid=True), nullable=False)
    tipo_linea = Column(String(12), nullable=False)  # 'ORIGINAL' o 'REEMPLAZO'
    detalle_venta_id = Column(UUID(as_uuid=True), ForeignKey("comercial.detalles_venta.id"), nullable=True)
    variante_reemplazo_id = Column(UUID(as_uuid=True), ForeignKey("catalogo.variantes_producto.id"), nullable=True)
    cantidad = Column(Integer, nullable=False)
    precio_unitario_bob = Column(Numeric(14, 2), nullable=True)
    estado = Column(String(30), nullable=False, default="PENDIENTE")

    cambio = relationship("Cambio", back_populates="detalles")


class MovimientoSaldo(Base):
    __tablename__ = "movimientos_saldo"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_movimientos_saldo_id_empresa"),
        UniqueConstraint("empresa_id", "referencia_unica", name="uq_movimientos_saldo_empresa_ref"),
        {"schema": "comercial", "extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("organizacion.empresas.id"), nullable=False)
    cliente_id = Column(UUID(as_uuid=True), nullable=False)
    tipo = Column(String(30), nullable=False)  # 'CREDITO', 'DEBITO'
    monto_bob = Column(Numeric(14, 2), nullable=False)
    origen_tipo = Column(String(40), nullable=False)
    origen_id = Column(UUID(as_uuid=True), nullable=False)
    referencia_unica = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    estado = Column(String(30), nullable=False, default="CONFIRMADO")
    creado_en = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)


# ============================================================================
# DTOs PYDANTIC
# ============================================================================

class LineaOriginalCambioDTO(BaseModel):
    detalle_venta_id: uuid.UUID
    cantidad: int = Field(gt=0, description="Cantidad de la prenda original a cambiar")


class LineaReemplazoCambioDTO(BaseModel):
    variante_id: uuid.UUID
    cantidad: int = Field(gt=0, description="Cantidad de la prenda solicitada en reemplazo")


class CambioSolicitudDTO(BaseModel):
    venta_id: uuid.UUID
    lineas_originales: List[LineaOriginalCambioDTO] = Field(min_length=1)
    reemplazos: List[LineaReemplazoCambioDTO] = Field(default_factory=list)
    sucursal_id: uuid.UUID
    modalidad_reemplazo: Literal["RECOJO", "DELIVERY"] = "RECOJO"
    direccion: Optional[str] = None
    motivo_codigo: Literal["TALLA", "COLOR", "DEFECTO_FABRICACION", "PRODUCTO_INCORRECTO", "OTRO"]
    motivo_descripcion: Optional[str] = None


class ResolverDiferenciaDTO(BaseModel):
    destino_diferencia: Optional[str] = None
    saldo_bob: Optional[Decimal] = None
    reembolso_bob: Optional[Decimal] = None


class DetalleCambioItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tipo_linea: str
    detalle_venta_id: Optional[uuid.UUID] = None
    variante_reemplazo_id: Optional[uuid.UUID] = None
    cantidad: int
    precio_unitario_bob: Optional[Decimal] = None
    estado: str


class CambioDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    cambio_id: uuid.UUID
    venta_id: uuid.UUID
    cliente_id: uuid.UUID
    sucursal_id: uuid.UUID
    nota_codigo: str
    estado: str
    motivo_codigo: str
    motivo_descripcion: Optional[str] = None
    valor_reconocido_bob: Decimal
    diferencia_bob: Decimal
    vence_espera_en: Optional[datetime] = None
    modalidad_reemplazo: Optional[str] = None
    direccion: Optional[str] = None
    creado_en: Optional[datetime] = None
    detalles: List[DetalleCambioItemDTO] = Field(default_factory=list)


# ============================================================================
# SERVICIO CAMBIO DE PRENDA
# ============================================================================

class CambioService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()

    def _autorizar(self, usuario: Usuario, recurso) -> None:
        exigir_empresa_recurso(usuario, recurso)
        rol = rol_de(usuario)
        if rol == "CLIENTE":
            if recurso.cliente_id != usuario.id:
                raise HTTPException(status_code=403, detail="El recurso pertenece a otro cliente")
        elif rol == "ENCARGADO":
            exigir_sucursal(usuario, recurso.sucursal_id)
        elif rol != "ADMINISTRADOR":
            raise HTTPException(status_code=403, detail="Rol no autorizado para gestionar cambios")

    async def listar_mios(
        self, usuario: Usuario, *, limite: int = 50, desplazamiento: int = 0
    ) -> List[CambioDTO]:
        if not usuario.empresa_id:
            return []
        stmt = (
            select(Cambio)
            .where(Cambio.empresa_id == usuario.empresa_id, Cambio.cliente_id == usuario.id)
            .order_by(Cambio.creado_en.desc(), Cambio.id.desc())
            .limit(limite)
            .offset(desplazamiento)
        )
        filas = (await self.db.execute(stmt)).scalars().all()
        return [await self.obtener_por_id(usuario, fila.id) for fila in filas]

    async def solicitar(
        self, usuario: Usuario, dto: CambioSolicitudDTO, clave: uuid.UUID
    ) -> CambioDTO:
        digest = hash_payload(dto.model_dump(mode="json"))

        # Idempotencia previa con comercial.registros_idempotencia
        if clave:
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:clave, 0))"),
                {"clave": f"CAMBIO:SOLICITAR:{usuario.id}:{clave}"},
            )
            stmt_idm = select(RegistroIdempotencia).where(
                RegistroIdempotencia.clave == clave,
                RegistroIdempotencia.usuario_id == usuario.id,
                RegistroIdempotencia.recurso_tipo == "CAMBIO",
                RegistroIdempotencia.operacion == "SOLICITAR_CAMBIO",
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
        self._autorizar(usuario, venta)
        if dto.sucursal_id != venta.sucursal_id:
            raise HTTPException(status_code=409, detail="El cambio debe recibirse en la sucursal de la venta original")
        await sucursal_autorizada(self.db, usuario, dto.sucursal_id)
        ids = [item.detalle_venta_id for item in dto.lineas_originales]
        if len(ids) != len(set(ids)):
            raise HTTPException(status_code=400, detail="Línea original duplicada en el cambio")
        reemplazos_ids = [item.variante_id for item in dto.reemplazos]
        if len(reemplazos_ids) != len(set(reemplazos_ids)):
            raise HTTPException(status_code=400, detail="Variante de reemplazo duplicada en el cambio")

        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE" and venta.cliente_id != usuario.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="La venta pertenece a otro cliente")

        if dto.motivo_codigo == "OTRO" and not (dto.motivo_descripcion and dto.motivo_descripcion.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El motivo OTRO requiere motivo_descripcion obligatorio",
            )

        if dto.modalidad_reemplazo == "DELIVERY" and not (dto.direccion and dto.direccion.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Modalidad DELIVERY requiere dirección de entrega",
            )

        ahora = self.reloj.ahora()
        empresa = await self.db.get(Empresa, usuario.empresa_id)
        if empresa is None or empresa.plazo_cambios_dias is None or empresa.plazo_cambios_dias <= 0:
            raise HTTPException(status_code=409, detail="Falta una política válida de plazo de cambios para la empresa")
        plazo_dias = empresa.plazo_cambios_dias
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
            if dias_pasados > plazo_dias:
                if not es_caso_excepcional:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"El plazo voluntario de cambio ({plazo_dias} días desde la entrega) ha vencido",
                    )
                estado_inicial = "PENDIENTE_EVALUACION"
            else:
                estado_inicial = "SOLICITADO"

        # 1. Reconocimiento neto de las prendas originales con descuento prorrateado
        valor_reconocido = Decimal("0.00")
        lineas_orig_procesadas = []

        for item in sorted(dto.lineas_originales, key=lambda linea: str(linea.detalle_venta_id)):
            stmt_det = (
                select(DetalleVenta)
                .where(DetalleVenta.id == item.detalle_venta_id, DetalleVenta.venta_id == venta.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            det = (await self.db.execute(stmt_det)).scalars().first()
            if det is None or det.venta_id != venta.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Línea de venta {item.detalle_venta_id} no pertenece a la venta {venta.id}",
                )

            cant_devuelta, cant_cambiada = await DetalleVentaRepository(self.db).cantidadesPosventaComprometidas(det.id)

            if cant_cambiada + cant_devuelta + item.cantidad > det.cantidad:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Cantidad solicitada en línea {det.id} supera la existencia disponible para cambio (vendido: {det.cantidad}, ya cambiado: {cant_cambiada}, ya devuelto: {cant_devuelta})",
                )

            # Precio neto unitario original
            precio_neto_orig = det.precio_unitario - (det.descuento / Decimal(str(det.cantidad)))
            tot_reconocido_linea = precio_neto_orig * Decimal(str(item.cantidad))
            valor_reconocido += tot_reconocido_linea
            lineas_orig_procesadas.append((det, item.cantidad, precio_neto_orig))

        # 2. Cotización de reemplazos
        valor_reemplazo = Decimal("0.00")
        lineas_reemp_procesadas = []
        inventario = await InventarioRepository(self.db).bloquearFilas([
            (dto.sucursal_id, item.variante_id) for item in dto.reemplazos
        ])

        for item in dto.reemplazos:
            var = await self.db.get(VarianteProducto, item.variante_id)
            if var is None or var.empresa_id != usuario.empresa_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Variante de reemplazo {item.variante_id} no encontrada en la empresa",
                )
            if not var.activa:
                raise HTTPException(status_code=409, detail="La variante de reemplazo está inactiva")
            fila = inventario.get((dto.sucursal_id, var.id))
            if fila is None or fila.disponible < item.cantidad:
                raise HTTPException(status_code=409, detail="Sin stock disponible para el reemplazo en la sucursal")
            p_actual = Decimal(str(var.precio or 0))
            tot_reemp = p_actual * Decimal(str(item.cantidad))
            valor_reemplazo += tot_reemp
            lineas_reemp_procesadas.append((var, item.cantidad, p_actual))

        diferencia = valor_reemplazo - valor_reconocido

        cambio_id = uuid.uuid4()
        nota_codigo = "CAMB-" + secrets.token_hex(4).upper()
        # Vigencia contractual CU08: Nota de cambio por 7 días; oferta de reemplazo específico por 48 horas
        if len(dto.reemplazos) > 0:
            vence_espera = ahora + timedelta(hours=48)
        else:
            vence_espera = ahora + timedelta(days=7)

        cambio = Cambio(
            id=cambio_id,
            empresa_id=usuario.empresa_id,
            venta_id=venta.id,
            cliente_id=venta.cliente_id or usuario.id,
            sucursal_id=dto.sucursal_id,
            nota_codigo=nota_codigo,
            estado=estado_inicial,
            motivo_codigo=dto.motivo_codigo,
            motivo_descripcion=dto.motivo_descripcion,
            modalidad_reemplazo=dto.modalidad_reemplazo,
            direccion=dto.direccion,
            valor_reconocido_bob=valor_reconocido,
            diferencia_bob=diferencia,
            vence_espera_en=vence_espera,
            oferta_revision=1 if len(dto.reemplazos) > 0 else None,
            revision=1,
            creado_en=ahora,
            actualizado_en=ahora,
        )
        self.db.add(cambio)

        detalles_dto: List[DetalleCambioItemDTO] = []

        # Detalles originales
        for det, cant, p_neto in lineas_orig_procesadas:
            dc = DetalleCambio(
                id=uuid.uuid4(),
                empresa_id=usuario.empresa_id,
                cambio_id=cambio_id,
                venta_id=venta.id,
                tipo_linea="ORIGINAL",
                detalle_venta_id=det.id,
                variante_reemplazo_id=None,
                cantidad=cant,
                precio_unitario_bob=p_neto,
                estado="PENDIENTE",
            )
            self.db.add(dc)
            detalles_dto.append(
                DetalleCambioItemDTO(
                    id=dc.id,
                    tipo_linea="ORIGINAL",
                    detalle_venta_id=det.id,
                    variante_reemplazo_id=None,
                    cantidad=cant,
                    precio_unitario_bob=p_neto,
                    estado="PENDIENTE",
                )
            )

        # Detalles de reemplazo
        for var, cant, p_act in lineas_reemp_procesadas:
            dc = DetalleCambio(
                id=uuid.uuid4(),
                empresa_id=usuario.empresa_id,
                cambio_id=cambio_id,
                venta_id=venta.id,
                tipo_linea="REEMPLAZO",
                detalle_venta_id=None,
                variante_reemplazo_id=var.id,
                cantidad=cant,
                precio_unitario_bob=p_act,
                estado="PENDIENTE",
            )
            self.db.add(dc)
            detalles_dto.append(
                DetalleCambioItemDTO(
                    id=dc.id,
                    tipo_linea="REEMPLAZO",
                    detalle_venta_id=None,
                    variante_reemplazo_id=var.id,
                    cantidad=cant,
                    precio_unitario_bob=p_act,
                    estado="PENDIENTE",
                )
            )

        salida = CambioDTO(
            cambio_id=cambio.id,
            venta_id=cambio.venta_id,
            cliente_id=cambio.cliente_id,
            sucursal_id=cambio.sucursal_id,
            nota_codigo=cambio.nota_codigo,
            estado=cambio.estado,
            motivo_codigo=cambio.motivo_codigo,
            motivo_descripcion=cambio.motivo_descripcion,
            valor_reconocido_bob=cambio.valor_reconocido_bob,
            diferencia_bob=cambio.diferencia_bob,
            vence_espera_en=cambio.vence_espera_en,
            modalidad_reemplazo=cambio.modalidad_reemplazo,
            direccion=cambio.direccion,
            detalles=detalles_dto,
        )

        reg_idem = RegistroIdempotencia(
            clave=clave,
            usuario_id=usuario.id,
            recurso_tipo="CAMBIO",
            operacion="SOLICITAR_CAMBIO",
            hash_solicitud=digest,
            recurso_id=cambio.id,
            respuesta=salida.model_dump(mode="json"),
            creada_en=ahora,
        )
        self.db.add(reg_idem)

        await self.db.commit()
        return salida

    async def resolver_diferencia(
        self, usuario: Usuario, cambio_id: uuid.UUID, dto: ResolverDiferenciaDTO, clave: uuid.UUID
    ) -> CambioDTO:
        digest = hash_payload(dto.model_dump(mode="json"))

        stmt_cambio = select(Cambio).where(
            Cambio.id == cambio_id, Cambio.empresa_id == usuario.empresa_id
        ).with_for_update().execution_options(populate_existing=True)
        cambio = (await self.db.execute(stmt_cambio)).scalars().first()
        if cambio is None or cambio.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cambio no encontrado")
        self._autorizar(usuario, cambio)

        # Titularidad derivada del recurso original en servidor, no de un
        # cliente_id inexistente en OrdenPago ni de la selección del formulario.
        venta_original = (await self.db.execute(select(Venta).where(
            Venta.id == cambio.venta_id, Venta.empresa_id == cambio.empresa_id
        ))).scalars().first()
        if (venta_original is None or venta_original.cliente_id is None or
                venta_original.cliente_id != cambio.cliente_id or
                venta_original.sucursal_id != cambio.sucursal_id):
            raise HTTPException(409, detail="CONCILIACION_REQUERIDA: el cambio no acredita titular y sucursal de la venta original")
        self._autorizar(usuario, venta_original)
        await sucursal_autorizada(self.db, usuario, venta_original.sucursal_id)
        titular = (await self.db.execute(select(Usuario.id).where(
            Usuario.id == venta_original.cliente_id, Usuario.empresa_id == cambio.empresa_id
        ))).scalar_one_or_none()
        if titular is None:
            raise HTTPException(409, detail="CONCILIACION_REQUERIDA: el titular original no pertenece a esta empresa")

        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if rol == "CLIENTE" and cambio.cliente_id != usuario.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El cambio pertenece a otro cliente")

        if not dto.destino_diferencia:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El campo 'destino_diferencia' es obligatorio",
            )

        destino = dto.destino_diferencia.upper().strip()

        # Rechazo explícito de combinaciones simultáneas o ambiguas (CU08 exclusión estricta)
        if destino in ("SALDO_Y_REEMBOLSO", "SALDO_REEMBOLSO", "MIXTO", "AMBOS") or (
            dto.saldo_bob is not None and dto.reembolso_bob is not None and dto.saldo_bob > 0 and dto.reembolso_bob > 0
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Resolución financiera simultánea (SALDO + REEMBOLSO) prohibida; la resolución debe ser exclusivamente SALDO o REEMBOLSO",
            )

        if destino not in ("SALDO", "REEMBOLSO", "PAGO_CLIENTE", "SIN_DIFERENCIA"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Destino de diferencia inválido o ambiguo: '{dto.destino_diferencia}'. Debe ser SALDO, REEMBOLSO, PAGO_CLIENTE o SIN_DIFERENCIA",
            )

        if cambio.estado == "PENDIENTE_EVALUACION":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El cambio se encuentra en PENDIENTE_EVALUACION; requiere evaluación autorizada previa antes de resolver diferencia",
            )

        if cambio.estado in ("RESUELTO", "LIQUIDADO", "RECHAZADO"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El cambio ya se encuentra en estado {cambio.estado}",
            )

        stmt_reemplazos = select(DetalleCambio).where(
            DetalleCambio.cambio_id == cambio.id,
            DetalleCambio.tipo_linea == "REEMPLAZO",
        )
        tiene_reemplazos = len((await self.db.execute(stmt_reemplazos)).scalars().all()) > 0

        dif = cambio.diferencia_bob
        ahora = self.reloj.ahora()

        # Verificar vigencia de la oferta (48 horas con reemplazos) o nota (7 días sin reemplazos)
        if cambio.vence_espera_en is not None and ahora > cambio.vence_espera_en:
            if tiene_reemplazos:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La oferta de reemplazo ha vencido (plazo de 48 horas expirado)",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La nota de cambio ha vencido (plazo de 7 días expirado)",
                )

        # REGLA OBLIGATORIA: Excluye reemplazo y saldo/reembolso simultáneos
        # "Misma unidad no obtiene simultáneamente reemplazo, saldo y reembolso."
        if tiene_reemplazos:
            if dif > Decimal("0.00"):
                # La prenda de reemplazo cuesta más: el cliente DEBE pagar la diferencia a la tienda
                if destino != "PAGO_CLIENTE":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="La diferencia es a favor de la tienda; destino debe ser PAGO_CLIENTE",
                    )
                from backend.app.core.modules.ventas_pagos.models_ordenes import OrdenPago
                capturas = (await self.db.execute(select(OrdenPago).where(
                    OrdenPago.empresa_id == cambio.empresa_id, OrdenPago.cambio_id == cambio.id,
                    OrdenPago.contexto == "CAMBIO", OrdenPago.estado == "CAPTURADO",
                ))).scalars().all()
                # OrdenPago -> cambio (misma empresa) -> venta -> titular ya
                # autorizado arriba. No se debilita la comprobación de propietario.
                if (len(capturas) != 1 or
                        capturas[0].pedido_id is not None or capturas[0].reserva_id is not None or
                        capturas[0].venta_id is not None or
                        capturas[0].monto_bob != dif or capturas[0].proveedor != "STRIPE" or
                        not capturas[0].referencia_externa or not capturas[0].referencia_externa.startswith("pi_")):
                    raise HTTPException(status_code=409, detail="DIFERENCIA_PENDIENTE_DE_PAGO: falta una captura original verificable por el importe de la diferencia")
                from backend.app.core.modules.organizacion.models import TasaCambio
                orden = capturas[0]
                tasa_original = await self.db.get(TasaCambio, orden.tasa_id) if orden.tasa_id else None
                try:
                    usd = Decimal(str(orden.monto_usd))
                    tasa = Decimal(str(tasa_original.tasa_bob_por_usd)) if tasa_original else Decimal("NaN")
                    if (not usd.is_finite() or usd <= 0 or not tasa.is_finite() or tasa <= 0 or
                            type(orden.centavos_usd) is not int or usd * 100 != orden.centavos_usd or
                            (dif / tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != usd):
                        raise ValueError("Captura inconsistente")
                except (InvalidOperation, ValueError, TypeError, ArithmeticError):
                    raise HTTPException(409, detail="CONCILIACION_REQUERIDA: importes o cotización de la captura del cambio inconsistentes") from None
                # La prueba financiera no acredita recepción/condición del original
                # ni entrega del reemplazo: el bloqueo físico del bloque 6 continúa.
                raise HTTPException(409, detail="CAMBIO_FISICO_PENDIENTE: captura vinculada y titular verificados; falta el flujo verificable de recepción y entrega, no se marca resuelto")
            elif dif < Decimal("0.00"):
                # La prenda de reemplazo cuesta menos: la tienda devuelve el sobrante como SALDO o REEMBOLSO (jamás ambos)
                if destino not in ("SALDO", "REEMBOLSO"):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="La diferencia es a favor del cliente; debe elegir SALDO o REEMBOLSO exclusivo",
                    )
                sobrante = abs(dif)
                if destino == "SALDO":
                    mov_saldo = MovimientoSaldo(
                        id=uuid.uuid4(),
                        empresa_id=usuario.empresa_id,
                        cliente_id=cambio.cliente_id,
                        tipo="CREDITO",
                        monto_bob=sobrante,
                        origen_tipo="CAMBIO",
                        origen_id=cambio.id,
                        referencia_unica=uuid.uuid4(),
                        estado="CONFIRMADO",
                        creado_en=ahora,
                    )
                    self.db.add(mov_saldo)
                elif destino == "REEMBOLSO":
                    reemb = ObligacionReembolso(
                        id=uuid.uuid4(),
                        empresa_id=usuario.empresa_id,
                        cliente_id=cambio.cliente_id,
                        origen_tipo="CAMBIO",
                        origen_id=cambio.id,
                        motivo_codigo="DIFERENCIA_CAMBIO",
                        monto_bob=sobrante,
                        estado="PENDIENTE_AUTORIZACION",
                        revision=1,
                        creada_en=ahora,
                    )
                    self.db.add(reemb)
            else:
                # diferencia == 0
                if destino != "SIN_DIFERENCIA":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Sin diferencia monetaria; destino debe ser SIN_DIFERENCIA",
                    )
        else:
            # Sin reemplazo (ej. nota vencida o falta de stock): se devuelve el valor reconocido total como SALDO o REEMBOLSO
            if destino not in ("SALDO", "REEMBOLSO"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Sin prendas de reemplazo; debe liquidar valor reconocido a SALDO o REEMBOLSO",
                )
            if destino == "SALDO":
                mov_saldo = MovimientoSaldo(
                    id=uuid.uuid4(),
                    empresa_id=usuario.empresa_id,
                    cliente_id=cambio.cliente_id,
                    tipo="CREDITO",
                    monto_bob=cambio.valor_reconocido_bob,
                    origen_tipo="CAMBIO",
                    origen_id=cambio.id,
                    referencia_unica=uuid.uuid4(),
                    estado="CONFIRMADO",
                    creado_en=ahora,
                )
                self.db.add(mov_saldo)
            elif destino == "REEMBOLSO":
                reemb = ObligacionReembolso(
                    id=uuid.uuid4(),
                    empresa_id=usuario.empresa_id,
                    cliente_id=cambio.cliente_id,
                    origen_tipo="CAMBIO",
                    origen_id=cambio.id,
                    motivo_codigo="CAMBIO_SIN_SUSTITUTO",
                    monto_bob=cambio.valor_reconocido_bob,
                    estado="PENDIENTE_AUTORIZACION",
                    revision=1,
                    creada_en=ahora,
                )
                self.db.add(reemb)

        cambio.estado = "RESUELTO"
        cambio.actualizado_en = ahora
        await self.db.commit()
        return await self.obtener_por_id(usuario, cambio.id)

    async def obtener_por_id(self, usuario: Usuario, cambio_id: uuid.UUID) -> CambioDTO:
        cambio = await self.db.get(Cambio, cambio_id)
        if cambio is None or cambio.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cambio no encontrado")
        self._autorizar(usuario, cambio)
        if rol_de(usuario) == "CLIENTE" and cambio.cliente_id != usuario.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cambio no encontrado")

        stmt_det = select(DetalleCambio).where(DetalleCambio.cambio_id == cambio.id)
        detalles = (await self.db.execute(stmt_det)).scalars().all()

        return CambioDTO(
            cambio_id=cambio.id,
            venta_id=cambio.venta_id,
            cliente_id=cambio.cliente_id,
            sucursal_id=cambio.sucursal_id,
            nota_codigo=cambio.nota_codigo,
            estado=cambio.estado,
            motivo_codigo=cambio.motivo_codigo,
            motivo_descripcion=cambio.motivo_descripcion,
            valor_reconocido_bob=cambio.valor_reconocido_bob,
            diferencia_bob=cambio.diferencia_bob,
            vence_espera_en=cambio.vence_espera_en,
            modalidad_reemplazo=cambio.modalidad_reemplazo,
            direccion=cambio.direccion,
            creado_en=cambio.creado_en,
            detalles=[
                DetalleCambioItemDTO(
                    id=d.id,
                    tipo_linea=d.tipo_linea,
                    detalle_venta_id=d.detalle_venta_id,
                    variante_reemplazo_id=d.variante_reemplazo_id,
                    cantidad=d.cantidad,
                    precio_unitario_bob=d.precio_unitario_bob,
                    estado=d.estado,
                )
                for d in detalles
            ],
        )

    async def evaluar(
        self, usuario: Usuario, cambio_id: uuid.UUID, aprobado: bool, clave: Optional[uuid.UUID] = None
    ) -> CambioDTO:
        cambio = (await self.db.execute(
            select(Cambio).where(Cambio.id == cambio_id, Cambio.empresa_id == usuario.empresa_id)
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().first()
        if cambio is None or cambio.empresa_id != usuario.empresa_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cambio no encontrado")
        self._autorizar(usuario, cambio)

        rol = (usuario.rol.nombre if usuario.rol else "").upper()
        if not (es_admin(usuario) or rol in ("ENCARGADO", "ADMINISTRADOR")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo personal autorizado (Encargado o Administrador) puede evaluar cambios",
            )

        if cambio.estado != "PENDIENTE_EVALUACION":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El cambio no está en PENDIENTE_EVALUACION (estado actual: {cambio.estado})",
            )

        cambio.estado = "SOLICITADO" if aprobado else "RECHAZADO"
        cambio.actualizado_en = self.reloj.ahora()
        await self.db.commit()
        return await self.obtener_por_id(usuario, cambio.id)
