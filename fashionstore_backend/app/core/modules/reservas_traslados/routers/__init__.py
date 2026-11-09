from backend.app.core.modules.reservas_traslados.routers.reservas import router as router_reservas
from backend.app.core.modules.reservas_traslados.routers.traslados import router as router_traslados
from backend.app.core.modules.reservas_traslados.routers.sincronizacion import router as router_sincronizacion

__all__ = [
    "router_reservas",
    "router_traslados",
    "router_sincronizacion",
]
