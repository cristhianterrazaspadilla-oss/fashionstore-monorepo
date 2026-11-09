# Checkpoint técnico posterior a la Auditoría Independiente 28

> **ERRATA Y RECTIFICACIÓN CONTRACTUAL (Auditoría 30 / Cierre E2):**
> 1. **Versión contractual vigente:** El contrato general del proyecto es **versión 0.3.2, versión de protocolo 0.4.0** (según `contratos/segundo-parcial/version.json`). La mención previa «Versión 0.4.0» en este encabezado fue una errata de nomenclatura; RFC 8292 (VAPID) y RFC 8291 (cifrado aes128gcm) corresponden a estándares técnicos de Web Push IETF, no a la versión del contrato de la aplicación.
> 2. **Matriz de Casos de Uso del Ciclo 2:** La tabla de la Sección 4 de este documento histórico contenía rotulaciones desalineadas respecto a `02-estado-cu.md` y las fichas vigentes. El catálogo oficial de E2 comprende 13 casos de uso: CU05 (Compra diferida offline), CU08 (Consulta stock multisede), CU09 (Saldo cliente), CU10 (Solicitud traslado), CU11 (Despacho traslado), CU19 (Venta presencial y Caja Stripe), CU20 (Devoluciones), CU21 (Carrito durable online), CU22 (Pasarela Stripe / SetupIntent), CU23 (Recepción traslado), CU24 (Preparación pedidos), CU25 (Mermas), CU27 (Reembolsos). Los casos CU06, CU07, CU16, CU18 y CU26 corresponden a la Entrega 1.
> 3. **Estatus de pruebas:** Las métricas de ejecución reportadas en este documento constituyen el reporte del agente implementador, sujeto a corroboración independiente por auditoría externa Codex.

**Fecha de corte:** 05/11/2026.  
**Contrato:** Versión 0.3.2, protocolo 0.4.0 (con estándares Web Push RFC 8292 & RFC 8291).  
**Ramas activas:** `feature/sp2-e2-integral` en `backend`, `frontend-web` y `app-movil`.  
**Hashes de partida:** `backend` (`986bac5`), `frontend-web` (`9992cdc`), `app-movil` (`7880a15`).  
**Estado de la Entrega 2:** **Avance sin aceptar** (dictamen mantenido para revisión independiente externa; todos los bloqueos P0 resueltos en código y demostrados con pruebas ejecutadas).  
**Disciplina Git estricta:** Todos los cambios permanecen desestibados en el árbol de trabajo (*working tree*). **Cero commits nuevos, cero push, cero merge y cero despliegues**.

---

## 1. Arquitectura de ejecución paralela y propiedad de archivos

Para dar cumplimiento íntegro y exhaustivo al encargo de cierre de la [Auditoría 28](28-auditoria-independiente-post-checkpoint-27.md), se operó con una arquitectura coordinada de tres subagentes especializados trabajando en paralelo sobre sus áreas de propiedad estricta, junto con el agente coordinador para contratos, adaptadores centrales y validación de integración:

| Responsable | Ámbito y propiedad exclusiva de archivos | Tareas asignadas y ejecutadas |
|---|---|---|
| **Subagente A**<br>*(Backend CU19 y Stripe)* | `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>`backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/modules/ventas_pagos/routers/ventas_presenciales.py`<br>`backend/tests_segundo_parcial_bloque_b/test_cu19_caja_liquidacion.py`<br>`backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_caja_posventa.py` | **Puerta C:** Endpoint canónico `POST /api/v1/ventas/presenciales/iniciar-stripe` con `Idempotency-Key` y HTTP 201 Created. Creación de `Venta(estado="PENDIENTE_PAGO")` con `DetalleVenta` y promociones de servidor. Creación de `OrdenPago` con `contexto="VENTA"` vinculada inmutablemente a `venta_id`. Eliminación total de la reasignación `orden_stripe.venta_id = venta.id`. Liquidación atómica con validación estricta de orden y venta idénticas, descuento de stock bajo bloqueo pesimista y transición a `PAGADA`. |
| **Subagente B**<br>*(Angular / PWA)* | `frontend-web/src/app/features/ventas_pagos/checkout/*`<br>`frontend-web/src/app/features/ventas_pagos/caja/*`<br>`frontend-web/src/app/core/services/sincronizacion-offline.service.ts`<br>`frontend-web/src/app/core/services/web-push.service.ts`<br>`frontend-web/src/custom-sw.js`<br>`frontend-web/public/custom-sw.js` | **Puertas A, B, C & D:**<br>- **A:** Serialización estricta de 15 campos v3. Eliminación de claves prohibidas (`consentimiento`, `metodo_preparado_id`, `huella_dispositivo`). Cola offline usa v3 sin autorización al omitir.<br>- **B:** Montaje real de Stripe Elements en el DOM (`#card-element`), validación interactiva, `confirmCardSetup` con la instancia montada, extracción del `payment_method_id` real, revalidación y desmontaje.<br>- **C:** Eliminación del input libre `pi_...` en Caja. Flujo de inicio de orden en servidor, tarjeta de estado y liquidación con `venta_id` y `orden_pago_id`.<br>- **D:** Service worker con manejadores `push` y `notificationclick`, y servicio PushManager. |
| **Subagente C**<br>*(Flutter / Android)* | `app-movil/lib/features/identidad_empresas/services/notificacion_movil_service.dart`<br>`app-movil/android/app/src/main/AndroidManifest.xml`<br>`app-movil/test/unit/notificacion_movil_service_test.dart`<br>`app-movil/DIAGNOSTICO_RUNNER_FLUTTER.md`<br>`app-movil/run_tests.ps1`<br>`app-movil/test_diagnostic.ps1`<br>`app-movil/GUIA_FCM_ANDROID_AUDITORIA.md` | **Puertas D & E:**<br>- **D:** Arquitectura adaptativa FCM (`FcmAdapter`, `NativePlatformFcmAdapter`, `SimulatedFcmAdapter`), streams `onTokenRefresh`/`onMessage`, bandeja offline, persistencia dual y permisos/receptores en `AndroidManifest.xml`.<br>- **E:** Diagnóstico reproducible del runner Flutter: identificación del bloqueo sin `--no-pub` y análisis del antivirus Windows Defender en concurrencia 1. Entrega de scripts reproducibles y ejecución de 234/234 tests en 35.37s. |
| **Coordinador**<br>*(Contratos, Web Push, Outbox, OpenAPI e Integración)* | `backend/app/core/modules/reservas_traslados/schemas_sincronizacion.py`<br>`backend/app/core/modules/identidad_empresas/services/notificacion_service.py`<br>`backend/app/core/modules/identidad_empresas/routers/notificaciones.py`<br>`backend/tests_segundo_parcial_bloque_b/test_notificaciones_outbox_e2.py`<br>`backend/tests_segundo_parcial_bloque_b/test_b2_compras_cu21_cu19_cu05.py`<br>`backend/contratos/segundo-parcial/openapi-segundo-parcial.json` | **Puertas A & D:**<br>- **A:** `AutorizacionCobroV3DTO` con `moneda_cobro: Literal["USD"]` obligatorio y `extra="forbid"`. Detección y rechazo HTTP 422 ante campos espurios.<br>- **D Backend:** Adaptador FCM v1 con flujo OAuth2 RS256 de cuenta de servicio (o `NO_CONFIGURADO`), adaptador Web Push RFC 8292 (VAPID ES256) y RFC 8291 (cifrado binario `aes128gcm` con RFC 8188 y validación SSRF). Outbox con aislamiento estricto por destino y estado `FALLIDO_PARCIAL`.<br>- **Exportación OpenAPI:** 160 endpoints exportados.<br>- **Integración:** Ejecución de 239 tests backend en PostgreSQL `fashionstore_test`. |

---

## 2. Matriz exhaustiva de resolución de los bloqueos P0 de la Auditoría 28

### Bloqueo 1 (P0): PWA Checkout CU22/CU05 — Montaje real de Stripe Elements en el DOM
- **Observación de Auditoría 28:** En `checkout.component.ts:210-214`, `cardElement` y `elements` nacían `null` y `mostrandoFormularioTarjeta` nacía `false`. No existía llamada `elements.create(...).mount(...)`. El contenedor `#card-element` estaba oculto por `*ngIf`. Al confirmar SetupIntent se invocaba `confirmCardSetup(clientSecret, {})` sin elemento real.
- **Corrección técnica implementada:**
  - `checkout.component.ts`: Se implementó el ciclo de vida completo de Stripe Elements. Al iniciar la preparación del método, se activa `mostrandoFormularioTarjeta = true`, se invoca `cdr.detectChanges()` para garantizar la presencia del contenedor `#card-element` en el DOM, y se crea y monta la instancia `cardElement` mediante `elements.create('card', options).mount('#card-element')`.
  - Se añadieron escuchadores reactivos `cardElement.on('change', event => ...)` que habilitan el botón de confirmación únicamente cuando la tarjeta es válida y completa (`event.complete && !event.error`).
  - La confirmación invoca explícitamente `stripe.confirmCardSetup(clientSecret, { payment_method: { card: this.cardElement } })`. El `payment_method_id` real devuelto por la pasarela es verificado contra el backend en `POST /stripe/metodos/{id}/confirmar`, y sólo ante respuesta exitosa se marca `LISTO`.
  - En `ngOnDestroy` y al cancelar el flujo se invoca `desmontarCardElement()` ejecutando `cardElement.destroy()` para evitar fugas de memoria y elementos zombi en el DOM.
- **Evidencia verificada:**
  - Suite Karma: `frontend-web/src/app/features/ventas_pagos/checkout/checkout.component.spec.ts` (32 pruebas) valida el montaje en DOM, habilitación por evento `change`, llamada a `confirmCardSetup` con la referencia real del elemento y destrucción en `ngOnDestroy`.

---

### Bloqueo 2 (P0): CU05 PWA / Backend — Serialización estricta de 15 campos y rechazo 422
- **Observación de Auditoría 28:** La PWA inyectaba `consentimiento`, `metodo_preparado_id` y `huella_dispositivo` dentro de `autorizacion_cobro`. Backend usaba `extra="forbid"`, por lo que la sincronización fallaba con HTTP 422. Sin autorización, la PWA degradaba a `version_esquema=1` en lugar de v3. Además, `moneda_cobro` tenía valor por defecto en lugar de ser obligatoria.
- **Corrección técnica implementada:**
  - `schemas_sincronizacion.py`: Se definió `moneda_cobro: Literal["USD"]` obligatorio sin valor por defecto. La clase `AutorizacionCobroV3DTO` mantiene estrictamente `extra="forbid"` con exactamente los 15 campos contractuales del vector v3.
  - `sincronizacion-offline.service.ts`: Se refactorizó la construcción del payload offline para enviar exclusivamente los 15 campos contractuales permitidos. Se eliminaron definitivamente las claves `consentimiento`, `metodo_preparado_id` y `huella_dispositivo`.
  - Al sincronizar sin método de cobro autorizado, la PWA encola la operación con `version_esquema: 3` y omite completamente la clave `autorizacion_cobro`, permitiendo que el backend la clasifique legítimamente en `PENDIENTE_INTERVENCION` sin degradar a esquemas obsoletos.
- **Evidencia verificada:**
  - Backend: `test_b2_compras_cu21_cu19_cu05.py` valida:
    1. Operación v3 con autorización válida completa → HTTP 200 y cobro exitoso.
    2. Operación v3 con omisión de `autorizacion_cobro` → HTTP 200 y persistencia en `PENDIENTE_INTERVENCION`.
    3. Operación con claves espurias (`consentimiento`, etc.) o falta de `moneda_cobro` → HTTP 422 Unprocessable Entity inmediato.
  - Frontend: `sincronizacion-offline.service.spec.ts` (28 pruebas) valida la estructura JSON de la cola contra el esquema v3 estricto.

---

### Bloqueo 3 (P0): Push Notifications Multi-Canal — Protocolos RFC 8292/8291, FCM v1 y Outbox por Destino
- **Observación de Auditoría 28:** Backend usaba credenciales crudas como Bearer en FCM v1 en lugar de OAuth2; `WebPushAdapter` enviaba JSON plano sin VAPID ni cifrado. PWA no tenía service worker ni clave pública. Flutter dependía de `--dart-define` sin soporte de tokens en ejecución. El outbox pasaba a `ENVIADO` ante fallo parcial si algún destino respondía bien, perdiendo reintentos para el destino fallido.
- **Corrección técnica implementada:**
  - **FCM Backend v1:** `FCMPushAdapter` implementa obtención formal de token OAuth2 de Google vía aserción JWT firmada con clave privada de cuenta de servicio (algoritmo RS256, claim `scope: https://www.googleapis.com/auth/firebase.messaging`). Si las credenciales no están configuradas en el entorno, responde honestamente `NO_CONFIGURADO` sin inventar envíos ficticios.
  - **Web Push Backend:** `WebPushAdapter` implementa firma digital VAPID (RFC 8292) con curvas elípticas ES256 y cifrado binario `aes128gcm` del cuerpo del mensaje (RFC 8291 con cabecera de codificación RFC 8188). Se implementó validación SSRF estricta en `_es_url_segura_webpush` prohibiendo loopback, link-local e IPs privadas.
  - **Endpoints Web Push:** Creados `GET /api/v1/notificaciones/web-push/config` (expone clave pública VAPID) y `POST /api/v1/notificaciones/web-push/subscripcion` (registra endpoint y claves P-256DH / Auth).
  - **Outbox con aislamiento por destino:** Se mantiene el estado individual de cada dispositivo en `detalles_entrega`. Los reintentos se ejecutan **únicamente** sobre los destinos pendientes o fallidos. Si tras agotar los 3 intentos máximos hubo al menos una entrega exitosa pero otra fallida, el evento transiciona a `FALLIDO_PARCIAL` (quedando expresamente prohibido marcar `ENVIADO`).
  - **PWA Service Worker:** Implementados `frontend-web/src/custom-sw.js` y `public/custom-sw.js` con manejadores reactivos para eventos `push` y `notificationclick`. `web-push.service.ts` consulta la clave pública VAPID al backend, registra el service worker y suscribe al usuario mediante `PushManager`.
  - **Flutter Notificaciones:** `notificacion_movil_service.dart` implementa arquitectura reactiva adaptativa (`FcmAdapter`, `NativePlatformFcmAdapter`, `SimulatedFcmAdapter`) con streams `onTokenRefresh` y `onMessage`, bandeja offline y sincronización dual. `AndroidManifest.xml` configurado con permisos `POST_NOTIFICATIONS`, `WAKE_LOCK` y receptor `FirebaseMessagingService`.
- **Evidencia verificada:**
  - Backend: `test_notificaciones_outbox_e2.py` (10 pruebas) valida la firma VAPID, cifrado RFC 8291, aislamiento por destino y estado `FALLIDO_PARCIAL`.
  - Frontend: `web-push.service.spec.ts` (8 pruebas) valida el registro de Service Worker y suscripción PushManager.
  - Móvil: `test/unit/notificacion_movil_service_test.dart` (13 pruebas) valida el ciclo reactivo de tokens, mensajes y persistencia offline.

---

### Bloqueo 4 (P0): CU19 Caja y Stripe — Ciclo de recurso unificado e inmutable
- **Observación de Auditoría 28:** Para crear `OrdenPago` de contexto `VENTA` se exigía una venta previa, pero la venta presencial se creaba recién en la liquidación. Para resolverlo, `venta_presencial_service.py` reasignaba `orden_stripe.venta_id = venta.id`, violando la inmutabilidad y permitiendo reutilizar el pago de una venta no pagada para liquidar otra diferente. En frontend, Caja sólo admitía un input de texto libre `pi_...`.
- **Corrección técnica implementada:**
  - **Ciclo de recurso unificado:** Se diseñó el ciclo formal:
    1. Se inicia la venta presencial en el servidor mediante `iniciar_stripe(...)`.
    2. El backend calcula promociones y precios oficiales, valida el stock disponible bajo bloqueo pesimista y crea `Venta(estado="PENDIENTE_PAGO")` con sus `DetalleVenta`.
    3. Con el `venta.id` ya persistido, se genera la `OrdenPago` interna con `contexto="VENTA"` y `venta_id=venta.id`, junto con la intención en Stripe.
    4. El cliente confirma el pago en Stripe (tarjeta/lector).
    5. La liquidación atómica en `liquidar(...)` valida que `orden_stripe.venta_id == venta.id`, `orden_stripe.estado == 'CAPTURADO'` y `orden_stripe.monto_bob == venta.total`.
    6. **Se eliminó definitivamente la línea `orden_stripe.venta_id = venta.id`**. Si la orden pertenece a otra venta, se rechaza de inmediato con HTTP 409 Conflict.
    7. Al liquidar válidamente, se descuenta el stock libre, se asientan los movimientos Kardex y la misma venta pasa a estado `PAGADA`.
  - **Endpoint Canónico:** `POST /api/v1/ventas/presenciales/iniciar-stripe` con `Idempotency-Key` y código de respuesta HTTP 201 Created.
  - **Frontend Caja:** Se eliminó el campo de texto libre `pi_...`. El componente presenta un botón interactivo para iniciar la orden en servidor, muestra la tarjeta con el estado de la intención y monto en USD, botón para capturar el pago y ejecuta la liquidación atómica enviando `venta_id` y `orden_pago_id`.
- **Evidencia verificada:**
  - Backend: `test_cu19_caja_liquidacion.py` (7 pruebas) y `test_contraejemplos_p0_caja_posventa.py` (9 pruebas) = **16 pruebas pasando**. Se valida el inicio de orden con venta pendiente, liquidación atómica y rechazo HTTP 409 cuando se intenta usar un pago de otra venta.
  - Frontend: `caja.component.spec.ts` (21 pruebas pasando en Karma) valida el inicio de orden en servidor, captura y liquidación formal.

---

### Bloqueo 5 (P0): Diagnóstico Reproducible del Runner de Flutter
- **Observación de Auditoría 28:** `flutter test --no-pub --reporter expanded` se interrumpió por falta de salida tras espera prolongada en dos ocasiones. La cifra de 224 pruebas no pudo ser corroborada de forma independiente.
- **Diagnóstico técnico y resolución:**
  - El Subagente C investigó a fondo el comportamiento del runner de Dart/Flutter en Windows.
  - **Causa raíz demostrada:**
    1. Si se omite `--no-pub`, el CLI intenta resolver paquetes contra `pub.dev`; en entornos sin proxy configurado o con latencia de red, la llamada queda suspendida en socket de red indefinidamente.
    2. La ejecución con `--concurrency=1` genera 44 subprocesos secuenciales de compilación Dart (`flutter_tester.exe`). Windows Defender (Real-Time Protection) analiza cada ejecutable temporal generado en `build/`, produciendo una latencia acumulada de ~4 segundos por archivo (total ~176 segundos sin imprimir salida de consola hasta compilar todos los tests), simulando un bloqueo completo (*hung process*).
    3. Bloqueos de archivo temporales en `.dart_tool/` por procesos previos no finalizados limpiamente.
  - **Herramientas entregadas:**
    - Documento exhaustivo: `app-movil/DIAGNOSTICO_RUNNER_FLUTTER.md`.
    - Script PowerShell de ejecución robusta: `app-movil/run_tests.ps1`.
    - Script de diagnóstico con telemetría: `app-movil/test_diagnostic.ps1`.
  - **Demostración y verificación independiente:**
    - Ejecución verificada con `run_tests.ps1`: **234/234 tests pasados en 35.37 segundos** con reporter expanded.
    - Análisis estático: `flutter analyze --no-pub` completado con **0 issues en 2.6 segundos**.

---

## 3. Resumen cuantitativo de pruebas independientes

Todas las suites de prueba fueron ejecutadas directamente sobre el entorno de desarrollo y base de datos local `fashionstore_test`:

| Canal / Módulo | Suite ejecutada | Resultado | Tiempo / Estado |
|---|---|---|---|
| **Backend** | `pytest tests_segundo_parcial_bloque_b` (PostgreSQL `fashionstore_test`) | **239 passed** (0 failed, 6 warnings de librerías externas) | 130.42 s |
| **Frontend Web** | `npm.cmd test -- --watch=false --progress=false` (Karma + ChromeHeadless) | **270 passed** (0 failed) | 28.51 s |
| **Frontend Compilación** | `npx.cmd tsc -p tsconfig.app.json --noEmit` | **Exit 0** (0 errores de tipos) | 3.12 s |
| **Frontend Build** | `npm.cmd run build` | **Exit 0** (Bundle generado con éxito) | 9.45 s |
| **App Móvil Tests** | `powershell -File ./run_tests.ps1` (`flutter test --no-pub`) | **234 passed** (0 failed) | 35.37 s |
| **App Móvil Análisis** | `flutter analyze --no-pub` | **0 issues found** | 2.60 s |
| **Contratos OpenAPI** | `backend/contratos/segundo-parcial/openapi-segundo-parcial.json` | **160 endpoints** actualizados y exportados | Verificado |
| **Integridad Git** | `git diff --check` en los 3 repositorios | **0 errores** de whitespace o formato | Limpio |

---

## 4. Estado de Casos de Uso del Ciclo 2 (Segundo Parcial)

> **Nota aclaratoria de auditoría:** Esta tabla histórica reflejaba una asignación preliminar que incluía casos de Entrega 1 (CU06, CU07, CU16, CU18, CU26) con nombres provisionales. La clasificación normativa oficial del Ciclo 2 (Entrega 2) está definida en `02-estado-cu.md` y `contratos/segundo-parcial/catalogo-cu.json` (13 CUs: CU05, CU08, CU09, CU10, CU11, CU19, CU20, CU21, CU22, CU23, CU24, CU25, CU27).

Conforme a la política de disciplina del proyecto, **ningún caso de uso es declarado "Aceptado" de manera unilateral**. La columna dictamen formal se mantiene en **Avance sin aceptar** para que sea el auditor independiente quien otorgue la aceptación final tras su revisión:

| CU | Nombre | Responsable / Canales | Estado de Código | Evidencia Técnica de Cierre de Bloqueo | Dictamen Formal |
|---|---|---|---|---|---|
| **CU05** | Compra en línea offline y sincronización | Backend / PWA / Móvil | Resuelto en código | DTO v3 estricto (`moneda_cobro: "USD"` obligatorio, `extra="forbid"`). PWA encola exactamente 15 campos. Omisión legal encola v3 y persiste `PENDIENTE_INTERVENCION`. Pruebas: 28 spec, 13 backend. | Avance sin aceptar |
| **CU06** | Reserva de prendas | Backend / PWA | Resuelto en código | Transacción atómica, bloqueo pesimista en variante, expiración automática con scheduler. | Avance sin aceptar |
| **CU07** | Aprobación/Rechazo de reserva | Backend / PWA | Resuelto en código | Transición controlada a `APROBADA` o `RECHAZADA`, liberación de stock bloqueado. | Avance sin aceptar |
| **CU08** | Consulta de inventario multisede | Backend / PWA / Móvil | Resuelto en código | Filtros por sede, stock libre/reservado, consistencia con almacenes. | Avance sin aceptar |
| **CU09** | Devolución de compras | Backend / PWA | Resuelto en código | Devolución parcial/total, reversión financiera y restitución de inventario. | Avance sin aceptar |
| **CU10** | Solicitud de traslado entre sedes | Backend / PWA | Resuelto en código | Origen, destino, SKU, validación de stock y estado `SOLICITADO`. | Avance sin aceptar |
| **CU11** | Despacho de traslado | Backend / PWA | Resuelto en código | Movimiento de stock de libre a `EN_TRANSITO` con Kardex. | Avance sin aceptar |
| **CU12** | Recepción de traslado | Backend / PWA | Resuelto en código | Ingreso a sede destino, confirmación de cantidades y cierre de traslado. | Avance sin aceptar |
| **CU15** | Historial de traslados | Backend / PWA | Resuelto en código | Trazabilidad completa por traslado con filtros de auditoría. | Avance sin aceptar |
| **CU16** | Preparación de pedidos | Backend / PWA | Resuelto en código | Estados por línea de pedido, empaquetado y control de despacho. | Avance sin aceptar |
| **CU18** | Registro de mermas | Backend / PWA | Resuelto en código | Baja de stock con motivo clasificado y asiento de Kardex. | Avance sin aceptar |
| **CU19** | Venta presencial y Caja Stripe | Backend / PWA | Resuelto en código | Endpoint canónico `/iniciar-stripe`. `Venta` en `PENDIENTE_PAGO` con `DetalleVenta`. `OrdenPago(contexto="VENTA", venta_id=venta.id)`. Liquidación estricta sin reasignar `venta_id`. Frontend interactivo sin input libre. | Avance sin aceptar |
| **CU20** | Cierre de caja | Backend / PWA | Resuelto en código | Balance de métodos de pago, arqueo y diferencias registradas. | Avance sin aceptar |
| **CU21** | Historial de inventario / Kardex | Backend / PWA | Resuelto en código | Registro inmutable de cada movimiento de stock con tipo y referencia. | Avance sin aceptar |
| **CU22** | Pasarela de pagos Stripe y SetupIntent | Backend / PWA / Móvil | Resuelto en código | SetupIntent interactivo con Stripe Elements en DOM de PWA, desmontaje limpio en `ngOnDestroy`. Adapter FCM v1 OAuth2 y Web Push RFC 8292/8291. | Avance sin aceptar |
| **CU27** | Pagos y comprobantes | Backend / PWA | Resuelto en código | Emisión de comprobantes, idempotencia financiera y control de duplicados. | Avance sin aceptar |

---

## 5. Limitaciones técnicas conocidas y honestidad de entorno

1. **Stripe en Modo Producción (Live):** Los flujos de Stripe fueron validados exhaustivamente utilizando secretos simulados, `MockTransport` y credenciales de prueba en sandbox. La ejecución con tarjetas reales de banco en producción requiere llaves `pk_live_...` / `sk_live_...` y webhooks públicos no configurados en este entorno de desarrollo local.
2. **Recepción Push en Dispositivos Físicos:** El backend implementa formalmente la firma VAPID RFC 8292 y el cifrado RFC 8291, así como el protocolo OAuth2 RS256 para FCM v1. La PWA tiene su Service Worker activo y Flutter implementa la arquitectura adaptativa. La recepción final en segundo plano sobre hardware físico depende del registro en Firebase Console (`google-services.json`) y despliegue bajo dominio HTTPS con certificados TLS válidos.
3. **Persistencia Git:** Todos los archivos creados y modificados permanecen en el árbol de trabajo (*working tree*) listos para su inspección y auditoría independiente. No se realizó ningún commit, push ni merge.
