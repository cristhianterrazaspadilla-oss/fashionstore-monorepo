# Guía de reanudación para otro chat

> **Punto de partida vigente (06/11/2026):** leer primero [checkpoint 47](47-ejecucion-plan-46.md), [estado por CU](02-estado-cu.md) y [bitácora](04-bitacora.md). El plan 46 fue aprobado y ejecutado parcialmente. No repetir como estado actual las observaciones del informe 45 o el checkpoint 44: sus flujos Stripe se reforzaron y E2 pasó 290 pruebas, pero la regresión heredada amplia y la suite Flutter siguen sin una puerta verde.

> **Dictamen independiente vigente (06/11/2026):** leer [informe 45](45-informe-final-auditoria-checkpoint-44.md) antes del checkpoint 44. E2 sigue en avance sin aceptar: webhook y liquidación presencial permiten captura con datos financieros incompletos; la cancelación de una orden provisional puede liberar stock sin conciliar un PI creado antes de la caída. Cobertura 27/27 CU, cierre técnico registrado 14/27. No registrar commits de aceptación hasta corregir y volver a probar.

> **Checkpoint técnico vigente post-auditoría 42 (06/11/2026):** leer [44-checkpoint-post-auditoria-42.md](44-checkpoint-post-auditoria-42.md). E2 permanece en **avance sin aceptar** para la revisión independiente del propietario y Codex. Se implementaron íntegramente las correcciones de las cuatro puertas J1–J4 del [plan 43](43-plan-cierre-post-auditoria-42.md):
> - **J1 (P0-1) Cancelación manual Stripe segura:** `cancelar_orden_pago` exige confirmación explícita `CANCELED` de Stripe. Respuestas no-canceled (`REQUIRES_PAYMENT_METHOD`, `PROCESSING`), ID ajeno o fallos de red lanzan HTTP 502 Bad Gateway y retienen la venta, la orden y el stock intactos sin Kardex `LIBERACION_DIGITAL`.
> - **J2 (P0-2) Validación de captura en todas las rutas:** `_validar_intencion_con_orden` obligatoria en webhook firmado, continuación 3DS (`continuar_accion`) y liquidación presencial. Cualquier discrepancia de ID, moneda USD, centavos o metadata (`empresa_id`, `venta_id`) rechaza con HTTP 400 Bad Request y la orden permanece PENDIENTE. En liquidación presencial, la excepción de pasarela lanza 502 y retiene stock.
> - **J3 (P0-3) Liquidación con importes congelados:** La liquidación de ventas iniciadas (`STRIPE_TEST`) consume exclusivamente `Venta.total` y `DetalleVenta` persistidos. La alteración posterior de catálogo o promociones no bloquea ni altera la entrega.
> - **J4 (P1) Reanudación de órdenes provisionales:** Órdenes creadas con `PENDIENTE_{clave}` se recuperan vía `POST /api/v1/pagos/stripe/ordenes/{id}/reanudar` usando la `venta.clave_idempotencia` durable sin duplicar venta ni Kardex. Activa-caja no expone `PENDIENTE_...` (`null` y `PROVISIONAL_PENDIENTE_INTENTO`) y Angular despliega aviso accesible y botón "Reanudar Cobro Stripe".
> - **Métricas de suites verificadas:** Backend **66 passed** en suites afectadas de Bloque B (`test_contraejemplos_p0_auditoria_42`, `test_subagente_a`, `test_subagente_b`, `test_contraejemplos_p0_auditoria_39`, `test_cu19`, `test_b1_finanzas`, `test_openapi`); Angular Karma **303/303 SUCCESS** (ChromeHeadlessNoSandbox), `tsc` app/spec exit 0, `ng build` exit 0; Flutter `analyze` 0 issues. OpenAPI con 164 endpoints sincronizados. `git diff --check` limpio en los 3 repositorios. Cero commits, cero push, cero merge, cero despliegues.

> **Dictamen histórico de partida, auditoría independiente 42 (06/11/2026):** leer [42-auditoria-independiente-post-checkpoint-41.md](42-auditoria-independiente-post-checkpoint-41.md). Previo al Checkpoint 44.

> **Checkpoint técnico vigente post-auditoría 39 (06/11/2026):** leer [41-checkpoint-post-auditoria-39.md](41-checkpoint-post-auditoria-39.md). E2 permanece en **avance sin aceptar** para la revisión independiente del propietario y Codex. Se implementaron íntegramente las correcciones de los tres bloqueos P0 del [plan 40](40-plan-cierre-post-auditoria-39.md):
> - **P0-1 Vencimiento sin liberación en incertidumbre:** Erradicado `except Exception: pass`. Si `cancelar_intencion` falla por red/timeout (502/503), rollback de la venta, omisión para reintento del worker, stock `comprometido_digital` intacto, cero Kardex `LIBERACION_DIGITAL`. Ante captura concurrente (Stripe 400 / `SUCCEEDED`), sincroniza `op.estado = "CAPTURADO"` y nunca libera stock.
> - **P0-2 Recuperación real de caja tras F5:** Endpoint `GET /api/v1/pagos/stripe/ordenes/activa-caja` retorna `OrdenActivaCajaDTO` con `venta_id`, `stripe_payment_intent_id`, tasa congelada, líneas persistidas desde `DetalleVenta`, procedencia (`TURNO_OFFLINE` / `PRESENCIAL`) y estado de verificación. Angular restaura el panel correspondiente con sus líneas y permite liquidar la misma venta tras recarga (F5) sin reiniciar PaymentIntent.
> - **P0-3 Validación financiera única antes de CAPTURADO:** Rutina compartida `_validar_intencion_con_orden` obligatoria en confirmación, recuperación y vencimiento. Rechazo HTTP 400 ante discrepancias de ID, moneda USD, centavos o metadata. Ante caídas de pasarela se retorna `estado_verificacion = "NO_VERIFICADO_ERROR_PASARELA"` sin silenciar con pass.
> - **Métricas de suites verificadas:** Backend **267 passed** (PostgreSQL `fashionstore_sp2_bloque_b_test`, 237.93s); Angular Karma **300/300 SUCCESS** (ChromeHeadlessNoSandbox), `tsc` exit 0, `ng build` exit 0; Flutter `analyze` 0 issues. OpenAPI con 163 rutas y 214 esquemas. `git diff --check` limpio en los 3 repositorios. Cero commits, cero push, cero merge, cero despliegues.

> **Dictamen histórico de partida, auditoría independiente 39 (06/11/2026):** leer [39-auditoria-independiente-post-checkpoint-38.md](39-auditoria-independiente-post-checkpoint-38.md) para entender el encargo anterior. La auditoría 42 anterior define el estado actual.

> **Checkpoint técnico previo post-auditoría 36 (06/11/2026):** leer [38-checkpoint-post-auditoria-36.md](38-checkpoint-post-auditoria-36.md).
> - **Compromiso durable de stock:** Traslado atómico a `comprometido_digital` con Kardex `COMPROMISO_DIGITAL`. Liquidación descuenta de `comprometido_digital`. Efectivo y saldo ven `disponible=0` y rechazan con 409. Llamada a pasarela fuera de locks SQL de inventario.
> - **Cancelación honesta:** Erradicado `except Exception: pass`. Si la pasarela falla o hay timeout, se responde 502 Bad Gateway y la orden/venta permanecen en `PENDIENTE` reteniendo el stock. Si el intento ya fue capturado (`SUCCEEDED`), se actualiza a `CAPTURADO` y se rechaza con 409 Conflict. Sólo con `CANCELED` verificado se cancela local y se libera inventario.
> - **Caja PWA & Recuperación:** En `caja.component.ts`, los bloques `error` conservan la orden visible en UI ante 409 o 502/timeout, permitiendo sincronización y reintento. Endpoint `GET /api/v1/pagos/stripe/ordenes/activa-caja` implementado para recuperación segura tras recarga sin almacenar secretos en el cliente.
> - **Expiración y metadata:** `Venta(PENDIENTE_PAGO)` con `expira_en` a 15 min. Tarea en `tareas.py` consulta Stripe antes de liberar stock. Confirmación exige obligatoriamente `empresa_id` y `venta_id`/`pedido_id` en metadata.
> - **Métricas de suites verificadas:** Backend **257 passed** (`fashionstore_test`, 146.21s); Angular Karma **296/296 SUCCESS**, `tsc` exit 0, `ng build` exit 0; Flutter **239/239 passed**, `analyze` 0 issues. OpenAPI con 163 rutas. `git diff --check` limpio en los 3 repositorios. Cero commits, cero push, cero merge, cero despliegues.

> **Dictamen previo, auditoría independiente 36 (06/11/2026):** [36-auditoria-independiente-post-checkpoint-35.md](36-auditoria-independiente-post-checkpoint-35.md). E2 seguía **en avance sin aceptar**, motivando la ejecución del Plan 37 y el Checkpoint 38.

> **Reporte histórico del agente, posterior a Auditoría Independiente 33 (06/11/2026):** leer [35-checkpoint-post-auditoria-33.md](35-checkpoint-post-auditoria-33.md) como entrega del implementador. Declaró **251 backend, 293 Angular, 239 Flutter = 783 pruebas pasadas** y F0–F5 completos. La auditoría 36 prevalece para el estado funcional. Cero commits, push, merge o despliegues; cambios en el árbol de trabajo.
> - **CU19:** Ambas cajas PWA (con turno y directa) montan Stripe Elements real (`#stripe-card-element-caja`, `#stripe-card-element-presencial`), capturan con `stripe.confirmCardPayment` usando `client_secret` oficial, soportan 3DS/SCA, sincronizan confirmación central en backend y liquidan la misma venta una sola vez. Concurrencia segura entre cajas concurrentes bajo `with_for_update()`.
> - **Inventario y Dinero (F2):** CU19 conectado consume exclusivamente stock libre (`disponible`). Con libre 0 / cupo 1 rechaza con 409 Conflict antes de crear PaymentIntent. Descuento en liquidación sólo afecta `disponible`, preservando cupos offline de CU06/CU07 (`comprometido_caja` y `cupo.consumido` intactos; `max(0, comprometido_caja - cant)` retirado).
> - **Seguridad Financiera y Cancelación (F2/F3):** `/pagos/stripe/ordenes/{id}/confirmar` valida ID de PI, moneda USD, centavos exactos (`op.centavos_usd`), y metadata de empresa/venta antes de `CAPTURADO`. Endpoint `POST /api/v1/pagos/stripe/ordenes/{id}/cancelar` implementado; si ya está capturado, rechaza con 409 impidiendo ocultar pagos.
> - **CU05 / CU22 (F4):** Sanitizador en Angular valida UUID RFC 4122, SHA-256 64 hex, importes positivos y fechas ISO válidas, omitiendo datos parciales antes de v3. Retiro definitivo de `window.stripeElementsEmulator` en producción.
> - **Runner Flutter (F5):** Timeout estrangulado de 45s diagnosticado y corregido; runner con temporizadores desacoplados (`-AnalyzeTimeoutSeconds 120`, `-TimeoutSeconds 180`), heartbeat cada 5s y terminación limpia de árbol de procesos con `taskkill`. La prueba focalizada que falló en auditoría 33 pasa exitosamente en 13.15s con Exit Code 0. Documentado en `DIAGNOSTICO_RUNNER_FLUTTER.md`.

> **Dictamen vigente de partida, auditoría independiente 33 (05/11/2026):** leer [33-auditoria-independiente-post-checkpoint-32.md](33-auditoria-independiente-post-checkpoint-32.md) y [34-plan-final-cierre-post-auditoria-33.md](34-plan-final-cierre-post-auditoria-33.md). Corresponde a Codex y al propietario auditar la entrega actual y determinar la aceptación.

> **Contrato y protocolo vigentes:** La versión general del contrato es **0.3.2** y la versión de protocolo es **0.4.0** (RFC 8291 y RFC 8292 corresponden a estándares de Web Push IETF). OpenAPI canónico sincronizado con **162 endpoints**.

> **Reporte histórico del agente, posterior a Auditoría Independiente 28 (05/11/2026):** leer [28-auditoria-independiente-post-checkpoint-27.md](28-auditoria-independiente-post-checkpoint-27.md) y [29-checkpoint-post-auditoria-28.md](29-checkpoint-post-auditoria-28.md). El agente declaró resueltos los bloqueos P0 y reportó suites automáticas en los tres canales; la auditoría 30 encontró rutas críticas abiertas:
> - **CU22/CU05:** Stripe Elements montado interactivamente en DOM de PWA (`#card-element`), `confirmCardSetup` con el elemento y desmontaje en `ngOnDestroy`.
> - **CU05:** Payload offline estrictamente limitado a 15 campos v3. `AutorizacionCobroV3DTO` con `moneda_cobro: "USD"` obligatorio sin default y `extra="forbid"`. Omisión usa v3 y persiste `PENDIENTE_INTERVENCION`. Rechazo HTTP 422 comprobado.
> - **Push Multi-Canal:** FCM v1 con OAuth2 RS256 de cuenta de servicio. Web Push RFC 8292 (VAPID ES256) y RFC 8291 (`aes128gcm` RFC 8188 con protección SSRF). Outbox con aislamiento por destino y estado `FALLIDO_PARCIAL`. PWA con Service Worker activo y PushManager. Flutter con adaptadores FCM y receptor en `AndroidManifest.xml`.
> - **CU19:** Eliminación total de `orden_stripe.venta_id = venta.id`. Venta inicial en `PENDIENTE_PAGO` con `DetalleVenta` y promociones oficiales. `OrdenPago(contexto="VENTA", venta_id=venta.id)` inmutable. Endpoint canónico `/iniciar-stripe`. Liquidación atómica sin reasignación. Caja sin input libre `pi_...`.
> - **Runner Flutter:** Causa raíz demostrada en `DIAGNOSTICO_RUNNER_FLUTTER.md` (falta de `--no-pub` e inspección de Windows Defender en subprocesos Dart). Entregados scripts reproducibles `run_tests.ps1` y `test_diagnostic.ps1`. **234/234 tests PASSED en 35.37s** y analyze 0 issues.
>
> Cero commits, cero push, cero merge, cero despliegues. Cambios desestibados en el árbol de trabajo (*working tree*).

---

**Fecha de corte:** 05/11/2026. **Fuentes operativas vigentes:** [auditoría 30](30-auditoria-independiente-post-checkpoint-29.md), [plan 31](31-plan-correccion-y-puertas-cierre-e2.md), [estado de CUs](02-estado-cu.md) y [bitácora](04-bitacora.md). Contrato 0.3.2, protocolo 0.4.0; RFC 8291 y RFC 8292 son estándares Web Push.

## Historial del checkpoint 29; no equivale a aceptación

- **E1 comprende 14 CU:** CU01, CU02, CU03, CU04, CU06, CU07, CU12, CU13, CU14, CU15, CU16, CU17, CU18 y CU26. Conserva sus commits de línea base registrados: backend `8b42fef` / `d548b94`, frontend `9992cdc` y Flutter `7880a15`.
- **E2 comprende 13 CU:** CU09, CU22, CU27, CU21, CU19, CU05, CU20, CU08, CU25, CU23, CU24, CU10 y CU11.
- **Resultados del checkpoint 29:** backend y Angular se corroboraron en la auditoría 30; la cifra móvil sólo fue reportada por el agente.
  - Backend FastAPI: **239 passed, 0 failed en 130.42s** en `tests_segundo_parcial_bloque_b` sobre PostgreSQL `fashionstore_test` en Alembic 0014.
  - Frontend Angular: `npx.cmd tsc -p tsconfig.app.json --noEmit` exit 0, **270 passed, 0 failed** en Karma, `npm.cmd run build` exit 0.
  - App Móvil Flutter: `flutter analyze --no-pub` 0 issues; **234 passed** en `run_tests.ps1` fue informado por el agente, sin corroboración independiente.
  - Total **743 pruebas** fue declarado en el checkpoint 29; no acredita cierre funcional ni reproducción independiente de Flutter.
- **Política de versiones y ramas:**
  - Repositorios en rama `feature/sp2-e2-integral`.
  - **Cero commits nuevos, cero push, cero merge, cero despliegues.** Todas las correcciones permanecen en el árbol de trabajo (*working tree*) para revisión e inspección manual del usuario y la auditoría externa.
  - Ningún CU se marca como «Aceptado» unilateralmente; los 13 CU E2 están en «Avance sin aceptar».
- **Base local:** PostgreSQL `fashionstore_db` en `127.0.0.1:5432`, base de pruebas `fashionstore_test` en revisión Alembic `0014_pago_ref_externa_unique`.

## Primeros pasos en un nuevo chat

1. Leer `README.md`, `02-estado-cu.md`, `30-auditoria-independiente-post-checkpoint-29.md`, `31-plan-correccion-y-puertas-cierre-e2.md` y `04-bitacora.md`. Consultar el checkpoint 29 sólo como historial del implementador.
2. Consultar `git status --short`, rama y `git rev-parse HEAD` por separado en `backend`, `frontend-web` y `app-movil`. Preservar cualquier cambio no comiteado existente en el working tree.
3. Para ejecutar pruebas de backend:
   ```powershell
   $env:FASHIONSTORE_TEST_DATABASE_URL="postgresql+asyncpg://postgres:CLAVE_LOCAL@127.0.0.1:5432/fashionstore_test"
   python -m pytest backend/tests_segundo_parcial_bloque_b -v
   ```
4. Para frontend web:
   ```powershell
   cd frontend-web
   npm.cmd test -- --watch=false --progress=false
   npm.cmd run build
   ```
5. Para app móvil (runner reparado y seguro con timeout real de 180s y sin borrado de archivos):
   ```powershell
   cd app-movil
   flutter analyze --no-pub
   .\run_tests.ps1 -Suite all
   ```
6. El usuario y Codex deciden cuándo integrar, commitear o desplegar tras la re-auditoría independiente.
