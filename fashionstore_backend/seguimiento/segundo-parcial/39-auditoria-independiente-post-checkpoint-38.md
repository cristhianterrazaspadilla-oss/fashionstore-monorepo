# Auditoría independiente 39 — entrega posterior al checkpoint 38

**Fecha:** 06/11/2026 (Bolivia). **Ramas:** `feature/sp2-e2-integral` en backend, frontend-web y app-movil. **Dictamen:** E2 continúa **en avance sin aceptar**. No procede cerrar la presentación ni registrar commits de aceptación.

## Alcance y mejoras comprobadas

Se contrastó el [checkpoint del implementador](38-checkpoint-post-auditoria-36.md) con código, DTO y consumidores. La iniciación de CU19 ahora compromete inventario digital antes de invocar Stripe, y la llamada de creación de intención sucede después del commit de reserva. La cancelación manual del backend conserva la orden ante error de pasarela; la caja Angular conserva su referencia ante errores de cancelación. La confirmación explícita exige metadata de pertenencia. Estas mejoras no subsanan los bloqueos siguientes.

## Bloqueos de cierre

### P0-1 — El vencimiento libera stock si Stripe no cancela

En `backend/app/core/modules/ventas_pagos/services/stripe_service.py:573-577`, `cancelar_ventas_stripe_vencidas` consulta una intención aún no cancelada y llama a `gateway.cancelar_intencion`. Si esa llamada falla, el `except Exception: pass` continúa. La misma iteración libera `comprometido_digital` o `reservado` (`:593-620`), marca venta y orden canceladas y hace commit (`:623-640`). Así puede coexistir un cobro externo vigente o capturado con una venta local cancelada y la unidad nuevamente disponible. La consulta anterior a la cancelación no prueba el resultado de la cancelación ni cubre una captura concurrente.

**Corrección exigida:** ante timeout, error o resultado distinto de cancelación confirmada, conservar venta, orden y stock, registrar estado incierto/reintento y continuar con otra venta. Si Stripe informa captura, conciliar el pago sin liberar stock. Añadir una prueba con `consultar_intencion=REQUIRES_PAYMENT_METHOD` y `cancelar_intencion` fallando, y otra con captura concurrente. Verificar estados, inventario y Kardex después del worker, no sólo la respuesta.

### P0-2 — Recuperación de caja incompatible entre API y Angular

`GET /api/v1/pagos/stripe/ordenes/activa-caja` declara `OrdenPagoDTO` (`backend/app/core/modules/ventas_pagos/routers/pagos_stripe.py:205-230`), y `StripeService.obtener_orden_activa_caja` retorna ese esquema (`stripe_service.py:1172-1181`). Incluye `estado` y `referencia_externa`, pero no `venta_id`, `stripe_payment_intent_id`, `tasa_bob_por_usd` ni `estado_orden` (`models_ordenes.py:130-139`). Angular lo tipa sin conversión como `IniciarVentaPresencialStripeRespuestaDTO` (`frontend-web/src/app/features/ventas_pagos/services/stripe.service.ts:110-120`), que exige exactamente esos campos (`models/venta-presencial.models.ts:19-28`). La caja asigna la respuesta directamente y lee `estado_orden` (`caja/caja.component.ts:193-218`); al liquidar usa `venta_id` y `stripe_payment_intent_id` ausentes (`:696-707`). Tras F5, las líneas de venta en memoria tampoco se restauran. La prueba Angular `caja.component.spec.ts:1267-1295` simula un DTO completo que el backend no devuelve, por lo que pasa sin detectar la incompatibilidad.

**Corrección exigida:** definir una respuesta dedicada de recuperación con identificador de venta, intención, estado, tasa, turno/modo y líneas persistidas; actualizar OpenAPI y el tipo TypeScript desde esa respuesta real. Restaurar la venta en el panel correcto y habilitar la liquidación de una orden capturada después de F5. Probar el JSON exacto del endpoint contra el consumidor, con F5 antes y después de captura.

### P0-3 — La lectura de recuperación puede marcar CAPTURADO sin validar la intención

En `stripe_service.py:1159-1169`, una consulta de estado `SUCCEEDED` marca la orden `CAPTURADO` y hace commit sin validar importe, moneda, ID de intención ni metadata de empresa/venta. La validación estricta incorporada a `confirmar_orden_pago` queda omitida en esta ruta. Además, `except Exception: pass` (`:1169-1170`) oculta fallas de consulta y devuelve un estado potencialmente obsoleto.

**Corrección exigida:** reutilizar una única conciliación que compruebe pertenencia, intención, moneda e importe antes de persistir captura; representar explícitamente indisponibilidad de Stripe sin afirmar éxito. Añadir pruebas para intención `SUCCEEDED` ajena, importe o moneda distintos y error de red.

## Verificación independiente de esta auditoría

- `tsc -p tsconfig.app.json --noEmit`: **exit 0**.
- Karma/ChromeHeadless: **no ejecutó las pruebas** en este entorno; Chrome falló al iniciar el proceso GPU dos veces (`GPU process isn't usable`, launcher exit 1). Las 296 pruebas son un resultado reportado por el implementador, no repetido aquí.
- La variable `FASHIONSTORE_TEST_DATABASE_URL` no está configurada en esta sesión; no se repitió pytest sobre PostgreSQL. El checkpoint reporta 257 pruebas pasadas.
- Flutter: `flutter analyze --no-pub` se lanzó, no produjo resultado tras una espera prolongada y se interrumpió; no hay verificación independiente de análisis ni de las 239 pruebas reportadas en el checkpoint.
- Proveedores externos Stripe/FCM y dispositivo Android físico siguen sin prueba manual en esta auditoría.

## Puerta para la siguiente revisión

Corregir P0-1 a P0-3, agregar pruebas de contraejemplo con los payloads reales, ejecutar las suites en entorno funcional y repetir la revisión independiente. Mantener los cambios sin commit de aceptación, push, merge ni despliegue hasta el dictamen. El alcance de E1 y la planificación 14+13 no cambian.
