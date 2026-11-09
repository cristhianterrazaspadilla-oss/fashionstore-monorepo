# Checkpoint Técnico 35 Posterior a Auditoría Independiente 33

**Fecha:** 06/11/2026  
**Ámbito:** Coordinador y 3 Subagentes en Paralelo (Subagente A: Backend Dinero/Inventario, Subagente B: Frontend Angular/PWA, Subagente C: Flutter/Entorno).  
**Contrato:** `version.json` 0.3.2, protocolo 0.4.0.  
**Dictamen:** Entrega 2 completamente implementada en código y verificada con pruebas automatizadas locales (**251 backend, 293 Angular, 239 Flutter = 783 pruebas pasadas**). **En avance para revisión independiente**. Cero commits, cero push, cero merge, cero despliegues; todos los cambios se conservan en el árbol de trabajo (*working tree*). La aceptación definitiva corresponde a la auditoría independiente de Codex y al propietario.

---

## 1. Línea Base y Disciplina Git (Puerta F0)

- **Repositorios y Ramas:**
  - `backend`: `feature/sp2-e2-integral`, base HEAD `986bac50ae727c166d31f98aa215538b21d95335`.
  - `frontend-web`: `feature/sp2-e2-integral`, base HEAD `9992cdc05a598064e7e43534dd838a36ead1d40a`.
  - `app-movil`: `feature/sp2-e2-integral`, base HEAD `7880a156eaf0254bd032afd7ab9dfbcbc2f144b6`.
- **Integridad de formato:** `git diff --check` ejecutado en los tres repositorios con **Exit Code 0** (0 errores de formato, sin trailing whitespaces).
- **Base de datos:** Todas las migraciones y pruebas backend se ejecutaron estrictamente sobre `fashionstore_test`, sin tocar `fashionstore_db`.
- **Secretos:** Ningún archivo contiene claves vivas de producción, secretos de Stripe, credenciales de base de datos ni tokens versionados.

---

## 2. Matriz Exhaustiva de Puertas de Corrección (F0–F5) y Hallazgos Auditoría 33

### Puerta F1: Captura Real Stripe en Ambas Cajas PWA (Hallazgo 1 Auditoría 33)
- **Defecto previo:** `caja.component.html` sólo mostraba intención y botón; no había Stripe Elements ni campo de tarjeta. `capturarStripeCaja` y `capturarStripePresencial` sólo consultaban `consultarOrdenPago` y las pruebas sustituían la captura con un mock de `consultarOrdenPago` que devolvía `CAPTURADO`.
- **Contraejemplo rojo:** Verificado en specs previas que la captura no ejecutaba el SDK de Stripe ni montaba elementos de tarjeta.
- **Corrección implementada:**
  - En `caja.component.html` se agregaron contenedores seguros `#stripe-card-element-caja` y `#stripe-card-element-presencial` en ambos paneles (caja con turno y venta presencial directa), con contenedores de error accesibles (`role="alert"`).
  - En `caja.component.ts`:
    - Montaje asíncrono dinámico de Stripe Card Element usando `environment.stripePublicKey` y el `client_secret` oficial retornado por `iniciar-stripe`.
    - Botón de cobro deshabilitado hasta que `cardElementValido && !capturandoStripe` para prevenir envíos de tarjeta incompleta o doble clic.
    - Captura real mediante SDK del cliente: `stripe.confirmCardPayment(clientSecret, { payment_method: { card } })`.
    - Soporte completo para 3DS/SCA cuando Stripe retorna `requires_action`.
    - Consulta y conciliación obligatoria con backend: tras `succeeded` del SDK, llamada a `POST /api/v1/pagos/stripe/ordenes/{id}/confirmar`. Sólo cuando el backend confirma centralmente `CAPTURADO`, se procede a liquidar la misma `venta_id`.
    - Limpieza y destrucción segura de elementos de tarjeta (`destroy()`) al salir o reiniciar.
- **Resultado verde:** Suite `caja.component.spec.ts` prueba el ciclo completo inyectando dobles del SDK de Stripe (tarjeta montada → llamada SDK → respuesta Stripe → confirmación central backend → liquidación de la misma venta). Pruebas de tarjeta incompleta, rechazo, 3DS cancelado, fallo de red y prevención de doble clic.

### Puerta F2: Inventario, Dinero y Seguridad Financiera (Hallazgos 2 y 3 Auditoría 33)
- **Defectos previos:**
  1. `iniciar_stripe` comprobaba cupos de caja offline si había `turno_caja_id` sin bloquear ni reservar, permitiendo que dos cajas generaran dos PaymentIntent para el mismo cupo; `liquidar` ejecutaba `max(0, comprometido_caja - cant)`.
  2. `confirmar_orden_pago` transicionaba a `CAPTURADO` con la sola condición `inten.estado == SUCCEEDED`, sin verificar ID, moneda USD, centavos exactos ni metadata de empresa y venta.
- **Contraejemplos rojos:**
  - CE1: `iniciar_stripe` con libre 0 / cupo 1 creaba PaymentIntent (201 en vez de 409).
  - CE2: Dos ventas concurrentes compitiendo por 1 unidad libre devolvían `[201, 201]`, cobrando doble intención.
  - CE3: Liquidación de Stripe con turno abierto decrementaba `comprometido_caja` en lugar de `disponible`.
  - CE4: `/pagos/stripe/ordenes/{id}/confirmar` aceptaba intenciones con moneda EUR o centavos adulterados y transicionaba a `CAPTURADO`.
- **Correcciones implementadas:**
  - En `venta_presencial_service.py`:
    - Decisión contractual del Plan 34 aplicada: **CU19 Stripe conectado consume exclusivamente stock libre (`InventarioSucursal.disponible`)**. Los cupos de caja offline (`CupoCaja`, `comprometido_caja`) quedan reservados para efectivo offline (CU06/CU07).
    - En `iniciar_stripe`: si `disponible < item.cantidad`, se rechaza **antes de crear el PaymentIntent** con HTTP 409 Conflict: *"Stock libre insuficiente para venta conectada Stripe (prenda asignada a caja offline o agotada)"*.
    - Concurrencia segura: bloqueo determinista de filas `InventarioSucursal` con `with_for_update()` ordenado y conteo de ventas presenciales en `PENDIENTE_PAGO`.
    - En `liquidar`: si `medio_pago == "STRIPE_TEST"`, se descuenta únicamente `fila_stock.disponible -= cant`. Se eliminó `max(0, comprometido_caja - cant)`. `comprometido_caja` y `cupo.consumido` permanecen intactos.
  - En `stripe_service.py`:
    - Endurecimiento estricto de `confirmar_orden_pago`: antes de transicionar a `CAPTURADO`, se verifica `inten.id == ref_pi`, `inten.moneda.lower() == "usd"`, `inten.monto_centavos == op.centavos_usd`, y metadata de seguridad (`empresa_id` y `venta_id`/`pedido_id`). Si alguna discrepa, rechaza con HTTP 400 Bad Request sin modificar el estado de la orden.
    - Idempotencia estricta en webhooks y consultas repetidas: si la orden ya está en `CAPTURADO`, se devuelve el DTO sin duplicar Pagos ni Kardex.
    - Captura seguida de fallo de liquidación: la venta permanece en `PENDIENTE_PAGO` con orden capturada; no se borra la venta; se permite reintento de liquidación o tramitar conciliación/reembolso CU27.
- **Resultado verde:** 43 tests pasando al 100% en `test_cu19_caja_liquidacion.py`, `test_contraejemplos_p0_caja_posventa.py` y `test_contraejemplos_p0_pagos.py`.

### Puerta F3: Cancelación y Recuperación (Hallazgo 4 Auditoría 33)
- **Defecto previo:** `cancelarStripeCaja` y `cancelarStripePresencial` sólo ponían la variable local a `null` sin notificar al backend, perdiendo cobros capturados.
- **Contraejemplo rojo:** CE5 fallaba con HTTP 404 Not Found porque no existía endpoint de cancelación.
- **Correcciones implementadas:**
  - Backend: Nuevo endpoint `POST /api/v1/pagos/stripe/ordenes/{id}/cancelar` en `pagos_stripe.py` y `stripe_service.py`.
    - Si la orden está en `PENDIENTE` o `REQUIERE_ACCION_CLIENTE`, cancela la orden (`CANCELADO`) y la Venta asociada (`CANCELADA`), y cancela la intención en Stripe si aplica.
    - Si la orden ya está en `CAPTURADO`, rechaza con HTTP 409 Conflict impidiendo ocultar el pago capturado.
  - Frontend:
    - En `caja.component.ts`, `cancelarStripeCaja` y `cancelarStripePresencial` invocan `stripeService.cancelarOrdenPago(ordenId)` en backend para órdenes cancelables.
    - Si la orden ya está en `CAPTURADO` o en estado incierto por caída de red, se prohíbe el borrado local a `null`: la orden permanece visible en pantalla con badges de advertencia y opciones para liquidar venta o conciliar.
- **Resultado verde:** CE5 verificado pasando en backend; specs de cancelación y protección de capturados pasando en Angular.

### Puerta F4: Observaciones Secundarias (CU05, CU22 y Push)
- **CU05 `sanitizarAutorizacionCobro`:**
  - Endurecimiento completo en `sincronizacion-offline.service.ts`:
    - Validación regex UUID RFC 4122 para `consentimiento_id`, `tasa_id`, `preparacion_pago_id`.
    - Validación regex SHA-256 de 64 caracteres hex para `huella_compra`.
    - Validación numérica de importes positivos (`base_bob`, `total_bob`, `importe_cobro`, `tasa_bob_por_usd` > 0) y no negativos (`descuento_bob`, `envio_bob` >= 0).
    - Parseo estricto de fechas ISO válidas.
    - Validación de `permite_cobro_al_reconectar === true`.
    - Ante cualquier dato parcial o mal formado, retorna `undefined`, la PWA omite el objeto y la solicitud se encola en v3 pasando a `PENDIENTE_INTERVENCION` sin cargo.
    - Si la API backend recibe un objeto parcial/inválido directamente, backend responde con HTTP 422 (`extra="forbid"`).
- **CU22 Retiro de emulador productivo:**
  - Retiro definitivo de `window['stripeElementsEmulator']` y `window['StripeEmulator']` del código en tiempo de ejecución de `checkout.component.ts`.
  - Dobles de prueba entran exclusivamente por inyección en tests.
- **Push FCM y Web Push:**
  - Adaptadores oficiales de FlutterFire (`firebase_core`, `firebase_messaging`) y RFC 8292/8291 Web Push conservados sin regresiones.
- **Resultado verde:** Specs de `sincronizacion-offline.service.spec.ts` y `checkout.component.spec.ts` pasando al 100%.

### Puerta F5: Regresión Completa y Documentación
- **Runner Móvil de Flutter (Hallazgo G6 de Auditoría 33):**
  - Causa raíz investigada y documentada: `flutter analyze --no-pub` en Windows 11 con Windows Defender toma ~29-38s en frío. Un timeout global de 45s estrangulaba la fase preliminar de análisis estático con exit 124.
  - Corrección en `run_tests.ps1` y `test_diagnostic.ps1`:
    - Temporizadores desacoplados: `-AnalyzeTimeoutSeconds 120` y `-TimeoutSeconds 180` por defecto.
    - Monitoreo con pulso (*heartbeat*) en consola cada 5s indicando PID y tiempo transcurrido, descartando cualquier sospecha de buffering o cuelgue.
    - Soporte de `-SkipAnalyze` y suites selectivas.
    - Comando de auditoría 33 (`run_tests.ps1 -Suite unit -TimeoutSeconds 45`): **Pasa exitosamente en 13.15s con Exit Code 0** (144 tests pasados).
- **OpenAPI canónico:**
  - Actualizado y exportado en `backend/contratos/segundo-parcial/openapi-segundo-parcial.json` con **162 endpoints** sincronizados con `app.openapi()`, incluyendo el nuevo `POST /api/v1/pagos/stripe/ordenes/{id}/cancelar`.

---

## 3. Evidencia Automatizada de Pruebas Multi-Repo

| Repositorio | Comando de Ejecución | Resultados | Tiempo | Exit Code |
|---|---|---|---|:---:|
| **Backend FastAPI** | `$env:FASHIONSTORE_TEST_DATABASE_URL="postgresql+asyncpg://postgres:CLAVE@127.0.0.1:5432/fashionstore_test"; python -m pytest backend/tests_segundo_parcial_bloque_b -q` | **251 passed, 5 warnings** (0 failed) | 119.88 s | `0` |
| **Backend Subagente A** | `python -m pytest backend/tests_segundo_parcial_bloque_b/test_cu19_caja_liquidacion.py backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_caja_posventa.py backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_pagos.py -q` | **43 passed, 1 warning** (0 failed) | 20.70 s | `0` |
| **Frontend Angular (TSC)** | `cmd.exe /c "cd frontend-web && npx tsc -p tsconfig.app.json --noEmit && npx tsc -p tsconfig.spec.json --noEmit"` | **0 errores de tipos** | 8.20 s | `0` |
| **Frontend Angular (Build)** | `cmd.exe /c "cd frontend-web && npm run build"` | **Compilación de producción exitosa** (`dist/fashionstore-web`) | 9.46 s | `0` |
| **Frontend Angular (Karma)** | `npm.cmd --prefix frontend-web test -- --watch=false --progress=false` | **293 SUCCESS, 0 FAILED** | 31.42 s | `0` |
| **App Móvil (Analyze)** | `powershell -Command "Set-Location app-movil; flutter.bat analyze --no-pub"` | **0 issues found** | 2.90 s | `0` |
| **App Móvil (Unit)** | `powershell -Command "Set-Location app-movil; flutter.bat test --no-pub --reporter expanded test/unit/"` | **144/144 passed** | 7.10 s | `0` |
| **App Móvil (Widget)** | `powershell -Command "Set-Location app-movil; flutter.bat test --no-pub --reporter expanded test/widget/ test/widget_test.dart"` | **95/95 passed** | 11.80 s | `0` |
| **App Móvil (Completa)** | `powershell -Command "Set-Location app-movil; flutter.bat test --no-pub --reporter expanded"` | **239/239 passed** | 18.20 s | `0` |
| **App Móvil (Runner F45)** | `powershell -File app-movil/run_tests.ps1 -Suite unit -TimeoutSeconds 45` | **144 tests passed** (analyze + unit) | 13.15 s | `0` |
| **App Móvil (Runner Completo)** | `powershell -File app-movil/run_tests.ps1 -Suite all -TimeoutSeconds 180` | **239 tests passed** (analyze + all) | 25.30 s | `0` |
| **OpenAPI Schema** | Sincronización con `app.openapi()` | **162 endpoints verificados** | 3.50 s | `0` |
| **Integridad Git** | `git diff --check` en `backend`, `frontend-web` y `app-movil` | **0 advertencias / 0 errores** | 0.95 s | `0` |

**Total de pruebas automatizadas locales verificadas: 251 + 293 + 239 = 783 tests pasados.**

---

## 4. Declaración Explícita de Límites Externos No Ejecutados

Conforme a las reglas de honradez contractual del proyecto:
1. **Stripe Test Live Interactivo:**
   - No se ejecutó confirmación con tarjeta Stripe real en la pasarela externa de producción con 3DS Challenge en vivo, dado que requiere credenciales secretas y navegador humano interactivo.
   - El protocolo, los dobles del SDK inyectados en test, el manejo de `client_secret`, la verificación de estados del PaymentIntent y la validación de montos/moneda están verificados y pasan al 100%.
2. **Recepción Push FCM en Dispositivo Físico:**
   - No se ejecutó entrega de mensajes push en hardware físico Android/iOS, ya que requiere proyecto aprovisionado en Firebase Console, certificados TLS y terminal físico con Google Play Services.
   - La arquitectura oficial de FlutterFire, encolado SQLite local, adaptadores de canal y fallback a `EstadoFcm.noConfigurado` están verificados y pasan al 100%.
3. **Prueba Física de Desconexión / Modo Avión:**
   - Validada mediante emulación de desconexión en navegador / tests de timeout, no con hardware móvil físico en mano.

---

## 5. Disciplina Git y Árbol de Trabajo

- **Ramas:**
  - `backend`: `feature/sp2-e2-integral`
  - `frontend-web`: `feature/sp2-e2-integral`
  - `app-movil`: `feature/sp2-e2-integral`
- **Commits:** **0 commits** realizados por el agente en esta sesión.
- **Pushes / Merges / Despliegues:** **0**.
- **Estado:** Todos los archivos permanecen en el árbol de trabajo (*working tree*) para la inspección previa de Codex y la decisión de registro por parte del propietario.
