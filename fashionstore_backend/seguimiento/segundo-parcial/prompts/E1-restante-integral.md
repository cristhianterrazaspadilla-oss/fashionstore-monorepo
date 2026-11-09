# Prompt para agente externo — completar entrega 1 (14 CU)

Fecha de preparación: 04/11/2026. Alcance: contrato 0.3.2 / protocolo 0.4.0.

## Encargo

Completa **toda la primera entrega** de FashionStore: CU01, CU02, CU03, CU04, CU06, CU07, CU12, CU13, CU14, CU15, CU16, CU17, CU18 y CU26. Implementa primero backend FastAPI y Angular/PWA; completa Flutter al final, solo para los CU y consumos móviles indicados en `backend/seguimiento/segundo-parcial/06-canales-y-cierre-movil.md`. CU06 y CU07 **sí** incluyen caja Flutter. No implementes los 13 CU de la segunda entrega.

Lee `AGENTS.md`, `backend/seguimiento/segundo-parcial/{README.md,01-alcance-y-orden.md,02-estado-cu.md,03-ramas-y-commits.md,04-bitacora.md,05-reanudacion.md,06-canales-y-cierre-movil.md}`, `backend/contratos/segundo-parcial/version.json`, cada ficha `casos/CUxx.md` afectada y los contratos transversales. Aplica los skills pertinentes de AGENTS.md. **Atención a la numeración:** CU17 del contrato vigente de segundo parcial es Kardex; la instrucción Decart de AGENTS.md se refiere al CU17 histórico de probador virtual y no aplica a esta tarea de Kardex. El archivo `docu_general/plan-implementacion-ciclo-2-backend.md` citado allí no estaba en la ruta indicada al preparar este prompt: búscalo una vez; si continúa ausente, registra ese hecho y sigue con las fichas vigentes y fuentes funcionales existentes, sin inventar reglas.

## Forma de trabajo para avanzar sin pausas entre lotes

1. Revisa `git status`, rama y HEAD de `backend`, `frontend-web` y `app-movil`; conserva todos los cambios locales. No hagas `reset`, `clean`, `stash` automático, commit, push, merge ni despliegue. No cambies de rama transportando cambios sin seguimiento. Mantén separados en la bitácora los archivos y resultados de cada lote, de modo que la revisión posterior pueda preparar commits coherentes por repositorio y rama.
2. Resuelve los lotes E1-B1 a E1-B5 **en ese orden por dependencias**, sin esperar un nuevo prompt entre ellos. Haz pruebas focalizadas al cerrar cada lote y ejecuta la regresión acumulada antes de pasar al siguiente. Si una decisión externa realmente impide una parte, documenta la pregunta precisa y continúa con las tareas independientes.
3. Para cambios de esquema, crea migraciones Alembic incrementales desde la revisión real (0010 al último corte). Prueba restauración y migración sobre una copia aislada de PostgreSQL con sufijo `_test`, sin pérdida de datos existentes. La autorización anterior del propietario permite aplicar migraciones a su PostgreSQL local: hazlo solo después de respaldo verificado y pruebas aisladas exitosas; documenta versión, consulta de comprobación y ruta del SQL funcional para pgAdmin. Nunca borres/reconstruyas `fashionstore_db`.
4. No marques un CU «Aceptado» por tu cuenta. Actualiza `02-estado-cu.md` con el avance real por canal y agrega a `04-bitacora.md` pruebas, ramas, migraciones, limitaciones y siguiente paso. La aceptación y los commits se decidirán tras revisión independiente.

## E1-B1 — cerrar observaciones CU01, CU13, CU14

- **CU01:** exige `Idempotency-Key` en `POST /empresas`; conserva la misma clave y payload durante reintentos PWA, incluso tras timeout. Prueba replay, cambio de payload y carrera. `require_administrador_plataforma` debe validar rol **y** ámbito global (`empresa_id` nulo), incluido `ADMINISTRADOR_SISTEMA`/`ADMINISTRADOR_PLATAFORMA`; un usuario empresarial con esos nombres de rol debe recibir 403. Conserva razón social/nombre comercial y filtro del listado público.
- **CU13:** oculta datos privados PWA exactamente al vencer las 8 h aunque la vista permanezca abierta, sin borrar la cola offline. Prueba con reloj controlado, logout, cambio de empresa, token vencido y reautenticación antes de sincronizar. Conserva el registro con empresa explícita y claims de sesión validados en servidor.
- **CU14:** `revision` debe ser obligatoria para la mutación contractual; compara y aumenta de forma atómica bajo concurrencia del **mismo** usuario, devolviendo 409 al perdedor. Las rutas heredadas deben usar una revisión vigente de forma segura o documentarse como adaptadores compatibles sin omitir el control. El historial/outbox debe escribirse en la misma transacción; elimina `except Exception: pass` y prueba rollback si falla el evento. Conserva validación de sucursal propia y protección concurrente del último administrador.

## E1-B2 — CU02 y CU15

- Implementa asignación, renovación, consulta de plan/capacidades, revisiones, historial y gracia de 72 h. Básico admite 2 sucursales activas, Profesional 10; ambos permiten offline. Tras gracia bloquea **nuevas** ventas, reservas y turnos, pero permite consultar y conciliar operaciones válidas previas. No inventes fechas de suscripción para la empresa heredada.
- Ciudades son globales y solo la plataforma las administra; cada empresa gestiona únicamente sus sucursales y tarifas. Valida importes/anillos, congelación de tarifa en operaciones aceptadas, límites bajo concurrencia y desactivación con compromisos pendientes. Prueba dos empresas y dos activaciones simultáneas de la tercera sucursal en plan Básico.

## E1-B3 — CU16, CU03, CU17 y CU12

- Cierra catálogo online y snapshot offline PWA con aislamiento por empresa, filtros de variante/color, disponibilidad conocida, versión/fecha/fuente; descarga atómica a IndexedDB, reinicio sin red y conservación del snapshot anterior ante interrupción/error. Revisa el avance 0.3.2 existente antes de reemplazarlo.
- Implementa Kardex consultable con físico, reservado, cupo offline y libre, costo histórico, valorización y documento origen. Cada movimiento debe ser único; asignar cupo reduce libre y sincronizar venta de cupo no descuenta dos veces. Conserva los puntos de integración con los CU financieros de E2 sin declararlos implementados.
- Implementa tasa BOB/USD global, versionada, sin vigencias solapadas. Usa Decimal y `ROUND_HALF_UP`; no fijes una tasa ficticia. Congela tasa e importes en la cotización aceptada cuando exista orden de pago, conserva historial y separa el trabajo Stripe/reembolso de E2.

## E1-B4 — CU18, CU26 y CU04

- Completa crear/consultar/cancelar reserva online, pagos de adelanto y disponibilidad por empresa con transacciones, bloqueo de stock e idempotencia. Plazo: 24 h local sin adelanto, 72 h tras adelanto válido; usa `America/La_Paz` para el horario local acordado de CU04 sin confundir hora local con instante UTC persistido.
- Cierra sincronización PWA de reserva offline con UUID estable, referencia horaria auténtica, resultado durable, reintentos/reinicio, rechazo de reserva vencida antes de aceptación central y aislamiento entre empresas. Conserva el avance ya existente CU03/04/16/18.
- Implementa expiración automática por lotes con bloqueo, liberación exactamente una vez, Kardex/eventos y reentrada tras caída. Prueba dos workers y carreras entre pago, cancelación y expiración. La expiración nunca libera cupos de caja ni pedidos digitales.

## E1-B5 — CU06 y CU07

- Implementa backend y caja PWA de turno/habilitación online, cupos exclusivos, snapshot de precios/promociones y vigencia de 8 h. Persistir habilitación local antes de declarar caja lista. Dos cajas concurrentes no pueden recibir la última unidad; turno vencido o caja perdida no libera cupos automáticamente.
- Implementa venta física **en efectivo** y entrega sin internet: cálculo con snapshot autorizado, cupo local transaccional, UUID y comprobante local durables; estado local COBRADA/ENTREGADA con conciliación central pendiente. Al reconectar, registra una vez venta, efectivo, entrega y Kardex sin doble descuento. Cierra turno solo tras conciliar y devuelve únicamente cupo no consumido. Incluye recuperación tras reinicio, reenvío, caja perdida y cierre supervisado. No simules Stripe offline ni adelantes la compra diferida digital de E2.

## E1-M — Flutter al final

Después de estabilizar backend/PWA, completa Flutter para CU03, CU04, CU13, CU16 y CU18 (cliente); CU06 y CU07 (caja de personal); y los consumos móviles de CU02, CU12, CU15 y CU26. Reutiliza la implementación móvil previa y SQLite. Verifica aislamiento por empresa/usuario, ventana privada, reinicio offline, reenvío de UUID y paridad de reglas de caja con PWA. CU01, CU14 y CU17 no requieren pantalla Flutter. No agregues pantallas móviles administrativas generales.

## Puertas finales y reporte

- Ejecuta pruebas de backend sobre copia aislada 0010+migraciones nuevas, incluidos `tests_segundo_parcial_bloque_b`, pagos/adelantos y pruebas nuevas de cada CU; revisa OpenAPI real. En Angular ejecuta TypeScript, build, tests con el launcher configurado y `git diff --check`; verifica UI a 360, 390, 440, 768, 1024 y 1440 px, teclado/foco/errores. En Flutter ejecuta análisis y tests de los flujos modificados; distingue explícitamente lo que requiera dispositivo físico.
- Entrega una tabla de los 14 CU con B/W/M, evidencia de prueba, estado, bloqueos y archivos. Informa migraciones y versión real de DB, rutas/DTO, resultados exactos de comandos, ramas/HEAD y datos de ensayo. No declares completa E1 mientras falte un canal o un criterio contractual.
- Si el trabajo excede una sesión, deja `04-bitacora.md` y `05-reanudacion.md` listos para continuar exactamente desde el siguiente paso; continúa después en la misma secuencia sin volver a implementar lo ya verificado.
