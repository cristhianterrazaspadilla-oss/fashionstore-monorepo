"""CU03/CU16: catálogo público aislado, sin campos privados y con instantánea."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text

from backend.app.core.modules.catalogo.models import Producto
from backend.app.core.modules.catalogo.services.catalogo_service import CatalogoService


@pytest.mark.asyncio
async def test_descarga_publica_aisla_empresas_y_no_expone_privados(
    escenario, fabrica_sesiones
):
    async with fabrica_sesiones() as db:
        servicio = CatalogoService(db)
        descarga_a = await servicio.descargarCatalogo(empresa_codigo=escenario.codigo_a)
        descarga_b = await servicio.descargarCatalogo(empresa_id=escenario.empresa_b_id)

    assert descarga_a.empresa_id == escenario.empresa_a_id
    assert descarga_a.total_productos == 1
    assert descarga_a.total_variantes == 3
    assert descarga_b.total_productos == 0
    assert descarga_b.total_variantes == 0
    assert all(p.nombre.startswith("Producto A") for p in descarga_a.productos)

    producto = descarga_a.productos[0]
    assert producto.precio_base_bob == "100.00"
    assert not hasattr(producto, "proveedor_principal_id")
    assert not hasattr(producto, "costo_estandar")
    assert not hasattr(producto, "margen_contribucion_minimo")
    variante = next(v for v in producto.variantes if v.id == escenario.variante_a_id)
    assert variante.precio_bob == "100.00"
    assert variante.disponibilidad == 5
    assert not hasattr(variante, "costo_promedio")
    assert not hasattr(variante, "costo_ultimo")


@pytest.mark.asyncio
async def test_catalogo_exige_contexto_de_empresa(escenario, fabrica_sesiones):
    async with fabrica_sesiones() as db:
        servicio = CatalogoService(db)
        for llamada in (
            lambda: servicio.listar(),
            lambda: servicio.filtrar(),
            lambda: servicio.obtenerOpcionesFiltros(),
            lambda: servicio.descargarCatalogo(),
        ):
            with pytest.raises(HTTPException) as error:
                await llamada()
            assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_catalogo_aisla_por_empresa_en_listado_y_filtros(
    escenario, fabrica_sesiones
):
    async with fabrica_sesiones() as db:
        servicio = CatalogoService(db)
        listado = await servicio.listar(empresa_id=escenario.empresa_a_id)
        filtros = await servicio.obtenerOpcionesFiltros(empresa_codigo=escenario.codigo_a)
        listado_b = await servicio.listar(empresa_id=escenario.empresa_b_id)

    assert len(listado) == 1
    assert listado[0].id == escenario.producto_a_id
    assert listado[0].proveedor_principal_id is None
    assert listado_b == []
    assert any(c.id == escenario.categoria_a_id for c in filtros.categorias)


@pytest.mark.asyncio
async def test_ruta_catalogo_productos_es_publica_y_sin_campos_privados(
    escenario, http
):
    respuesta = await http.cliente.get(
        "/api/v1/catalogo/productos",
        params={"empresa_codigo": escenario.codigo_a},
    )
    assert respuesta.status_code == 200
    items = respuesta.json()
    assert len(items) == 1
    assert items[0]["nombre"].startswith("Producto A")
    assert "proveedor_principal_id" not in items[0]
    assert "activo" not in items[0]
    assert "creado_en" not in items[0]

    sin_contexto = await http.cliente.get("/api/v1/catalogo/productos")
    assert sin_contexto.status_code == 400


@pytest.mark.asyncio
async def test_ruta_administrativa_productos_usa_empresa_de_sesion(
    escenario, http
):
    http.usar(escenario.usuario_admin_a)
    respuesta = await http.cliente.get("/api/v1/productos")
    assert respuesta.status_code == 200
    items = respuesta.json()
    assert len(items) == 1
    assert "proveedor_principal_id" in items[0]
    assert items[0]["proveedor_principal_id"] is None

    otra_empresa = await http.cliente.get(
        "/api/v1/productos", params={"empresa_id": str(escenario.empresa_b_id)}
    )
    assert otra_empresa.status_code == 403

    http.usar(escenario.usuario_global_sin_empresa)
    sin_empresa = await http.cliente.get("/api/v1/productos")
    assert sin_empresa.status_code == 400


@pytest.mark.asyncio
async def test_instantanea_usa_repeatable_read(escenario, fabrica_sesiones):
    async with fabrica_sesiones() as db:
        servicio = CatalogoService(db, fabrica_sesion=fabrica_sesiones)
        async with servicio._sesion_instantanea() as instantanea:
            nivel = await instantanea.scalar(text("show transaction_isolation"))
            assert nivel == "repeatable read"

            def contar_productos():
                return select(func.count()).select_from(Producto).where(
                    Producto.empresa_id == escenario.empresa_a_id
                )

            antes = int(await instantanea.scalar(contar_productos()) or 0)
            assert antes == 1

            # Otra transacción publica un producto y confirma durante la descarga.
            async with fabrica_sesiones() as otra:
                otra.add(
                    Producto(
                        id=uuid.uuid4(),
                        empresa_id=escenario.empresa_a_id,
                        categoria_id=escenario.categoria_a_id,
                        nombre="Producto concurrente",
                        precio_base=Decimal("10.00"),
                        activo=True,
                    )
                )
                await otra.commit()

            durante = int(await instantanea.scalar(contar_productos()) or 0)
            assert durante == antes, "La instantánea debe ignorar escrituras confirmadas después de su corte"

        descarga = await servicio.descargarCatalogo(empresa_id=escenario.empresa_a_id)
        assert descarga.total_productos == 2

        # Una sesión nueva sí observa el producto recién publicado.
        async with fabrica_sesiones() as nueva:
            despues = int(
                await nueva.scalar(
                    select(func.count()).select_from(Producto).where(
                        Producto.empresa_id == escenario.empresa_a_id
                    )
                )
                or 0
            )
    assert despues == 2
