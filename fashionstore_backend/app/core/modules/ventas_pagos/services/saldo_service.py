"""Módulo de compatibilidad y reexportación para SaldoService en ventas_pagos."""
from backend.app.core.modules.posventa.services.saldo_service import (
    MovimientoSaldo,
    SaldoService,
)

__all__ = ["SaldoService", "MovimientoSaldo"]
