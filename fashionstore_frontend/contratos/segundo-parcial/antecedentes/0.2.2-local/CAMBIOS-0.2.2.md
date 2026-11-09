# Cambios de revisión documental 0.2.2 — 25/10/2026

El propietario aprobó la decisión **C34** para CU04: la referencia horaria emitida en un acceso online permite crear solicitudes offline durante ocho horas, con cinco minutos de tolerancia de desfase. El plazo de la solicitud sigue siendo 24 horas desde su creación local original. Puede sincronizarse después de caducar la referencia, si se creó dentro de su ventana y llega antes de vencer la solicitud; requiere autenticación central al enviar. Obtener otra referencia no reinicia las ocho horas privadas desde el último login online.

Se actualizaron `reglas-aprobadas.md`, `integracion.md`, `payloads.md`, la aclaración de la ficha CU04 y las instrucciones específicas de cada repositorio. `interfaz.json` continúa en 0.2.0 y `version_esquema=1`: no cambian campos, identificadores, estados, códigos ni rutas propuestas. Los clientes conservan operaciones pendientes. La tolerancia de reloj no demuestra físicamente la hora de creación en un dispositivo desconectado; una fecha incoherente genera `CONFLICTO/TIEMPO_INCOHERENTE` durable sin apartado.

Esta actualización documental no demuestra implementación ni pruebas funcionales. Las migraciones y servicios se revisan por separado antes de cualquier cambio en la base activa o publicación.

## Resolución de bloqueos de aceptación del Bloque B (25/10/2026)

- **1. Catálogo unificado y compatibilidad sin romper clientes:**
  - `GET /productos` y `GET /productos/{id}` no quedan reservados exclusivamente al administrador: los clientes actuales y llamadas públicas sin sesión reciben `ProductoPublicoDTO` (sin `proveedor_principal_id`, `costo_estandar` ni `margen_contribucion_minimo`).
  - Las llamadas con rol administrativo empresarial reciben `ProductoDTO` con sus campos internos acotados a la empresa de la sesión.
  - `GET /variantes` y `GET /variantes/{id}` devuelven `VariantePublicaDTO` (sin `costo_promedio` ni `costo_ultimo`) para llamadas públicas. Para administradores se conserva `VarianteDTO`.
  - `GET /variantes/{id}/disponibilidad` aísla estrictamente las sucursales devueltas a aquellas pertenecientes a la empresa de la variante.
  - Compatibilidad de solo lectura: para llamadas antiguas que no envían empresa (clientes actuales de Angular y Flutter), se resuelve la empresa activa única del sistema en modo lectura sin mezclar catálogos y sin permitir contexto implícito para ninguna operación de escritura.

- **2. Validación de visita al sincronizar solicitudes offline:**
  - Al sincronizar, la fecha de visita (`visita_en`) debe ser estrictamente posterior a la hora de recepción del servidor (`visita > ahora`) y estar dentro de las 24 horas contadas desde la creación local original (`origen_plazo`).
  - Si la visita ya transcurrió durante el período de desconexión o no cumple la ventana, la solicitud se rechaza de forma durable persistiendo `CONFLICTO/TIEMPO_INCOHERENTE` con el detalle explicativo para que el cliente la corrija, sin crear reserva, sin apartar stock y sin generar movimientos en el Kardex.
  - Se conserva íntegra la decisión C34: referencia horaria de 8 horas, tolerancia de desfase de 5 minutos y sincronización posterior válida de solicitudes creadas a tiempo dentro de sus 24 horas.

- **3. Política real de capacidad del plan:**
  - Se implementó `PlanService.validar_capacidad` consultando directamente las tablas reales `organizacion.planes` y `organizacion.suscripciones` existentes, con una interfaz común y desacoplada adoptable por el Bloque A.
  - Aplica fechas manuales en UTC y el período de 3 días de gracia continua (72 h): durante la gracia el servicio de reserva continúa; tras la gracia se bloquean nuevas reservas, permitiendo el cierre de compromisos ya aceptados.
  - La empresa se obtiene siempre de la sesión autenticada en el servidor (nunca del cuerpo como autoridad).
  - Para creación online bloqueada: devuelve HTTP 403 Forbidden con detalle `PLAN_NO_HABILITADO` coherente.
  - Para solicitud offline bloqueada: persiste el resultado durable `RECHAZADA/PLAN_NO_HABILITADO` sin reserva, apartado ni Kardex.
