# Interfaz Compartida y Acuerdos de Arquitectura — Post-Auditoría 36

**Fecha de emisión:** 06/11/2026  
**Ámbito:** Coordinador, Subagente A (Backend Inventario / Venta Presencial), Subagente B (Backend Stripe / Conciliación), Subagente C (Frontend Web Angular & Flutter Mobile).  
**Base contractual:** Contrato 0.3.2 / Protocolo 0.4.0 / Plan 37 / Auditoría 36.

---

## 1. Separación Estricta de Propiedad de Archivos (Dueño Único)

Cada archivo del sistema tiene un único propietario. Queda terminantemente prohibida la edición concurrente o cruzada:

| Responsable | Archivos Bajo su Propiedad Exclusiva |
|---|---|
| **Subagente A** (Backend Inventario / Venta) | `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>`backend/app/core/modules/inventario/repositories/inventario_repository.py`<br>`backend/tests_segundo_parcial_bloque_b/test_cu19_caja_liquidacion.py`<br>`backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_caja_posventa.py` |
| **Subagente B** (Backend Stripe / Conciliación) | `backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/modules/ventas_pagos/integraciones/stripe_gateway.py`<br>`backend/app/core/modules/ventas_pagos/routers/pagos_stripe.py`<br>`backend/app/core/tareas.py`<br>`backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_pagos.py` |
| **Subagente C** (Angular PWA & Flutter Móvil) | `frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.html`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.css`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.spec.ts`<br>`frontend-web/src/app/features/ventas_pagos/services/stripe.service.ts`<br>`frontend-web/src/app/features/ventas_pagos/models/venta-presencial.models.ts`<br>`app-movil/**` (`run_tests.ps1`, `test_diagnostic.ps1`, `DIAGNOSTICO_RUNNER_FLUTTER.md`) |
| **Coordinador** (Contratos y Puertas) | `backend/seguimiento/segundo-parcial/**`<br>`backend/contratos/segundo-parcial/openapi-segundo-parcial.json`<br>Orquestación de pruebas sin colisión, ejecución de puertas H0–H5 y checkpoint final. |

---

## 2. Decisiones de Arquitectura e Interfaz de Dominio

### 2.1 Compromiso Durable de Inventario (H1)
1. **Columna utilizada:** `InventarioSucursal.comprometido_digital` (ya existente en el esquema con constraint `comprometido_digital >= 0`).
2. **Inicio CU19 (`iniciar_stripe`):**
   - Bloquear deterministamente `InventarioSucursal` por `(sucursal_id, variante_id)`.
   - Validar stock libre: `fila_stock.disponible >= cant`. Los cupos de caja offline (`comprometido_caja`) no se tocan ni se usan para Stripe.
   - Trasladar cantidad durablemente:
     `fila_stock.disponible -= cant`
     `fila_stock.comprometido_digital += cant`
   - Registrar movimiento Kardex `COMPROMISO_DIGITAL` referenciado a `VENTA`, `venta.id`.
   - Asignar `Venta.expira_en = ahora + timedelta(minutes=15)`.
3. **Liquidación Stripe (`liquidar` con `STRIPE_TEST`):**
   - Validar que la orden esté `CAPTURADO`.
   - Consumir el compromiso: `fila_stock.comprometido_digital -= cant`.
   - **NO** descontar `fila_stock.disponible` nuevamente.
   - Registrar Kardex `VENTA_PRESENCIAL`.
4. **Ventas Efectivo y Saldo:**
   - Si no tienen cupo o no hay turno, verifican `fila_stock.disponible >= cant`. Al haberse restado `disponible` en `iniciar_stripe`, efectivo/saldo no pueden sobrevender la unidad comprometida (rechazo HTTP 409).
   - Si tienen cupo de turno (`CU06/CU07`), consumen su cupo respectivo y decrementan `comprometido_caja`, sin interferir con Stripe.

### 2.2 Stripe Fuera de Locks SQL (H2)
1. En `iniciar_stripe`:
   - Transacción 1: Validar stock, descontar `disponible`, incrementar `comprometido_digital`, crear `Venta(PENDIENTE_PAGO)` y `DetalleVenta`, crear `OrdenPago(PENDIENTE, clave_externa=f"PENDIENTE_{clave}")`, registrar Kardex.
   - **Hacer `commit()`**. Se liberan todos los bloqueos a nivel de base de datos antes de realizar cualquier llamada externa por red.
   - Fuera de locks: Llamar a pasarela `gateway.crear_o_reutilizar_intencion(...)`.
   - Transacción 2: Actualizar `OrdenPago.referencia_externa = intencion.id`, `OrdenPago.clave_externa = intencion.id`. Commit.
   - Si la llamada al gateway o el commit posterior falla, la clave de idempotencia permite reintentar o la tarea de expiración concilia sin duplicar ni bloquear el inventario de otras cajas.

### 2.3 Cancelación Honesta y Manejo de Incertidumbre (H3)
1. En `stripe_service.py::cancelar_orden_pago`:
   - Eliminar `except Exception: pass`.
   - Consultar pasarela / llamar `gateway.cancelar_intencion`.
   - Si el gateway devuelve `CANCELED`:
     - Marcar `op.estado = "CANCELADO"`, `v.estado = "CANCELADA"`.
     - Liberar inventario comprometido: `fila_stock.comprometido_digital -= cant`, `fila_stock.disponible += cant`.
     - Registrar Kardex `LIBERACION_DIGITAL`.
   - Si el PaymentIntent ya estaba `SUCCEEDED` / capturado:
     - Marcar `op.estado = "CAPTURADO"`.
     - Retornar HTTP 409 `CONFLICT`: cobro capturado en pasarela, no se puede cancelar localmente.
   - Si el gateway lanza excepción / timeout / 502:
     - Conservar orden y venta en `PENDIENTE` (estado incierto).
     - **NO** liberar inventario.
     - Lanzar HTTP 502 `BAD_GATEWAY` para informar error de pasarela sin fabricar éxito.

### 2.4 PWA: Preservación de Orden y Recuperación (H3 / H4)
1. En `caja.component.ts` (`cancelarStripeCaja` y `cancelarStripePresencial`):
   - En el callback `error`: **NO** poner la orden en `null`.
   - Mantener la orden visible con el error reportado por el backend y habilitar botones de "Reintentar confirmación", "Verificar estado" o "Tramitar incidencia".
2. Recuperación tras recarga / reingreso:
   - Nuevo endpoint seguro en backend: `GET /api/v1/pagos/stripe/ordenes/activa-caja?sucursal_id=...&turno_caja_id=...`
   - Permite recuperar una orden pendiente o capturada perteneciente al cajero/turno para continuar su flujo tras F5/reconexión sin almacenar `client_secret` en localStorage ni IndexedDB.

### 2.5 Validación Estricta de Metadata (H4)
1. En `stripe_service.py::confirmar_orden_pago`:
   - Validar que `inten.metadata` contenga `empresa_id` y que `inten.metadata["empresa_id"] == str(op.empresa_id)`. Si falta o no coincide: HTTP 400.
   - Para `contexto == "VENTA"`, validar que contenga `venta_id` y que `inten.metadata["venta_id"] == str(op.venta_id)`. Si falta o no coincide: HTTP 400.
   - Excepción de compatibilidad heredada: únicamente si la orden interna no tiene `empresa_id` (imposible en CU19 moderno) y está explícitamente probada.

---

## 3. Protocolo de Ejecución de Suites

Para evitar bloqueos concurrentes sobre la base `_test`:
- Los subagentes no ejecutan pytest simultáneamente.
- Cada subagente escribe sus contraejemplos rojos y verifica la solución verde en su turno coordinado.
- El coordinador supervisa las corridas de pruebas completas y la sincronización con OpenAPI.
