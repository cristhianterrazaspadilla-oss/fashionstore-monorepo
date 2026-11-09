from backend.app.core.modules.inventario.routers.proveedores import router as router_proveedores
from backend.app.core.modules.inventario.routers.recepciones import router as router_recepciones
from backend.app.core.modules.inventario.routers.inventario import router as router_inventario

__all__ = [
    "router_proveedores",
    "router_recepciones",
    "router_inventario",
]
