"""Contrato OpenAPI vigente del segundo parcial y compatibilidad histórica.

La exportación histórica del Ciclo 3 no se modifica: el contrato actual debe
seguir conteniéndola y se identifica aparte en
``contratos/segundo-parcial/openapi-segundo-parcial.json``.
"""
import json
from pathlib import Path

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
RAIZ_PROYECTO = RAIZ_BACKEND.parent


def _spec():
    from backend.app.main import app

    return app.openapi()


def _canon(objeto) -> str:
    return json.dumps(objeto, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_openapi_exportado_del_segundo_parcial_esta_actualizado():
    ruta = RAIZ_BACKEND / "contratos" / "segundo-parcial" / "openapi-segundo-parcial.json"
    assert ruta.exists(), f"falta la exportación vigente {ruta}"
    exportado = json.loads(ruta.read_text(encoding="utf-8"))
    assert _canon(exportado) == _canon(_spec()), (
        "openapi-segundo-parcial.json desincronizado: regenere con backend.app.main.app.openapi()"
    )


def test_openapi_declara_rutas_y_esquemas_del_bloque_b():
    spec = _spec()
    for ruta in (
        "/api/v1/catalogo/descarga",
        "/api/v1/sincronizacion/operaciones",
        "/api/v1/sincronizacion/operaciones/{operacion_id}",
        "/api/v1/sincronizacion/referencia-horaria",
    ):
        assert ruta in spec["paths"], f"falta la ruta {ruta}"

    esquemas = spec["components"]["schemas"]
    for nombre in (
        "CatalogoDescargaDTO",
        "ProductoPublicoDTO",
        "OperacionDTO",
        "OperacionDatosReservaDTO",
        "ResultadoOperacionDTO",
    ):
        assert nombre in esquemas, f"falta el esquema {nombre}"

    publico = set(esquemas["ProductoPublicoDTO"]["properties"])
    assert "proveedor_principal_id" not in publico
    assert "costo_promedio" not in publico
    assert "costo_ultimo" not in publico

    datos = esquemas["OperacionDatosReservaDTO"]
    assert "visita_en" in datos["required"]
    version = esquemas["OperacionDTO"]["properties"]["version_esquema"]
    assert (
        set(version.get("enum", [])) == {1, 2, 3}
        or version.get("const") == 1
    ), f"version_esquema debe aceptar versiones 1, 2 y 3 según operacion.schema.json, obtenido {version}"

    assert "empresa_id" in esquemas["ReservaDTO"]["required"]
    assert "origen_plazo_en" in esquemas["ReservaDTO"]["properties"]


def test_contrato_historico_del_ciclo_3_sigue_presente():
    historico = RAIZ_PROYECTO / "docu_general" / "ciclo-3" / "openapi-ciclo3.json"
    assert historico.exists(), f"falta el contrato histórico {historico}"
    exportado = json.loads(historico.read_text(encoding="utf-8"))
    spec = _spec()

    for ruta, operaciones in exportado["paths"].items():
        assert ruta in spec["paths"], f"se eliminó una ruta histórica: {ruta}"
        for metodo in operaciones:
            assert metodo in spec["paths"][ruta], (
                f"se eliminó la operación histórica {metodo.upper()} {ruta}"
            )

    for nombre in exportado["components"]["schemas"]:
        assert nombre in spec["components"]["schemas"], (
            f"se eliminó el esquema histórico {nombre}"
        )
