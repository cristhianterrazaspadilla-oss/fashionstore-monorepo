# Trazabilidad de casos de uso — primera presentación

**Fecha de actualización:** 25/10/2026; fecha original de fichas: 24/10/2026.<br>
**Responsable de actualización:**<br>
**Alcance detallado:** ocho casos de la primera presentación; se conserva también un mapa general de los otros dieciocho.<br>
**Condición de la evidencia:** planificación documental apoyada en la auditoría estática aportada; no equivale a pruebas ejecutadas ni a cumplimiento demostrado.

[paquetes-cu.md](paquetes-cu.md) establece el paquete principal y la correspondencia entre repositorios. Este archivo identifica origen, cambios, dependencias y verificaciones previstas; no reemplaza las fichas de especificación ni los contratos API.

**B:** backend FastAPI/PostgreSQL. **W:** Angular/PWA. **M:** Flutter/SQLite. Los códigos de las tablas corresponden al catálogo actual de 26; la numeración anterior se identifica expresamente.

## 1. Correspondencia de numeración y tipo de trabajo

| CU actual | Nombre actual | Código anterior | Clasificación |
|---|---|---|---|
| CU01 | Registrar empresa contratante | CU26 | Nuevo del segundo parcial. |
| CU02 | Administrar suscripción de empresa | CU27 | Nuevo del segundo parcial. |
| CU03 | Descargar catálogo para consulta offline | CU28 | Nuevo del segundo parcial. |
| CU04 | Registrar reserva offline | CU29 | Nuevo del segundo parcial; el nombre explicita el registro local ya contemplado en el proceso. |
| CU13 | Registrarse e iniciar sesión por empresa | CU01 | Anterior adaptado al modelo multitenant. |
| CU15 | Gestionar ciudades, sucursales y tarifas | CU03 | Anterior adaptado a empresa, plan y sucursales. |
| CU16 | Consultar catálogo de prendas | CU06 | Anterior adaptado a empresa y consulta offline. |
| CU18 | Gestionar reservas de prendas | CU08 | Anterior adaptado e integrado con solicitudes offline. |

Esta presentación comprende cuatro nuevos y cuatro anteriores adaptados. En el catálogo completo se acordaron doce nuevos y catorce anteriores adaptados. No mezclar estos códigos con referencias antiguas todavía presentes en contratos o código.

## 2. Casos nuevos: alcance y salida verificable

| CU | Alcance acordado | Paquete dueño / componentes | Verificación prevista |
|---|---|---|---|
| CU01 | Administrador de plataforma registra empresa y administrador inicial. Validar datos y unicidad; guardar ambos consistentemente. Un alta sin plan habilitado no concede automáticamente operaciones comerciales. | `identidad_empresas`; B y W. M consume posteriormente el contexto empresarial. | Registrar dos empresas independientes; comprobar identidad y administrador de cada una; rechazar lecturas/escrituras cruzadas; verificar que un fallo no deje un alta parcial. |
| CU02 | Administrador de plataforma asigna, renueva o cambia plan y fechas; administrador de empresa consulta su plan. Límites configurables: Básico 2 sucursales activas y Profesional 10. Gracia de 3 días y restricciones posteriores según las reglas acordadas. No requiere cobro recurrente real. | `identidad_empresas`; B y W. Las restricciones afectan también a peticiones M. | Probar límites, fechas inválidas, cambio/reducción de plan y falta de permisos; después de la gracia bloquear nuevas operaciones restringidas y permitir posventa válida/cierre de compromisos previos. Un fallo conserva la suscripción anterior. |
| CU03 | Descargar un subconjunto público por empresa identificada mediante enlace de navegación propuesto `/tienda/{empresa_codigo}`: productos, variantes, precios, tallas, colores, disponibilidad pública conocida y fecha/versión. Datos restringidos exigen permiso; persistir en IndexedDB y SQLite. La copia informa antigüedad y no garantiza stock. | `catalogo`; B, W y M. | Descargar, cerrar y reabrir sin red en PWA y Flutter; consultar datos y fecha. Probar error de almacenamiento, descarga interrumpida y separación por empresa; conservar la copia válida anterior ante fallo. |
| CU04 | Crear reserva local con identificador estable, empresa, sucursal, prendas, cantidades, visita y fecha local original; mostrar pendiente y conservarla tras reinicio. Al reconectar, autenticar y validar centralmente plan, pertenencia, reloj y stock; solicitud llegada vencida se rechaza sin apartado. Resultado aceptado/rechazado/CONFLICTO durable; 24 h desde origen local y 72 h desde el mismo origen solo con adelanto online oportuno. | `reservas_traslados`; B, W y M; usa existencias de `inventario` y regla compartida con CU18. | Crear offline y reiniciar; sincronizar; repetir identificador sin duplicar. Probar visita distinta de origen, stock insuficiente, vencimiento, empresa ajena y TIEMPO_INCOHERENTE; conservar pendiente ante fallo de red y resultado definitivo. |

## 3. Casos anteriores: qué se conserva y qué se modifica

| CU | Base existente según auditoría estática | Adaptación de esta presentación | Paquete / componentes | Verificación prevista |
|---|---|---|---|---|
| CU13 | Registro/autenticación y controles por rol. | Conservar el contexto empresarial desde enlace público a registro/login sin reutilizar sesión de otra empresa; backend valida pertenencia y recursos. Registro público solo de clientes; personal requiere creación autorizada; plataforma tiene ámbito explícito. Datos privados offline visibles 8 h desde último login online; al vencer/logout ocultar, conservar aislados pendientes y resultados, y reautenticar. Ventana local independiente de JWT actual de 24 h; no autoriza sincronizar con token vencido. | `identidad_empresas`; B, W, M. Relación: CU01–CU02. | Login correcto/incorrecto, usuario inactivo, empresa no autorizada y roles; acceso cruzado rechazado en backend. Probar cambio de enlace con sesión ajena, 8 h/logout, catálogo público aún visible y reautenticación antes de sincronizar. |
| CU15 | Ciudades, sucursales y tarifas existentes sin ámbito empresarial completo. | Ciudades: catálogo global administrado solo por plataforma; empresa consulta/selecciona. Sucursales y tarifas: propias de cada empresa, con permisos, plan y control de compromisos al desactivar. La administración global es capacidad relacionada sin nuevo CU prioritario. | `organizacion`; B y W; M consulta. Relación: CU01–CU02. | Dos empresas comparten ciudad sin compartir sucursales/tarifas; administrador empresarial no modifica ciudad global; límites 2/10, activación/desactivación y rechazo de modificaciones ajenas. |
| CU16 | Catálogo, filtros, detalle de variantes y disponibilidad. | Restringir a empresa y sucursal; resolver consulta online o desde la descarga de CU03. Mostrar fuente/fecha, aviso de antigüedad y disponibilidad conocida; los filtros offline se limitan al subconjunto descargado. Consultar no reserva ni descuenta stock. | `catalogo`; B, W, M. Relación: CU03. | Misma búsqueda con y sin red; filtros, variantes y sin resultados; ausencia de copia local; caída de red con alternativa local identificada; ninguna consulta altera existencias. |
| CU18 | Creación, cancelación y expiración de reservas centrales; `ReservaService.crear` usa actualmente visita +1 día si recibe visita. | Conservar creación/consulta/cancelación online propias, aisladas por empresa, e incluir offline solo tras aceptación CU04. Online: creación central +24 h; offline aceptada: creación local original +24 h; adelanto confirmado online antes de vencer: +72 h desde el mismo origen, no adicionales. Fecha de visita y reintentos no lo sustituyen; cancelar/expirar libera existencias una vez. | `reservas_traslados`; B, W, M; usa `inventario`, adelantos y actual CU26 de expiración. | Probar visita distinta del origen, solicitud offline vencida, adelanto dentro/fuera de plazo, cancelación doble, job de expiración y fechas presentadas en ambos clientes; no recalcular historial en esta aclaración. |

La capacidad existente indicada en la segunda columna procede de una revisión estática aportada por el equipo. No certifica ejecución correcta ni adaptación multitenant. Las integraciones con adelantos y expiración se verifican al conectar estos casos con sus servicios existentes; no convierten automáticamente esos otros casos en entregables completos de esta presentación.

## 4. Correspondencia con requisitos y pautas del examen

Los códigos RF-SP corresponden al catálogo de requisitos acordado para el documento nuevo. Los RNF01–RNF12 corresponden al enunciado del examen.

| Exigencia / requisito | Casos de esta presentación | Resultado esperado y límite de cobertura |
|---|---|---|
| Examen §§9.1–9.3 y 9.6; RF-SP-01: empresas e identidad | CU01, CU13, CU15; controles transversales en los ocho | Dos empresas en PostgreSQL compartido, aislamiento lógico aplicado en backend, pertenencia de recursos y autorización. Una sucursal no es un tenant. |
| Examen §§9.4–9.5; RF-SP-02: planes y suscripciones | CU02, CU15; restricciones consumidas por los demás | Planes, fechas, límites configurables y permisos efectivos. Mostrar el plan en pantalla no sustituye los controles del backend. |
| Examen §§5.2–5.3 y 6.2–6.3; RF-SP-03: catálogo offline | CU03, CU16 | Productos/variantes y disponibilidad conocida persistidos en IndexedDB/SQLite; consulta sin red y tras reinicio, con fecha y advertencia. |
| Examen §§5.3–5.4 y 6.2–6.4; RF-SP-04: reservas offline | CU04, CU18 | Registro local y detalles, pendientes y resultados; aceptación central con stock; no duplicar ni borrar operaciones por el mero intento de envío. |
| Examen §§5.4 y 6.4; RF-SP-11 y RF-SP-12: sincronización y conflictos | CU04; apoyo de CU03, CU13, CU15 y CU18 | Identificadores estables, empresa/sucursal, reintentos, autorización y resultado durable. Esta entrega cubre el flujo de reservas, no toda la sincronización de ventas. |
| Examen §§5.1–5.2 y §11; RF-SP-14: PWA | CU03, CU04, CU16 y soporte técnico compartido | Manifest, Service Worker y recursos necesarios para instalar y abrir las funciones offline. No se presume existente por usar Angular. |
| RNF01–RNF02 | Los ocho, según operación y rol | Autenticación, autorización y aislamiento, incluidas consultas por ID, cachés y sincronización. |
| RNF03, RNF05, RNF06 y RNF10 | Principalmente CU03–CU04 y CU16–CU18 | Persistencia tras reinicio, idempotencia, recuperación y registros diagnósticos sin datos sensibles innecesarios. |
| RNF04 | CU01, CU02, CU04, CU15 y CU18, según operación | Cambios consistentes; en reservas, stock y movimientos atómicos sin efectos parciales. La integridad de ventas se completa en entregas posteriores. |
| RNF07–RNF09, RNF11–RNF12 | Los ocho y sus componentes | Separación de responsabilidades, compatibilidad, consultas justificadas, pruebas críticas y coherencia entre requisitos, fichas, UML, código y evidencia. |

## 5. Contratos mínimos que deben quedar alineados

| Área | Acuerdo mínimo para implementar e integrar |
|---|---|
| Identidad y empresa | Enlace público de navegación propuesto `/tienda/{empresa_codigo}` identifica catálogo y conserva contexto hacia registro/login; no da autorización. Backend valida pertenencia, rol y recursos; cambio de empresa requiere validación explícita, sin reutilizar sesión ajena. Ventana privada offline de 8 h desde login online independiente del JWT de 24 h y del turno de caja. |
| Suscripción y sucursales | Plan, fechas, capacidades, límites 2/10, errores y reglas ante reducción/vencimiento. Ciudades globales administradas por plataforma; empresa solo consulta/selecciona, y administra sucursales/tarifas propias. Si se confirman tres sucursales activas heredadas, asignar Profesional administrativamente con fechas explícitas. |
| Descarga | Ámbito de empresa/sucursal, versión/fecha y contenido mínimo de productos, variantes, precios y existencias conocidas. Persistir de forma consistente y distinguir datos públicos y privados. |
| Reserva local | Identificador único estable; empresa, sucursal, responsable, fecha de creación, detalle de variantes/cantidades y datos de visita. No generar un ID diferente en cada reintento. |
| Resultado de sincronización | Correlación con la operación local, resultado durable, identificador central cuando exista y motivo legible de rechazo/conflicto. La pérdida de respuesta requiere reconciliación, no recreación de la reserva. |
| Reserva central | Propiedad, estado, fechas, stock y movimientos; aceptación, consulta y cancelación autorizadas. Online +24 h desde creación central; offline aceptada +24 h desde creación local original; adelanto oportuno hasta +72 h desde el mismo origen. Revisar creación, pago de adelanto, cancelación, expiración y presentación de fechas. El transporte compartido no duplica estas reglas. |

Son acuerdos de contenido, no nuevos endpoints ni nombres definitivos de campos o estados. Revisar los contratos existentes antes de fijar el esquema. La numeración actual no autoriza declarar implementado `interfaz.json` ni ninguna ruta propuesta de la revisión `0.2.0`; ver [alineacion-codigo.md](alineacion-codigo.md).

## 6. Dependencias, límites y conservación del proyecto

1. Acordar el contexto de identidad/empresa/sucursal y coordinar migraciones antes de integrar el trabajo paralelo. CU01, CU02, CU13 y CU15 habilitan el aislamiento que consumen catálogo y reservas.
2. CU03 aporta los datos locales que consulta CU16 y utiliza CU04. La descarga se hace con conexión; consulta y registro local continúan sin red dentro de las autorizaciones aplicables.
3. CU04 utiliza las reglas centrales de CU18 y de inventario. El stock conocido local no garantiza aceptación. Tras aceptar, consultar/cancelar mediante CU18; expirar mediante el servicio del actual CU26.
4. No se agregan como casos completos de esta presentación los otros 18 del catálogo. Puede haber cambios de soporte en sus módulos, por ejemplo identidad, inventario o expiración, sin declarar terminado su alcance completo.
5. Se conservan las funcionalidades del primer parcial aunque no todas sean casos prioritarios del documento nuevo. El retiro de una fila de este mapa no ordena borrar código.

**Obligación de Flutter corregida:** el examen exige venta de contado offline en web y Flutter. La decisión antigua que excluía caja móvil queda sustituida por la aclaración posterior del equipo con la docente. Los actuales CU06 (habilitar turno y cupos) y CU07 (registrar y sincronizar venta de contado offline), antiguos CU31–CU32, deben cubrir esa operación en la planificación posterior. No están incluidos en estos ocho y, por tanto, esta primera presentación no demuestra por sí sola el cumplimiento completo de ventas offline. Una compra digital diferida no equivale a venta de contado móvil.

Reportes generativos, modelos ML, cambios de prendas, saldo, pagos digitales y conversión monetaria conservan su alcance en el catálogo de 26 y se detallarán en las presentaciones correspondientes. El despliegue externo y la documentación ICONIX exigidos por el examen siguen siendo obligaciones globales del proyecto.

## 7. Evidencia pendiente y uso de este archivo

Todas las verificaciones de este documento son **previstas**. Durante la implementación, registrar por caso la ruta real de pruebas, comando/entorno, resultado, fecha y evidencia pertinente. No marcar como ejecutada una prueba por disponer de una ficha, carpeta o captura documental.

Esta revisión integra el alcance detallado de la primera presentación y conserva el mapa global del catálogo. Conservar el historial de los 37 códigos y actualizar referencias cruzadas por equivalencia; no interpretar la renumeración como eliminación de funcionalidades. Las fichas completas de los ocho casos se mantienen por separado, con sus autores vacíos y fecha 24/10/2026 conforme a lo acordado.

## 8. Mapa general de los otros dieciocho casos

Estas filas conservan contexto para futuras presentaciones y regresión. No declaran implementación ni asignan aún su reparto. Sus fichas heredadas se mantienen en casos-de-uso.md; los detalles pendientes se revisarán antes de implementar cada bloque.

| CU | Paquete dueño | Alcance conservado / por completar |
|---|---|---|
| CU05 | `ventas_pagos` | Solicitud digital diferida: stock/precio central, aceptación de cambio de importe, apartado 60 min y pago explícito online. |
| CU06 | `caja_offline` | Turno y cupos exclusivos por variante/dispositivo; habilitación de 8 h y precios congelados en PWA y Flutter. |
| CU07 | `caja_offline` | Efectivo y entrega local, venta/detalle durables, sincronización sin doble descuento y recuperación auditada en PWA y Flutter. |
| CU08 | `posventa` | Cambio dentro de plazo, valor neto original, reemplazo a precio vigente, diferencia pagada/saldo y caso sin diferencia. |
| CU09 | `posventa` | Saldo personal por empresa, uso parcial online, sin vencimiento/transferencia/efectivo y sin doble gasto. |
| CU10 | `analitica` | Modelo supervisado entrenado, datos sintéticos versionados, evaluación e inferencia por empresa. |
| CU11 | `analitica` | Modelo no supervisado entrenado, agrupaciones interpretables, métricas y datos insuficientes. |
| CU12 | `organizacion` | Tasa BOB/USD positiva, global, versionada y vigente; conversión decimal congelada por intención. |
| CU14 | `identidad_empresas` | Usuarios y roles dentro de empresa; superadministración separada y autorizaciones de personal. |
| CU17 | `inventario` | Stock libre/reservado/comprometido sin duplicación; Kardex y valoración por empresa. |
| CU19 | `ventas_pagos` | Conservar venta online y pago en caja; integración coherente con nuevos flujos físicos. |
| CU20 | `posventa` | Devolución/merma con cantidades autorizadas y stock consistente; relación con cambio y saldo. |
| CU21 | `ventas_pagos` | Compra web/móvil, revalidación de precio/stock, solicitud diferida y saldo online. |
| CU22 | `ventas_pagos` | Stripe Test web/móvil: BOB comercial a USD aceptado, webhook/reconciliación e incertidumbre de pago. |
| CU23 | `analitica` | Indicadores reales por empresa y periodos; separar métricas convencionales de ML Profesional. |
| CU24 | `analitica` | Cuatro reportes reales con filtros variables, consultas controladas, texto/voz y exportación Excel/PDF; CSV adicional. |
| CU25 | `analitica` | Ventas centrales por sucursal; fecha central por defecto y fecha física visible/filtrable. |
| CU26 | `reservas_traslados` | Expiración idempotente de reservas aceptadas; respetar origen temporal y conciliación de adelantos/pagos. |

El catálogo completo, los códigos LB y sus equivalencias están en [equivalencias-cu.md](equivalencias-cu.md). Las verificaciones previstas para los ocho se ejecutan primero; regresión de funciones previas según el código afectado.
