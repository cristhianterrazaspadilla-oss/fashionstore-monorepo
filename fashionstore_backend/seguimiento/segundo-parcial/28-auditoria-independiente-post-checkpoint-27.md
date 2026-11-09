# Auditoría independiente posterior al checkpoint 27

**Corte:** 05/11/2026. **Ramas:** `feature/sp2-e2-integral` en backend, frontend-web y app-movil. **Dictamen:** la Entrega 2 sigue en **avance sin aceptar**. El checkpoint 27 registra avances reales, pero sus declaraciones de cierre de CU05, CU22, CU19 y avisos push no coinciden con las rutas ejecutadas por las interfaces. No se hicieron commits, push, merge ni despliegues en esta revisión.

## Verificación repetida

| Canal | Resultado independiente |
|---|---|
| Backend / PostgreSQL `fashionstore_test` | `pytest tests_segundo_parcial_bloque_b -q --disable-warnings`: **233 passed, 6 warnings**, 155.36 s. |
| Angular | `npm.cmd test -- --watch=false --progress=false`: **264/264**. `npx.cmd tsc -p tsconfig.app.json --noEmit`: exit 0. `npm.cmd run build`: exit 0, con avisos de tamaño CSS en Inteligencia y Dashboard. |
| Flutter | `flutter analyze --no-pub`: **0 issues**. Dos intentos de `flutter test --no-pub --reporter expanded` (el segundo con `--concurrency=1`) no produjeron salida durante una espera prolongada y se interrumpieron. La cifra de **224 passed** del checkpoint 27 queda como reporte del agente, **sin corroboración independiente**. El diagnóstico de buffering del reporte compacto no explica el silencio con `--reporter expanded`. |
| Git | `git diff --check` exit 0 en los tres repositorios; sólo avisos de normalización LF/CRLF. Cambios de E2 aún sin commit. |

Las suites que pasan no cubren el recorrido vertical PWA → cola offline → DTO FastAPI, una captura de tarjeta real ni la entrega push conforme al proveedor.

## Bloqueos comprobados

### P0 — CU22/CU05: la PWA no monta Stripe Elements

En `frontend-web/src/app/features/ventas_pagos/checkout/checkout.component.ts:210-214`, `cardElement` y `elements` nacen `null` y `mostrandoFormularioTarjeta` nace `false`. No existe asignación posterior ni llamada `elements.create(...).mount(...)` en ese componente. El contenedor de tarjeta está oculto por `*ngIf="mostrandoFormularioTarjeta"` en `checkout.component.html:262`. `confirmarSetupIntentConPasarela` llama `confirmCardSetup(clientSecret, {})` cuando `cardElement` es nulo (`checkout.component.ts:598-625`). Por tanto, un cliente nuevo no puede introducir tarjeta ni preparar el método desde esta pantalla. El emulador global sólo hace pasar los tests.

**Salida exigida:** montar Stripe Elements después de renderizar el contenedor, esperar tarjeta válida, confirmar SetupIntent con ese elemento, desmontarlo al salir y probar el recorrido DOM con Stripe.js simulado sin inyectar directamente `cardElement`.

### P0 — CU05: la autorización offline PWA contiene claves prohibidas

`checkout.component.ts:739-757` añade `consentimiento`, `metodo_preparado_id` y `huella_dispositivo` al objeto de los 15 campos contractuales. `src/app/core/services/sincronizacion-offline.service.ts:268-287` conserva las tres claves al encolar. `backend/app/core/modules/reservas_traslados/schemas_sincronizacion.py:92-110` usa `extra="forbid"` para `AutorizacionCobroV3DTO`. La validación directa del DTO con un objeto base válido devuelve `extra_forbidden` para **cada una** de esas tres claves. La compra offline autorizada de la PWA será rechazada con HTTP 422 al sincronizar. Además, sin autorización `sincronizacion-offline.service.ts:260-266` selecciona `version_esquema=1`; el contrato vigente prescribe el flujo v3 sin autorización para `PENDIENTE_INTERVENCION`. `moneda_cobro` tiene un valor por defecto en el DTO (`schemas_sincronizacion.py:103`), pese a que el esquema la declara obligatoria.

**Salida exigida:** serializar exactamente los 15 campos de v3 cuando hay autorización; seleccionar v3 también cuando se omite; exigir `moneda_cobro` explícita en backend; probar el JSON real que sale de la cola contra JSON Schema y endpoint FastAPI, tanto autorizado como pendiente.

### P0 — CU05 y avisos de compra: los adaptadores push no implementan los protocolos

`backend/app/core/modules/identidad_empresas/services/notificacion_service.py:108-125` usa el valor de `GOOGLE_APPLICATION_CREDENTIALS` o `FCM_SERVER_KEY` literalmente como `Bearer` en FCM HTTP v1. La primera variable suele ser una ruta a credenciales; HTTP v1 requiere un token OAuth2 derivado de la cuenta de servicio. `WebPushAdapter` (`:197-227`) sólo comprueba que exista `VAPID_PRIVATE_KEY` y hace POST de JSON plano al endpoint: no firma VAPID ni cifra el payload con las claves de la suscripción. Una respuesta de un `MockTransport` confirma únicamente que se hizo HTTP, no la aceptación por FCM/Web Push reales.

En la PWA, `login.component.ts:158` llama `suscribirWebPush()` sin clave pública VAPID; `web-push.service.ts:126-137` espera un service worker, pero no hay registro de service worker ni manejador `push` en `src` o `angular.json`. En Flutter, `notificacion_movil_service.dart:5-32` toma el token de `--dart-define=FCM_PUSH_TOKEN` o inyección manual; `pubspec.yaml` y `lib` no integran Firebase Messaging para obtener, renovar o recibir el token en ejecución. El scheduler backend sí está agregado, avance que se conserva.

En `notificacion_service.py:610-629`, al agotar tres intentos, el outbox pasa a `ENVIADO` si **algún** destino funcionó aunque otro siga fallando. Esa fila no se reintentará para el destino fallido. Se debe conservar el estado individual y dejar una señal explícita de entrega parcial/fallida.

**Salida exigida:** OAuth2 de cuenta de servicio para FCM v1, envío Web Push con VAPID y cifrado estándar, service worker y clave pública en PWA, token/refresh y receptor FCM en Flutter, prueba por destino con fallo parcial y pruebas de protocolo con solicitudes verificadas; recepción real en staging queda como verificación externa posterior.

### P0 — CU19: orden Stripe y venta presencial tienen ciclo incompatible

`backend/app/core/modules/ventas_pagos/services/stripe_service.py:804-817` exige una venta ya persistida para crear una `OrdenPago` de contexto `VENTA`. `venta_presencial_service.py:245-290` ahora exige esa orden previa y capturada para liquidar, pero crea la venta recién en `:395-418`. Después, en `:431-440`, cambia `orden_stripe.venta_id` de su venta original a la venta nueva si la primera no está pagada. Esto rompe la vinculación inmutable recurso-cargo que afirma el checkpoint 27 y permite usar el pago de una venta no pagada para liquidar otra de igual monto. `frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts:341-362` y `:808-825` sólo piden escribir un `pi_...`; no crean la venta previa ni la orden interna.

**Salida exigida:** definir y ejecutar un ciclo único: crear venta borrador sin descontar stock, generar orden para ese mismo `venta_id`, cobrar, confirmar y liquidar **esa misma** venta de forma idempotente; o usar un recurso de preliquidación vinculado inmutablemente. Nunca reasignar `orden_stripe.venta_id` a una venta diferente. Probar inicio a fin desde caja y que un pago de otra venta, aun con mismo cliente/monto, sea rechazado sin tocar stock/Kardex.

## Orden mínimo de corrección

1. Corregir el contrato CU05 y la serialización PWA; añadir la prueba vertical de cola a API.
2. Montar Stripe Elements en checkout PWA y probar captura de tarjeta/SetupIntent.
3. Rediseñar el ciclo de recurso y orden de CU19, con prueba completa desde caja.
4. Completar protocolo y clientes push; verificar fallos parciales y preparación para prueba real.
5. Repetir suites y resolver el runner Flutter con evidencia reproducible antes de atribuir 224 pruebas verificadas. Después, reauditar por CU/canal y registrar commits por grupos revisados.

**Alcance del dictamen:** CU05, CU22 y CU19 siguen observados; no se declara aceptada E2. Los otros CU de E2 conservan su evidencia anterior sin nueva aceptación transversal. No se aplicaron migraciones a `fashionstore_db` ni se tocaron credenciales.
