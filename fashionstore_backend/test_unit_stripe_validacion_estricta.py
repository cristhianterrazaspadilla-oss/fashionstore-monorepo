"""Pruebas puras de la puerta de validación de PaymentIntents."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

from backend.app.core.modules.ventas_pagos.integraciones.stripe_gateway import (  # noqa: E402
    FakeStripeGateway,
)
from backend.app.core.modules.ventas_pagos.services.stripe_service import StripeService  # noqa: E402


@pytest.fixture
def orden():
    return SimpleNamespace(
        referencia_externa="pi_unit_1",
        clave_externa="pi_unit_1",
        centavos_usd=1250,
        empresa_id=uuid4(),
        contexto="VENTA",
        venta_id=uuid4(),
        pedido_id=None,
        reserva_id=None,
        cambio_id=None,
    )


def _evento(orden, **cambios):
    evento = {
        "id": "pi_unit_1",
        "currency": "usd",
        "amount": 1250,
        "metadata": {
            "empresa_id": str(orden.empresa_id),
            "venta_id": str(orden.venta_id),
        },
    }
    evento.update(cambios)
    return evento


def _validar(evento, orden):
    StripeService._validar_intencion_con_orden(None, evento, orden)


def test_webhook_valido_con_monto_moneda_y_metadata_completos(orden):
    _validar(_evento(orden), orden)


@pytest.mark.parametrize(
    "mutar",
    [
        lambda pi, orden: pi.pop("currency"),
        lambda pi, orden: pi.update(currency="bob"),
        lambda pi, orden: pi.pop("amount"),
        lambda pi, orden: pi.update(amount=1251),
        lambda pi, orden: pi.update(amount=1250.5),
        lambda pi, orden: pi.pop("metadata"),
        lambda pi, orden: pi.update(metadata={}),
        lambda pi, orden: pi.update(metadata={"empresa_id": "otra", "venta_id": str(orden.venta_id)}),
        lambda pi, orden: pi.update(metadata={"empresa_id": str(orden.empresa_id), "venta_id": str(uuid4())}),
    ],
)
def test_rechaza_datos_financieros_o_metadata_ausentes_y_discordantes(orden, mutar):
    evento = _evento(orden)
    mutar(evento, orden)
    with pytest.raises(HTTPException) as exc:
        _validar(evento, orden)
    assert exc.value.status_code == 400


def test_rechaza_payment_intent_ajeno(orden):
    evento = _evento(orden, id="pi_otra_venta")
    with pytest.raises(HTTPException):
        _validar(evento, orden)


@pytest.mark.parametrize(
    ("contexto", "campo", "resource_attr"),
    [
        ("PEDIDO", "pedido_id", "pedido_id"),
        ("RESERVA", "reserva_id", "reserva_id"),
        ("CAMBIO", "cambio_id", "cambio_id"),
    ],
)
def test_exige_empresa_y_recurso_para_cada_contexto(orden, contexto, campo, resource_attr):
    resource_id = uuid4()
    setattr(orden, "contexto", contexto)
    setattr(orden, "venta_id", None)
    setattr(orden, resource_attr, resource_id)
    evento = {
        "id": "pi_unit_1",
        "currency": "usd",
        "amount": 1250,
        "metadata": {"empresa_id": str(orden.empresa_id), campo: str(resource_id)},
    }
    _validar(evento, orden)
    evento["metadata"].pop(campo)
    with pytest.raises(HTTPException):
        _validar(evento, orden)


@pytest.mark.asyncio
async def test_fake_gateway_conserva_metadata_que_se_envia_a_stripe():
    gateway = FakeStripeGateway()
    metadata = {"empresa_id": "empresa-1", "pedido_id": "pedido-1"}
    inten = await gateway.crear_pago_conectado(
        recurso_id="pedido-1",
        monto_centavos=1250,
        moneda="usd",
        idempotency_key="idem-unit-1",
        metadata=metadata,
    )
    assert inten.metadata == {"recurso_id": "pedido-1", **metadata}
