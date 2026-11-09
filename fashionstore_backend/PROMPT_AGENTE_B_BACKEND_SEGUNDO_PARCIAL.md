# Encargo para agente — backend, CU03/CU04/CU16/CU18

Implementa **solo el backend** de mi bloque B de la primera presentación del segundo parcial de FashionStore: CU03 Descargar catálogo para consulta offline, CU04 Registrar reserva offline, CU16 Consultar catálogo de prendas y CU18 Gestionar reservas de prendas. Trabaja en la rama local `feature/segundo-parcial-bloque-b`, creada desde `main` con los cambios pendientes preservados. Yo revisaré tu código y haré pruebas manuales antes de cualquier commit. El otro programador es dueño de CU01/CU02/CU13/CU15 (empresa, plan, sesión y sucursales).

## Fuentes obligatorias

1. Lee `AGENTS.md` del workspace, el skill `fashionstore-ciclo-2` y `docu_general/plan-implementacion-ciclo-2-backend.md` si están disponibles en tu entorno. Para CU18 prevalecen las reglas de 24/72 horas exactas desde el origen nuevo acordado en el contrato 0.2.2.
2. Lee completos los archivos pertinentes de `contratos/segundo-parcial/`: `primera-presentacion.md`, `casos-de-uso.md`, `trazabilidad-cu.md`, `reglas-aprobadas.md`, `backend.md`, `interfaz.json`, `payloads.md`, `integracion.md`, `paquetes-cu.md`, `plan-migracion-db.md` y `equivalencias-cu.md` y `CAMBIOS-0.2.2.md`. Esta carpeta es autosuficiente; no interpretes el número académico como ruta o ID técnico.
3. Lee `alembic/SEGUNDO_PARCIAL_0006_0007.md` y las revisiones `0006_empresas_planes` y `0007_reservas_offline`. Ya hay modelos/migraciones **sin commit** en el workspace; conserva esos cambios. La base activa `fashionstore_db` continúa en `0005`; la base aislada actual para ensayar es `fashionstore_sp2_ensayo_20261025_revisado`, en `0007`.
4. Revisa código real antes de cambiarlo: `app/core/modules/catalogo/`, `reservas_traslados/`, `inventario/`, `ventas_pagos/services/pago_service.py`, `app/core/dependencias.py` y `app/api/v1/api.py`. Mantén los casos antiguos y sus rutas. Nombra en **español** cualquier método o función nueva, salvo funciones exigidas por un framework.

## Coordinación con bloque A

Obtén del programador A un contrato de integración para: empresa ligada a la sesión, empresa pública por código, autorización de sucursal/recurso y política de plan para nuevas reservas, además de rol de aplicación/RLS. No confíes en `empresa_id` del cuerpo. No introduzcas un valor por defecto que escriba futuras operaciones en la empresa heredada. Puedes avanzar en DTO, lectura pública, repositorios y pruebas aisladas mientras A termina, pero marca como pendiente una integración real, sin stubs que aparenten seguridad. Coordina cualquier edición simultánea de `app/api/v1/api.py`, dependencias y servicios compartidos.

## Trabajo requerido

### CU03/CU16

- Filtra catálogo, filtros, detalle y disponibilidad por empresa/sucursal. No expongas costos, márgenes, proveedores privados ni datos de otra empresa en la descarga pública. Conserva la consulta online existente y su comportamiento de filtros.
- Implementa `GET /api/v1/catalogo/descarga` como instantánea coherente y tipada: empresa/código, ámbito de sucursal, versión y fecha UTC, producto/variante, precio BOB en cadena decimal, talla/color y disponibilidad pública conocida. Consultar nunca aparta stock. El frontend debe poder conservar una copia completa tras reinicio; no necesita información privada.
- Publica el DTO y ejemplos en el OpenAPI real. El enlace `/tienda/{empresa_codigo}` es navegación Angular propuesta; no lo trates como autorización API.

### CU18

- Adapta `ReservaService.crear`, consulta, listado, búsqueda por código, cancelación, adelanto en `PagoService` y expiración: empresa y actor autorizados en cada ruta, incluida la recuperación de claves idempotentes. Mantén traslados y estados por línea previos.
- Reserva online nueva: `origen_plazo_en` = creación central, `vence_en` = origen +24 h, aunque haya visita. Reserva offline aceptada desde CU04: origen = creación local original validada, `vence_en` = origen +24 h. Un adelanto confirmado **antes** de vencer extiende a origen +72 h, no 72 h adicionales. Visita, recepción, reintento y aviso no reinician plazo. Históricos con origen nulo conservan `vence_en` sin recálculo.
- Conserva bloqueo de inventario ordenado `(sucursal_id,variante_id)`, una sola transacción de servicio, Kardex por efecto y liberación única en cancelación/expiración. No insertes movimientos por simple lectura o rechazo.

### CU04

- Implementa `GET /api/v1/sincronizacion/referencia-horaria`, `POST /api/v1/sincronizacion/operaciones` (una operación por solicitud) y `GET /api/v1/sincronizacion/operaciones/{operacion_id}`. En esta entrega procesa únicamente `tipo=SOLICITAR_RESERVA`; `SOLICITAR_COMPRA` y `REGISTRAR_VENTA_CAJA` son posteriores.
- Usa el envoltorio exacto de `interfaz.json` versión 1. Valida sesión/empresa/propietario antes de buscar un UUID previo. Hashea de modo canónico todos los campos inmutables; mismo actor/empresa/UUID/cuerpo devuelve respuesta persistida, cuerpo diferente da 409 `OPERACION_MODIFICADA`, GET ajeno da 404. Un corte de red no implica rechazo comercial.
- Comprueba referencia horaria, coherencia de creación local, visita y recepción. **C34 aprobado:** referencia válida para crear solicitudes durante 8 h desde su emisión en el acceso online, con 5 min de tolerancia de desfase. Emitir otra referencia no amplía las 8 h de privacidad local desde el último login online. Permite sincronizar más tarde con sesión revalidada si la fecha original se creó dentro de la referencia y no venció su plazo de 24 h; el vencimiento de la referencia al sincronizar no reinicia ni rechaza por sí mismo la solicitud. El servidor no puede probar físicamente la hora de creación offline. Si el tiempo es incoherente, registra resultado durable `CONFLICTO/TIEMPO_INCOHERENTE`. Si llega tras `creada_local_en + 24 h`, registra `RECHAZADA/SOLICITUD_VENCIDA` sin stock. Si falta stock central en la sucursal elegida, `RECHAZADA/SIN_STOCK`, sin traslado automático y sin cobro. El cuerpo CU04 no incluye sucursal de origen de traslado.
- Una aceptación crea operación, reserva, líneas, apartado/Kardex y resultado consultable en una única transacción, reutilizando la lógica de CU18. Un error técnico hace rollback; un rechazo comercial se persiste sin efectos. La respuesta aceptada incluye `recurso_id`, `aceptada_en` y `vence_en`; rechazos/conflictos comerciales usan HTTP 200 con estado/código; las fallas de autorización y los UUID modificados usan sus códigos HTTP acordados.

## Pruebas y evidencia de entrega

Ejecuta pruebas automáticas significativas con reloj inyectable y dos empresas en una **base restaurada independiente**, sin alterar `fashionstore_db`: aislamiento en listados/IDs/código/SKU/operación, descarga pública sin datos privados, visita distinta del origen, plazo exacto 24/72 h, solicitud vencida o tiempo incoherente, reintento igual y alterado, respuesta perdida, disputa por última unidad, multiítem con rollback, adelanto oportuno/tardío, cancelación/expiración repetida y regresión de rutas anteriores. Verifica modelos, OpenAPI, `python -m compileall`, pruebas relevantes y `git diff --check`. Reporta expresamente si la integración con A o RLS aún impide un escenario.

Entrega al terminar: resumen de cambios por CU, lista de archivos, ejemplos reales de petición/respuesta de la API, pruebas ejecutadas con resultados, diferencias pendientes contra contratos, dependencias concretas del bloque A, nombre de la base de ensayo y pasos de prueba manual para el propietario. No declare terminado un CU que dependa de stubs o de un plan inexistente.

**Restricción obligatoria:** permanece en `feature/segundo-parcial-bloque-b`; no hagas commit, push, merge, migración de `fashionstore_db` ni carga a GitHub. Mantén los cambios locales para mi revisión y mi OK explícito posterior. No incluyas dumps, `.env` ni secretos en el repositorio.
