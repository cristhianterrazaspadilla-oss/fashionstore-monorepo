# Prompt para agente integrador — cierre técnico integral de E1 con subagentes

Fecha: 04/11/2026. Contrato vigente: 0.3.2 / protocolo 0.4.0. Alcance: los 14 CU de E1. Este documento es un encargo de implementación, no una aceptación.

## Objetivo y fuentes

Termina la implementación de **CU01, CU02, CU03, CU04, CU06, CU07, CU12, CU13, CU14, CU15, CU16, CU17, CU18 y CU26** en todos sus canales contractuales: FastAPI, Angular/PWA y Flutter solo donde corresponde según `backend/seguimiento/segundo-parcial/06-canales-y-cierre-movil.md`. No trabajes E2. La auditoría de partida es `backend/seguimiento/segundo-parcial/07-auditoria-entrega-integral-e1.md`; el estado vivo está en `02-estado-cu.md`. Lee además `AGENTS.md`, `01-alcance-y-orden.md`, `03-ramas-y-commits.md`, las 14 fichas `backend/contratos/segundo-parcial/casos/CUxx.md`, los contratos transversales y los skills pertinentes. **CU17 vigente es Kardex**; la mención a Decart/CU17 en AGENTS.md usa numeración histórica y no corresponde al Kardex.

## Delegación obligatoria

**Crea y usa subagentes reales.** Como integrador, define de inmediato propiedad de archivos y una interfaz compartida de DTO/rutas/estados. Distribuye al menos estos frentes; si hay límite de concurrencia, escalónalos sin perder el trabajo paralelo independiente:

1. **Backend caja e inventario:** CU06/CU07, seguridad, turnos, cupos, venta, conciliación, Kardex y pruebas negativas/concurrentes. Propiedad principal: `backend/app/core/modules/ventas_pagos/{routers/cajas.py,services/caja_service.py}` y tests de caja.
2. **Backend restante E1:** CU02/CU12/CU15/CU26 y regresión CU03/04/16/17/18; historial de suscripciones/tasas, límites, scheduler, OpenAPI y pruebas. Propiedad principal: paquetes `identidad_empresas`, `organizacion`, `reservas_traslados`, `catalogo` e `inventario`, excepto archivos de caja.
3. **Angular/PWA:** integración de caja, almacenamiento local durable, privacidad, formularios, roles, textos y responsive; pruebas de integración contra DTO reales. Propiedad principal: `frontend-web`.
4. **Flutter:** E1-M, priorizando caja offline CU06/CU07 con SQLite y pantallas reales, luego consumo de CU02/CU12/CU15/CU26 y regresión de CU03/04/13/16/18. Propiedad principal: `app-movil`.

El integrador es dueño exclusivo de archivos compartidos (`backend/app/api/v1/api.py`, schemas/models comunes, migraciones Alembic, OpenAPI y seguimiento). Los subagentes proponen cambios a esos archivos al integrador; no deben editar simultáneamente el mismo archivo. Coordina interfaces antes de integrar frontend/móvil y revisa personalmente cada entrega de subagente. No aceptes un informe de subagente sin inspeccionar su diff y ejecutar sus pruebas relevantes.

## Bloqueos que debes resolver

### CU06/CU07 — puerta crítica

- Angular genera `dispositivo_id` como `disp-...`, pero FastAPI exige UUID. Unifica el formato, migra IDs locales antiguos sin perder un turno pendiente y prueba apertura real PWA→API; el DTO actual rechaza ese valor con `uuid_parsing`/422.
- Autoriza todas las mutaciones de caja en backend por **rol y ámbito**: cajero/administrador empresarial permitido, cliente y personal ajeno rechazados. Al habilitar, valida empresa, sucursal, caja/dispositivo, plan operativo y turno incompatible. Dos cajas no reciben la última unidad. La vigencia es de 8 h, sin liberar cupos por timeout.
- Al sincronizar venta, valida contra la habilitación original y su snapshot: turno/empresa/dispositivo/actor, estado, instante local de cobro y entrega dentro de la autorización, secuencia y UUID, versión de precios/promociones, cantidades, precio por línea, total, efectivo recibido y cambio. Recalcula importes en servidor con Decimal; no confíes en importes enviados por el cliente. Una venta válida anterior se concilia aunque luego venza el plan o se revoque el usuario, conforme al contrato; una venta nueva fuera del turno se rechaza. Mantén resultado durable de reintento y exactamente un pago, venta, consumo y movimiento Kardex.
- El cierre debe determinar pendientes y cupos desde datos centrales y evidencia de sincronización, no solo desde `operaciones_pendientes` declarado por el cliente. El cierre/recuperación supervisados exigen permiso y no borran ventas cobradas pendientes. Caja perdida no libera stock por simple timeout.
- En PWA, sustituye escrituras `localStorage` separadas y errores silenciados por persistencia transaccional durable (IndexedDB o solución contractual equivalente) de turno, cupo, venta, efectivo, entrega, UUID y comprobante. Si falla el almacenamiento, **no declares venta/entrega completada**; informa al cajero y conserva estado recuperable. Reintento de red usa el mismo UUID. Prueba reinicio, almacenamiento lleno y envío repetido.
- En Flutter, el `CajaService` actual solo usa `_turnoActivoMemoria`/`_colaVentasMemoria`, y `_storage` está sin uso. Implementa persistencia SQLite transaccional, restauración tras matar/reabrir la app y aislamiento por empresa/usuario/dispositivo. Conecta el servicio a una pantalla y navegación accesibles para cajero autorizado: habilitar, vender/entregar sin red, comprobante, pendientes, sincronizar, cerrar y recuperar. Prueba el flujo desde UI y no solo instanciando el servicio.

### CU02/CU12 — historial

- `SuscripcionService.asignar_o_renovar` y `TasaCambioService.crear_tasa` ejecutan `DELETE` de versiones futuras solapadas. Conserva trazabilidad/versiones mediante transiciones o cancelación auditada sin borrar registros. Mantén restricciones de no solapamiento, revisión, idempotencia y concurrencia. Demuestra que una tasa o plan posterior no altera cotizaciones, pagos, tarifas ni hechos históricos ya aceptados. No inventes tasa BOB/USD ni fechas de suscripción heredada. Flutter debe consumir capacidades/tasa vigente desde flujos cliente reales cuando corresponde.

### Resto de E1 — cierre por contrato

- Revalida CU01/CU14 con flujos reales de plataforma y empresa, replay idempotente, revisión concurrente, último administrador y permisos cruzados. Verifica que CU13 oculte datos privados al vencer las 8 h en una vista abierta y mantenga colas aisladas en PWA y Flutter.
- Para CU03/CU16, comprueba snapshot por empresa, versión/fecha/fuente, filtros, descarga atómica y reinicio sin red en IndexedDB y SQLite. Para CU04/CU18, comprueba reloj `America/La_Paz`, UUID estable, reserva online/offline, origen 24/72 h, adelanto, cancelación, reintentos y carrera de stock. CU15 exige sucursales/tarifas propias, límites 2/10 bajo concurrencia y consulta móvil real. CU17 exige saldos físico/reservado/cupo/libre, costos históricos y movimientos únicos. CU26 exige expiración reentrante y evidencia del scheduler en ejecución: el `.env` local lo habilita, pero la auditoría no observó un ciclo periódico completo.
- Sustituye textos técnicos visibles en inventario/recepciones (`saldo_fisico`, `fecha_hora`, `RECEPCION_PROVEEDOR`, etc.) por lenguaje del usuario sin perder precisión funcional. Revisa estados de carga/error/vacío, teclado, foco y los anchos 360, 390, 440, 768, 1024 y 1440 px.

## Base, ramas y pruebas

- Preserva todos los cambios sin commit de `backend`, `frontend-web` y `app-movil`. No hagas reset, clean, stash automático, commit, push, merge ni despliegue. Los lotes B2–B5 están mezclados en `feature/sp2-e1-b1-identidad`; Flutter está en `refactor/paquetes-cu`. No cambies de rama transportando cambios sin seguimiento. Documenta archivos por lote para separar commits **después de la revisión del propietario**.
- La base local está en Alembic `0011_sucursales_revision_sp2`. Si necesitas migrar, crea revisión incremental, respalda datos, ensaya en copia `_test` restaurada y valida migración/datos. Aplica al PostgreSQL local solo tras prueba aislada exitosa y conforme a la autorización anterior del propietario. No reconstruyas ni trunques `fashionstore_db`. Registra versión, SQL aplicable y consultas de comprobación.
- Añade pruebas de comportamiento que fallen con el código auditado: cliente intentando abrir caja, PWA `dispositivo_id`, plan vencido, turno cerrado/vencido, precio/total/efectivo adulterados, cierre que oculta pendientes, reenvío del mismo UUID, recuperación tras reinicio PWA/Flutter, error de almacenamiento, historial de plan/tasa y carrera entre cajas. Prueba también flujos positivos completos.
- Ejecuta tras cada frente pruebas focalizadas y al final: backend `tests_segundo_parcial_bloque_b` más regresiones relevantes; OpenAPI real; Angular TypeScript, build, tests con launcher configurado; Flutter `analyze` y `test`. Investiga por qué `flutter test` no terminó en la auditoría independiente (dos intentos sin salida) y deja comando, salida y causa. Pruebas finales Android físico si hay dispositivo; si no, indica exactamente qué escenario queda sin ejecutar y no lo llames verificado.

## Entrega del integrador

No te detengas tras corregir solo CU06/CU07: termina el alcance E1 que pueda resolverse con el repositorio y las herramientas disponibles. Actualiza `02-estado-cu.md`, `04-bitacora.md` y `05-reanudacion.md` con una matriz de los 14 CU por canal B/W/M, archivos, pruebas ejecutadas, resultados, migraciones, ramas y pendientes. Separa «código implementado», «prueba automática pasada», «prueba manual pendiente» y «aceptación». No marques ningún CU «Aceptado» por tu cuenta; la revisión final y los commits corresponden al propietario y a Codex después de inspeccionar la entrega.
