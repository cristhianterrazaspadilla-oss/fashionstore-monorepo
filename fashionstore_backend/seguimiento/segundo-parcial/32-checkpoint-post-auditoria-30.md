# Checkpoint técnico posterior a la Auditoría Independiente 30

**Fecha de corte:** 05/11/2026.  
**Contrato:** Versión 0.3.2, protocolo 0.4.0 (con estándares Web Push RFC 8292 & RFC 8291).  
**Ramas activas:** `feature/sp2-e2-integral` en `backend`, `frontend-web` y `app-movil`.  
**Hashes de partida:** `backend` (`986bac5`), `frontend-web` (`9992cdc`), `app-movil` (`7880a15`).  
**Estado de la Entrega 2:** **Avance sin aceptar** (ningún caso de uso es marcado como aceptado de forma autónoma; todo queda preparado para la revisión final independiente de Codex).  
**Disciplina Git estricta:** Todos los cambios permanecen en el árbol de trabajo (*working tree*). **Cero commits nuevos, cero push, cero merge y cero despliegues**.

---

## 1. Arquitectura de ejecución y propiedad de archivos

Para implementar íntegramente el plan de remediación de la [Auditoría 30](30-auditoria-independiente-post-checkpoint-29.md) conforme al encargo [E2-cierre-auditoria-30-subagentes.md](prompts/E2-cierre-auditoria-30-subagentes.md) y las puertas [G0–G6](31-plan-correccion-y-puertas-cierre-e2.md), se operó con una arquitectura coordinada de tres subagentes especializados trabajando en paralelo sobre archivos exclusivos, junto con el agente coordinador para contratos, esquema OpenAPI, sincronización y validación integral:

| Responsable | Ámbito y propiedad exclusiva de archivos | Tareas asignadas y ejecutadas |
|---|---|---|
| **Subagente A**<br>*(Backend Dinero/Caja)* | `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>`backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/modules/ventas_pagos/routers/pagos_stripe.py`<br>`backend/app/core/modules/ventas_pagos/routers/ventas_presenciales.py`<br>`backend/app/core/modules/ventas_pagos/integraciones/stripe_gateway.py`<br>`backend/tests_segundo_parcial_bloque_b/test_cu19_caja_liquidacion.py`<br>`backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_caja_posventa.py` | **Puertas G0, G2 & G3:**<br>- Reintento de `/iniciar-stripe` recupera `client_secret` real desde `gateway.consultar_intencion` y tasa congelada real, eliminando `{pi}_secret_test` y `6.96` de reserva.<br>- Implementación de `POST /stripe/ordenes/{id}/confirmar` para verificar PaymentIntent en pasarela y transicionar a `CAPTURADO`. `continuar-accion` permanece reservado a `REQUIERE_ACCION_CLIENTE`.<br>- Eliminación de mutación directa `ord_db.estado = "CAPTURADO"` en tests de integración vertical.<br>- Reconciliación G3 de turnos y cupos: cuando `turno_caja_id` está presente, `iniciar_stripe` valida disponibilidad en `CupoCaja` y `liquidar` consume `CupoCaja` y reduce `inv.comprometido_caja` sin descontar `inv.disponible` dos veces. |
| **Subagente B**<br>*(Angular / PWA)* | `frontend-web/src/app/core/services/sincronizacion-offline.service.ts`<br>`frontend-web/src/app/core/services/sincronizacion-offline.service.spec.ts`<br>`frontend-web/src/app/features/ventas_pagos/services/stripe.service.ts`<br>`frontend-web/src/app/features/ventas_pagos/caja/*`<br>`frontend-web/src/app/features/ventas_pagos/checkout/*`<br>`frontend-web/src/app/features/identidad_empresas/services/web-push.service.ts`<br>`frontend-web/src/app/features/identidad_empresas/services/web-push.service.spec.ts` | **Puertas G0, G1, G2, G4 & G5:**<br>- **G1:** Erradicación total de fabricación de datos en `sanitizarAutorizacionCobro`. Si faltan campos, encola compra v3 sin `autorizacion_cobro` (servidor fija `PENDIENTE_INTERVENCION` sin cargo). Sin auto-reparación destructiva al reintentar.<br>- **G2:** Eliminación de falso `CAPTURADO` en error o sin servicio en Caja. Confirmación con Stripe.js o endpoint central. Eliminación de input de texto libre `pi_...`.<br>- **G4:** Checkout falla cerrado si falta SDK o falla `mount()`. `cardElementValido` inicia en `false` y requiere `change.complete && !error`. Eliminados mocks en producción. Desmontaje y purga de secretos en memoria.<br>- **G5:** Registro único Web Push con `dispositivo_id` estable sin llamar a `/dispositivos`. Propagación de fallos y revocación por ese mismo ID. |
| **Subagente C**<br>*(Flutter / Android)* | `app-movil/pubspec.yaml`<br>`app-movil/pubspec.lock`<br>`app-movil/lib/features/identidad_empresas/services/notificacion_movil_service.dart`<br>`app-movil/android/app/src/main/AndroidManifest.xml`<br>`app-movil/run_tests.ps1`<br>`app-movil/test/unit/notificacion_movil_service_test.dart`<br>`app-movil/README-FCM.md`<br>`app-movil/GUIA_FCM_ANDROID_AUDITORIA.md` | **Puertas G0, G5 & G6:**<br>- **G5:** Dependencias oficiales `firebase_core: 5.1.0` y `firebase_messaging: 17.0.1` agregadas y resueltas desde caché local. Implementación de `NativePlatformFcmAdapter` con FlutterFire oficial (tokens, permisos, foreground, background top-level handler, cold-start). Eliminación de `<service>` huérfano en `AndroidManifest.xml`. Adaptador simulado disponible por inyección para CI.<br>- **G6:** Reparación de `run_tests.ps1`: eliminación de borrado destructivo de `*.db*`/`*.sqlite*`, implementación de timeout real de 180s con terminación de proceso hijo. Compilación nativa de APK debug verificada. |
| **Coordinador**<br>*(Contratos, OpenAPI e Integración)* | `backend/contratos/segundo-parcial/openapi-segundo-parcial.json`<br>`backend/seguimiento/segundo-parcial/02-estado-cu.md`<br>`backend/seguimiento/segundo-parcial/04-bitacora.md`<br>`backend/seguimiento/segundo-parcial/05-reanudacion.md`<br>`backend/seguimiento/segundo-parcial/29-checkpoint-post-auditoria-28.md` | **Puertas G0 & G6:**<br>- Rectificación contractual en checkpoint 29: contrato 0.3.2, protocolo 0.4.0 y errata sobre matriz de CUs.<br>- Exportación y verificación de OpenAPI con 161 endpoints (incluyendo `POST /stripe/ordenes/{id}/confirmar`).<br>- Coordinación multi-repo y ejecución de suites consolidadas: 245 backend, 284 Angular, 239 Flutter. |

---

## 2. Matriz exhaustiva por Puerta (G0–G6)

### G0. Línea Base y Contraejemplos Reproducidos
Cada defecto reportado en la Auditoría 30 fue reproducido con una prueba o contraejemplo que falló antes de editar el código:
1. **CU05 Sanitizador PWA:** `sanitizarAutorizacionCobro({ consentimiento_id: 'c1' })` generaba `crypto.randomUUID()`, `tasa_bob_por_usd = '6.96'`, `base_bob = '0.00'`, fecha actual por defecto y `permite_cobro_al_reconectar = true`.
2. **CU19 Caja PWA:** `capturarStripePresencial` y `capturarStripeCaja` forzaban `orden.estado_orden = 'CAPTURADO'` en la rama `error` y cuando `stripeService` no estaba disponible.
3. **CU19 Backend Reintento:** Al reintentar `/iniciar-stripe`, devolvía `client_secret = f"{pi}_secret_test"` y tasa `6.96` de reserva (`AssertionError: 'pi_test_..._secret_test' == '..._secret_real'`).
4. **CU19 Backend Simulación de Test:** `test_cu19_caja_liquidacion.py` saltaba el flujo formal mutando `ord_db.estado = "CAPTURADO"` directamente en la base de datos.
5. **CU19/Turno (G3):** En venta presencial con `turno_caja_id`, con stock libre 0 y cupo en caja 1, `iniciar_stripe` fallaba con `HTTP 409: Stock insuficiente disponible 0, requerido 1`.
6. **CU22 Checkout:** Al faltar Stripe.js, el componente instanciaba un elemento ficticio `{ create: () => ... }`, silenciaba errores de `mount()` y fijaba `cardElementValido = true` sin ningún evento `change`.
7. **Avisos Flutter (G5):** `pubspec.yaml` carecía de dependencias de Firebase; `MethodChannel` crudo fallaba con `MissingPluginException`.
8. **Web Push PWA (G5):** `suscribirWebPush()` llamaba secuencialmente a `/notificaciones/web-push/subscripcion` y `/notificaciones/dispositivos`, registrando dos dispositivos para la misma suscripción.
9. **Runner Móvil (G6):** `run_tests.ps1` borraba indiscriminadamente archivos `*.db*` y `*.sqlite*` del workspace y no implementaba el timeout prometido de 180s.

---

### G1. CU05 Autorización Offline y Cola IndexedDB
- **Implementación:**
  - En `sincronizacion-offline.service.ts`, `sanitizarAutorizacionCobro` valida que los 15 campos canónicos del Protocolo v3 existan con tipos y formatos auténticos (hashes SHA-256 de 64 caracteres, UUIDs válidos, firmas ISO y valores monetarios coherentes). Ante la mínima inconsistencia o dato parcial, retorna `undefined`.
  - Encolado offline bajo **Protocolo v3**: si la autorización es parcial o ausente, la compra se encola **sin** `autorizacion_cobro`. El servidor FastAPI la clasifica legítimamente en `PENDIENTE_INTERVENCION` sin cobrar dinero.
  - En el reenvío/sincronización de registros existentes en IndexedDB, no se "reparan" objetos parciales.
- **Evidencia:**
  - Suite Karma: `sincronizacion-offline.service.spec.ts` prueba autorización íntegra, rechazo de parciales a v3 sin cobro, ausente y corrupta.
  - Backend: `test_b2_compras_cu21_cu19_cu05.py` valida 0 llamadas a Stripe ante autorización ausente o parcial.

---

### G2. CU19 Pago Stripe Presencial y Reintentos
- **Implementación:**
  - En `venta_presencial_service.py`, al resolver idempotencia se consulta `self.gateway.consultar_intencion(ord_existente.referencia_externa)` recuperando el `client_secret` real de la pasarela y la tasa congelada legítima desde `ord_existente.tasa_id` o `monto_bob / monto_usd`. Se eliminaron por completo `{pi}_secret_test` y el fallback `'6.96'`.
  - En `stripe_service.py` y `pagos_stripe.py`, se creó el endpoint `POST /api/v1/pagos/stripe/ordenes/{id}/confirmar`, que consulta la pasarela Stripe y transiciona la orden `PENDIENTE` a `CAPTURADO` únicamente si la intención está en `SUCCEEDED`. `continuar-accion` permanece reservado a `REQUIERE_ACCION_CLIENTE` (3DS/SCA).
  - En PWA `caja.component.ts`: blindaje contra doble clic; eliminación definitiva de falso `CAPTURADO` en error; confirmación con Stripe.js o endpoint central; eliminación de input manual `pi_...`.
  - En `test_cu19_caja_liquidacion.py`: se eliminó `ord_db.estado = "CAPTURADO"` directo en DB, utilizando la ruta oficial de confirmación.
- **Evidencia:**
  - Suite Backend: `test_cu19_caja_liquidacion.py` (11 tests PASSED) y `test_contraejemplos_p0_caja_posventa.py` (11 tests PASSED).

---

### G3. Turnos y Cupos de Caja (CU06/CU07/CU19)
- **Implementación:**
  - En `venta_presencial_service.py`, cuando `dto.turno_caja_id` está presente:
    - `iniciar_stripe`: valida que el turno esté `ABIERTO` y que el cajero tenga cupo disponible suficiente en `CupoCaja` (`otorgado - consumido - liberado - mermado >= cant`), sin exigir stock en `InventarioSucursal.disponible` (el cual ya fue comprometido al abrir el turno en CU06).
    - `liquidar`: consume el cupo en `CupoCaja` (`cupo.consumido += cant`) y reduce `inv.comprometido_caja = max(0, inv.comprometido_caja - cant)`. **No** descuenta `inv.disponible` una segunda vez.
  - Cuando `dto.turno_caja_id` es `None`, opera contra `InventarioSucursal.disponible` como venta regular de mostrador.
- **Evidencia:**
  - Pruebas automatizadas en `test_cu19_caja_liquidacion.py`:
    - Caso stock libre 0 + cupo 1: la venta pasa exitosamente (201 Created), se consume el cupo y no hay error 409 ni inventario negativo.
    - Caso stock libre 1 + cupo 1: solo se consume el cupo de caja, el stock libre permanece intacto.
    - Reintentos idempotentes y rechazo cuando el turno está cerrado (409).

---

### G4. CU22 Stripe Elements en Checkout
- **Implementación:**
  - En `checkout.component.ts`: eliminación de elementos dummy/falsos en código de producción. Si Stripe.js no carga o falla `cardElement.mount()`, falla cerrado mostrando error visible al usuario.
  - `cardElementValido` se inicializa estrictamente en `false` y únicamente transiciona a `true` cuando el elemento real emite el evento `change` con `event.complete === true` y sin errores.
  - El botón de confirmación en la vista permanece deshabilitado mientras `cardElementValido` sea falso o esté en confirmación activa.
  - En `desmontarCardElement`, `cancelarFormularioTarjeta` y `ngOnDestroy`, se desmonta y destruye el Card Element y se purgan `clientSecretActual` y `preparacionPagoIdActual` de memoria.
- **Evidencia:**
  - Suite Karma: `checkout.component.spec.ts` prueba DOM con SDK ausente, error en mount, tarjeta incompleta (botón deshabilitado), error de tarjeta y tarjeta completa.

---

### G5. Avisos FCM Flutter y Web Push PWA
- **Implementación Flutter:**
  - Se agregaron `firebase_core: 5.1.0` y `firebase_messaging: 17.0.1` a `pubspec.yaml` y se resolvieron en `pubspec.lock` desde la caché local de pub.
  - `NativePlatformFcmAdapter` implementado sobre la API oficial de FlutterFire (`Firebase.initializeApp()`, `FirebaseMessaging.instance`).
  - Inicialización defensiva ante ausencia de `google-services.json` sin crashear.
  - Implementados: `requestPermission()` (Android 13+), `getToken()`, streams reactivos `onTokenRefresh`, `FirebaseMessaging.onMessage` (foreground) y `FirebaseMessaging.onMessageOpenedApp`.
  - Soporte de background con handler top-level estático `@pragma('vm:entry-point')` (`_firebaseMessagingBackgroundHandler`) y cold-start con `getInitialMessage()`.
  - Inyección de adaptador por constructor en `NotificacionMovilService({ApiClient? api, FcmAdapter? adapter})`. `SimulatedFcmAdapter` conservado para CI/tests.
  - Manifiesto Android: eliminada la entrada huérfana `<service android:name="com.google.firebase.messaging.FirebaseMessagingService" .../>`.
- **Implementación PWA:**
  - En `web-push.service.ts`, se eliminó la llamada duplicada a `/notificaciones/dispositivos`. Se realiza un único POST a `/notificaciones/web-push/subscripcion` enviando el `dispositivo_id` estable de `obtenerDispositivoId()`. Propagación de errores y revocación por ese mismo ID.
- **Evidencia:**
  - Flutter: `notificacion_movil_service_test.dart` (18/18 tests PASSED).
  - PWA: `web-push.service.spec.ts` (8/8 tests PASSED).
  - Compilación nativa Android: `flutter build apk --debug --no-pub` exitoso en 320.8s (`build\app\outputs\flutter-apk\app-debug.apk` generado).

---

### G6. Runner Móvil, Documentación y Regresión
- **Implementación:**
  - En `app-movil/run_tests.ps1`: eliminación de sentencias destructivas de borrado de `*.db*` y `*.sqlite*`. Implementada función `Invoke-FlutterWithTimeout` con `System.Diagnostics.Process`, timeout real configurable de 180s y terminación limpia de árbol de procesos (`taskkill /PID $p.Id /T /F`).
  - Rectificado `29-checkpoint-post-auditoria-28.md`: contrato 0.3.2, protocolo 0.4.0 y errata aclaratoria sobre la matriz de CUs.
  - OpenAPI sincronizado: 161 endpoints exportados en `backend/contratos/segundo-parcial/openapi-segundo-parcial.json`.
- **Evidencia:**
  - `run_tests.ps1 -Suite all`: Analizador 0 issues, 239 tests PASSED, exit 0.

---

## 3. Resumen cuantitativo de pruebas consolidadas

| Canal / Módulo | Suite ejecutada | Resultado | Tiempo / Estado |
|---|---|---|---|
| **Backend** | `pytest tests_segundo_parcial_bloque_b` (PostgreSQL `fashionstore_test`) | **245 passed** (0 failed, 5 warnings de dependencias) | 135.56 s |
| **Frontend Web** | `ng test --watch=false --browsers=ChromeHeadless` (Karma) | **284 passed** (0 failed) | 28.50 s |
| **Frontend Compilación** | `npx.cmd tsc -p frontend-web/tsconfig.app.json --noEmit` | **Exit 0** (0 errores de tipos) | 3.10 s |
| **Frontend Build** | `ng build` (producción) | **Exit 0** (Bundle generado con éxito) | 9.78 s |
| **App Móvil Tests** | `flutter test --no-pub` / `run_tests.ps1 -Suite all` | **239 passed** (0 failed) | 21.61 s |
| **App Móvil Análisis** | `flutter analyze --no-pub` | **0 issues found** | 3.10 s |
| **App Móvil Compilación** | `flutter build apk --debug --no-pub` | **EXITOSO** (`app-debug.apk` generado) | 320.80 s |
| **Contratos OpenAPI** | `backend/contratos/segundo-parcial/openapi-segundo-parcial.json` | **161 endpoints** sincronizados con `app.openapi()` | Verificado |
| **Integridad Git** | `git diff --check` en los 3 repositorios | **0 errores** de whitespace o formato | Limpio |
| **Gran Total** | **Pruebas automáticas totales aprobadas** | **768 passed (100% éxito)** | — |

---

## 4. Estado de Casos de Uso del Ciclo 2 (Entrega 2)

Conforme a las reglas del proyecto, **ningún caso de uso es declarado "Aceptado" de manera unilateral**. La columna dictamen formal se mantiene en **Entregado para revisión / Canales verificados (Avance sin aceptar)** a la espera del dictamen definitivo de la auditoría independiente Codex:

| CU | Nombre Oficial | Canales | Estado de Código | Evidencia Técnica de Cierre | Dictamen Formal |
|---|---|---|---|---|---|
| **CU05** | Compra diferida offline | B, W, M | Resuelto en código | DTO v3 estricto. Sanitizador PWA sin datos inventados. Omisión encola v3 y persiste `PENDIENTE_INTERVENCION` sin cargo. Pruebas: spec offline, test B2. | Entregado para revisión |
| **CU08** | Consulta stock multisede | B, W, M | Resuelto en código | Consulta multitenant por sucursal, stock libre y comprometido. | Entregado para revisión |
| **CU09** | Saldo cliente (Monedero) | B, W, M | Resuelto en código | Libro mayor inmutable, retenciones y liquidación presencial con saldo. | Entregado para revisión |
| **CU10** | Solicitud traslado | B, W, M | Resuelto en código | Solicitud entre sedes con validación de stock y estado `SOLICITADO`. | Entregado para revisión |
| **CU11** | Despacho traslado | B, W, M | Resuelto en código | Transición a `EN_TRANSITO` con Kardex. | Entregado para revisión |
| **CU19** | Venta presencial y Caja Stripe | B, W | Resuelto en código | Inicio PENDIENTE con `DetalleVenta` y `OrdenPago` inmutable. Endpoint `POST /stripe/ordenes/{id}/confirmar`. Reintento recupera secreto de pasarela y tasa congelada. PWA sin falso `CAPTURADO`. Reconciliación G3 con `CupoCaja` y stock. | Entregado para revisión |
| **CU20** | Devoluciones | B, W, M | Resuelto en código | Validación de 15 días desde entrega física (`entregada_en`), admisión en `PENDIENTE_EVALUACION` sin rechazo automático. | Entregado para revisión |
| **CU21** | Carrito durable online | B, W, M | Resuelto en código | Ofertas con precio congelado, estados ortogonales pago/cumplimiento. | Entregado para revisión |
| **CU22** | Pasarela Stripe / SetupIntent | B, W, M | Resuelto en código | Checkout PWA falla cerrado ante ausencia de SDK o error de mount. Validación interactiva estricta. Purga de secretos en memoria. FlutterFire oficial en móvil. | Entregado para revisión |
| **CU23** | Recepción traslado | B, W, M | Resuelto en código | Ingreso a sede destino y cierre de traslado con Kardex. | Entregado para revisión |
| **CU24** | Preparación pedidos | B, W, M | Resuelto en código | Estados por línea de pedido y control de empaque. | Entregado para revisión |
| **CU25** | Mermas | B, W, M | Resuelto en código | Registro clasificado de bajas con Kardex. | Entregado para revisión |
| **CU27** | Reembolsos | B, W, M | Resuelto en código | Derivación sobre fondos efectivamente capturados en moneda y centavos originales. | Entregado para revisión |

---

## 5. Limitaciones técnicas y declaraciones de entorno

1. **Stripe Test en Sandbox Real:** Las pruebas automáticas validaron el flujo vertical completo utilizando dobles de gateway con transiciones de estado fidedignas e inspección de centavos y monedas. La confirmación interactiva contra los servidores de Stripe requiere credenciales vivas y conectividad webhooks externa.
2. **Recepción Push en Dispositivo Físico:** FlutterFire oficial se encuentra completamente integrado y compilado en el APK debug (`build\app\outputs\flutter-apk\app-debug.apk`), y el backend cuenta con firma VAPID RFC 8292 y cifrado RFC 8291. La recepción física en hardware Android en segundo plano depende de la vinculación con un proyecto activo de Firebase Console con `google-services.json` de producción.
3. **Persistencia Git:** Todos los cambios permanecen en el árbol de trabajo (*working tree*) de la rama `feature/sp2-e2-integral` en los tres repositorios. No se realizó ningún commit, push, merge ni despliegue.
