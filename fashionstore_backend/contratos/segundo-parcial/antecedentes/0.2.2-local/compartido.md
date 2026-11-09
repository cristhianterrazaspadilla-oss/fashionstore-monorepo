# Contrato compartido de API y sincronización

**Estado:** diseño de sincronización para reservas, compras y caja, con detalle prioritario de los ocho casos de la primera presentación. No equivale al OpenAPI real. Ver [casos-de-uso.md](casos-de-uso.md), [primera-presentacion.md](primera-presentacion.md) y [reglas-aprobadas.md](reglas-aprobadas.md).

## Identidad y versión

- Todas las operaciones privadas requieren sesión/identidad válida. El backend deriva `empresa_id` del usuario autenticado y comprueba la pertenencia de cada recurso, sucursal y cliente. Los identificadores de empresa incluidos en comandos son referencias de comprobación, nunca autorización suficiente.
- El enlace público de navegación propuesto `/tienda/{empresa_codigo}` identifica únicamente el catálogo de una empresa. Su código se conserva al pasar a registro/login, pero no sustituye la pertenencia validada ni permite reutilizar silenciosamente la sesión de otra empresa. La pantalla inicial para escoger empresas queda como mejora opcional posterior, no forma parte de los ocho casos.
- Los datos privados del cliente se muestran offline durante 8 h desde el último login online. Al vencer o hacer logout se ocultan, manteniendo aislados por empresa/usuario los datos, pendientes y resultados hasta reautenticar; el catálogo público descargado puede seguir visible. Recuperar red o reintentar no reinicia esa ventana. Es independiente del JWT actual de 24 h y de la habilitación de caja offline de 8 h. Un token vencido nunca queda habilitado por la ventana local; sincronizar exige identidad online válida y autorización backend.
- `version_esquema` identifica la forma del comando. Cambios incompatibles producen versión nueva y migración local; no reinterpretar silenciosamente pendientes antiguos.
- Cada comando tiene `operacion_id` UUID estable, `tipo`, `creada_local_en`, `empresa_id`, `usuario_id`, `dispositivo_id`, `secuencia_local` y `datos` tipados. Caja añade `turno_id`, `habilitacion_id`, versión de precios y cupos consumidos. El servidor conserva hash canónico del comando y respuesta.
- Repetir mismo `operacion_id` y contenido devuelve el mismo resultado tras reautorizar actor y empresa. Mismo ID con contenido diferente devuelve conflicto `OPERACION_MODIFICADA`. Los reintentos no cambian la fecha original ni prolongan vencimientos.
- El resultado contiene `operacion_id`, `estado`, `codigo`, `recibida_en`, `aceptada_en` si aplica, `recurso_id` si aplica, `revision` y detalle legible. La pérdida de respuesta se resuelve consultando por ID, no enviando una nueva operación con otro ID.

## Familias de operaciones

| Tipo lógico | Origen y datos mínimos | Efecto central |
|---|---|---|
| `SOLICITAR_RESERVA` | Cliente PWA/Flutter: sucursal, visita, variantes/cantidades y fecha local | Revalidar tiempo, identidad y stock; aceptar y reservar o rechazar/conflicto. |
| `SOLICITAR_COMPRA` | Cliente PWA/Flutter: sucursal elegida, líneas y precios vistos | Revalidar total y stock; pedir aceptación de precio si cambió, o apartar 60 min y ofrecer pago online. |
| `REGISTRAR_VENTA_CAJA` | Caja PWA/Flutter: turno, habilitación, líneas, precio autorizado, total BOB, efectivo/entrega y cupo consumido | Registrar venta/pago/Kardex contra cupo asignado; auditar incidencias. |

Esta versión transporta **un comando por solicitud** y cada comando tiene transacción y resultado independiente. Las colas cliente envían operaciones en orden; un rechazo no revierte otras operaciones ya aceptadas. No mezclar ventas físicas cobradas con solicitudes digitales pendientes de pago. Los comandos cliente se envían solo después de reautenticación online; la caja envía ventas realizadas bajo habilitación original y el backend audita revocaciones posteriores.

La reserva online vence a las 24 h desde creación central; la offline aceptada, a las 24 h desde creación local original. Un adelanto confirmado online antes del vencimiento fija 72 h desde ese mismo origen, sin sumar 72 h. Fecha de visita, recepción, reintentos y notificaciones no cambian el origen. Una solicitud offline que llega vencida es `RECHAZADA`/`SOLICITUD_VENCIDA` sin apartado; si el tiempo no es verificable, `CONFLICTO`/`TIEMPO_INCOHERENTE` durable. Creación, adelantos, cancelación y expiración deben usar la misma regla y exponer fechas coherentes en los clientes.

## Estados visibles

| Flujo | Estados locales/centrales principales |
|---|---|
| Reserva | `GUARDADA_LOCAL`, `PENDIENTE_ENVIO`, `EN_REVISION`, `ACEPTADA`, `RECHAZADA`, `CONFLICTO`. Solo `ACEPTADA` aparta stock. |
| Compra digital | `GUARDADA_LOCAL`, `PENDIENTE_ENVIO`, `REQUIERE_ACEPTACION_PRECIO`, `SIN_STOCK`, `PENDIENTE_PAGO`, `PAGO_EN_VERIFICACION`, `PAGADA`, `PAGO_FALLIDO`, `VENCIDA`. Solo webhook/reconciliación confiable confirma `PAGADA`. |
| Venta de caja | `BORRADOR_LOCAL`, `COBRADA_ENTREGADA_LOCAL`, `PENDIENTE_ENVIO`, `REGISTRADA_CENTRAL`, `CONCILIACION_REQUERIDA`. La etiqueta local no se presenta como confirmación central. |

Los nombres se precisarán en enums del backend y se exportarán una sola vez a clientes. Las transiciones permitidas deberán probarse; un aviso tardío no retrocede ni renueva un estado.

## Causas de resultado y recuperación

| Código | Significado y acción de interfaz |
|---|---|
| `SIN_STOCK` | Mostrar variantes faltantes; no cobrar ni crear reserva/venta digital parcial. |
| `PRECIO_CAMBIADO` | Mostrar total actualizado y pedir aceptación online antes de apartar. |
| `SOLICITUD_VENCIDA` | Reserva fuera de 24/72 h: iniciar solicitud nueva si el cliente desea continuar. |
| `TIEMPO_INCOHERENTE` | Conservar operación en conflicto; no apartar automáticamente; mostrar revisión/renovación según contrato. |
| `PLAN_NO_HABILITADO` | No aceptar nuevas operaciones; las ventas de caja ya realizadas válidamente se concilian y auditan. |
| `CUPO_INSUFICIENTE` | Impedir nueva venta de caja local; una venta ya cobrada se trata mediante incidencia auditada. |
| `TASA_NO_VIGENTE` | Impedir nueva intención Stripe, conservando pedido/stock según vencimiento original. |
| `OPERACION_MODIFICADA` | No reaplicar; mantener original y registrar incidencia de sincronización. |
| `PAGO_EN_VERIFICACION` | Consultar estado remoto; no afirmar éxito ni fracaso y no liberar stock prematuramente. |

Los estados HTTP exactos y esquemas de error se fijarán en OpenAPI del backend, conservando estos códigos de negocio estables. Ningún cliente interpreta una falla de red como rechazo comercial.

## Importes, fechas y notificaciones

- BOB comercial y saldo con dos decimales. Tasa positiva BOB por USD versionada y vigente; convertir con aritmética decimal y `ROUND_HALF_UP` a USD de dos decimales. Exponer BOB, tasa, fecha de vigencia y USD final para aceptación. Webhook compara contra intención congelada. Ningún cliente calcula el monto final como autoridad.
- En reportes, fecha predeterminada de aceptación central; fecha física local y recepción son campos separados. Solicitud de compra offline no es venta confirmada. Venta de caja cobrada localmente entra al reporte central al aceptarse, con su fecha física disponible.
- Cada resultado central relevante persiste en bandeja propia. Android FCM y PWA Web Push son canales de aviso, no fuente del estado ni mecanismo para enviar un borrador que nunca salió del dispositivo. Abrir aviso vuelve a consultar recurso tras autenticar.

## Operaciones REST a concretar sobre `/api/v1`

Estas son rutas **propuestas**, nuevas o extensiones, sujetas a reconciliación con las rutas existentes al implementar:

| Propósito | Ruta de diseño |
|---|---|
| Descargar catálogo versionado | `GET /catalogo/descarga` |
| Enviar un comando | `POST /sincronizacion/operaciones` |
| Obtener referencia de hora del servidor | `GET /sincronizacion/referencia-horaria` |
| Recuperar resultado | `GET /sincronizacion/operaciones/{operacion_id}` |
| Consultar bandeja propia | `GET /notificaciones/mias` |
| Aceptar precio y preparar pago | `POST /compras/{operacion_id}/aceptar-precio` |
| Consultar saldo propio | `GET /saldos/mio` |

No duplicar `/reservas`, `/carritos` o `/pagos` existentes sin evaluar sus contratos y compatibilidad. OpenAPI se exporta desde FastAPI después de implementar y se compara con esta especificación.

## Protocolo 0.2.0, aclaración documental 0.2.1 y alcance actual

Los ocho CU de la primera presentación se detallan en [primera-presentacion.md](primera-presentacion.md). Los códigos actuales son los de [equivalencias-cu.md](equivalencias-cu.md), no los de la versión anterior. Se añade CONFLICTO al enum de resultados: TIEMPO_INCOHERENTE se conserva como conflicto durable, sin stock apartado. Los clientes deben reconocerlo antes de integrar esta versión; no es un fallo de red ni un estado de reserva aceptada.

El envoltorio de operación mantiene version_esquema=1 y todos sus campos obligatorios. La renumeración es documental; no modificar UUID persistidos ni vaciar IndexedDB/SQLite. Los resultados y pendientes antiguos se preservan; coordinar actualización de validadores entre los tres repositorios. No se declara ya ejecutada una migración de clientes.

Un GET de resultado sin registro visible no autoriza generar otro UUID: el POST anterior podría estar en curso. Reintentar el mismo comando/UUID es seguro solo con unicidad, serialización y transacción idempotente del backend. Evitar sincronizadores concurrentes en cliente y proteger también servidor.

La venta física de contado requiere efectivo; el turno ya determina empresa/sucursal/responsable/dispositivo, que deben validarse al recibir. Para próximas presentaciones, formalizar además el campo de cliente opcional y su pertenencia, y los datos de comprobante/entrega; esta revisión no inventa nuevos campos obligatorios de caja ni la presenta como implementada.
