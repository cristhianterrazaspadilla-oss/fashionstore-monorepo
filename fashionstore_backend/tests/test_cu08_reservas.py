"""CU08 — Crear, consultar y cancelar reserva local (RF09-RF12) + adelanto RN-03.

Contratos: ReservaService.crear()/cancelar()/obtener(),
PagoService.registrarAdelanto(); 201/200/400/401/403/404/409.
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.reservas_traslados.models import Reserva
from backend.app.core.modules.ventas_pagos.models import Pago
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


async def _stock(variante_id, sucursal_id):
    async with AsyncSessionLocal() as db:
        reg = (
            await db.execute(
                select(InventarioSucursal).where(
                    InventarioSucursal.variante_id == uuid.UUID(variante_id),
                    InventarioSucursal.sucursal_id == uuid.UUID(sucursal_id),
                )
            )
        ).scalars().first()
        return reg


async def _kardex_total(referencia_id):
    async with AsyncSessionLocal() as db:
        return int(
            (
                await db.execute(
                    select(func.count()).select_from(MovimientoInventario).where(
                        MovimientoInventario.referencia_id == uuid.UUID(referencia_id)
                    )
                )
            ).scalar()
            or 0
        )


async def test_crear_reserva_local_ok(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, destino, 5, tag="r1")
    async with await crear_cliente("r1") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, None)]))
        assert resp.status_code == 201, resp.text
        datos = resp.json()
        assert datos["codigo"].startswith("FS-") and len(datos["codigo"]) == 9
        assert datos["estado"] == "PENDIENTE"
        assert datos["detalles"][0]["estado_linea"] == "RESERVADA"
        assert datos["detalles"][0]["cantidad_reservada"] == 2
        vence = datetime.fromisoformat(datos["vence_en"])
        delta = (vence - datetime.now(timezone.utc)).total_seconds() / 3600
        assert 23 < delta < 25
        reg = await _stock(var["variante_id"], destino)
        assert (reg.disponible, reg.reservado) == (3, 2)
        assert await _kardex_total(datos["id"]) == 1


async def test_crear_multiitem_invalida_sin_efectos(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    var_ok = await crear_variante_con_stock(cliente_http, destino, 5, tag="r2a")
    var_sin = await crear_variante_con_stock(cliente_http, destino, 0, tag="r2b")
    async with await crear_cliente("r2") as cli:
        clave = str(uuid.uuid4())
        resp = await post_reserva(
            cli, bolsa(destino, [(var_ok["variante_id"], 2, None), (var_sin["variante_id"], 1, None)]), clave
        )
        assert resp.status_code == 409, resp.text
        # Atomicidad: nada persistido (ni reserva, ni stock movido, ni kardex).
        async with AsyncSessionLocal() as db:
            n = await db.execute(
                select(func.count()).select_from(Reserva).where(Reserva.clave_idempotencia == uuid.UUID(clave))
            )
            assert n.scalar() == 0
        reg = await _stock(var_ok["variante_id"], destino)
        assert (reg.disponible, reg.reservado) == (5, 0)
        movs = await _kardex_total(str(uuid.uuid4()))
        assert movs == 0


async def test_crear_mixta_local_y_traslado(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    origen = await crear_sucursal(cliente_http, tag="r3")
    var_local = await crear_variante_con_stock(cliente_http, destino, 4, tag="r3a")
    var_lejana = await crear_variante_con_stock(cliente_http, origen, 3, tag="r3b")
    async with await crear_cliente("r3") as cli:
        resp = await post_reserva(
            cli,
            bolsa(destino, [(var_local["variante_id"], 1, None), (var_lejana["variante_id"], 2, origen)]),
        )
        assert resp.status_code == 201, resp.text
        datos = resp.json()
        assert datos["estado"] == "PENDIENTE_TRASLADO"
        estados = {d["variante_id"]: d["estado_linea"] for d in datos["detalles"]}
        assert estados[var_local["variante_id"]] == "RESERVADA"
        assert estados[var_lejana["variante_id"]] == "PENDIENTE_TRASLADO"
        assert len(datos["traslados"]) == 1
        assert datos["traslados"][0]["estado"] == "SOLICITADO"
        # Sin movimiento de stock en origen hasta aprobar.
        reg_origen = await _stock(var_lejana["variante_id"], origen)
        assert (reg_origen.disponible, reg_origen.comprometido_traslado) == (3, 0)


async def test_crear_origen_sin_stock_409(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    origen = await crear_sucursal(cliente_http, tag="r4")
    var = await crear_variante_con_stock(cliente_http, origen, 1, tag="r4a")
    async with await crear_cliente("r4") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, origen)]))
        assert resp.status_code == 409, resp.text


async def test_crear_idempotencia_misma_y_distinta_clave(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, destino, 5, tag="r5")
    async with await crear_cliente("r5") as cli:
        carga = bolsa(destino, [(var["variante_id"], 1, None)])
        clave = str(uuid.uuid4())
        r1 = await post_reserva(cli, carga, clave)
        assert r1.status_code == 201, r1.text
        r2 = await post_reserva(cli, carga, clave)
        assert r2.status_code in (200, 201), r2.text
        assert r2.json()["id"] == r1.json()["id"]
        reg = await _stock(var["variante_id"], destino)
        assert (reg.disponible, reg.reservado) == (4, 1)
        assert await _kardex_total(r1.json()["id"]) == 1
        otra = bolsa(destino, [(var["variante_id"], 2, None)])
        r3 = await post_reserva(cli, otra, clave)
        assert r3.status_code == 409, r3.text


async def test_concurrencia_http_ultima_unidad(cliente_http: AsyncClient):
    import asyncio

    destino = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, destino, 1, tag="r6")
    async with await crear_cliente("r6a") as cli_a, await crear_cliente("r6b") as cli_b:
        carga_a = bolsa(destino, [(var["variante_id"], 1, None)])
        carga_b = bolsa(destino, [(var["variante_id"], 1, None)])
        ra, rb = await asyncio.gather(
            post_reserva(cli_a, carga_a), post_reserva(cli_b, carga_b)
        )
        codigos = sorted([ra.status_code, rb.status_code])
        assert codigos == [201, 409], (ra.text, rb.text)
        reg = await _stock(var["variante_id"], destino)
        assert (reg.disponible, reg.reservado) == (0, 1)


async def test_consulta_permisos(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, destino, 3, tag="r7")
    async with await crear_cliente("r7a") as duenio, await crear_cliente("r7b") as otro:
        resp = await post_reserva(duenio, bolsa(destino, [(var["variante_id"], 1, None)]))
        rid, codigo = resp.json()["id"], resp.json()["codigo"]
        assert (await duenio.client.get(f"/api/v1/reservas/{rid}")).status_code == 200
        assert (await duenio.client.get(f"/api/v1/reservas/codigo/{codigo}")).status_code == 200
        assert (await otro.client.get(f"/api/v1/reservas/{rid}")).status_code == 403
        assert (await otro.client.get(f"/api/v1/reservas/codigo/{codigo}")).status_code == 403
        # Sin sesion -> 401.
        from tests.helpers_ciclo2 import _nuevo_client

        anon = await _nuevo_client()
        try:
            assert (await anon.get(f"/api/v1/reservas/{rid}")).status_code == 401
        finally:
            await anon.aclose()
        # Inexistente -> 404.
        assert (await duenio.client.get(f"/api/v1/reservas/{uuid.uuid4()}")).status_code == 404
        # Personal de la sucursal puede localizar por codigo.
        cajero = await crear_staff(cliente_http, "CAJERO", destino, tag="r7c")
        try:
            r = await cajero.client.get(f"/api/v1/reservas/codigo/{codigo}")
            assert r.status_code == 200, r.text
        finally:
            await cajero.client.aclose()
        # Listado del cliente solo trae las propias.
        lista = await duenio.client.get("/api/v1/reservas")
        assert lista.status_code == 200
        assert all(i["cliente_id"] == duenio.id for i in lista.json()["items"])
        assert any(i["id"] == rid for i in lista.json()["items"])
        # Otro cliente no puede forzar cliente_id ajeno.
        assert (await otro.client.get("/api/v1/reservas", params={"cliente_id": duenio.id})).status_code == 403


async def test_cancelar_pendiente_y_repetida(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    var = await crear_variante_con_stock(cliente_http, destino, 4, tag="r8")
    async with await crear_cliente("r8") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 3, None)]))
        rid = resp.json()["id"]
        r1 = await cli.client.patch(f"/api/v1/reservas/{rid}/cancelar")
        assert r1.status_code == 200, r1.text
        assert r1.json()["estado"] == "CANCELADA"
        reg = await _stock(var["variante_id"], destino)
        assert (reg.disponible, reg.reservado) == (4, 0)
        assert await _kardex_total(rid) == 2  # RESERVA + LIBERACION_RESERVA
        # Repetir es idempotente: mismo estado, sin mas movimientos.
        r2 = await cli.client.patch(f"/api/v1/reservas/{rid}/cancelar")
        assert r2.status_code == 200
        assert r2.json()["estado"] == "CANCELADA"
        assert await _kardex_total(rid) == 2


async def test_cancelar_con_traslado_solicitado(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    origen = await crear_sucursal(cliente_http, tag="r9")
    var = await crear_variante_con_stock(cliente_http, origen, 2, tag="r9a")
    async with await crear_cliente("r9") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, origen)]))
        assert resp.status_code == 201
        rid = resp.json()["id"]
        tid = resp.json()["traslados"][0]["id"]
        r = await cli.client.patch(f"/api/v1/reservas/{rid}/cancelar")
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "CANCELADA"
        assert r.json()["traslados"][0]["estado"] == "CANCELADO"


async def test_cancelar_permisos(cliente_http: AsyncClient):
    destino = await sucursal_semilla(cliente_http)
    otra = await crear_sucursal(cliente_http, tag="r10")
    var = await crear_variante_con_stock(cliente_http, destino, 3, tag="r10a")
    async with await crear_cliente("r10") as duenio, await crear_cliente("r10b") as ajeno:
        resp = await post_reserva(duenio, bolsa(destino, [(var["variante_id"], 1, None)]))
        rid = resp.json()["id"]
        assert (await ajeno.client.patch(f"/api/v1/reservas/{rid}/cancelar")).status_code == 403
        enc_otra = await crear_staff(cliente_http, "ENCARGADO", otra, tag="r10c")
        try:
            assert (await enc_otra.client.patch(f"/api/v1/reservas/{rid}/cancelar")).status_code == 403
        finally:
            await enc_otra.client.aclose()
        enc = await crear_staff(cliente_http, "ENCARGADO", destino, tag="r10d")
        try:
            r = await enc.client.patch(f"/api/v1/reservas/{rid}/cancelar")
            assert r.status_code == 200, r.text
        finally:
            await enc.client.aclose()


async def test_adelanto_monto_fijo_extiende_72h(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="r11s")
    await activar_adelanto(cliente_http, destino, "MONTO_FIJO", "50.00")
    var = await crear_variante_con_stock(cliente_http, destino, 3, tag="r11")
    async with await crear_cliente("r11") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 1, None)]))
        rid = resp.json()["id"]
        r = await cli.client.post(
            "/api/v1/pagos/adelantos",
            json={"reserva_id": rid, "metodo": "EFECTIVO"},
            headers=cli.headers_clave(),
        )
        assert r.status_code == 201, r.text
        pago = r.json()
        assert pago["contexto"] == "RESERVA" and pago["tipo_pago"] == "ADELANTO"
        assert pago["no_reembolsable"] is True and pago["estado"] == "APROBADO"
        assert pago["monto"] == "50.00"
        reserva = (await cli.client.get(f"/api/v1/reservas/{rid}")).json()
        assert reserva["adelanto_monto"] == "50.00"
        assert reserva["adelanto_modalidad"] == "MONTO_FIJO"
        vence = datetime.fromisoformat(reserva["vence_en"])
        creada = datetime.fromisoformat(reserva["fecha_creacion"])
        assert abs((vence - creada).total_seconds() / 3600 - 72) < 0.05
        # Segundo adelanto -> 409 (no acumula).
        r2 = await cli.client.post(
            "/api/v1/pagos/adelantos",
            json={"reserva_id": rid, "metodo": "EFECTIVO"},
            headers=cli.headers_clave(),
        )
        assert r2.status_code == 409, r2.text
        # Idempotencia: misma clave + mismo payload -> original.
        clave = str(uuid.uuid4())
        a1 = await cli.client.post(
            "/api/v1/pagos/adelantos",
            json={"reserva_id": rid, "metodo": "TRANSFERENCIA"},
            headers=cli.headers_clave(clave),
        )
        assert a1.status_code == 409  # ya existe adelanto con otra clave


async def test_adelanto_porcentaje_y_sin_politica(cliente_http: AsyncClient):
    destino = await crear_sucursal(cliente_http, tag="r12s")
    var = await crear_variante_con_stock(cliente_http, destino, 2, tag="r12", precio="200.00")
    async with await crear_cliente("r12") as cli:
        resp = await post_reserva(cli, bolsa(destino, [(var["variante_id"], 2, None)]))
        rid = resp.json()["id"]
        # Sin politica activa -> 409.
        r = await cli.client.post(
            "/api/v1/pagos/adelantos",
            json={"reserva_id": rid, "metodo": "EFECTIVO"},
            headers=cli.headers_clave(),
        )
        assert r.status_code == 409, r.text
        await activar_adelanto(cliente_http, destino, "PORCENTAJE", "10.00")
        r = await cli.client.post(
            "/api/v1/pagos/adelantos",
            json={"reserva_id": rid, "metodo": "QR_CAJA"},
            headers=cli.headers_clave(),
        )
        assert r.status_code == 201, r.text
        assert r.json()["monto"] == "40.00"  # 10% de 2x200
        assert r.json()["modalidad_adelanto"] == "PORCENTAJE"
