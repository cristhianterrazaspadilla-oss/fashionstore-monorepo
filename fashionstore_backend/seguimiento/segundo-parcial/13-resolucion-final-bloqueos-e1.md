# Resolución técnica de bloqueos E1 — CU06, CU07 y CU17

**Fecha:** 04/11/2026
**Contrato:** 0.3.2 / protocolo 0.4.0
**Estado:** Los defectos técnicos de la auditoría 12 quedaron corregidos y la suite backend del segundo parcial pasó. E1 sigue **pendiente de aceptación formal**: la prueba widget Flutter de conciliación no pudo confirmarse en esta sesión y faltan las verificaciones manuales en PWA y Android físico.

Este documento es la actualización vigente de [la auditoría final 12](12-auditoria-final-e1.md). Las observaciones 1–4 de aquella auditoría están resueltas en código y migración; las limitaciones de verificación indicadas aquí siguen abiertas.

## Cambios realizados

1. **Conciliación supervisada en Angular/PWA y Flutter:** el supervisor puede registrar motivo, referencia de acta, efectivo contado, conteo físico por cada variante y resolución explícita del faltante. Las ventas locales aún no sincronizadas bloquean la resolución final en ambos clientes. Tras una conciliación parcial, el cliente vuelve a consultar los cupos autoritativos del backend.
2. **Cierre y estados de inventario:** un cierre ordinario con cupos remanentes pasa a `CONCILIACION` y mantiene las unidades en `comprometido_caja`. La supervisión valida rol, acta, conteo exacto de variantes y arqueo antes de mutar stock. Las unidades encontradas vuelven a disponibilidad; `PENDIENTE_SINCRONIZACION` conserva compromiso para aceptar una venta tardía; `MERMA` consume el compromiso, aumenta `mermado` y registra un movimiento `MERMA`. No se confía en `descarte_venta_fisica` como autorización global.
3. **Cierre provisional y auditoría:** los turnos con remanentes permanecen en conciliación y admiten sincronizar ventas tardías. Cada decisión genera un evento por revisión en `comercial.turnos_caja_eventos`. La respuesta `cupos_devueltos` incluye unidades realmente devueltas o mermadas; los pendientes permanecen en `cupos_retenidos`.
4. **Kardex y costo:** la apertura, devolución y merma de cupos registran `COMPROMISO_CAJA`, `LIBERACION_CUPO_CAJA` y `MERMA` con idempotencia. Cada `CupoCaja` conserva `costo_unitario_snapshot` tomado de `VarianteProducto.costo_promedio` al habilitar el turno, por lo que cambios posteriores del catálogo no alteran el costo histórico.
5. **Contrato:** `openapi-segundo-parcial.json` se regeneró desde `app.openapi()` para incorporar `mermado`, `evento_id` y el estado nullable de `cerrado_en`. La comparación estructural entre la exportación y el OpenAPI actual da igualdad.

## Migración de PostgreSQL

La base local de desarrollo `fashionstore_db` está en PostgreSQL `127.0.0.1:5432`; no es un archivo `.db` extraíble. Se aplicaron las migraciones `0012_cierre_turno_supervision` y `0013_cupo_merma_eventos_kardex` con `alembic upgrade head` después de validarlas en una copia aislada.

Verificación posterior en la base local:

- `alembic_version = 0013_cupo_merma_eventos_kardex`.
- `inventario.cupos_caja` contiene `mermado` y `costo_unitario_snapshot`.
- No hay `costo_unitario_snapshot IS NULL`.
- Existe `comercial.turnos_caja_eventos`.
- `movimientos_inventario_tipo_check` incluye los dos tipos nuevos de cupos y conserva los tipos anteriores.

## Verificación automatizada

- **Backend focalizado CU06/CU07:** 22 passed, 1 warning. Base temporal creada desde `local-backups/fashionstore_db_0009_completa.sql`, migrada 0010–0013 y eliminada al terminar.
- **Backend completo `tests_segundo_parcial_bloque_b`:** 122 passed, 5 warnings en 90.18 s, con una copia temporal del mismo respaldo migrada 0010–0013. La base temporal se eliminó.
- **Angular/PWA:** 201/201 pruebas, build de producción y `tsc -p tsconfig.app.json --noEmit` pasaron en la revisión independiente.
- **Flutter:** `flutter analyze` y `dart format` pasaron según verificación del implementador. La prueba dedicada `test/widget/caja_conciliacion_supervisada_test.dart` se intentó con `flutter test --no-pub test/widget/caja_conciliacion_supervisada_test.dart --reporter expanded --concurrency=1 --verbose`; tras más de un minuto, el log temporal permaneció vacío y no había procesos Flutter/Dart activos. Se interrumpió, así que no se registra como aprobada hasta repetirla con resultado observable.
- **OpenAPI:** exportación igual a `app.openapi()`; la suite completa anterior incluyó el test de contrato.
- **Git:** `git diff --check` terminó con código 0 en backend, frontend y móvil (Git reportó advertencias de normalización LF/CRLF, sin errores de whitespace).

## Pendiente antes de aceptar E1

1. Obtener resultado verificable del test widget Flutter de conciliación y de las suites móviles pertinentes.
2. Hacer recorrido manual de conciliación PWA y Flutter/Android físico, incluyendo: caja sin ventas, venta sincronizada con remanente físico, venta pendiente, merma y reintento/cierre final.
3. Inspeccionar los diffs por lote y registrar commits en las ramas existentes solo después de la revisión indicada en `03-ramas-y-commits.md`.
4. El propietario debe dar aceptación formal de los 14 CU. Hasta entonces CU06/CU07/CU17 permanecen observados para aceptación y E2 no empieza.

## Ramas y continuidad

- `backend`: `feature/sp2-e1-b1-identidad`, HEAD `f8f4f71`.
- `frontend-web`: `feature/sp2-e1-b1-identidad`, HEAD `245f22e`.
- `app-movil`: `refactor/paquetes-cu`, HEAD `92aa79d`.
- No se crearon commits, no se hizo push ni merge. Los cambios siguen locales y deben preservarse.
- Siguiente paso: completar la verificación Flutter y las pruebas manuales; actualizar este seguimiento antes de declarar aceptada E1.
