# Contrato Flutter, SQLite y caja móvil posterior

**Estado:** aclaración documental 0.2.1 sobre diseño móvil 0.2.0. SQLite y operaciones offline son requisitos pendientes según la inspección estática. Comparte comandos/resultados con [compartido.md](compartido.md), no la persistencia física de Angular.

## Ubicación de la implementación

[paquetes-cu.md](paquetes-cu.md) distingue carpetas actuales de propuestas bajo `lib/features/<paquete>/`; [equivalencias-cu.md](equivalencias-cu.md) conserva los números anteriores. Los servicios y modelos específicos permanecen en su paquete; `lib/core/` alojaría SQLite y sincronización reutilizable. CU09 prevé `lib/features/posventa/saldo/`; checkout lo consumiría sin duplicar el cálculo. CU06/CU07 posteriores exigen caja móvil de personal autorizado en `lib/features/caja_offline/` o paquete equivalente acordado. Las funciones y métodos nuevos Dart usan español `camelCase`, salvo firmas exigidas por SDK o framework.

## Alcance y almacenamiento

La app actual atiende principalmente al cliente y consume catálogo/reservas online. El contrato global incluye catálogo descargado, reserva propia, carrito/solicitud de compra diferida, pendientes/resultados, pago Stripe **online**, saldo consultable/utilizable online, notificaciones y probador virtual. También incluye, para CU06/CU07 posteriores, personal autorizado, turno/cupos, efectivo y venta de contado offline con SQLite y sincronización. Esa capacidad no se encontró implementada; su ausencia de los ocho CU prioritarios no la excluye del alcance global.

El catálogo público de una empresa se identifica mediante un enlace/contexto propuesto como `/tienda/{empresa_codigo}`; en Flutter es referencia de navegación compartible, no ruta implementada ni permiso. Conservar la empresa al pasar a registro/login y a solicitudes. Una sesión de otra empresa requiere validación explícita; no se reutiliza silenciosamente. La pantalla inicial de selección de empresas es mejora opcional posterior. Ciudades son referencias globales administradas por plataforma; móvil solo las consulta/selecciona cuando corresponda, y muestra sucursales de la empresa autorizada.

SQLite tendrá tablas o estructuras equivalentes versionadas para catálogo/variantes por empresa, copia de sucursales permitidas, identidad local mínima, solicitudes y líneas, cola de operaciones, resultados/notificaciones y metadatos de sincronización. No guardar tarjeta ni clave permanente de proveedores. Cada fila privada se vincula a empresa y usuario; logout/cambio de cuenta oculta datos propios y no los sincroniza con otra identidad.

La ventana privada local vale ocho horas desde último login online; es independiente del JWT actual de 24 horas guardado por `SessionManager` y de la habilitación de caja offline. Al vencer o cerrar sesión se ocultan datos privados, pero se conservan aislados por empresa/usuario, incluidos pendientes y resultados. Catálogo público descargado continúa visible. Recuperar red o reintentar no renueva las ocho horas; al reautenticar, la app recupera pendientes propios y backend revalida empresa, plan, stock, precio y vigencia. Un token vencido impide sincronizar aunque la ventana local estuviera vigente. Una escritura local confirmada debe sobrevivir a cierre/reinicio normal.

## Reserva, compra y avisos

**Reloj de reservas offline (C34).** Guardar en SQLite la referencia horaria emitida durante el acceso online. Se usa para crear solicitudes durante 8 h desde emisión; backend tolera 5 min de desfase. La app también respeta sus 8 h privadas desde el último login online, que no se renuevan por obtener otra referencia. Al reconectar, reautenticar y enviar UUID, referencia y fecha originales aunque la referencia haya caducado; el servidor valida si la solicitud se creó dentro de su ventana y si ya transcurrieron sus 24 h. No declarar aceptada una reserva hasta recibir el resultado central.

| Acción | Comportamiento móvil |
|---|---|
| Crear reserva sin red | Guardar UUID, creación local, sucursal, visita y líneas; mostrar pendiente sin prometer stock. |
| Mostrar vencimiento | Separar visita de origen: online 24 h desde creación central; offline aceptada 24 h desde creación local original; adelanto confirmado online antes de vencer fija 72 h desde ese mismo origen. Recepción y reintentos no prolongan. Mostrar rechazo por solicitud vencida o conflicto temporal durable sin prometer apartado. |
| Crear compra sin red | Guardar solicitud y líneas; no crear intención Stripe ni reservar stock desde el teléfono. |
| Recuperar Internet | Enviar operaciones propias con UUID estable; consultar resultado si se perdió respuesta; presentar falta de stock, precio cambiado o aceptación. |
| Pagar | Solo online, después de apartado central y aceptación del BOB/USD mostrado. Abrir flujo Stripe existente y consultar estado final; no inferir éxito de la navegación de retorno. |
| Avisar | Guardar bandeja propia y recibir push FCM Android cuando haya permiso y servicio; al tocarlo, autenticar y consultar estado. |

La sincronización en segundo plano depende del sistema operativo; debe existir recuperación al abrir y reintento manual. No prometer ejecución instantánea estando cerrada. El probador existente conserva Lucy 2.5 y su puente Android oficial, con autorización por tenant; no rediseñarlo como parte de ML.

## Funciones nuevas en español y pruebas

Nombres sugeridos Dart: `guardarSolicitudLocal`, `sincronizarPendientes`, `consultarResultado`, `ocultarDatosPrivados`, `registrarTokenNotificacion`, `abrirPagoEnLinea`. Mantener firmas obligatorias de SDK como adaptadores y no renombrar silenciosamente servicios públicos existentes.

Pruebas de aceptación: reinicio sin conexión, sesión local vencida, cambio de usuario/empresa, solicitud de reserva vencida desde creación local, competencia por última unidad, precio nuevo, mismo UUID tras pérdida de respuesta, push concedido/denegado, pago exitoso/fallido/en verificación. Validar push y probador realtime final en Android físico. La venta de contado móvil requiere pruebas propias en la presentación posterior.
