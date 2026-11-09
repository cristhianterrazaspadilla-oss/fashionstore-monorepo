# Contrato transversal 0.3.2

Leer [decisiones-0.3.1.md](decisiones-0.3.1.md), [integracion.md](integracion.md), las fichas de [casos-de-uso.md](casos-de-uso.md) y el [cierre CU03/04/16/18](cierre-cu03-cu04-cu16-cu18-0.3.2.md). La revisión documental 0.3.2 no cambia el protocolo de sincronización 0.4.0.

## Invariantes
- Empresa se deriva de sesión y autorización; parámetros/body identifican recursos, no otorgan acceso. Verificar cada FK y ámbito de empresa, usuario y sucursal. Plataforma tiene ámbito separado.
- Fechas ISO8601 con zona; almacenar timestamptz UTC y mostrar zona de empresa, inicialmente America/La_Paz. Reloj local no gobierna autorización central sin referencia verificada.
- UUID para recursos/comandos; correos normalizados únicos por empresa; códigos públicos únicos globalmente. No renumerar IDs persistidos por numeración académica.
- Importes BOB/USD como cadenas decimales, PostgreSQL NUMERIC, Decimal en backend. Centavos de proveedor como enteros. HALF_UP a dos decimales; precio/tasa congelados por operación.
- Cantidad positiva entera; importes no negativos salvo diferencia firmada del cambio. Total = base - descuentos + envío; adelanto/saldo son medios aplicados, no descuento comercial duplicado.
- Unidades entregadas = base de elegibilidad; devueltas/cambiadas/bloqueadas no se usan otra vez. Reembolso de dinero no altera inventario automáticamente.
- Stock libre = existencia física - reservas/compromisos pendientes - cupos offline no liquidados, con categorías excluyentes. La oferta digital no crea compromiso previo al cobro; tras captura se asigna un compromiso bajo bloqueo sin registrar todavía salida física. Entrega/despacho produce salida física única y libera compromiso. Sincronizar venta de cupo reduce físico y cupo consumido sin doble descuento del libre.
- Cantidades físicas vendidas no pueden ser negativas. Preparar lote de movimientos y referencias de negocio en una transacción, con bloqueo estable por empresa/sucursal/variante.
- Suma de devoluciones financieras reservadas/ejecutadas <= componentes originales disponibles; saldo se restaura sin conversión a efectivo.

## Mutaciones, fallos y concurrencia
Idempotency-Key UUID obligatorio para mutaciones comerciales, altas, liquidaciones, pagos y reembolsos. Ámbito (empresa, actor, tipo, clave) y hash canónico del cuerpo. Misma clave/contenido recupera resultado; clave con contenido distinto 409 OPERACION_MODIFICADA. No reutilizar la clave para nueva oferta/revisión. Secuencia de transición se valida bajo bloqueo y revision/If-Match lógico. Lecturas GET no requieren clave.

El webhook Stripe es una entrada firmada del proveedor: se autentica por firma/cuerpo y se deduplica por identificador de evento, sin header `Idempotency-Key` del cliente. Los trabajos internos (expiración, conciliación y outbox) usan clave de trabajo/recurso y transición, no sesión de un actor humano. `GET /carritos/mio` heredado puede crear el carrito en el servidor; su repetición no debe duplicarlo y se preserva compatibilidad.

Revisiones monótonas por agregado. Confirmar empresa y permisos antes de devolver resultado previo. Error de transporte no prueba rechazo ni no ejecución: conservar comando y consultar resultado. 401: reautenticar; 403: no reintentar sin resolver permiso; 409: conciliar revisión; 422: corregir; 503/timeout: consultar y reintentar misma operación.

No hay transacción SQL que incluya Stripe. Persistir orden/intención local y evento durable antes de llamada externa; reconciliador tolera caída antes/después de proveedor. Clave externa estable por orden. Registrar IDs de eventos y deduplicar; no retroceder estado final por webhook antiguo. Pago/reembolso incierto bloquea nueva ejecución equivalente hasta conocer resultado. No guardar secretos de tarjetas ni client_secret en logs.

Para `SOLICITAR_COMPRA` v3, el consentimiento local específico y el `preparacion_pago_id` opaco sobreviven reinicio, pero no son pago ni sustituyen sesión válida. El servidor conserva Customer/PaymentMethod/SetupIntent del proveedor y valida importe, moneda, tasa, condiciones, vigencia, tenant y propiedad antes de un intento conectado. Un cambio exige nueva aceptación; un método ausente o autenticación adicional exige intervención. UUID de operación, orden y clave del proveedor permanecen estables entre reenvíos. La cancelación de solicitud antes de cobro se serializa con el inicio de éste; una carrera se concilia antes de declarar cancelación, captura o reembolso.

## Privacidad y almacenamiento local
Catálogo público separado por empresa. Información privada separada por empresa/usuario/dispositivo; visible 8h desde login online. Logout/vencimiento oculta y bloquea acciones privadas, conserva pendientes para recuperar con identidad original. No dar resultados privados de otra cuenta. Turno caja8h es autorización específica distinta de JWT24h y privacidad8h. Si vence sesión online, no sincronizar hasta revalidar.

IndexedDB y SQLite: transacción local de cabecera/detalle/cola/cupo; estados PENDIENTE_ENVIO, ENVIANDO, RESULTADO_RECIBIDO, REQUIERE_ACCION. La compra v3 conserva consentimiento/huella/oferta y referencia opaca de preparación de pago en área privada aislada por empresa, usuario y dispositivo; nunca PAN/CVC, PaymentMethod, client_secret ni credenciales Stripe. Reinicio recupera ENVIANDO como pendiente de consulta sin nuevo UUID. Logout o fin de ventana privada oculta datos y suspende sync hasta reautenticar; no borra solicitudes pendientes ni las autoriza por sí mismo. Política de retención por confirmar antes de purgar: no purgar pendientes o obligaciones financieras abiertas.

## Notificaciones y comprobantes
Outbox en PostgreSQL junto con hecho de negocio; FCM Android/Web Push con consentimiento, bandeja durable y recuperación por cursor. Push indica cambio y abre consulta autorizada; no ejecuta pago al tocarla. Evento único por recurso/transición/revisión; reintento de entrega no duplica obligación. No prometer notificación si dispositivo no está conectado.

Comprobantes operativos no fiscales: UUID/código, empresa, sucursal, usuario, fecha, referencias a venta/recepción/cambio/pago/reembolso, líneas/importes y estado local/central/pendiente/ejecutado. PDF/consulta recuperable según caso. No afirmar devolución de dinero hasta evidencia de ejecución; conservar versión inmutable y corrección por documento enlazado.

## Capas y funciones conservadas
Backend modular único en app/core/modules; nueve módulos actuales y `caja_offline` como décimo paquete propuesto. Routers llaman servicios dueños; sincronizador despacha, no duplica stock/dinero. Repositorios/modelos SQLAlchemy del dueño; infraestructura transversal en core/db. Angular src/app/features y Flutter lib/features replican ámbitos según canal, no toda administración en móvil. Nuevos métodos en español, respetando firmas de SDK/framework.
Conservar LB04/05/09/10/13/16/17/18/20/22/25 y protocolos de Decart. [funciones-conservadas.md](funciones-conservadas.md) describe sus funciones y [modelo-datos-completo.md](modelo-datos-completo.md) sus ampliaciones. No crear archivos vacíos por plantilla ni microservicios nuevos.
