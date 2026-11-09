# FashionStore — contratos segundo parcial 0.3.2 (móvil)

Especificación textual de 27 CU y funciones conservadas, actualizada el 01/11/2026 para cerrar [CU03, CU04, CU16 y CU18](cierre-cu03-cu04-cu16-cu18-0.3.2.md). Las otras 23 fichas mantienen sus reglas 0.3.1. La [alineación estática con los tres checkouts](alineacion-codigo.md) distingue código anterior, adaptaciones y capacidades nuevas; no acredita ejecución de pruebas. Las rutas nuevas siguen siendo objetivo de implementación.

## Orden de lectura
1. [Decisiones vigentes](decisiones-0.3.1.md): A-PAGO-01 confirmado por compañero, compra v3 y políticas configurables; confirmación académica posterior anotada.
2. [Catálogo 27 CU](casos-de-uso.md), fichas casos/ y [cierre CU03/04/16/18](cierre-cu03-cu04-cu16-cu18-0.3.2.md).
3. [Contrato transversal](compartido.md), [integración](integracion.md), [estados](estados-y-transiciones.md).
4. [API por CU](api-casos.json), [interfaz](interfaz.json), [DTO propuestos](payloads.md), esquemas y ejemplos.
5. [Datos completos](modelo-datos-completo.md), [paquetes](paquetes-cu.md), [trazabilidad](trazabilidad-cu.md), [examen](matriz-examen.md).
6. [Construcción coordinada](flujo-trabajo.md), [pruebas](guia-revision-manual.md), [auditoría Codex](PROMPT-AUDITORIA-CODEX.md).
7. [flutter.md](flutter.md).

## Historial
antecedentes/0.2.1 conserva íntegra copia recibida del repositorio. Contiene reglas sustituidas y no es fuente operativa vigente. [Cambios 0.3.0](CAMBIOS-0.3.0.md), [0.3.1](CAMBIOS-0.3.1.md) y [0.3.2](CAMBIOS-0.3.2.md) registran la evolución. El protocolo sigue en 0.4.0; reserva/caja siguen v1 y compra v3 requiere negociación con clientes anteriores. El informe `validacion-documental.json` es evidencia histórica de 0.3.1; no certifica esta revisión.

Datos reales de destino, fechas del plan heredado, porcentajes concretos de promociones y hosts/secretos no se inventan. La inspección de código fue solo lectura; el SQL de 42 tablas sigue siendo propuesta, no estado certificado de Neon.
