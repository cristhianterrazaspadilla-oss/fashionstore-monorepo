# Guía de revisión manual — primera presentación

Revisión documental 0.2.1 del diseño/protocolo 0.2.0. No prueba implementación. Leer README.md, primera-presentacion.md y equivalencias-cu.md antes de usar números de CU. Revisar las ocho fichas y sus paquetes; las dieciocho restantes y las once funciones LB se conservan como contexto/regresión.

## Revisión documental

- CU04 incluye registro local y sincronización; CU13 registro público de clientes y login empresarial; CU16 filtros/detalle/disponibilidad; CU18 crear/consultar/cancelar. Las ocho fichas tienen autor vacío y fecha 24/10/2026.
- Paquetes reales y grupos académicos son conceptos distintos. La distribución A/B corresponde a ocho casos, no a una división por tecnología.
- Flutter sí incluye contado offline en próximas presentaciones. No mantener la antigua exclusión móvil ni eliminar otras funciones del primer parcial.
- Comparar interfaz, esquemas y payloads: TIEMPO_INCOHERENTE se representa como CONFLICTO, sin reserva ni stock apartado. No confundir con un fallo de comunicación.
- Abrir enlaces locales de la carpeta; las referencias del catálogo actual se resuelven en casos-de-uso.md y las LB en funciones-conservadas.md.
- Comprobar que `/tienda/{empresa_codigo}` figura solo como navegación pública propuesta; no como API existente ni permiso. Ciudades globales pertenecen a plataforma; empresa consulta/selecciona y administra únicamente sucursales/tarifas propias. La pantalla inicial de selección de empresas es opcional posterior.
- Confirmar que la empresa heredada conserva datos/IDs/sucursales y que Profesional es asignación administrativa **condicional al conteo real de tres activas**. Fechas de inicio/vencimiento no se inventan en migración; el conteo del 18/10 es histórico.
- Separar visita de vencimiento: online desde creación central, offline aceptada desde creación local original; adelanto oportuno hasta 72 h desde el mismo origen. Ventana privada local de 8 h y JWT actual de 24 h son independientes; pendientes/resultados se conservan al ocultar datos.

## Verificación funcional cuando exista implementación

1. Registrar dos empresas y administradores; comprobar que el alta incompleta no deja residuos y que sin plan no se habilitan operaciones comerciales nuevas.
2. Asignar/renovar/cambiar plan; probar fechas inválidas, límites configurables, reducción, gracia y consulta propia sin permiso para modificar suscripción.
3. Registrar clientes e iniciar sesión por empresa desde el enlace público propuesto; probar roles, pertenencia, acceso por ID, cambio de enlace con sesión ajena y datos locales aislados. Tras 8 h/logout ocultar privados conservando pendientes/resultados, mantener catálogo público visible y recuperar privados solo tras reautenticar; un JWT vencido impide sincronizar aunque exista ventana local.
4. Gestionar sucursales/tarifas de la empresa; impedir cruces, exceder límites y desactivar con compromisos. Empresa consulta/selecciona ciudad global sin modificarla; plataforma administra ciudades. Consulta móvil solo muestra sucursales permitidas.
5. Instalar PWA compatible, descargar catálogo público por empresa en web y móvil, cerrar/reabrir sin red; verificar IndexedDB/SQLite, variantes, filtros, fechas y ausencia de stock garantizado. Probar sin descarga, cambio de empresa y descarga fallida sin perder copia previa.
6. Registrar reserva offline, cerrar/reabrir, enviar al recuperar red y conservar resultado. Probar visita distinta del origen de vencimiento, llegada después de 24 h, adelanto confirmado antes/después del plazo, tiempo incoherente y error de autenticación/red sin pérdida del pendiente ni apartado indebido.
7. Reenviar mismo UUID/contenido tras perder respuesta; una sola reserva y un solo efecto de stock. Mismo UUID con contenido distinto no altera el original ni filtra resultados ajenos.
8. Crear, consultar y cancelar reserva online propia; distinguir solicitud local de reserva central. Cancelar dos veces sin doble liberación; verificar 24 h desde creación central o local según caso, extensión hasta 72 h desde el mismo origen, fecha de visita independiente y consistencia con expiración/adelantos y fechas mostradas en clientes.

Estas son pruebas previstas; anotar por caso entorno, fecha, comando/pasos, resultado y evidencia real. No probar sobre la base activa. Pruebas de caja, pagos, cambios/saldo, reportes y ML se detallarán al abordar sus presentaciones; conservar regresión pertinente.

## Integridad y hallazgos

Comparar SHA-256 de cada archivo compartido enumerado en version.json, con las copias de los tres repositorios. Las huellas no validan lógica de negocio. Leer CAMBIOS-0.2.1.md y el historial CAMBIOS-0.2.0.md para distinguir aclaración documental de cambio de protocolo.

Registrar hallazgo con CU, archivo/sección, comportamiento observado, regla esperada y propuesta. Codex debe cotejar con el código/OpenAPI actual; no transformar una limitación de la implementación en cambio de requisito.
