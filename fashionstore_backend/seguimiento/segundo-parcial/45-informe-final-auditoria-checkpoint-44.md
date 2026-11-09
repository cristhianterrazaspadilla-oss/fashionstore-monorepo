# Informe puntual de estado — revisión del checkpoint 44

**Corte:** 06/11/2026, Bolivia. **Dictamen:** el proyecto aún no cumple las condiciones de cierre. La entrega 1 está registrada técnicamente; la entrega 2 conserva bloqueos financieros y cambios sin commit.

## Porcentajes verificables

| Indicador | Resultado | Alcance de la cifra |
|---|---:|---|
| Casos de uso con implementación entregada para revisión | **27/27 = 100 %** | 14 de E1 y 13 de E2, según `02-estado-cu.md`; no significa aceptación funcional. |
| Casos de uso en entrega técnica previamente revisada y registrada en commits | **14/27 = 52 %** | E1, según `14-entrega-e1-y-plan-e2.md`; sus pruebas manuales aún tienen límites declarados. |
| Casos de uso de E2 pendientes de aceptación y registro | **13/27 = 48 %** | E2 está en tres árboles de trabajo con cambios sin commit. |

**Porcentaje de cierre técnico defendible: 52 %.** El 100 % expresa cobertura de código declarada, no un sistema listo para cerrar o desplegar. No hay base para asignar un porcentaje intermedio de calidad funcional a los 13 CU de E2.

## Qué se tiene

- Backend FastAPI, Angular/PWA, Flutter, contratos 0.3.2/protocolo 0.4.0, migraciones PostgreSQL y seguimiento de los 27 CU.
- E1: CU01, CU02, CU03, CU04, CU06, CU07, CU12, CU13, CU14, CU15, CU16, CU17, CU18 y CU26, con commits y verificación técnica documentada en la entrega 14.
- E2: CU05, CU08, CU09, CU10, CU11, CU19, CU20, CU21, CU22, CU23, CU24, CU25 y CU27, entregados para revisión. El checkpoint 44 incorpora cancelación financiera, liquidación congelada y reanudación de órdenes provisionales.
- Verificación independiente de este corte: Angular Karma **303/303**, build **exit 0** con dos advertencias de presupuesto CSS, compilación Python de `ventas_pagos` **exit 0** y Flutter Analyze **exit 0**, sin problemas. El implementador reporta **66 pytest focalizados**, pero esta sesión no tiene `FASHIONSTORE_TEST_DATABASE_URL` y no repitió la suite backend integral sobre una base `_test`.

## Bloqueos de cierre

1. **P0 — Webhook de pago acepta campos ausentes.** `stripe_service.py:1197-1202` convierte moneda ausente en `usd`; `:1263-1283` sólo compara metadata del evento cuando está presente. Un caso mínimo ejecutado sobre `_validar_intencion_con_orden` aceptó `metadata: {}` y también `currency` ausente con ID y monto coincidentes. `confirmarWebhook` llama esa validación antes de `_aplicar_aprobado_orden` (`:286-288`), por lo que la ruta puede registrar `CAPTURADO` sin toda la evidencia exigida por J2.
2. **P0 — Liquidación presencial usa una validación financiera distinta y permisiva.** `venta_presencial_service.py:742-765` admite `bob`, omite comparar centavos si faltan y sólo comprueba `empresa_id`/`venta_id` cuando vienen en metadata. Luego puede marcar la orden `CAPTURADO` (`:777-779`). J2 exige USD, importe exacto y pertenencia completa en todas las rutas.
3. **P1 — Cancelación de orden provisional sin conciliación externa.** `stripe_service.py:1561-1562,1619-1625` salta la consulta de Stripe para la referencia `PENDIENTE_...` y cancela/libera localmente. J4 contempla explícitamente que el PI se haya creado antes de fallar la segunda persistencia; ese escenario requiere recuperar o conciliar el PI antes de liberar stock. Falta un contraejemplo que simule esa caída.
4. **Puertas de salida pendientes.** Repetir suite backend completa en PostgreSQL aislado, pruebas manuales de Stripe Test/webhook/3DS, caja offline con reconexión en PWA y Android físico, push FCM/Web Push y flujo Decart en Android físico. Revisar, registrar commits E2 y aceptar formalmente sólo tras cerrar los bloqueos.

## Estado Git y credenciales

Rama `feature/sp2-e2-integral` en los tres repositorios; HEAD: backend `986bac5`, web `9992cdc`, móvil `7880a15`. En esta revisión se observaron 77, 20 y 21 entradas modificadas/no rastreadas, respectivamente. El checkpoint 44 contenía una URL local de PostgreSQL con credencial; fue sustituida por un marcador sin secreto. Si esa contraseña sigue vigente, debe rotarse. No se hizo commit, push, merge ni despliegue en esta revisión.

**Siguiente decisión:** mantener E2 en «avance sin aceptar». Corregir las tres rutas indicadas con pruebas de contraejemplo y repetir las puertas de salida; entonces hacer la auditoría de aceptación y registrar los commits por lote revisado.
