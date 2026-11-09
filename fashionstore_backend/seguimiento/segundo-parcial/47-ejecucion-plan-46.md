# Ejecución del plan 46 y resultado de cierre

**Fecha:** 06/11/2026. **Estado:** plan 46 aprobado por el propietario y ejecutado parcialmente. **Dictamen:** FashionStore aún no queda cerrado; E2 sigue en avance sin aceptar. Este checkpoint sustituye como estado operativo a los informes anteriores, sin borrar su historial.

## Cambios y correcciones verificadas

- Stripe valida PaymentIntent contra el monto exacto en centavos, USD, ID, empresa y recurso de la operación antes de marcar una captura. La cancelación conserva inventario cuando Stripe no confirma `CANCELED`; la reanudación recupera por clave durable.
- CU19 consulta Stripe fuera de los bloqueos de inventario y liquida importes/líneas persistidos. La recepción de inventario asigna empresa al lote para cumplir el trigger de tenant.
- Se corrigió una carrera en CU21: dos checkout concurrentes con la misma clave podían insertar dos registros de idempotencia y filtrar `IntegrityError`. El servicio ahora reclama la clave en el ámbito (usuario, recurso, operación), serializa checkouts del mismo carrito y devuelve el mismo pedido en el reintento. Se agregó la prueba contractual test_cu21_checkout_concurrente_misma_clave_retorna_mismo_pedido en tests_segundo_parcial_bloque_b/test_b2_compras_cu21_cu19_cu05.py; el cambio del servicio está en app/core/modules/ventas_pagos/services/pedido_service.py.
- Las pruebas del Bloque B se ejecutaron en la base aislada `fashionstore_cierre_test`; `alembic current` confirma `0014_pago_ref_externa_unique (head)`. No se usó ni modificó `fashionstore_db`.

## Verificación reproducible

| Área | Resultado | Lectura |
|---|---|---|
| Backend, suite completa Bloque B | **290 passed, 5 warnings**, 209.31 s | Verde; incluye CU21 checkout, E2, contraejemplos, contratos OpenAPI y caja/Stripe simulados. |
| Backend, checkout CU21 | **2 passed** | Pasa idempotencia secuencial y dos peticiones simultáneas con la misma clave; un `pedido_id`. |
| Backend, identidad/infraestructura/CU04 | **20 passed, 1 warning**, 20.87 s | Verde sobre la base aislada, después del cambio de idempotencia. |
| Backend, validación Stripe estricta | **15 passed** en ejecución previa de esta sesión | Verde; el cambio posterior fue en CU21 y no altera este módulo. |
| Backend, suite heredada amplia `tests/` + validación Stripe | **92 failed, 97 passed, 2 warnings**, 370.90 s antes del arreglo CU21 | No es una puerta verde. Incluye fixtures antiguos (administrador de empresa usado donde se exige superadministrador global, falta de suscripción/empresa en datos directos) y expectativas previas del contrato (p. ej. checkout espera `venta_id` y estado de venta donde CU21 actual devuelve `pedido_id` y pedido `BORRADOR`). Aún hay que comparar cada grupo fallido con el contrato vigente; no se atribuye todo a pruebas obsoletas ni a regresiones de producto sin esa auditoría. La suite amplia no se repitió después del arreglo concurrente. |
| Backend, compilación Python | `compileall` de Stripe, caja y CU21: exit 0 | Verde. |
| Frontend Angular/PWA, Karma | **303/303 SUCCESS** | Verde en Chrome Headless. |
| Frontend Angular/PWA, build producción | Exit 0; bundle inicial 366.38 kB | Verde. Dos avisos de presupuesto CSS: inteligencia 19.35 kB (máximo 12.29 kB) y dashboard 12.32 kB (máximo 12.29 kB). |
| Flutter, análisis estático | **0 issues**, 50.9 s (`--no-pub`) | Verde. |
| Flutter, suite completa | **Sin resultado** | `flutter test` no terminó en ejecución directa; el runner seguro agotó 180 s en `-Suite unit`, antes de producir conteo. No declarar la suite móvil aprobada. Se intentó la prueba enfocada de pagos offline y notificaciones; tampoco produjo resultado tras más de 3 minutos y se interrumpió. No hay conteo móvil unitario o widget. |
| Migración | `0014_pago_ref_externa_unique (head)` | Confirmada en `fashionstore_cierre_test`; no en la base diaria. |
| Git | `git diff --check` exit 0 en los tres repositorios | Hay cambios y archivos sin commit preexistentes; ramas y HEAD registrados abajo. No se hizo commit, push, merge ni despliegue. |

### Ramas y HEAD observados

| Repositorio | Rama | HEAD |
|---|---|---|
| Backend | `feature/sp2-e2-integral` | `986bac50ae727c166d31f98aa215538b21d95335` |
| Frontend web | `feature/sp2-e2-integral` | `9992cdc05a598064e7e43534dd838a36ead1d40a` |
| App móvil | `feature/sp2-e2-integral` | `7880a156eaf0254bd032afd7ab9dfbcbc2f144b6` |

HEAD es el último commit, no incluye los cambios actuales del working tree. No se hizo commit porque la regresión heredada sigue roja, Flutter no entregó un conteo completo y los working trees contienen trabajo previo que no debe mezclarse sin revisión.

## Pendiente para poder cerrar

1. Terminar las pruebas móviles enfocadas y hallar por qué la suite `unit` supera el timeout. Verificar por separado unitarias y widget; `integration_test/` no existe en este repositorio y el recorrido final necesita Android físico.
2. Clasificar y resolver la suite heredada de backend por grupos: contrato/API vigente, permisos de plataforma frente a tenant, suscripción/fixtures y defectos reales. Actualizar pruebas solo cuando el contrato confirme que cambió el comportamiento esperado. Repetirla después de CU21.
3. Mantener las verificaciones externas como pendientes: Stripe Test con tarjeta/3DS/webhook/reembolso, push real FCM/Web Push, PWA offline con reconexión y dispositivos Android. Las pruebas con gateway falso no sustituyen estas actas.
4. Revisar los dos avisos CSS si deben quedar bajo presupuesto; no bloquean la compilación.
5. Tras puertas verdes y revisión final, registrar commits por lote y repositorio según [ramas y commits](03-ramas-y-commits.md). No hacer push, merge o despliegue por inferencia.

## Comandos comprobados

Desde `backend` (la URL se construye localmente y no se guarda en el repositorio):

```powershell
$env:FASHIONSTORE_TEST_DATABASE_URL = "postgresql+asyncpg://<usuario>:<clave>@127.0.0.1:5432/fashionstore_cierre_test"
.\venv\Scripts\python.exe -m pytest tests_segundo_parcial_bloque_b/ -q -p no:cacheprovider --tb=short
```

Desde `frontend-web`:

```powershell
npm.cmd test -- --watch=false
npm.cmd run build
```

Desde `app-movil`:

```powershell
flutter.bat analyze --no-pub
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_tests.ps1 -Suite unit -TimeoutSeconds 180 -SkipAnalyze
```

Leer primero este archivo, luego el [estado por CU](02-estado-cu.md), [bitácora](04-bitacora.md) y [plan aprobado](46-plan-ejecucion-cierre-proyecto.md). No usar el checkpoint 44 o los reportes anteriores como estado más reciente.
