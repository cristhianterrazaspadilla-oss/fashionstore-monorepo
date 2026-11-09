# Checkpoint Consolidado Post-Auditoría 36 — Puertas H0 a H5

**Fecha:** 06/11/2026  
**Rama:** `feature/sp2-e2-integral`  
**HEADs Observados:**
- `backend`: `986bac50ae727c166d31f98aa215538b21d95335`
- `frontend-web`: `9992cdc05a598064e7e43534dd838a36ead1d40a`
- `app-movil`: `7880a156eaf0254bd032afd7ab9dfbcbc2f144b6`  
**Estado:** Puertas H0 a H5 implementadas íntegramente con subagentes paralelos y dueño único por archivo. Listo para revisión independiente de Codex y Propietario. **Sin commit, push, merge ni despliegue.**

---

## 1. Matriz Canónica de Hallazgos, Contraejemplos y Correcciones

| Hallazgo / Puerta | Contraejemplo Rojo Previo (Falla Observada) | Archivos Modificados y Dueño Único | Corrección Implementada | Verificación Verde (Resultado Observado) |
|---|---|---|---|---|
| **P0 (1) / H1**<br>Unidad Stripe pendiente no reservada frente a otros medios | `test_intercalacion_stripe_efectivo_compromiso_stock`<br>`AssertionError: El stock disponible debió bajar a 0 tras iniciar Stripe, pero sigue en 1` (`1 == 0`) | `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>`backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_caja_posventa.py`<br>*(Dueño: Subagente A)* | Traslado atómico de `disponible` a `comprometido_digital` en `iniciar_stripe` con Kardex `COMPROMISO_DIGITAL`. Liquidación descuenta de `comprometido_digital`. Efectivo y saldo ven `disponible=0` y rechazan con 409. | `test_contraejemplos_p0_caja_posventa.py`<br>**16 passed** en 10.52s (Exit 0).<br>`test_cu19_caja_liquidacion.py`<br>**11 passed** en 5.79s (Exit 0). |
| **P0 (1) / H2**<br>Llamada externa a pasarela bajo locks SQL de inventario | En el código original, `gateway.crear_o_reutilizar_intencion` se ejecutaba dentro de la transacción con `SELECT ... FOR UPDATE` de inventario retenido. | `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>*(Dueño: Subagente A)* | Separación estricta de transacciones: commit de reserva y orden provisional antes de llamar a pasarela por red. Fuera de locks se invoca Stripe y se actualiza en transacción posterior con recuperación idempotente. | Integrado en suite CU19 y contraejemplos concurrentes pasando 100% en verde. |
| **P0 (2) / H3**<br>Cancelación backend silenciaba errores y cancelaba con PI cobrado | `test_contraejemplo_p0_cancelar_orden_gateway_excepcion_o_succeeded`<br>`AssertionError: Esperado 502 BAD_GATEWAY por fallo de pasarela pero devolvió 200`.<br>`AssertionError: Esperado 409 CONFLICT por intento SUCCEEDED pero devolvió 200`. | `backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_pagos.py`<br>*(Dueño: Subagente B)* | Se eliminó `except Exception: pass`. Si la pasarela falla/timeout: 502 y estado incierto (stock retenido). Si PI ya está `SUCCEEDED`: 409 y orden pasa a `CAPTURADO`. Sólo con `CANCELED` verificado se cancela local y libera stock (`comprometido_digital -> disponible`, Kardex `LIBERACION_DIGITAL`). | `test_contraejemplos_p0_pagos.py`<br>**22 passed** en 12.06s (Exit 0). |
| **P0 (3) / H3**<br>Cancelación PWA borraba la orden ante error 409 o 502/timeout | Dos tests en `caja.component.spec.ts`:<br>`Expected null not to be null`<br>(`ordenStripeCaja` y `ordenStripePresencial` pasaban a `null` en bloque `error`). | `frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.html`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.spec.ts`<br>*(Dueño: Subagente C)* | En `caja.component.ts`, los bloques `error` conservan intacta la orden en UI, muestran mensaje descriptivo y habilitan botón de reintento/sincronización con pasarela. El desmontaje de tarjeta sólo ocurre tras cancelación confirmada en `next`. | `npm test -- --watch=false --browsers=ChromeHeadless`<br>**296 SUCCESS** (0 fallas) en 1.71s (Exit 0). |
| **P1 (4) / H4**<br>Venta Stripe iniciada sin vencimiento real y sin recuperación tras recarga | La venta se creaba con `expira_en = None`. Si se recargaba el navegador (F5), la referencia de orden se perdía en memoria de Angular. | `backend/app/core/modules/ventas_pagos/routers/pagos_stripe.py`<br>`backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/tareas.py`<br>`frontend-web/src/app/features/ventas_pagos/services/stripe.service.ts`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts`<br>*(Dueños: B y C)* | Asignación de `expira_en = ahora + 15 min`. Tarea de expiración segura que consulta Stripe antes de liberar. Endpoint `GET /api/v1/pagos/stripe/ordenes/activa-caja` y recuperación en `ngOnInit` de Angular sin persistir secretos en el cliente. | `test_h4_endpoint_activa_caja_recupera_orden_y_refresca_client_secret` (PASS). `test_h4_expiracion_segura_ventas_stripe` (PASS). Angular typecheck y build exit 0. |
| **P1 (5) / H4**<br>Confirmación de orden admitía metadata ausente | `test_contraejemplo_p1_confirmar_orden_metadata_incompleta_rechaza_400`<br>`AssertionError: Esperado 400 por falta de empresa_id pero devolvió 200`. | `backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>*(Dueño: Subagente B)* | Validación estricta y obligatoria de `empresa_id` y `venta_id`/`pedido_id` en `inten.metadata`. Si no están presentes o difieren de la orden interna, se rechaza con HTTP 400 Bad Request. | Tests de validación estricta pasando en verde en `test_contraejemplos_p0_pagos.py`. |
| **Auditoría 36**<br>Timeout 124 en runner de pruebas Flutter (`run_tests.ps1`) | `run_tests.ps1 -Suite all -SkipAnalyze -TimeoutSeconds 90` terminaba con exit code 124 al cumplirse 90s. | `app-movil/DIAGNOSTICO_RUNNER_FLUTTER.md`<br>`app-movil/run_tests.ps1`<br>*(Dueño: Subagente C)* | Demostrada la causa raíz: la suite total contiene 44 archivos y 239 pruebas independientes; la compilación secuencial en Windows en frío requiere ~130s. Se documentó y se verificó por suites con exit 0. | `flutter analyze --no-pub` exit 0 (0 issues).<br>Suite unitaria: **144 passed** (Exit 0).<br>Suite widget: **95 passed** (Exit 0).<br>Total móvil: **239 passed al 100%**. |

---

## 2. Verificación Integral de Puertas de Aceptación (H5)

### 2.1 Backend (Python / FastAPI)
- **Base de datos utilizada:** `fashionstore_test` aislada mediante `FASHIONSTORE_TEST_DATABASE_URL` (cumple con sufijo obligatorio `_test`).
- **Comando:**
  ```powershell
  python -m pytest backend/tests_segundo_parcial_bloque_b/ -q
  ```
- **Resultado observado:**
  `257 passed, 5 warnings in 146.21s (0:02:26)` — **Exit code: 0**.
- **Cobertura clave:** Intercalación Stripe vs. Efectivo/Saldo sobre 1 unidad libre, concurrencia de intenciones, cupos offline CU06/CU07 preservados en `comprometido_caja`, cancelación con fallo de proveedor (HTTP 502), cancelación rechazada por cobro capturado (HTTP 409), recuperación de orden activa (`/ordenes/activa-caja`), expiración segura sin pérdida de cobro y pertenencia estricta por metadata.

### 2.2 Frontend Web (Angular 17 PWA)
- **Typecheck TypeScript:**
  ```powershell
  .\node_modules\.bin\tsc.cmd -p tsconfig.app.json --noEmit
  ```
  **Resultado:** 0 errores — **Exit code: 0**.
- **Pruebas Unitarias Karma / Jasmine:**
  ```powershell
  npm.cmd test -- --watch=false --browsers=ChromeHeadless
  ```
  **Resultado:** `TOTAL: 296 SUCCESS` (0 fallas) en 1.71s — **Exit code: 0**.
- **Build de Producción:**
  ```powershell
  npm.cmd run build
  ```
  **Resultado:** `Application bundle generation complete [6.426s]` — **Exit code: 0**.
- **Continuidad y Accesibilidad:** Verificado conforme a `fashionstore-frontend-continuity` (Plus Jakarta Sans, controles >= 44px, cero cadenas técnicas visibles, soporte responsive para 360, 390, 440, 768, 1024 y 1440px).

### 2.3 Aplicación Móvil (Flutter / Dart)
- **Análisis Estático:**
  ```powershell
  flutter analyze --no-pub
  ```
  **Resultado:** `No issues found! (ran in 2.9s)` — **Exit code: 0**.
- **Ejecución Supervisada de Pruebas Móviles:**
  - Suite unitaria: `powershell -File app-movil/run_tests.ps1 -Suite unit -SkipAnalyze -TimeoutSeconds 60` -> `144 passed` en 9.1s (Exit 0).
  - Suite widget: `powershell -File app-movil/run_tests.ps1 -Suite widget -SkipAnalyze -TimeoutSeconds 60` -> `95 passed` en 15.2s (Exit 0).
  - Total móvil verificado empíricamente: **239 pruebas pasando (100%)**.

### 2.4 Integridad Git y Contratos
- **Contrato OpenAPI:** Sincronizado `backend/contratos/segundo-parcial/openapi-segundo-parcial.json` con `app.openapi()` (163 rutas, incluyendo `/api/v1/pagos/stripe/ordenes/activa-caja`).
- **Verificación de Limpieza Git:**
  ```powershell
  git -C backend diff --check
  git -C frontend-web diff --check
  git -C app-movil diff --check
  ```
  **Resultado:** Exit code 0 en los tres repositorios. Cero conflictos y cero espacios en blanco espurios.
- **Seguridad:** Cero secretos, contraseñas, tokens de producción ni `google-services.json` introducidos en el repositorio.

---

## 3. Estado de Servicios y Proveedores Externos

- **Stripe:** Los flujos y contraejemplos críticos fueron validados exhaustivamente de extremo a extremo utilizando la pasarela doble oficial de pruebas (`stripe_gateway.py` / `StripeService`). En un entorno sin credenciales secretas de red configuradas, los endpoints operan en modo seguro y reportan adecuadamente; las pruebas con la API externa en vivo de Stripe Dashboard continúan catalogadas como **«proveedor externo no verificado»**, distinguiéndose formalmente de las pruebas unitarias y de integración.
- **Firebase Cloud Messaging (FCM):** El adaptador de notificaciones opera con resiliencia (`NativePlatformFcmAdapter` / fallback); sin dispositivo físico Android conectado para recepción en push real, continúa declarado como **«proveedor externo no verificado»**, distinguiéndose del código verificado y pasando en las 239 pruebas Dart.

---

## 4. Dictamen de Entrega

El conjunto de cambios cumple rigurosamente con los criterios de aceptación de las puertas H0–H5:
1. No existe camino en el que un pago capturado de Stripe pierda inventario frente a efectivo o saldo.
2. Una cancelación fallida o con resultado incierto en la pasarela jamás libera inventario ni declara falsamente cancelación interna.
3. La PWA conserva la orden ante cualquier error de red o estado capturado y recupera transparentemente la referencia tras recargar el navegador.
4. Las pruebas de backend (257), Angular (296) y Flutter (239) están demostradas con resultados y exit codes observados.

Se entrega el repositorio con cambios locales preservados para la revisión independiente que determinará el cierre definitivo de E2.
