# Contrato Angular y PWA

**Estado:** aclaración documental 0.2.1 sobre diseño web 0.2.0; PWA y almacenamiento offline no se encontraron en la inspección estática. Reglas compartidas en [compartido.md](compartido.md). Al modificar `frontend-web`, conservar la identidad visual existente, navegación y permisos por rol, diseño adaptable, accesibilidad de teclado/lectores, estados de carga/error claros y textos de producto comprensibles. Verificar rutas y flujos en pantalla real antes de dar por terminada una capacidad.

## Ubicación de la implementación

[paquetes-cu.md](paquetes-cu.md) relaciona los CU actuales y las carpetas propuestas bajo `src/app/features/<paquete>/`; [equivalencias-cu.md](equivalencias-cu.md) conserva la numeración anterior. Cada nueva vista, servicio y modelo pertenece a su paquete; `src/app/core/` se reserva para sesión, guardas, interceptores y sincronización reutilizable. CU06/CU07 posteriores requieren `features/caja_offline/` separado de la caja online existente en `features/ventas_pagos/caja/`. CU09 usa `features/posventa/saldo/` y checkout consume ese servicio sin duplicar reglas. Las URL públicas siguen definidas en `app.routes.ts` y los mensajes HTTP en el contrato compartido, aunque cambie la ubicación interna de archivos.

## Ámbitos y navegación

| Área | Conexión | Persistencia local |
|---|---|---|
| Administración habitual | Obligatoria | Solo datos de sesión/caché ordinario; gestión de empresas, planes, inventario, cambios, reportes y ML no opera offline. |
| Cliente PWA parcial | Catálogo descargado, carrito, solicitud de reserva/compra y pendientes disponibles offline según reglas | IndexedDB separado por empresa/usuario para privados; catálogo público versionado. |
| Caja web instalada | Turno habilitado online; venta de contado dentro de cupos durante desconexión | IndexedDB separado de cliente: habilitación, precios, promociones, cupos, borradores, ventas, efectivo/entrega y resultados. |

La caja requiere rol de cajero/administrador y sucursal asignada. Nunca se habilita por una sesión de cliente. Se debe probar instalación y reinicio offline reales; compartir origen Angular no implica compartir datos ni permiso. Configurar manifest y service worker sin ámbitos/cachés que entreguen datos de otra empresa o usuario.

La navegación pública propuesta `/tienda/{empresa_codigo}` selecciona productos, variantes, precios y disponibilidad pública conocida de una empresa; aún no es ruta implementada ni endpoint API. Mantener ese contexto al abrir registro/login y continuar operaciones. Si la sesión activa pertenece a otra empresa, exigir cambio y validación explícitos antes de datos privados. Una pantalla inicial para escoger empresas es mejora opcional posterior. Ciudades se consultan/seleccionan desde catálogo global; la interfaz empresarial administra solo sucursales y tarifas propias. La edición global de ciudades corresponde a plataforma.

## Cliente PWA

- Invitado consulta solo catálogo público previamente descargado de la empresa identificada. Usuario previamente autenticado puede ver datos privados hasta ocho horas desde último login online; al vencer/logout se ocultan y se conservan aislados por empresa/usuario junto con pendientes y resultados hasta reautenticación. El catálogo público puede seguir visible. Recuperar red o reintentar no reinicia la ventana. La aplicación no envía pendientes con una cuenta distinta ni con JWT vencido; la ventana local es independiente de la vigencia JWT actual de 24 h y del turno de caja.
- Cada operación se escribe antes de mostrar «guardada localmente» y conserva UUID/versión/fecha/estado tras reinicio. Enviar al abrir, volver al primer plano, recuperar red o pulsar reintentar; no prometer sincronización garantizada con PWA cerrada.
- Mostrar fecha de última descarga y «existencia conocida», no «stock reservado» para copia local. Si precio o stock cambia al sincronizar, mostrar detalle y acción de aceptación o corrección.
- Presentar en reserva la fecha de visita separada de `vence_en`: online 24 h desde creación central, offline aceptada 24 h desde creación local original; adelanto confirmado online antes de vencer fija 72 h desde el mismo origen. Recepción, reintento o aviso no alteran ese plazo; una solicitud offline vencida se muestra rechazada y el conflicto temporal conserva su resultado.
- Bandeja de resultados persistida, aviso visible con app abierta y Web Push cuando navegador/permiso lo permiten. Push abre y reconsulta estado autenticado; no inicia pago.

## Caja web offline

- Descargar antes de desconectar habilitación de ocho horas, cupos, productos, precios y promociones autorizados. Guardar todo en una transacción local verificable antes de permitir el turno.
- Impedir nueva venta sin cupo, después de ocho horas, ante fallo de persistencia o con una caja/usuario distinto. Guardar borrador y cupo provisional; si se recibe efectivo, registrar venta durable antes de entregar. Si falla, devolver efectivo y no entregar.
- Etiquetas separadas: «cobrado y entregado localmente», «pendiente central», «registrado central» e «incidencia para conciliar». No borrar registros de efectivo/entrega por un error de red o conflicto.
- Al volver Internet, consultar/enviar operaciones con mismo UUID, recuperar resultados, sincronizar todo, cerrar turno y solo entonces devolver cupos no usados. Pérdida de almacenamiento requiere flujo online de conteo auditado; no auto liberar.

## Funciones nuevas en español y aceptación

Ejemplos de nombres Angular: `guardarSolicitudLocal`, `sincronizarPendientes`, `consultarResultado`, `ocultarDatosPrivados`, `abrirTurnoCaja`, `guardarVentaLocal`, `cerrarTurnoCaja`, `mostrarEstadoPago`. Adaptar servicios HTTP existentes en vez de duplicar lógica de negocio; stock, precio, permiso y aceptación son del backend.

Pruebas: instalación, reapertura sin red, múltiples pestañas, cambio de usuario/empresa, sesión de ocho horas, solicitud caducada, stock/importe cambiado, dos cajas, cuota agotada, turno vencido, error de escritura IndexedDB, push denegado y recibo/resultado durable. Pago, cambios, reportes y ML requieren conexión.
