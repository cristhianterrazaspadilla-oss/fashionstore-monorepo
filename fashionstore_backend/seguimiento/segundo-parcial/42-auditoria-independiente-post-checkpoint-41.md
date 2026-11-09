# Auditoría independiente 42 — entrega posterior al checkpoint 41

**Fecha:** 06/11/2026 (Bolivia). **Dictamen:** E2 permanece **en avance sin aceptar**. Los cambios del [checkpoint 41](41-checkpoint-post-auditoria-39.md) corrigen los contraejemplos focalizados de la auditoría 39, pero aún hay rutas financieras que impiden cerrar la presentación o registrar commits de aceptación.

## Mejoras corroboradas

- El worker de vencimiento ahora conserva venta y stock cuando `cancelar_intencion` lanza una excepción y omite una captura concurrente que detecta al reconsultar. Hay una prueba nueva con estados de DB, inventario y Kardex.
- `GET /api/v1/pagos/stripe/ordenes/activa-caja` declara y devuelve `OrdenActivaCajaDTO`; Angular consume ese tipo y repone líneas, procedencia y estado. La validación compartida se usa en esa lectura y en la confirmación explícita.
- Verificación propia: TypeScript `tsc` **exit 0**; Karma con `ChromeHeadlessNoSandbox` **300/300 SUCCESS, exit 0**; `npm run build` repetido secuencialmente **exit 0** (dos advertencias de presupuesto CSS); `compileall` de los módulos Python tocados **exit 0**. La ejecución simultánea inicial del build falló por acceso a archivos mientras Karma/compilación corrían; el reintento secuencial pasó.

## Bloqueos de cierre

### P0-1 — La cancelación manual aún puede liberar stock sin confirmación de cancelación

En `backend/app/core/modules/ventas_pagos/services/stripe_service.py:1513-1524`, `cancelar_orden_pago` llama a `gateway.cancelar_intencion(ref_pi)`. Sólo trata explícitamente `SUCCEEDED`/`CAPTURADO`; si la pasarela **responde normalmente con otro estado** (`REQUIRES_PAYMENT_METHOD`, `REQUIRES_ACTION`, `PROCESSING` o respuesta inválida), el flujo cae a `op.estado = "CANCELADO"` (`:1538`) y libera la venta y su inventario (`:1542-1579`). El worker nuevo sí exige `CANCELED`, pero esta ruta manual no lo hace. Las pruebas nuevas cubren excepción y captura, no respuesta no cancelada.

**Puerta:** exigir confirmación `CANCELED` de la intención correcta antes de cancelar localmente y liberar stock. Cualquier otro estado conserva la venta y el compromiso para conciliación/reintento. Añadir contraejemplo con gateway que devuelve `REQUIRES_PAYMENT_METHOD` sin lanzar, verificando DB y Kardex.

### P0-2 — Webhook y continuación 3DS pueden registrar captura sin la validación común

La rutina nueva `_validar_intencion_con_orden` se invoca en confirmación explícita, recuperación y vencimiento, pero `confirmarWebhook` llama a `_aplicar_aprobado_orden` para `payment_intent.succeeded` (`stripe_service.py:268-303`); ese método pone `op.estado = "CAPTURADO"` (`:452-457`) sin comprobar importe, moneda ni metadata del evento/intención. `continuar_accion` también pone `CAPTURADO` (`:1635-1653`) después de comprobar sólo moneda e importe, sin ID ni metadata de empresa/recurso. `confirmar_orden_pago` devuelve de inmediato cuando la orden ya figura capturada (`:1401-1411`). Por tanto, una captura almacenada por estas rutas elude la puerta financiera declarada en el checkpoint. En la liquidación de CU19, una excepción al consultar Stripe se silencia (`venta_presencial_service.py:762-788`); el estado local capturado puede bastar para seguir.

**Puerta:** todas las rutas que persisten `CAPTURADO` deben usar una validación equivalente sobre evidencia verificable del proveedor. En webhook firmado, validar los campos del objeto del evento contra la orden o reconsultar de forma segura; manejar eventos duplicados y carreras. En 3DS, validar ID y metadata además de importe/moneda. La liquidación no debe aceptar incertidumbre sin una prueba durable previa de validación. Añadir pruebas con webhook firmado/3DS de importe y metadata discordantes y consulta fallida al liquidar.

### P0-3 — Una venta ya cobrada puede quedar imposible de liquidar al cambiar precio o promoción

`iniciar_stripe` congela `Venta.total`, `DetalleVenta` y `OrdenPago.monto_bob` (`venta_presencial_service.py:284-314, :349-410`). `liquidar` vuelve a leer `VarianteProducto.precio` y `PromocionService.mejorDescuento` actuales (`:578-611`) y exige que el total recalculado coincida exactamente con `OrdenPago.monto_bob` (`:797-802`). Si precio o promoción cambian entre inicio y liquidación, Stripe puede haber capturado el importe original y la liquidación devuelve 400. La recuperación tras F5 añade el precio original a la solicitud, que además falla la comprobación de «precio desactualizado» (`:584-599`). La prueba Angular de F5 sólo comprueba la llamada mockeada; no ejecuta la liquidación real con precio modificado.

**Puerta:** para una venta Stripe iniciada, liquidar con las líneas, promociones e importe **congelados y persistidos** en la venta/orden; comprobar que la solicitud corresponde a esas líneas y que el PI validado coincide con la orden. La variación posterior del catálogo no debe cambiar el cargo ni bloquear entrega. Añadir prueba vertical: iniciar a precio A, capturar, cambiar precio/promoción a B, recuperar tras F5 y liquidar exactamente una vez con total A, stock y Kardex correctos.

### P1 — Orden provisional sin reanudación visible tras fallo entre transacciones

`iniciar_stripe` confirma reserva y orden `PENDIENTE_{clave}` antes de crear la intención (`venta_presencial_service.py:394-445`). Si la llamada o persistencia posterior falla, la recuperación busca esa referencia provisional en Stripe y devuelve un PI que no existe (`stripe_service.py:1344-1384`); el cliente genera una `Idempotency-Key` nueva en cada inicio (`frontend-web/.../services/venta-presencial.service.ts:24-33`). Tras F5 no dispone de la clave original para reanudar la orden provisional (`venta_presencial_service.py:194-218`). El stock queda comprometido hasta vencimiento y la caja no tiene una acción clara para completar/cancelar ese intento.

**Puerta:** recuperación/reintento del servidor por la venta provisional y su clave durable, con transición idempotente hacia un único PI o cancelación verificada; no exponer el marcador `PENDIENTE_...` como PaymentIntent. Cubrir caída de proceso tras el primer commit y fallo tras respuesta de Stripe antes del segundo commit.

## Verificación y estado de pruebas

- `FASHIONSTORE_TEST_DATABASE_URL` no está definida en esta sesión. No se repitió pytest contra PostgreSQL; **267 passed** es el resultado informado por el implementador, no una reproducción independiente. Las pruebas nuevas no cubren los contraejemplos anteriores.
- `git diff --check`: backend, Angular y Flutter **exit 0**. Se quitó una línea en blanco final de `04-bitacora.md` detectada durante la auditoría.
- No se ejecutó Stripe Test externo, FCM real ni prueba en Android físico en esta auditoría. El checkpoint distingue esos límites.
- Ramas y HEAD permanecen `feature/sp2-e2-integral`: backend `986bac5`, Angular `9992cdc`, Flutter `7880a15`; sin commits de aceptación, push, merge o despliegue.

## Siguiente revisión

Corregir P0-1 a P0-3 y el caso provisional P1 con pruebas de contraejemplo y suite de integración sobre una base `_test`. Repetir revisión independiente del diff, OpenAPI, Angular y estados de DB/Stripe simulado antes de decidir cierre o commits. Mantener E2 en **avance sin aceptar**.
