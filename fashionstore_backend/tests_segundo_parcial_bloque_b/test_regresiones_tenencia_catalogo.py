"""Regresiones de catálogo tras exigir empresa_id en la migración 0006."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from backend.app.core.modules.catalogo.models import Categoria, Color, Producto, Talla, VarianteProducto
from backend.app.core.modules.catalogo.services.catalogo_service import resolver_empresa_lectura_defecto
from backend.app.core.modules.identidad_empresas.models import Rol, Suscripcion, Usuario
from backend.app.core.modules.identidad_empresas.services.plan_service import PlanService

from .conftest import T0


@pytest.mark.asyncio
async def test_altas_heredadas_guardan_empresa_y_rechazan_referencias_ajenas(escenario, fabrica_sesiones, http):
    http.usar(escenario.usuario_admin_a)
    sufijo = uuid.uuid4().hex[:8]

    for ruta, cuerpo in (
        ("tallas", {"nombre": f"T-{sufijo}"}),
        ("colores", {"nombre": f"Color {sufijo}", "codigo_hex": "#010203"}),
        ("categorias", {"nombre": f"Categoria {sufijo}"}),
        ("temporadas", {"nombre": f"Temporada {sufijo}"}),
        ("colecciones", {"nombre": f"Coleccion {sufijo}"}),
        ("proveedores", {"razon_social": f"Proveedor {sufijo}", "nit": sufijo}),
    ):
        respuesta = await http.cliente.post(f"/api/v1/{ruta}", json=cuerpo)
        assert respuesta.status_code == 201, (ruta, respuesta.text)
        identificador = uuid.UUID(respuesta.json()["id"])
        async with fabrica_sesiones() as db:
            tabla = {
                "tallas": Talla, "colores": Color, "categorias": Categoria,
            }.get(ruta)
            if tabla:
                assert (await db.get(tabla, identificador)).empresa_id == escenario.empresa_a_id
        if ruta == "tallas":
            talla_id = identificador
        elif ruta == "colores":
            color_id = identificador
        elif ruta == "categorias":
            categoria_id = identificador

    producto = await http.cliente.post(
        "/api/v1/productos",
        json={"nombre": f"Producto {sufijo}", "precio_base": "120.00", "categoria_id": str(categoria_id)},
    )
    assert producto.status_code == 201, producto.text
    producto_id = uuid.UUID(producto.json()["id"])

    variante = await http.cliente.post(
        "/api/v1/variantes",
        json={"producto_id": str(producto_id), "talla_id": str(talla_id),
              "color_id": str(color_id), "sku": f"SKU-{sufijo}", "precio": "120.00"},
    )
    assert variante.status_code == 201, variante.text
    async with fabrica_sesiones() as db:
        assert (await db.get(Producto, producto_id)).empresa_id == escenario.empresa_a_id
        assert (await db.get(VarianteProducto, uuid.UUID(variante.json()["id"]))).empresa_id == escenario.empresa_a_id
        categoria_ajena = Categoria(id=uuid.uuid4(), empresa_id=escenario.empresa_b_id,
                                     nombre=f"Ajena {sufijo}", activo=True)
        db.add(categoria_ajena)
        await db.commit()

    ajeno = await http.cliente.post(
        "/api/v1/productos",
        json={"nombre": f"Cruce {sufijo}", "precio_base": "10.00", "categoria_id": str(categoria_ajena.id)},
    )
    assert ajeno.status_code == 404

    http.usar(escenario.usuario_a)
    proveedores_cliente = await http.cliente.get("/api/v1/proveedores")
    assert proveedores_cliente.status_code == 403
    http.usar(escenario.usuario_admin_a)

    promocion = await http.cliente.post(
        "/api/v1/promociones",
        json={"codigo": f"PROMO-{sufijo}", "nombre": f"Promocion {sufijo}",
              "tipo": "PORCENTAJE", "valor": "10.00",
              "variante_ids": [variante.json()["id"]]},
    )
    assert promocion.status_code == 201, promocion.text


@pytest.mark.asyncio
async def test_renovacion_futura_no_desplaza_plan_vigente(escenario, fabrica_sesiones):
    async with fabrica_sesiones() as db:
        actual = (await db.execute(
            select(Suscripcion).where(Suscripcion.empresa_id == escenario.empresa_a_id)
        )).scalars().one()
        db.add(Suscripcion(
            id=uuid.uuid4(), empresa_id=escenario.empresa_a_id,
            plan_id=actual.plan_id, version=2,
            inicia_en=T0 + timedelta(days=366), vence_en=T0 + timedelta(days=730),
            creada_en=T0, creada_por=escenario.ids["superadmin"], motivo="Renovación futura",
        ))
        await db.commit()
        capacidad = await PlanService(db).validar_capacidad(escenario.empresa_a_id, ahora=T0)
        assert capacidad.habilitado is True
        assert capacidad.estado_suscripcion == "VIGENTE"
        assert capacidad.inicia_en == actual.inicia_en


@pytest.mark.asyncio
async def test_cajero_no_recibe_costos_ni_proveedor(escenario, fabrica_sesiones, http):
    async with fabrica_sesiones() as db:
        rol = (await db.execute(select(Rol).where(Rol.nombre == "CAJERO"))).scalars().first()
        assert rol is not None
        cajero = Usuario(
            id=uuid.uuid4(), empresa_id=escenario.empresa_a_id, rol_id=rol.id, rol=rol,
            nombres="Cajero", apellidos="Prueba", correo_electronico=f"cajero_{uuid.uuid4().hex}@test.local",
            contrasenia_hash="no-usar", estado="ACTIVO",
        )
        db.add(cajero)
        await db.commit()
    http.usar(cajero)
    productos = await http.cliente.get("/api/v1/productos")
    variantes = await http.cliente.get("/api/v1/variantes")
    assert productos.status_code == variantes.status_code == 200
    assert productos.json() and variantes.json()
    assert "proveedor_principal_id" not in productos.json()[0]
    assert "costo_promedio" not in variantes.json()[0]
    assert "costo_ultimo" not in variantes.json()[0]


@pytest.mark.asyncio
async def test_sin_empresa_heredada_y_con_varias_activas_no_se_elige_una_al_azar():
    class Resultado:
        def __init__(self, filas):
            self.filas = filas

        def scalars(self):
            return self

        def first(self):
            return self.filas[0] if self.filas else None

        def all(self):
            return self.filas

    class Sesion:
        def __init__(self):
            self.contador = 0

        async def execute(self, _consulta):
            self.contador += 1
            return Resultado([] if self.contador == 1 else [object(), object()])

    assert await resolver_empresa_lectura_defecto(Sesion()) is None
