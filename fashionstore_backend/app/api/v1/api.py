from fastapi import APIRouter

# Paquetes canónicos bajo backend/app/core/modules
from backend.app.core.modules.identidad_empresas.routers import (
    clientes,
    empresas,
    notificaciones,
    roles,
    sesion,
    suscripciones,
    usuarios,
)
from backend.app.core.modules.organizacion.routers import (
    ciudades,
    sucursales,
    tasas_cambio,
)
from backend.app.core.modules.inventario.routers import (
    inventario,
    proveedores,
    recepciones,
)
from backend.app.core.modules.catalogo.routers import (
    catalogo,
    maestros,
    productos,
    promociones,
    variantes,
)
from backend.app.core.modules.reservas_traslados.routers import (
    reservas,
    sincronizacion,
    traslados,
)
from backend.app.core.modules.ventas_pagos.routers import (
    cajas,
    carritos,
    entregas,
    pagos,
    pagos_stripe,
    pedidos,
    ventas,
    ventas_presenciales,
)
from backend.app.core.modules.posventa.routers import (
    cambios,
    devoluciones,
    reembolsos,
    saldos,
)
from backend.app.core.modules.analitica.routers import (
    dashboard,
    ia_analitica,
    ml_modelos,
    reportes,
)
from backend.app.core.modules.experiencia_cliente.routers import (
    ia,
    probador,
)

api_router = APIRouter()

# Identidad y Empresas (CU01, CU02, CU13, CU14)
api_router.include_router(suscripciones.router, prefix="", tags=["Suscripciones CU02"])
api_router.include_router(empresas.router, prefix="/empresas", tags=["Empresas CU01"])
api_router.include_router(clientes.router, prefix="/clientes", tags=["Clientes CU13"])
api_router.include_router(sesion.router, prefix="/sesion", tags=["Autenticación"])
api_router.include_router(usuarios.router, prefix="/usuarios", tags=["Gestión de Usuarios"])
api_router.include_router(roles.router, prefix="/roles", tags=["Roles"])
api_router.include_router(notificaciones.router, prefix="/notificaciones", tags=["Notificaciones y Avisos"])

# Organización (CU03, CU12, CU15)
api_router.include_router(ciudades.router, prefix="/ciudades", tags=["Ciudades"])
api_router.include_router(sucursales.router, prefix="/sucursales", tags=["Sucursales y Delivery"])
api_router.include_router(tasas_cambio.router, prefix="/plataforma/tasas-cambio", tags=["Tasa de Cambio BOB/USD CU12"])

# Inventario (CU04, CU07)
api_router.include_router(proveedores.router, prefix="/proveedores", tags=["Proveedores"])
api_router.include_router(recepciones.router, prefix="/recepciones", tags=["Recepción de Lotes"])
api_router.include_router(inventario.router, prefix="/inventario", tags=["Inventario Kardex CU07"])

# Catálogo (CU05, CU06, CU22)
api_router.include_router(maestros.router_tallas, prefix="/tallas", tags=["Maestros - Tallas"])
api_router.include_router(maestros.router_colores, prefix="/colores", tags=["Maestros - Colores"])
api_router.include_router(maestros.router_categorias, prefix="/categorias", tags=["Maestros - Categorías"])
api_router.include_router(maestros.router_temporadas, prefix="/temporadas", tags=["Maestros - Temporadas"])
api_router.include_router(maestros.router_colecciones, prefix="/colecciones", tags=["Maestros - Colecciones"])
api_router.include_router(productos.router, prefix="/productos", tags=["Productos"])
api_router.include_router(variantes.router, prefix="/variantes", tags=["Variantes de Producto"])
api_router.include_router(catalogo.router, prefix="/catalogo", tags=["Catálogo CU06"])
api_router.include_router(promociones.router, prefix="/promociones", tags=["Promociones CU22"])

# Reservas y Traslados (CU08, CU09, CU10, CU24, CU04, CU18)
api_router.include_router(reservas.router, prefix="/reservas", tags=["Reservas CU08/CU10/CU24/CU18"])
api_router.include_router(traslados.router, prefix="/traslados", tags=["Traslados CU09"])
api_router.include_router(sincronizacion.router, prefix="/sincronizacion", tags=["Sincronización CU04"])

# Ventas y Pagos (CU11, CU13, CU14, CU15, CU16, CU19, CU21, CU22)
api_router.include_router(ventas_presenciales.router, prefix="/ventas/presenciales", tags=["Ventas Presenciales CU19"])
api_router.include_router(pedidos.router, prefix="", tags=["Pedidos y Carrito CU21"])
api_router.include_router(cajas.router, prefix="", tags=["Cajas Offline CU06/CU07"])
api_router.include_router(pagos.router, prefix="/pagos", tags=["Pagos y Adelantos CU11"])
api_router.include_router(ventas.router, prefix="/ventas", tags=["Venta Presencial CU11"])
api_router.include_router(carritos.router, prefix="/carritos", tags=["Carrito y Checkout CU14"])
api_router.include_router(pagos_stripe.router, prefix="/pagos", tags=["Stripe Test CU15/CU22"])
api_router.include_router(entregas.router, prefix="/entregas", tags=["Entregas CU16"])

# Posventa y Finanzas (CU08, CU09, CU12, CU20, CU27)
api_router.include_router(cambios.router, prefix="/cambios", tags=["Cambios CU08"])
api_router.include_router(saldos.router, prefix="", tags=["Saldos CU09"])
api_router.include_router(reembolsos.router, prefix="/reembolsos", tags=["Reembolsos CU27"])
api_router.include_router(devoluciones.router_devoluciones, prefix="/devoluciones", tags=["Devoluciones CU12/CU20"])
api_router.include_router(devoluciones.router_mermas, prefix="/mermas", tags=["Mermas CU12/CU20"])


# Analítica (CU10, CU11, CU19, CU21, CU23, CU24, CU25)
api_router.include_router(reportes.router, prefix="/analitica", tags=["Reportes CU25"])
api_router.include_router(dashboard.router, prefix="/analitica", tags=["Dashboard CU23"])
api_router.include_router(ia_analitica.router, prefix="/analitica", tags=["IA Analítica CU24"])
api_router.include_router(ml_modelos.router, prefix="/analitica", tags=["Modelos ML CU10/CU11"])

# Compatibilidad legada
api_router.include_router(reportes.router, prefix="/reportes", tags=["Reportes CU23"])
api_router.include_router(dashboard.router, prefix="/reportes", tags=["Dashboard CU19"])
api_router.include_router(ia_analitica.router, prefix="/ia", tags=["IA CU18/CU20/CU21/CU25"])

# Experiencia del Cliente (CU17, CU18, CU20)
api_router.include_router(probador.router, prefix="", tags=["Probador Decart CU17"])
api_router.include_router(ia.router, prefix="/ia", tags=["IA CU18/CU20/CU21/CU25"])
