# Plan de migración — textual, sin ejecución

## Punto de partida
El TXT recibido es propuesta ajustada de 42 tablas (25/10), no exportación certificada del estado actual. En el checkout inspeccionado hay revisiones Alembic `0001`–`0005`, modelos SQLAlchemy en `app/core/modules/*/models.py` y DDL directo en `app/main.py` durante `lifespan`. Esto no certifica el esquema real de Neon ni las revisiones aplicadas. Verificar esquema, Alembic heads y datos mediante inventario autorizado de solo lectura antes de preparar migración. No ejecutar CREATE completo sobre una base existente ni inventar `alembic_version`; no arrancar `main.py` para inspeccionarla.

## Etapas
1. Inventario solo lectura: tablas/columnas/FKs/índices/enums, revisiones y conteos no sensibles; backup y restauración ensayada en base aislada. No publicar credenciales ni filas personales.
2. Expandir tenant: empresa heredada con IDs existentes, códigos/ámbitos, roles globales, email por empresa. `Usuario.correo_electronico` es único global y `Rol.nombre` también; `Sucursal` es única por `(ciudad_id,nombre)` y aún no contiene `empresa_id`. Agregar columnas nullable para backfill; verificar cero huérfanos/cruces; después NOT NULL/FKs compuestas y reemplazar unicidades con índices/constraints por ámbito sin ventana de duplicados. Confirmar sucursales y fechas/plan heredado administrativamente. No inventar tenant para registros ambiguos.
3. Expandir catálogo/stock: componentes de color, reglas de cantidad, snapshots, cupos/turnos y fuentes de movimientos únicas. No crear stock adicional por convertir esquema.
4. Crear pedidos/ofertas/órdenes de pago; ampliar contexto de pago para cambios; separar pago/cumplimiento/entrega. Versionar tasa/centavos, registrar eventos proveedor y reconciliador.
5. Posventa/libros: recepción/inspección/notas, entregas de reemplazo, obligaciones/ejecuciones de reembolso y saldo. Migrar devoluciones anteriores sin inventar que hubo un egreso; marcar datos no verificables para conciliación.
6. Sync/outbox/comprobantes/analítica: `version_esquema` v1/v2/v3; nuevos resultados no confundidos con pago. Mantener consumidores viejos en versión compatible hasta actualizar W/M.
7. Contracción solo tras verificar dependencias, pruebas y ausencia de pendientes incompatibles; nunca borrar datos financieros para pasar una migración.

## Compatibilidad y semántica v1/v2/v3
Reserva y venta caja mantienen v1 y payload; compra v2 conserva solicitud con consentimiento posterior, y compra v3 agrega autorización específica para cobro conectado al reconectar. Una compra v1/v2 pendiente conserva UUID/cuerpo y resultado histórico; no se convierte por reintento en cobro automático. Para adoptar flujo nuevo, el cliente confirma nueva oferta y crea vínculo de migración a solicitud v3; original queda migrada/cancelada solo tras constatar que no se cobró ni comprometió dos veces. No cambiar hash de operación emitida.
Protocolo 0.4.0 requiere ampliar CHECK de estados/tipos donde proceda (SQL propuesta solo permitía 7 estados y conflicto temporal). Mantener estados viejos legibles; adaptar clientes antes de recibir nuevos estados. Migración SQLite/IndexedDB mantiene colas y datos aislados; no limpiar almacenamiento para resolver incompatibilidad. `Venta`, `PedidoEntrega`, `Pago` y sus claves existentes se conservan: añadir órdenes/ofertas/obligaciones y referencias sin reinterpretar una venta `PENDIENTE_PAGO` como cobro confirmado. Los movimientos de reserva digital previos al pago se conservan históricamente, pero el nuevo flujo no los crea; cortar por versión/fecha, sin deshacer compromisos heredados aún vigentes.

## Expansión 0.3.1 / protocolo 0.4.0 sin ejecución

Para motivos históricos de devolución: si hay texto libre conservado, asignar `motivo_codigo=OTRO` y copiarlo íntegro a `motivo_descripcion` sin inferir defecto/culpa. Si no hay texto, conservar `motivo_codigo` nulo bajo marca `LEGADO_SIN_CLASIFICAR` hasta revisión autorizada; la exigencia de código aplica a nuevas solicitudes. La condición física, responsabilidad y resolución no demostradas permanecen pendientes; no reponer stock por migración.

### Datos y flujos nuevos

Agregar método preparado y consentimiento específico con referencias del proveedor protegidas solo en backend; índices únicos de operación, orden, evento y obligación. Ampliar CHECK/enum para `version_esquema=3` solo en compra y estados/códigos nuevos, sin eliminar v1/v2. Negociar protocolo 0.4.0 en W/M antes de emitir estados nuevos. Nunca interpretar compra v1/v2 pendiente como autorización de cobro. Serializar cancelación e inicio de cargo; conservar órdenes y claves externas tras reinicio.

Separar compromiso de stock digital posterior a captura, salida física posterior y cupo de caja, con referencias únicas. Antes de activar el cobro previo a asignación, habilitar CU27, outbox y conciliación. Migrar devoluciones anteriores preservando texto y aptitud conocida; condición, responsabilidad o resolución no demostradas quedan con evaluación pendiente, sin deducir culpa ni reponer stock. Versionar políticas configurables por empresa para operaciones nuevas sin recalcular históricos. SQLite/IndexedDB agregan metadatos comerciales y referencia opaca con migración que preserva colas y lápidas; no persistir PAN/CVC, PaymentMethod, client_secret ni credenciales. Ensayar solo después en copias aisladas.
## Validación/recuperación

Ensayar upgrade en base aislada, copia restaurada y regresión de funciones previas; comparar conteos/IDs, sumas de pagos/saldo/reembolsos, stock por origen y pendientes. Detectar y detenerse ante violaciones. Rollback de app no puede olvidar pagos ya procesados: mantener columnas/tablas nuevas y compatibilidad mientras se concilian; preferir corrección hacia delante cuando exista nueva actividad financiera. Downgrade destructivo requiere estrategia separada, no se autoriza aquí.
