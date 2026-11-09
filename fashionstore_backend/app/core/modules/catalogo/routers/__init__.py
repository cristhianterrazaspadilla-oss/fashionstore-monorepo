from backend.app.core.modules.catalogo.routers.maestros import (
    router_tallas,
    router_colores,
    router_categorias,
    router_temporadas,
    router_colecciones,
)
from backend.app.core.modules.catalogo.routers.productos import router as router_productos
from backend.app.core.modules.catalogo.routers.variantes import router as router_variantes
from backend.app.core.modules.catalogo.routers.catalogo import router as router_catalogo
from backend.app.core.modules.catalogo.routers.promociones import router as router_promociones

__all__ = [
    "router_tallas",
    "router_colores",
    "router_categorias",
    "router_temporadas",
    "router_colecciones",
    "router_productos",
    "router_variantes",
    "router_catalogo",
    "router_promociones",
]
