# Revisión móvil y pruebas pendientes

- **Fecha:** 7 de noviembre de 2026
- **Dispositivo:** Xiaomi 21061110AG, Android 13 (API 33)
- **APK:** `app-movil/build/app/outputs/flutter-apk/app-debug.apk`
**API y datos:** FastAPI local por USB/`adb reverse`; bases locales separadas `fashionstore_manual_test` (prueba en teléfono) y `fashionstore_test` (pytest). No se usó ni modificó la base oficial.

Este informe reemplaza los resultados intermedios anteriores de esta auditoría. Separa los flujos ejecutados en el teléfono, las pruebas automatizadas y lo que aún requiere una prueba manual o una corrección adicional.

## Correcciones incorporadas

- **Caja Flutter CU06/CU07:** el selector consulta variantes activas y existencias de la sucursal; excluye artículos sin disponibilidad, muestra el stock libre, inicia la cantidad en una unidad y limita las unidades que se pueden añadir. Al cerrar o conciliar un turno, vuelve a consultar existencias para evitar dejar cantidades antiguas en pantalla.
- **Caja Flutter:** se corrigió el ancho del selector de artículo que desbordaba el formulario en el teléfono.
- **Checkout Flutter CU21:** la respuesta durable basada en `pedido_id` continúa al pago del pedido mediante PaymentSheet y confirmación del backend, en lugar de interpretar la respuesta como una venta CU14.
- **Posventa Flutter:** servicio, modelos e historial usan las rutas y respuestas actuales de saldos, devoluciones, cambios y reembolsos. La pantalla de historial permite solicitar devolución.
- **Backend de traslados CU09:** al reintentar una línea rechazada, el nuevo traslado toma explícitamente `empresa_id` de su reserva. El disparador multitenant ya no rechaza esa operación válida.
- **Fixtures de vencimiento:** el helper de pruebas mueve conjuntamente el origen temporal y el vencimiento, conservando la restricción `vence_en >= origen_plazo_en` y la ventana original de 24/72 horas.
- **OpenAPI segundo parcial:** se regeneró `contratos/segundo-parcial/openapi-segundo-parcial.json` desde `backend.app.main.app.openapi()` después de que la prueba detectara que el contrato exportado estaba desactualizado.

## Prueba manual en el teléfono

| Flujo | Resultado | Evidencia y alcance |
|---|---|---|
| API local y conexión USB | **Verificado** | `/health` operativo. Se restauró `adb reverse tcp:8000 tcp:8000` cuando fue necesario. |
| Inicio de sesión y catálogo | **Verificado** | Inicio como cliente y como cajero; catálogo FashionStore, variantes y disponibilidad cargaron desde la API local. |
| Catálogo offline | **Verificado** | Se descargó la copia y continuó visible tras desactivar Wi-Fi en la prueba previa de esta sesión. |
| Notificación FCM | **Verificado** | Se registró el token del dispositivo, Firebase aceptó el envío de prueba y Android mostró la notificación. No se revalidó una notificación posterior a una compra Stripe. |
| Reserva online | **Verificado** | Crear, consultar detalle y cancelar; la cancelación liberó el stock. |
| Carrito | **Verificado** | Precio durable correcto: una unidad Bs 130; dos unidades Bs 260. |
| Caja: apertura con stock real | **Verificado** | La lista móvil mostró para `DEMO-CAMISETA-L-AZUL` una unidad disponible, asignó ese cupo y abrió el turno por ocho horas. |
| Caja: venta en efectivo sin enlace con la API | **Verificado** | Se quitó temporalmente `adb reverse` para simular pérdida de conexión con la API local. Se registró una unidad por Bs 145, recibido Bs 150, cambio Bs 5 y comprobante local `COMP-LOC-7F2A50FC`. La venta quedó pendiente en el teléfono y el cupo libre pasó a cero. Esto prueba pérdida del enlace a la API local, no una certificación de todos los modos de radio del teléfono. |
| Caja: sincronización | **Verificado** | Al restaurar `adb reverse`, la sincronización quitó la venta de pendientes. La base `fashionstore_manual_test` muestra venta `PAGADA` y `recibida_central_en` asignado; el turno cerró con arqueo Bs 145. |
| Caja: conciliación supervisada | **Verificado** | Un segundo cierre sin arqueo entró en `CONCILIACION`; se resolvió en la app con conteo físico y referencia de acta. El historial registra cierre en conciliación y posterior conciliación supervisada; terminó `CERRADO`. La unidad no vendida quedó disponible: SKU M con 8 unidades y cupo comprometido en cero. El SKU L vendido quedó con cero unidades libres. No hay turno de prueba abierto. |
| Refresco visual de stock tras cierre | **Pendiente de confirmación física** | Antes del último ajuste, la pantalla conservaba 7 aunque la base ya mostraba 8. Se implementó la recarga y el widget test comprueba que no siga ofreciendo la prenda agotada al cerrar. La APK final se compiló e instaló, pero Android quedó bloqueado antes de observar en pantalla la recarga final. |
| Checkout/Stripe en el teléfono | **No probado de extremo a extremo** | El código y la pantalla de pago de pedido tienen pruebas automatizadas, pero no se completó un cobro Stripe con el teléfono. Requiere conectividad externa y una compra de prueba. |
| Compra diferida sin conexión y confirmación posterior | **No probado físicamente** | Falta recorrer en el teléfono el estado pendiente, recuperación de red, reintento automático, confirmación del backend y notificación push de compra exitosa. |
| Solicitud de devolución/cambio desde cliente | **No probada de extremo a extremo** | Las rutas/modelos móviles y la lógica backend se alinearon; falta una compra pagada/entregada de prueba para recorrer el ciclo completo y observar el saldo/reembolso. |
| Reserva offline y sincronización | **No probada en teléfono** | Hay pruebas automatizadas del detalle/cola offline, pero no se completó el recorrido físico de crear offline y sincronizar después. |
| Probador CU17 | **Flujo principal verificado por el usuario** | El usuario confirmó que el stream de video realtime funciona y Decart muestra la prenda sobre él. Un intento anterior registrado por ADB falló durante la señalización; queda como incidencia transitoria, no como estado final. |

Las operaciones de Caja se ejecutaron únicamente en `fashionstore_manual_test`. No se tocaron inventarios, ventas ni turnos de la base oficial.

## Verificación automatizada

| Verificación | Resultado |
|---|---|
| `flutter analyze --no-pub` | Sin problemas. |
| `flutter test --no-pub --reporter compact` | **243 aprobadas, 0 fallidas, 0 omitidas.** |
| Widgets de Caja tras recarga de stock | **7 aprobadas** (`caja_flujo_productivo_completo_test.dart`, `caja_offline_screen_test.dart`). |
| Compilación APK debug | Correcta e instalada en el dispositivo. |
| `python -m compileall -q app tests` | Correcto después de las correcciones CU09 y del helper de pruebas. |
| Pruebas backend focalizadas anteriores (CU03/04/06/07/12) | **23 aprobadas**, 3 advertencias, en `fashionstore_test`. |
| CU09 reintento de traslado + CU10 preparación + CU11 venta de reserva | **3 aprobadas** tras corregir CU09 y el helper de vencimiento. |
| Suite principal `python -m pytest tests/ -q` | **128 aprobadas, 48 fallidas** en 587.99 s, antes de las dos últimas correcciones. Tres fallos de esa corrida se volvieron a ejecutar y aprobaron por separado; no se repitió la suite completa después, así que no se presenta un nuevo total global. |

Los fallos backend restantes requieren clasificación y corrección; se concentran en pruebas `test_ciclo3_correcciones_*`, CU02, CU14–CU17, CU18/CU20, CU19/CU21/CU25, CU22 y CU24. Entre los síntomas observados hay pruebas que todavía esperan `venta_id`/`pedido_entrega_id` mientras el checkout durable actual devuelve `pedido_id`, escenarios de concurrencia/idempotencia, promociones, roles y expiración. No se concluye que todas sean solo pruebas desactualizadas: hace falta resolverlas contra el contrato vigente.

La suite aislada `tests_segundo_parcial_bloque_b/` se ejecutó en `fashionstore_test`: **289 aprobadas y 1 fallida** porque el OpenAPI exportado estaba desincronizado. Se regeneró el JSON desde FastAPI y las tres pruebas del archivo OpenAPI pasaron al repetirlas. No se repitieron los 290 casos del bloque completo después de regenerarlo. La primera invocación general de `pytest` sí abortó durante colección porque faltaba `FASHIONSTORE_TEST_DATABASE_URL`; esa invocación no llegó a ejecutar pruebas.

## Pendientes para dar por verificada la app móvil

1. Desbloquear el teléfono y confirmar en la APK instalada que la disponibilidad de Caja se refresca en pantalla tras cierre normal y conciliación supervisada.
2. Ejecutar compra Stripe de prueba completa y comprobar estado de pedido y push de éxito.
3. Ejecutar compra diferida sin conexión, recuperación de conectividad y sincronización automática hasta recibir push.
4. Crear una compra pagada y entregada, pedir una devolución desde Flutter y revisar inspección, saldo y reembolso.
5. Ejecutar reserva offline y sincronizarla físicamente.
6. Para CU17, conservar evidencia del reintento exitoso y verificar cambio de prenda y liberación de cámara al terminar la sesión.
7. Clasificar y corregir el conjunto de fallos de backend; hasta entonces la verificación global del proyecto no está cerrada.

## Actualización backend del 8 de noviembre de 2026

- Se unificó la ruta `/carritos/mio/checkout`: el cuerpo con `canal` conserva la respuesta legada `venta_id`; el cuerpo sin `canal` usa el pedido durable CU21 y responde con `pedido_id`. Se regeneró el OpenAPI vigente.
- Se corrigieron el tenant de la venta/entrega legada, la correspondencia ORM de entregas con la base migrada y la idempotencia de mutaciones del carrito durable.
- La suite aislada del segundo parcial terminó con **290 aprobadas** y 3 advertencias en `fashionstore_test`.
- La suite principal terminó con **165 aprobadas y 11 fallidas** antes de la corrección del test de concurrencia Stripe. Ese test reutilizaba un ID de evento para seis pagos, se corrigió y pasó de forma aislada. La suite global no se repitió después de esa corrección; permanecen 10 fallos observados en la corrida global, principalmente CU17/Decart, identidad, IA y un caso de entregas sensible al orden.
- La solicitud de checkout actual de Flutter aún incluye `canal` en el cuerpo, por lo que entra en la rama legada. Para usar la compra durable desde móvil deberá actualizarse el cliente Flutter y probarse el pago de extremo a extremo en el teléfono. Este commit modifica únicamente el repositorio backend.

## Prueba CU17 / Decart - 8 de noviembre de 2026

### Alcance y configuracion

- FashionStore usa una **cuenta y API key global de Decart para todos los tenants**. La clave vive solo en el backend; no se configura por empresa ni se incluye en Flutter. Catalogo e imagen de referencia se resuelven dentro del `empresa_id` del usuario.
- Se documento el flujo, privacidad, alcance multitenant y criterios de prueba completa en `seguimiento/segundo-parcial/52-arquitectura-probador-decart.md` dentro del repositorio backend; la ruta exigida por AGENTS tambien esta en `docu_general/ciclo-3/07-arquitectura-probador-decart.md`.
- Para preparar el ensayo se anadio un cliente de prueba y una prenda superior con imagen HTTPS en la base local `fashionstore_manual_test`. No se modifico la base oficial.

### Resultado observado

- **Catalogo y acceso:** comprobados en la APK conectada al backend local; tras reiniciar FashionStore, el telefono cargo la imagen de camisa de Cloudinary en el detalle y en la pantalla de consentimiento CU17. La imagen paso el validador real (HTTPS, host permitido, WebP valido y resolucion minima). El host `res.cloudinary.com` ya estaba permitido; no se cambio el allowlist.
- **Aislamiento multitenant:** el recurso de probador de una variante de otra empresa respondio 404 para el cliente FashionStore.
- **Backend automatizado:** `backend/tests/test_cu17_decart.py` paso con **6 pruebas aprobadas**.
- **Compatibilidad multitenant del recurso:** `GET /api/v1/variantes/{id}/prueba-virtual` respondio **200** y `compatible=true` para el cliente y la prenda del tenant FashionStore; la URL resuelta uso `res.cloudinary.com`. El filtro de empresa no bloqueo el flujo.
- **Token Decart real:** no emitido. `POST /api/v1/probador/autorizaciones` respondio **502 `DECART_RECHAZO`** y Flutter mostro `ERROR_GENERICO`; el intento directo anterior al proveedor habia devuelto **HTTP 401**. La API key configurada no es aceptada por Decart y debe reemplazarse/rotarse antes de repetir.
- **Video y frames:** **no verificados**. No se obtuvo conexion realtime, video publicado ni frame remoto transformado; CU17 no se declara funcional de extremo a extremo. Tras volver a la pantalla de consentimiento, `dumpsys media.camera` no mostro un cliente activo de `com.example.fashionstore_movil`.

### Para repetir y cerrar CU17

1. Regenerar o corregir la API key en Decart y reemplazar `DECART_API_KEY` localmente (o el secreto de Render para produccion). La credencial usada en esta auditoria debe rotarse por seguridad. No enviar la clave por chat ni guardarla en Git.
2. Reiniciar FastAPI y comprobar que `POST /api/v1/probador/autorizaciones` devuelve 201 con token temporal sin exponerlo en logs.
3. Con el Xiaomi conectado, iniciar CU17, aceptar consentimiento, comprobar preview local, conexion del SDK, video remoto y al menos un frame transformado visible.
4. Cambiar de prenda y salir; confirmar que se detienen stream/camara y que no quedan datos audiovisuales persistidos.

**Conclusion:** arquitectura, validacion de tenant y pruebas unitarias listas; falta una credencial Decart aceptada y la prueba fisica realtime para concluir CU17.

## Reintento tras actualizar credenciales Decart - 8 de noviembre de 2026

> Este resultado posterior reemplaza el estado de rechazo de credenciales descrito en los dos apartados anteriores.

- La base URL local quedó en el origen raíz `https://api.decart.ai`, porque el cliente oficial compone la ruta de emisión de tokens. La captura del usuario corresponde a `/v1/jobs/lucy-2.5` (trabajo de video no realtime), no a la ruta de señalización de CU17.
- Con la clave actualizada, FashionStore inició sesión contra FastAPI local (**200**), consultó el recurso compatible (**200**) y creó una autorización Decart (**201**). El token temporal no se mostró ni guardó en el informe; la app indicó una vigencia aproximada de 59 segundos.
- El catálogo de la primera apertura seguía mostrando una copia SQLite anterior. Al reiniciar la app y volver a cargar desde la API, la imagen Cloudinary apareció en el catálogo, detalle y consentimiento; el botón de CU17 se habilitó.
- El consentimiento se aceptó y Android abrió la cámara local. Al iniciar la señalización realtime, Logcat reportó: `Fields [server_ip, server_port] are required for type ... SessionIdMessage, but they were missing`. Flutter mostró `WEBRTC_SIGNALING_ERROR` (código de interfaz `ERROR_RED`) y el WebSocket cerró con `wasConnected=false`. No se completó la señalización; la evidencia no demuestra rechazo de la API key ni permite atribuir con certeza la causa al SDK o al servicio.
- **Video y frames remotos:** no recibidos. Solo se comprobó la cámara/vista local; no se mostró prenda transformada ni se confirmó un frame remoto.
- Al salir del probador, `dumpsys media.camera` confirmó `Active Camera Clients: []`; el SDK cerró el WebSocket con `wasConnected=false`.
- Durante el intento, el registro accesorio de navegación falló con `NameError` por import faltante y ausencia de `empresa_id`. Se corrigió el import de `HistorialNavegacion`, se asigna el tenant del usuario y `tests/test_ia_navegacion.py` pasó (**1 aprobada**).
- La documentación actual de Decart sigue publicando Android SDK `0.7.10`, autenticación con token efímero y `baseUrl` WebSocket `wss://api.decart.ai`; la integración local usa esos valores. La documentación describe el stream realtime por WebSocket/LiveKit separado del procesamiento por cola.

### Confirmación posterior del usuario

- Después del intento fallido capturado arriba, el usuario informó que el stream de video realtime sí funcionó y que Decart le colocó la prenda.
- Esta confirmación posterior establece el resultado funcional del flujo principal. El error `SessionIdMessage` se conserva como diagnóstico de un intento previo; no representa el estado final confirmado.
- La sesión exitosa no quedó capturada por ADB/Logcat en nuestra prueba. Para completar evidencia reproducible, queda documentar un cambio de prenda y confirmar el cierre/liberación de cámara al salir de esa sesión.

**Estado vigente:** CU17 funciona en su flujo principal según la prueba manual confirmada por el usuario: video en vivo y prenda aplicada. Solo queda completar evidencia de cambio de prenda y cierre limpio; la clave y el endpoint de tokens ya no son bloqueos.

## Revision de la URL de referencia Decart - 8 de noviembre de 2026

- La captura compartida muestra `POST https://api.decart.ai/v1/jobs/lucy-2.5`, con un cuerpo multipart `data`. Es el endpoint de trabajos de video; no debe configurarse como `DECART_API_BASE_URL` para el probador realtime.
- CU17 usa el flujo realtime: el backend crea un token temporal y Flutter conecta con el SDK Android. Referencias oficiales: [Client Tokens](https://docs.platform.decart.ai/getting-started/client-tokens) y [SDK Direct](https://docs.platform.decart.ai/integrations/sdk-direct).
- En la revisión inicial, la ruta incluida en `.env` causaba un 404 al duplicar el endpoint. Se corrigió al origen raíz. El resultado de autenticación anterior quedó superado: con la clave actualizada se obtuvo 201 para el token; el fallo pendiente actual es el mensaje de señalización descrito en “Reintento tras actualizar credenciales Decart”. No usar `/v1/jobs/lucy-2.5` como base URL realtime.
