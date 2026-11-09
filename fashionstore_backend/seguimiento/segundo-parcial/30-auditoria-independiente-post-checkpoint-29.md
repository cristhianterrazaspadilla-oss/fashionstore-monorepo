# Auditoría independiente posterior al checkpoint 29

**Corte:** 05/11/2026. **Ramas:** `feature/sp2-e2-integral` en backend, frontend-web y app-movil. **Dictamen:** la Entrega 2 permanece **en avance sin aceptar**. El agente resolvió parte de los defectos de la auditoría 28, pero subsisten rutas que simulan una autorización o captura y un cliente FCM sin SDK instalado. Este dictamen prevalece sobre las afirmaciones de cierre del checkpoint 29.

## Pruebas repetidas por Codex

| Componente | Resultado independiente |
|---|---|
| Backend, PostgreSQL `fashionstore_test` | `pytest tests_segundo_parcial_bloque_b -q --disable-warnings`: **239 passed, 6 warnings**, 126.24 s. |
| Angular | Karma **270/270**. `npx.cmd tsc -p tsconfig.app.json --noEmit`: exit 0. `npm.cmd run build`: exit 0; avisos CSS de Dashboard e Inteligencia. |
| Flutter | `flutter analyze --no-pub`: **0 issues**. `flutter test --no-pub --reporter expanded`, y después el archivo focalizado `test/unit/notificacion_movil_service_test.dart`, no produjeron salida tras una espera prolongada; ambos se interrumpieron. La cifra **234/234** es un reporte del agente, sin corroboración independiente en esta revisión. |
| Git | `git diff --check` exit 0 en los tres repositorios; avisos LF/CRLF. No se hicieron commits, push, merge ni despliegues en esta auditoría. |

El script nuevo `app-movil/run_tests.ps1` declara un timeout de 180 s en su documentación, pero el script no implementa un límite de tiempo. Además borra `*.db*` y `*.sqlite*` en la raíz de `app-movil` antes de probar. Por ese efecto sobre archivos locales no se ejecutó en la auditoría; la suite se intentó directamente con Flutter. El diagnóstico atribuido a `--no-pub` no explica estos intentos, que sí usaron esa opción.

## Avances comprobados

- La PWA ya muestra un contenedor de Stripe Elements y llama a `elements.create('card')`/`mount`; el DTO backend exige `moneda_cobro` y prohíbe campos adicionales.
- La cola PWA fija `version_esquema=3` para nuevas compras y elimina claves adicionales del objeto serializado.
- CU19 crea una `Venta(PENDIENTE_PAGO)` y una `OrdenPago` ligada a esa venta; se quitó la reasignación directa de `orden_stripe.venta_id`.
- Backend añadió autenticación OAuth2 para FCM, firma/cifrado Web Push y estado `FALLIDO_PARCIAL` por destino; la PWA registra un service worker. Estos avances no acreditan recepción real de push.

## Bloqueos restantes

### P0 — CU19: la interfaz declara captura aunque el proveedor la rechace

En `frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts:375-400` y `:912-937`, `capturarStripeCaja`/`capturarStripePresencial` asignan `estado_orden='CAPTURADO'` tanto en `next` como en `error`, e incluso cuando `StripeService` no se inyecta. No se invoca Stripe.js para confirmar el PaymentIntent con tarjeta. La ruta llamada es `POST /stripe/ordenes/{id}/continuar-accion`, pero `backend/app/core/modules/ventas_pagos/services/stripe_service.py:1078-1082` sólo acepta órdenes en `REQUIERE_ACCION_CLIENTE`; `iniciar_stripe` crea la orden en `PENDIENTE` (`venta_presencial_service.py:303-321`). La secuencia normal es, por tanto, 409 en el backend, `CAPTURADO` falso en UI y rechazo al liquidar. Los tests de CU19 marcan `ord_db.estado='CAPTURADO'` directamente (`test_cu19_caja_liquidacion.py:492`), omitiendo este trayecto.

**Salida necesaria:** la caja debe confirmar el `client_secret` mediante Stripe.js/Elements o flujo oficial adecuado, esperar estado verificado del servidor/webhook y mostrar `CAPTURADO` sólo con esa confirmación. Probar fallo, 3DS, inicio pendiente, repetición, captura real y liquidación de la misma venta. Eliminar la opción de liquidar con un PI suelto sin la orden iniciada.

### P0 — CU05: el sanitizador fabrica autorización y tasa

`frontend-web/src/app/core/services/sincronizacion-offline.service.ts:29-58` genera `consentimiento_id` con `crypto.randomUUID()` si falta, rellena fecha, importes y vigencia, fija `permite_cobro_al_reconectar=true` y usa `tasa_bob_por_usd='6.96'` como fallback. `registrarCompraOffline` usa siempre ese resultado (`:294-318`), y el envío vuelve a sanitizar la cola (`:423-434`). Un objeto parcial con `preparacion_pago_id` se transforma en una autorización de 15 claves en vez de omitir `autorizacion_cobro` o rechazarlo. Las pruebas comprueban el número de claves, pero no preservan la procedencia de consentimiento/tasa ni el caso de entrada parcial.

**Salida necesaria:** construir la autorización completa exclusivamente a partir de consentimiento, método `LISTO`, oferta y tasa oficiales previamente verificados. Si falta cualquier campo contractual, omitir el objeto y registrar `PENDIENTE_INTERVENCION` conforme al contrato, sin inventar consentimiento, tasa, importe ni vencimiento. Rechazar o poner en intervención operaciones antiguas parciales al reenvío. Probar desde IndexedDB hasta FastAPI con entrada parcial y demostrar que no se crea cobro.

### P0 — Avisos móviles: FCM no está integrado en Flutter

`app-movil/pubspec.yaml` y `pubspec.lock` carecen de `firebase_core` y `firebase_messaging`. `notificacion_movil_service.dart:34-124` llama directamente a `MethodChannel('plugins.flutter.io/firebase_messaging')` y captura `MissingPluginException`; no hay inicialización de Firebase ni registro de plugin en la aplicación. La entrada añadida en `AndroidManifest.xml` apunta a `com.google.firebase.messaging.FirebaseMessagingService` sin incorporar el SDK/plugin. El `SimulatedFcmAdapter` hace pasar las pruebas unitarias, pero un Android normal no obtendrá token FCM por esta implementación. La guía externa `google-services.json` no sustituye las dependencias ni la integración en código.

**Salida necesaria:** integrar FlutterFire/Firebase Messaging compatible con el SDK instalado, inicializar Firebase, solicitar permiso cuando corresponda, obtener/renovar token, registrar/revocar dispositivo y procesar foreground/background/apertura desde los callbacks oficiales. Probar compilación Android y dejar recepción en equipo físico como verificación externa explícita si no hay hardware/configuración. Referencia: documentación oficial Firebase Flutter.

### P1 — CU22: Stripe Elements permite confirmar antes de validar tarjeta

`frontend-web/src/app/features/ventas_pagos/checkout/checkout.component.ts:611-654` instala un elemento ficticio si no carga Stripe.js, silencia errores de `mount`, y fija `cardElementMontado=true` y `cardElementValido=true` sin esperar el evento `change`. El botón de `checkout.component.html` queda habilitado inmediatamente. Aunque Stripe.js real puede devolver un error, la UI afirma que la tarjeta está lista y la ruta de error queda disfrazada por el fallback. Debe fallar cerrado ante falta de SDK o montaje y habilitar el botón únicamente tras `change.complete && !change.error` del elemento auténtico.

### P1 — CU19: reintento de inicio devuelve datos ficticios

`backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py:139-159` devuelve `client_secret=f"{referencia_externa}_secret_test"` y tasa `6.96` de reserva al recuperar una orden idempotente. La rama de colisión (`:329-344`) también reconstruye el secreto ficticio. El primer inicio devuelve `intencion.client_secret` real (`:350-358`). Un reintento tras timeout no puede confirmar la intención con un secreto fabricado, y puede presentar una tasa diferente de la congelada. Debe recuperarse la intención real del gateway o guardar/recuperar su secreto efímero de forma segura según el diseño, y devolver la tasa congelada sin fallback.

### P1 — CU19 en un turno offline: cupo y stock libre se tratan como la misma venta

La rama de caja con turno llama a `iniciarVentaPresencialStripe` usando `lineasVentaOffline` y `turno_caja_id` (`frontend-web/src/app/features/ventas_pagos/caja/caja.component.ts:337-361`). CU06 deduce esos cupos de `InventarioSucursal.disponible` y los pasa a `comprometido_caja` (`backend/app/core/modules/ventas_pagos/services/caja_service.py:184-191`). Sin embargo, `iniciar_stripe` exige otra vez stock **libre** (`venta_presencial_service.py:191-201`) y la liquidación lo descuenta de nuevo; la UI suma consumo al cupo local (`caja.component.ts:459-464`) sin consumir `CupoCaja` central en ese servicio. Con exactamente las unidades asignadas al turno, Stripe puede rechazar por stock insuficiente; si hay stock libre adicional, puede descontarlo y dejar el cupo comprometido. Probar y resolver la relación entre venta conectada y cupo del turno sin duplicar disponibilidad ni alterar la semántica de CU07.

### P1 — Push PWA: doble registro y fallo silenciado

`frontend-web/src/app/features/identidad_empresas/services/web-push.service.ts:176-192` registra la misma suscripción primero en `/web-push/subscripcion` sin `dispositivo_id` y descarta silenciosamente su resultado; el router genera entonces un UUID nuevo (`backend/app/core/modules/identidad_empresas/routers/notificaciones.py:59-77`). Luego registra otro dispositivo con ID local por `/dispositivos`. `NotificacionService.registrar_dispositivo` hace upsert por `dispositivo_id` (`notificacion_service.py:603-608`), de modo que quedan dos destinos activos para una suscripción y pueden duplicarse avisos. Usar un único registro estable y esperar su resultado; revocar el mismo ID.

### P1 — Documentación de entrega incoherente con el contrato

`29-checkpoint-post-auditoria-28.md` rotula «Contrato: versión 0.4.0», pero `contratos/segundo-parcial/version.json` sigue en **contrato 0.3.2 / protocolo 0.4.0**. Su matriz de CU06–CU27 usa nombres y reparto distintos de `02-estado-cu.md` y las fichas vigentes. No se deben derivar aceptación ni alcance desde esa matriz. Corregir con la numeración contractual real y etiquetar las afirmaciones de pruebas como reporte del agente hasta la auditoría independiente.

## Orden de cierre

1. Eliminar los falsos positivos financieros: autorización fabricada en CU05 y `CAPTURADO` visual falso en CU19. Añadir contraejemplos que fallen con el código actual.
2. Completar Stripe.js de caja y la verificación de pago en backend, con reintento idempotente que devuelva datos reales. Probar inicio → pago → webhook/consulta → liquidación → venta/pago/Kardex.
3. Completar plugin FCM Flutter y corregir Stripe Elements del checkout para fallar cerrado. Evitar registros Web Push duplicados. Conciliar la venta Stripe dentro de un turno con sus cupos centrales.
4. Repetir suites y una compilación Android cuando el entorno lo permita. Corregir el diagnóstico/script Flutter y el checkpoint contractual. Mantener E2 sin aceptar hasta nueva auditoría por CU y canal.

**Límites:** no se ejecutaron pruebas Stripe Test con proveedor real, recepción FCM/Web Push en dispositivo físico ni Android build. No se modificó la base principal `fashionstore_db` ni se tocaron credenciales.
