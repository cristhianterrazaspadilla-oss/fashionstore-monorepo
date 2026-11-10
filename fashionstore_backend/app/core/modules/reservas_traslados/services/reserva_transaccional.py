"""Núcleo transaccional compartido para apartar stock de reservas (CU04/CU08/CU18).

Centraliza las validaciones y la persistencia que deben ser idénticas entre la
creación online (`ReservaService.crear`) y la aceptación offline
(`SincronizacionService.procesarOperacion`):

- validación de líneas (cantidad positiva y variante única),
- validación de la fecha de visita contra el origen y el vencimiento,
- validación de sucursal y variantes dentro de la empresa,
- bloqueo pesimista determinista del inventario,
- decisión LOCAL/TRASLADO por línea,
- cabecera, detalles, movimiento de Kardex y traslados en una sola transacción.

Las diferencias de contrato se resuelven en los servicios llamadores: la
creación online exige traslados explícitos y responde 409; la aceptación
offline no crea traslados y convierte el faltante en rechazo durable.
"""
import secrets
import string
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.reloj import RelojSistema, asegurar_utc
from backend.app.core.modules.catalogo.repositories.variante_repository import VarianteRepository
from backend.app.core.modules.inventario.models import MovimientoInventario
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.reservas_traslados.models import (
    DetalleReserva,
    DetalleTraslado,
    Reserva,
    Traslado,
)
from backend.app.core.modules.reservas_traslados.repositories.reserva_repository import ReservaRepository
from backend.app.core.modules.reservas_traslados.repositories.traslado_repository import TrasladoRepository

CODIGO_ALFABETO = string.ascii_uppercase + string.digits
MODO_LOCAL = "LOCAL"
MODO_TRASLADO = "TRASLADO"


def validar_lineas_reserva(lineas: List[Any]) -> None:
    """Valida cantidad positiva y una sola línea por variante.

    Es un error de forma (HTTP 400) tanto en línea como en sincronización
    offline: nunca debe llegar a apartar stock ni a una violación de la
    restricción `uq_detalles_reserva_reserva_variante`.
    """
    if not lineas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La reserva requiere al menos una linea",
        )
    vistos = set()
    for linea in lineas:
        if linea.cantidad <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cantidad solicitada debe ser mayor a cero",
            )
        if linea.variante_id in vistos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Variante duplicada en la reserva (una linea por variante)",
            )
        vistos.add(linea.variante_id)


def validar_visita_reserva(
    visita_en: Optional[datetime],
    origen_plazo_en: datetime,
    vence_en: datetime,
) -> None:
    """La visita debe ser futura respecto al origen y caber en la vigencia.

    No sustituye el origen del plazo: solo se comprueba que sea coherente antes
    de apartar stock. El contrato no define un código de rechazo comercial para
    una visita inválida, por lo que se trata como error de validación (422).
    """
    if visita_en is None:
        return
    visita = asegurar_utc(visita_en)
    origen = asegurar_utc(origen_plazo_en)
    vence = asegurar_utc(vence_en)
    if visita < origen:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La fecha de visita no puede ser anterior a la creacion de la reserva",
        )
    if visita > vence:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La fecha de visita debe estar dentro de la vigencia de la reserva",
        )


class ReservaTransaccional:
    """Operaciones comunes de apartado para reservas online y offline."""

    def __init__(self, db: AsyncSession, reloj: Optional[Any] = None):
        self.db = db
        self.reloj = reloj or RelojSistema()
        self.reserva_repo = ReservaRepository(db)
        self.inventario_repo = InventarioRepository(db)
        self.movimiento_repo = MovimientoRepository(db)
        self.traslado_repo = TrasladoRepository(db)
        self.sucursal_repo = SucursalRepository(db)
        self.variante_repo = VarianteRepository(db)

    # ---------------- validaciones de ámbito ----------------
    async def validar_sucursal_destino(self, sucursal_id: uuid.UUID, empresa_id: uuid.UUID):
        sucursal = await self.sucursal_repo.buscarPorId(sucursal_id)
        if sucursal is None or sucursal.empresa_id != empresa_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sucursal destino no encontrada",
            )
        if not sucursal.activa:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sucursal destino inactiva",
            )
        return sucursal

    async def validar_origenes(self, lineas: List[Any], empresa_id: uuid.UUID) -> None:
        for linea in lineas:
            origen_id = getattr(linea, "sucursal_origen_id", None)
            if origen_id is None:
                continue
            origen = await self.sucursal_repo.buscarPorId(origen_id)
            if origen is None or origen.empresa_id != empresa_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Sucursal origen no encontrada",
                )
            if not origen.activa:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Sucursal origen inactiva",
                )

    async def validar_variantes(
        self, lineas: List[Any], empresa_id: uuid.UUID
    ) -> Dict[uuid.UUID, Any]:
        variantes: Dict[uuid.UUID, Any] = {}
        for linea in lineas:
            variante = await self.variante_repo.buscarPorId(linea.variante_id)
            if variante is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Variante {linea.variante_id} no encontrada",
                )
            if variante.empresa_id != empresa_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Variante {linea.variante_id} no encontrada",
                )
            if not variante.activa:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Variante {variante.sku} inactiva",
                )
            variantes[linea.variante_id] = variante
        return variantes

    # ---------------- inventario ----------------
    async def bloquear_filas(
        self,
        sucursal_destino_id: uuid.UUID,
        lineas: List[Any],
        incluir_origenes: bool = True,
    ) -> Dict[Tuple[uuid.UUID, uuid.UUID], Any]:
        claves = [(sucursal_destino_id, linea.variante_id) for linea in lineas]
        if incluir_origenes:
            claves += [
                (linea.sucursal_origen_id, linea.variante_id)
                for linea in lineas
                if getattr(linea, "sucursal_origen_id", None) is not None
            ]
        # El repositorio ordena las claves para evitar interbloqueos.
        return await self.inventario_repo.bloquearFilas(claves)

    def planificar_apartado(
        self,
        filas: Dict[Tuple[uuid.UUID, uuid.UUID], Any],
        sucursal_destino_id: uuid.UUID,
        lineas: List[Any],
        permitir_traslado: bool,
        variantes: Optional[Dict[uuid.UUID, Any]] = None,
    ) -> Tuple[List[Tuple[Any, str, int]], Optional[str]]:
        """Decide por línea LOCAL o TRASLADO sin mutar nada.

        Retorna ``(planes, faltante)``. Si ``faltante`` no es ``None`` ninguna
        línea debe persistirse; el llamador decide entre 409 (online) o un
        rechazo durable SIN_STOCK (offline).
        """
        variantes = variantes or {}
        planes: List[Tuple[Any, str, int]] = []
        for linea in lineas:
            fila_destino = filas.get((sucursal_destino_id, linea.variante_id))
            disponible_destino = fila_destino.disponible if fila_destino else 0
            if disponible_destino >= linea.cantidad:
                planes.append((linea, MODO_LOCAL, linea.cantidad))
                continue
            origen_id = getattr(linea, "sucursal_origen_id", None)
            if not permitir_traslado or origen_id is None:
                sku = getattr(variantes.get(linea.variante_id), "sku", linea.variante_id)
                return [], f"Sin stock local para {sku}"
            fila_origen = filas.get((origen_id, linea.variante_id))
            disponible_origen = fila_origen.disponible if fila_origen else 0
            if disponible_origen < linea.cantidad:
                sku = getattr(variantes.get(linea.variante_id), "sku", linea.variante_id)
                return [], f"Sin stock suficiente en origen para {sku}"
            planes.append((linea, MODO_TRASLADO, linea.cantidad))
        return planes, None

    # ---------------- persistencia ----------------
    async def persistir_apartado(
        self,
        reserva: Reserva,
        planes: List[Tuple[Any, str, int]],
        variantes: Dict[uuid.UUID, Any],
        filas: Dict[Tuple[uuid.UUID, uuid.UUID], Any],
        permitir_traslado: bool,
        cliente_id: uuid.UUID,
        observacion_kardex: Optional[str] = None,
    ) -> None:
        """Crea detalles, descuenta stock y registra Kardex/traslados.

        Corre dentro de la transacción del llamador; este módulo solo hace
        flush y nunca confirma ni revierte.
        """
        for linea, modo, cantidad in planes:
            detalle = DetalleReserva(
                reserva_id=reserva.id,
                variante_id=linea.variante_id,
                cantidad_solicitada=linea.cantidad,
                cantidad_reservada=cantidad if modo == MODO_LOCAL else 0,
                cantidad_pendiente_traslado=cantidad if modo == MODO_TRASLADO else 0,
                cantidad_vendida=0,
                cantidad_liberada=0,
                estado_linea="RESERVADA" if modo == MODO_LOCAL else "PENDIENTE_TRASLADO",
            )
            self.db.add(detalle)
            await self.db.flush()

            if modo == MODO_LOCAL:
                fila = filas.get((reserva.sucursal_destino_id, linea.variante_id))
                if fila is None or fila.disponible < cantidad:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Stock insuficiente al confirmar el apartado",
                    )
                fila.disponible -= cantidad
                fila.reservado += cantidad
                await self.db.flush()
                await self.movimiento_repo.registrar(
                    MovimientoInventario(
                        variante_id=linea.variante_id,
                        sucursal_destino_id=reserva.sucursal_destino_id,
                        tipo="RESERVA",
                        cantidad=cantidad,
                        costo_unitario=Decimal(
                            str(variantes[linea.variante_id].costo_promedio or 0)
                        ),
                        referencia_tipo="RESERVA",
                        referencia_id=reserva.id,
                        linea_referencia_id=detalle.id,
                        observacion=observacion_kardex or f"Reserva {reserva.codigo}",
                    )
                )
                continue

            if not permitir_traslado:  # pragma: no cover (defensivo)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="La aceptacion offline no admite traslados",
                )
            traslado = Traslado(
                empresa_id=reserva.empresa_id,
                reserva_id=reserva.id,
                sucursal_origen_id=linea.sucursal_origen_id,
                sucursal_destino_id=reserva.sucursal_destino_id,
                estado="SOLICITADO",
                solicitado_por_id=cliente_id,
            )
            await self.traslado_repo.crear(traslado)
            self.db.add(
                DetalleTraslado(
                    traslado_id=traslado.id,
                    detalle_reserva_id=detalle.id,
                    variante_id=linea.variante_id,
                    cantidad=cantidad,
                )
            )
            await self.db.flush()

    def generar_codigo(self) -> str:
        return "FS-" + "".join(secrets.choice(CODIGO_ALFABETO) for _ in range(6))

    async def codigo_unico(self, empresa_id: Optional[uuid.UUID] = None) -> str:
        for _ in range(5):
            codigo = self.generar_codigo()
            if not await self.reserva_repo.existeCodigo(codigo, empresa_id=empresa_id):
                return codigo
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo generar un codigo de reserva unico",
        )
