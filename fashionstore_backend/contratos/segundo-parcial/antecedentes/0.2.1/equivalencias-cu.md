# Equivalencia de códigos y alcance

La numeración académica cambia; los IDs persistidos, rutas públicas y nombres de métodos no se modifican automáticamente. Cualquier referencia externa antigua debe identificarse por su nombre y esta tabla. LB indica función conservada fuera de los 26 prioritarios.

| Código anterior | Código actual | Nombre actual o función conservada | Primera presentación |
|---|---|---|---|
| CU01 | CU13 | Registrarse e iniciar sesión por empresa | Sí |
| CU02 | CU14 | Gestionar usuarios y roles de la empresa | No |
| CU03 | CU15 | Gestionar ciudades, sucursales y tarifas | Sí |
| CU04 | LB04 | Gestionar proveedores y lotes de recepción con costos | No |
| CU05 | LB05 | Gestionar productos, variantes y maestros | No |
| CU06 | CU16 | Consultar catálogo de prendas | Sí |
| CU07 | CU17 | Consultar Kardex, existencias y valorización | No |
| CU08 | CU18 | Gestionar reservas de prendas | Sí |
| CU09 | LB09 | Solicitar, aprobar y recibir traslados | No |
| CU10 | LB10 | Preparar y atender reserva | No |
| CU11 | CU19 | Registrar venta presencial y pago en caja | No |
| CU12 | CU20 | Registrar devolución y merma | No |
| CU13 | LB13 | Consultar historial de compras | No |
| CU14 | CU21 | Gestionar carrito y confirmar compra digital | No |
| CU15 | CU22 | Procesar pago digital con Stripe Test | No |
| CU16 | LB16 | Configurar y simular delivery por anillos | No |
| CU17 | LB17 | Usar probador virtual móvil | No |
| CU18 | LB18 | Generar sugerencias IA para cliente | No |
| CU19 | CU23 | Consultar dashboard e indicadores | No |
| CU20 | LB20 | Buscar prendas por comando de voz | No |
| CU21 | CU24 | Solicitar reporte generativo por voz o texto | No |
| CU22 | LB22 | Gestionar promociones | No |
| CU23 | CU25 | Consultar ventas de la sucursal | No |
| CU24 | CU26 | Expirar reservas automáticamente | No |
| CU25 | LB25 | Consultar decisiones IA para inventario | No |
| CU26 | CU01 | Registrar empresa contratante | Sí |
| CU27 | CU02 | Administrar suscripción de empresa | Sí |
| CU28 | CU03 | Descargar catálogo para consulta offline | Sí |
| CU29 | CU04 | Registrar reserva offline | Sí |
| CU30 | CU05 | Sincronizar solicitud de compra digital | No |
| CU31 | CU06 | Habilitar turno y cupos de caja offline | No |
| CU32 | CU07 | Registrar y sincronizar venta de contado offline | No |
| CU33 | CU08 | Cambiar prenda y liquidar diferencia | No |
| CU34 | CU09 | Aplicar saldo personal a una compra | No |
| CU35 | CU10 | Consultar pronóstico de unidades vendidas | No |
| CU36 | CU11 | Consultar grupos de productos | No |
| CU37 | CU12 | Configurar tasa de conversión BOB/USD | No |

Solo se simplifican ahora los nombres de CU04, CU13, CU16 y CU18, todos incluidos en la primera presentación. No se reduce su alcance. El catálogo actual contiene doce casos nuevos (CU01–CU12) y catorce anteriores adaptados (CU13–CU26). Las fichas LB se encuentran en [funciones-conservadas.md](funciones-conservadas.md).
