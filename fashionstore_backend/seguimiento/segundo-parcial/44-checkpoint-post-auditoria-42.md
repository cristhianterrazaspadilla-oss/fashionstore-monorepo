# Checkpoint Técnico 44 — Entrega Posterior a la Auditoría Independiente 42

**Fecha:** 06/11/2026 (Bolivia)  
**Estado:** Avance técnico sin aceptar, listo para revisión independiente del propietario y Codex.  
**Ramas activas:** `feature/sp2-e2-integral` en `backend`, `frontend-web` y `app-movil`.  
**Dictamen de partida:** [Auditoría independiente 42](42-auditoria-independiente-post-checkpoint-41.md).  
**Plan de ejecución:** [Plan 43](43-plan-cierre-post-auditoria-42.md), [Prompt E2](prompts/E2-cierre-auditoria-42-subagentes.md) e [Interfaz Compartida](interfaz-compartida-auditoria-42.md).  
**Regla de custodia:** Cero commits, cero push, cero merge, cero despliegues. Cambios conservados íntegramente en el working tree sin alterar ramas ni repositorios externos.

---

## 1. Matriz de Puertas de Calidad J0 a J5 (Auditoría 42)

| Puerta | Requerimiento / Causa Raíz Auditoría 42 | Corrección Implementada | Evidencia Roja (Contraejemplo) | Evidencia Verde (Solución) | Archivos y Dueños Únicos |
|---|---|---|---|---|---|
| **J0 — Coordinación y Dueño Único** | Riesgo de colisiones concurrentes entre subagentes en archivos críticos de caja, pagos y contratos. | Establecido contrato estricto de propiedad de archivos en `interfaz-compartida-auditoria-42.md`. 3 subagentes paralelos ejecutados sin pisar archivos ajenos. | N/A (Estructural). Verificado que ningún subagente modificó archivos fuera de su frontera. | Verificado con `git status` y marcas de tiempo de escritura: cero solapamientos. | Subagente A: Stripe Backend.<br>Subagente B: Venta/Inventario Backend.<br>Subagente C: Angular Frontend.<br>Coordinador: Integración y Checkpoint. |
| **J1 (P0-1) — Cancelación Stripe Manual Segura** | `cancelar_orden_pago` liberaba stock ante errores de red/timeout o respuestas no canceladas (`REQUIRES_PAYMENT_METHOD`, `PROCESSING`) en pasarela. | `cancelar_orden_pago` ahora exige estrictamente que el gateway confirme `inten.estado == 'CANCELED'` y que el ID coincida con el solicitado. Si el gateway responde `REQUIRES_PAYMENT_METHOD`, `PROCESSING`, ID ajeno o falla por red/timeout, lanza HTTP 502 Bad Gateway; la orden y la venta se conservan `PENDIENTE` y `PENDIENTE_PAGO` y el stock comprometido permanece intacto con 0 Kardex `LIBERACION_DIGITAL`. Si devuelve `SUCCEEDED`, sincroniza a `CAPTURADO` y rechaza con 409 Conflict sin liberar stock. | `test_j1a` a `test_j1d`:<br>En código no parcheado, respuestas no-canceled cancelaban localmente la venta y liberaban `comprometido_digital` con Kardex espurio. | `test_j1a...` PASSED.<br>`test_j1b...` PASSED.<br>`test_j1c...` PASSED.<br>`test_j1d...` PASSED.<br>DB: `Venta.estado='PENDIENTE_PAGO'`, `OrdenPago.estado='PENDIENTE'`, stock comprometido retenido, cero movimientos Kardex `LIBERACION_DIGITAL`. | `backend/app/core/modules/ventas_pagos/services/stripe_service.py` (`cancelar_orden_pago`).<br>Subagente A. |
| **J2 (P0-2) — Validación de Captura en Todas las Rutas** | `confirmarWebhook` y `continuar_accion` (3DS) marcaban `CAPTURADO` sin validar moneda USD, centavos ni metadata (`empresa_id`, `venta_id`). En `liquidar`, una caída de pasarela se silenciaba con `pass`. | Extraída validación rigurosa unificada `_validar_intencion_con_orden` obligatoria en webhook, 3DS y liquidación presencial. Webhook y 3DS validan ID, moneda USD, centavos exactos y metadata de tenant y venta; ante cualquier discordancia rechazan con HTTP 400 Bad Request y la orden permanece `PENDIENTE`. En `liquidar`, el `except: pass` fue erradicado: ante caída de red o pasarela no verificada, lanza HTTP 502 Bad Gateway reteniendo la venta y el stock. | `test_j2a` a `test_j2d` y `test_j2b_liquidar...`:<br>Webhooks con centavos o metadata discordante marcaban `CAPTURADO` con 200.<br>En liquidación con pasarela caída, respondía 201 Created silenciando el fallo. | `test_j2a` a `test_j2d`: PASSED (400 Bad Request y orden permanece PENDIENTE).<br>`test_j2b_liquidar...`: PASSED (502 Bad Gateway y retiene stock). | `backend/app/core/modules/ventas_pagos/services/stripe_service.py`, `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`.<br>Subagentes A y B. |
| **J3 (P0-3) — Liquidación con Importes Congelados** | `liquidar` recalculaba contra `VarianteProducto.precio` y `PromocionService.mejorDescuento` actuales. Si el catálogo cambiaba tras iniciar el cobro, la liquidación fallaba con 400 y bloqueaba la entrega. | Para ventas iniciadas (`STRIPE` / `STRIPE_TEST`), `liquidar` recupera y utiliza exclusivamente las líneas, precios unitarios, descuentos y total **congelados y persistidos** en `Venta.total` y `DetalleVenta`. Se valida que la solicitud corresponda a esas líneas y que `OrdenPago.monto_bob` coincida con `Venta.total`. La variación de catálogo posterior no bloquea la liquidación ni altera el importe. | `test_j3`: Venta iniciada a 100 BOB -> capturado PI -> alterado catálogo a 250 BOB -> `liquidar` devolvía 400: *"Precio unitario adulterado o desactualizado para la variante ... enviado 100.0, servidor 250.00"*. | `test_j3`: PASSED (201 Created, total respetado de 100 BOB, Kardex exacto por 100 BOB, stock descontado de comprometido). | `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py` (`liquidar`).<br>Subagente B. |
| **J4 (P1) — Reanudación de Órdenes Provisionales** | Ante fallo entre la creación de la venta/reserva y la invocación de Stripe, la orden quedaba con `PENDIENTE_{clave}` y se exponía ese valor espurio como PaymentIntent en caja; Angular no podía reanudarlo y liquidar devolvía 400. | 1. `obtener_orden_activa_caja` detecta órdenes provisionales y retorna `stripe_payment_intent_id = null`, `client_secret = null`, `estado_verificacion = "PROVISIONAL_PENDIENTE_INTENTO"` y `provisional = true`.<br>2. Endpoint contractual `POST /api/v1/pagos/stripe/ordenes/{id}/reanudar`: reanuda usando la `venta.clave_idempotencia` durable sin duplicar venta ni Kardex, asociando el `pi_...` oficial de Stripe.<br>3. En Angular (`caja.component`), despliega aviso accesible `role="alert"`, oculta el formulario de tarjeta y expone botón táctil "Reanudar Cobro Stripe". Al reanudar, monta el Card Element con el `client_secret` oficial. | `test_j4`: Activa-caja exponía `"stripe_payment_intent_id": "PENDIENTE_..."`; endpoint de reanudación arrojaba 404 Not Found. | `test_j4`: PASSED.<br>Activa-caja retorna `stripe_payment_intent_id: null`. Reanudación devuelve 200 con `pi_...` real de Stripe, actualiza la orden y conserva 1 solo compromiso digital en Kardex. | `backend/app/core/modules/ventas_pagos/services/stripe_service.py`, `routers/pagos_stripe.py`, `models_ordenes.py`, `frontend-web/src/app/features/ventas_pagos/caja/caja.component.*`, `stripe.service.ts`.<br>Subagentes A y C. |
| **J5 — Custodia, Verificación Integral y Contratos** | Necesidad de garantizar que no se realizaron commits ni pushes, que la base compartida `fashionstore_db` no fue tocada y que el contrato OpenAPI está sincronizado. | 1. OpenAPI regenerado en `openapi-segundo-parcial.json` con los nuevos endpoints y esquemas (164 paths).<br>2. Pruebas ejecutadas exclusivamente contra base aislada `fashionstore_sp2_bloque_b_test`.<br>3. Verificación de working tree intacto en los 3 repositorios (cero commits). | N/A (Regla de integridad y custodia). | Todas las suites pasando con código de salida 0. Contrato OpenAPI 100% sincronizado. Cero cambios comprometidos en Git. | Todos los repositorios y archivos de seguimiento.<br>Coordinador. |

---

## 2. Contratos y Endpoints Verificados

### A. Endpoint de Reanudación de Orden Provisional (J4)
- **Ruta:** `POST /api/v1/pagos/stripe/ordenes/{id}/reanudar`
- **Cabeceras:** `Authorization: Bearer <token>`, opcional `Idempotency-Key`
- **Respuesta 200 OK (`OrdenPagoDTO`):**
  ```json
  {
    "orden_pago_id": "550e8400-e29b-41d4-a716-446655440000",
    "estado": "PENDIENTE",
    "monto_bob": "100.00",
    "monto_usd": "14.37",
    "centavos_usd": 1437,
    "tasa_id": "880e8400-e29b-41d4-a716-446655440001",
    "client_secret": "pi_123456789_secret_abc123",
    "referencia_externa": "pi_123456789"
  }
  ```
- **Códigos de Error Controlados:**
  - `404 Not Found`: Si la orden de pago no existe o no pertenece al usuario autenticado.
  - `409 Conflict`: Si la orden ya se encuentra `CAPTURADO` o `CANCELADO`, o la venta ya está `PAGADA`.
  - `502 Bad Gateway`: Si ocurre indisponibilidad temporal o error de red con Stripe al reanudar (la orden se conserva provisional para reintento).

### B. Endpoint de Consulta de Orden Activa de Caja (`OrdenActivaCajaDTO`)
- **Ruta:** `GET /api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={id}&turno_caja_id={id}`
- **Payload para Orden Provisional:**
  ```json
  {
    "orden_pago_id": "550e8400-e29b-41d4-a716-446655440000",
    "venta_id": "660e8400-e29b-41d4-a716-446655440002",
    "stripe_payment_intent_id": null,
    "client_secret": null,
    "monto_bob": "100.00",
    "monto_usd": "14.37",
    "centavos_usd": 1437,
    "tasa_bob_por_usd": "6.96",
    "estado_orden": "PENDIENTE",
    "procedencia": "TURNO_OFFLINE",
    "lineas": [
      {
        "variante_id": "770e8400-e29b-41d4-a716-446655440003",
        "cantidad": 1,
        "precio_unitario_bob": "100.00",
        "descuento_bob": "0.00",
        "sku": "POLO-001",
        "nombre_producto": "Polo Urbano"
      }
    ],
    "estado_verificacion": "PROVISIONAL_PENDIENTE_INTENTO",
    "provisional": true
  }
  ```

---

## 3. Demostración de Contraejemplos y Evidencias Rojas y Verdes

### A. Suite de Integración Vertical del Coordinador (`test_contraejemplos_p0_auditoria_42.py`)
Ejecutada con `$env:FASHIONSTORE_TEST_DATABASE_URL` contra base aislada `fashionstore_sp2_bloque_b_test`:

```text
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_42.py::test_j1a_cancelar_orden_pago_gateway_devuelve_requires_payment_method_no_libera_stock PASSED [ 14%]
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_42.py::test_j1b_cancelar_orden_pago_gateway_devuelve_id_ajeno_rechaza_502 PASSED [ 28%]
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_42.py::test_j1c_cancelar_orden_pago_gateway_capturado_succeeded_rechaza_409 PASSED [ 42%]
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_42.py::test_j2a_webhook_payment_intent_succeeded_con_metadata_ajena_rechaza_400 PASSED [ 57%]
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_42.py::test_j2b_liquidar_presencial_con_pasarela_caida_arroja_502_y_no_liquida PASSED [ 71%]
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_42.py::test_j3_liquidar_con_precio_catalogo_modificado_posterior_mantiene_total_congelado PASSED [ 85%]
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_42.py::test_j4_reanudacion_orden_provisional_recupera_mismo_pi_sin_duplicar PASSED [100%]

======================== 7 passed, 1 warning in 5.15s =========================
```

### B. Suites Automatizadas de los Subagentes
1. **Subagente A — Stripe Backend (`test_subagente_a_stripe_auditoria_42.py`):**
   - **12 passed in 7.59s (Exit Code: 0)**
   - Demostración roja previa: 11 failed, 1 passed.
   - Demostración verde final: 12/12 passed (J1a-d, J2a-d, J4a-d).
2. **Subagente B — Venta Presencial / Inventario (`test_subagente_b_venta_auditoria_42.py`):**
   - **3 passed in 3.36s (Exit Code: 0)**
   - Demostración roja previa: 2 failed, 1 passed (J3 y J2 liquidación fallaban).
   - Demostración verde final: 3/3 passed.
3. **Subagente C — Frontend Angular Karma (`caja.component.spec.ts`):**
   - **303 passed in ChromeHeadless (Exit Code: 0)**
   - Cobertura de orden provisional, botón táctil "Reanudar Cobro Stripe", aislamiento DOM y preservación de líneas congeladas tras F5.

### C. Suites Consolidadas del Bloque B Backend
Ejecución de las 7 suites del Bloque B afectadas:
```powershell
$env:FASHIONSTORE_TEST_DATABASE_URL="<URL_POSTGRESQL_LOCAL_DE_BASE__test>"
python -m pytest backend/tests_segundo_parcial_bloque_b/test_subagente_a_stripe_auditoria_42.py backend/tests_segundo_parcial_bloque_b/test_subagente_b_venta_auditoria_42.py backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_auditoria_42.py backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_auditoria_39.py backend/tests_segundo_parcial_bloque_b/test_cu19_caja_liquidacion.py backend/tests_segundo_parcial_bloque_b/test_b1_finanzas_cu09_cu22_cu27.py backend/tests_segundo_parcial_bloque_b/test_openapi_segundo_parcial.py -q
```
**Resultado:** `66 passed, 1 warning in 38.95s` (Exit Code: 0).

---

## 4. Comandos Ejecutados y Códigos de Salida

| Repositorio / Ámbito | Comando Ejecutado | Código de Salida | Resultado Resumido |
|---|---|---|---|
| **Backend — OpenAPI Sync** | `backend\venv\Scripts\python.exe -m pytest backend/tests_segundo_parcial_bloque_b/test_openapi_segundo_parcial.py -v` | **0** | 3 passed (164 endpoints sincronizados, compatibilidad histórica preservada). |
| **Backend — Coordinador P0** | `backend\venv\Scripts\python.exe -m pytest backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_auditoria_42.py -v` | **0** | 7 passed en 5.15s (todas las puertas J1, J2, J3, J4 verificadas en verde). |
| **Backend — Subagente A** | `backend\venv\Scripts\python.exe -m pytest backend/tests_segundo_parcial_bloque_b/test_subagente_a_stripe_auditoria_42.py -q` | **0** | 12 passed en 7.59s (cancelación Stripe, validación captura y reanudación). |
| **Backend — Subagente B** | `backend\venv\Scripts\python.exe -m pytest backend/tests_segundo_parcial_bloque_b/test_subagente_b_venta_auditoria_42.py -q` | **0** | 3 passed en 3.36s (liquidación congelada y pasarela 502). |
| **Backend — Regresión CU19** | `backend\venv\Scripts\python.exe -m pytest backend/tests_segundo_parcial_bloque_b/test_cu19_caja_liquidacion.py -q` | **0** | 11 passed en 5.91s (caja presencial sin regresiones). |
| **Backend — Regresión Finanzas** | `backend\venv\Scripts\python.exe -m pytest backend/tests_segundo_parcial_bloque_b/test_b1_finanzas_cu09_cu22_cu27.py -q` | **0** | 20 passed en 11.43s (saldo, online y reembolsos intactos). |
| **Backend — Consolidado 42** | `backend\venv\Scripts\python.exe -m pytest (7 suites) -q` | **0** | **66 passed, 1 warning in 38.95s**. |
| **Frontend — Typecheck App** | `.\node_modules\.bin\tsc.cmd -p tsconfig.app.json --noEmit` | **0** | 0 errores TypeScript en aplicación Angular. |
| **Frontend — Typecheck Spec** | `.\node_modules\.bin\tsc.cmd -p tsconfig.spec.json --noEmit` | **0** | 0 errores TypeScript en especificaciones de prueba. |
| **Frontend — Karma Tests** | `npm.cmd test -- --watch=false --browsers=ChromeHeadlessNoSandbox` | **0** | **TOTAL: 303 SUCCESS, 0 FAILED** en 1.82s. |
| **Frontend — Build Producción** | `npm.cmd run build` | **0** | Bundle de producción generado en `dist/fashionstore-web` [6.78s]. |
| **Frontend — Higiene de Textos** | `Get-ChildItem src/app/features/ventas_pagos/caja/ -Include *.ts -Recurse | Select-String "prompt\|alert\|confirm"` | **0** | 0 llamadas nativas prohibidas. 0 textos técnicos en templates. |
| **Móvil — Flutter Analyze** | `flutter analyze --no-pub` | **0** | `No issues found! (ran in 2.9s)`. |
| **Git — Diff Check (3 repos)** | `git diff --check` en `backend`, `frontend-web` y `app-movil` | **0** | Limpio en los 3 repositorios (sin marcadores de conflicto ni espacios espurios). |

---

## 5. Estado de Git y Custodia en los Tres Repositorios

### Backend
- **Rama:** `feature/sp2-e2-integral`
- **HEAD:** `986bac5`
- **Archivos Modificados:**
  - `app/core/modules/ventas_pagos/models_ordenes.py`
  - `app/core/modules/ventas_pagos/routers/pagos_stripe.py`
  - `app/core/modules/ventas_pagos/services/stripe_service.py`
  - `app/core/modules/ventas_pagos/services/venta_presencial_service.py`
  - `contratos/segundo-parcial/openapi-segundo-parcial.json`
  - `seguimiento/segundo-parcial/02-estado-cu.md`
  - `seguimiento/segundo-parcial/04-bitacora.md`
  - `seguimiento/segundo-parcial/05-reanudacion.md`
  - `seguimiento/segundo-parcial/README.md`
- **Archivos Nuevos de Prueba y Documentación:**
  - `tests_segundo_parcial_bloque_b/test_subagente_a_stripe_auditoria_42.py`
  - `tests_segundo_parcial_bloque_b/test_subagente_b_venta_auditoria_42.py`
  - `tests_segundo_parcial_bloque_b/test_contraejemplos_p0_auditoria_42.py`
  - `seguimiento/segundo-parcial/interfaz-compartida-auditoria-42.md`
  - `seguimiento/segundo-parcial/43-plan-cierre-post-auditoria-42.md`
  - `seguimiento/segundo-parcial/44-checkpoint-post-auditoria-42.md`
- **Regla estricta:** Cero commits, cero push, cero merge, cero despliegue.

### Frontend Web
- **Rama:** `feature/sp2-e2-integral`
- **HEAD:** `9992cdc`
- **Archivos Modificados:**
  - `src/app/features/ventas_pagos/services/stripe.service.ts`
  - `src/app/features/ventas_pagos/models/venta-presencial.models.ts`
  - `src/app/features/ventas_pagos/caja/caja.component.ts`
  - `src/app/features/ventas_pagos/caja/caja.component.html`
  - `src/app/features/ventas_pagos/caja/caja.component.css`
  - `src/app/features/ventas_pagos/caja/caja.component.spec.ts`
- **Regla estricta:** Cero commits, cero push, cero merge, cero despliegue.

### App Móvil
- **Rama:** `feature/sp2-e2-integral`
- **HEAD:** `7880a15`
- **Status:** Sin modificaciones funcionales en esta iteración. `flutter analyze` reporta 0 issues.
- **Regla estricta:** Cero commits, cero push, cero merge, cero despliegue.

---

## 6. Límites Declarados y Estado de la Entrega

- **Límites Técnicos / Manuales:** Las pruebas automatizadas utilizan emuladores deterministas y dobles probados (`FakeStripeGateway`, `ChromeHeadlessNoSandbox`). Tarjeta bancaria real de producción, terminales físicos Android con FCM y Webhooks públicos en vivo quedan declarados como límites de infraestructura física para pruebas finales presenciales.
- **Dictamen de Entrega:** Todas las observaciones de la Auditoría 42 (P0-1, P0-2, P0-3 y P1) han sido resueltas y probadas exhaustivamente con evidencias rojas y verdes verificables.
- **Estado de E2:** **Avance técnico sin aceptar**, listo para revisión y dictamen independiente del propietario y Codex.
