"""Servicio de Dominio: Saldo Personal del Cliente — CU09 (B1 Finanzas).

Reglas de negocio:
- Aislamiento estricto por empresa (multi-tenant).
- Saldo sin vencimiento y no transferible a terceros.
- Retenciones atómicas bajo SELECT ... FOR UPDATE en movimientos_saldo.
- Cálculo de saldo disponible y retenido por libro de movimientos.
- Idempotencia estricta vía Idempotency-Key (referencia_unica).
"""
import uuid
from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.posventa.models import MovimientoSaldo
from backend.app.core.modules.posventa.schemas import (
    MovimientoSaldoDTO,
    SaldoAplicadoDTO,
    SaldoResumenDTO,
)
from backend.app.core.permisos import es_admin, rol_de
from backend.app.core.reloj import RelojSistema


class SaldoService:
    def __init__(self, db: AsyncSession, reloj=None):
        self.db = db
        self.reloj = reloj or RelojSistema()

    async def acreditar_saldo(
        self,
        cliente_id: uuid.UUID,
        empresa_id: uuid.UUID,
        monto_bob: Decimal,
        origen_tipo: str = "MANUAL",
        origen_id: Optional[uuid.UUID] = None,
        referencia_unica: Optional[uuid.UUID] = None,
    ) -> MovimientoSaldo:
        """Acredita saldo a la cuenta personal del cliente dentro de la empresa."""
        if monto_bob <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El monto a acreditar debe ser mayor a cero",
            )
        ref = referencia_unica or uuid.uuid4()
        mov = MovimientoSaldo(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            cliente_id=cliente_id,
            tipo="CREDITO",
            monto_bob=monto_bob,
            origen_tipo=origen_tipo,
            origen_id=origen_id or uuid.uuid4(),
            referencia_unica=ref,
            estado="CONFIRMADO",
            creado_en=self.reloj.ahora(),
        )
        self.db.add(mov)
        await self.db.flush()
        return mov

    async def debitar_saldo(
        self,
        cliente_id: uuid.UUID,
        empresa_id: uuid.UUID,
        monto_bob: Decimal,
        origen_tipo: str = "VENTA",
        origen_id: Optional[uuid.UUID] = None,
        referencia_unica: Optional[uuid.UUID] = None,
    ) -> MovimientoSaldo:
        """Debita saldo personal del cliente para pago directo (CU19/CU09)."""
        if monto_bob <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El monto a debitar debe ser mayor a cero",
            )
        disp, _, _ = await self.calcular_totales(
            cliente_id=cliente_id, empresa_id=empresa_id, con_bloqueo=True,
        )
        if monto_bob > disp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Saldo insuficiente: disponible {disp} BOB, requerido {monto_bob} BOB",
            )
        ref = referencia_unica or uuid.uuid4()
        mov = MovimientoSaldo(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            cliente_id=cliente_id,
            tipo="DEBITO",
            monto_bob=monto_bob,
            origen_tipo=origen_tipo,
            origen_id=origen_id or uuid.uuid4(),
            referencia_unica=ref,
            estado="CONFIRMADO",
            creado_en=self.reloj.ahora(),
        )
        self.db.add(mov)
        await self.db.flush()
        return mov

    async def calcular_totales(
        self, cliente_id: uuid.UUID, empresa_id: uuid.UUID, con_bloqueo: bool = False,
    ) -> Tuple[Decimal, Decimal, List[MovimientoSaldo]]:
        """Calcula (saldo_disponible, saldo_retenido, movimientos) bajo libro append-only."""
        stmt = (
            select(MovimientoSaldo)
            .where(
                MovimientoSaldo.empresa_id == empresa_id,
                MovimientoSaldo.cliente_id == cliente_id,
            )
            .order_by(MovimientoSaldo.creado_en.desc())
        )
        if con_bloqueo:
            stmt = stmt.with_for_update()

        result = await self.db.execute(stmt)
        movimientos = list(result.scalars().all())

        # Sumas de créditos y débitos
        total_credito = Decimal("0.00")
        total_debito = Decimal("0.00")

        # Agrupación por referencia_unica para evaluar retenciones activas
        por_ref: dict[uuid.UUID, dict[str, Decimal]] = {}

        for m in movimientos:
            monto = Decimal(str(m.monto_bob))
            if m.tipo in ("CREDITO", "RESTAURACION"):
                total_credito += monto
            elif m.tipo == "DEBITO":
                total_debito += monto

            if m.referencia_unica not in por_ref:
                por_ref[m.referencia_unica] = {}
            por_ref[m.referencia_unica][m.tipo] = monto

        # Una retención está activa si existe RETENCION y no hay DEBITO ni LIBERACION con esa misma ref
        saldo_retenido = Decimal("0.00")
        for ref, tipos in por_ref.items():
            if "RETENCION" in tipos:
                if "DEBITO" not in tipos and "LIBERACION" not in tipos:
                    saldo_retenido += tipos["RETENCION"]

        saldo_total = total_credito - total_debito
        saldo_disponible = max(Decimal("0.00"), saldo_total - saldo_retenido)

        return saldo_disponible, saldo_retenido, movimientos

    async def obtener_saldo_resumen(
        self, cliente_id: uuid.UUID, empresa_id: uuid.UUID,
    ) -> SaldoResumenDTO:
        disponible, retenido, movs = await self.calcular_totales(
            cliente_id=cliente_id, empresa_id=empresa_id, con_bloqueo=False,
        )
        dtos = [
            MovimientoSaldoDTO(
                id=m.id,
                tipo=m.tipo,
                monto_bob=Decimal(str(m.monto_bob)),
                origen_tipo=m.origen_tipo,
                origen_id=m.origen_id,
                referencia_unica=m.referencia_unica,
                estado=m.estado,
                creado_en=m.creado_en,
            )
            for m in movs
        ]
        return SaldoResumenDTO(
            saldo_disponible_bob=disponible,
            saldo_retenido_bob=retenido,
            movimientos=dtos,
        )

    async def aplicar_saldo_venta(
        self,
        usuario: Usuario,
        venta_id: uuid.UUID,
        monto_bob: Decimal,
        clave_idempotencia: uuid.UUID,
        revision: Optional[int] = 1,
    ) -> SaldoAplicadoDTO:
        """Aplica retención atómica de saldo a una venta presencial o digital (CU09)."""
        if monto_bob <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El monto a aplicar debe ser mayor a cero",
            )

        empresa_id = usuario.empresa_id
        if not empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )

        # 1. Idempotencia: Verificar si ya existe una retención con esta clave
        existente = await self.db.execute(
            select(MovimientoSaldo).where(
                MovimientoSaldo.empresa_id == empresa_id,
                MovimientoSaldo.referencia_unica == clave_idempotencia,
                MovimientoSaldo.tipo == "RETENCION",
            )
        )
        mov_existente = existente.scalars().first()

        # 2. Bloquear la venta para validar montos y estados
        r_venta = await self.db.execute(
            text(
                "SELECT id, empresa_id, cliente_id, estado, total, expira_en "
                "FROM comercial.ventas WHERE id = :vid FOR UPDATE"
            ),
            {"vid": venta_id},
        )
        fila_venta = r_venta.first()
        if not fila_venta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Venta no encontrada",
            )

        v_id, v_empresa_id, v_cliente_id, v_estado, v_total, v_expira = fila_venta

        if v_empresa_id != empresa_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Aislamiento por empresa: venta pertenece a otra organización",
            )

        # Permisos: si es CLIENTE, debe ser dueño
        rol = rol_de(usuario)
        if rol == "CLIENTE" and v_cliente_id != usuario.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el cliente titular puede aplicar su saldo personal",
            )

        cliente_efectivo_id = v_cliente_id or usuario.id

        if mov_existente is not None:
            # Respuesta idempotente
            disp, ret, _ = await self.calcular_totales(
                cliente_id=cliente_efectivo_id, empresa_id=empresa_id, con_bloqueo=False,
            )
            restante = max(Decimal("0.00"), Decimal(str(v_total)) - Decimal(str(mov_existente.monto_bob)))
            return SaldoAplicadoDTO(
                saldo_disponible_bob=disp,
                saldo_retenido_bob=ret,
                movimiento_id=mov_existente.id,
                restante_por_pagar_bob=restante,
            )

        if str(v_estado) in ("PAGADA", "CANCELADA", "DEVUELTA"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No se puede aplicar saldo a una venta en estado {v_estado}",
            )

        if v_expira is not None and v_expira <= self.reloj.ahora():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ventana de pago de la venta vencida",
            )

        if monto_bob > Decimal(str(v_total)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El importe supera el total de la venta; rechazar sin débito parcial implícito",
            )

        # 3. Bloqueo FOR UPDATE de los movimientos del cliente para evitar doble gasto concurrente
        disp, ret, _ = await self.calcular_totales(
            cliente_id=cliente_efectivo_id, empresa_id=empresa_id, con_bloqueo=True,
        )

        if monto_bob > disp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Importe supera el saldo disponible del cliente; no se permite débito parcial implícito",
            )

        # 4. Registrar la RETENCION
        mov = MovimientoSaldo(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            cliente_id=cliente_efectivo_id,
            tipo="RETENCION",
            monto_bob=monto_bob,
            origen_tipo="VENTA",
            origen_id=v_id,
            referencia_unica=clave_idempotencia,
            estado="CONFIRMADO",
            creado_en=self.reloj.ahora(),
        )
        self.db.add(mov)
        await self.db.flush()
        await self.db.commit()

        disp_nuevo = disp - monto_bob
        ret_nuevo = ret + monto_bob
        restante = max(Decimal("0.00"), Decimal(str(v_total)) - monto_bob)

        return SaldoAplicadoDTO(
            saldo_disponible_bob=disp_nuevo,
            saldo_retenido_bob=ret_nuevo,
            movimiento_id=mov.id,
            restante_por_pagar_bob=restante,
        )

    async def aplicar_saldo_pedido(
        self,
        usuario: Usuario,
        pedido_id: uuid.UUID,
        monto_bob: Decimal,
        clave_idempotencia: uuid.UUID,
        revision: Optional[int] = 1,
    ) -> SaldoAplicadoDTO:
        """Aplica retención atómica de saldo a un pedido de compra digital (CU09)."""
        if monto_bob <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El monto a aplicar debe ser mayor a cero",
            )

        empresa_id = usuario.empresa_id
        if not empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )

        # 1. Idempotencia
        existente = await self.db.execute(
            select(MovimientoSaldo).where(
                MovimientoSaldo.empresa_id == empresa_id,
                MovimientoSaldo.referencia_unica == clave_idempotencia,
                MovimientoSaldo.tipo == "RETENCION",
            )
        )
        mov_existente = existente.scalars().first()

        # 2. Bloquear pedido_compra
        r_ped = await self.db.execute(
            text(
                "SELECT id, empresa_id, cliente_id, estado, total_bob "
                "FROM comercial.pedidos_compra WHERE id = :pid FOR UPDATE"
            ),
            {"pid": pedido_id},
        )
        fila_ped = r_ped.first()
        if not fila_ped:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pedido de compra no encontrado",
            )

        p_id, p_empresa_id, p_cliente_id, p_estado, p_total = fila_ped

        if p_empresa_id != empresa_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Aislamiento por empresa: pedido pertenece a otra organización",
            )

        rol = rol_de(usuario)
        if rol == "CLIENTE" and p_cliente_id != usuario.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el cliente titular puede aplicar su saldo personal",
            )

        cliente_efectivo_id = p_cliente_id

        if mov_existente is not None:
            disp, ret, _ = await self.calcular_totales(
                cliente_id=cliente_efectivo_id, empresa_id=empresa_id, con_bloqueo=False,
            )
            restante = max(Decimal("0.00"), Decimal(str(p_total)) - Decimal(str(mov_existente.monto_bob)))
            return SaldoAplicadoDTO(
                saldo_disponible_bob=disp,
                saldo_retenido_bob=ret,
                movimiento_id=mov_existente.id,
                restante_por_pagar_bob=restante,
            )

        if str(p_estado) in ("CANCELADO", "ENTREGADO", "PAGADO"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No se puede aplicar saldo a un pedido en estado {p_estado}",
            )

        if monto_bob > Decimal(str(p_total)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El importe supera el total del pedido",
            )

        # 3. Bloqueo FOR UPDATE
        disp, ret, _ = await self.calcular_totales(
            cliente_id=cliente_efectivo_id, empresa_id=empresa_id, con_bloqueo=True,
        )

        if monto_bob > disp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Importe supera el saldo disponible del cliente; no se permite débito parcial implícito",
            )

        # 4. Registrar RETENCION
        mov = MovimientoSaldo(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            cliente_id=cliente_efectivo_id,
            tipo="RETENCION",
            monto_bob=monto_bob,
            origen_tipo="PEDIDO",
            origen_id=p_id,
            referencia_unica=clave_idempotencia,
            estado="CONFIRMADO",
            creado_en=self.reloj.ahora(),
        )
        self.db.add(mov)
        await self.db.flush()
        await self.db.commit()

        disp_nuevo = disp - monto_bob
        ret_nuevo = ret + monto_bob
        restante = max(Decimal("0.00"), Decimal(str(p_total)) - monto_bob)

        return SaldoAplicadoDTO(
            saldo_disponible_bob=disp_nuevo,
            saldo_retenido_bob=ret_nuevo,
            movimiento_id=mov.id,
            restante_por_pagar_bob=restante,
        )
