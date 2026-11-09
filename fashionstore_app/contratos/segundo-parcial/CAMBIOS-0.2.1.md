# Cambios de revisión documental 0.2.1 — 25/10/2026

Esta revisión incorpora decisiones aprobadas después de 0.2.0. **No cambia el protocolo de `interfaz.json` (versión 0.2.0), los dos JSON Schema, los campos del comando ni `version_esquema=1`.** Las fichas de los ocho CU prioritarios conservan autor vacío, fecha 24/10/2026, nombres, numeración y reparto A/B. [CAMBIOS-0.2.0.md](CAMBIOS-0.2.0.md) permanece como historial.

## Decisiones cerradas

1. Catálogo público por enlace empresarial de navegación propuesto `/tienda/{empresa_codigo}`: productos, variantes, precios y disponibilidad pública conocida de esa empresa. El enlace no es API implementada ni autorización. El contexto debe conservarse al registro/login y operaciones posteriores sin reutilizar silenciosamente sesión de otra empresa. Pantalla inicial de selección de empresas: mejora opcional posterior.
2. Ciudades globales administradas por plataforma. La empresa consulta/selecciona ciudades y administra únicamente sucursales y tarifas propias; compartir ciudad no comparte datos comerciales. La administración global es capacidad relacionada sin añadir CU prioritario.
3. Migración futura de todos los datos, IDs, relaciones, historial y sucursales a empresa heredada. Si el conteo real confirma las tres sucursales activas del registro histórico, asignarle **administrativamente Profesional** con fechas de inicio/vencimiento explícitas. Si difiere, documentar y revisar antes de aplicar. No crear suscripción ficticia, desactivar sucursales, cambiar límites Básico 2/Profesional 10 ni introducir cobro SaaS.

## Adaptaciones técnicas registradas, todavía no implementadas

- `ReservaService.crear` calcula hoy `fecha_visita + 1 día` cuando recibe visita; `PagoService` extiende desde `reserva.fecha_creacion`. La regla pactada usa creación central +24 h para reserva online, creación local original +24 h para offline aceptada y, con adelanto online confirmado antes del vencimiento, hasta +72 h desde **ese mismo origen**. Visita, recepción, reintentos y avisos no reinician el plazo. Solicitud offline vencida se rechaza sin stock; tiempo incoherente queda en CONFLICTO/TIEMPO_INCOHERENTE. Revisar conjuntamente creación, adelanto, cancelación, expiración y fechas mostradas; no recalcular datos históricos por actualizar documentos.
- La visualización privada offline dura 8 h desde el último login online. Al vencer/logout se oculta, conservando por empresa/usuario los pendientes y resultados; el catálogo público sigue visible. Recuperar conexión no reinicia las 8 h. Es independiente del JWT actual de 24 h y del turno de caja de 8 h; token vencido no permite sincronizar.

## Alcance y comprobación

La primera presentación continúa con CU01, CU02, CU03, CU04, CU13, CU15, CU16 y CU18. CU06/CU07 posteriores conservan contado offline en Flutter con personal autorizado, SQLite y sincronización. Se modificaron solo documentos contractuales y sus copias; no se ejecutaron pruebas funcionales, servicios, migraciones ni cambios de base de datos en esta revisión. Las comprobaciones documentales y huellas de los archivos compartidos se registran en `version.json`; no prueban funcionamiento.
