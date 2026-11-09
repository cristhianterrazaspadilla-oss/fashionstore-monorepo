"""Ayudas compartidas para las pruebas HTTP del Ciclo 3 (CU14-CU22, CU25).

Reutiliza tests/helpers_ciclo2.py (usuarios, sucursales, variantes con stock)
y agrega: promociones, carrito/checkout, fakes de Stripe/Decart, viaje en el
tiempo para ventas digitales y variantes compatibles con el probador.
"""
import uuid
from datetime import datetime, timedelta, timezone

import app  # noqa: F401  alias backend.*
from sqlalchemy import text

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.modules.catalogo.models import (
    Categoria, Color, Producto, Talla, VarianteProducto,
)
from tests.helpers_ciclo2 import EMPRESA_TEST_ID, UsuarioPrueba  # noqa: F401  re-export


def clave() -> str:
    return str(uuid.uuid4())


async def crear_promocion(
    admin, codigo: str, tipo: str = "PORCENTAJE", valor: str = "10.00",
    variante_ids: list | None = None, dias_inicio: int = -1, dias_fin: int = 1,
    activa: bool = True,
) -> dict:
    ahora = datetime.now(timezone.utc)
    codigo_unico = f"{codigo}-{uuid.uuid4().hex[:6].upper()}"
    carga = {
        "codigo": codigo_unico,
        "nombre": f"Promo {codigo_unico}",
        "tipo": tipo,
        "valor": valor,
        "activa": activa,
        "vigencia_inicio": (ahora + timedelta(days=dias_inicio)).isoformat(),
        "vigencia_fin": (ahora + timedelta(days=dias_fin)).isoformat(),
        "variante_ids": variante_ids or [],
    }
    resp = await admin.post("/api/v1/promociones", json=carga)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def agregar_linea(cliente: UsuarioPrueba, variante_id: str, cantidad: int,
                        canal: str = "WEB", clave_id: str | None = None) -> dict:
    resp = await cliente.client.post(
        "/api/v1/carritos/mio/lineas",
        params={"canal": canal},
        json={"variante_id": variante_id, "cantidad": cantidad},
        headers={"Idempotency-Key": clave_id or clave()},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def hacer_checkout(
    cliente: UsuarioPrueba, sucursal_id: str, canal: str = "WEB",
    modalidad: str = "RECOJO", direccion: str | None = None,
    anillo: int | None = None, clave_id: str | None = None,
    estado_esperado: int = 201,
) -> dict:
    carga = {"sucursal_id": sucursal_id, "canal": canal, "modalidad": modalidad}
    if direccion:
        carga["direccion"] = direccion
    if anillo is not None:
        carga["anillo_destino"] = anillo
    resp = await cliente.client.post(
        "/api/v1/carritos/mio/checkout",
        params={"canal": canal},
        json=carga,
        headers={"Idempotency-Key": clave_id or clave()},
    )
    assert resp.status_code == estado_esperado, resp.text
    return resp.json()


async def forzar_vencimiento_venta(venta_id: str, minutos_atras: int = 61) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                text("UPDATE comercial.ventas SET expira_en = now() - make_interval(mins => :m) "
                     "WHERE id = :vid"),
                {"m": minutos_atras, "vid": venta_id},
            )


async def stock_en(sucursal_id: str, variante_id: str) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        fila = await db.execute(
            text("SELECT disponible, reservado FROM inventario.inventario_sucursal "
                 "WHERE sucursal_id = :s AND variante_id = :v"),
            {"s": sucursal_id, "v": variante_id},
        )
        row = fila.first()
        return (row[0], row[1]) if row else (0, 0)


async def contar_kardex(venta_id: str, tipo: str) -> int:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            text("SELECT count(*) FROM inventario.movimientos_inventario "
                 "WHERE referencia_tipo = 'VENTA' AND referencia_id = :v AND tipo = :t"),
            {"v": venta_id, "t": tipo},
        )
        return int(r.scalar() or 0)


async def crear_variante_probador(admin, sucursal_id: str, disponible: int = 5,
                                  tag: str = "t17") -> dict:
    """Variante compatible CU17: categoría de prenda superior + recurso HTTPS."""
    from tests.helpers_ciclo2 import crear_variante_con_stock  # noqa

    uid = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        async with db.begin():
            talla = Talla(empresa_id=EMPRESA_TEST_ID, nombre=f"T-T17-{tag}-{uid}", orden=1, activo=True)
            color = Color(empresa_id=EMPRESA_TEST_ID, nombre=f"Color T17 {tag} {uid}", codigo_hex="#FFFFFF", activo=True)
            categoria = Categoria(empresa_id=EMPRESA_TEST_ID, nombre=f"Camisa T17 {tag} {uid}", activo=True)
            db.add_all([talla, color, categoria])
            await db.flush()
            producto = Producto(
                empresa_id=EMPRESA_TEST_ID,
                categoria_id=categoria.id, nombre=f"Camisa prueba {tag} {uid}",
                precio_base=150, activo=True,
            )
            db.add(producto)
            await db.flush()
            variante = VarianteProducto(
                empresa_id=EMPRESA_TEST_ID,
                producto_id=producto.id, talla_id=talla.id, color_id=color.id,
                sku=f"SKU-T17-{tag}-{uid}".upper(), precio=150,
                recurso_prueba_virtual=f"https://cdn.fashionstore.test/prendas/{uid}.webp",
                activa=True,
            )
            db.add(variante)
            await db.flush()
            variante_id = str(variante.id)
    if disponible > 0:
        from tests.helpers_ciclo2 import crear_staff
        prov = await admin.post(
            "/api/v1/proveedores", json={"razon_social": f"Prov T17 {tag} {uid}"}
        )
        assert prov.status_code == 201, prov.text
        receptor = await crear_staff(admin, "ENCARGADO", sucursal_id, tag=f"t17{uid[:4]}")
        try:
            lote = await admin.post(
                "/api/v1/recepciones",
                json={
                    "proveedor_id": prov.json()["id"], "sucursal_id": sucursal_id,
                    "recibido_por_id": receptor.id, "numero_documento": f"T17-{uid}",
                    "detalles": [{"variante_id": variante_id, "cantidad": disponible,
                                  "costo_unitario": "60.00"}],
                },
            )
            assert lote.status_code == 201, lote.text
        finally:
            await receptor.client.aclose()
    return {"variante_id": variante_id}


class FakeStripe:
    """Envoltorio del FakeStripeGateway con helpers de estado para pruebas."""

    def __init__(self):
        from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw

        self.gw = gw.FakeStripeGateway()

    def instalar(self):
        from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw

        gw.fijar_gateway(self.gw)

    def desinstalar(self):
        from backend.app.core.modules.ventas_pagos.integraciones import stripe_gateway as gw

        gw.fijar_gateway(None)


def instalar_decart_falso(token: str = "tok-corto-prueba"):
    """Doble fiel al SDK (`client.tokens.create`): sin red ni créditos.

    Imita `CreateTokenResponse` con atributos snake_case: `api_key`,
    `expires_at`, `permissions` y `constraints`. Retorna capturas con los
    parámetros contractuales (expires_in=60, lucy-2.5, maxSessionDuration=120).
    """
    from datetime import datetime, timezone

    from backend.app.core.modules.experiencia_cliente.integraciones import decart_client

    capturas: dict = {}

    class _TokenSDK:
        def __init__(self, api_key: str, expires_at):
            self.api_key = api_key
            self.expires_at = expires_at
            self.permissions = {"models": ["lucy-2.5"]}
            self.constraints = {"realtime": {"maxSessionDuration": 120}}

    async def _falso(correlation_id: str):
        capturas["correlation_id"] = correlation_id
        capturas["parametros"] = decart_client.parametros_token(correlation_id)
        expira = datetime.now(timezone.utc) + timedelta(seconds=60)
        return _TokenSDK(token, expira)

    decart_client.fijar_creador_falso(_falso)
    return capturas


def desinstalar_decart_falso():
    from backend.app.core.modules.experiencia_cliente.integraciones import decart_client

    decart_client.fijar_creador_falso(None)


def instalar_validador_falso(modo: str = "ok"):
    """Validador de imágenes sin red para pruebas (sintaxis real + modo)."""
    from backend.app.core.modules.experiencia_cliente.integraciones import decart_imagen as di

    di.fijar_validador(di.ValidadorFalso(modo))


def desinstalar_validador_falso():
    from backend.app.core.modules.experiencia_cliente.integraciones import decart_imagen as di

    di.fijar_validador(None)
