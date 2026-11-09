"""Contrato OpenAPI Ciclo 2 — huecos CU06 (solo lectura).

Verifica que los endpoints de consulta del catálogo exponen response_model
explícito sin cambiar el JSON actual ni la lógica de negocio:
- GET /api/v1/catalogo/filtros-opciones
- GET /api/v1/catalogo/variantes/{variante_id}/disponibilidad
- GET /api/v1/variantes/{variante_id}/disponibilidad (mismo contrato)
"""
import uuid
from datetime import datetime, timezone


def _openapi():
    import app  # noqa: F401 - alias para ejecución aislada
    from backend.app.main import app as fastapi_app
    return fastapi_app.openapi()


def test_openapi_filtros_opciones_tiene_respuesta_tipada():
    spec = _openapi()
    path = "/api/v1/catalogo/filtros-opciones"
    assert path in spec["paths"], f"{path} debe existir en OpenAPI"
    op = spec["paths"][path]["get"]
    assert "responses" in op
    ok = op["responses"].get("200", {})
    assert "content" in ok, "filtros-opciones debe declarar response_model (content 200)"
    schema = ok["content"]["application/json"]["schema"]
    ref = schema.get("$ref", "") or schema.get("allOf", [{}])[0].get("$ref", "")
    assert "FiltrosOpcionesDTO" in ref, f"filtros-opciones debe referenciar FiltrosOpcionesDTO, got {schema}"


def test_openapi_disponibilidad_tiene_respuesta_tipada():
    spec = _openapi()
    for path in (
        "/api/v1/catalogo/variantes/{variante_id}/disponibilidad",
        "/api/v1/variantes/{variante_id}/disponibilidad",
    ):
        assert path in spec["paths"], f"{path} debe existir en OpenAPI"
        op = spec["paths"][path]["get"]
        ok = op["responses"].get("200", {})
        assert "content" in ok, f"{path} debe declarar response_model (content 200)"
        schema = ok["content"]["application/json"]["schema"]
        # Debe ser array de DisponibilidadSucursalDTO
        items = schema.get("items", {})
        ref = items.get("$ref", "") or schema.get("$ref", "")
        assert "DisponibilidadSucursalDTO" in ref, f"{path} debe referenciar DisponibilidadSucursalDTO, got {schema}"


def test_dto_filtros_opciones_preserva_json_actual():
    """El DTO acepta exactamente el JSON que el endpoint ya devolvía."""
    from backend.app.core.modules.catalogo.schemas import FiltrosOpcionesDTO

    payload = {
        "categorias": [{"id": str(uuid.uuid4()), "nombre": "Camisas"}],
        "tallas": [{"id": str(uuid.uuid4()), "nombre": "M", "orden": 2}],
        "colores": [{"id": str(uuid.uuid4()), "nombre": "Rojo", "codigo_hex": "#FF0000"}],
        "temporadas": [{"id": str(uuid.uuid4()), "nombre": "Verano"}],
        "colecciones": [{"id": str(uuid.uuid4()), "nombre": "Urbana"}],
        "generos": ["HOMBRE", "MUJER"],
        "marcas": ["FashionStore"],
    }
    dto = FiltrosOpcionesDTO.model_validate(payload)
    out = dto.model_dump(mode="json")
    assert set(out.keys()) == set(payload.keys())
    assert out["generos"] == ["HOMBRE", "MUJER"]
    assert out["colores"][0]["codigo_hex"] == "#FF0000"


def test_dto_disponibilidad_preserva_json_actual():
    """El DTO acepta exactamente cada fila que disponibilidadPorSucursal ya devolvía."""
    from backend.app.core.modules.catalogo.schemas import DisponibilidadSucursalDTO

    ahora = datetime.now(timezone.utc)
    fila = {
        "inventario_id": str(uuid.uuid4()),
        "variante_id": str(uuid.uuid4()),
        "sucursal_id": str(uuid.uuid4()),
        "sucursal_nombre": "Sucursal Centro",
        "ciudad_id": str(uuid.uuid4()),
        "ciudad_nombre": "Santa Cruz",
        "direccion": "Av Principal 123",
        "telefono": "+591 70000000",
        "disponible": 15,
        "reservado": 3,
        "comprometido_traslado": 2,
        "en_transito": 1,
        "actualizado_en": ahora.isoformat(),
    }
    dto = DisponibilidadSucursalDTO.model_validate(fila)
    out = dto.model_dump(mode="json")
    assert set(out.keys()) == set(fila.keys())
    assert out["disponible"] == 15
    assert out["sucursal_nombre"] == "Sucursal Centro"

    # Teléfono/dirección opcionales pueden ser None sin romper el contrato
    fila_nula = dict(fila, telefono=None, direccion=None, actualizado_en=None)
    # actualizado_en es Optional en el DTO para tolerar filas sin marca temporal
    dto2 = DisponibilidadSucursalDTO.model_validate(fila_nula)
    assert dto2.telefono is None
