# Contratos FashionStore — Flutter

**Revisión documental 0.2.2 — 25/10/2026; protocolo 0.2.0.** Diseño contractual contrastado por lectura estática; no equivale a funcionalidad implementada ni a OpenAPI exportado.

El catálogo compartido contiene 26 CU actuales. Esta primera presentación prioriza CU01, CU02, CU03, CU04, CU13, CU15, CU16 y CU18, distribuidos en bloques A/B en [primera-presentacion.md](primera-presentacion.md). [equivalencias-cu.md](equivalencias-cu.md) conserva la numeración anterior y [alineacion-codigo.md](alineacion-codigo.md) separa evidencia del código de comportamiento requerido. Las funciones anteriores restantes se conservan en [funciones-conservadas.md](funciones-conservadas.md).

## Guía de esta copia

- [casos-de-uso.md](casos-de-uso.md), [reglas-aprobadas.md](reglas-aprobadas.md), [trazabilidad-cu.md](trazabilidad-cu.md) y [paquetes-cu.md](paquetes-cu.md): alcance, reglas y mapa de paquetes.
- [interfaz.json](interfaz.json), [operacion.schema.json](operacion.schema.json), [resultado.schema.json](resultado.schema.json), [compartido.md](compartido.md), [integracion.md](integracion.md) y [payloads.md](payloads.md): contratos propuestos, no rutas nuevas ya verificadas en ejecución.
- [flutter.md](flutter.md): almacenamiento SQLite, cliente offline y caja móvil posterior; pago Stripe y avisos siguen sus reglas de conexión.
- [flujo-trabajo.md](flujo-trabajo.md), [guia-revision-manual.md](guia-revision-manual.md), [CAMBIOS-0.2.2.md](CAMBIOS-0.2.2.md) y [CAMBIOS-0.2.1.md](CAMBIOS-0.2.1.md), [CAMBIOS-0.2.0.md](CAMBIOS-0.2.0.md) y [version.json](version.json): coordinación, revisión, historial y huellas.

El código Flutter actual se organiza en `lib/features/<paquete>/` y `lib/core/`. Hoy muestra y consume funciones de cliente por HTTP; `SharedPreferences` y el `BolsaStore` en memoria no son la persistencia SQLite requerida. La primera presentación incorpora identidad empresarial, catálogo descargado y reserva offline. CU06/CU07 posteriores obligan a venta de contado offline para personal autorizado también en Flutter, con turno, cupos, SQLite y sincronización. La implementación actual no acredita esa capacidad.

El enlace `/tienda/{empresa_codigo}` es contexto público propuesto, no ruta implementada ni autorización. Ciudades son globales y las sucursales/tarifas pertenecen a cada empresa. La ventana privada local de 8 h desde login online es independiente del JWT actual de 24 h; los detalles móviles están en [flutter.md](flutter.md).

El backend es origen editorial de los archivos compartidos enumerados en `version.json`. Se copian idénticos a los tres repositorios y se cotejan sus SHA-256. Los archivos específicos de Flutter, en especial este README y `flutter.md`, se conservan. Una modificación de protocolo debe contemplar la migración de pendientes SQLite por `version_esquema`; renumerar CU no cambia rutas ni IDs existentes.

Para trabajo de implementación rige la puerta del propietario descrita en [flujo-trabajo.md](flujo-trabajo.md). Esta revisión solo modifica documentación local. Los nombres nuevos Dart se proponen en español `camelCase`, salvo firmas obligatorias del SDK.
