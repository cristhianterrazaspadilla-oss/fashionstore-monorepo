"""Pruebas exhaustivas para CU03, CU04, CU16 y CU18 bajo el contrato 0.3.2."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from backend.app.core.modules.catalogo.models import Color, ColorComponente, Promocion, PromocionVariante, VarianteProducto
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.reservas_traslados.models import Reserva

ZONA_BOLIVIA = ZoneInfo("America/La_Paz")


def ahora_bolivia() -> datetime:
    return datetime.now(ZONA_BOLIVIA)


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


# ==============================================================================
# CU03 — Descargar catálogo para consulta offline
# ==============================================================================
@pytest.mark.asyncio
async def test_cu03_descarga_catalogo_campos_ampliados_y_formato_bolivia(
    escenario, http, fabrica_sesiones
):
    """CU03: Verifica campos generados/descargados, sucursales con ciudad, colores compuestos y promociones."""
    # 1. Crear color compuesto y promoción en la base para empresa A
    async with fabrica_sesiones() as db:
        color_base1 = Color(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            nombre="Color Base Azul",
            codigo_hex="#0000FF",
            activo=True,
        )
        color_base2 = Color(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            nombre="Color Base Blanco",
            codigo_hex="#FFFFFF",
            activo=True,
        )
        color_comp = Color(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            nombre="Azul Marino Bicolor",
            codigo_hex="#000080",
            activo=True,
        )
        db.add_all([color_base1, color_base2, color_comp])
        await db.flush()

        comp1 = ColorComponente(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            color_id=color_comp.id,
            componente_id=color_base1.id,
            orden=1,
        )
        comp2 = ColorComponente(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            color_id=color_comp.id,
            componente_id=color_base2.id,
            orden=2,
        )
        db.add_all([comp1, comp2])

        # Crear promoción con cantidad mínima
        promo = Promocion(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            codigo=f"PROMO-{uuid.uuid4().hex[:6]}",
            nombre="Promoción Descuento Volumen",
            tipo="PORCENTAJE",
            valor=Decimal("15.00"),
            cantidad_minima=3,
            activa=True,
            vigencia_inicio=ahora_utc() - timedelta(days=1),
            vigencia_fin=ahora_utc() + timedelta(days=10),
        )
        db.add(promo)
        await db.flush()

        promo_var = PromocionVariante(
            promocion_id=promo.id,
            variante_id=escenario.variante_a_id,
        )
        db.add(promo_var)
        await db.commit()

    # 2. Descargar catálogo
    res = await http.cliente.get(
        "/api/v1/catalogo/descarga",
        params={"empresa_codigo": escenario.codigo_a},
    )
    assert res.status_code == 200, res.text
    data = res.json()

    # Verificar metadatos canónicos
    assert data["empresa_id"] == str(escenario.empresa_a_id)
    assert data["catalogo_version"] >= 1
    assert "generado_en" in data
    assert "descargado_en" in data
    assert len(data["ambito_sucursales"]) >= 1
    assert str(escenario.sucursal_a_id) in data["ambito_sucursales"]

    # Verificar sucursales con ciudad_nombre
    assert len(data["sucursales"]) >= 1
    suc_a = next(s for s in data["sucursales"] if s["id"] == str(escenario.sucursal_a_id))
    assert suc_a["nombre"] is not None
    assert "ciudad_nombre" in suc_a

    # Verificar colores compuestos
    col_found = next((c for c in data["colores"] if c["id"] == str(color_comp.id)), None)
    assert col_found is not None
    assert len(col_found["componentes"]) == 2
    assert col_found["componentes"][0]["color_id"] == str(color_base1.id)
    assert col_found["componentes"][0]["orden"] == 1
    assert col_found["componentes"][1]["color_id"] == str(color_base2.id)
    assert col_found["componentes"][1]["orden"] == 2

    # Verificar promociones con cantidad_minima
    prom_found = next((p for p in data["promociones"] if p["id"] == str(promo.id)), None)
    assert prom_found is not None
    assert prom_found["tipo"] == "PORCENTAJE"
    assert prom_found["valor"] == "15.00"
    assert prom_found["cantidad_minima"] == 3
    assert str(escenario.variante_a_id) in prom_found["variante_ids"]

    # Verificar variantes con disponibilidad_por_sucursal
    prod = next(p for p in data["productos"] if p["id"] == str(escenario.producto_a_id))
    var = next(v for v in prod["variantes"] if v["id"] == str(escenario.variante_a_id))
    assert var["disponibilidad"] == 5
    assert len(var["disponibilidad_por_sucursal"]) >= 1
    disp_item = next(
        d for d in var["disponibilidad_por_sucursal"] if d["sucursal_id"] == str(escenario.sucursal_a_id)
    )
    assert disp_item["disponible_conocido"] == 5
    assert "actualizado_en" in disp_item


# ==============================================================================
# CU04 — Referencias horarias y sincronización offline
# ==============================================================================
@pytest.mark.asyncio
async def test_cu04_referencias_horarias_post_validaciones_idempotencia_y_drift(
    escenario, http
):
    """CU04: POST /referencias-horarias valida offset Bolivia, drift 300s e idempotencia."""
    http.usar(escenario.usuario_a)
    dispositivo = str(uuid.uuid4())
    ahora_bo = ahora_bolivia()

    # 1. Sin Idempotency-Key -> 400 o 422
    res_sin_key = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        json={"dispositivo_id": dispositivo, "hora_local_en": ahora_bo.isoformat()},
    )
    assert res_sin_key.status_code in (400, 422)

    # 2. Datetime naive (sin timezone offset) -> 422
    naive_dt = datetime.now()
    res_naive = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"dispositivo_id": dispositivo, "hora_local_en": naive_dt.strftime("%Y-%m-%dT%H:%M:%S")},
    )
    assert res_naive.status_code == 422

    # 2b. Offset distinto a Bolivia (-04:00) -> 422
    res_utc = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"dispositivo_id": dispositivo, "hora_local_en": "2026-11-01T14:00:00Z"},
    )
    assert res_utc.status_code == 422

    res_plus2 = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"dispositivo_id": dispositivo, "hora_local_en": "2026-11-01T16:00:00+02:00"},
    )
    assert res_plus2.status_code == 422

    # 3. Drift temporal excesivo (> 300 s): 305 segundos adelantado -> 409 TIEMPO_INCOHERENTE
    adelantado = ahora_bo + timedelta(seconds=305)
    res_adelanto = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"dispositivo_id": dispositivo, "hora_local_en": adelantado.isoformat()},
    )
    assert res_adelanto.status_code == 409
    assert "TIEMPO_INCOHERENTE" in res_adelanto.text

    # 4. Drift temporal excesivo (> 300 s): 305 segundos atrasado -> 409 TIEMPO_INCOHERENTE
    atrasado = ahora_bo - timedelta(seconds=305)
    res_atraso = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"dispositivo_id": dispositivo, "hora_local_en": atrasado.isoformat()},
    )
    assert res_atraso.status_code == 409

    # 5. Emisión válida dentro de tolerancia (desfase normal ~0s)
    clave_idemp = str(uuid.uuid4())
    payload_valido = {"dispositivo_id": dispositivo, "hora_local_en": ahora_bo.isoformat()}
    res_valida = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": clave_idemp},
        json=payload_valido,
    )
    assert res_valida.status_code == 200, res_valida.text
    ref_data = res_valida.json()
    assert ref_data["empresa_id"] == str(escenario.empresa_a_id)
    assert ref_data["usuario_id"] == str(escenario.usuario_a.id)
    assert ref_data["dispositivo_id"] == dispositivo
    assert ref_data["tolerancia_segundos"] == 300
    assert ref_data["politica_version"] == 1
    assert ref_data["hora_central_en"].endswith("-04:00")
    assert ref_data["valida_hasta"].endswith("-04:00")

    # 6. Idempotencia: misma clave + mismo payload retorna HTTP 200 con la misma referencia
    res_repetida = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": clave_idemp},
        json=payload_valido,
    )
    assert res_repetida.status_code == 200
    assert res_repetida.json()["referencia_horaria_id"] == ref_data["referencia_horaria_id"]

    # 7. Conflicto de idempotencia: misma clave + payload distinto -> 409
    payload_distinto = {
        "dispositivo_id": str(uuid.uuid4()),
        "hora_local_en": ahora_bo.isoformat(),
    }
    res_conflicto = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": clave_idemp},
        json=payload_distinto,
    )
    assert res_conflicto.status_code == 409


@pytest.mark.asyncio
async def test_cu04_sincronizacion_offline_resolucion_referencia_y_limites(
    escenario, http, fabrica_sesiones
):
    """CU04: Sincronización offline con resolución de referencia previa y validación de 24h/visita."""
    http.usar(escenario.usuario_a)
    dispositivo = str(uuid.uuid4())
    ahora_bo = ahora_bolivia()

    # 1. Emitir referencia horaria válida
    res_ref = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"dispositivo_id": dispositivo, "hora_local_en": ahora_bo.isoformat()},
    )
    assert res_ref.status_code == 200
    ref_id = res_ref.json()["referencia_horaria_id"]

    # 2. Operación offline válida con referencia_horaria_id
    op_id = str(uuid.uuid4())
    creacion = ahora_bo + timedelta(minutes=5)
    visita = creacion + timedelta(hours=2)
    cuerpo_op = {
        "version_esquema": 1,
        "operacion_id": op_id,
        "tipo": "SOLICITAR_RESERVA",
        "creada_local_en": creacion.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": dispositivo,
        "secuencia_local": 1,
        "referencia_horaria_id": ref_id,
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "visita_en": visita.isoformat(),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    res_op = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=cuerpo_op)
    assert res_op.status_code == 200, res_op.text
    res_json = res_op.json()
    assert res_json["estado"] == "ACEPTADA"
    assert res_json["codigo"] == "OK"
    assert res_json["vence_en"] is not None
    assert res_json["vence_en"].endswith("-04:00")
    assert res_json["recibida_en"].endswith("-04:00")

    # 3. Operación offline que OMITE referencia_horaria_id: debe resolver la previa verificable
    op_id2 = str(uuid.uuid4())
    cuerpo_sin_ref = {
        **cuerpo_op,
        "operacion_id": op_id2,
        "secuencia_local": 2,
        "referencia_horaria_id": None,
    }
    res_op2 = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=cuerpo_sin_ref)
    assert res_op2.status_code == 200
    assert res_op2.json()["estado"] == "ACEPTADA"

    # 4. Operación offline con dispositivo ajeno sin referencia previa: CONFLICTO TIEMPO_INCOHERENTE
    dispositivo_desconocido = str(uuid.uuid4())
    op_id3 = str(uuid.uuid4())
    cuerpo_desconocido = {
        **cuerpo_op,
        "operacion_id": op_id3,
        "dispositivo_id": dispositivo_desconocido,
        "secuencia_local": 1,
        "referencia_horaria_id": None,
    }
    res_op3 = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=cuerpo_desconocido)
    assert res_op3.status_code == 200
    assert res_op3.json()["estado"] == "CONFLICTO"
    assert res_op3.json()["codigo"] == "TIEMPO_INCOHERENTE"

    # 5. Creación fuera de la ventana de la referencia (antes de emisión): CONFLICTO TIEMPO_INCOHERENTE
    op_id4 = str(uuid.uuid4())
    creacion_antes_ref = ahora_bo - timedelta(minutes=10)
    cuerpo_fuera_ventana = {
        **cuerpo_op,
        "operacion_id": op_id4,
        "creada_local_en": creacion_antes_ref.isoformat(),
        "secuencia_local": 3,
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "visita_en": (ahora_bo + timedelta(hours=2)).isoformat(),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    res_op4 = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=cuerpo_fuera_ventana)
    assert res_op4.status_code == 200
    assert res_op4.json()["estado"] == "CONFLICTO"
    assert res_op4.json()["codigo"] == "TIEMPO_INCOHERENTE"

    # 6. Operación creada hace 25 h (durante una referencia válida en su momento), sincronizada ahora:
    # recibida_en >= creada_local + 24 h -> durable RECHAZADA / SOLICITUD_VENCIDA
    from backend.app.core.modules.reservas_traslados.models import ReferenciaHoraria
    async with fabrica_sesiones() as db:
        ref_vieja = ReferenciaHoraria(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            dispositivo_id=uuid.UUID(dispositivo),
            emitida_en=ahora_utc() - timedelta(hours=26),
            hora_local_en=ahora_utc() - timedelta(hours=26),
            vence_en=ahora_utc() - timedelta(hours=18),
            tolerancia_segundos=300,
            politica_version=1,
            desfase_segundos=0,
            clave_idempotencia=uuid.uuid4(),
            hash_solicitud="test_hash_old",
        )
        db.add(ref_vieja)
        await db.commit()

    op_id5 = str(uuid.uuid4())
    creacion_vieja = ahora_bo - timedelta(hours=25)
    cuerpo_vencido = {
        **cuerpo_op,
        "operacion_id": op_id5,
        "creada_local_en": creacion_vieja.isoformat(),
        "referencia_horaria_id": str(ref_vieja.id),
        "secuencia_local": 4,
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "visita_en": (ahora_bo + timedelta(hours=2)).isoformat(),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    res_op5 = await http.cliente.post("/api/v1/sincronizacion/operaciones", json=cuerpo_vencido)
    assert res_op5.status_code == 200
    assert res_op5.json()["estado"] == "RECHAZADA"
    assert res_op5.json()["codigo"] == "SOLICITUD_VENCIDA"


# ==============================================================================
# CU16 — Consultar catálogo
# ==============================================================================
@pytest.mark.asyncio
async def test_cu16_consultar_catalogo_filtros_color_compuesto_precios_y_paginacion(
    escenario, http, fabrica_sesiones
):
    """CU16: Filtros modo_color EXACTO vs TODOS_COMPONENTES, precios BOB y paginado."""
    # 1. Crear producto con variante de color compuesto
    async with fabrica_sesiones() as db:
        c_rojo = Color(
            id=uuid.uuid4(), empresa_id=escenario.empresa_a_id, nombre=f"Rojo {uuid.uuid4().hex[:4]}", codigo_hex="#FF0000", activo=True
        )
        c_negro = Color(
            id=uuid.uuid4(), empresa_id=escenario.empresa_a_id, nombre=f"Negro {uuid.uuid4().hex[:4]}", codigo_hex="#000000", activo=True
        )
        c_bicolor = Color(
            id=uuid.uuid4(), empresa_id=escenario.empresa_a_id, nombre=f"Bicolor {uuid.uuid4().hex[:4]}", codigo_hex="#880000", activo=True
        )
        db.add_all([c_rojo, c_negro, c_bicolor])
        await db.flush()

        comp1 = ColorComponente(
            id=uuid.uuid4(), empresa_id=escenario.empresa_a_id, color_id=c_bicolor.id, componente_id=c_rojo.id, orden=1
        )
        comp2 = ColorComponente(
            id=uuid.uuid4(), empresa_id=escenario.empresa_a_id, color_id=c_bicolor.id, componente_id=c_negro.id, orden=2
        )
        db.add_all([comp1, comp2])

        # Variante de prueba con precio 150.00
        var_comp = VarianteProducto(
            id=uuid.uuid4(),
            empresa_id=escenario.empresa_a_id,
            producto_id=escenario.producto_a_id,
            talla_id=escenario.ids["talla"],
            color_id=c_bicolor.id,
            sku=f"SKU-BICOLOR-{uuid.uuid4().hex[:6]}",
            precio=Decimal("150.00"),
            costo_promedio=Decimal("50.00"),
            costo_ultimo=Decimal("50.00"),
            activa=True,
        )
        db.add(var_comp)
        await db.flush()

        inv = InventarioSucursal(
            id=uuid.uuid4(),
            sucursal_id=escenario.sucursal_a_id,
            variante_id=var_comp.id,
            disponible=10,
            reservado=0,
            comprometido_traslado=0,
            en_transito=0,
        )
        db.add(inv)
        await db.commit()

    # 2. Prueba paginado=True -> {total, limit, offset, items[]}
    res_pag = await http.cliente.get(
        "/api/v1/catalogo/productos",
        params={"empresa_codigo": escenario.codigo_a, "paginado": "true", "limit": 10, "offset": 0},
    )
    assert res_pag.status_code == 200
    pag_data = res_pag.json()
    assert "total" in pag_data
    assert "limit" in pag_data
    assert "offset" in pag_data
    assert "items" in pag_data
    assert isinstance(pag_data["items"], list)
    assert pag_data["total"] >= 1

    # 3. Prueba paginado=False -> lista items[] directa
    res_no_pag = await http.cliente.get(
        "/api/v1/catalogo/productos",
        params={"empresa_codigo": escenario.codigo_a, "paginado": "false"},
    )
    assert res_no_pag.status_code == 200
    assert isinstance(res_no_pag.json(), list)

    # 4. Filtro por modo_color=TODOS_COMPONENTES con ambos componentes [Rojo, Negro]
    res_comp_ok = await http.cliente.get(
        "/api/v1/catalogo/productos",
        params={
            "empresa_codigo": escenario.codigo_a,
            "modo_color": "TODOS_COMPONENTES",
            "componentes_color": [str(c_rojo.id), str(c_negro.id)],
            "paginado": "true",
        },
    )
    assert res_comp_ok.status_code == 200
    data_comp = res_comp_ok.json()
    assert data_comp["total"] >= 1
    # La variante debe tener el color bicolor
    var_ids = [v["id"] for p in data_comp["items"] for v in p["variantes"]]
    assert str(var_comp.id) in var_ids

    # 5. Filtro por modo_color=TODOS_COMPONENTES con componente no presente -> total 0
    color_ajeno = uuid.uuid4()
    res_comp_no = await http.cliente.get(
        "/api/v1/catalogo/productos",
        params={
            "empresa_codigo": escenario.codigo_a,
            "modo_color": "TODOS_COMPONENTES",
            "componentes_color": [str(c_rojo.id), str(color_ajeno)],
            "paginado": "true",
        },
    )
    assert res_comp_no.status_code == 200
    assert res_comp_no.json()["total"] == 0

    # 6. Filtro precio_min_bob y precio_max_bob
    res_precio = await http.cliente.get(
        "/api/v1/catalogo/productos",
        params={
            "empresa_codigo": escenario.codigo_a,
            "precio_min_bob": "140.00",
            "precio_max_bob": "160.00",
            "paginado": "true",
        },
    )
    assert res_precio.status_code == 200
    assert res_precio.json()["total"] >= 1


# ==============================================================================
# CU18 — Reservas online y cancelación con revisión
# ==============================================================================
@pytest.mark.asyncio
async def test_cu18_reservas_online_revision_fechas_bolivia_y_cancelacion(
    escenario, http, fabrica_sesiones
):
    """CU18: Creación con revision=1, fechas en Bolivia, y cancelación con control de revisión e idempotencia."""
    http.usar(escenario.usuario_a)
    clave_crear = str(uuid.uuid4())
    cuerpo = {
        "sucursal_destino_id": str(escenario.sucursal_a_id),
        "fecha_visita": (ahora_utc() + timedelta(hours=2)).isoformat(),
        "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
    }

    # 1. Crear reserva online
    res_crear = await http.cliente.post(
        "/api/v1/reservas", json=cuerpo, headers={"Idempotency-Key": clave_crear}
    )
    assert res_crear.status_code == 201, res_crear.text
    reserva = res_crear.json()
    reserva_id = reserva["id"]
    assert reserva["revision"] == 1
    assert reserva["fecha_creacion"].endswith("-04:00")
    assert reserva["vence_en"].endswith("-04:00")

    # 2. Consultar listado GET /reservas
    res_list = await http.cliente.get("/api/v1/reservas")
    assert res_list.status_code == 200
    lista = res_list.json()
    assert "total" in lista
    item = next(r for r in lista["items"] if r["id"] == reserva_id)
    assert item["revision"] == 1
    assert len(item["detalles"]) == 1
    linea = item["detalles"][0]
    assert linea["cantidad_solicitada"] == 1
    assert linea["cantidad_reservada"] == 1
    assert linea["estado_linea"] == "RESERVADA"

    # 3. Cancelar con revisión incorrecta (e.g. revision=99) -> 409 Conflict
    clave_canc = str(uuid.uuid4())
    res_bad_rev = await http.cliente.patch(
        f"/api/v1/reservas/{reserva_id}/cancelar",
        headers={"Idempotency-Key": clave_canc},
        json={"revision": 99},
    )
    assert res_bad_rev.status_code == 409
    assert "REVISION_OBSOLETA" in res_bad_rev.text or "Conflicto" in res_bad_rev.text

    # 4. Cancelar con revisión correcta (revision=1) -> 200 OK, revision se incrementa a 2
    res_canc = await http.cliente.patch(
        f"/api/v1/reservas/{reserva_id}/cancelar",
        headers={"Idempotency-Key": clave_canc},
        json={"revision": 1},
    )
    assert res_canc.status_code == 200, res_canc.text
    canc_data = res_canc.json()
    assert canc_data["estado"] == "CANCELADA"
    assert canc_data["revision"] == 2

    # Verificar que el Kardex registró LIBERACION_RESERVA
    async with fabrica_sesiones() as db:
        q_kardex = select(MovimientoInventario).where(
            MovimientoInventario.tipo == "LIBERACION_RESERVA",
            MovimientoInventario.referencia_id == uuid.UUID(reserva_id),
        )
        movs = list((await db.execute(q_kardex)).scalars().all())
        assert len(movs) >= 1

    # 5. Repetir cancelación (idempotente) -> 200 OK sin generar segundo Kardex
    res_canc_rep = await http.cliente.patch(
        f"/api/v1/reservas/{reserva_id}/cancelar",
        headers={"Idempotency-Key": clave_canc},
        json={"revision": 2},
    )
    assert res_canc_rep.status_code == 200
    assert res_canc_rep.json()["estado"] == "CANCELADA"

    # Verificar que no se duplicó el movimiento en Kardex
    async with fabrica_sesiones() as db:
        q_kardex = select(MovimientoInventario).where(
            MovimientoInventario.tipo == "LIBERACION_RESERVA",
            MovimientoInventario.referencia_id == uuid.UUID(reserva_id),
        )
        movs = list((await db.execute(q_kardex)).scalars().all())
        assert len(movs) == 1


@pytest.mark.asyncio
async def test_cu04_flutter_contrato_estricto_y_rechazo_campos_extra(
    escenario, http
):
    """Verifica que el backend rechace campos extra en datos (fecha_local, notas) y empresa_id no-UUID."""
    http.usar(escenario.usuario_a)
    dispositivo = str(uuid.uuid4())
    ahora_bo = ahora_bolivia()

    # 1. Emitir referencia válida
    res_ref = await http.cliente.post(
        "/api/v1/sincronizacion/referencias-horarias",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"dispositivo_id": dispositivo, "hora_local_en": ahora_bo.isoformat()},
    )
    assert res_ref.status_code == 200
    ref_id = res_ref.json()["referencia_horaria_id"]

    # 2. Flutter defectuoso envía empresa_id="fashionstore" (no-UUID) -> 422
    payload_err_empresa = {
        "version_esquema": 1,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_RESERVA",
        "creada_local_en": ahora_bo.isoformat(),
        "empresa_id": "fashionstore",
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": dispositivo,
        "secuencia_local": 1,
        "referencia_horaria_id": ref_id,
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "visita_en": (ahora_bo + timedelta(hours=3)).isoformat(),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    res_err_empresa = await http.cliente.post(
        "/api/v1/sincronizacion/operaciones",
        json=payload_err_empresa,
    )
    assert res_err_empresa.status_code == 422

    # 3. Flutter defectuoso envía fecha_local o notas dentro de datos -> 422 (extra fields forbidden)
    payload_err_datos = {
        "version_esquema": 1,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_RESERVA",
        "creada_local_en": ahora_bo.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": dispositivo,
        "secuencia_local": 2,
        "referencia_horaria_id": ref_id,
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "visita_en": (ahora_bo + timedelta(hours=3)).isoformat(),
            "fecha_local": ahora_bo.isoformat(),
            "notas": "Una nota de prueba",
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    res_err_datos = await http.cliente.post(
        "/api/v1/sincronizacion/operaciones",
        json=payload_err_datos,
    )
    assert res_err_datos.status_code == 422

    # 4. Flutter corregido: exactamente sucursal_id, visita_en, lineas y empresa_id UUID de la sesión -> 200 ACEPTADA
    momento_creacion_op = ahora_bolivia()
    payload_corregido = {
        "version_esquema": 1,
        "operacion_id": str(uuid.uuid4()),
        "tipo": "SOLICITAR_RESERVA",
        "creada_local_en": momento_creacion_op.isoformat(),
        "empresa_id": str(escenario.empresa_a_id),
        "usuario_id": str(escenario.usuario_a.id),
        "dispositivo_id": dispositivo,
        "secuencia_local": 3,
        "referencia_horaria_id": ref_id,
        "datos": {
            "sucursal_id": str(escenario.sucursal_a_id),
            "visita_en": (ahora_bo + timedelta(hours=3)).isoformat(),
            "lineas": [{"variante_id": str(escenario.variante_a_id), "cantidad": 1}],
        },
    }
    res_corregido = await http.cliente.post(
        "/api/v1/sincronizacion/operaciones",
        json=payload_corregido,
    )
    assert res_corregido.status_code == 200
    res_json = res_corregido.json()
    assert res_json["estado"] == "ACEPTADA"
    assert res_json["codigo"] == "OK"
    assert res_json["recurso_id"] is not None
