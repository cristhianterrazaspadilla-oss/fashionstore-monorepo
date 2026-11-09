"""
Ciclo 2 Entrega 1 — Infraestructura transaccional (solo backend, sin endpoints).

Cubre el plan plan-implementacion-ciclo-2-backend.md / Entrega 1:
  - constraints no negativos y rollback completo inventario <-> Kardex
  - bloqueo pesimista SELECT FOR UPDATE con orden determinista
  - competencia por la ultima unidad: 1 confirmacion + 1 conflicto 409
  - idempotencia: misma clave + mismo payload -> original; distinto payload -> 409
  - unicidad Kardex por efecto logico (sin duplicados)
  - reloj UTC inyectable y vigencias 24 h / 72 h (RN-03)

No toca frontend ni Ciclo 3. Limpia todos sus datos de prueba.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import AsyncSessionLocal
from backend.app.core import reloj as reloj_mod
from backend.app.core.reloj import (
    RelojFijo,
    a_hora_bolivia,
    calcular_vencimiento,
    entrada_local_a_utc,
    vencida,
)
from backend.app.core.idempotencia import (
    hash_payload,
    resolver_idempotencia,
    validar_clave_idempotencia,
)
from backend.app.core.seguridad import generar_contrasenia_hash
from backend.app.core.modules.catalogo.models import (
    VarianteProducto,
    Producto,
    Talla,
    Color,
    Categoria,
    Proveedor,
)
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from backend.app.core.modules.organizacion.models import Sucursal
from backend.app.core.modules.reservas_traslados.models import Reserva
from backend.app.core.modules.identidad_empresas.models import Cliente, Rol, Usuario
from tests.helpers_ciclo2 import EMPRESA_TEST_ID
from backend.app.core.modules.inventario.repositories.inventario_repository import InventarioRepository
from backend.app.core.modules.inventario.repositories.movimiento_repository import MovimientoRepository

TIPO_PRUEBA = "PRUEBA_INFRA"


@pytest.fixture(scope="function")
async def base_infra():
    """Datos propios del modulo: variante + cliente scratch y sucursal semilla.

    Hace al archivo independiente del orden de ejecucion (corre primero
    alfabeticamente) y de datos acumulados de otras corridas. Limpia todo.
    """
    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            rol = (
                await db.execute(select(Rol).where(Rol.nombre == "CLIENTE"))
            ).scalars().one()
            sucursal = (await db.execute(select(Sucursal).limit(1))).scalars().one()
            talla = Talla(empresa_id=EMPRESA_TEST_ID, nombre=f"T-INFRA-{uid}", orden=99, activo=True)
            color = Color(empresa_id=EMPRESA_TEST_ID, nombre=f"Color Infra {uid}", codigo_hex="#123456", activo=True)
            categoria = Categoria(empresa_id=EMPRESA_TEST_ID, nombre=f"Cat Infra {uid}", activo=True)
            proveedor = Proveedor(empresa_id=EMPRESA_TEST_ID, razon_social=f"Prov Infra {uid}", nit=f"900900{uid[:6]}")
            db.add_all([talla, color, categoria, proveedor])
            await db.flush()
            producto = Producto(
                empresa_id=EMPRESA_TEST_ID,
                categoria_id=categoria.id,
                proveedor_principal_id=proveedor.id,
                nombre=f"Producto Infra {uid}",
                precio_base=Decimal("100.00"),
                activo=True,
            )
            db.add(producto)
            await db.flush()
            variante = VarianteProducto(
                empresa_id=EMPRESA_TEST_ID,
                producto_id=producto.id,
                talla_id=talla.id,
                color_id=color.id,
                sku=f"SKU-INFRA-{uid}",
                precio=Decimal("100.00"),
                activa=True,
            )
            db.add(variante)
            await db.flush()
            usuario = Usuario(
                empresa_id=EMPRESA_TEST_ID,
                rol_id=rol.id,
                nombres="Cliente",
                apellidos=f"Infra {uid}",
                correo_electronico=f"infra.{uid}@fashionstore.com",
                contrasenia_hash=generar_contrasenia_hash("infra123456"),
                estado="ACTIVO",
            )
            db.add(usuario)
            await db.flush()
            db.add(Cliente(usuario_id=usuario.id))
            await db.flush()
            datos = {
                "variante_id": variante.id,
                "producto_id": producto.id,
                "talla_id": talla.id,
                "color_id": color.id,
                "categoria_id": categoria.id,
                "proveedor_id": proveedor.id,
                "sucursal_id": sucursal.id,
                "cliente_id": usuario.id,
                "usuario_id": usuario.id,
            }
    yield datos
    async with AsyncSessionLocal() as db:
        async with db.begin():
            movs = (
                await db.execute(
                    select(MovimientoInventario).where(
                        MovimientoInventario.referencia_tipo == TIPO_PRUEBA
                    )
                )
            ).scalars().all()
            for m in movs:
                await db.delete(m)
            reservas = (
                await db.execute(
                    select(Reserva).where(Reserva.cliente_id == datos["cliente_id"])
                )
            ).scalars().all()
            for r in reservas:
                await db.delete(r)
            inv = (
                await db.execute(
                    select(InventarioSucursal).where(
                        InventarioSucursal.variante_id == datos["variante_id"]
                    )
                )
            ).scalars().all()
            for i in inv:
                await db.delete(i)
            for modelo, mid in (
                (VarianteProducto, datos["variante_id"]),
                (Producto, datos["producto_id"]),
                (Talla, datos["talla_id"]),
                (Color, datos["color_id"]),
                (Categoria, datos["categoria_id"]),
                (Proveedor, datos["proveedor_id"]),
                (Cliente, datos["cliente_id"]),
                (Usuario, datos["usuario_id"]),
            ):
                obj = await db.get(modelo, mid)
                if obj is not None:
                    await db.delete(obj)


async def _limpiar(variante_id, sucursal_id, referencia_ids):
    async with AsyncSessionLocal() as db:
        async with db.begin():
            movs = (
                await db.execute(
                    select(MovimientoInventario).where(
                        MovimientoInventario.referencia_tipo == TIPO_PRUEBA,
                        MovimientoInventario.referencia_id.in_(list(referencia_ids)),
                    )
                )
            ).scalars().all()
            for m in movs:
                await db.delete(m)
            inv = (
                await db.execute(
                    select(InventarioSucursal).where(
                        InventarioSucursal.variante_id == variante_id,
                        InventarioSucursal.sucursal_id == sucursal_id,
                    )
                )
            ).scalars().first()
            if inv is not None:
                await db.delete(inv)


def test_orden_bloqueo_determinista():
    """Orden (sucursal_id, variante_id) estable ante cualquier orden de entrada."""
    s1, s2 = uuid.uuid4(), uuid.uuid4()
    v1, v2 = uuid.uuid4(), uuid.uuid4()
    entrada = [(s2, v2), (s1, v2), (s2, v1), (s1, v1)]
    esperado = sorted(entrada, key=lambda c: (str(c[0]), str(c[1])))
    assert InventarioRepository.ordenarClavesBloqueo(entrada) == esperado
    assert InventarioRepository.ordenarClavesBloqueo(list(reversed(entrada))) == esperado


def test_reloj_vigencias_24_72():
    """RN-03: sin pago 24 h; con adelanto confirmado 72 h desde creada_en."""
    base = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    assert calcular_vencimiento(base, False) == base + timedelta(hours=24)
    assert calcular_vencimiento(base, True) == base + timedelta(hours=72)
    # El pago no mueve la base temporal ni acumula: misma creada_en, mismo vence_en.
    assert calcular_vencimiento(base, True) == calcular_vencimiento(base, True)
    reloj = RelojFijo(base)
    assert not vencida(base + timedelta(hours=24), reloj.ahora())
    reloj.avanzar(timedelta(hours=24))
    assert vencida(base + timedelta(hours=24), reloj.ahora())
    # Naive se asume UTC (prohibido utcnow, pero robusto ante legacy).
    assert calcular_vencimiento(base.replace(tzinfo=None), False).tzinfo is not None


def test_hash_payload_canonico():
    assert hash_payload({"b": 1, "a": 2}) == hash_payload({"a": 2, "b": 1})
    assert hash_payload({"a": 1}) != hash_payload({"a": 2})
    with pytest.raises(HTTPException) as exc:
        validar_clave_idempotencia(None)
    assert exc.value.status_code == 400
    clave = validar_clave_idempotencia(str(uuid.uuid4()))
    assert isinstance(clave, uuid.UUID)


async def test_check_inventario_no_negativo_y_rollback(base_infra):
    """CHECK >= 0: un disponible negativo falla y no deja efectos parciales."""
    variante_id, sucursal_id = base_infra["variante_id"], base_infra["sucursal_id"]
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                db.add(
                    InventarioSucursal(
                        variante_id=variante_id,
                        sucursal_id=sucursal_id,
                        disponible=5,
                        reservado=0,
                        comprometido_traslado=0,
                        en_transito=0,
                    )
                )
        async with AsyncSessionLocal() as db:
            with pytest.raises(IntegrityError):
                async with db.begin():
                    reg = (
                        await db.execute(
                            select(InventarioSucursal).where(
                                InventarioSucursal.variante_id == variante_id,
                                InventarioSucursal.sucursal_id == sucursal_id,
                            )
                        )
                    ).scalars().one()
                    reg.disponible = -1
        async with AsyncSessionLocal() as db:
            reg = (
                await db.execute(
                    select(InventarioSucursal).where(
                        InventarioSucursal.variante_id == variante_id,
                        InventarioSucursal.sucursal_id == sucursal_id,
                    )
                )
            ).scalars().one()
            assert reg.disponible == 5
    finally:
        await _limpiar(variante_id, sucursal_id, [])


async def test_rollback_completo_inventario_kardex(base_infra):
    """Un fallo entre inventario y Kardex revierte la transaccion completa."""
    variante_id, sucursal_id = base_infra["variante_id"], base_infra["sucursal_id"]
    ref_id = uuid.uuid4()
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                db.add(
                    InventarioSucursal(
                        variante_id=variante_id,
                        sucursal_id=sucursal_id,
                        disponible=3,
                        reservado=0,
                        comprometido_traslado=0,
                        en_transito=0,
                    )
                )
        with pytest.raises(RuntimeError, match="fallo simulado"):
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    repo = InventarioRepository(db)
                    await repo.moverDisponibleAReservado(variante_id, sucursal_id, 2)
                    db.add(
                        MovimientoInventario(
                            variante_id=variante_id,
                            sucursal_destino_id=sucursal_id,
                            tipo="RESERVA",
                            cantidad=2,
                            costo_unitario=Decimal("0"),
                            referencia_tipo=TIPO_PRUEBA,
                            referencia_id=ref_id,
                        )
                    )
                    await db.flush()
                    raise RuntimeError("fallo simulado entre inventario y Kardex")
        async with AsyncSessionLocal() as db:
            reg = (
                await db.execute(
                    select(InventarioSucursal).where(
                        InventarioSucursal.variante_id == variante_id,
                        InventarioSucursal.sucursal_id == sucursal_id,
                    )
                )
            ).scalars().one()
            assert (reg.disponible, reg.reservado) == (3, 0)
            movs = (
                await db.execute(
                    select(MovimientoInventario).where(
                        MovimientoInventario.referencia_tipo == TIPO_PRUEBA,
                        MovimientoInventario.referencia_id == ref_id,
                    )
                )
            ).scalars().all()
            assert movs == []
    finally:
        await _limpiar(variante_id, sucursal_id, [ref_id])


async def test_concurrencia_ultima_unidad(base_infra):
    """Dos solicitudes por la ultima unidad: una confirma, la otra recibe 409.

    Solo existe un efecto de reserva y un movimiento Kardex.
    """
    import asyncio

    variante_id, sucursal_id = base_infra["variante_id"], base_infra["sucursal_id"]
    ref_id = uuid.uuid4()
    resultados = {}

    async def intento(indice: int):
        async with AsyncSessionLocal() as db:
            try:
                async with db.begin():
                    repo = InventarioRepository(db)
                    filas = await repo.bloquearFilas([(sucursal_id, variante_id)])
                    reg = filas[(sucursal_id, variante_id)]
                    # Revalidacion despues del bloqueo (serializa al segundo).
                    if reg is None or reg.disponible < 1:
                        raise HTTPException(status_code=409, detail="Stock insuficiente")
                    reg.disponible -= 1
                    reg.reservado += 1
                    await db.flush()
                    mov_repo = MovimientoRepository(db)
                    mov, _ = await mov_repo.registrarUnico(
                        MovimientoInventario(
                            variante_id=variante_id,
                            sucursal_destino_id=sucursal_id,
                            tipo="RESERVA",
                            cantidad=1,
                            costo_unitario=Decimal("0"),
                            referencia_tipo=TIPO_PRUEBA,
                            referencia_id=ref_id,
                        )
                    )
                resultados[indice] = "ok"
            except HTTPException as e:
                resultados[indice] = e.status_code

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                db.add(
                    InventarioSucursal(
                        variante_id=variante_id,
                        sucursal_id=sucursal_id,
                        disponible=1,
                        reservado=0,
                        comprometido_traslado=0,
                        en_transito=0,
                    )
                )
        await asyncio.gather(intento(0), intento(1))
        assert sorted(str(v) for v in resultados.values()) == ["409", "ok"]
        async with AsyncSessionLocal() as db:
            reg = (
                await db.execute(
                    select(InventarioSucursal).where(
                        InventarioSucursal.variante_id == variante_id,
                        InventarioSucursal.sucursal_id == sucursal_id,
                    )
                )
            ).scalars().one()
            assert (reg.disponible, reg.reservado) == (0, 1)
            total = (
                await db.execute(
                    select(MovimientoInventario).where(
                        MovimientoInventario.referencia_tipo == TIPO_PRUEBA,
                        MovimientoInventario.referencia_id == ref_id,
                    )
                )
            ).scalars().all()
            assert len(total) == 1
    finally:
        await _limpiar(variante_id, sucursal_id, [ref_id])


async def test_kardex_unico_por_efecto_e_idempotente(base_infra):
    """Repetir el mismo efecto no duplica Kardex; otra linea si crea uno nuevo."""
    variante_id, sucursal_id = base_infra["variante_id"], base_infra["sucursal_id"]
    ref_id = uuid.uuid4()
    linea_a, linea_b = uuid.uuid4(), uuid.uuid4()
    try:
        async with AsyncSessionLocal() as db:
            repo = MovimientoRepository(db)
            async with db.begin():
                primero, creado1 = await repo.registrarUnico(
                    MovimientoInventario(
                        variante_id=variante_id,
                        sucursal_destino_id=sucursal_id,
                        tipo="RESERVA",
                        cantidad=1,
                        costo_unitario=Decimal("10.50"),
                        referencia_tipo=TIPO_PRUEBA,
                        referencia_id=ref_id,
                        linea_referencia_id=linea_a,
                    )
                )
                assert creado1 is True
                repetido, creado2 = await repo.registrarUnico(
                    MovimientoInventario(
                        variante_id=variante_id,
                        sucursal_destino_id=sucursal_id,
                        tipo="RESERVA",
                        cantidad=1,
                        costo_unitario=Decimal("10.50"),
                        referencia_tipo=TIPO_PRUEBA,
                        referencia_id=ref_id,
                        linea_referencia_id=linea_a,
                    )
                )
                assert creado2 is False
                assert repetido.id == primero.id
                otra_linea, creado3 = await repo.registrarUnico(
                    MovimientoInventario(
                        variante_id=variante_id,
                        sucursal_destino_id=sucursal_id,
                        tipo="RESERVA",
                        cantidad=1,
                        costo_unitario=Decimal("10.50"),
                        referencia_tipo=TIPO_PRUEBA,
                        referencia_id=ref_id,
                        linea_referencia_id=linea_b,
                    )
                )
                assert creado3 is True
        async with AsyncSessionLocal() as db:
            total = (
                await db.execute(
                    select(MovimientoInventario).where(
                        MovimientoInventario.referencia_tipo == TIPO_PRUEBA,
                        MovimientoInventario.referencia_id == ref_id,
                    )
                )
            ).scalars().all()
            assert len(total) == 2
    finally:
        await _limpiar(variante_id, sucursal_id, [ref_id])


async def test_idempotencia_clave_mismo_y_distinto_payload(base_infra):
    """Misma clave + mismo hash -> original; misma clave + otro hash -> 409."""
    cliente_id = base_infra["cliente_id"]
    sucursal_id = base_infra["sucursal_id"]
    clave = uuid.uuid4()
    payload = {"cliente_id": str(cliente_id), "items": [{"sku": "X", "cantidad": 1}]}
    h1 = hash_payload(payload)
    h2 = hash_payload({"cliente_id": str(cliente_id), "items": [{"sku": "X", "cantidad": 2}]})
    reserva_id = None
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                assert await resolver_idempotencia(db, Reserva, clave, h1) is None
                reserva = Reserva(
                    empresa_id=EMPRESA_TEST_ID,
                    cliente_id=cliente_id,
                    sucursal_destino_id=sucursal_id,
                    codigo=f"FS-{uuid.uuid4().hex[:6].upper()}",
                    estado="PENDIENTE",
                    fecha_creacion=datetime.now(timezone.utc),
                    vence_en=datetime.now(timezone.utc) + timedelta(hours=24),
                    clave_idempotencia=clave,
                    hash_solicitud=h1,
                )
                db.add(reserva)
                await db.flush()
                reserva_id = reserva.id
        async with AsyncSessionLocal() as db:
            original = await resolver_idempotencia(db, Reserva, clave, h1)
            assert original is not None and original.id == reserva_id
            with pytest.raises(HTTPException) as exc:
                await resolver_idempotencia(db, Reserva, clave, h2)
            assert exc.value.status_code == 409
    finally:
        if reserva_id is not None:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    obj = await db.get(Reserva, reserva_id)
                    if obj is not None:
                        await db.delete(obj)


async def test_liberar_sin_reservado_responde_409_sin_efectos(base_infra):
    """Liberar mas de lo reservado -> 409 y cantidades intactas."""
    variante_id, sucursal_id = base_infra["variante_id"], base_infra["sucursal_id"]
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                db.add(
                    InventarioSucursal(
                        variante_id=variante_id,
                        sucursal_id=sucursal_id,
                        disponible=4,
                        reservado=1,
                        comprometido_traslado=0,
                        en_transito=0,
                    )
                )
        async with AsyncSessionLocal() as db:
            repo = InventarioRepository(db)
            with pytest.raises(HTTPException) as exc:
                async with db.begin():
                    await repo.liberarReservado(variante_id, sucursal_id, 2)
            assert exc.value.status_code == 409
        async with AsyncSessionLocal() as db:
            reg = (
                await db.execute(
                    select(InventarioSucursal).where(
                        InventarioSucursal.variante_id == variante_id,
                        InventarioSucursal.sucursal_id == sucursal_id,
                    )
                )
            ).scalars().one()
            assert (reg.disponible, reg.reservado) == (4, 1)
    finally:
        await _limpiar(variante_id, sucursal_id, [])


async def test_sucursal_adelanto_coherente():
    """Politica de adelanto: activa exige modalidad y valor; porcentaje <= 100."""
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        sucursal = (await db.execute(select(Sucursal).limit(1))).scalars().first()
        sucursal_id = sucursal.id if sucursal else None
        estado_original = (
            sucursal.adelanto_activo,
            sucursal.modalidad_adelanto,
            sucursal.valor_adelanto,
        ) if sucursal else None
    assert sucursal_id is not None
    async with AsyncSessionLocal() as db:
        with pytest.raises(IntegrityError):
            async with db.begin():
                await db.execute(
                    text(
                        "UPDATE organizacion.sucursales SET adelanto_activo = TRUE, "
                        "modalidad_adelanto = 'PORCENTAJE', valor_adelanto = 150 "
                        "WHERE id = :sid"
                    ),
                    {"sid": str(sucursal_id)},
                )
    async with AsyncSessionLocal() as db:
        fila = (
            await db.execute(
                select(Sucursal).where(Sucursal.id == sucursal_id),
            )
        ).scalars().one()
        assert (
            fila.adelanto_activo,
            fila.modalidad_adelanto,
            fila.valor_adelanto,
        ) == estado_original


def test_fecha_sin_offset_se_interpreta_como_hora_boliviana():
    local = datetime(2026, 9, 19, 14, 30, 0)
    utc = entrada_local_a_utc(local)
    assert utc == datetime(2026, 9, 19, 18, 30, 0, tzinfo=timezone.utc)


def test_fecha_con_offset_respeta_el_instante_y_presenta_bolivia():
    instante = datetime(2026, 9, 19, 18, 30, 0, tzinfo=timezone.utc)
    local = a_hora_bolivia(instante)
    assert local.isoformat() == "2026-09-19T14:30:00-04:00"
    assert entrada_local_a_utc(local) == instante


async def test_sesion_postgresql_usa_zona_horaria_boliviana():
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        zona = (await db.execute(text("SHOW TIME ZONE"))).scalar_one()
    assert zona == "America/La_Paz"
