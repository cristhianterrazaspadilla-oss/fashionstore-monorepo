# Integración funcional — segundo parcial

Protocolo de diseño 0.2.0, aclaración documental 0.2.1 del 25/10/2026. Las rutas de esta tabla son propuestas salvo las marcadas «existente»; FastAPI deberá publicar el OpenAPI real antes de integrarlas. Todas usan `/api/v1`; las operaciones privadas requieren sesión validada y empresa autorizada en servidor. La consulta/descarga pública de catálogo identifica la empresa publicada sin conceder acceso a datos privados. Un `empresa_id` recibido se contrasta con la sesión y nunca concede acceso. Respuestas de error propuestas: `{ "codigo": "...", "detalle": "..." }`, sin datos de otro tenant. Importes BOB/USD son cadenas decimales de dos posiciones; tasa BOB por USD es decimal positivo versionado. Fechas ISO 8601 con zona.

## Identidad, empresa y plan

| Operación | Petición mínima | Respuesta/regla |
|---|---|---|
| `POST /sesion` (existente, a ampliar) | `correo_electronico`, `contrasenia` y `empresa_codigo` opcional en el diseño; el contexto del enlace empresarial debe validarse y el código se exige si la identidad pertenece a varias empresas | Sesión ligada a la empresa validada; nunca elegirla con encabezado mutable ni reutilizar sesión de otra empresa. Login sin código solo si la pertenencia es inequívoca y no contradice el contexto elegido. |
| `POST /empresas` | Nombre y datos de alta; superadministrador | Empresa y administrador inicial creados; plan pendiente hasta asignación administrativa, sin cobro SaaS. |
| `POST /empresas/{id}/suscripciones` | Plan, inicio y fin manuales; motivo; superadministrador | Historial de vigencias, 72 h de gracia. Básico 2 sucursales activas; Profesional 10. Reducción rechazada hasta quedar dentro del límite sin borrar datos. |
| `GET /empresas/mi-plan` | Sesión | Plan, capacidad, vencimiento y gracia para mostrar capacidad efectiva. |

El enlace `/tienda/{empresa_codigo}` es una **ruta de navegación propuesta en web**, no un endpoint API ni una ruta ya implementada. El código identifica el catálogo público de esa empresa (productos, variantes, precios y disponibilidad pública conocida); no concede acceso privado. El contexto elegido pasa a registro/login y luego se comprueba contra empresa y recursos de la identidad autenticada. Si hay una sesión de otra empresa, el cliente exige cambio y validación explícitos; ni el código de la URL ni el campo enviado autorizan por sí solos. Una pantalla inicial de selección de empresas es mejora opcional posterior.

`organizacion.ciudades` se mantiene como catálogo global de referencia: administración reservada a plataforma; la empresa consulta y selecciona ciudades para sus sucursales. Sus sucursales y tarifas siguen aisladas por empresa. La administración global es capacidad relacionada, sin CU prioritario adicional. Para la empresa heredada, conservar registros/IDs/historial; si el conteo real confirma tres sucursales activas, asignar Profesional administrativamente con fechas introducidas explícitamente. Ante otro conteo, registrar y revisar antes de aplicar; no inventar suscripción ni desactivar sucursales.

Tras la gracia se bloquean ventas, reservas y turnos nuevos. Continúan consultas, cambios/devoluciones en plazo y conclusión de pedidos aceptados. Una sucursal con compromisos pendientes no se desactiva. Reportes generativos y ambos modelos ML son solo Profesional vigente o en gracia.

## Sincronización de clientes

`interfaz.json` fija el envoltorio de `operacion`/`resultado`. `POST /sincronizacion/operaciones` recibe **una operación por solicitud**, con transacción y respuesta durable propias. No se requiere lote en esta versión; los clientes envían su cola en orden. `operacion_id` UUID permanece igual en cada reintento; igual actor/empresa/ID y mismo contenido canónico devuelve el resultado guardado, después de reautorizar. Mismo ID con contenido diferente produce 409 `OPERACION_MODIFICADA`. Antes de repetir tras un corte, consultar `GET /sincronizacion/operaciones/{operacion_id}`. Una falla de red significa estado desconocido, nunca rechazo comercial.

`GET /sincronizacion/referencia-horaria` entrega hora del servidor, referencia e instante de caducidad para controlar coherencia del reloj local. La reserva online vence 24 h desde creación central; la solicitud offline aceptada, 24 h desde creación local original. Un adelanto confirmado online antes del vencimiento extiende hasta 72 h desde el mismo origen, no añade 72 h. Fecha de visita, recepción, reintentos y notificaciones no reinician el plazo. Una solicitud offline vencida se rechaza sin apartar stock; una referencia temporal incoherente da `CONFLICTO`/`TIEMPO_INCOHERENTE` durable sin apartado. Se comprueba visita futura, identidad, plan, sucursal y stock al recibir. La compra diferida exige stock completo; falta de stock da `SIN_STOCK`, texto «Lo sentimos, el producto no se encuentra disponible» y ningún cobro. Si cambia el precio, `REQUIERE_ACEPTACION_PRECIO` devuelve revisión y total BOB vigente; `POST /compras/{operacion_id}/aceptar-precio` recibe revisión/total aceptados y vuelve a comprobar stock. El apartado aceptado dura 60 min desde aceptación central y habilita el pago online. Los clientes no pagan por el mero hecho de reconectar.

La venta digital sigue `POST /pagos/stripe/intenciones` (existente) solo tras apartado central. Backend muestra BOB, tasa global vigente/versionada, USD calculado con decimal y redondeo `ROUND_HALF_UP`; conserva la aceptación por intención. Una tasa ausente o vencida bloquea nueva intención. El webhook o reconciliación Stripe confiable confirma pago; navegación, push o timeout de red no lo confirman. `GET /pagos/stripe/estado/{venta_id}` (existente) permite consultar. Saldo personal se consulta/aplica **online** después de validar stock y total; se reserva durante pago mixto, se libera si se cancela y no genera intención Stripe de cero.

## Caja offline en PWA y Flutter

`POST /cajas/turnos` recibe caja, sucursal y cupos solicitados por variante; devuelve `turno_id`, `habilitacion_id`, ventana de ocho horas desde autorización online, cupos concedidos y versión inmutable de precios/promociones. Backend aparta esos cupos bajo bloqueo de inventario. La caja guarda habilitación, cupos y precios durablemente antes de vender. Solo cajero/administrador asignado a esa sucursal puede crear ventas locales; al expirar la ventana cesan ventas nuevas.

Cada venta cobrada y entregada usa `REGISTRAR_VENTA_CAJA` y se registra localmente antes de entregar. Al volver la red, backend verifica habilitación original, cupos consumidos, secuencia, precio y efectivo; `efectivo_recibido_bob - cambio_entregado_bob = total_bob` (cambio cero si se omite). Registra venta, pago/Kardex y resultado una sola vez, **sin volver a restar** las unidades ya apartadas. Una baja posterior de empleado/plan no borra una venta hecha válidamente: se acepta y audita. Una incidencia de datos o diferencia física pasa a `CONCILIACION_REQUERIDA`, conservando constancia de efectivo y entrega. `POST /cajas/turnos/{id}/cerrar` solo libera cupos tras recibir y resolver operaciones pendientes. Si se pierde caja/almacenamiento, `POST /cajas/turnos/{id}/recuperar` exige conteo físico, motivo, evidencia e intervención de encargado; reconcilia antes de liberar y nunca expira cupos automáticamente. Flutter consume también estas rutas con actor de caja autorizado y persistencia SQLite; la operación móvil de contado es obligatoria.

## Cambios, saldo y tasa

| Operación propuesta | Petición mínima | Respuesta/regla |
|---|---|---|
| `POST /cambios` | Venta/comprobante, unidades originales, variantes reemplazo, sucursal de origen, `Idempotency-Key` | Borrador valorado; hasta 15 días desde entrega, sin uso, misma sucursal y dentro de empresa. |
| `POST /cambios/{id}/confirmar` | Revisión y precio reemplazo aceptado, forma de cubrir diferencia, `Idempotency-Key` | Diferencia favorable a tienda: cobrar antes de entregar; favorable al cliente: emitir saldo personal. Estado recuperable si Stripe está incierto. |
| `GET /saldos/mio` | Sesión cliente | Saldo BOB y movimientos propios de la empresa. |
| `POST /ventas/{id}/aplicar-saldo` | Importe BOB, revisión e `Idempotency-Key` | Reserva/uso parcial online, sin doble gasto; resto por efectivo en caja online o Stripe online según canal. |
| `POST /plataforma/tasas-cambio` | Tasa BOB/USD positiva, inicio/fin de vigencia y motivo; superadministrador | Nueva versión global sin solape, auditable; no modifica intenciones anteriores. |

Valor de cada unidad devuelta: precio de la prenda menos descuento prorrateado, conservando centavos y excluyendo envío. Saldo utilizado originalmente es medio de pago, no descuento. Se reparte el residuo de centavos en orden estable de línea/unidad. Reemplazo usa precio vigente mostrado y aceptado. Saldo: mismo cliente y empresa, cualquier sucursal o canal online, sin vencimiento, uso parcial, no transferible ni convertible en efectivo.

## Reportes, ML y avisos

| Operación propuesta | Petición mínima | Respuesta/regla |
|---|---|---|
| `POST /reportes/interpretar` | Texto o transcripción web, nunca audio bruto como SQL | Gemini existente propone intención; backend valida tipo/filtros/rol/tenant y ejecuta consulta parametrizada. |
| `POST /reportes/consultar` | Tipo y filtros validados | Resultado tipado de datos reales, tabla/gráfico. Tipos: ventas por sucursal y periodo; productos más/menos vendidos; evolución semanal; ventas/ingresos por categoría. |
| `POST /reportes/exportar` | Misma consulta y formato `excel`, `csv` o `pdf` | Archivo derivado del mismo resultado, con autorización comprobada otra vez. |
| `GET /analitica/pronosticos` | Sucursal/producto/periodo, plan Profesional | Unidades previstas para la próxima semana, versión del modelo, periodo, métrica y aviso si faltan datos. |
| `GET /analitica/grupos-productos` | Filtros permitidos, plan Profesional | Agrupación por comportamiento, versión y métricas. |
| `GET /notificaciones/mias` | Sesión cliente | Bandeja durable de resultados propios; FCM Android y Web Push PWA solo avisan y al abrir reconsultan. |
| `POST /notificaciones/suscripciones` y `DELETE /notificaciones/suscripciones/{id}` | Canal `FCM` o `WEB_PUSH` y token/suscripción de dispositivo; sesión cliente | Vincular o revocar un dispositivo del usuario autenticado; ningún token concede acceso a los datos. |

Reportes usan fecha de aceptación central por defecto; fecha física local es filtro/dato separado. Brutas, descuentos, cambios/devoluciones y netas se muestran por separado; saldo emitido/usado no se suma otra vez como ingreso. ML se entrena localmente fuera de HTTP: generador sintético con semilla y versión separados de datos reales, evaluación temporal del pronóstico contra referencia simple y métricas para agrupación. Inferencia/reentrenamiento reales se aíslan por empresa. El descenso a Básico conserva historia para auditoría, pero bloquea acceso Profesional. La voz se transcribe en la web online; Flutter no administra reportes.

## Escenarios de aceptación entre repositorios

1. Dos empresas con un correo o SKU coincidente no se filtran por lectura, escritura, exportación, aviso ni resultado idempotente.
2. Dos clientes solicitan la última unidad offline: el primer apartado central puede seguir a pago; el segundo recibe `SIN_STOCK`, sin intención Stripe.
3. Reinicio y pérdida de respuesta: un UUID repetido no crea otra reserva/venta; payload modificado retorna 409.
4. Caja offline cobra/entrega dentro de cupo y turno, sincroniza y cierra sin doble descuento; caja perdida exige conteo auditado.
5. Tasa cambiada tras intención: webhook concilia USD y tasa congelados. Pago incierto no libera stock prematuramente.
6. Cambio entre productos con descuento y saldo mixto conserva centavos, impide doble uso y entrega solo tras confirmar diferencia.
7. Los cuatro reportes coinciden entre pantalla y exportaciones; ML muestra versión, métricas y datos insuficientes cuando corresponda.
