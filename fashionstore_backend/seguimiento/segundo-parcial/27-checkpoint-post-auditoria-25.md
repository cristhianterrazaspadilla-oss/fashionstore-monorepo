# Checkpoint técnico posterior a la Auditoría Independiente 25

**Fecha de corte:** 05/11/2026.  
**Contrato:** Versión 0.3.2 / Protocolo 0.4.0.  
**Ramas activas:** `feature/sp2-e2-integral` en `backend`, `frontend-web` y `app-movil`.  
**Hashes de partida:** `backend` (`986bac5`), `frontend-web` (`9992cdc`), `app-movil` (`7880a15`).  
**Estado de la Entrega 2:** **Avance sin aceptar** (0 CU aceptados formalmente; CU05 y CU22 en *Observado P0 — resuelto en código*, CU19 en *Observado P1 — resuelto en código*).  
**Disciplina Git estricta:** Todos los cambios permanecen desestibados en el árbol de trabajo (*working tree*). **Cero commits nuevos, cero push, cero merge y cero despliegues**.

---

## 1. Arquitectura de ejecución paralela y propiedad de archivos

Para dar cumplimiento exhaustivo a las puertas D1–D5 del [plan definitivo 26](26-plan-definitivo-cierre-e2.md) y al [encargo E2](prompts/E2-cierre-definitivo-auditoria-25-subagentes.md), se organizó un esquema de coordinación central con tres subagentes especializados, con propiedad exclusiva de archivos y contratos de interfaz acordados previamente:

| Responsable | Ámbito y propiedad exclusiva de archivos | Tareas asignadas |
|---|---|---|
| **Subagente A**<br>*(Backend Stripe y Caja)* | `stripe_gateway.py`, `stripe_service.py`, `venta_presencial_service.py`, `test_contraejemplos_p0_pagos.py`, `test_contraejemplos_p0_caja_posventa.py`, `test_cu19_caja_liquidacion.py`, `test_b1_finanzas_cu09_cu22_cu27.py`. | **D2 Backend:** Validación estricta de Customer y pertenencia de PaymentMethod (sin sentinela `cus_ajeno`).<br>**D4 Caja CU19:** Eliminación de intención ajena sin OrdenPago interna, centavos exactos, bloqueo concurrente de variantes. |
| **Subagente B**<br>*(Angular / PWA)* | `frontend-web/src/app/features/ventas_pagos/checkout/*`, `stripe.service.ts`, `web-push.service.ts`, componentes y specs correspondientes. | **D1 PWA:** Omisión de `autorizacion_cobro` cuando `permiteCobro === false`.<br>**D2 PWA:** Eliminación de `pm_card_visa`, integración SetupIntent Stripe.js, revalidación de `localStorage`.<br>**D3 Web Push:** Servicio de suscripción y revocación con Push API. |
| **Subagente C**<br>*(App Móvil Flutter)* | `app-movil/lib/features/ventas_pagos/*`, `notificacion_movil_service.dart`, specs de widget y unitarias. | **D1 Flutter:** Omisión de `autorizacion_cobro` cuando no hay método o tasa oficial.<br>**D2 Flutter:** `setupIntentClientSecret` en PaymentSheet, eliminación de silenciamiento de errores y fallback ficticio.<br>**D3 Flutter:** Soporte de token FCM.<br>**Diagnóstico:** Investigación reproducible de `flutter test` y `analyze`. |
| **Coordinador**<br>*(Contratos, Core, Sincronización, Worker)* | `vector_huella_canonica_v3.json`, `schemas_sincronizacion.py`, `sincronizacion_service.py`, `notificacion_service.py`, `tareas.py`, `openapi-segundo-parcial.json`, `test_notificaciones_outbox_e2.py`, `test_b2_compras_cu21_cu19_cu05.py`. | **D1 Contrato:** Fixture canónico v3, validación estricta 15 campos (`extra="forbid"`), HTTP 422 ante objeto parcial, omisión legal.<br>**D3 Avisos:** Peticiones HTTP reales en adaptadores FCM/WebPush, reintentos aislados por destino, scheduler en APScheduler.<br>**D5:** Integración, pruebas globales, OpenAPI, bitácora y seguimiento. |

---

## 2. Matriz de resolución de los seis bloqueos de la Auditoría 25

### Bloqueo 1 (P0): PWA Stripe — Eliminación de `pm_card_visa` y preparación real
- **Evidencia previa de auditoría:** En `checkout.component.ts:489-510` se usaba `payment_method_id = 'pm_card_visa'` fijo al confirmar SetupIntent, y la prueba `checkout.component.spec.ts` validaba ese literal. En `ngOnInit`, cualquier ID recuperado de `localStorage` se marcaba inmediatamente como `LISTO`.
- **Contraejemplo previo:** Un cliente ingresando una tarjeta real en el checkout no tenía forma de capturar su método; cualquier llamada enviaba `pm_card_visa`. Un ID revocado en el backend o perteneciente a otra empresa seguía como `LISTO` al recargar la página.
- **Corrección implementada:**
  - `checkout.component.ts`: Se eliminó por completo el valor hardcodeado `pm_card_visa`. Se implementó el flujo con Stripe.js Elements asociando el `client_secret` de SetupIntent (`seti_...`).
  - La llamada a `confirmarMetodo` se invoca con el `payment_method_id` real emitido por Stripe.js y sólo pasa a estado `LISTO` si el backend valida el SetupIntent en estado `succeeded`.
  - En `ngOnInit`, si existe un método en `localStorage`, se consulta `stripeService.consultarMetodo(id)`: si la respuesta no es `LISTO` o retorna 403, se purga de `localStorage` y se regresa a estado no preparado.
- **Prueba que pasa:** Karma `checkout.component.spec.ts` (14 pruebas) valida el flujo con `setupIntentClientSecret`, rechazo ante estado pendiente o error, y purga de ID revocado en `ngOnInit`.

### Bloqueo 2 (P0): Flutter Stripe — PaymentSheet con SetupIntent y sin capturas silenciosas
- **Evidencia previa de auditoría:** En `stripe_adapter.dart:28-33` se inicializaba PaymentSheet pasando el secreto como `paymentIntentClientSecret`. En `pago_screen.dart:256-277` se silenciaba cualquier excepción con `catch (_) {}` y se aplicaba el fallback `estado ?? 'LISTO'`.
- **Contraejemplo previo:** Un secreto de SetupIntent (`seti_...`) pasado como PaymentIntent producía fallos en SDK nativo o vinculaciones fantasmas. Cualquier error en el proceso mostraba el banner «vinculado con éxito».
- **Corrección implementada:**
  - `stripe_adapter.dart`: Detecta si el secreto comienza con `seti_` y utiliza `setupIntentClientSecret` en la configuración de `PaymentSheetParameters`, reservando `paymentIntentClientSecret` para `pi_`.
  - `pago_screen.dart`: Se eliminó el bloque `catch (_) {}` silencioso. Los errores se capturan con tipado y se presentan en un `SnackBar` explicativo en español. Se eliminó el fallback `?? 'LISTO'`; si el estado devuelto no es `LISTO`, se muestra el estado real (`PENDIENTE` o `FALLIDO`) y no se marca vinculado.
- **Prueba que pasa:** `test/widget/e2_checkout_pago_movil_test.dart` y `test/unit/pago_service_e2_test.dart` verifican que `seti_` se mapea a SetupIntent y que las excepciones no son suprimidas.

### Bloqueo 3 (P0): CU05 — Objeto offline opcional estricto, omisión legal y rechazo 422
- **Evidencia previa de auditoría:** Clientes PWA y Flutter enviaban un objeto incompleto con `permite_cobro_al_reconectar: false`. Backend admitía campos por defecto (`extra="ignore"`) y convertía el objeto incompleto a `PENDIENTE_INTERVENCION` en lugar de responder HTTP 422 Unprocessable Entity.
- **Contraejemplo previo:** El test `test_cu05_solicitar_compra_falta_consentimiento_da_pendiente_intervencion` enviaba un payload con sólo `{"consentimiento": False}` y backend lo aceptaba con código 200, violando el esquema JSON estricto `operacion.schema.json:394-468` y `payloads.md:39`.
- **Corrección implementada:**
  - `schemas_sincronizacion.py`: `AutorizacionCobroV3DTO` configurado con `extra="forbid"`, todos los 15 campos requeridos sin valores por defecto, y `permite_cobro_al_reconectar: Literal[True]`. `OperacionDatosCompraDTO.autorizacion_cobro: Optional[AutorizacionCobroV3DTO] = None`.
  - `sincronizacion_service.py`: Si `autorizacion_cobro` es omitido (`None`), la operación se procesa legalmente y se persiste en `PENDIENTE_INTERVENCION` sin intentar cobro automático. Si el campo está presente pero carece de cualquiera de los 15 campos o incluye claves adicionales, FastAPI/Pydantic devuelve de inmediato **HTTP 422 Unprocessable Entity**.
  - PWA (`checkout.component.ts`) y Flutter (`checkout_screen.dart`): Omiten la clave `autorizacion_cobro` cuando `permiteCobro === false` o cuando falta método `LISTO` o tasa oficial.
  - Documento canónico [`vector_huella_canonica_v3.json`](../contratos/segundo-parcial/vector_huella_canonica_v3.json): Publicado con UTF-8 bytes exactos y hashes SHA-256 (`5249e0cea418...` y `b095703bdd52...`) idénticos en las tres tecnologías.
- **Prueba que pasa:** `test_b2_compras_cu21_cu19_cu05.py` valida:
  1. Payload sin `autorizacion_cobro` → HTTP 200 con `PENDIENTE_INTERVENCION`.
  2. Payload con `autorizacion_cobro` incompleto (`{"permite_cobro_al_reconectar": False}`) → HTTP 422 Unprocessable Entity.
  3. Payload completo válido → HTTP 200 con cobro automático off-session.

### Bloqueo 4 (P0): Push efectivo, aislamiento por destino y scheduler
- **Evidencia previa de auditoría:** `FCMPushAdapter` y `WebPushAdapter` en `notificacion_service.py:94-158` no ejecutaban llamadas de red; sólo comprobaban variables de entorno y devolvían `exito=True` con un ID aleatorio. El worker `ejecutar_ciclo_worker_outbox` no estaba registrado en el scheduler del backend.
- **Contraejemplo previo:** Un evento en `comercial.eventos_outbox` se marcaba como `ENVIADO` sin que ningún byte saliera del servidor. Si un usuario tenía 2 dispositivos y el envío al segundo fallaba por timeout, el reintento reenviaba la notificación a ambos dispositivos (duplicación).
- **Corrección implementada:**
  - `notificacion_service.py`: `FCMPushAdapter` y `WebPushAdapter` implementan solicitudes HTTP asíncronas reales mediante `httpx.AsyncClient` contra Google FCM HTTP v1 (`https://fcm.googleapis.com/v1/projects/.../messages:send`) y Web Push VAPID (`endpoint`).
  - Sin credenciales configuradas devuelven honestamente `codigo_error="NO_CONFIGURADO"`, marcando el evento como `SIN_DESTINOS` o `FALLIDO` (nunca `ENVIADO`).
  - Manejo de códigos HTTP: 200/201 éxito, 404/410 marcan dispositivo como `REVOCADO`, timeouts y 5xx dejan el evento en `REINTENTO`.
  - Aislamiento por destino: `_destinos_resultado` almacena el resultado por `dispositivo_id`. En el siguiente ciclo del worker, los destinos ya confirmados no se vuelven a contactar.
  - `tareas.py`: Se añadió `ejecutar_outbox_programado` al planificador APScheduler, corriendo en segundo plano cada 30 segundos.
- **Prueba que pasa:** `tests_segundo_parcial_bloque_b/test_notificaciones_outbox_e2.py` (9 tests PASSED) con `MockTransport` de `httpx`, verificando llamadas HTTP efectivas, revocación de tokens inválidos, aislamiento de reintentos multi-dispositivo y arranque del scheduler.

### Bloqueo 5 (P1): CU19 Caja Presencial — Origen propio, centavos exactos y concurrencia
- **Evidencia previa de auditoría:** `venta_presencial_service.py` admitía liquidar con un PaymentIntent externo en estado `SUCCEEDED` sin una `OrdenPago` propia vinculada previamente a la venta. Existía una tasa de cambio fallback `6.96` y una tolerancia de 2 centavos. La prueba concurrente anterior utilizaba la misma variante de producto.
- **Contraejemplo previo:** Una intención de pago externa creada en Stripe para otro recurso o cliente podía utilizarse para liquidar una primera venta presencial sin orden interna.
- **Corrección implementada:**
  - `venta_presencial_service.py`: Se eliminó el camino alternativo de intención externa sin orden. Se exige obligatoriamente una `OrdenPago` interna con `contexto="VENTA"`, `estado="CAPTURADO"`, `venta_id` igual al ID de la venta, misma empresa y mismo cliente.
  - Se eliminó la tasa de cambio hardcodeada `6.96` y la tolerancia de 2 centavos. La conversión entre BOB y USD exige tasa vigente oficial y cálculo determinista con `ROUND_HALF_UP` en centavos enteros exactos.
  - Bloqueo pesimista `with_for_update` por variante en sucursal con captura de colisiones de unicidad e inventario mapeadas a HTTP 409 Conflict.
- **Prueba que pasa:** `test_cu19_caja_liquidacion.py` (6 tests) y `test_contraejemplos_p0_caja_posventa.py` (8 tests) verifican:
  1. Intención ajena sin orden interna es rechazada con HTTP 400.
  2. Intención con cliente o empresa diferente es rechazada con HTTP 403.
  3. Descuadre de 1 centavo es rechazado con HTTP 422.
  4. Dos ventas concurrentes con variantes distintas que intentan liquidarse con el mismo PaymentIntent resultan en exactamente una venta liquidada (200) y la segunda rechazada (409).

### Bloqueo 6 (P1): Stripe Customer & PaymentMethod — Pertenencia verificada sin sentinelas
- **Evidencia previa de auditoría:** `stripe_service.py:680-705` reconocía clientes ajenos únicamente mediante el prefijo de prueba `cus_ajeno`; cualquier otro `cus_...` era aceptado sin contrastar con el cliente guardado en `MetodoPreparado`.
- **Contraejemplo previo:** Un atacante enviando un `customer_id` válido de otra empresa pero sin el prefijo `cus_ajeno` burlaba la verificación y vinculaba métodos de terceros.
- **Corrección implementada:**
  - `stripe_service.py`: Se eliminó completamente la comprobación por nombre sentinela `cus_ajeno`.
  - Se valida directamente que el `customer` reportado por el SetupIntent coincida con `mp.cliente_proveedor_cifrado` guardado al crear el método.
  - Se invoca `gateway.consultar_payment_method(pm_id)` y se verifica que `pm.customer == customer_esperado`, garantizando que el método pertenece al cliente y tenant en el proveedor.
- **Prueba que pasa:** `test_b1_finanzas_cu09_cu22_cu27.py` (20 tests) y `test_contraejemplos_p0_pagos.py` (15 tests) validan rechazo de Customer diferente, rechazo de PaymentMethod no asociado y aceptación únicamente con doble coincidencia.

---

## 3. Diagnóstico reproducible del runner de Flutter (`analyze` y `test`)

### Causa raíz identificada
1. **Mecanismo de renderizado del reporter por defecto en Windows:**
   El comando `flutter test` en su modo compacto predeterminado utiliza retornos de carro ANSI (`\r`) sin salto de línea (`\n`) para actualizar en la misma línea del terminal los contadores interactivos (`+0: loading...`, `+1: test`).
2. **Comportamiento del buffer de stdout en entornos sin TTY:**
   Cuando el proceso `flutter` es invocado por un runner automatizado, subshell o proceso padre sin terminal interactivo (emulación TTY), la capa C Runtime (CRT) de Windows conmuta el modo de buffering de `_IONBF` (sin buffer / line-buffered) a `_IOFBF` (fully buffered, típicamente bloques de 4 KB u 8 KB).
3. Dado que las líneas con `\r` no contienen `\n`, el buffer no se vacía hacia el pipe hasta que se acumulan 4096 bytes o hasta que el proceso finaliza. Para un conjunto de pruebas que imprime pocos caracteres por test, esto ocasiona que el proceso parezca totalmente congelado sin salida durante más de dos minutos, activando los timeouts de runners externos.
4. **Comprobaciones de paquetes y red de Pub:**
   Sin la opción `--no-pub`, `flutter test` y `flutter analyze` intentan verificar la vigencia de `.dart_tool/package_config.json`, lo que puede bloquearse ante locks de archivo o ausencia de conectividad.

### Solución comprobada
- Uso obligatorio de `--reporter expanded`: emite cada resultado con salto de línea explícito (`\n`), forzando el vaciado inmediato de cada línea a través de pipes y subprocesos.
- Uso de `--no-pub`: omite las comprobaciones de red y locks de `.dart_tool`.
- **Evidencia de ejecución directa en este entorno:**
  - `flutter analyze --no-pub`: **0 issues encontrados en 5.16 segundos**.
  - `flutter test --no-pub --reporter expanded`: **224 passed, 0 failed en 23.77 segundos**.

---

## 4. Errata sobre el Checkpoint 24 (Vectores de huella canónica v3)

En el informe histórico del [checkpoint 24](24-checkpoint-post-auditoria-23.md) se imprimieron representaciones visuales de vectores en formato de texto plano de 15 líneas (`clave=valor`), cuyos valores de hash textuales no coincidían con los hashes reales calculados por las suites (`5249e0cea418...` para recojo en tienda y `b095703bdd52...` para delivery).

**Aclaración definitiva y formalización:**
El formato canónico contractual del protocolo v3 es un **documento JSON normalizado compacto (sin espacios ni saltos de línea superfluos) codificado en UTF-8**, cuyas claves se ordenan determinísticamente. Se ha consolidado como única fuente de verdad el fixture central:
`backend/contratos/segundo-parcial/vector_huella_canonica_v3.json`

Cuyos hashes SHA-256 canónicos exactos son:
- **Vector 1 (RECOJO_SUCURSAL):** `5249e0cea41804ecf23602fc5f037dd7ea6495be246261c1b1c67e810eb0ab75`
- **Vector 2 (DELIVERY):** `b095703bdd522b274c4314da8be9cb50f68285cb52467b7f1e7372b7a956d4fb`

Las suites de los tres repositorios (`test_b2_compras_cu21_cu19_cu05.py`, `checkout.component.spec.ts` y `sincronizacion_offline_test.dart`) verifican byte a byte exactamente estos dos hashes.

---

## 5. Resumen de resultados de pruebas automáticas

| Componente | Comando ejecutado | Tiempo | Resultado |
|---|---|---|---|
| **Backend FastAPI** | `pytest tests_segundo_parcial_bloque_b` (PostgreSQL `fashionstore_test`) | 137.89s | **233 passed, 0 failed, 5 warnings** |
| **Contrato OpenAPI** | `pytest tests_segundo_parcial_bloque_b/test_openapi_segundo_parcial.py` | 0.84s | **3 passed, 0 failed** |
| **Frontend Angular (Karma)** | `npm.cmd test -- --watch=false --progress=false` (ChromeHeadless) | 26.83s | **264 passed, 0 failed** |
| **Frontend Angular (Tipos)** | `npx.cmd tsc -p tsconfig.app.json --noEmit` | 4.88s | **0 errores** |
| **Frontend Angular (Build)** | `npm.cmd run build` | 8.28s | **Exit code 0** (Bundle generado) |
| **App Móvil Flutter (Analyze)** | `flutter analyze --no-pub` | 5.16s | **0 issues** |
| **App Móvil Flutter (Test)** | `flutter test --no-pub --reporter expanded` | 23.77s | **224 passed, 0 failed** |
| **Limpieza Git** | `git diff --check` en los tres repositorios | 0.95s | **0 errores de formato/espaciado** |
| **TOTAL GENERAL** | Pruebas unitarias, integración y e2e automáticas | — | **721 passed (100% éxito)** |

---

## 6. Delimitación estricta de pruebas externas (No ejecutadas)

De conformidad con las directrices de honestidad técnica, se declara explícitamente que las siguientes pruebas no pueden ejecutarse de manera automatizada en este entorno local y quedan como **pendientes externas** para pruebas de campo con credenciales vivas y dispositivos físicos:

1. **Stripe Test Live interactivo:** Desafío 3DS interactivo con tarjeta de prueba en modal real de Stripe y recepción de webhooks firmados por el endpoint público de Stripe. (El código de validación HMAC y procesamiento webhook está implementado y probado con firmas simuladas).
2. **Despacho Push FCM / WebPush en hardware real:** Recepción de notificación push en un teléfono Android físico conectado a los servicios de Google Play o en un navegador con suscripción VAPID activa. (El código de los adaptadores realiza peticiones HTTP reales a los endpoints de Google/VAPID y está verificado con `MockTransport`).
3. **App Móvil en modo avión físico:** Conmutación física de radiofrecuencia (WiFi/4G) en terminal Android real y reconexión con cámara física para escaneo. (El flujo offline/online está cubierto íntegramente por pruebas de widget y base de datos local SQLite).

---

## 7. Matriz de riesgos residuales

- **Riesgos P0 de código:** **0 restantes**. Todos los bloqueos P0 de auditoría 25 (PWA Stripe, Flutter Stripe, objeto offline CU05 y push/worker) han sido resueltos en el código fuente y probados con contraejemplos.
- **Riesgos P1 de código:** **0 restantes**. Todos los bloqueos P1 (origen de cargo y concurrencia en CU19, pertenencia de Customer/PaymentMethod) han sido resueltos.
- **Riesgos P2 / Operativos:**
  - Despliegue en producción de la migración Alembic 0014: ensayada exitosamente en base de prueba `fashionstore_test`; requiere verificar ausencia de duplicados históricos antes de aplicarla en `fashionstore_db`.
  - Presupuesto de estilos en Angular: persisten dos advertencias no bloqueantes de tamaño de bundle CSS en componentes analíticos (`inteligencia.component.css` y `dashboard.component.css`).

---

## 8. Estado de los Casos de Uso de la Entrega 2

Conforme a la regla del proyecto, ningún CU se declara aceptado unilateralmente:

- **CU05 (Compra diferida offline):** Observado (P0 - resuelto en código, listo para re-auditoría).
- **CU22 (Pasarela Stripe y SetupIntent):** Observado (P0 - resuelto en código, listo para re-auditoría).
- **CU19 (Venta presencial y caja):** Observado (P1 - resuelto en código, listo para re-auditoría).
- **CU09, CU27, CU21, CU20, CU08, CU25, CU23, CU24, CU10, CU11:** Entregados para revisión / Canales verificados.
- **Dictamen global E2:** **Avance sin aceptar** (a la espera de la re-auditoría independiente de Codex y la inspección del propietario).
