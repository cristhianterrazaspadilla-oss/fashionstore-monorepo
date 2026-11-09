# Funcionalidades conservadas fuera de los 26 prioritarios

Los identificadores LB conservan el número de la línea base anterior y no pertenecen al catálogo actual CU01–CU26. Estas funciones deben seguir operativas y recibir controles transversales de empresa/permisos cuando corresponda. Su ausencia del catálogo prioritario no autoriza borrar pantallas, datos o servicios. El detalle heredado es referencia de conservación, no evidencia de pruebas. Autor y fecha heredados se conservan como procedencia.

## LB04 — Gestionar proveedores y lotes de recepción con costos

<table><tbody>
<tr><th>Nombre:</th><td>Gestionar proveedores y lotes de recepción con costos</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Registrar proveedores y recepciones valoradas de prendas.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Encargado de Almacén o Administrador.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Personal autorizado y sucursal/empresa identificadas.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El actor consulta proveedor.</li><li>Registra lote, variantes, cantidades y costos. El lote identifica la fecha, sucursal de destino y documento de referencia de la recepción.</li><li>El sistema valida datos y referencias.</li><li>Actualiza inventario, costos y Kardex.</li><li>Muestra el lote.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si cantidad, costo o proveedor no son válidos o pertenecen a otra empresa, no se confirma la recepción.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Lote y movimientos de entrada quedan consistentes y auditables.</td></tr>
</tbody></table>

## LB05 — Gestionar productos, variantes y maestros

<table><tbody>
<tr><th>Nombre:</th><td>Gestionar productos, variantes y maestros</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Mantener catálogo administrable, variantes y maestros relacionados.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Administrador autenticado en su empresa.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El administrador consulta maestros.</li><li>Crea o edita producto.</li><li>Añade variantes de talla/color. Cada variante queda vinculada al producto y conserva su identificador comercial para inventario y ventas.</li><li>El sistema valida referencias y SKU.</li><li>Guarda y presenta catálogo actualizado.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si SKU o combinación está duplicada dentro de la empresa, se solicita corrección sin crear variante.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Producto y variantes quedan vinculados a la empresa.</td></tr>
</tbody></table>

## LB09 — Solicitar, aprobar y recibir traslados

<table><tbody>
<tr><th>Nombre:</th><td>Solicitar, aprobar y recibir traslados</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Gestionar traslado entre sucursales asociado a reserva.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente; Encargado de Sucursal.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Existe necesidad de traslado y personal autorizado para aprobar/recibir.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente solicita prendas en sucursal destino.</li><li>El sistema identifica necesidad de traslado.</li><li>El encargado aprueba o rechaza. La aprobación compromete las unidades en origen para evitar venderlas durante el traslado.</li><li>Si aprueba, se despacha y recibe.</li><li>El inventario/Kardex refleja cada etapa.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si no hay stock en origen o se rechaza el traslado, la línea no pasa a preparada y el cliente recibe el resultado.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Estados de traslado y cantidades por sucursal quedan consistentes.</td></tr>
</tbody></table>

## LB10 — Preparar y atender reserva

<table><tbody>
<tr><th>Nombre:</th><td>Preparar y atender reserva</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Separar prendas y atender al cliente que visita la sucursal.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Encargado de Sucursal.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Reserva aceptada de la sucursal; encargado autenticado.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El encargado abre panel de reservas.</li><li>Selecciona una reserva.</li><li>Prepara las prendas y actualiza estado. La preparación se registra antes de entregar las prendas al cliente.</li><li>Atiende al cliente y registra el resultado.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si la reserva venció, fue cancelada o no pertenece a la sucursal, no se prepara ni entrega como vigente.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Reserva conserva su estado de atención y trazabilidad.</td></tr>
</tbody></table>

## LB13 — Consultar historial de compras

<table><tbody>
<tr><th>Nombre:</th><td>Consultar historial de compras</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Consultar ventas y detalles propios.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Cliente autenticado en la empresa correspondiente.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente abre historial.</li><li>El sistema valida identidad.</li><li>Lista sus ventas. El listado distingue las compras por su fecha e información de estado disponible.</li><li>El cliente abre detalle y estado de pago/entrega.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si intenta abrir compra ajena o de otra empresa, se deniega sin revelar datos.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">No hay cambios comerciales; se muestra solo historial propio.</td></tr>
</tbody></table>

## LB16 — Configurar y simular delivery por anillos

<table><tbody>
<tr><th>Nombre:</th><td>Configurar y simular delivery por anillos</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Calcular envío y dar seguimiento interno a una entrega simulada.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador; Cliente.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Tarifas de delivery configuradas; dirección en cobertura simulada.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El administrador configura tarifas.</li><li>El cliente elige dirección. La dirección seleccionada se conserva junto con el pedido para aplicar la tarifa correcta.</li><li>El sistema calcula anillo y costo.</li><li>El cliente confirma delivery.</li><li>El sistema muestra estado posterior.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si dirección queda fuera de cobertura o no existe tarifa válida, se solicita otra opción antes de confirmar.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Pedido conserva costo y modalidad de entrega acordados.</td></tr>
</tbody></table>

## LB17 — Usar probador virtual móvil

<table><tbody>
<tr><th>Nombre:</th><td>Usar probador virtual móvil</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Visualizar transformación remota de video para una prenda.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Cliente en Flutter con prenda elegida, permisos y conexión necesarios.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente elige prenda y abre probador.</li><li>El backend autoriza sesión y emite token temporal.</li><li>El SDK Android oficial establece sesión Decart Lucy 2.5. El permiso temporal limita la sesión al cliente y a la prenda seleccionada.</li><li>El cliente ve el resultado y cierra sesión.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si faltan permisos, conectividad o autorización, se informa y no se expone la clave permanente ni se inicia sesión no autorizada.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Sesión temporal finalizada o activa solo para cliente/empresa autorizados.</td></tr>
</tbody></table>

## LB18 — Generar sugerencias IA para cliente

<table><tbody>
<tr><th>Nombre:</th><td>Generar sugerencias IA para cliente</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Obtener sugerencias de prendas relacionadas con preferencias o catálogo.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente; Servicio IA.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Cliente autenticado; contexto permitido disponible online.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente solicita sugerencias.</li><li>El backend reúne contexto autorizado.</li><li>Consulta al servicio IA. La solicitud se limita al contexto necesario para que la recomendación corresponda al catálogo de la empresa.</li><li>Valida respuesta contra catálogo.</li><li>Muestra opciones.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si el servicio falla o propone artículos inválidos, se informa o usa respuesta segura sin exponer otros tenants.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">No modifica compras; recomendaciones quedan acotadas a la empresa.</td></tr>
</tbody></table>

## LB20 — Buscar prendas por comando de voz

<table><tbody>
<tr><th>Nombre:</th><td>Buscar prendas por comando de voz</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Buscar catálogo a partir de voz interpretada.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Cliente; Servicio IA.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Cliente en canal compatible con micrófono y permiso; catálogo disponible.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El cliente dicta la búsqueda.</li><li>El sistema transcribe e interpreta los filtros.</li><li>Valida los filtros permitidos. La interpretación se convierte en filtros revisables y no en una consulta libre a la base de datos.</li><li>Consulta el catálogo y presenta prendas coincidentes.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si no hay permiso de micrófono o no se entiende el comando, se solicita reformular o buscar por texto.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Solo consulta productos autorizados; no altera inventario.</td></tr>
</tbody></table>

## LB22 — Gestionar promociones

<table><tbody>
<tr><th>Nombre:</th><td>Gestionar promociones</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Crear, actualizar y consultar promociones.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Administrador autorizado; productos/variantes de su empresa disponibles.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El administrador define promoción y vigencia.</li><li>El sistema valida condiciones y referencias.</li><li>Guarda promoción. La vista previa permite revisar vigencia y productos alcanzados antes de activar la regla.</li><li>Muestra vigentes aplicables.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si condición se solapa de modo inválido o referencia otro tenant, se rechaza. Los turnos de caja abiertos conservan su versión autorizada.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Promoción versionada para operaciones posteriores, sin revalorizar ventas previas.</td></tr>
</tbody></table>

## LB25 — Consultar decisiones IA para inventario

<table><tbody>
<tr><th>Nombre:</th><td>Consultar decisiones IA para inventario</td></tr>
<tr><th>Autor:</th><td>Equipo FashionStore</td></tr>
<tr><th>Fecha:</th><td>18/10/2026</td></tr>
<tr><th colspan="2">Descripción:</th></tr><tr><td colspan="2">Solicitar sugerencias interpretativas de inventario.</td></tr>
<tr><th colspan="2">Actores:</th></tr><tr><td colspan="2">Administrador; Servicio IA.</td></tr>
<tr><th colspan="2">Precondiciones:</th></tr><tr><td colspan="2">Administrador autorizado; datos de inventario de su empresa disponibles online.</td></tr>
<tr><th colspan="2">Flujo Normal:</th></tr><tr><td colspan="2"><ol><li>El administrador solicita análisis.</li><li>El backend prepara métricas autorizadas.</li><li>Consulta servicio IA. El sistema presenta la sugerencia como apoyo de decisión para que el administrador la evalúe.</li><li>Valida y muestra sugerencias.</li></ol></td></tr>
<tr><th colspan="2">Flujo Alternativo:</th></tr><tr><td colspan="2"><ol><li>Si faltan datos o IA falla, se informa; ninguna sugerencia ejecuta automáticamente compras o movimientos.</li></ol></td></tr>
<tr><th colspan="2">Poscondiciones:</th></tr><tr><td colspan="2">Recomendación consultiva sin alterar inventario.</td></tr>
</tbody></table>
