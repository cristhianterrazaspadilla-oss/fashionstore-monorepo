"""CU24 — Expirar reserva automáticamente (RF10, RF12).

Job testeable con reloj inyectado, advisory lock, SKIP LOCKED e
idempotencia por reserva. Via endpoint manual (personal) y servicio.
"""
import uuid
from httpx import AsyncClient
from sqlalchemy import select, func
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.reservas_traslados.models import Reserva
from tests.helpers_ciclo2 import (
    activar_adelanto,
    bolsa,
    crear_cliente,
    crear_staff,
    crear_sucursal,
    crear_variante_con_stock,
    forzar_vencimiento,
    post_reserva,
    sucursal_semilla,
)


async def _reserva(id_reserva):
    async with AsyncSessionLocal() as db:
        return await db.get(Reserva, uuid.UUID(id_reserva))


async def test_expira_local_24h_y_libera(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, destino, 4, tag="e1")
    async with await crear_cliente("e1") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 3, None)]))
        rid = resp.json()["id"]
        await forzar_vencimiento(rid)
        r = await cliente_http.post("/api/v1/reservas/expiracion/ejecutar")
        assert r.status_code == 200, r.text
        datos = r.json()
        assert rid in datos["expiradas"]
        assert (await _reserva(rid)).estado == "VENCIDA"
        async with AsyncSessionLocal() as db:
            reg = (
                await db.execute(
                    select(InventarioSucursal).where(
                        InventarioSucursal.variante_id == uuid.UUID(var["variante_id"]),
                        InventarioSucursal.sucursal_id == uuid.UUID(destino),
                    )
                )
            ).scalars().one()
            assert (reg.disponible, reg.reservado) == (4, 0)
            n = await db.execute(
                select(func.count()).select_from(MovimientoInventario).where(
                    MovimientoInventario.referencia_tipo == "RESERVA",
                    MovimientoInventario.referencia_id == uuid.UUID(rid),
                )
            )
            assert n.scalar() == 2  # RESERVA + LIBERACION_RESERVA


async def test_expiracion_idempotente_y_concurrente(cliente_http: AsyncClient):
    import asyncio

    destino = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, destino, 6, tag="e2")
    async with await crear_cliente("e2") as cli:
        r1 = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, None)]))
        r2 = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, None)]))
        await forzar_vencimiento(r1.json()["id"])
        await forzar_vencimiento(r2.json()["id"])
        a, b = await asyncio.gather(
            cliente_http.post("/api/v1/reservas/expiracion/ejecutar"),
            cliente_http.post("/api/v1/reservas/expiracion/ejecutar"),
        )
        assert a.status_code == 200 and b.status_code == 200
        total = sorted(a.json()["expiradas"] + b.json()["expiradas"])
        assert total == sorted([r1.json()["id"], r2.json()["id"]])
        # Tercera corrida no encuentra nada vencido pendiente.
        c = await cliente_http.post("/api/v1/reservas/expiracion/ejecutar")
        assert c.json()["expiradas"] == [] and c.json()["procesadas"] == 0


async def test_no_expira_vigente_ni_permiso_cliente(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, destino, 2, tag="e3")
    async with await crear_cliente("e3") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 1, None)]))
        rid = resp.json()["id"]
        r = await cliente_http.post("/api/v1/reservas/expiracion/ejecutar")
        assert r.json()["expiradas"] == []
        assert (await _reserva(rid)).estado == "PENDIENTE"
        # Cliente no puede ejecutar el job -> 403; anonimo -> 401.
        assert (await cli.client.post("/api/v1/reservas/expiracion/ejecutar")).status_code == 403


async def test_expira_con_adelanto_72h(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="e4s")
    await activar_adelanto(cliente_http, destino, "MONTO_FIJO", "20.00")
    var = await crear_variante_con_stock(cliente_http, destino, 3, tag="e4")
    async with await crear_cliente("e4") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, None)]))
        rid = resp.json()["id"]
        pago = await cli.client.post(
            "/api/v1/pagos/adelantos",
            json={"reserva_id": rid, "metodo": "EFECTIVO"},
            headers=cli.headers_clave(),
        )
        assert pago.status_code == 201
        await forzar_vencimiento(rid)
        r = await cliente_http.post("/api/v1/reservas/expiracion/ejecutar")
        assert rid in r.json()["expiradas"]
        # El adelanto no reembolsable permanece registrado.
        async with AsyncSessionLocal() as db:
            from backend.app.core.modules.ventas_pagos.models import Pago

            pagos = (
                await db.execute(
                    select(Pago).where(
                        Pago.contexto == "RESERVA",
                        Pago.reserva_id == uuid.UUID(rid),
                        Pago.tipo_pago == "ADELANTO",
                    )
                )
            ).scalars().all()
            assert len(pagos) == 1 and pagos[0].no_reembolsable is True


async def test_expira_libera_traslado_aprobado_en_origen(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    origen = await crear_sucursal(cliente_http, tag="e5")
    var = await crear_variante_con_stock(cliente_http, origen, 5, tag="e5a")
    async with await crear_cliente("e5") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, origen)]))
        rid, tid = resp.json()["id"], resp.json()["traslados"][0]["id"]
        enc = await crear_staff(cliente_http, "ENCARGADO", origen, tag="e5b")
        try:
            # Aprobar aun no existe (Entrega 3); simular viaje: vencer con SOLICITADO.
            await forzar_vencimiento(rid)
            r = await cliente_http.post("/api/v1/reservas/expiracion/ejecutar")
            assert rid in r.json()["expiradas"]
            assert (await _reserva(rid)).estado == "VENCIDA"
        finally:
            await enc.client.aclose()
