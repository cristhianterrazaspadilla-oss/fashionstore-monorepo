# Interfaz Compartida y Acuerdos de Arquitectura — Auditoría 39

**Fecha de emisión:** 06/11/2026 (Bolivia)  
**Coordinador y Subagentes:** Coordinador (Integración y Documentación), Subagente A (Backend de Producción), Subagente B (Caja Angular), Subagente C (Contraejemplos Backend y Contrato).  
**Base Contractual:** Plan 40 / Auditoría 39 / Prompt E2 / Contratos CU19 y CU22.

---

## 1. Asignación Estricta de Propiedad de Archivos (Dueño Único)

| Responsable | Archivos Bajo su Propiedad Exclusiva |
|---|---|
| **Subagente A — Backend Producción** | `backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/modules/ventas_pagos/models_ordenes.py`<br>`backend/app/core/modules/ventas_pagos/routers/pagos_stripe.py`<br>`backend/app/core/tareas.py` |
| **Subagente B — Caja Angular** | `frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.html`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.css`<br>`frontend-web/src/app/features/ventas_pagos/caja/caja.component.spec.ts`<br>`frontend-web/src/app/features/ventas_pagos/services/stripe.service.ts`<br>`frontend-web/src/app/features/ventas_pagos/models/venta-presencial.models.ts` |
| **Subagente C — Contraejemplos Backend y Contrato** | `backend/tests_segundo_parcial_bloque_b/test_contraejemplos_p0_auditoria_39.py` (archivo nuevo dedicado)<br>Inspección de Flutter `app-movil/` (sin cambios salvo regresión demostrada). |
| **Coordinador — Integración y Documentación** | `backend/seguimiento/segundo-parcial/interfaz-compartida-auditoria-39.md`<br>`backend/contratos/segundo-parcial/openapi-segundo-parcial.json`<br>`backend/seguimiento/segundo-parcial/41-checkpoint-post-auditoria-39.md`<br>`backend/seguimiento/segundo-parcial/README.md`<br>`backend/seguimiento/segundo-parcial/02-estado-cu.md`<br>`backend/seguimiento/segundo-parcial/04-bitacora.md`<br>`backend/seguimiento/segundo-parcial/05-reanudacion.md`<br>Supervisión y ejecución secuencial de suites finales sin colisión en base `_test`. |

---

## 2. Contrato HTTP de Recuperación de Orden Activa de Caja (R0 / P0-2)

### Endpoint
`GET /api/v1/pagos/stripe/ordenes/activa-caja`

### Query Parameters
- `sucursal_id` (UUID, obligatorio): Sucursal en la que opera el cajero.
- `turno_caja_id` (UUID, opcional): Turno activo de caja (si está en modo offline/turno).

### Reglas de Autorización y Filtrado en Backend
1. **Tenant:** `OrdenPago.empresa_id == usuario.empresa_id` y `Venta.empresa_id == usuario.empresa_id`.
2. **Cajero:** Si el usuario no es `ADMINISTRADOR`/`SUPERADMIN`, `Venta.cajero_id == usuario.id`.
3. **Turno:** Si se suministra `turno_caja_id`, `Venta.turno_caja_id == turno_caja_id`. Si no se suministra, se buscan órdenes del cajero en la sucursal (presenciales sin turno o de cualquier turno asignado).
4. **Estados de Orden Elegibles:** `OrdenPago.estado IN ('PENDIENTE', 'CAPTURADO', 'REQUIERE_ACCION_CLIENTE')` y `Venta.estado == 'PENDIENTE_PAGO'`.
5. **Determinismo ante Múltiples Órdenes:** `ORDER BY OrdenPago.creada_en DESC, OrdenPago.id DESC LIMIT 1`.
6. **Seguridad de Secretos:** `client_secret` sólo se entrega si la orden no está capturada/liquidada y la pasarela lo requiere para montar el formulario. Jamás se almacena en `localStorage` ni en `IndexedDB`.

### Estructura del JSON de Respuesta (`OrdenActivaCajaDTO`)

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

Si no hay orden activa, responde `HTTP 200` con `null` (o `HTTP 204`).

### Derivación de Campos de Dominio
- `tasa_bob_por_usd`: Derivada congelada desde `TasaCambio` asociada a `OrdenPago.tasa_id`. No se usa la tasa actual ni valores volátiles de memoria.
- `lineas`: Derivadas de los registros persistidos en `comercial.detalles_ventas` vinculados a `Venta.id`.
- `procedencia`: `"TURNO_OFFLINE"` si `Venta.turno_caja_id IS NOT NULL`, `"PRESENCIAL"` si `Venta.turno_caja_id IS NULL`.
- `estado_verificacion`:
  - `"VERIFICADO"`: La consulta al gateway Stripe fue exitosa y pasó validaciones rigurosas.
  - `"NO_VERIFICADO_ERROR_PASARELA"`: La llamada a Stripe arrojó timeout, 502 o error de red. La orden se conserva en su estado local, sin mutar a `CAPTURADO` ni `CANCELADO`, y el frontend informa estado no verificado con acción de reintento.

---

## 3. Reglas de Validación Financiera Única (P0-3)

Se extrae y aplica una única rutina de validación compartida: `validar_intencion_con_orden(inten: IntencionPago, op: OrdenPago)`:

1. **ID de Intención:** `inten.id == op.referencia_externa` (o `op.clave_externa`).
2. **Moneda:** `inten.moneda.lower() == "usd"`.
3. **Centavos Congelados:** Si `op.centavos_usd` está definido, `inten.monto_centavos == op.centavos_usd`.
4. **Metadata de Empresa:** `inten.metadata["empresa_id"] == str(op.empresa_id)`.
5. **Metadata de Recurso:**
   - Si `op.contexto == "VENTA"`, `inten.metadata["venta_id"] == str(op.venta_id)`.
   - Si `op.contexto == "PEDIDO"`, `inten.metadata["pedido_id"] == str(op.pedido_id)`.
6. Si alguna falla: rechazar con `HTTP 400 Bad Request` explicando el desajuste exacto. Jamás transicionar a `CAPTURADO`, no liquidar y no liberar stock.
7. Esta rutina se invoca obligatoriamente en:
   - `confirmar_orden_pago`
   - `obtener_orden_activa_caja`
   - `cancelar_ventas_stripe_vencidas` (al encontrar una intención con estado `SUCCEEDED` / `CAPTURADO`)

---

## 4. Reglas del Worker de Vencimiento de Ventas (P0-1)

En `cancelar_ventas_stripe_vencidas`:
1. Si la intención tiene `SUCCEEDED` / `CAPTURADO`:
   - Validar con `validar_intencion_con_orden`.
   - Si pasa validación: sincronizar `OrdenPago.estado = 'CAPTURADO'`, `Pago.estado = 'APROBADO'`, commit, añadir a `omitidas`. **NUNCA liberar stock**.
   - Si no pasa validación: registrar error/incertidumbre, rollback, añadir a `omitidas`, **NUNCA liberar stock**.
2. Si la intención NO está `CANCELED`:
   - Invocar `gateway.cancelar_intencion(ref_pi)`.
   - Si la llamada arroja excepción (timeout, 502, error de red) o retorna un estado distinto de `CANCELED`:
     - **NO capturar con `except: pass`**.
     - Rollback de la transacción de esa venta.
     - Añadir `venta_id` a `omitidas`.
     - **NO tocar `comprometido_digital` ni `disponible`**.
     - **NO registrar Kardex `LIBERACION_DIGITAL`**.
     - Conservar `Venta.estado = 'PENDIENTE_PAGO'` y `OrdenPago.estado = 'PENDIENTE'`.
     - Continuar con las demás ventas del lote (un fallo no aborta el lote).
3. Si la llamada a `cancelar_intencion` arroja `HTTP 400` porque el PaymentIntent ya fue capturado concurrentemente:
   - Reconsultar intención en Stripe. Si está `SUCCEEDED`, validar y marcar `CAPTURADO`. Commit.
   - Si no, añadir a `omitidas` y rollback.
4. Únicamente si el gateway confirma `CANCELED` (o responde 404):
   - Liberar `comprometido_digital` -> `disponible`.
   - Emitir Kardex `LIBERACION_DIGITAL`.
   - Marcar `Venta.estado = 'CANCELADA'`, `OrdenPago.estado = 'CANCELADO'`.
   - Commit.

---

## 5. Comportamiento en Caja Angular (P0-2)

1. **Al iniciar (`ngOnInit`) o tras recarga (F5):**
   - Invocar `recuperarOrdenActivaCaja()`.
   - Consumir el DTO `OrdenActivaCajaDTO`.
2. **Si `procedencia === 'TURNO_OFFLINE'`:**
   - Seleccionar panel offline (`vistaModo = 'TURNO_OFFLINE'`).
   - Asignar `ordenStripeCaja = orden`, `medioPagoCaja = 'STRIPE_TEST'`.
   - Reconstruir `lineasVentaOffline` desde `orden.lineas`:
     `{ variante_id, cantidad, precio_bob: Number(l.precio_unitario_bob) }`.
   - Si `cliente_id` existe, restaurar `clienteIdCaja`.
   - Si `estado_orden === 'CAPTURADO'`:
     Habilitar botón "Liquidar Venta" con los datos y líneas ya restaurados sin exigir crear un nuevo cobro.
   - Si `estado_orden === 'PENDIENTE'` y `client_secret`:
     Montar Stripe CardElement y habilitar confirmación o cancelación.
3. **Si `procedencia === 'PRESENCIAL'`:**
   - Seleccionar panel presencial directo (`vistaModo = 'RESERVA'`).
   - Asignar `ordenStripePresencial = orden`, `metodo = 'STRIPE_TEST'`.
   - Reconstruir `items` desde `orden.lineas`:
     `{ variante_id, cantidad }`.
   - Si `cliente_id` existe, restaurar `clienteIdPresencial`.
   - Manejo análogo de estados `CAPTURADO` y `PENDIENTE`.
4. **Manejo de `estado_verificacion === 'NO_VERIFICADO_ERROR_PASARELA'`:**
   - Mostrar advertencia visible y accesible en caja: "No se pudo verificar el estado en Stripe por problema de red. Reintente la verificación antes de cobrar."
   - Ofrecer botón de reintento.
   - No asumir falsamente éxito ni cancelación.
5. **Liquidación posterior a F5:**
   - Al pulsar "Liquidar Venta", enviar `VentaPresencialLiquidarDTO` con:
     `venta_id: orden.venta_id`, `orden_pago_id: orden.orden_pago_id`, `stripe_payment_intent_id: orden.stripe_payment_intent_id`, y las líneas restauradas del servidor.
   - El backend revalida pertenencia, estado `CAPTURADO` y coincidencia de líneas, liquidando exitosamente la misma venta.
