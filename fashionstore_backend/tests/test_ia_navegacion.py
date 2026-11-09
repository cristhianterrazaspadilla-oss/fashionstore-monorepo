"""Registros de navegación del cliente con aislamiento por empresa."""
import uuid
from types import SimpleNamespace

import pytest

from backend.app.core.modules.experiencia_cliente.models import HistorialNavegacion
from backend.app.core.modules.experiencia_cliente.services.ia_service import IAService


class SesionMemoria:
    def __init__(self):
        self.agregados = []
        self.confirmada = False
        self.revertida = False

    def add(self, entidad):
        self.agregados.append(entidad)

    async def commit(self):
        self.confirmada = True

    async def rollback(self):
        self.revertida = True


@pytest.mark.asyncio
async def test_registrar_navegacion_guarda_empresa_y_evento():
    empresa_id = uuid.uuid4()
    usuario_id = uuid.uuid4()
    variante_id = uuid.uuid4()
    db = SesionMemoria()
    usuario = SimpleNamespace(
        id=usuario_id,
        empresa_id=empresa_id,
        rol=SimpleNamespace(nombre="CLIENTE"),
    )

    resultado = await IAService(db).registrarNavegacion(
        usuario, "PRUEBA_VIRTUAL", variante_id=variante_id
    )

    assert resultado == {"evento": "PRUEBA_VIRTUAL", "registrado": True}
    assert db.confirmada is True
    assert db.revertida is False
    assert len(db.agregados) == 1
    evento = db.agregados[0]
    assert isinstance(evento, HistorialNavegacion)
    assert evento.empresa_id == empresa_id
    assert evento.cliente_id == usuario_id
    assert evento.usuario_id == usuario_id
    assert evento.variante_id == variante_id
    assert evento.evento == "PRUEBA_VIRTUAL"
