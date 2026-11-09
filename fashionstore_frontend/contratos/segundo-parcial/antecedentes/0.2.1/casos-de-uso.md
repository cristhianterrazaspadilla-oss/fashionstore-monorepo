# Casos de uso — catálogo académico actual de 26

Actualización documental: **24/10/2026**. Las fichas no prueban implementación. Los ocho prioritarios son **CU01, CU02, CU03, CU04, CU13, CU15, CU16 y CU18**; tienen autor vacío y fecha 24/10/2026. Sus nombres y alcance rigen esta presentación.

Los otros dieciocho conservan el contenido de análisis anterior, con referencias renumeradas y corrección obligatoria de caja móvil; quedan sujetos a revisión detallada en próximas presentaciones. No se cambian todavía los nombres de CU07, CU08 y CU21 propuestos para revisión posterior.

[Equivalencias](equivalencias-cu.md) identifica los códigos antiguos. Las once funcionalidades no seleccionadas se conservan en [funciones-conservadas.md](funciones-conservadas.md) con códigos LB; no se eliminan del producto. Ver [reglas-aprobadas.md](reglas-aprobadas.md), [trazabilidad-cu.md](trazabilidad-cu.md) e [interfaz.json](interfaz.json).


## CU01 — Registrar empresa contratante

**Primera presentación.**

<table><tbody>
<tr><th>Nombre:</th><td>Registrar empresa contratante</td></tr>
<tr><th>Autor:</th><td></td></tr>
<tr><th>Fecha:</th><td>24/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Registrar una empresa contratante independiente y su administrador inicial en la plataforma compartida.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador de plataforma.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Conexión disponible; administrador de plataforma autenticado y autorizado; datos de empresa y administrador inicial disponibles.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor abre el registro de empresas e introduce los datos de la empresa, su código público y su administrador inicial.</li><li>El sistema valida permisos, campos y unicidad de los identificadores empresariales.</li><li>El actor revisa el resumen y confirma el alta.</li><li>El sistema crea empresa y administrador inicial y vincula su pertenencia en una operación consistente.</li><li>El sistema muestra el alta y el estado pendiente de asignación de plan.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ul><li><strong>2a.</strong> Si faltan datos, son inválidos o el identificador ya existe, informa qué corregir sin registrar el alta.</li><li><strong>2b.</strong> Si el actor no tiene permiso de plataforma, rechaza la operación.</li><li><strong>4c.</strong> Si falla cualquier parte del registro, revierte el alta incompleta; si se pierde la respuesta, comprueba el resultado antes de repetirla.</li></ul></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Empresa y administrador inicial asociados y aislados de las demás empresas. La creación no habilita por sí sola operaciones comerciales: requiere un plan válido según CU02.</td></tr>
</tbody></table>


## CU02 — Administrar suscripción de empresa

**Primera presentación.**

<table><tbody>
<tr><th>Nombre:</th><td>Administrar suscripción de empresa</td></tr>
<tr><th>Autor:</th><td></td></tr>
<tr><th>Fecha:</th><td>24/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Asignar, consultar, renovar o cambiar administrativamente la suscripción de una empresa, con plan, fechas y capacidades efectivas.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador de plataforma: asigna, renueva y cambia. Administrador de empresa: consulta únicamente la suscripción propia.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Empresa registrada; conexión y sesión válidas; actor autorizado para consultar o modificar según su ámbito.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor abre la suscripción de la empresa autorizada.</li><li>El sistema muestra plan, fechas, estado, límites y capacidades; si solo consulta, el flujo termina aquí.</li><li>El administrador de plataforma selecciona asignar, renovar o cambiar e introduce plan, fechas y motivo.</li><li>El sistema valida fechas, permiso y límite de sucursales activas; presenta un resumen.</li><li>El actor confirma la modificación.</li><li>El sistema guarda la suscripción y auditoría y muestra sus capacidades efectivas.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ul><li><strong>2a.</strong> Si no hay suscripción, muestra que está pendiente y permite asignarla al administrador de plataforma.</li><li><strong>3b.</strong> Si el administrador de empresa intenta modificar el plan, rechaza la operación.</li><li><strong>4c.</strong> Si las fechas son inválidas o la reducción excede el límite, pide regularizar sin borrar sucursales ni compromisos.</li><li><strong>4d.</strong> Para la empresa heredada, si se confirma que conserva tres sucursales activas, el administrador asigna Profesional con fechas explícitas; si el conteo difiere, registra el dato y revisa la asignación antes de aplicar. No crea una vigencia ficticia ni desactiva sucursales.</li><li><strong>6e.</strong> Si falla el guardado, conserva la versión anterior; una respuesta perdida requiere consultar el resultado.</li></ul></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Suscripción consultada o modificada consistentemente. Límites configurables: Básico 2 sucursales activas y Profesional 10. Gracia de 3 días; después se bloquean nuevas ventas, reservas y turnos, permitiendo consultas, posventa válida y cierre de compromisos previos. No hay cobro SaaS real.</td></tr>
</tbody></table>


## CU03 — Descargar catálogo para consulta offline

**Primera presentación.**

<table><tbody>
<tr><th>Nombre:</th><td>Descargar catálogo para consulta offline</td></tr>
<tr><th>Autor:</th><td></td></tr>
<tr><th>Fecha:</th><td>24/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Descargar y conservar un subconjunto del catálogo para consultar prendas y disponibilidad conocida sin conexión en PWA y Flutter.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente, incluido visitante para catálogo público; cajero o administrador cuando tenga permiso sobre el catálogo solicitado.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Conexión disponible para descargar; catálogo publicado y empresa identificada. Datos restringidos requieren identidad y permisos válidos.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor elige descargar catálogo en el contexto de empresa identificado por su enlace público, propuesto como `/tienda/{empresa_codigo}`, y las sucursales del ámbito permitido.</li><li>El sistema obtiene solo productos, variantes, precios, tallas, colores y disponibilidad pública conocida de esa empresa, con fecha y versión; cualquier dato restringido exige identidad y permiso.</li><li>La aplicación guarda la copia consistentemente en IndexedDB para PWA o SQLite para Flutter, separada por empresa.</li><li>La aplicación confirma la descarga solo tras completar la persistencia.</li><li>El actor puede cerrar y reabrir la aplicación sin red y consultar la copia mediante CU16, con fecha y aviso de posible desactualización.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ul><li><strong>2a.</strong> Si falla la comunicación, conserva la última copia válida e informa que no se actualizó.</li><li><strong>2b.</strong> Si no hay productos, muestra el catálogo vacío sin inventar existencias.</li><li><strong>2c.</strong> Si se solicitan datos restringidos sin permiso, deniega esa descarga.</li><li><strong>3d.</strong> Si falla el almacenamiento, no anuncia descarga completada y mantiene la copia válida anterior si existe.</li></ul></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Copia local durable asociada a empresa, sucursal/ámbito, fecha y versión. La descarga no reserva unidades ni modifica inventario central.</td></tr>
</tbody></table>


## CU04 — Registrar reserva offline

**Primera presentación.**

<table><tbody>
<tr><th>Nombre:</th><td>Registrar reserva offline</td></tr>
<tr><th>Autor:</th><td></td></tr>
<tr><th>Fecha:</th><td>24/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Registrar sin conexión una solicitud de reserva propia y sincronizarla para obtener aceptación, rechazo o conflicto central. El título abreviado incluye todo ese proceso.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Catálogo y sucursal conocidos; cliente autenticado previamente y datos privados locales habilitados dentro de las 8 h desde último login online. Para sincronizar se requiere conexión e identidad online válida.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente selecciona prendas, variantes, cantidades, sucursal y fecha de visita.</li><li>La aplicación muestra el resumen y aclara que la solicitud local no garantiza stock.</li><li>El cliente confirma; la aplicación persiste solicitud, detalle, UUID estable, empresa, sucursal y fecha de creación local.</li><li>La aplicación muestra pendiente de sincronización y conserva los datos tras cierre/reinicio.</li><li>Al recuperar conexión y validar la sesión, envía la misma operación con su fecha e identificador originales.</li><li>El backend valida actor, empresa, sucursal, plan, coherencia temporal, vigencia, visita y stock.</li><li>Si corresponde, registra reserva, líneas, movimientos y resultado durable de forma atómica.</li><li>La aplicación guarda y muestra el resultado; solo la aceptación central confirma el apartado.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ul><li><strong>3a.</strong> Si falla la persistencia local, no declara registrada la solicitud y permite intentar guardarla de nuevo.</li><li><strong>5b.</strong> Si no hay red o falla la comunicación, conserva el pendiente; no interpreta el corte como rechazo.</li><li><strong>5c.</strong> Si la sesión requiere renovación, oculta datos privados cuando corresponda y pide reautenticación, conservándolos aislados.</li><li><strong>6d.</strong> Si está vencida, no hay stock o una regla comercial impide aceptarla, registra rechazo durable sin apartado.</li><li><strong>6e.</strong> Si el tiempo es incoherente o no se puede validar, registra CONFLICTO con TIEMPO_INCOHERENTE, sin apartar stock.</li><li><strong>7f.</strong> Si ya existe resultado para el mismo UUID y contenido, devuelve el guardado tras reautorizar. Si se perdió la respuesta, consulta y reintenta con el mismo UUID; contenido distinto produce conflicto sin alterar la operación original.</li></ul></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Solicitud y resultado conservados. La reserva offline aceptada vence a las 24 h desde la creación local original; un adelanto confirmado online antes de vencer puede extenderla hasta 72 h desde ese mismo origen. La fecha de visita no sustituye ese origen. Recepción central, reenvíos y avisos no reinician ni prolongan el plazo; una solicitud vencida se rechaza sin apartar stock.</td></tr>
</tbody></table>


**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU05 — Sincronizar solicitud de compra digital

<table><tbody>
<tr><th>Nombre:</th><td>Sincronizar solicitud de compra digital</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr><tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Permite preparar una compra sin conexión y recibir una oferta de pago online solo después de verificar y apartar stock central.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Cliente autenticado previamente, sesión local privada válida, artículos seleccionados; ningún dato de tarjeta guardado localmente.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente guarda el pedido provisional en PWA o Flutter durante la desconexión.</li><li>La aplicación muestra «solicitud guardada, sin stock ni pago confirmados».</li><li>Al reconectar, envía la operación estable tras revalidar identidad.</li><li>El backend comprueba empresa, plan, precio y stock de todas las líneas desde una sucursal. La comprobación se realiza para el pedido completo y no confirma líneas parciales.</li><li>Con precio aceptado y stock suficiente, el backend aparta todas las líneas por 60 minutos y devuelve importe BOB y estado «falta pagar».</li><li>La aplicación informa el resultado por bandeja y, cuando corresponda, push; el cliente inicia CU22 online para pagar.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li value="4">Si falta una línea, se rechaza el pedido completo, se informa el faltante y no se cobra.</li><li value="4">Si cambió el importe, se solicita aceptación expresa del nuevo total antes de apartar y pagar; rechazarlo deja la compra sin cobro.</li><li value="5">Si otro cliente toma la última unidad primero, esta solicitud recibe indisponibilidad; un reintento con el mismo UUID no crea un segundo pedido.</li><li value="6">Si el compromiso vence antes de pagar, se libera según conciliación de Stripe y se notifica que debe comenzar una nueva solicitud.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Resultado central persistido y visible. Puede haber stock apartado temporalmente, pero la venta solo queda pagada tras CU22 y confirmación de Stripe; no hay cobro automático al reconectar.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU06 — Habilitar turno y cupos de caja offline

<table><tbody>
<tr><th>Nombre:</th><td>Habilitar turno y cupos de caja offline</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr><tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Asigna unidades físicas por variante a una caja PWA instalada o aplicación Flutter autorizada y autoriza un turno de hasta ocho horas.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cajero o Administrador de empresa autorizado para la sucursal.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Conexión disponible; actor autenticado; sucursal activa; plan en estado que permite nuevos turnos; caja identificada.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor solicita abrir turno y especifica variantes y cantidades físicamente verificadas.</li><li>El backend valida permisos, sucursal, disponibilidad libre y que la caja no tenga un turno incompatible abierto.</li><li>El backend asigna cupos por variante sin duplicarlos y congela precios/promociones autorizados. La asignación reduce la disponibilidad general mientras el cupo está bajo responsabilidad de la caja.</li><li>El backend emite habilitación ligada a empresa, sucursal, actor, dispositivo, lote y plazo de ocho horas.</li><li>La caja persiste habilitación, cupos y precios y muestra el turno listo para operar offline.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li value="2">Si falta stock, permiso o vigencia de plan, se informa la causa y no se aparta el cupo.</li><li value="5">Si falla la persistencia local, la caja no inicia ventas; el cupo asignado queda pendiente de cierre o recuperación controlada.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Cupo apartado del stock general y turno auditable; no se libera automáticamente al vencer el plazo.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU07 — Registrar y sincronizar venta de contado offline

<table><tbody>
<tr><th>Nombre:</th><td>Registrar y sincronizar venta de contado offline</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr><tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Permite cobrar efectivo y entregar prendas en caja PWA o Flutter sin Internet, y registrar después la venta central sin doble descuento de inventario.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cajero o Administrador de empresa autorizado para la sucursal.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Turno CU06 habilitado, dentro de ocho horas; cupo local suficiente; prendas físicamente presentes; precios autorizados descargados.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor selecciona variantes y cantidades dentro del cupo y verifica el total BOB autorizado.</li><li>La caja guarda un borrador local y bloquea temporalmente esas unidades del cupo para la operación.</li><li>El actor recibe el efectivo y confirma la operación.</li><li>La caja guarda atómicamente venta, líneas, total, efectivo, UUID y consumo definitivo del cupo; informa que el registro local es durable. La confirmación local preserva el importe efectivamente cobrado aunque la caja siga sin conexión.</li><li>El actor entrega las prendas y la caja registra la entrega en el mismo comprobante local.</li><li>La interfaz muestra «cobrado y entregado; pendiente de sincronización».</li><li>Al volver Internet, la caja envía la operación con la habilitación original.</li><li>El backend verifica cupo, turno, versión de precios y duplicados; registra venta, pago efectivo y Kardex una vez, y devuelve resultado.</li><li>La caja conserva el resultado y, al cerrar el turno tras enviar todas las ventas, devuelve solo cupo no usado.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li value="1">Si no hay cupo o el turno venció, la caja no permite cobrar ni entregar como venta offline.</li><li value="4">Si falla la persistencia antes de entregar, el actor devuelve el efectivo y no entrega prendas; el borrador se concilia o cancela sin consumir cupo definitivo.</li><li value="5">Si excepcionalmente falla el registro de entrega después del cobro, se conserva la venta local y se abre incidencia de entrega; no se borra el efectivo.</li><li value="8">Si plan o empleado expiró después de una venta válida, se registra y marca para revisión. Si hay corrupción, pérdida física o inconsistencia, se conserva el registro y se abre conciliación auditada.</li><li value="9">Si se perdió la caja, un encargado autorizado realiza conteo físico y cierre auditado antes de liberar cupos.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Venta físicamente realizada queda registrada o en conciliación trazable; resultado central durable, sin dos cargos de inventario ni dos pagos por reintento.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU08 — Cambiar prenda y liquidar diferencia

<table><tbody>
<tr><th>Nombre:</th><td>Cambiar prenda y liquidar diferencia</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr><tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Permite cambiar una o varias unidades entregadas por otra talla, color o producto, cobrando diferencia o emitiendo saldo.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Encargado de sucursal o Administrador de empresa autorizado; Cliente presenta la prenda y comprobante.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Conexión online; entrega hace como máximo el plazo configurado (15 días iniciales); sucursal de origen; comprobante; prenda sin uso; cantidad no cambiada previamente.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor localiza venta y unidades originales y registra la inspección de la prenda.</li><li>El sistema valida empresa, sucursal, plazo, comprobante, cantidades y estado.</li><li>El actor selecciona reemplazo; el sistema muestra valor neto reconocido por unidad, precio actual y diferencia. El cliente compara la prenda sustituta y la diferencia antes de autorizar el cambio.</li><li>El cliente acepta el reemplazo y el importe.</li><li>Si la diferencia favorece a la tienda, se confirma el cobro online antes de entregar; si favorece al cliente, se emite saldo personal.</li><li>El sistema registra cambio, inventario y Kardex sin duplicados y se entrega el reemplazo cuando la liquidación está resuelta.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li value="2">Si está fuera de plazo, usado, sin comprobante o en otra sucursal, se rechaza sin alterar venta ni inventario.</li><li value="3">Si no hay reemplazo disponible, se solicita otra opción antes de comprometer la operación.</li><li value="5">Si el pago Stripe queda incierto, se mantiene reemplazo y saldo aplicable reservados; no se entrega hasta confirmar o cancelar y conciliar.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Cambio vinculado a venta original, valores históricos y liquidación auditados; saldo emitido una sola vez o diferencia cobrada antes de entrega.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU09 — Aplicar saldo personal a una compra

<table><tbody>
<tr><th>Nombre:</th><td>Aplicar saldo personal a una compra</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr><tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Permite usar parcialmente o por completo el saldo de cambios en una compra online o presencial de la misma empresa.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente; Cajero o Administrador de empresa en una venta presencial autorizada.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Conexión disponible; cliente identificado; saldo positivo propio de la empresa; compra con importe aceptado.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente consulta su saldo y elige cuánto aplicar a la compra.</li><li>El backend valida identidad, empresa, saldo disponible y total.</li><li>El backend reserva el importe de saldo para impedir doble gasto. El bloqueo temporal del saldo evita que otra compra del mismo cliente use ese importe simultáneamente.</li><li>Si queda diferencia, el cliente la paga mediante efectivo registrado en tienda o Stripe online; si no queda diferencia, no se crea cobro Stripe de cero.</li><li>Al confirmarse la compra, el backend consume el saldo una sola vez y muestra el nuevo balance.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li value="2">Si el saldo pertenece a otra empresa/persona, no está disponible o la sesión es inválida, se rechaza sin aplicarlo.</li><li value="4">Si el pago complementario falla o queda incierto, el saldo permanece reservado hasta reconciliación; al cancelar, se libera.</li><li value="5">Un reintento devuelve la liquidación previa, sin segundo consumo.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Saldo consumido y compra liquidada de forma consistente; su uso no se cuenta como ingreso comercial nuevo.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU10 — Consultar pronóstico de unidades vendidas

<table><tbody>
<tr><th>Nombre:</th><td>Consultar pronóstico de unidades vendidas</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr><tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Muestra estimaciones de unidades para la semana siguiente por producto y sucursal, junto con versión y evaluación del modelo supervisado.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador de empresa con plan Profesional.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Sesión online autorizada; modelo entrenado/evaluado y datos suficientes para el ámbito solicitado.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor selecciona producto, sucursal y periodo de pronóstico en el dashboard.</li><li>El backend valida empresa, rol y plan Profesional.</li><li>El sistema prepara variables conocidas hasta la fecha de corte y ejecuta inferencia con modelo versionado. Solo se usan variables conocidas a la fecha de corte para no incorporar información futura al cálculo.</li><li>El dashboard presenta estimación, periodo, datos usados y error de evaluación, señalando si la validación fue solo sintética.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li value="2">Si el plan o permiso no habilita ML, se rechaza la consulta sin exponer resultados históricos de otra empresa.</li><li value="3">Si falta historial o modelo válido, se muestra «datos insuficientes» o indisponibilidad, sin inventar una predicción confiable.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Resultado de consulta auditable; ninguna venta ni inventario cambia por la estimación.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU11 — Consultar grupos de productos

<table><tbody>
<tr><th>Nombre:</th><td>Consultar grupos de productos</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr><tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Presenta agrupaciones aprendidas sin etiquetas previas a partir del comportamiento de ventas de productos.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador de empresa con plan Profesional.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Sesión online autorizada; datos e indicadores de productos de su empresa disponibles; modelo evaluado.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor abre el análisis de agrupación de productos.</li><li>El backend valida empresa, rol y plan.</li><li>El sistema calcula o recupera grupos de productos de esa empresa con el modelo versionado. El resultado se explica con los rasgos de ventas que caracterizan cada grupo.</li><li>El dashboard muestra productos por grupo, indicadores que lo caracterizan y métricas de calidad.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li value="2">Si no dispone de Profesional, se deniega el acceso.</li><li value="3">Si hay pocos productos o datos insuficientes para una agrupación interpretable, se muestra la causa sin asignar etiquetas arbitrarias.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Consulta registrada y resultados limitados a la empresa; ningún stock se modifica.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU12 — Configurar tasa de conversión BOB/USD

<table><tbody>
<tr><th>Nombre:</th><td>Configurar tasa de conversión BOB/USD</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr><tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Registra la tasa única de plataforma necesaria para preparar cobros Stripe Test en USD de importes comerciales BOB.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador de plataforma.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Actor autenticado; tasa positiva y fechas de vigencia conocidas.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor introduce tasa BOB por USD e intervalo de vigencia.</li><li>El sistema valida valor, fechas y que no existan versiones vigentes incompatibles.</li><li>El actor confirma; el sistema guarda nueva versión y autor del cambio. La fecha de vigencia permite saber qué versión corresponde a cada nuevo cobro.</li><li>Las nuevas intenciones de pago muestran BOB, tasa aplicada y USD redondeado antes de aceptar.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li value="2">Si la tasa es inválida o el intervalo se solapa, se rechaza y se indica qué corregir.</li><li value="4">Si no hay tasa vigente, se bloquea la preparación de un nuevo cobro Stripe; pagos existentes conservan tasa y USD previamente aceptados.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Versión de tasa auditada; ningún pago histórico se recalcula.</td></tr>
</tbody></table>

## CU13 — Registrarse e iniciar sesión por empresa

**Primera presentación.**

<table><tbody>
<tr><th>Nombre:</th><td>Registrarse e iniciar sesión por empresa</td></tr>
<tr><th>Autor:</th><td></td></tr>
<tr><th>Fecha:</th><td>24/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Permitir registro público de clientes y autenticación de usuarios en el ámbito empresarial autorizado.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente; administrador de empresa; encargado; cajero; administrador de plataforma con ámbito explícito de plataforma. El registro público solo crea clientes.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Conexión para registro/login central; contexto de empresa identificado para cuentas empresariales. Las cuentas de personal deben haber sido creadas por un proceso autorizado.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El usuario abre registro de cliente o inicio de sesión en el contexto de la empresa identificada, por ejemplo desde `/tienda/{empresa_codigo}`, o la selecciona explícitamente cuando corresponde.</li><li>Para registrarse, introduce sus datos; el sistema valida campos y unicidad dentro de la empresa y crea la cuenta de cliente.</li><li>Para iniciar sesión, introduce sus credenciales; el sistema valida identidad, estado y pertenencia a la empresa solicitada.</li><li>El sistema entrega una sesión con rol y ámbito autorizado: empresa o plataforma según la cuenta; nunca reutiliza silenciosamente una sesión de otra empresa.</li><li>La aplicación muestra funciones permitidas y mantiene separados los datos locales de cada usuario y empresa.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ul><li><strong>2a.</strong> Si hay campos inválidos o correo duplicado en esa empresa, pide corregir sin crear otra cuenta.</li><li><strong>3b.</strong> Si las credenciales son incorrectas, la cuenta está inactiva o no pertenece a la empresa, rechaza el acceso sin exponer datos ajenos.</li><li><strong>2c.</strong> Si se intenta obtener rol de personal o plataforma mediante registro público, rechaza esa elevación.</li><li><strong>3d.</strong> Si no hay conexión o se pierde la respuesta, no declara validado un nuevo login central; una ventana privada local previa solo permite consultar sus datos mientras siga vigente, sin autorizar sincronización.</li><li><strong>4e.</strong> Si el enlace apunta a otra empresa que la sesión activa, exige cambio de contexto y validación explícitos antes de acceder a datos privados.</li></ul></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Cliente registrado o usuario autenticado con rol y ámbito válidos; el código de empresa del enlace no concede acceso privado. Datos privados del cliente visibles localmente hasta 8 h desde último login online; al vencer o cerrar sesión, ocultar y conservar aislados, incluidos pendientes y resultados, hasta reautenticar. El catálogo público descargado sigue visible. La ventana local no modifica la vigencia JWT ni permite sincronizar con token vencido; reconectar o reintentar no la reinicia. Permisos y plan se verifican por operación.</td></tr>
</tbody></table>


**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU14 — Gestionar usuarios y roles de la empresa

<table><tbody>
<tr><th>Nombre:</th><td>Gestionar usuarios y roles de la empresa</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Crear, consultar, asignar rol y desactivar usuarios de la empresa.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Administrador autenticado en su empresa.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El administrador abre usuarios.</li><li>Consulta o introduce datos y rol. La selección puede corresponder a consultar, crear, cambiar rol o desactivar, según la tarea del administrador.</li><li>El sistema valida permiso y pertenencia.</li><li>Registra el cambio y muestra el estado actualizado.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si rol, datos o recurso no corresponden a su empresa, se rechaza sin alterar usuarios.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Usuarios y roles de la empresa quedan actualizados y auditables.</td></tr>
</tbody></table>

## CU15 — Gestionar ciudades, sucursales y tarifas

**Primera presentación.**

<table><tbody>
<tr><th>Nombre:</th><td>Gestionar ciudades, sucursales y tarifas</td></tr>
<tr><th>Autor:</th><td></td></tr>
<tr><th>Fecha:</th><td>24/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Consultar y seleccionar ciudades del catálogo global de plataforma; administrar sucursales y tarifas propias dentro del ámbito empresarial y de los límites del plan. La administración global de ciudades es una capacidad relacionada de plataforma, sin nuevo CU prioritario.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador de empresa: consulta/selecciona ciudades y administra sucursales y tarifas propias. Administrador de plataforma: administra el catálogo global de ciudades mediante capacidad relacionada. El primero no recibe permiso para modificar ciudades globales.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Conexión disponible; sesión y permisos administrativos válidos. Las operaciones que agregan recursos activos requieren capacidad de plan.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El administrador empresarial consulta las ciudades globales disponibles y las sucursales y tarifas de su empresa.</li><li>Selecciona una ciudad de referencia y crea o modifica únicamente sucursales y tarifas propias.</li><li>El sistema valida campos, referencias, permisos y pertenencia empresarial de sucursales y tarifas.</li><li>Si crea o activa una sucursal, comprueba el límite configurable del plan; si la desactiva, comprueba compromisos pendientes.</li><li>El actor confirma y el sistema guarda consistentemente y muestra la configuración. La administración del catálogo global de ciudades queda reservada al administrador de plataforma.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ul><li><strong>2a.</strong> Si el administrador empresarial intenta crear, editar o desactivar una ciudad global, rechaza la modificación; puede consultar y seleccionar ciudades disponibles.</li><li><strong>3b.</strong> Si hay datos inválidos, recurso ajeno o permiso insuficiente, rechaza el cambio sin afectar otra empresa.</li><li><strong>4c.</strong> Si el plan no habilita la nueva sucursal activa o se supera el límite, informa la causa.</li><li><strong>4d.</strong> Si existen pedidos, reservas, cupos u otros compromisos que impiden desactivar, exige resolverlos antes.</li><li><strong>5e.</strong> Si falla el guardado, conserva los datos anteriores y no informa éxito.</li></ul></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Ciudades globales consultadas/seleccionadas sin compartir por ello sucursales, tarifas ni datos comerciales. Sucursales y tarifas autorizadas de la empresa consultadas o actualizadas. Límites iniciales: Básico 2 y Profesional 10 sucursales activas, configurables desde backend. Flutter consume sucursales autorizadas para consulta/selección, sin requerir administración general.</td></tr>
</tbody></table>


## CU16 — Consultar catálogo de prendas

**Primera presentación.**

<table><tbody>
<tr><th>Nombre:</th><td>Consultar catálogo de prendas</td></tr>
<tr><th>Autor:</th><td></td></tr>
<tr><th>Fecha:</th><td>24/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Buscar prendas y consultar detalles, variantes y disponibilidad por empresa/sucursal, online o desde el subconjunto descargado.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente o visitante del catálogo público; cajero y administrador según permisos.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Empresa identificada; catálogo publicado con conexión o copia local válida disponible. Acceso a datos privados sujeto a autenticación.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor abre el catálogo de la empresa identificada por su enlace público propuesto `/tienda/{empresa_codigo}` o por contexto previamente validado; la aplicación identifica si consulta backend o copia local.</li><li>El actor aplica filtros y el sistema muestra solo productos públicos de esa empresa dentro del ámbito disponible.</li><li>El actor abre una prenda y consulta detalle, precios, tallas, colores y disponibilidad pública conocida por variante/sucursal.</li><li>Si se usa copia local, la aplicación muestra fecha de actualización, fuente local y aviso de disponibilidad conocida.</li><li>El actor ajusta filtros o selecciona una prenda para continuar en el proceso correspondiente, conservando el contexto de empresa sin conferir permisos privados.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ul><li><strong>1a.</strong> Si no hay red ni copia descargada, indica que debe descargar con conexión antes de consultar offline.</li><li><strong>2b.</strong> Si no hay coincidencias, muestra el resultado vacío y permite ajustar filtros.</li><li><strong>3c.</strong> Si el detalle no fue descargado, indica que requiere conexión; si no hay existencias, muestra indisponibilidad.</li><li><strong>1d.</strong> Si falla la consulta online y existe copia local, puede mostrarla identificándola claramente como información almacenada.</li></ul></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Consulta limitada al catálogo autorizado. No crea reserva, venta ni movimientos de inventario. Filtros y disponibilidad offline solo cubren los datos descargados por CU03.</td></tr>
</tbody></table>


**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU17 — Consultar Kardex, existencias y valorización

<table><tbody>
<tr><th>Nombre:</th><td>Consultar Kardex, existencias y valorización</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Consultar movimientos, cantidades y costos de inventario.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Encargado de Sucursal o Administrador.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Personal autenticado con permiso sobre sucursal/empresa.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor selecciona sucursal y filtro.</li><li>El sistema valida ámbito.</li><li>Obtiene existencias y Kardex. Los filtros permiten acotar la consulta a una variante o movimiento de interés.</li><li>Calcula o consulta valorización.</li><li>Presenta resultados.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si se solicita una sucursal ajena o sin permiso, se rechaza sin revelar movimientos.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">El inventario no cambia por la consulta.</td></tr>
</tbody></table>

## CU18 — Gestionar reservas de prendas

**Primera presentación.**

<table><tbody>
<tr><th>Nombre:</th><td>Gestionar reservas de prendas</td></tr>
<tr><th>Autor:</th><td></td></tr>
<tr><th>Fecha:</th><td>24/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Crear reservas centrales online, consultar reservas propias y cancelar las que permitan esa operación. Incluye reservas aceptadas desde CU04.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Conexión y sesión válidas para crear, consultar estado central o cancelar; empresa y recursos identificados. La creación offline se realiza mediante CU04.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>Para crear, el cliente selecciona variantes, cantidades, sucursal y fecha de visita.</li><li>El sistema presenta un resumen y el cliente revisa los datos.</li><li>El cliente confirma la solicitud online.</li><li>El backend valida identidad, empresa, plan, plazo/visita y stock.</li><li>El sistema registra reserva, líneas y apartado/movimientos de inventario consistentemente.</li><li>El sistema devuelve código, estado y vencimiento.</li><li>Para consultar, el cliente abre sus reservas.</li><li>El sistema lista únicamente sus reservas de la empresa, incluidas las aceptadas centralmente desde CU04.</li><li>Para cancelar, el cliente selecciona una reserva propia y solicita cancelación.</li><li>El sistema pide confirmación y comprueba que el estado permite cancelar.</li><li>El sistema registra la cancelación, libera las unidades que correspondan una sola vez y devuelve el resultado.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ul><li><strong>4a.</strong> Si falta stock o una regla impide crear la reserva, rechaza sin apartado parcial.</li><li><strong>5b.</strong> Si falla el registro, evita dejar reserva o movimientos parciales.</li><li><strong>7c.</strong> Si no hay conexión, solo puede mostrarse información previamente descargada como copia local; no se afirma estado central actualizado.</li><li><strong>8d.</strong> Si el recurso es de otra persona/empresa, rechaza sin revelar datos.</li><li><strong>10e.</strong> Si la reserva no permite cancelación, muestra la causa sin liberar stock.</li><li><strong>11f.</strong> Si ya fue cancelada, devuelve el resultado sin liberar unidades por segunda vez.</li><li><strong>11g.</strong> Si se pierde la respuesta, consulta/reconcilia antes de afirmar la cancelación; la interfaz no la presenta como confirmada por el mero intento de envío.</li></ul></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Reserva creada, consultada o cancelada según la rama elegida, con stock consistente. Creación online: 24 h desde creación central; creación offline aceptada: 24 h desde creación local original de CU04. Adelanto confirmado online dentro de vigencia extiende hasta 72 h desde el mismo origen, no añade 72 h. Fecha de visita, recepción, reintentos y avisos no cambian ese origen. Una solicitud offline vencida se rechaza sin apartado; una solicitud local sin aceptar no es reserva central. Cancelación y expiración liberan stock una sola vez.</td></tr>
</tbody></table>


**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU19 — Registrar venta presencial y pago en caja

<table><tbody>
<tr><th>Nombre:</th><td>Registrar venta presencial y pago en caja</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Cobrar venta presencial y registrar salida de inventario.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cajero.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Cajero autorizado; prendas o reserva disponibles.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cajero selecciona prendas o reserva.</li><li>El sistema calcula total y adelanto aplicable.</li><li>El cajero registra efectivo/pago. El total presentado incluye los conceptos vigentes y el saldo de reserva que corresponda.</li><li>El sistema confirma venta, líneas, pago y Kardex.</li><li>Emite comprobante.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si falta stock o el pago no queda confirmado, no se completa la venta. Para venta sin Internet se usa el flujo específico CU06, CU07.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Venta pagada e inventario actualizado una vez.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU20 — Registrar devolución y merma

<table><tbody>
<tr><th>Nombre:</th><td>Registrar devolución y merma</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Registrar retorno de prendas o merma de inventario.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Encargado de Sucursal.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Encargado autorizado; venta o inventario de su ámbito.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El encargado selecciona venta/prenda o existencia.</li><li>Indica cantidad y motivo.</li><li>El sistema valida cantidades y permisos. El sistema conserva el motivo indicado para explicar por qué cambia la existencia.</li><li>Registra movimiento de devolución o merma.</li><li>Muestra resultado.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si cantidad supera lo permitido o recurso pertenece a otra empresa, se rechaza. El cambio por otra prenda se trata en CU08.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Inventario y Kardex reflejan la operación aprobada.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU21 — Gestionar carrito y confirmar compra digital

<table><tbody>
<tr><th>Nombre:</th><td>Gestionar carrito y confirmar compra digital</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Preparar compra web o móvil y confirmar un pedido digital.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Cliente autenticado para confirmar; catálogo y sucursal disponibles.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente añade variantes al carrito.</li><li>Revisa cantidades y entrega/recojo.</li><li>Confirma. El resumen final permite detectar errores en cantidades o modalidad antes de confirmar.</li><li>El sistema valida precio y stock.</li><li>Aparta unidades y crea pedido pendiente de pago.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si se preparó offline, se guarda solicitud y CU05 valida al reconectar. Si falta stock o cambia precio, se informa antes del pago.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Pedido pendiente de pago o solicitud local, claramente distinguidos.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU22 — Procesar pago digital con Stripe Test

<table><tbody>
<tr><th>Nombre:</th><td>Procesar pago digital con Stripe Test</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Completar pago digital tras aceptación explícita del monto USD.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente; Pasarela Stripe de Prueba.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Pedido con stock apartado vigente; cliente online; tasa BOB/USD vigente.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente revisa BOB, tasa y USD.</li><li>Acepta e inicia Stripe Test.</li><li>La pasarela informa resultado. La aplicación muestra la referencia del pedido para que el cliente identifique el cobro.</li><li>El backend verifica evento, importe e intención.</li><li>Confirma venta y notifica.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si tasa falta, pago falla, queda incierto o llega tarde, se muestra estado recuperable y se reconcilia antes de liberar stock; no se confirma por retorno de navegador.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Venta pagada solo tras confirmación confiable, con moneda y tasa históricas.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU23 — Consultar dashboard e indicadores

<table><tbody>
<tr><th>Nombre:</th><td>Consultar dashboard e indicadores</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Consultar métricas operativas de la empresa.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Administrador autenticado con permiso para los indicadores solicitados.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El administrador abre dashboard.</li><li>El backend valida empresa/plan.</li><li>Consulta ventas e inventario reales. Los indicadores aplican el mismo periodo y sucursal elegidos por el administrador.</li><li>Calcula indicadores.</li><li>Presenta tablas o gráficos.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si se solicitan indicadores ML exclusivos de Profesional con plan Básico, se bloquea ese módulo; los indicadores convencionales permitidos siguen disponibles.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Consulta sin alterar datos y sin mezclar empresas.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU24 — Solicitar reporte generativo por voz o texto

<table><tbody>
<tr><th>Nombre:</th><td>Solicitar reporte generativo por voz o texto</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Crear reporte variable a partir de petición en lenguaje natural.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador; Servicio IA.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Administrador online con plan Profesional y permiso de reportes.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El administrador escribe o dicta petición.</li><li>El sistema transcribe si procede.</li><li>Gemini interpreta intención y filtros.</li><li>FastAPI valida tipo, tenant y parámetros. Los filtros quedan visibles para que el administrador compruebe qué periodo y alcance generaron el resultado.</li><li>Ejecuta consulta controlada y muestra tabla/gráfico.</li><li>Permite Excel, CSV y PDF.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si petición es ambigua, no soportada o excede permiso, se pide precisión o se rechaza sin ejecutar SQL arbitrario.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Reporte y exportación reflejan el mismo resultado autorizado de datos reales.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU25 — Consultar ventas de la sucursal

<table><tbody>
<tr><th>Nombre:</th><td>Consultar ventas de la sucursal</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Revisar ventas registradas de una sucursal.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Encargado de Sucursal o Administrador.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Personal autenticado con acceso a la sucursal.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor elige periodo/sucursal.</li><li>El backend valida ámbito.</li><li>Lista ventas aceptadas. El listado incluye las referencias necesarias para abrir el detalle de una venta autorizada.</li><li>Muestra detalle y totales.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si se consulta otra sucursal sin permiso, se rechaza. Venta offline aún no aceptada centralmente no figura como confirmada.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Consulta sin cambios; datos limitados a sucursal/empresa.</td></tr>
</tbody></table>

**Próximas presentaciones; detalle heredado pendiente de revisión específica.**

## CU26 — Expirar reservas automáticamente

<table><tbody>
<tr><th>Nombre:</th><td>Expirar reservas automáticamente</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Liberar stock de reservas vencidas de forma idempotente.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Temporizador.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Existen reservas vigentes con fecha de vencimiento; proceso autorizado.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El proceso identifica reservas vencidas.</li><li>Bloquea registros.</li><li>Actualiza estado y libera cantidades reservadas. La comprobación evita liberar existencias asociadas a una operación que todavía debe resolverse.</li><li>Registra Kardex.</li><li>Conserva resultado.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si una reserva ya se vendió, canceló o expiró, no se libera dos veces; si hay adelanto o pago en curso, se sigue su regla de conciliación.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Reservas vencidas y stock consistentes, con trazabilidad.</td></tr>
</tbody></table>
