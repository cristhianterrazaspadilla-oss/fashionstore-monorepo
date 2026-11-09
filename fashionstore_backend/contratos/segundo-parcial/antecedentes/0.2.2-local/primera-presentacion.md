# Primera presentación — alcance acordado

**Alcance fijado el 24/10/2026; aclaraciones aprobadas el 25/10/2026.** Ocho casos: CU01, CU02, CU03, CU04, CU13, CU15, CU16 y CU18. Cuatro nuevos y cuatro anteriores adaptados; pertenecen al catálogo completo de 26, cuya numeración se fija en [equivalencias-cu.md](equivalencias-cu.md).

## Nombres vigentes

| CU | Nombre | Tipo |
|---|---|---|
| CU01 | Registrar empresa contratante | Nuevo |
| CU02 | Administrar suscripción de empresa | Nuevo |
| CU03 | Descargar catálogo para consulta offline | Nuevo |
| CU04 | Registrar reserva offline | Nuevo |
| CU13 | Registrarse e iniciar sesión por empresa | Anterior adaptado |
| CU15 | Gestionar ciudades, sucursales y tarifas | Anterior adaptado |
| CU16 | Consultar catálogo de prendas | Anterior adaptado |
| CU18 | Gestionar reservas de prendas | Anterior adaptado |

Solo CU04, CU13, CU16 y CU18 se abrevian ahora. Las fichas conservan el alcance: CU04 incluye persistencia y sincronización; CU16 incluye filtros y disponibilidad conocida; CU18 incluye crear/consultar/cancelar. Autor vacío y fecha 24/10/2026 en las ocho fichas. No renombrar silenciosamente API, tablas o métodos por estos títulos.

## División propuesta, sin asignar persona

| Bloque | Casos | Dueños técnicos |
|---|---|---|
| A | CU01, CU02, CU13, CU15 | identidad_empresas y organizacion |
| B | CU03, CU04, CU16, CU18 | catalogo y reservas_traslados, con apoyo de inventario |

Cada bloque cubre backend y sus clientes pertinentes. CU01/CU02 se administran en web; móvil consume empresa/capacidades. CU13 opera en web/móvil; CU15 administra en web y aporta consulta/selección móvil. Bloque B trabaja PWA y Flutter. No dividir automáticamente una persona por tecnología: se acordó reducir cruces por funcionalidad.

Antes de avanzar en paralelo, acordar sesión/empresa/sucursal, permisos, errores, DTO y quién integra migraciones/rutas/configuración. El bloque A coordina identidad y migraciones; el bloque B, persistencia offline y reservas. No editar ambos simultáneamente un archivo común sin coordinar.

## Criterios de salida

- Dos empresas independientes en PostgreSQL compartido; backend valida pertenencia y permiso, no solo la interfaz.
- Catálogo público identificable por enlace empresarial propuesto `/tienda/{empresa_codigo}`; conserva ese contexto hacia registro/login y operaciones posteriores sin reutilizar silenciosamente una sesión de otra empresa. La pantalla inicial de selección de empresas queda como mejora opcional posterior.
- Planes Básico/Profesional con 2/10 sucursales activas configurables, fechas manuales, 72 h de gracia y continuidad de compromisos/posventa según reglas.
- Empresa heredada conserva datos e identificadores. Si el conteo histórico de tres sucursales activas se confirma en destino, se le asigna administrativamente Profesional con fechas introducidas explícitamente; si difiere, se registra y revisa antes de aplicar. No hay asignación ficticia ni desactivación automática.
- Ciudades como referencia global administrada por plataforma; CU15 permite a la empresa consultarlas/seleccionarlas y administrar únicamente sus sucursales y tarifas. La administración global no añade otro CU prioritario.
- Catálogo descargado, consultable offline y tras reinicio en IndexedDB y SQLite; fecha, versión y aviso de disponibilidad conocida.
- Reserva offline durable con UUID estable y resultado persistido; aceptación central atómica, reintentos sin duplicación, rechazos/conflictos conservados.
- Registro/login por empresa y separación local de usuarios/empresas. Datos privados del cliente visibles 8 h desde último login online y ocultos al vencer/logout, conservando pendientes/resultados hasta reautenticar; catálogo público continúa visible. La ventana local es independiente del JWT actual de 24 h y no autoriza sincronización sin token válido.
- Reservas online propias consultables/cancelables; liberación de stock una sola vez e integración con solicitudes aceptadas. Online vence 24 h desde creación central; offline aceptada, 24 h desde creación local original. Adelanto confirmado online antes del vencimiento fija 72 h desde el mismo origen; la fecha de visita, recepción y reintentos no prolongan el plazo.
- PWA instalable y recursos para abrir funciones offline; pruebas críticas apropiadas, evidencia y coherencia ICONIX.

La automatización de expiración actual CU26 y el inventario actual CU17 pueden necesitar cambios de soporte; no declararlos casos completos de esta presentación por ese hecho. Igual criterio para usuarios/roles CU14.

## Alcance posterior que debe preservarse

Flutter sí debe registrar ventas de contado offline con SQLite, actor autorizado, detalle y sincronización. Los CU06/CU07 se implementarán en una presentación posterior; no sustituirlos por compra diferida. Caja, pagos/moneda, cambios/saldo, reportes/ML y notificaciones conservan su planificación global. La primera presentación no completa por sí sola todas las pautas del examen.

La auditoría aportada y el [contraste del código actual](alineacion-codigo.md) son estáticos. No se ejecutaron pruebas ni migraciones en esa revisión. Las discrepancias técnicas se documentan sin cambiar reglas acordadas para acomodarlas a una limitación de la implementación.
