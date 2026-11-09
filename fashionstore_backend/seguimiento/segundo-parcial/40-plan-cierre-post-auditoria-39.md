# Plan de corrección E2 posterior a la auditoría 39

**Fecha:** 06/11/2026 (Bolivia). **Estado:** encargo preparado; implementación pendiente. **Ramas existentes:** `feature/sp2-e2-integral` en `backend`, `frontend-web` y `app-movil`. **Dictamen vigente:** [auditoría independiente 39](39-auditoria-independiente-post-checkpoint-38.md). E2 sigue en avance sin aceptar.

## Objetivo y alcance

Cerrar los tres bloqueos P0 de CU19/CU22: (1) vencimiento sin liberación de stock cuando Stripe no confirmó cancelación, (2) recuperación real de caja tras F5 con DTO y líneas compatibles, y (3) validación financiera única antes de registrar captura. Conservar las reservas digitales y los cupos offline de CU06/CU07, la liquidación, Kardex e idempotencia existentes. No ampliar CU17/Decart, Flutter ni otros CU sin una regresión demostrada.

## R0 — Contrato común antes de editar consumidores

El coordinador y los tres subagentes acuerdan en un archivo de interfaz compartida los campos, estados, autorización y errores de `GET /api/v1/pagos/stripe/ordenes/activa-caja`. Fuente: `Venta`, `DetalleVenta`, `OrdenPago`, tasa congelada, turno y ficha CU19/CU22. La respuesta debe permitir liquidar una venta capturada tras recarga: `venta_id`, `orden_pago_id`, ID de PaymentIntent, `estado_orden`, importes/tasa congelados, sucursal, turno o procedencia de la venta y líneas persistidas. Si el esquema actual no guarda un dato, definir cómo recuperarlo del servidor; no fabricarlo en Angular. `client_secret` se entrega sólo cuando corresponde y jamás se persiste en el navegador. Un estado externo incierto no se presenta como capturado ni cancelado.

El contrato debe delimitar qué cajero/turno puede ver la orden, qué ocurre con más de una orden activa, qué panel muestra una venta de turno y una venta presencial/de reserva, y cómo se reintenta después de 502. Revisar la consistencia con `IniciarVentaPresencialStripeRespuestaDTO` y `VentaPresencialLiquidarDTO`; si el endpoint usa un DTO distinto, tiparlo como tal y convertirlo de forma explícita. Sincronizar OpenAPI y las fichas/API de los repositorios afectados cuando cambie el contrato.

## R1 — Vencimiento seguro y conciliación única

Una llamada fallida a `cancelar_intencion` deja `Venta`, `OrdenPago`, stock y Kardex sin cancelación/liberación; el worker registra la omisión y podrá reintentar. Un `CANCELED` verificado autoriza la liberación exactamente una vez. Si Stripe informa `SUCCEEDED`, validar ID, metadata de empresa/venta, moneda y centavos contra la orden antes de marcar `CAPTURADO`; jamás liberar por vencimiento. La consulta previa a una cancelación no basta para decidir: verificar el resultado de la operación de cancelación y contemplar una captura concurrente. No mantener locks SQL de inventario durante llamadas de red si puede evitarse sin perder idempotencia/serialización; documentar la solución elegida.

Extraer o reutilizar una validación compartida entre `confirmar_orden_pago`, lectura de recuperación y vencimiento. El procesamiento de un error en una venta del lote no debe cancelar ni saltarse silenciosamente las demás. No ocultar errores con `except Exception: pass`. Toda transición de inventario genera un Kardex único.

## R2 — Recuperación completa de caja Angular

La PWA consume el JSON real del endpoint, selecciona el panel correspondiente y repone `lineasVentaOffline` o `items` desde `DetalleVenta` de la venta persistida. Debe permitir continuar o cancelar una orden pendiente y liquidar una capturada tras F5 sin iniciar una segunda venta o PaymentIntent. El servidor revalida identidad, orden, líneas y estado al liquidar; el cliente no inventa monto, tasa ni artículos. Mostrar estado verificable y acción de reintento ante red/Stripe indisponibles. Probar ambos paneles y el caso de cambio de turno. Mantener navegación por rol, accesibilidad, responsive y diseño del skill `fashionstore-frontend-continuity`.

## R3 — Contraejemplos y verificación

Antes de cambiar producción, escribir y demostrar rojo para: fallo/timeout de `cancelar_intencion` tras consulta pendiente; captura concurrente durante cancelación; `SUCCEEDED` con ID, metadata, moneda o centavos ajenos en recuperación y vencimiento; fallo de consulta del proveedor; JSON exacto de recuperación contra el modelo del frontend; recarga antes/después de captura en ambas cajas; líneas y liquidación después de F5; acceso de otro tenant/cajero/turno; reintento sin duplicar stock, venta, pago ni Kardex. Corregir y demostrar verde. No usar en pruebas un mock más rico que la respuesta real del backend.

Ejecutar backend sobre una base PostgreSQL desechable cuyo nombre termine en `_test`, nunca sobre `fashionstore_db`; suite focalizada y `tests_segundo_parcial_bloque_b`. En Angular ejecutar `tsc`, Karma y build; si ChromeHeadless falla por entorno, diagnosticar el launcher y distinguir claramente prueba no ejecutada de prueba aprobada. Ejecutar `flutter analyze --no-pub` y pruebas focalizadas sólo si algún contrato móvil cambia; documentar el estado de las suites previas sin atribuirlas a este encargo. Comprobar `app.openapi()` frente al OpenAPI versionado, contratos compartidos, `git diff --check` en los tres repositorios, y ausencia de secretos. Stripe externo/FCM/Android físico se reportan por separado de dobles automatizados.

## Distribución y puerta de entrega

Tres subagentes más coordinador, con un solo dueño por archivo: A posee backend de producción de pagos/Stripe, DTO/router y worker; B posee componentes, servicios, modelos y pruebas Angular de caja; C posee un **archivo nuevo** de pruebas de contraejemplos backend y pruebas de contrato, sin editar archivos de A. El coordinador posee documentación, contrato compartido, OpenAPI y verificación integral. A y C acuerdan fixtures/dobles antes de escribir; B implementa contra el contrato R0. No ejecutar suites concurrentes contra la misma base `_test`.

El agente entrega un checkpoint con matriz P0-1/P0-2/P0-3, evidencia roja y verde, archivo/función, comandos y códigos de salida, ramas/HEAD/status, contrato JSON real, migraciones si las hay y limitaciones externas. Actualiza `README.md`, `02-estado-cu.md`, `04-bitacora.md` y `05-reanudacion.md` sin marcar E2 aceptada. **Sin commit, push, merge ni despliegue**: la revisión independiente posterior decide si procede cerrar y registrar commits.
