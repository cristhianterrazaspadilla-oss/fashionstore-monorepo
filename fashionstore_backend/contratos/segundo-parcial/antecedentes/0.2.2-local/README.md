# Contratos FashionStore — segundo parcial

**Revisión documental 0.2.2 — 25/10/2026. Estado: diseño documental actualizado; implementación por verificar.** El protocolo de `interfaz.json` conserva su versión 0.2.0 y `version_esquema=1`.

Esta carpeta integra el catálogo actual de **26 casos de uso** y prioriza la primera presentación: **CU01, CU02, CU03, CU04, CU13, CU15, CU16 y CU18**. Los doce nuevos son CU01–CU12 y los catorce anteriores adaptados CU13–CU26. Las once funcionalidades anteriores no prioritarias se conservan con códigos LB; su impacto está en [trazabilidad-funciones-conservadas.md](trazabilidad-funciones-conservadas.md). No borrar su código.

Los cuatro nombres abreviados de esta presentación son CU04 Registrar reserva offline, CU13 Registrarse e iniciar sesión por empresa, CU16 Consultar catálogo de prendas y CU18 Gestionar reservas de prendas. La abreviación no recorta persistencia, sincronización, filtros, disponibilidad ni las ramas de reserva.

## Orden de lectura para Codex y el equipo

1. [primera-presentacion.md](primera-presentacion.md): ocho casos, reparto A/B, canales y criterios de salida.
2. [equivalencias-cu.md](equivalencias-cu.md) y [equivalencias-cu.json](equivalencias-cu.json): numeración anterior y actual; no renumerar IDs persistidos ni rutas públicas.
3. [casos-de-uso.md](casos-de-uso.md): catálogo de 26; ocho fichas actualizadas y dieciocho de referencia para próximas presentaciones. [funciones-conservadas.md](funciones-conservadas.md): las once funciones LB. [alineacion-codigo.md](alineacion-codigo.md): contraste estático de los ocho prioritarios con los tres proyectos.
4. [reglas-aprobadas.md](reglas-aprobadas.md), [trazabilidad-cu.md](trazabilidad-cu.md) y [paquetes-cu.md](paquetes-cu.md): reglas, requisitos, paquetes y dependencias.
5. [integracion.md](integracion.md), [backend.md](backend.md) y [compartido.md](compartido.md): comportamiento esperado y contratos de intención.
6. [interfaz.json](interfaz.json), [operacion.schema.json](operacion.schema.json), [resultado.schema.json](resultado.schema.json) y [payloads.md](payloads.md): formas de mensajes, resultados y ejemplos propuestos.
7. [flujo-trabajo.md](flujo-trabajo.md), [plan-migracion-db.md](plan-migracion-db.md), [guia-revision-manual.md](guia-revision-manual.md) y [PROMPT-AGENTE-E1.md](PROMPT-AGENTE-E1.md): implementación, coordinación y verificación.
8. [CAMBIOS-0.2.2.md](CAMBIOS-0.2.2.md) y [CAMBIOS-0.2.1.md](CAMBIOS-0.2.1.md): decisiones cerradas el 25/10/2026; [CAMBIOS-0.2.0.md](CAMBIOS-0.2.0.md) conserva el historial anterior.

## Prioridad y alcance

Las pautas del examen y las aclaraciones posteriores del usuario prevalecen sobre restricciones antiguas. **La venta de contado offline en Flutter es obligatoria**, con personal autorizado, persistencia SQLite y sincronización. PWA usa IndexedDB. Los actuales CU06/CU07 se abordarán después; su ausencia de los ocho no elimina la obligación. Compra digital diferida y efectivo offline son procesos distintos.

Administración general y reportes permanecen online en web. El enlace público por empresa `/tienda/{empresa_codigo}` es una **propuesta de navegación**, no una ruta ni API existente; identifica su catálogo sin dar acceso privado y conserva el contexto al pasar a registro/login. La selección inicial de empresas es una mejora opcional posterior. Las ciudades son referencias globales administradas por plataforma; sucursales y tarifas pertenecen a su empresa. Los datos privados offline del cliente se rigen por 8 h desde el último login online, independientemente del JWT actual de 24 h; el turno de caja es otra autorización de 8 h. No confundir empresa con sucursal.

Esta carpeta conserva los contratos de pagos, cambios, saldo, caja, reportes, ML y notificaciones como contexto global. Detallar primero los ocho no significa implementar todos esos módulos ahora. Los nombres propuestos para simplificar CU07/CU08/CU21 aún no se aplican en esta revisión.

## Estado de implementación e interfaz

Las rutas nuevas son propuestas, no OpenAPI certificado. El 24/10/2026 se inspeccionó estáticamente el código actual de los tres repositorios; los hallazgos y rutas concretas están en [alineacion-codigo.md](alineacion-codigo.md). No se ejecutaron pruebas de aplicación ni migraciones en esa revisión. Los datos de base local de 18/10 son evidencia histórica informada que debe verificarse en cada instalación.

La instantánea OpenAPI vigente de este segundo parcial se exporta en [openapi-segundo-parcial.json](openapi-segundo-parcial.json) y la suite aislada la compara byte a byte con `backend.app.main.app.openapi()`. El contrato histórico del Ciclo 3 (`docu_general/ciclo-3/openapi-ciclo3.json`) no se modifica: se verifica que todas sus rutas, operaciones y esquemas sigan presentes. Cualquier diferencia entre ambos archivos debe ser aditiva y explicarse en [CAMBIOS-0.2.2.md](CAMBIOS-0.2.2.md).

0.2.0 identifica el diseño del protocolo previo a 1.0; **no garantiza compatibilidad automática de clientes antiguos**. La aclaración documental 0.2.1 no cambia sus mensajes. Se mantiene version_esquema=1 y los campos obligatorios del envoltorio de operación. En 0.2.0 se incorporó CONFLICTO al resultado y se alineó TIEMPO_INCOHERENTE. Coordinar enums/validadores y conservar pendientes locales; nunca vaciar SQLite/IndexedDB para adoptar la documentación. Ver [CAMBIOS-0.2.0.md](CAMBIOS-0.2.0.md) y [CAMBIOS-0.2.1.md](CAMBIOS-0.2.1.md).

El backend es origen editorial de interfaz y esquemas. Los tres repositorios deben usar copias idénticas de los archivos compartidos de [version.json](version.json); sus huellas permiten detectar divergencia, pero no demuestran implementación. Los contratos específicos de repositorio que no venían en el RAR se conservan al incorporar esta carpeta; no eliminarlos.

## Cómo incorporar la carpeta

El ZIP contiene `contratos/segundo-parcial/` y una guía exterior. Extraer sobre la raíz del repositorio y sobrescribir únicamente los archivos entregados. No borrar la carpeta contratos completa: podría contener archivos propios de frontend/móvil o contenido nuevo no incluido en el RAR. Revisar el diff en Git y conservar el historial.

Después, pedir a Codex que lea esta carpeta, compruebe el estado real y trabaje solo el bloque asignado. No hacer commit, push, PR ni despliegue con esta entrega documental. El flujo anterior del propietario mantiene los cambios de implementación locales hasta su prueba manual y OK explícito para publicar; la actualización documental no autoriza tocar una base activa ni enviar secretos.

Los métodos y funciones nuevos usan español (`snake_case` Python, `camelCase` TypeScript/Dart), preservando firmas públicas o exigidas por frameworks. Cambiar nombres académicos no exige renombrar funciones existentes.
