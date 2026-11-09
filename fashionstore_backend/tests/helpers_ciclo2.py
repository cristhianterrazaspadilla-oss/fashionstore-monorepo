"""Ayudas compartidas para las pruebas HTTP del Ciclo 2 (entregas 2-7).

Crea usuarios, sucursales, variantes con stock y reservas con nombres unicos
por corrida. No reutiliza datos entre pruebas salvo la sucursal semilla.
"""
import os
import uuid
from decimal import Decimal

import app  # noqa: F401  alias backend.*
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from backend.app.main import app as aplicacion
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.catalogo.models import Categoria, Color, Producto, Talla, VarianteProducto

EMPRESA_TEST_ID = uuid.UUID("0ddf24a9-edeb-510f-b8e2-22d41847f477")


def _uid(n: int = 6) -> str:
    return uuid.uuid4().hex[:n]


class UsuarioPrueba:
    """Cliente HTTP propio con token. Usar como `async with await crear_...()`."""

    def __init__(self, client: AsyncClient, token: str, usuario_id: str, email: str, rol: str):
        self.client = client
        self.token = token
        self.id = usuario_id
        self.email = email
        self.rol = rol

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    def headers_clave(self, clave=None):
        return {"Idempotency-Key": clave or str(uuid.uuid4())}


async def _nuevo_client(token=None) -> AsyncClient:
    transport = ASGITransport(app=aplicacion)
    client = AsyncClient(transport=transport, base_url="http://test")
    if token:
        client.headers["Authorization"] = f"Bearer {token}"
    return client


async def _login(email: str, contrasenia: str):
    client = await _nuevo_client()
    try:
        resp = await client.post(
            "/api/v1/sesion",
            json={"correo_electronico": email, "contrasenia": contrasenia},
        )
        assert resp.status_code == 200, resp.text
        datos = resp.json()
        return datos["access_token"], datos["usuario"]["usuario_id"]
    finally:
        await client.aclose()


async def crear_cliente(tag: str = "c2") -> UsuarioPrueba:
    uid = _uid()
    email = f"cli.{tag}.{uid}@fashionstore.com"
    clave = "clave123456"
    anon = await _nuevo_client()
    try:
        resp = await anon.post(
            "/api/v1/clientes",
            json={
                "empresa_codigo": "fashionstore",
                "nombres": f"Cliente {tag}",
                "apellidos": f"Prueba {uid}",
                "correo_electronico": email,
                "contrasenia": clave,
            },
        )
        assert resp.status_code == 201, resp.text
    finally:
        await anon.aclose()
    token, usuario_id = await _login(email, clave)
    return UsuarioPrueba(await _nuevo_client(token), token, usuario_id, email, "CLIENTE")


async def crear_superadmin() -> UsuarioPrueba:
    """Autentica el actor global que administra el catálogo de ciudades."""
    email = os.getenv("TEST_SUPERADMIN_EMAIL", "superadmin@fashionstore.com")
    clave = os.getenv("TEST_SUPERADMIN_PASSWORD", "Fashion123!")
    token, usuario_id = await _login(email, clave)
    return UsuarioPrueba(
        await _nuevo_client(token), token, usuario_id, email, "SUPERADMIN"
    )


async def crear_ciudad_plataforma(nombre: str) -> dict:
    """Crea una ciudad global usando el actor que exige el contrato actual."""
    async with await crear_superadmin() as plataforma:
        respuesta = await plataforma.client.post(
            "/api/v1/ciudades", json={"nombre": nombre}
        )
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()


async def crear_staff(admin: AsyncClient, rol: str, sucursal_id: str, tag: str = "c2") -> UsuarioPrueba:
    uid = _uid(8)
    email = f"{rol.lower()}.{tag}.{uid}@fashionstore.com"
    clave = "clave123456"
    resp_roles = await admin.get("/api/v1/roles")
    assert resp_roles.status_code == 200
    rol_obj = next(r for r in resp_roles.json() if r["nombre"] == rol)
    resp = await admin.post(
        "/api/v1/usuarios",
        json={
            "rol_id": rol_obj["id"],
            "nombres": f"{rol.title()} {tag}",
            "apellidos": f"Prueba {uid}",
            "correo_electronico": email,
            "contrasenia": clave,
            "telefono": "+591 70000000",
            "sucursal_id": sucursal_id,
            "cargo": f"{rol} de prueba",
        },
    )
    assert resp.status_code == 201, resp.text
    usuario_id = resp.json()["id"]
    token, _ = await _login(email, clave)
    return UsuarioPrueba(await _nuevo_client(token), token, usuario_id, email, rol)


async def crear_sucursal(admin: AsyncClient, tag: str = "c2") -> str:
    uid = _uid()
    ciudad = await crear_ciudad_plataforma(f"Ciudad C2 {tag} {uid}")
    resp_suc = await admin.post(
        "/api/v1/sucursales",
        json={
            "ciudad_id": ciudad["id"],
            "nombre": f"Sucursal C2 {tag} {uid}",
            "direccion": "Av. prueba 123",
            "numero_anillo": 4,
            "tarifa_base_delivery": "10.00",
            "incremento_anillo_delivery": "2.00",
        },
    )
    assert resp_suc.status_code == 201, resp_suc.text
    return resp_suc.json()["id"]


async def sucursal_semilla(admin: AsyncClient) -> str:
    resp = await admin.get("/api/v1/sucursales")
    assert resp.status_code == 200
    assert resp.json(), "Se requiere la sucursal semilla"
    return resp.json()[0]["id"]


async def crear_variante_con_stock(
    admin: AsyncClient,
    sucursal_id: str,
    disponible: int,
    precio: str = "120.00",
    costo: str = "60.00",
    tag: str = "c2",
) -> dict:
    """Crea maestros + producto + variante y la ingresa con un lote (CU04)."""
    uid = _uid()
    async with AsyncSessionLocal() as db:
        async with db.begin():
            talla = Talla(empresa_id=EMPRESA_TEST_ID, nombre=f"T-C2-{tag}-{uid}", orden=1, activo=True)
            color = Color(empresa_id=EMPRESA_TEST_ID, nombre=f"Color C2 {tag} {uid}", codigo_hex="#AABBCC", activo=True)
            categoria = Categoria(empresa_id=EMPRESA_TEST_ID, nombre=f"Cat C2 {tag} {uid}", activo=True)
            db.add_all([talla, color, categoria])
            await db.flush()
            producto = Producto(
                empresa_id=EMPRESA_TEST_ID,
                categoria_id=categoria.id,
                nombre=f"Producto C2 {tag} {uid}",
                precio_base=Decimal(precio),
                activo=True,
            )
            db.add(producto)
            await db.flush()
            variante = VarianteProducto(
                empresa_id=EMPRESA_TEST_ID,
                producto_id=producto.id,
                talla_id=talla.id,
                color_id=color.id,
                sku=f"SKU-C2-{tag}-{uid}".upper(),
                precio=Decimal(precio),
                activa=True,
            )
            db.add(variante)
            await db.flush()
            variante_id = str(variante.id)
    resp_prov = await admin.post(
        "/api/v1/proveedores", json={"razon_social": f"Prov C2 {tag} {uid}", "nit": f"700{tag}{uid}"[:20]}
    )
    assert resp_prov.status_code == 201, resp_prov.text
    receptor = await crear_staff(admin, "ENCARGADO", sucursal_id, tag=f"rec{uid}")
    try:
        if disponible <= 0:
            return {"variante_id": variante_id, "precio": precio, "costo": costo}
        resp_lote = await admin.post(
            "/api/v1/recepciones",
            json={
                "proveedor_id": resp_prov.json()["id"],
                "sucursal_id": sucursal_id,
                "recibido_por_id": receptor.id,
                "numero_documento": f"DOC-{uid}",
                "detalles": [{"variante_id": variante_id, "cantidad": disponible, "costo_unitario": costo}],
            },
        )
        assert resp_lote.status_code == 201, resp_lote.text
    finally:
        await receptor.client.aclose()
    return {"variante_id": variante_id, "precio": precio, "costo": costo}


async def activar_adelanto(admin: AsyncClient, sucursal_id: str, modalidad: str, valor: str) -> dict:
    resp = await admin.patch(
        f"/api/v1/sucursales/{sucursal_id}/adelanto",
        json={"adelanto_activo": True, "modalidad_adelanto": modalidad, "valor_adelanto": valor},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def bolsa(sucursal_destino_id: str, lineas: list, fecha_visita=None, observacion=None) -> dict:
    """lineas: [(variante_id, cantidad, origen_id|None), ...]."""
    items = [
        {"variante_id": v, "cantidad": c, **({"sucursal_origen_id": o} if o else {})}
        for v, c, o in lineas
    ]
    carga = {"sucursal_destino_id": sucursal_destino_id, "lineas": items}
    if fecha_visita:
        carga["fecha_visita"] = fecha_visita
    if observacion:
        carga["observacion"] = observacion
    return carga


async def post_reserva(user: UsuarioPrueba, carga: dict, clave=None):
    return await user.client.post(
        "/api/v1/reservas", json=carga, headers=user.headers_clave(clave)
    )


async def forzar_vencimiento(reserva_id: str, minutos_atras: int = 60) -> None:
    """Mueve vence_en al pasado (viaje en el tiempo solo para pruebas)."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                text(
                    "UPDATE comercial.reservas "
                    "SET origen_plazo_en = CASE "
                    "WHEN origen_plazo_en IS NULL THEN NULL "
                    "ELSE now() - make_interval(mins => :m) - (vence_en - origen_plazo_en) "
                    "END, vence_en = now() - make_interval(mins => :m) "
                    "WHERE id = :rid"
                ),
                {"m": minutos_atras, "rid": reserva_id},
            )


async def preparar_atender(enc_client, reserva_id: str) -> None:
    r = await enc_client.patch(f"/api/v1/reservas/{reserva_id}/preparar")
    assert r.status_code == 200, r.text
    r = await enc_client.patch(f"/api/v1/reservas/{reserva_id}/atender")
    assert r.status_code == 200, r.text


async def vender_reserva(cajero, reserva_id: str, sucursal_id: str, items: list, metodo="EFECTIVO", clave=None):
    """items: [(detalle_reserva_id, variante_id, cantidad), ...]. Retorna comprobante."""
    carga = {
        "reserva_id": reserva_id,
        "sucursal_id": sucursal_id,
        "metodo": metodo,
        "items": [
            {"detalle_reserva_id": d, "variante_id": v, "cantidad": c} for d, v, c in items
        ],
    }
    resp = await cajero.client.post(
        "/api/v1/ventas/presenciales", json=carga,
        headers={"Idempotency-Key": clave or str(uuid.uuid4())},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
