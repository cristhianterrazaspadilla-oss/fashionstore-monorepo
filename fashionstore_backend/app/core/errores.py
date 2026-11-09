"""Respuestas de error comunes del backend para OpenAPI.

Formato común: `{"detail": {"codigo": "<ESTABLE>", "mensaje": "<humano>"}}`
o `{"detail": "<texto>"}` en validaciones simples. Códigos estables usados en
pruebas y por Angular/Flutter (no interpretar textos humanos).
"""
from typing import Any

_ERROR = {
    "type": "object",
    "properties": {
        "detail": {
            "oneOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "properties": {
                        "codigo": {"type": "string"},
                        "mensaje": {"type": "string"},
                    },
                },
            ]
        }
    },
}


def _r(descripcion: str, codigo: str, mensaje: str) -> dict[str, Any]:
    return {
        "description": descripcion,
        "content": {
            "application/json": {
                "schema": _ERROR,
                "example": {"detail": {"codigo": codigo, "mensaje": mensaje}},
            }
        },
    }


# Documentación por código (reutilizable en cada operación).
E400 = _r("Solicitud inválida", "SOLICITUD_INVALIDA", "Datos inválidos")
E401 = _r("Sesión inválida o ausente", "NO_AUTENTICADO", "Sesión requerida")
E403 = _r("RBAC: rol, propietario o sucursal no autorizado", "FORBIDDEN", "No autorizado")
E404 = _r("Recurso no encontrado", "NO_ENCONTRADO", "Recurso no encontrado")
E409_IDEM = _r(
    "Conflicto idempotente u operación incompatible",
    "IDEMPOTENCIA_CONFLICTO",
    "Idempotency-Key ya usada con otra solicitud",
)
E409_AMBITO = _r(
    "Idempotency-Key en uso por otro propietario",
    "IDEMPOTENCIA_AMBITO",
    "Idempotency-Key en uso por otro propietario",
)
E409_NEGOCIO = _r("Conflicto de negocio", "CONFLICTO_NEGOCIO", "Operación incompatible con el estado")
E422 = _r("Payload o consentimiento inválido", "VALIDACION", "Payload inválido")
E429 = _r("Rate limit de emisión", "LIMITE_FRECUENCIA", "Demasiadas solicitudes; reintente en un minuto")
E502 = _r("Proveedor rechazó la operación", "PROVEEDOR_RECHAZO", "El proveedor rechazó la operación")
E503_STRIPE = _r(
    "Stripe deshabilitado o fuera de Test Mode",
    "STRIPE_DESHABILITADO",
    "Pasarela en modo prueba no configurada",
)
E503_DECART = _r(
    "Decart deshabilitado, sin allowlist o sin cupo",
    "DECART_DESHABILITADO",
    "Probador virtual no configurado",
)

IDEMPOTENCY_HEADER = {
    "Idempotency-Key": {
        "description": "UUID v4 obligatorio. Mismo usuario+operación+payload devuelve el recurso; "
        "distinto payload devuelve 409; otro propietario nunca recibe datos ajenos.",
        "schema": {"type": "string", "format": "uuid"},
        "required": True,
    }
}
