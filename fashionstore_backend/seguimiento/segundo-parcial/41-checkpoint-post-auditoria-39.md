# Checkpoint Técnico 41 — Entrega Posterior a la Auditoría Independiente 39

**Fecha:** 06/11/2026 (Bolivia)  
**Estado:** Avance técnico sin aceptar, listo para revisión independiente del propietario y Codex.  
**Ramas activas:** `feature/sp2-e2-integral` en `backend`, `frontend-web` y `app-movil`.  
**Dictamen de partida:** [Auditoría independiente 39](39-auditoria-independiente-post-checkpoint-38.md).  
**Plan de ejecución:** [Plan 40](40-plan-cierre-post-auditoria-39.md) y [Prompt E2](prompts/E2-cierre-auditoria-39-subagentes.md).  
**Regla de custodia:** Cero commits, cero push, cero merge, cero despliegues. Cambios conservados íntegramente en el working tree.

---

## 1. Matriz de Corrección P0-1 / P0-2 / P0-3

| Bloqueo | Causa Raíz en Auditoría 39 | Corrección Implementada | Evidencia Roja (Contraejemplo) | Evidencia Verde (Solución) | Archivos y Funciones |
|---|---|---|---|---|---|
| **P0-1 — Vencimiento sin liberación en incertidumbre** | En `stripe_service.py:573-577`, fallo en `cancelar_intencion` continuaba tras `except Exception: pass`, liberando `comprometido_digital`, Kardex `LIBERACION_DIGITAL` y cancelando `Venta` sin confirmar pasarela. | Erradicado `except: pass`. Ante error de pasarela/timeout (502/503), rollback de la venta, omisión para reintento del worker, inventario intacto, cero Kardex `LIBERACION_DIGITAL`. Ante captura concurrente (Stripe 400 / `SUCCEEDED`), valida con `_validar_intencion_con_orden`, sincroniza `op.estado = "CAPTURADO"`, commit y nunca libera stock. | `test_p0_1a_cancelar_intencion_falla_red_timeout_no_libera_stock_ni_kardex_y_omite`<br>Falla con código anterior: stock se liberaba y venta pasaba a `CANCELADA`. | `test_p0_1a...`: PASSED.<br>`test_p0_1b_captura_concurrente...`: PASSED.<br>DB: `Venta.estado='PENDIENTE_PAGO'`, `OrdenPago.estado='PENDIENTE'`, `comprometido_digital` retenido, 0 Kardex `LIBERACION_DIGITAL`. | `backend/app/core/modules/ventas_pagos/services/stripe_service.py` (`cancelar_ventas_stripe_vencidas`), `backend/app/core/tareas.py` (`expirar_ventas_stripe_segura`). |
| **P0-2 — Recuperación real de caja tras F5** | `GET /api/v1/pagos/stripe/ordenes/activa-caja` devolvía `OrdenPagoDTO` sin `venta_id`, `stripe_payment_intent_id`, tasa congelada, líneas ni procedencia. Angular esperaba `IniciarVentaPresencialStripeRespuestaDTO`, no restauraba líneas en memoria y fallaba al liquidar. | Implementado `OrdenActivaCajaDTO` con `venta_id`, `stripe_payment_intent_id`, `client_secret`, tasa congelada de `TasaCambio`, `procedencia` (`TURNO_OFFLINE` / `PRESENCIAL`), `lineas` persistidas desde `DetalleVenta`, y `estado_verificacion`. En Angular, `recuperarOrdenActivaCaja` restaura líneas y estado en el panel correspondiente. Tras F5, permite liquidar la misma venta con sus líneas sin reiniciar PaymentIntent. | `caja.component.spec.ts:1267` usaba mock simulando datos inexistentes en backend; tras F5 las líneas quedaban vacías imposibilitando liquidar. | 5 tests unitarios en Karma pasando (TOTAL: 300 SUCCESS). `test_p0_2a...` y `test_p0_2b...` en Pytest PASSED. F5 restaura líneas y permite liquidar con HTTP 200 en backend. | `backend/app/core/modules/ventas_pagos/models_ordenes.py`, `routers/pagos_stripe.py`, `stripe_service.py`, `frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts`, `services/stripe.service.ts`, `models/venta-presencial.models.ts`. |
| **P0-3 — Validación financiera única antes de CAPTURADO** | `obtener_orden_activa_caja` marcaba `CAPTURADO` al ver `SUCCEEDED` sin validar ID, moneda USD, centavos exactos ni metadata de empresa y venta. Además `except: pass` ocultaba caídas de pasarela. | Extraída rutina única `_validar_intencion_con_orden` obligatoria en confirmación, recuperación y vencimiento. Si no coincide ID, moneda, centavos o metadata, rechaza con HTTP 400 y no transiciona a `CAPTURADO`. Ante indisponibilidad de pasarela, retorna `estado_verificacion = "NO_VERIFICADO_ERROR_PASARELA"` sin silenciar con pass. UI muestra advertencia con reintento. | Intenciones con ID ajeno, moneda EUR, centavos distintos, o metadata sin `empresa_id`/`venta_id` transicionaban espuriamente a `CAPTURADO`. | 6 tests unitarios dedicados en `test_contraejemplos_p0_auditoria_39.py` (`test_p0_3a` a `test_p0_3f`): todos PASSED. La orden permanece `PENDIENTE` y el error de pasarela reporta no verificado. | `stripe_service.py` (`_validar_intencion_con_orden`, `obtener_orden_activa_caja`, `confirmar_orden_pago`), `caja.component.ts`, `caja.component.html`. |

---

## 2. Contrato JSON Real Verificado (`OrdenActivaCajaDTO`)

### Endpoint
`GET /api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={id}&turno_caja_id={id}`

### Payload JSON de Producción
```json
{
  "orden_pago_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "venta_id": "c3d1f11e-28b3-4f91-8e01-d852a4e21a22",
  "stripe_payment_intent_id": "pi_test_1234abcd",
  "client_secret": "pi_test_1234abcd_secret_test",
  "monto_bob": "300.00",
  "monto_usd": "43.10",
  "centavos_usd": 4310,
  "tasa_bob_por_usd": "6.96",
  "estado_orden": "PENDIENTE",
  "estado": "PENDIENTE",
  "sucursal_id": "11111111-1111-1111-1111-111111111111",
  "turno_caja_id": "22222222-2222-2222-2222-222222222222",
  "cliente_id": "33333333-3333-3333-3333-333333333333",
  "procedencia": "TURNO_OFFLINE",
  "lineas": [
    {
      "variante_id": "44444444-4444-4444-4444-444444444444",
      "cantidad": 2,
      "precio_unitario_bob": "150.00",
      "descuento_bob": "0.00",
      "sku": "POLO-BLANCO-M",
      "nombre_producto": "Polo Clásico Blanco"
    }
  ],
  "estado_verificacion": "VERIFICADO"
}
```

---

## 3. Demostración de Contraejemplos y Evidencias Rojas y Verdes

### Suite Dedicada `test_contraejemplos_p0_auditoria_39.py` (Base `fashionstore_sp2_bloque_b_test`)
```
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_1a_cancelar_intencion_falla_red_timeout_no_libera_stock_ni_kardex_y_omite PASSED
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_1b_captura_concurrente_entre_consulta_y_cancelacion_no_libera_stock_y_sincroniza_capturado PASSED
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_2a_recuperar_orden_activa_caja_estructura_completa_dto_presencial_y_offline PASSED
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_2b_autorizacion_y_aislamiento_caja_tenant_y_cajero PASSED
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_3a_intencion_id_discrepante_rechaza_captura PASSED
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_3b_intencion_moneda_discrepante_rechaza_captura PASSED
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_3c_intencion_centavos_discrepantes_rechaza_captura PASSED
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_3d_intencion_metadata_empresa_faltante_o_ajena_rechaza_captura PASSED
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_3e_intencion_metadata_venta_faltante_o_ajena_rechaza_captura PASSED
backend\tests_segundo_parcial_bloque_b\test_contraejemplos_p0_auditoria_39.py::test_p0_3f_gateway_timeout_o_error_conexion_no_silencia_y_reporta_no_verificado PASSED
======================= 10 passed, 1 warning en 8.42s =======================
```

### Suite de Compatibilidad de Caja y Pagos
- `test_contraejemplos_p0_pagos.py`, `test_cu19_caja_liquidacion.py`, `test_contraejemplos_p0_caja_posventa.py`:
  **49 passed in 52.25s (100% de éxito, exit code 0)**.

### Suite Completa Bloque B Backend (`tests_segundo_parcial_bloque_b`)
- `pytest backend/tests_segundo_parcial_bloque_b/ -q`:
  **267 passed, 4 warnings in 237.93s (exit code 0)**.

---

## 4. Verificación de Recuperación Real de Caja tras F5 en Angular

Pruebas unitarias en Karma (`frontend-web/src/app/features/ventas_pagos/caja/caja.component.spec.ts`):
1. **F5 en modo `TURNO_OFFLINE`:** `recuperarOrdenActivaCaja` restaura `ordenStripeCaja`, asigna `medioPagoCaja = 'STRIPE_TEST'`, puebla `lineasVentaOffline` con cantidad y precio unitario persistidos, y restaura `clienteIdCaja`.
2. **F5 en modo `PRESENCIAL`:** Restaura `ordenStripePresencial`, `metodo = 'STRIPE_TEST'`, puebla `items` con las líneas del servidor y restaura `clienteIdPresencial`.
3. **F5 con orden `CAPTURADO`:** Al recuperar orden ya capturada tras F5, el cajero liquida exitosamente la misma venta enviando `venta_id`, `orden_pago_id`, `stripe_payment_intent_id` y las líneas restauradas; no se solicita un nuevo PaymentIntent ni se duplica el cobro.
4. **Cambio de turno:** Si la orden pertenece a un turno distinto del activo, no se asocia localmente y se alerta al cajero con aviso accesible.
5. **Fallo de pasarela (`NO_VERIFICADO_ERROR_PASARELA`):** Conserva la orden en `PENDIENTE`, muestra banner de advertencia accesible `.stripe-alerta-verificacion` y botón con foco y min-height de 44px para reintentar comprobación.

---

## 5. Comandos Ejecutados y Códigos de Salida

| Repositorio / Ámbito | Comando Ejecutado | Código de Salida | Resultado Resumido |
|---|---|---|---|
| **Backend — OpenAPI** | `python -m pytest backend/tests_segundo_parcial_bloque_b/test_openapi_segundo_parcial.py -v` | **0** | 3 passed (contrato sincronizado y compatible con Ciclo 3). |
| **Backend — P0 Auditoría 39** | `python -m pytest backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_auditoria_39.py -v` | **0** | 10 passed en 8.42s (contraejemplos demostrados y resueltos). |
| **Backend — Suite Pagos/Caja** | `python -m pytest test_contraejemplos_p0_pagos.py test_cu19_caja_liquidacion.py test_contraejemplos_p0_caja_posventa.py -v` | **0** | 49 passed en 52.25s. |
| **Backend — Suite Bloque B** | `python -m pytest backend/tests_segundo_parcial_bloque_b/ -q` | **0** | **267 passed, 4 warnings in 237.93s**. |
| **Frontend — Typecheck** | `.\node_modules\.bin\tsc.cmd -p tsconfig.app.json --noEmit` | **0** | Compilación TypeScript limpia sin errores de tipos. |
| **Frontend — Karma Tests** | `npm.cmd test -- --watch=false --browsers=ChromeHeadlessNoSandbox` | **0** | **TOTAL: 300 SUCCESS** (296 existentes + 4 nuevas especificaciones). |
| **Frontend — Build Producción** | `npm.cmd run build` | **0** | Bundle de producción generado en `dist/fashionstore-web`. |
| **Frontend — Textos técnicos** | `Select-String -Path src/app/features/ventas_pagos/caja/* -Pattern 'CU[0-9]+...'` | **0** | Cero cadenas técnicas en templates HTML o mensajes de usuario. |
| **Móvil — Flutter Analyze** | `flutter analyze --no-pub` | **0** | `No issues found! (ran in 2.8s)`. |
| **Git — Diff Check (3 repos)** | `git diff --check` | **0** | Limpio en los 3 repositorios (sin marcadores ni espacios espurios). |

---

## 6. Estado de Git y Custodia en los Tres Repositorios

### Backend
- **Rama:** `feature/sp2-e2-integral`
- **HEAD:** `986bac5`
- **Status:** Modificados: `models_ordenes.py`, `routers/pagos_stripe.py`, `stripe_service.py`, `tareas.py`, `openapi-segundo-parcial.json`. Nuevo: `tests_segundo_parcial_bloque_b/test_contraejemplos_p0_auditoria_39.py`. Seguimiento: `interfaz-compartida-auditoria-39.md`, `41-checkpoint-post-auditoria-39.md`, `README.md`, `02-estado-cu.md`, `04-bitacora.md`, `05-reanudacion.md`.
- Cambios de trabajo previos conservados sin alteración.
- **Sin commit, push, merge ni despliegue.**

### Frontend Web
- **Rama:** `feature/sp2-e2-integral`
- **HEAD:** `9992cdc`
- **Status:** Modificados: `caja.component.ts`, `caja.component.html`, `caja.component.css`, `caja.component.spec.ts`, `stripe.service.ts`, `venta-presencial.models.ts`.
- Cambios de trabajo previos conservados sin alteración.
- **Sin commit, push, merge ni despliegue.**

### App Móvil
- **Rama:** `feature/sp2-e2-integral`
- **HEAD:** `7880a15`
- **Status:** Sin modificaciones realizadas en este encargo (Flutter no consume `/activa-caja`, `analyze` 0 issues).
- Cambios de trabajo previos conservados sin alteración.
- **Sin commit, push, merge ni despliegue.**

---

## 7. Límites Manuales y Siguiente Paso

- **Límites Manuales Declarados:** Tarjeta física real de Stripe, Webhooks en vivo desde Internet, FCM real hacia terminal físico Android y dispositivo físico Android permanecen declarados como no verificados en este entorno automatizado (utilizan emuladores locales deterministas y dobles probados).
- **Siguiente Paso:** Entrega del checkpoint al propietario y Codex para la revisión independiente del cierre de los tres P0 de la auditoría 39. E2 permanece en **avance sin aceptar**.
