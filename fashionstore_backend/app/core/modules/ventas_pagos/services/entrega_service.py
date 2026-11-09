"""Controller EntregaService — CU16 (extensión: delivery por anillos)."""
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from backend.app.core.ambito_comercial import empresa_comercial, exigir_empresa_recurso, sucursal_autorizada
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.permisos import es_admin, exigir_sucursal, rol_de
from backend.app.core.modules.ventas_pagos.models import Venta
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.ventas_pagos.repositories.pedido_repository import PedidoRepository
from backend.app.core.modules.organizacion.repositories.sucursal_repository import SucursalRepository
from backend.app.core.modules.ventas_pagos.repositories.venta_repository import VentaRepository
from backend.app.core.modules.ventas_pagos.schemas import CotizacionDTO, PedidoDTO

RECOJO_FLUJO = ["SOLICITADO", "PREPARADO", "LISTO_RECOJO", "RECOGIDO"]
DELIVERY_FLUJO = ["SOLICITADO", "PREPARADO", "EN_REPARTO", "ENTREGADO"]


def costo_delivery(tarifa_base, incremento, anillo_sucursal: int, anillo_destino: int) -> Decimal:
    base = Decimal(str(tarifa_base or 0))
    incr = Decimal(str(incremento or 0))
    return (base + abs(anillo_destino - anillo_sucursal) * incr).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


class EntregaService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.pedido_repo = PedidoRepository(db)
        self.sucursal_repo = SucursalRepository(db)
        self.venta_repo = VentaRepository(db)

    async def cotizar(self, usuario: Usuario, sucursal_id: uuid.UUID, anillo_destino: int) -> CotizacionDTO:
        sucursal = await sucursal_autorizada(self.db, usuario, sucursal_id)
        if sucursal is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sucursal no encontrada")
        if not sucursal.delivery_activo:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sucursal sin delivery activo")
        minimo = int(sucursal.anillo_minimo_delivery or 1)
        maximo = int(sucursal.anillo_maximo_delivery or 10)
        if not (minimo <= anillo_destino <= maximo):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Anillo fuera de rango [{minimo}, {maximo}]",
            )
        anillo_suc = int(sucursal.numero_anillo or minimo)
        base = Decimal(str(sucursal.tarifa_base_delivery or 0))
        incr = Decimal(str(sucursal.incremento_anillo_delivery or 0))
        return CotizacionDTO(
            sucursal_id=sucursal.id, anillo_sucursal=anillo_suc,
            anillo_destino=anillo_destino, tarifa_base=base,
            incremento_anillo=incr,
            costo_entrega=costo_delivery(base, incr, anillo_suc, anillo_destino),
        )

    def _calcular_capacidades(
        self, pedido, usuario: Optional[Usuario] = None, venta: Optional[Any] = None
    ) -> Tuple[bool, bool, Optional[str]]:
        if usuario is None:
            return False, False, None

        admin = es_admin(usuario)
        rol = rol_de(usuario)
        es_duenio = (rol == "CLIENTE" and pedido.cliente_id == usuario.id)
        propia_suc = (
            usuario.empleado.sucursal_id
            if getattr(usuario, "empleado", None) is not None
            else None
        )
        es_operativo_sucursal = (
            rol in ("ENCARGADO", "CAJERO") and propia_suc is not None and propia_suc == pedido.sucursal_id
        )

        estado_v = None
        if venta is not None:
            estado_v = venta.estado if isinstance(venta.estado, str) else getattr(venta.estado, "name", str(venta.estado))

        autorizado_cancelar = admin or es_duenio or es_operativo_sucursal
        puede_cancelar = (
            autorizado_cancelar
            and pedido.estado == "SOLICITADO"
            and estado_v == "PENDIENTE_PAGO"
        )

        puede_transicionar = False
        siguiente_estado = None

        autorizado_operar = admin or es_operativo_sucursal
        if autorizado_operar:
            flujo = RECOJO_FLUJO if pedido.modalidad == "RECOJO" else DELIVERY_FLUJO
            if pedido.estado in flujo:
                idx = flujo.index(pedido.estado)
                if idx + 1 < len(flujo):
                    candidato = flujo[idx + 1]
                    if pedido.estado == "SOLICITADO" and candidato == "PREPARADO":
                        if estado_v == "PAGADA":
                            puede_transicionar = True
                            siguiente_estado = candidato
                    else:
                        puede_transicionar = True
                        siguiente_estado = candidato

        return puede_cancelar, puede_transicionar, siguiente_estado

    def _a_dto(
        self, pedido, usuario: Optional[Usuario] = None, venta: Optional[Any] = None
    ) -> PedidoDTO:
        dto = PedidoDTO.model_validate(pedido)
        p_canc, p_trans, sig = self._calcular_capacidades(pedido, usuario, venta)
        dto.puede_cancelar = p_canc
        dto.puede_transicionar = p_trans
        dto.siguiente_estado = sig
        return dto

    def _autorizar_cola(self, usuario: Usuario, sucursal_id: Optional[uuid.UUID]) -> None:
        empresa_comercial(usuario)
        if es_admin(usuario):
            return
        rol = rol_de(usuario)
        if rol in ("ENCARGADO", "CAJERO"):
            if sucursal_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Indique la sucursal de su ámbito",
                )
            exigir_sucursal(usuario, sucursal_id)
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo personal operativo o Administrador")

    def _autorizar_pedido(self, usuario: Usuario, pedido) -> None:
        exigir_empresa_recurso(usuario, pedido)
        if es_admin(usuario):
            return
        rol = rol_de(usuario)
        if rol == "CLIENTE":
            if pedido.cliente_id != usuario.id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pedido de otro cliente")
            return
        if rol in ("ENCARGADO", "CAJERO"):
            exigir_sucursal(usuario, pedido.sucursal_id)
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado")

    async def mis_pedidos(self, usuario: Usuario, limit=50, offset=0):
        empresa_id = empresa_comercial(usuario)
        if rol_de(usuario) != "CLIENTE":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el Cliente consulta sus pedidos")
        items, total = await self.pedido_repo.pedidosDeCliente(usuario.id, limit=limit, offset=offset, empresa_id=empresa_id)
        ventas_map = {}
        if items:
            v_ids = [p.venta_id for p in items]
            res = await self.db.execute(select(Venta).where(Venta.id.in_(v_ids), Venta.empresa_id == empresa_comercial(usuario)))
            for v in res.scalars().all():
                ventas_map[v.id] = v
        return {"total": total, "limit": limit, "offset": offset,
                "items": [self._a_dto(p, usuario=usuario, venta=ventas_map.get(p.venta_id)) for p in items]}

    async def obtener(self, usuario: Usuario, pedido_id: uuid.UUID) -> PedidoDTO:
        pedido = await self.pedido_repo.buscarPorId(pedido_id, empresa_id=empresa_comercial(usuario))
        if pedido is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
        self._autorizar_pedido(usuario, pedido)
        await sucursal_autorizada(self.db, usuario, pedido.sucursal_id)
        venta = await self.venta_repo.buscarPorId(pedido.venta_id, empresa_id=empresa_comercial(usuario))
        return self._a_dto(pedido, usuario=usuario, venta=venta)

    async def cola(
        self, usuario: Usuario, sucursal_id: Optional[uuid.UUID] = None,
        estado: Optional[str] = None, limit: int = 50, offset: int = 0,
    ):
        self._autorizar_cola(usuario, sucursal_id)
        if sucursal_id is not None:
            await sucursal_autorizada(self.db, usuario, sucursal_id)
        items, total = await self.pedido_repo.cola(
            sucursal_id=sucursal_id, estado=estado, limit=limit, offset=offset, empresa_id=empresa_comercial(usuario)
        )
        ventas_map = {}
        if items:
            v_ids = [p.venta_id for p in items]
            res = await self.db.execute(select(Venta).where(Venta.id.in_(v_ids), Venta.empresa_id == empresa_comercial(usuario)))
            for v in res.scalars().all():
                ventas_map[v.id] = v
        return {"total": total, "limit": limit, "offset": offset,
                "items": [self._a_dto(p, usuario=usuario, venta=ventas_map.get(p.venta_id)) for p in items]}

    async def transicionar(self, usuario: Usuario, pedido_id: uuid.UUID, destino: str) -> PedidoDTO:
        pedido = await self.pedido_repo.buscarPorId(pedido_id, empresa_id=empresa_comercial(usuario))
        if pedido is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
        self._autorizar_pedido(usuario, pedido)
        await sucursal_autorizada(self.db, usuario, pedido.sucursal_id)
        rol = rol_de(usuario)
        if rol not in ("ENCARGADO", "CAJERO") and not es_admin(usuario):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo personal operativo")
        if not es_admin(usuario):
            exigir_sucursal(usuario, pedido.sucursal_id)
        venta = await self.venta_repo.buscarPorId(pedido.venta_id, empresa_id=empresa_comercial(usuario))
        if destino == pedido.estado:
            return self._a_dto(pedido, usuario=usuario, venta=venta)
        flujo = RECOJO_FLUJO if pedido.modalidad == "RECOJO" else DELIVERY_FLUJO
        if destino == "CANCELADO":
            return await self.cancelar(usuario, pedido_id)
        if destino not in flujo:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transición inválida para {pedido.modalidad}: {pedido.estado} -> {destino}",
            )
        actual_idx = flujo.index(pedido.estado) if pedido.estado in flujo else -1
        if flujo.index(destino) != actual_idx + 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transición no secuencial: {pedido.estado} -> {destino}",
            )
        if pedido.estado == "SOLICITADO" and destino == "PREPARADO":
            estado_v = venta.estado if isinstance(venta.estado, str) else venta.estado.name
            if estado_v != "PAGADA":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Solo pedidos pagados entran a preparación",
                )
        try:
            pedido.estado = destino
            await self.db.flush()
            await self.db.commit()
            return self._a_dto(pedido, usuario=usuario, venta=venta)
        except Exception:
            await self.db.rollback()
            raise

    async def cancelar(self, usuario: Usuario, pedido_id: uuid.UUID) -> PedidoDTO:
        pedido = await self.pedido_repo.buscarPorId(pedido_id, empresa_id=empresa_comercial(usuario))
        if pedido is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
        self._autorizar_pedido(usuario, pedido)
        await sucursal_autorizada(self.db, usuario, pedido.sucursal_id)
        if es_admin(usuario):
            pass
        else:
            rol = rol_de(usuario)
            if rol == "CLIENTE":
                if pedido.cliente_id != usuario.id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Pedido de otro cliente",
                    )
            elif rol in ("ENCARGADO", "CAJERO"):
                exigir_sucursal(usuario, pedido.sucursal_id)
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Rol no autorizado para cancelar pedidos",
                )
        venta = await self.venta_repo.buscarPorId(pedido.venta_id, empresa_id=empresa_comercial(usuario))
        if pedido.estado in ("RECOGIDO", "ENTREGADO", "CANCELADO"):
            if pedido.estado == "CANCELADO":
                return self._a_dto(pedido, usuario=usuario, venta=venta)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pedido ya finalizado")
        estado_v = venta.estado if isinstance(venta.estado, str) else venta.estado.name
        if estado_v == "PAGADA":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pedido pagado: la cancelación usa devolución (CU12), no cancela stock digital",
            )
        if estado_v != "PENDIENTE_PAGO" or pedido.estado != "SOLICITADO":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Solo se cancela en SOLICITADO con venta PENDIENTE_PAGO",
            )
        from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService

        try:
            venta.expira_en = venta.creada_en
            await self.db.flush()
            await self.db.commit()
            resumen = await StripeService(self.db).cancelarVencidas(
                lote=1, empresa_id=empresa_comercial(usuario), venta_id=venta.id
            )
            pedido = await self.pedido_repo.buscarPorId(pedido_id, empresa_id=empresa_comercial(usuario))
            if pedido.estado != "CANCELADO":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="No se pudo cancelar el pedido",
                )
            return self._a_dto(pedido, usuario=usuario, venta=venta)
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise
