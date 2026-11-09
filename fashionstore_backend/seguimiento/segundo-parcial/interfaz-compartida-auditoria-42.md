# Interfaz Compartida y Acuerdos de Arquitectura — Auditoría 42

**Fecha de emisión:** 06/11/2026 (Bolivia)  
**Coordinador y Subagentes:** Coordinador (Integración, OpenAPI y Checkpoint 44), Subagente A (Stripe/Backend Financiero: J1/J2 y API J4), Subagente B (Venta/Inventario Backend: J3 y Ejecución J4), Subagente C (Caja Angular/PWA: UX J3/J4 y Reanudación).  
**Base Contractual:** Plan 43 / Auditoría 42 / Prompt E2 / Contratos CU19 y CU22 / Skills `fashionstore-ciclo-2` y `fashionstore-frontend-continuity`.

---

## 1. Asignación Estricta de Propiedad de Archivos (Dueño Único)

| Responsable | Archivos Bajo su Propiedad Exclusiva | Entregable Principal |
|---|---|---|
| **Subagente A — Stripe / Backend Financiero** | `backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/modules/ventas_pagos/routers/pagos_stripe.py`<br>`backend/app/core/modules/ventas_pagos/models_ordenes.py`<br>`backend/tests_segundo_parcial_bloque_b/test_subagente_a_stripe_auditoria_42.py` (nuevo) | J1 (cancelación manual con CANCELED verificado), J2 (validación rigurosa en webhook, 3DS y todas las rutas), API de reanudación provisional J4. |
| **Subagente B — Venta Presencial / Inventario** | `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>`backend/tests_segundo_parcial_bloque_b/test_subagente_b_venta_auditoria_42.py` (nuevo) | J3 (liquidación con importes congelados de la venta sin recálculo de catálogo), validación de captura sin silenciar errores (J2 en liquidación), idempotencia y reanudación de venta provisional (J4). |
| **Subagente C — Angular / PWA** | `frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.html`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.css`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.spec.ts`<br>`frontend-web/src/app/features/ventas_pagos/services/stripe.service.ts`<br>`frontend-web/src/app/features/ventas_pagos/services/venta-presencial.service.ts`<br>`frontend-web/src/app/features/ventas_pagos/models/venta-presencial.models.ts` | Consumo de orden provisional, botón/flujo explícito de "Reanudar cobro", recuperación tras F5 antes y después de captura, liquidación con líneas/precio congelados, accesibilidad y alertas claras. |
| **Coordinador — Integración y Documentación** | `backend/seguimiento/segundo-parcial/interfaz-compartida-auditoria-42.md`<br>`backend/contratos/segundo-parcial/openapi-segundo-parcial.json`<br>`backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_auditoria_42.py` (nuevo vertical)<br>`backend/seguimiento/segundo-parcial/44-checkpoint-post-auditoria-42.md`<br>`backend/seguimiento/segundo-parcial/README.md`<br>`backend/seguimiento/segundo-parcial/02-estado-cu.md`<br>`backend/seguimiento/segundo-parcial/04-bitacora.md`<br>`backend/seguimiento/segundo-parcial/05-reanudacion.md` | Supervisión general, contratos OpenAPI, suite vertical de integración, ejecución de suites serializadas en base `_test`, y redacción del checkpoint 44. |

---

## 2. Estados y Transiciones de Orden y Venta

```
[Venta: PENDIENTE_PAGO]
  ├─ Iniciar Stripe (1er commit) ───────────────> OrdenPago: PENDIENTE (clave_externa="PENDIENTE_{clave}", referencia_externa=None/"PENDIENTE_{clave}")
  │                                               Inventario: comprometido_digital += cant, disponible -= cant, Kardex COMPROMISO_DIGITAL
  │
  ├─ Llamada a Stripe exitosa (2do commit) ─────> OrdenPago: PENDIENTE (clave_externa="pi_...", referencia_externa="pi_...")
  │
  ├─ Reanudación provisional (si falló 2do commit) ─> Usa venta.clave_idempotencia durable en Stripe -> guarda "pi_..."
  │
  ├─ Confirmación de Cobro (Stripe SUCCEEDED) ──> OrdenPago: CAPTURADO (validación exhaustiva obligatoria)
  │                                               Venta: PENDIENTE_PAGO (aún no liquidada en inventario final)
  │
  ├─ Liquidación Presencial (CU19) ─────────────> Venta: PAGADA
  │                                               OrdenPago: CAPTURADO (ya verificado)
  │                                               Inventario: comprometido_digital -= cant, Kardex VENTA_PRESENCIAL
  │                                               Comprobante emitido con total congelado
  │
  └─ Cancelación confirmada por Stripe (CANCELED) -> OrdenPago: CANCELADO
                                                     Venta: CANCELADA
                                                     Inventario: comprometido_digital -= cant, disponible += cant, Kardex LIBERACION_DIGITAL
```

---

## 3. Evidencia Requerida para CAPTURADO y CANCELADO

### A. Para marcar `OrdenPago.estado = 'CAPTURADO'`
Toda ruta (`confirmar_orden_pago`, `obtener_orden_activa_caja`, `confirmarWebhook`, `_aplicar_aprobado_orden`, `continuar_accion`, `liquidar`) debe verificar de forma obligatoria e ineludible:
1. **ID de PaymentIntent:** El objeto o respuesta de Stripe debe tener `id` coincidente con `op.referencia_externa` o `op.clave_externa`. Si la orden tiene `PENDIENTE_...`, jamás se marca capturado sin antes obtener el ID real mediante reanudación/consulta segura.
2. **Moneda:** `moneda.lower() == 'usd'`.
3. **Monto en centavos:** `monto_centavos == op.centavos_usd` (si `op.centavos_usd` está registrado).
4. **Metadata de Empresa:** `metadata["empresa_id"] == str(op.empresa_id)`.
5. **Metadata de Recurso:**
   - Para contexto VENTA: `metadata["venta_id"] == str(op.venta_id)`.
   - Para contexto PEDIDO: `metadata["pedido_id"] == str(op.pedido_id)`.
6. Si la llamada al proveedor arroja excepción o red caída: **NO marcar CAPTURADO**. En liquidación arrojar `HTTP 502 Bad Gateway` salvo que exista evidencia durable verificada previa (`EventoProveedor` procesado o comprobación previa registrada).

### B. Para marcar `OrdenPago.estado = 'CANCELADO'` y liberar inventario
En `StripeService.cancelar_orden_pago`:
1. Si la orden tiene un PI real (`pi_...`): invocar `gateway.cancelar_intencion(ref_pi)`.
2. La pasarela DEBE devolver confirmación explícita `inten.estado.upper() == "CANCELED"` y `inten.id == ref_pi`.
3. Si la pasarela devuelve `SUCCEEDED` / `CAPTURADO`:
   - Validar con `_validar_intencion_con_orden`.
   - Sincronizar `op.estado = "CAPTURADO"`.
   - **NUNCA liberar stock**.
   - Arrojar `HTTP 409 Conflict` indicando que los fondos ya fueron capturados y debe liquidarse o reembolsarse.
4. Si la pasarela devuelve cualquier otro estado (`REQUIRES_PAYMENT_METHOD`, `REQUIRES_ACTION`, `PROCESSING`, respuesta con ID ajeno o inválida):
   - **NO marcar CANCELADO**.
   - **NO liberar stock (`comprometido_digital` y Kardex intactos)**.
   - Arrojar `HTTP 502 Bad Gateway` informando que Stripe no confirmó la cancelación y la orden permanece pendiente.
5. Si la llamada arroja excepción (timeout, 5xx, error de red):
   - **NO marcar CANCELADO**.
   - **NO liberar stock**.
   - Arrojar `HTTP 502 Bad Gateway`.
6. Si la orden era provisional (`PENDIENTE_{clave}`):
   - Intentar cancelar en Stripe usando la intención asociada si fue creada por la pasarela, o marcar cancelada localmente sólo si se comprueba que Stripe no retiene fondos.

---

## 4. Reanudación de Orden Provisional (J4)

### Causa Raíz
`iniciar_stripe` realiza dos transacciones:
- Transacción 1: Persiste `Venta` (con `clave_idempotencia`) y `OrdenPago` con `clave_externa="PENDIENTE_{clave}"`.
- Transacción 2: Llama a Stripe y actualiza `OrdenPago` con `intencion.id`.
Si el proceso se interrumpe entre Transacción 1 y Transacción 2 (o Stripe responde pero falla el segundo commit), la orden queda provisional.

### Solución Contractual
1. **Endpoint de Reanudación:**
   `POST /api/v1/pagos/stripe/ordenes/{id}/reanudar`
   - Autorizado por tenant y cajero/sucursal/turno de la venta.
   - Si la orden ya tiene PI real, consulta y sincroniza su estado.
   - Si la orden tiene `PENDIENTE_{clave}`:
     Recupera la clave idempotente durable desde `venta.clave_idempotencia`.
     Invoca `gateway.crear_o_reutilizar_intencion(..., idempotency_key=str(venta.clave_idempotencia))` de forma idempotente.
     Actualiza `op.clave_externa = intencion.id`, `op.referencia_externa = intencion.id`.
     Retorna `OrdenPagoDTO` con `client_secret` y `referencia_externa`.
2. **Protección en `obtener_orden_activa_caja`:**
   - Si `op.referencia_externa` o `op.clave_externa` comienza con `"PENDIENTE_"`, **NO enviar este valor como `stripe_payment_intent_id`** a Angular (se envía `null` o se declara `provisional: true`).
   - `estado_verificacion` reporta `"PROVISIONAL_PENDIENTE_INTENTO"`.
   - Angular detecta este estado y ofrece el botón explícito **"Reanudar Cobro Stripe"** en lugar de crear una venta nueva.

---

## 5. Liquidación con Importes Congelados (J3)

### Regla Financiera
Una vez creada la `Venta` en `iniciar_stripe`:
- `Venta.total`, `DetalleVenta` (`variante_id`, `cantidad`, `precio_unitario`, `descuento_aplicado`) y `OrdenPago.monto_bob` son la fuente canónica congelada.
- Al liquidar (`POST /api/v1/ventas/presenciales/liquidar` con `medio_pago == 'STRIPE_TEST'` o `venta_id` existente):
  1. No recalcular precios con `VarianteProducto.precio` actual ni promociones vigentes en el catálogo.
  2. Validar que las líneas enviadas por el frontend correspondan exactamente a los `DetalleVenta` persistidos (mismas variantes y cantidades).
  3. Validar que `orden_stripe.monto_bob == venta_existente.total`.
  4. Consumir el stock previamente comprometido (`comprometido_digital`), pasando a descontado y registrando `Kardex` `VENTA_PRESENCIAL`.
  5. Si el catálogo aumentó o redujo precios en el interín, la liquidación **prosigue exitosamente a HTTP 200 con el total congelado original**.
  6. Para ventas presenciales nuevas en `EFECTIVO` o `SALDO` (sin venta previa iniciada), se mantiene la validación rigurosa de precios contra catálogo y cálculo en servidor.

---

## 6. DTOs y Contrato JSON Real para Angular (`OrdenActivaCajaDTO`)

### Endpoint
`GET /api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id={id}&turno_caja_id={id}`

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

*Nota para órdenes provisionales:*
Cuando la orden no tiene aún `pi_...` confirmado en Stripe:
- `stripe_payment_intent_id`: `null`
- `client_secret`: `null`
- `estado_verificacion`: `"PROVISIONAL_PENDIENTE_INTENTO"`
- El frontend presenta aviso accesible y botón "Reanudar Cobro Stripe". Al pulsar, invoca `POST /api/v1/pagos/stripe/ordenes/{orden_pago_id}/reanudar`.

---

## 7. Errores HTTP y Respuestas Estándar

| Situación | Código HTTP | Mensaje / Causa |
|---|---|---|
| Cancelación sin confirmación de Stripe (estado devuelto != CANCELED) | `502 BAD GATEWAY` | `La pasarela Stripe no confirmó la cancelación (estado: {estado}); la orden y el inventario se conservan pendientes para reintento.` |
| Intento de cancelar orden con fondos capturados (`SUCCEEDED`) | `409 CONFLICT` | `No se puede cancelar una orden con fondos capturados en pasarela; liquide la venta o tramite reembolso CU27` |
| Discrepancia en ID, moneda, centavos o metadata en webhook / 3DS | `400 BAD REQUEST` | `Datos del PaymentIntent no coinciden con la orden: {detalle}` |
| Indisponibilidad de pasarela al liquidar sin evidencia durable | `502 BAD GATEWAY` | `No se pudo verificar el estado del pago en Stripe por error de conexión; la orden se conserva pendiente para reintento.` |
| Reanudar orden no provisional o ya capturada/liquidada | `409 CONFLICT` | `La orden ya se encuentra capturada o liquidada` |
| Reanudación con error de red en pasarela | `502 BAD GATEWAY` | `Error al comunicar con la pasarela Stripe para reanudar la orden; se conserva provisional para reintento.` |

---

## 8. Confirmación de Subagentes

- **Subagente A:** Acepta propiedad de `stripe_service.py`, `pagos_stripe.py`, `models_ordenes.py` e implementación de J1, J2 y endpoint `reanudar`.
- **Subagente B:** Acepta propiedad de `venta_presencial_service.py` e implementación de J3 (liquidación con importes congelados sin recálculo de variantes), no silenciar errores de gateway al liquidar (J2) y reanudación idempotente con clave durable (J4).
- **Subagente C:** Acepta propiedad de `caja.component.*`, `stripe.service.ts`, `venta-presencial.service.ts` e implementación de UI accesible para provisional, F5 antes/después de captura y liquidación congelada.
