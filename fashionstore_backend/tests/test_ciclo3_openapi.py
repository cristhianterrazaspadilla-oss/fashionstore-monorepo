"""Corrección 8 — OpenAPI completo: errores de negocio + compatibilidad histórica.

El contrato del segundo parcial agrega rutas y campos; la exportación histórica
del Ciclo 3 se conserva intacta y debe seguir siendo un subconjunto válido.
La instantánea vigente se compara en
``tests_segundo_parcial_bloque_b/test_openapi_segundo_parcial.py``.
"""
import json
from pathlib import Path


def _spec():
    import app  # noqa: F401
    from backend.app.main import app as fastapi_app
    return fastapi_app.openapi()


def test_errores_documentados_carrito_checkout():
    spec = _spec()
    op = spec["paths"]["/api/v1/carritos/mio/checkout"]["post"]
    for codigo in ("400", "401", "403", "404", "409", "422"):
        assert codigo in op["responses"], f"checkout debe documentar {codigo}"
    op2 = spec["paths"]["/api/v1/carritos/mio/lineas"]["post"]
    assert "409" in op2["responses"] and "422" in op2["responses"]


def test_errores_stripe_y_decart():
    spec = _spec()
    inten = spec["paths"]["/api/v1/pagos/stripe/intenciones"]["post"]
    for codigo in ("400", "401", "403", "404", "409", "502", "503"):
        assert codigo in inten["responses"], f"stripe intenciones debe documentar {codigo}"
    aut = spec["paths"]["/api/v1/probador/autorizaciones"]["post"]
    for codigo in ("401", "403", "404", "409", "422", "429", "502", "503"):
        assert codigo in aut["responses"], f"decart debe documentar {codigo}"
    # Idempotency-Key documentado en la descripción.
    assert "Idempotency-Key" in aut.get("description", "")


def test_openapi_conserva_contrato_ciclo3():
    spec = _spec()
    ruta = Path(__file__).resolve().parent.parent.parent / "docu_general" / "ciclo-3" / "openapi-ciclo3.json"
    assert ruta.exists(), f"falta {ruta}"
    exportado = json.loads(ruta.read_text(encoding="utf-8"))

    for camino, operaciones in exportado["paths"].items():
        assert camino in spec["paths"], f"se eliminó la ruta histórica {camino}"
        for metodo in operaciones:
            assert metodo in spec["paths"][camino], (
                f"se eliminó la operación histórica {metodo.upper()} {camino}"
            )
    for nombre in exportado["components"]["schemas"]:
        assert nombre in spec["components"]["schemas"], (
            f"se eliminó el esquema histórico {nombre}"
        )
