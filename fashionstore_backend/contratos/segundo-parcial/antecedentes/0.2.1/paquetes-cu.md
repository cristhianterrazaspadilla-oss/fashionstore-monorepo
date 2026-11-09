# Paquetes funcionales y casos de uso

**Revisión documental 0.2.1 — 25/10/2026.** Catálogo actual de 26, con ocho prioritarios. Fija un paquete dueño por caso; llamadas a otro paquete no cambian pertenencia. Ver [equivalencias-cu.md](equivalencias-cu.md), [casos-de-uso.md](casos-de-uso.md) y [trazabilidad-cu.md](trazabilidad-cu.md).

Las carpetas existentes se cotejaron por lectura con los tres proyectos el 24/10/2026; el resultado por CU está en [alineacion-codigo.md](alineacion-codigo.md). «Existente» describe el módulo, no certifica la nueva funcionalidad. Las rutas de pantallas nuevas son propuestas; no renombrar carpetas reales para igualarlas a grupos académicos.

## Catálogo completo y paquete dueño

| CU actual | Nombre | Paquete backend bajo `app/core/modules/` | Primera presentación |
|---|---|---|---|
| CU01 | Registrar empresa contratante | `identidad_empresas/` | Sí |
| CU02 | Administrar suscripción de empresa | `identidad_empresas/` | Sí |
| CU03 | Descargar catálogo para consulta offline | `catalogo/` | Sí |
| CU04 | Registrar reserva offline | `reservas_traslados/` | Sí |
| CU05 | Sincronizar solicitud de compra digital | `ventas_pagos/` | No |
| CU06 | Habilitar turno y cupos de caja offline | `caja_offline/` | No |
| CU07 | Registrar y sincronizar venta de contado offline | `caja_offline/` | No |
| CU08 | Cambiar prenda y liquidar diferencia | `posventa/` | No |
| CU09 | Aplicar saldo personal a una compra | `posventa/` | No |
| CU10 | Consultar pronóstico de unidades vendidas | `analitica/` | No |
| CU11 | Consultar grupos de productos | `analitica/` | No |
| CU12 | Configurar tasa de conversión BOB/USD | `organizacion/` | No |
| CU13 | Registrarse e iniciar sesión por empresa | `identidad_empresas/` | Sí |
| CU14 | Gestionar usuarios y roles de la empresa | `identidad_empresas/` | No |
| CU15 | Gestionar ciudades, sucursales y tarifas | `organizacion/` | Sí |
| CU16 | Consultar catálogo de prendas | `catalogo/` | Sí |
| CU17 | Consultar Kardex, existencias y valorización | `inventario/` | No |
| CU18 | Gestionar reservas de prendas | `reservas_traslados/` | Sí |
| CU19 | Registrar venta presencial y pago en caja | `ventas_pagos/` | No |
| CU20 | Registrar devolución y merma | `posventa/` | No |
| CU21 | Gestionar carrito y confirmar compra digital | `ventas_pagos/` | No |
| CU22 | Procesar pago digital con Stripe Test | `ventas_pagos/` | No |
| CU23 | Consultar dashboard e indicadores | `analitica/` | No |
| CU24 | Solicitar reporte generativo por voz o texto | `analitica/` | No |
| CU25 | Consultar ventas de la sucursal | `analitica/` | No |
| CU26 | Expirar reservas automáticamente | `reservas_traslados/` | No |

## Grupos académicos y plataformas


Los grupos del documento académico reúnen casos relacionados y pueden abarcar varias carpetas reales. No implican mover ni renombrar módulos del proyecto.

| Grupo académico | Casos de esta presentación | Casos del catálogo completo que completan el grupo | Paquetes reales relacionados |
|---|---|---|---|
| Identidad, organización y SaaS | CU01, CU02, CU13, CU15 | CU12, CU14 | `identidad_empresas`, `organizacion` |
| Catálogo e inventario | CU03, CU16 | CU17 | `catalogo`, `inventario` |
| Reservas y sincronización | CU04, CU18 | CU26 | `reservas_traslados` |

Los casos adicionales de la tercera columna permiten entender la agrupación completa; no se incluyen como entregables de esta presentación. El criterio heredado de un mínimo de tres casos se aplica al grupo académico completo, no a cada carpeta técnica ni al subconjunto presentado. La sincronización también sirve a ventas en presentaciones posteriores.

## 3. Correspondencia por plataforma

| CU | Angular: `src/app/features/` | Flutter: `lib/features/` | Alcance por canal |
|---|---|---|---|
| CU01 | `identidad_empresas/empresas/` — pantalla propuesta | Adaptar `identidad_empresas/auth/` para usar el contexto de empresa | Alta administrativa online en web; móvil consume el contexto empresarial, sin pantalla de alta de empresas. |
| CU02 | `identidad_empresas/planes/` — pantalla propuesta | Adaptar sesión/cuenta para consultar capacidades y aplicar restricciones pertinentes | Administración online en web; backend aplica vigencia, límites y permisos también a peticiones móviles. |
| CU03 | `catalogo/catalogo/`; servicios/modelos de `catalogo` | `catalogo/catalogo/`; servicios/modelos de `catalogo` | Descarga online y almacenamiento persistente para consulta posterior sin red en ambas aplicaciones. |
| CU04 | `reservas_traslados/reservas/`; servicios/modelos del paquete | `reservas_traslados/reservas/`; servicios/modelos del paquete | Registro offline, pendientes, sincronización y consulta durable del resultado en ambas aplicaciones. |
| CU13 | `identidad_empresas/auth/`; servicios/modelos del paquete | `identidad_empresas/auth/`; servicios/modelos del paquete | Registro de clientes y autenticación online por empresa; protección de datos privados locales. |
| CU15 | `organizacion/sucursales/`; servicios/modelos del paquete | Servicios/modelos de `organizacion` y selección de sucursal donde corresponda | Administración online en web; consulta/selección de sucursales autorizadas en móvil. |
| CU16 | `catalogo/catalogo/`; servicios/modelos de `catalogo` | `catalogo/catalogo/`; servicios/modelos de `catalogo` | Consulta online u offline de la copia descargada, filtros, variantes y disponibilidad conocida. |
| CU18 | `reservas_traslados/reservas/`; servicios/modelos del paquete | `reservas_traslados/reservas/`; servicios/modelos del paquete | Creación, consulta y cancelación central online. La creación offline corresponde a CU04. |

La consulta de información descargada no confirma una reserva ni garantiza stock. Una solicitud de CU04 pasa a ser reserva central únicamente tras la aceptación del backend. La cancelación central de CU18 requiere conexión y confirmación del servidor.

## 4. Responsabilidades compartidas

- **Backend:** `identidad_empresas` gestiona empresa, suscripción e identidad; `organizacion`, sucursales y tarifas; `catalogo`, consulta y descarga; `reservas_traslados`, reglas de reservas. `inventario` conserva la propiedad de existencias, bloqueos y Kardex, aunque CU17 no sea entregable completo de esta presentación.
- **Angular/PWA:** IndexedDB conserva el catálogo descargado, reservas locales, pendientes y resultados; Service Worker y Web App Manifest permiten instalación y apertura de las funciones offline. Los componentes compartidos permanecen en `src/app/core/` cuando sirven a varios paquetes.
- **Flutter:** SQLite conserva datos de operación y resultados. `lib/core/` concentra red, sesión y mecanismos reutilizables; los servicios de negocio permanecen en su paquete dueño. El catálogo y las reservas no deben depender únicamente de memoria o de preferencias de sesión.
- **Sincronización:** un adaptador común transporta operaciones; las reglas de identidad, stock y reserva se resuelven en sus servicios dueños. Reutilizar identificadores estables, conservar resultados y reintentar sin duplicar efectos.
- **Integración:** coordinar montaje de rutas, registro de modelos y migraciones. Revisar especialmente `app/api/v1/api.py`, `app/db/modelos.py`, dependencias de autenticación, rutas/configuración web y cliente API/sesión móvil. Esos archivos son puntos de coordinación, no módulos que ambos deban modificar simultáneamente.

## 5. Distribución propuesta para trabajar en paralelo

| Bloque | Casos | Responsabilidad principal | Coordinación necesaria |
|---|---|---|---|
| A | CU01, CU02, CU13, CU15 | Empresa, planes, sesión, permisos y sucursales; integración de migraciones y contexto de empresa. | Publicar primero el contrato mínimo de identidad/empresa/sucursal que consumirá el bloque B. |
| B | CU03, CU04, CU16, CU18 | Catálogo, persistencia offline, reservas, pendientes y sincronización; integración con inventario. | Consumir el contrato acordado y coordinar los cambios comunes de red, sesión, rutas y migraciones. |

La asignación personal queda pendiente. Los bloques reducen cruces de archivos, pero comparten dependencias. Antes de desarrollar en paralelo, acordar identificadores, permisos, errores y estructura mínima de los mensajes. No duplicar DTO o reglas para evitar esa coordinación.

## Referencia de carpetas del mapa anterior

Cotejar con el código actual antes de editar; los directorios «previstos» no se consideran creados.

### Ruta visual de Angular

| Paquete | Carpetas actuales bajo `src/app/features/<paquete>/` |
|---|---|
| `identidad_empresas` | `auth/`, `usuarios/`, `services/`, `models/` |
| `organizacion` | `sucursales/`, `services/`, `models/` |
| `catalogo` | `catalogo/`, `productos/`, `promociones/`, `services/`, `models/` |
| `inventario` | `inventario/`, `recepciones/`, `services/`, `models/` |
| `reservas_traslados` | `reservas/`, `traslados/`, `services/`, `models/` |
| `ventas_pagos` | `caja/` (CU19 online), `carrito/`, `checkout/`, `pago/`, `pedidos/`, `mis-pedidos/`, `historial/`, `services/`, `models/` |
| `caja_offline` | Previsto para CU06, CU07; sin carpeta de implementación. |
| `posventa` | `operaciones/`, `services/`, `models/` |
| `experiencia_cliente` | `landing/`, `services/`, `models/` |
| `analitica` | `dashboard/`, `inteligencia/`, `services/`, `models/` |

`operaciones/` reúne la interfaz de reporte de ventas, devolución y merma; consume los servicios dueños de `analitica`, `ventas_pagos` y `posventa`. La ruta pública y sus permisos se revisan en `app.routes.ts`; la renumeración documental no exige cambiar URLs.

### Ruta visual de Flutter: funciones existentes y ampliaciones previstas

| Paquete | Carpetas actuales bajo `lib/features/<paquete>/` |
|---|---|
| `identidad_empresas` | `auth/`, `cuenta/`, `services/`, `models/` |
| `organizacion` | `services/`, `models/` para consulta de sucursales; sin pantalla administrativa. |
| `catalogo` | `catalogo/`, `services/`, `models/` |
| `reservas_traslados` | `reservas/`, `services/`, `models/` |
| `ventas_pagos` | `carrito/`, `checkout/`, `pago/`, `pedidos/`, `historial/`, `services/`, `models/` |
| `experiencia_cliente` | `home/`, `busqueda/`, `recomendaciones/`, `probador/`, `services/`, `models/` |
| `posventa` | Previsto para CU09: saldo del cliente y su uso online; sin carpeta móvil actual. CU08 se tramita en web. |

La administración general de `inventario` y `analitica` continúa en web. `caja_offline` debe incorporarse a Flutter para CU06 y CU07. `posventa` conserva la parte cliente de CU09; cambios se tramitan en web online. La pantalla de catálogo puede consumir IA del paquete `experiencia_cliente` y la selección de sucursal del paquete `organizacion`, manteniendo un único dueño por servicio y DTO.

## Próximas presentaciones y funciones conservadas

`caja_offline` es nuevo como paquete de negocio previsto para CU06 y CU07, en backend y clientes PWA/Flutter (`turnos/`, `ventas/`, servicios/modelos según necesidad). Ya no queda excluido de móvil. `posventa` se amplía para CU08/CU09; `analitica`, para CU10/CU11 y reportes; `organizacion`, para CU12. Esas capacidades no se implementan automáticamente en la primera presentación.

Los otros grupos académicos son: Ventas, pagos y caja offline (CU05, CU06, CU07, CU19, CU21, CU22); Posventa y saldo (CU08, CU09, CU20); Reportes y analítica (CU10, CU11, CU23, CU24, CU25). El mínimo heredado de tres casos se entiende por grupo académico completo, no por carpeta técnica ni por cada presentación.

Las funciones LB de [funciones-conservadas.md](funciones-conservadas.md) mantienen sus dueños: LB04 inventario; LB05/LB22 catálogo; LB09/LB10 reservas_traslados; LB13/LB16 ventas_pagos; LB17/LB18/LB20 experiencia_cliente; LB25 analitica. No son once casos nuevos ni se suman a los 26 prioritarios.

`inventario` posee existencias/Kardex; `catalogo` productos/variantes/precios; `organizacion` sucursales/tarifas. Reservas, ventas, caja y posventa consumen esas capacidades sin duplicarlas. La sincronización transversal solo transporta/despacha; sesión, reloj, persistencia reutilizable y registro de modelos permanecen en infraestructura cuando sirven a varios paquetes. Reutilizar servicios y DTO, no crear archivos vacíos por plantilla.

Aclaración aprobada el 25/10/2026: `organizacion` conserva ciudades como referencia global administrada por plataforma; CU15 permite a la empresa consultarlas/seleccionarlas y administrar solo sus sucursales/tarifas. No surge otro CU prioritario. El enlace público `/tienda/{empresa_codigo}` es una ruta de navegación propuesta que lleva contexto empresarial a `catalogo` y `identidad_empresas`; no es un endpoint API ni un permiso. La ventana privada local de 8 h pertenece a la experiencia de cliente y sesión, sin acortar por ello el JWT actual de 24 h. El origen de vencimiento de reserva se resuelve en `reservas_traslados` junto con adelantos y expiración, sin duplicar reglas en sincronización.

## Ubicaciones propuestas conservadas para los doce nuevos


La tabla conserva las ubicaciones propuestas para los doce casos nuevos; cotejar con el checkout antes de crear carpetas. Los cuatro primeros son prioritarios actuales; los demás son contexto posterior. Dentro del paquete backend se reutilizan `routers/`, `services/`, `repositories/`, `schemas.py` y `models.py` según la necesidad real; una operación no exige crear cinco archivos vacíos. En Angular y Flutter, la pantalla queda en la subcarpeta indicada y sus servicios/modelos en `services/` y `models/` del mismo paquete. Los nombres nuevos de funciones y métodos siguen el patrón español acordado.

| CU | Backend: `app/core/modules/` | Angular: `src/app/features/` | Flutter: `lib/features/` |
|---|---|---|---|
| CU01 Registrar empresa | `identidad_empresas/` | `identidad_empresas/empresas/` | Sin alta de empresa; adaptar `identidad_empresas/auth/` al contexto de empresa. |
| CU02 Administrar suscripción | `identidad_empresas/` | `identidad_empresas/planes/` | Sin administración; mostrar capacidad de la empresa en sesión/cuenta si corresponde. |
| CU03 Descargar catálogo | `catalogo/` | `catalogo/catalogo/` | `catalogo/catalogo/` |
| CU04 Registrar reserva offline | `reservas_traslados/` | `reservas_traslados/reservas/` | `reservas_traslados/reservas/` |
| CU05 Sincronizar compra | `ventas_pagos/` | `ventas_pagos/carrito/`, `checkout/` y `mis-pedidos/` | `ventas_pagos/carrito/`, `checkout/` y `pedidos/` |
| CU06 Habilitar caja offline | `caja_offline/` (nuevo paquete) | `caja_offline/turnos/` | `caja_offline/turnos/` (previsto; personal autorizado) |
| CU07 Venta de contado offline | `caja_offline/` | `caja_offline/ventas/` | `caja_offline/ventas/` (previsto; SQLite) |
| CU08 Cambio de prenda | `posventa/` | `posventa/cambios/` | Fuera de alcance; trámite web online. |
| CU09 Aplicar saldo | `posventa/` | `posventa/saldo/`; checkout consume su servicio | `posventa/saldo/` (nuevo paquete); checkout consume su servicio |
| CU10 Pronóstico supervisado | `analitica/` | `analitica/pronosticos/` | Fuera de alcance. |
| CU11 Grupos no supervisados | `analitica/` | `analitica/grupos/` | Fuera de alcance. |
| CU12 Tasa BOB/USD | `organizacion/` | `organizacion/tasa/` | Sin configuración; checkout muestra la conversión devuelta por backend. |
