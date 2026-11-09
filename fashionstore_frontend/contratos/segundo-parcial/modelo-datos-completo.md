# Modelo de datos completo propuesto — contrato de persistencia

El TXT SQL recibido es la propuesta estructural de 42 tablas para primera presentación; no acredita estado de Neon ni migraciones aplicadas. Se conserva como antecedente, sin ejecutarlo. Esta especificación amplía el modelo para todos los CU: no es DDL ejecutable ni prueba de implementación. Antes de escribir Alembic, comparar modelos y esquema real de destino con auditoría de solo lectura.

## Convenciones
Nuevos agregados UUID PK, empresa_id NOT NULL salvo referencia global, creada_en timestamptz, revision>=1. UNIQUE(id,empresa_id) permite FK compuesta a recursos del mismo tenant; también para detalles. Cantidad entera positiva, dinero NUMERIC no negativo, tasa NUMERIC positiva, fechas coherentes. FKs no sustituyen autorización en SELECT. RLS solo si se diseña rol/contexto transaccional verificable; no declararlo existente. Índices empezando por empresa_id y filtros de consulta; índices de FK cuando proceda.

Los nombres siguientes son lógicos propuestos: adaptar al esquema real sin duplicar entidades equivalentes; documentar correspondencia en migración.

| Entidad / ampliación | Campos principales y relaciones | Restricciones / dueño |
|---|---|---|
| empresas | código público, nombre, estado, version_catalogo, zona_horaria, politica_posventa_version | Código global único; identidad_empresas. |
| planes / suscripciones / historial_suscripcion | límites, capacidades, inicio/fin, gracia, asignador y motivo | Plan global; suscripción empresarial; no intervalos efectivos contradictorios; historial inmutable. |
| usuarios / roles / clientes / empleados | ámbito plataforma/empresa, correo normalizado, rol y sucursal | Unicidad correo por empresa y separada plataforma; cliente/empleado no referencia usuario ajeno. |
| sesiones/dispositivos autorizados | usuario, empresa, dispositivo, login online, revocación | Datos mínimos de control; no guardar JWT claro innecesariamente. |
| colores / color_componentes | color compuesto, componentes referenciados, orden de presentación | Sin ciclo, sin componente ajeno; una variante tiene un SKU y stock, aunque su color tenga varios componentes. |
| promociones / reglas_cantidad / promocion_variante | vigencia, ámbito, cantidad_minima, tipo descuento, valor, prioridad, acumulable=false inicial | cantidad_minima>=1, porcentaje0..100, importe>=0, fechas ordenadas; más de3 equivale mínimo4. |
| detalle_precio_aplicado / snapshots | línea origen, precio base, cantidad, promociones, descuento prorrateado, versión | Copia histórica; suma de centavos coincide con cabecera. catálogo/ventas_pagos/caja según origen. |
| inventario_sucursal / movimientos | variante/sucursal, físico, reservas, compromisos digitales posteriores a captura, cupos; documento origen | Único tenant/sucursal/variante; movimiento único por documento/tipo/línea; bloqueo e invariantes en transacción. |
| reservas / detalles / adelantos | origen_plazo_en, origen LOCAL/CENTRAL, visita, vence, operación y pagos | 24/72 h desde mismo origen; cambios históricos requieren regla explícita, no recálculo masivo ciego. |
| pedidos_compra / detalles_pedido | cliente, sucursal propuesta/asignada, origen offline, oferta, pago, cumplimiento, dirección snapshot | Pago y cumplimiento independientes; operación única; detalle por variante sin duplicados ambiguos. |
| ofertas_compra / detalles_oferta | versión, base/descuento/envío/total BOB, tasa_id, USD, aceptada_en, vence_en | Inmutable tras aceptación; 60min configurable antes de iniciar pago. No garantiza stock. |
| ordenes_pago / pagos / eventos_proveedor | contexto pedido/cambio/reserva, importe BOB/USD/centavos, tasa, proveedor/id externo, estado, idempotencia | Referencia externa única por proveedor/cuenta; evento_id único; soporte cambio requiere ampliar contexto original que solo admitía reserva/venta. |
| ventas / detalles_venta / entregas | pedido/caja origen, líneas netas, descuentos, fechas física/central, origen_turno | Preservar IDs existentes, agregar referencia pedido; no convertir captura pendiente de cumplimiento en entrega. |
| cajas / turnos / habilitaciones | dispositivo, actor, sucursal, autorizado_en, vence_en, snapshot_precios, estado, firma/token de autorización | Un turno incompatible por dispositivo; habilitación8h. No guardar secretos de firma en clientes. |
| cupos_caja / consumos_cupo | turno, variante, asignado, consumido, devuelto, incidencias | Consumo único por UUID/línea; consumido+devuelto<=asignado; cierre auditado. |
| devoluciones / detalles_devolucion / inspecciones | venta/línea, cantidad, recibido_en, motivo_codigo/descripcion, condicion_fisica, responsabilidad_tienda, inspector, resolución financiera | Unidad elegible bloqueada contra cambio/reembolso simultáneo; recepción en custodia, inventario separado de liquidación. |
| cambios / detalles_cambio / notas_cambio | devolución, valor neto original, reemplazos, diferencia, política, plazo/estado | Espera/aceptación explícitas; una resolución financiera por importe, no saldo más dinero duplicados. |
| compromisos_reemplazo / traslados | nota, variante, sucursal origen/destino, cantidades, vence, traslado_id | Reutilizar traslado existente; no inventar stock en tránsito como vendible antes de recepción. |
| entregas_reemplazo | cambio, dirección, tarifa aceptada, pagador, estado, fechas, comprobante | Original pedidos_entrega con UNIQUE venta_id no alcanza por sí solo para múltiples reemplazos; ampliar o entidad separada con FK explícita. |
| cuentas_saldo / movimientos_saldo / retenciones_saldo | cliente+empresa, crédito/débito, origen, compra, estado y revisión | Cuenta única cliente/empresa; libro inmutable; débito reservado bajo bloqueo; restauración única por resolución. |
| obligaciones_reembolso / detalles / ejecuciones | origen, pago, unidades, importe BOB, centavos USD, tasa original, medio, causa, estado, referencia externa | Reservar importe contra otros reembolsos/saldo; sumas por pago<=capturado-restaurado; external_ref único. |
| comprobantes / versiones | tipo, código, recurso origen, emisor, contenido snapshot/hash, fechas | Único empresa/tipo/código; no fiscal; corregir por documento vinculado. No sobreescribir evidencia de cobro. |
| operaciones_sincronizacion | esquema, UUID, actor/empresa/dispositivo/secuencia, hash, contenido, resultado/revisión | Conservar v1/v2; añadir v3 de compra y estados nuevos negociados en protocolo 0.4.0. SQL previo restringía CONFLICTO a TIEMPO_INCOHERENTE: ampliar coherentemente a otros conflictos si se usan. |
| referencias_horarias | empresa/actor/dispositivo, hora central/local, desfase_segundos, emitida_en, valida_hasta, tolerancia_segundos, politica_version, clave/hash idempotentes | Política congelada al emitir; referencia 8 h y tolerancia inicial 5 min configurables. La hora local con offset Bolivia se normaliza a UTC; no confiar en hora local arbitraria ni renovar privacidad por emitir referencia. |
| outbox / notificaciones / dispositivos_push | evento, empresa, destinatario, recurso/revisión, canal, intentos, estado, leído_en | Dedupe evento/usuario/canal; secretos de suscripción protegidos; logout desvincula dispositivo apropiadamente. |
| consultas_reporte / resultados | actor, empresa, tipo/filtros autorizados, snapshot, fecha, hash, formato | Snapshot consistente entre pantalla/exportación; paginación y límites; retención explícita. |
| datasets / ejecuciones_ml / modelos / predicciones / grupos | tenant, tipo, versión, origen sintético/real, semilla, features, métricas, artefacto/hash, periodo | Artefacto por empresa, validación temporal, no ejecutar pickles no confiables; guardar versiones de dependencias. |
| políticas_posventa / auditoría | versión, parámetros, actor, causa, antes/después minimizados | Política congelada por operación; no exponer secretos o contenido privado completo en logs. |

## Almacenamiento local
IndexedDB y SQLite conservan tablas/stores equivalentes: catalogos_versiones, productos, variantes, colores/componentes, promociones, sucursales, sesión mínima, operaciones_pendientes, líneas_operación, resultados, turnos, cupos, ventas_locales, detalles_venta_local, comprobantes_locales y cursores. FK/índices o integridad equivalente; transacciones para venta+cola+cupo. Sesión sensible en mecanismo adecuado de plataforma; no trasladar datos de tarjeta a SQLite.

Migraciones locales versionadas y recuperables preservan pendientes v1/v2; no limpiar datos para actualizar esquema. Backend propuesto acepta v1/v2 y v3 solo para compra según capacidad negociada. Datos de empresa/usuario permanecen aislados en logout/cambio de cuenta. En Flutter usar persistencia real SQLite; SharedPreferences/BolsaStore RAM no la sustituyen.

## Políticas de integridad financiera

### Extensión 0.3.1 propuesta

| Agregado | Campos principales | Restricción |
|---|---|---|
| Métodos preparados | ID opaco, empresa/cliente, referencias Customer/PaymentMethod/SetupIntent protegidas solo en backend, estado LISTO/REVOCADO | Vinculación verificada online; referencia única; no guardar datos sensibles en cliente local. |
| Consentimientos de compra | operación, huella, desglose BOB/USD, tasa, condiciones, vigencia, método preparado, aceptación | Inmutables y específicos; no sustituyen sesión válida; revocación/cancelación auditada. |
| Orden/cobro/cancelación | operación v3, revisión, clave estable del proveedor, inicio/captura, cancelación en carrera | Un único cargo efectivo y una obligación CU27 por causa; reconciliar antes de resolver carrera. |
| Compromiso/salida | pedido, variante/sucursal, cantidad, estado, referencia captura y entrega | Oferta sin compromiso; compromiso posterior a captura; salida física única al entregar. Cupos caja excluyentes. |
| Devolución/inspección | motivo código/descripción, condición física, responsabilidad tienda, resolución financiera, política versión | Recibo en custodia no vendible; evaluación tardía autorizada; reposición solo por movimiento aprobado. |

IndexedDB y SQLite se expanden con compra/consentimiento/referencia opaca aislados por empresa/usuario/dispositivo y lápida de cancelación durable. La transacción local guarda compra, consentimiento y cola juntos. Reinicio/timeout consulta el UUID anterior; logout oculta datos y suspende sync sin purgar obligación. Conservar v1/v2 legibles y no convertirlos en cobro automático.
Pedido pagado sin stock genera obligación de devolución sin movimiento de salida de prenda. Devolución física apta genera reposición sin afirmar que dinero se devolvió. Diferencia a favor cliente se asigna por resolución única a saldo o reembolso. Reembolso parcial se calcula del neto histórico prorrateado; último remanente absorbe ajuste de centavos sin exceder captura. En pago mixto, reintegrar saldo hasta componente original y dinero por pago de origen. No usar nueva tasa USD para reembolsar.
