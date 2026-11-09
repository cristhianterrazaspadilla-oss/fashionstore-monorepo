import uuid
import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.catalogo.models import Categoria, Talla, Color, Producto, VarianteProducto
from backend.app.core.modules.inventario.models import InventarioSucursal, MovimientoInventario
from tests.helpers_ciclo2 import EMPRESA_TEST_ID, crear_ciudad_plataforma

async def _obtener_ciudad_sucursal(cliente_http):
    # Intentar usar sucursal existente, si no crear nueva
    resp_list = await cliente_http.get("/api/v1/sucursales")
    sucursales = resp_list.json()
    if sucursales:
        return sucursales[0]["id"]
    # crear ciudad + sucursal
    uid = uuid.uuid4().hex[:6]
    ciudad = await crear_ciudad_plataforma(f"Ciudad CU04 {uid}")
    ciudad_id = ciudad["id"]
    payload = {
        "ciudad_id": ciudad_id,
        "nombre": f"Sucursal CU04 {uid}",
        "direccion": "Av. test 123",
        "numero_anillo": 2,
        "tarifa_base_delivery": "10.00",
        "incremento_anillo_delivery": "2.00",
    }
    resp_suc = await cliente_http.post("/api/v1/sucursales", json=payload)
    assert resp_suc.status_code == 201
    return resp_suc.json()["id"]

async def _crear_usuario_receptor(cliente_http):
    # necesita sucursal existente
    resp_suc = await cliente_http.get("/api/v1/sucursales")
    suc_id = resp_suc.json()[0]["id"] if resp_suc.json() else None
    resp_roles = await cliente_http.get("/api/v1/roles")
    roles = resp_roles.json()
    rol = next((r for r in roles if r["nombre"] == "ENCARGADO"), roles[0])
    uid = uuid.uuid4().hex[:8]
    correo = f"recep.{uid}@fashionstore.com"
    payload = {
        "rol_id": rol["id"],
        "nombres": "Receptor",
        "apellidos": f"Test {uid}",
        "correo_electronico": correo,
        "contrasenia": "clave123456",
        "telefono": "+591 70000000",
        "sucursal_id": suc_id,
        "cargo": "Encargado de Sucursal"
    }
    resp = await cliente_http.post("/api/v1/usuarios", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]

async def _crear_producto_variante(sku_suffix: str):
    async with AsyncSessionLocal() as db:
        # Obtener maestros existentes
        res_cat = await db.execute(select(Categoria).limit(1))
        cat = res_cat.scalars().first()
        if not cat:
            cat = Categoria(empresa_id=EMPRESA_TEST_ID, nombre=f"Cat CU04 {sku_suffix}", activo=True)
            db.add(cat)
            await db.flush()
        res_talla = await db.execute(select(Talla).limit(1))
        talla = res_talla.scalars().first()
        res_color = await db.execute(select(Color).limit(1))
        color = res_color.scalars().first()
        # Crear producto
        producto = Producto(
            empresa_id=EMPRESA_TEST_ID,
            categoria_id=cat.id,
            nombre=f"Producto CU04 {sku_suffix}",
            descripcion="Producto de prueba CU04",
            genero="UNISEX",
            marca="FashionStore",
            precio_base=Decimal("100.00"),
            activo=True
        )
        db.add(producto)
        await db.flush()
        sku = f"SKU-CU04-{sku_suffix}-{uuid.uuid4().hex[:6].upper()}"
        variante = VarianteProducto(
            empresa_id=EMPRESA_TEST_ID,
            producto_id=producto.id,
            talla_id=talla.id,
            color_id=color.id,
            sku=sku,
            precio=Decimal("100.00"),
            costo_promedio=Decimal("0.00"),
            costo_ultimo=Decimal("0.00"),
            activa=True
        )
        db.add(variante)
        await db.commit()
        await db.refresh(variante)
        return variante.id, producto.id, sku

@pytest.mark.asyncio
async def test_crear_proveedor(cliente_http: AsyncClient):
    uid = uuid.uuid4().hex[:6]
    payload = {
        "razon_social": f"Textiles Andinos SRL {uid}",
        "nit": f"100100{uid}",
        "contacto": "Juan Perez",
        "telefono": "+591 70011122",
        "correo_electronico": f"contacto{uid}@textiles.com",
        "direccion": "Parque Industrial",
        "convenio": "Pago 30 días"
    }
    resp = await cliente_http.post("/api/v1/proveedores", json=payload)
    assert resp.status_code == 201, resp.text
    datos = resp.json()
    assert datos["razon_social"] == payload["razon_social"]
    assert datos["nit"] == payload["nit"]
    assert datos["activo"] is True
    proveedor_id = datos["id"]

    # Listar y verificar presencia
    resp_list = await cliente_http.get("/api/v1/proveedores")
    assert resp_list.status_code == 200
    lista = resp_list.json()
    assert any(p["id"] == proveedor_id for p in lista)

    # NIT duplicado -> 409
    resp_dup = await cliente_http.post("/api/v1/proveedores", json=payload)
    assert resp_dup.status_code == 409


@pytest.mark.asyncio
async def test_registrar_lote_simple_y_verificar_costos_inventario_kardex(cliente_http: AsyncClient):
    # Preparar maestros
    sucursal_id = await _obtener_ciudad_sucursal(cliente_http)
    receptor_id = await _crear_usuario_receptor(cliente_http)
    uid = uuid.uuid4().hex[:6]
    # Proveedor
    resp_prov = await cliente_http.post("/api/v1/proveedores", json={
        "razon_social": f"Prov Simple {uid}",
        "nit": f"200200{uid}",
        "contacto": "Contacto",
    })
    assert resp_prov.status_code == 201
    proveedor_id = resp_prov.json()["id"]

    variante_id, _, sku = await _crear_producto_variante(uid)

    payload_lote = {
        "proveedor_id": proveedor_id,
        "sucursal_id": sucursal_id,
        "recibido_por_id": receptor_id,
        "numero_documento": f"FAC-{uid}-001",
        "observacion": "Lote simple prueba",
        "detalles": [
            {"variante_id": str(variante_id), "cantidad": 10, "costo_unitario": "20.00"}
        ]
    }
    resp_lote = await cliente_http.post("/api/v1/recepciones", json=payload_lote)
    assert resp_lote.status_code == 201, resp_lote.text
    datos_lote = resp_lote.json()
    assert datos_lote["proveedor_id"] == proveedor_id
    assert datos_lote["sucursal_id"] == sucursal_id
    assert len(datos_lote["detalles"]) == 1
    assert datos_lote["detalles"][0]["cantidad"] == 10
    assert Decimal(datos_lote["detalles"][0]["costo_unitario"]) == Decimal("20.00")

    lote_id = datos_lote["id"]

    # Verificar GET /recepciones/{id}
    resp_get = await cliente_http.get(f"/api/v1/recepciones/{lote_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == lote_id

    # Verificar variante costos RN-09
    async with AsyncSessionLocal() as db:
        res_var = await db.execute(select(VarianteProducto).where(VarianteProducto.id == variante_id))
        variante = res_var.scalars().first()
        assert variante is not None
        assert Decimal(str(variante.costo_promedio)) == Decimal("20.00")
        assert Decimal(str(variante.costo_ultimo)) == Decimal("20.00")

        # Verificar inventario disponible =10
        res_inv = await db.execute(select(InventarioSucursal).where(
            InventarioSucursal.variante_id == variante_id,
            InventarioSucursal.sucursal_id == uuid.UUID(sucursal_id)
        ))
        inv = res_inv.scalars().first()
        assert inv is not None
        assert inv.disponible == 10
        assert inv.reservado == 0

        # Verificar Kardex RECEPCION_PROVEEDOR con costo
        res_mov = await db.execute(select(MovimientoInventario).where(
            MovimientoInventario.variante_id == variante_id,
            MovimientoInventario.tipo == "RECEPCION_PROVEEDOR",
            MovimientoInventario.referencia_id == uuid.UUID(lote_id)
        ))
        movs = list(res_mov.scalars().all())
        assert len(movs) == 1
        assert movs[0].cantidad == 10
        assert Decimal(str(movs[0].costo_unitario)) == Decimal("20.00")
        assert movs[0].sucursal_destino_id == uuid.UUID(sucursal_id)


@pytest.mark.asyncio
async def test_segundo_lote_promedio_ponderado(cliente_http: AsyncClient):
    """
    RN-09: existencia 10 costo 20 + recibir 10 costo 30 => promedio 25
    Verifica recálculo, costo_ultimo sobrescribe, inventario disponible y Kardex.
    """
    sucursal_id = await _obtener_ciudad_sucursal(cliente_http)
    receptor_id = await _crear_usuario_receptor(cliente_http)
    uid = uuid.uuid4().hex[:6]

    resp_prov = await cliente_http.post("/api/v1/proveedores", json={
        "razon_social": f"Prov Ponderado {uid}",
        "nit": f"300300{uid}"
    })
    assert resp_prov.status_code == 201
    proveedor_id = resp_prov.json()["id"]

    variante_id, _, _ = await _crear_producto_variante(uid + "P")

    # Primer lote: 10 x 20.00
    payload1 = {
        "proveedor_id": proveedor_id,
        "sucursal_id": sucursal_id,
        "recibido_por_id": receptor_id,
        "numero_documento": f"FAC-{uid}-A",
        "detalles": [{"variante_id": str(variante_id), "cantidad": 10, "costo_unitario": "20.00"}]
    }
    resp1 = await cliente_http.post("/api/v1/recepciones", json=payload1)
    assert resp1.status_code == 201, resp1.text
    lote1_id = resp1.json()["id"]

    async with AsyncSessionLocal() as db:
        res_var = await db.execute(select(VarianteProducto).where(VarianteProducto.id == variante_id))
        var1 = res_var.scalars().first()
        assert Decimal(str(var1.costo_promedio)) == Decimal("20.00")
        assert Decimal(str(var1.costo_ultimo)) == Decimal("20.00")

    # Segundo lote: 10 x 30.00 => promedio (10*20+10*30)/20 = 25.00
    payload2 = {
        "proveedor_id": proveedor_id,
        "sucursal_id": sucursal_id,
        "recibido_por_id": receptor_id,
        "numero_documento": f"FAC-{uid}-B",
        "detalles": [{"variante_id": str(variante_id), "cantidad": 10, "costo_unitario": "30.00"}]
    }
    resp2 = await cliente_http.post("/api/v1/recepciones", json=payload2)
    assert resp2.status_code == 201, resp2.text
    lote2_id = resp2.json()["id"]

    async with AsyncSessionLocal() as db:
        res_var = await db.execute(select(VarianteProducto).where(VarianteProducto.id == variante_id))
        var2 = res_var.scalars().first()
        assert Decimal(str(var2.costo_promedio)) == Decimal("25.00"), f"Promedio esperado 25.00, got {var2.costo_promedio}"
        assert Decimal(str(var2.costo_ultimo)) == Decimal("30.00")

        # Inventario total disponible debe ser 20 (10+10) en esa sucursal
        res_inv = await db.execute(select(InventarioSucursal).where(
            InventarioSucursal.variante_id == variante_id,
            InventarioSucursal.sucursal_id == uuid.UUID(sucursal_id)
        ))
        inv = res_inv.scalars().first()
        assert inv.disponible == 20, f"Disponible esperado 20, got {inv.disponible}"

        # Kardex: 2 movimientos RECEPCION_PROVEEDOR
        res_mov = await db.execute(select(MovimientoInventario).where(
            MovimientoInventario.variante_id == variante_id,
            MovimientoInventario.tipo == "RECEPCION_PROVEEDOR"
        ).order_by(MovimientoInventario.fecha_hora))
        movs = list(res_mov.scalars().all())
        assert len(movs) >= 2
        # Filtrar solo los de este test (por lote ids)
        mov_lote1 = [m for m in movs if str(m.referencia_id) == lote1_id]
        mov_lote2 = [m for m in movs if str(m.referencia_id) == lote2_id]
        assert len(mov_lote1) == 1 and Decimal(str(mov_lote1[0].costo_unitario)) == Decimal("20.00")
        assert len(mov_lote2) == 1 and Decimal(str(mov_lote2[0].costo_unitario)) == Decimal("30.00")

        # Validar existencia_total sigue siendo 20 (solo disponible en este caso)
        res_total = await db.execute(select(
            InventarioSucursal.disponible + InventarioSucursal.reservado + InventarioSucursal.comprometido_traslado + InventarioSucursal.en_transito
        ).where(InventarioSucursal.variante_id == variante_id))
        # Sum manually
        invs = await db.execute(select(InventarioSucursal).where(InventarioSucursal.variante_id == variante_id))
        total = sum(i.disponible + i.reservado + i.comprometido_traslado + i.en_transito for i in invs.scalars().all())
        assert total == 20


@pytest.mark.asyncio
async def test_validacion_cantidad_y_costo(cliente_http: AsyncClient):
    sucursal_id = await _obtener_ciudad_sucursal(cliente_http)
    receptor_id = await _crear_usuario_receptor(cliente_http)
    uid = uuid.uuid4().hex[:6]
    resp_prov = await cliente_http.post("/api/v1/proveedores", json={"razon_social": f"Prov Val {uid}", "nit": f"400400{uid}"})
    proveedor_id = resp_prov.json()["id"]
    variante_id, _, _ = await _crear_producto_variante(uid + "V")

    # cantidad 0 debe fallar 422
    payload_cero = {
        "proveedor_id": proveedor_id,
        "sucursal_id": sucursal_id,
        "recibido_por_id": receptor_id,
        "detalles": [{"variante_id": str(variante_id), "cantidad": 0, "costo_unitario": "10.00"}]
    }
    resp_cero = await cliente_http.post("/api/v1/recepciones", json=payload_cero)
    assert resp_cero.status_code == 422

    # costo negativo debe fallar 422
    payload_neg = {
        "proveedor_id": proveedor_id,
        "sucursal_id": sucursal_id,
        "recibido_por_id": receptor_id,
        "detalles": [{"variante_id": str(variante_id), "cantidad": 5, "costo_unitario": "-5.00"}]
    }
    resp_neg = await cliente_http.post("/api/v1/recepciones", json=payload_neg)
    assert resp_neg.status_code == 422

    # variante duplicada en mismo lote -> 400
    payload_dup = {
        "proveedor_id": proveedor_id,
        "sucursal_id": sucursal_id,
        "recibido_por_id": receptor_id,
        "detalles": [
            {"variante_id": str(variante_id), "cantidad": 2, "costo_unitario": "10.00"},
            {"variante_id": str(variante_id), "cantidad": 3, "costo_unitario": "12.00"},
        ]
    }
    resp_dup = await cliente_http.post("/api/v1/recepciones", json=payload_dup)
    assert resp_dup.status_code == 400
