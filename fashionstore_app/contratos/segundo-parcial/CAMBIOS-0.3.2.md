# Cambios contractuales 0.3.2 — 01/11/2026

Alcance deliberado: **CU03, CU04, CU16 y CU18** ya trabajados bajo contratos anteriores. Se concretan para empezar por su adaptación antes de definir la implementación de los otros diez CU de la primera entrega. La versión de protocolo **permanece 0.4.0** y la operación de reserva continúa v1. Las otras 23 fichas siguen con reglas 0.3.1.

- [Cierre de los cuatro CU](cierre-cu03-cu04-cu16-cu18-0.3.2.md): rutas, DTO, campos canónicos, adaptadores, aislamiento, persistencia local, estados, tiempo y pruebas de aceptación.
- CU03 fija snapshot completo y coherente con `catalogo_version`, `generado_en`, sucursales, colores compuestos y promociones con umbral. W usa IndexedDB y M SQLite; una copia nueva solo sustituye la anterior tras commit local.
- CU04 añade solicitud/respuesta tipadas de referencia horaria y fija presentación `America/La_Paz` (`-04:00`) con persistencia UTC. Validez inicial 8 h y tolerancia inicial 5 min quedan versionadas por referencia; la privacidad desde login es independiente. Se preservan operaciones v1 anteriores sin reescribir UUID/fecha/cuerpo. El origen original determina las 24 h.
- CU16 fija filtros y paginación canónicos para online y copia local, semántica de color compuesto y promoción condicionada. Los alias actuales de lectura se mantienen durante migración.
- CU18 fija nombres reales del DTO de creación (`sucursal_destino_id`, `fecha_visita`), revisión de cancelación, estado por línea, origen de plazo e inclusión de reservas CU04 solo tras aceptación central.
- Se actualizan fichas, índice API, payloads, interfaz, esquema de operación, ejemplos y guía de aceptación; se añaden dos JSON Schema para la referencia horaria. Los hashes de `version.json` identifican los archivos compartidos idénticos en B/W/M.

**Estado:** contrato documental cerrado para implementación. No acredita endpoints nuevos, base activa, pruebas de integración, OpenAPI real ni consumidores PWA/Flutter actualizados. El informe histórico `validacion-documental.json` corresponde a 0.3.1; la comprobación de 0.3.2 se registra por separado.
