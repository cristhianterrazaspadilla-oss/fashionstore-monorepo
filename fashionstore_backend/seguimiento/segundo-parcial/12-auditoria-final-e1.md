# Auditoría final independiente E1 — 04/11/2026

## Veredicto

La entrega mejoró los cinco puntos de la revisión 10, pero **E1 no puede marcarse cerrada ni iniciar E2 bajo la puerta de cierre de `06-canales-y-cierre-movil.md`**. CU06, CU07 y CU17 siguen observados por el ciclo de vida de cupos y su trazabilidad. Las suites automatizadas que se pudieron repetir pasan; no sustituyen los escenarios operativos descritos abajo.

## Verificación repetida

- PostgreSQL: restauración de `local-backups/fashionstore_db_0009_completa.sql` en una copia aislada, migraciones 0010→0012 y `tests_segundo_parcial_bloque_b -q --tb=line --disable-warnings`: **118 passed, 6 warnings, 94.92 s**. La copia se eliminó. `alembic current` en la base principal sigue en **0011**, por lo que el backend nuevo no está listo para operar contra ella. No se aplicó 0012 a la base principal durante esta auditoría.
- Angular: `npm.cmd test -- --watch=false --progress=false`: **198/198**; build de producción y `tsc -p tsconfig.app.json --noEmit`: correctos.
- Flutter: `flutter analyze`: sin problemas. `flutter test test/widget_test.dart` no produjo resultado y se interrumpió. Los **194 tests Flutter** del agente permanecen como reporte externo, sin repetición independiente en esta sesión. No se ensayó Android físico ni los seis anchos PWA manualmente.
- `git diff --check` sale 0 en los tres repositorios. Ramas/SHA sin commits nuevos: backend `feature/sp2-e1-b1-identidad`/`f8f4f71`, Angular `feature/sp2-e1-b1-identidad`/`245f22e`, Flutter `refactor/paquetes-cu`/`92aa79d`.

## Bloqueos que impiden el cierre

1. **CU06/CU07, conciliación sin salida en ambos clientes.** `CajaService.cerrar_turno` envía a `CONCILIACION` todo turno sin ventas centrales que tenga cupos, incluso si el cajero no cobró ninguna venta. Flutter y Angular solo ofrecen cierre ordinario y recuperación; no tienen flujo de resolución supervisada con `supervision_forzada`, `descarte_venta_fisica`, evidencia y arqueo. Un turno normal sin ventas no puede devolver sus cupos desde las interfaces. Añadir el flujo supervisado y probar turno vacío, venta pendiente, conteo físico, descarte y devolución de cupos.
2. **CU07, cierre provisional deja stock retenido en estado final.** Con `supervision_forzada=true` y `descarte_venta_fisica=false`, `cerrar_turno` marca `CERRADO` y deja cupos en `comprometido_caja`. La venta tardía puede consumir parte de esos cupos, pero `cerrar_turno` rechaza cualquier siguiente cierre por estar `CERRADO`; no hay ruta explícita de resolución del remanente. `recuperar_turno` tampoco valida el estado previo y podría cambiar un `CERRADO` a `RECUPERACION` de forma indirecta, sobrescribiendo datos de auditoría. Mantener un estado resoluble hasta conciliación final o crear una transición supervisada, auditada e idempotente para liberar solo el remanente físico comprobado.
3. **CU07, descarte físico sin evidencia obligatoria.** Un supervisor puede enviar `descarte_venta_fisica=true` y solo un motivo de tres caracteres; `evidencia_cierre`, `ajustes_inventario` y arqueo son opcionales. El backend libera todos los cupos remanentes aunque no se haya registrado conteo por variante. Esto puede convertir en stock libre una prenda entregada y afectar CU16/CU17 y ventas posteriores. Exigir y validar el acta/conteo físico por variante antes de liberar, con prueba de datos incompletos y discrepancias.
4. **CU17, cupos sin movimiento de Kardex al asignar o liberar.** `CajaService.habilitar_turno` cambia `disponible` y `comprometido_caja`, y `cerrar_turno` revierte esos campos al liberar, pero ninguno registra `MovimientoInventario`; únicamente la venta sincronizada lo hace. El skill obligatorio `fashionstore-ciclo-2` exige Kardex para cada transición de inventario, y CU17 exige movimientos trazables por documento origen. Registrar asignación y devolución de cupos con referencias e idempotencia; probar que no se dupliquen durante reintentos o cierres.

## Siguiente puerta

Corregir los cuatro bloqueos y añadir pruebas integradas PWA/API y Flutter/API de apertura → venta offline → reconexión → cierre/conciliación. Repetir backend en copia migrada y suites web/móvil. Solo después aplicar la migración 0012 a `fashionstore_db`, verificarla, revisar y registrar commits por lote, y considerar la aceptación formal de los 14 CU. E2 debe permanecer pendiente hasta ese momento. Los ensayos manuales PWA y Android físico siguen como evidencia de aceptación pendiente.
