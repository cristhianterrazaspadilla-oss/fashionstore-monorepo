# Interfaz Compartida y Acuerdos de Arquitectura — Auditoría 33

**Fecha de emisión:** 06/11/2026  
**Ámbito:** Coordinador, Subagente A (Backend Dinero/Inventario), Subagente B (Angular/PWA), Subagente C (Flutter/Entorno).  
**Base contractual:** Contrato 0.3.2 / Protocolo 0.4.0 / Plan Final 34 / Auditoría 33.

---

## 1. Separación Estricta de Propiedad de Archivos

Cada archivo del sistema tiene un único propietario. Queda prohibida la edición cruzada o concurrente:

| Responsable | Propiedad Exclusiva de Archivos |
|---|---|
| **Subagente A** (Backend Dinero/Inventario) | `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>`backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/modules/ventas_pagos/routers/pagos_stripe.py`<br>`backend/app/core/modules/ventas_pagos/routers/ventas_presenciales.py`<br>`backend/app/core/modules/ventas_pagos/integraciones/stripe_gateway.py`<br>`backend/tests_segundo_parcial_bloque_b/test_cu19_caja_liquidacion.py`<br>`backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_caja_posventa.py`<br>`backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_pagos.py` |
| **Subagente B** (Angular / PWA) | `frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.html`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.css`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.spec.ts`<br>`frontend-web/src/app/features/ventas_pagos/services/stripe.service.ts`<br>`frontend-web/src/app/features/ventas_pagos/models/venta-presencial.models.ts`<br>`frontend-web/src/app/features/ventas_pagos/checkout/checkout.component.ts`<br>`frontend-web/src/app/features/ventas_pagos/checkout/checkout.component.html`<br>`frontend-web/src/app/features/ventas_pagos/checkout/checkout.component.spec.ts`<br>`frontend-web/src/app/core/services/sincronizacion-offline.service.ts`<br>`frontend-web/src/app/core/services/sincronizacion-offline.service.spec.ts` |
| **Subagente C** (Flutter / Entorno) | `app-movil/**` (código Dart, scripts de prueba `run_tests.ps1`, `test_diagnostic.ps1`, documentación `DIAGNOSTICO_RUNNER_FLUTTER.md`, specs unit y widget de CU05/push/caja). |
| **Coordinador** (Contratos y Verificación) | `backend/seguimiento/segundo-parcial/**`<br>`backend/contratos/segundo-parcial/openapi-segundo-parcial.json`<br>`backend/app/core/modules/reservas_traslados/schemas_sincronizacion.py` (si requiere ajuste de DTO compartido pactado)<br>Verificación vertical multi-repo y auditoría cruzada. |

---

## 2. Decisión Contractual CU19 e Inventario (Stock Libre vs. Cupos)

1. **CU19 Venta Conectada Stripe usa stock libre (`InventarioSucursal.disponible`):**
   - CU06 aparta cupos (`CupoCaja`, `comprometido_caja`) para venta presencial offline en efectivo (CU07).
   - Que el cajero tenga turno abierto no autoriza consumir cupos para transacciones Stripe.
   - En `iniciar_stripe`: el stock verificado es el stock libre. Si `disponible < cantidad`, se rechaza con HTTP 409 `CONFLICT` antes de crear el PaymentIntent con mensaje: *"Stock libre insuficiente para venta conectada Stripe (prenda asignada a caja offline o agotada)"*.
   - Caso libre 0 / cupo 1: **Rechazar con 409 antes de crear PaymentIntent**.
   - Caso libre 1 / cupo 1: Stripe consume únicamente 1 de `disponible`, dejando `disponible = 0`, `comprometido_caja = 1` y cupo intacto para CU07.
   - En `liquidar`: eliminar `max(0, comprometido_caja - cant)`. La liquidación de Stripe decrementa sólo `disponible`.
2. **Prevención de doble intención sobre la misma unidad:**
   - La reserva o comprobación atómica evita que dos cajas concurrentes emitan dos PaymentIntent cuando sólo existe 1 unidad libre.
   - Si una llamada a Stripe falla o se reintenta con la misma clave idempotente, se devuelve la misma orden/venta sin duplicar.

---

## 3. Endurecimiento de `/pagos/stripe/ordenes/{id}/confirmar`

Al consultar la pasarela para confirmar una `OrdenPago`, antes de pasar a `CAPTURADO`:
1. Validar que la referencia de la intención coincida (`inten.id == op.referencia_externa`).
2. Validar que la moneda sea exactamente `"usd"`.
3. Validar que el importe en centavos coincida exactamente con la orden (`inten.monto_centavos == op.centavos_usd`).
4. Validar metadata de seguridad:
   - `inten.metadata.get("empresa_id") == str(op.empresa_id)`
   - Si `op.contexto == "VENTA"`, validar `inten.metadata.get("venta_id") == str(op.venta_id)`.
   - Si `op.contexto == "PEDIDO"`, validar `inten.metadata.get("pedido_id") == str(op.pedido_id)`.
5. Si alguna validación falla, **NO cambiar a CAPTURADO** y rechazar con HTTP 400/409/422.
6. La transición a `CAPTURADO` debe ser estrictamente idempotente. Webhooks o peticiones duplicadas devuelven la orden capturada sin duplicar registros de Pago, Venta ni Kardex.

---

## 4. Cancelación y Recuperación (F3)

1. **Endpoint backend:**
   - `POST /api/v1/pagos/stripe/ordenes/{id}/cancelar`
   - Si la orden está en `PENDIENTE` o `REQUIERE_ACCION_CLIENTE`, cancela la orden en Stripe (si aplica) y en base de datos (`CANCELADO`). Si está asociada a una Venta `PENDIENTE_PAGO`, transiciona la venta a `CANCELADA`.
   - Si la orden ya está en `CAPTURADO`, no cancela silenciosamente: devuelve HTTP 409 indicando que el cobro ya fue capturado y requiere liquidación o reembolso CU27.
2. **Frontend Angular:**
   - En ambos paneles de caja (con turno y directa), `cancelarStripeCaja` y `cancelarStripePresencial`:
     - Si la orden está pendiente, invocar la cancelación en backend antes de limpiar localmente.
     - Si la orden está `CAPTURADO` o en estado incierto (error de red durante captura), no borrar la orden a `null`: ofrecer reintento de confirmación central o liquidación del cobro ya capturado.

---

## 5. Captura Real Stripe en Ambas Cajas PWA (F1)

1. En `caja.component.html` (ambos paneles: caja con turno y venta directa):
   - Montar Stripe Elements seguro (`card` o `payment` element) usando `client_secret` oficial retornado por `iniciar-stripe`.
   - El botón de confirmación permanece deshabilitado hasta que el elemento de tarjeta esté completo y sin error (`change.complete && !change.error`).
2. Flujo de confirmación:
   - Deshabilitar controles contra doble clic.
   - Invocar al SDK oficial del cliente (`stripe.confirmCardPayment` o `stripe.confirmPayment`) con el `client_secret` de la orden.
   - Gestionar 3DS/SCA si Stripe lo requiere.
   - Si el SDK retorna error del proveedor: mostrarlo con claridad al cajero sin inventar éxito ni alterar la orden a capturada.
   - Si el SDK confirma éxito (`succeeded`):
     - Invocar al backend `/pagos/stripe/ordenes/{id}/confirmar`.
     - Confirmada la orden como `CAPTURADO` por el backend central, liquidar la misma `venta_id`.
   - Al salir o resetear, limpiar y destruir elementos de tarjeta (`destroy()`).

---

## 6. Validación de CU05 y Retiro de Emulador CU22 (F4)

1. **CU05 `sanitizarAutorizacionCobro` en Angular:**
   - Validar formatos estrictos:
     - UUIDs (`consentimiento_id`, `tasa_id`, `preparacion_pago_id`).
     - Hash SHA-256 de 64 caracteres hex (`huella_compra`).
     - Decimales positivos (`base_bob`, `total_bob`, `importe_cobro`, `tasa_bob_por_usd` > 0).
     - Decimales no negativos (`descuento_bob`, `envio_bob` >= 0).
     - Fechas ISO válidas (`aceptado_local_en`, `vigente_hasta`).
     - Consentimiento explícito booleano `permite_cobro_al_reconectar === true`.
   - Si falta algún campo o tiene formato inválido, retornar `undefined`.
   - PWA omitirá el objeto antes de enviar `SOLICITAR_COMPRA` v3, permitiendo que se encole y quede en `PENDIENTE_INTERVENCION` sin cargo.
   - Backend ya rechaza objetos mal formados o parciales con HTTP 422 (`extra="forbid"`).
2. **CU22 en `checkout.component.ts`:**
   - Eliminar `window.stripeElementsEmulator` y `window.StripeEmulator` del código en ejecución productivo.
   - En pruebas unitarias, la inyección del SDK se hace mediante el servicio `StripeService` o dobles inyectados formalmente.
