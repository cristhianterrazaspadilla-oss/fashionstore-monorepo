# Plan de cierre E2 posterior a la auditoría independiente 42

**Fecha:** 06/11/2026 (Bolivia). **Estado:** preparado para el agente implementador; ejecución pendiente. **Fuente:** [auditoría 42](42-auditoria-independiente-post-checkpoint-41.md). **Ramas:** `feature/sp2-e2-integral` en los tres repositorios. E2 continúa **en avance sin aceptar**.

## Objetivo

Resolver completamente los tres bloqueos P0 y el caso provisional P1 de CU19/CU22, manteniendo el negocio de CU06/CU07 y el resto de E1/E2. Los cuatro casos son una misma puerta financiera: un PI capturado debe corresponder a una única venta, un importe congelado y una unidad comprometida; una cancelación no verificada nunca devuelve stock; una falla entre transacciones debe poder reanudarse sin segunda venta ni segundo PI.

## Puertas de trabajo

| Puerta | Resultado exigido | Prueba que debe fallar antes y pasar después |
|---|---|---|
| **J0 — acuerdo de interfaz** | Estado de orden provisional, reanudación autenticada, JSON de caja, transiciones y evidencia de validación financiera definidos desde modelos reales; contrato y consumidores coordinados antes de editar. | Contrato API/TypeScript y escenario provisional con respuesta exacta. |
| **J1 — cancelación manual segura** | `cancelar_orden_pago` sólo marca `CANCELADO` y libera stock tras confirmar `CANCELED` para el PI correcto. Otros estados, timeout y respuesta inválida conservan venta, orden y stock para reintento. | Gateway responde normalmente `REQUIRES_PAYMENT_METHOD`, `PROCESSING` o ID distinto al cancelar; cero `LIBERACION_DIGITAL`. |
| **J2 — captura validada en todas las entradas** | Confirmación, recuperación, vencimiento, webhook firmado, continuación 3DS y liquidación aplican la misma comprobación de ID, metadata de empresa/recurso, moneda y centavos. Consulta fallida no se silencia ni liquida. Captura y webhook duplicados son idempotentes. | Webhook/3DS con metadata o monto distintos; gateway indisponible al liquidar; estado local y Kardex sin falso éxito. |
| **J3 — precio y promoción congelados** | La venta Stripe iniciada se liquida con `Venta.total`, `DetalleVenta`, `OrdenPago` y tasa persistidos. Cambios posteriores de precio/promoción no alteran el cargo ni bloquean la entrega. Líneas del cliente se comparan con las persistidas. | Inicio a precio A → captura → cambio a B → F5 → liquidación una sola vez a A; inventario y comprobante exactos. |
| **J4 — orden provisional reanudable** | Si falla el proceso tras el primer commit o después de crear el PI antes del segundo, un cajero autorizado recupera y reanuda la **misma** venta/orden mediante clave durable; no se expone `PENDIENTE_{clave}` como PI. | Simular caída en ambos puntos, F5 y reintento; una venta, una reserva, un PI, cero doble Kardex. |
| **J5 — integración y salida** | Pruebas focalizadas y suite backend sobre PostgreSQL `_test`; Angular tsc, Karma y build secuenciales; OpenAPI/contratos sincronizados; Git limpio de errores de whitespace/secretos; checkpoint honesto. | JSON real, estados DB y UI, codes de salida y matriz de regresiones. |

## Distribución sin colisiones

- **Subagente A, Stripe y transiciones:** dueño único de `stripe_service.py`, router/DTO Stripe y pruebas focalizadas propias. J1/J2 y parte API de J4. Coordina con B el método de reanudación; no edita `venta_presencial_service.py`.
- **Subagente B, venta e inventario:** dueño único de `venta_presencial_service.py` y pruebas focalizadas propias. J3 y operación idempotente de J4. No edita `stripe_service.py`.
- **Subagente C, Angular/PWA:** dueño de caja, servicios/modelos frontend y sus tests. Consume contrato J0, muestra provisional/reintento, permite F5 y liquidación congelada. No edita backend.
- **Coordinador:** dueño de interfaz compartida, contratos de los repositorios, OpenAPI, tests verticales nuevos de integración y seguimiento. Revisa cada diff, asigna cualquier archivo adicional a un solo dueño, serializa suites que usen la misma DB y entrega checkpoint. Si necesita trabajo paralelo adicional, puede delegar inspecciones de sólo lectura sin dos editores del mismo archivo.

## Reglas de implementación

- Leer `AGENTS.md`, skills `fashionstore-ciclo-2` y `fashionstore-frontend-continuity`, plan backend Ciclo 2 y fichas CU19/CU22; preservar cupos offline CU06/CU07. No tocar CU17/Decart.
- Conservar árboles de trabajo y ramas actuales; sin `reset --hard`, `clean`, stash automático ni sobrescritura de cambios ajenos. No aplicar migraciones/fixtures a `fashionstore_db`. Si se requiere migración, probar upgrade y downgrade únicamente en copia `_test`.
- No resolver errores financieros cambiando tests, ocultando excepciones o fabricando `CAPTURADO`, `CANCELED`, precio o PI. Cada movimiento de inventario tiene Kardex único; capturas, cancelaciones, webhook y reintentos son idempotentes bajo concurrencia.
- Si Stripe/FCM/dispositivo físico faltan, reportar esa validación externa como pendiente y terminar todas las pruebas automatizables. No confundir dobles de pasarela con prueba real.

## Criterio de entrega y registro

El agente deja un checkpoint posterior a la auditoría 42 con matriz J0–J5, contraejemplos rojos/verdes, comandos y exit codes, JSON/estados reales, base `_test` utilizada sin credenciales, migraciones, archivos, ramas/HEAD, pruebas externas pendientes y riesgos residuales. Actualiza `README.md`, `02-estado-cu.md`, `04-bitacora.md` y `05-reanudacion.md`. Conserva E2 **en avance sin aceptar**, sin commit, push, merge ni despliegue. Sólo la revisión independiente posterior decide cierre y registro de commits.
