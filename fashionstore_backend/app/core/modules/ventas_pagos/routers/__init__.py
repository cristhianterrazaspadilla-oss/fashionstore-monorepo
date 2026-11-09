from backend.app.core.modules.ventas_pagos.routers.ventas import router as router_ventas
from backend.app.core.modules.ventas_pagos.routers.pagos import router as router_pagos
from backend.app.core.modules.ventas_pagos.routers.pagos_stripe import router as router_pagos_stripe
from backend.app.core.modules.ventas_pagos.routers.carritos import router as router_carritos
from backend.app.core.modules.ventas_pagos.routers.entregas import router as router_entregas

__all__ = [
    "router_ventas",
    "router_pagos",
    "router_pagos_stripe",
    "router_carritos",
    "router_entregas",
]
