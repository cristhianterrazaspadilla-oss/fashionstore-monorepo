from backend.app.core.modules.posventa.routers.devoluciones import (
    router_devoluciones,
    router_mermas,
)
from backend.app.core.modules.posventa.routers.reembolsos import router as router_reembolsos
from backend.app.core.modules.posventa.routers.saldos import router as router_saldos

__all__ = [
    "router_devoluciones",
    "router_mermas",
    "router_reembolsos",
    "router_saldos",
]
