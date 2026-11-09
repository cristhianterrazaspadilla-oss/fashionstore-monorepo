# Contratos FashionStore — Angular/PWA

**Revisión documental 0.2.1 — 25/10/2026; protocolo 0.2.0.** Diseño contractual contrastado por lectura estática; no equivale a funcionalidad implementada ni a OpenAPI exportado.

El catálogo compartido contiene 26 CU actuales. Esta primera presentación prioriza CU01, CU02, CU03, CU04, CU13, CU15, CU16 y CU18, distribuidos en bloques A/B en [primera-presentacion.md](primera-presentacion.md). [equivalencias-cu.md](equivalencias-cu.md) conserva la numeración anterior y [alineacion-codigo.md](alineacion-codigo.md) separa evidencia del código de comportamiento requerido. Las funciones anteriores restantes se conservan en [funciones-conservadas.md](funciones-conservadas.md).

## Guía de esta copia

- [casos-de-uso.md](casos-de-uso.md), [reglas-aprobadas.md](reglas-aprobadas.md), [trazabilidad-cu.md](trazabilidad-cu.md) y [paquetes-cu.md](paquetes-cu.md): alcance, reglas y mapa de paquetes.
- [interfaz.json](interfaz.json), [operacion.schema.json](operacion.schema.json), [resultado.schema.json](resultado.schema.json), [compartido.md](compartido.md), [integracion.md](integracion.md) y [payloads.md](payloads.md): contratos propuestos, no rutas nuevas ya verificadas en ejecución.
- [angular-pwa.md](angular-pwa.md): navegación y almacenamiento web, instalación PWA y caja web futura.
- [flujo-trabajo.md](flujo-trabajo.md), [guia-revision-manual.md](guia-revision-manual.md), [CAMBIOS-0.2.1.md](CAMBIOS-0.2.1.md), [CAMBIOS-0.2.0.md](CAMBIOS-0.2.0.md) y [version.json](version.json): coordinación, revisión, historial y huellas.

El código Angular actual agrupa funciones en `src/app/features/<paquete>/`; las rutas públicas se registran en `src/app/app.routes.ts` y la infraestructura común en `src/app/core/`. La caja existente bajo `ventas_pagos/caja` es online. La PWA, IndexedDB y la caja offline de CU06/CU07 son exigencias de diseño pendientes; Flutter también participa en esa caja posterior mediante SQLite.

El enlace público `/tienda/{empresa_codigo}` es navegación propuesta para catálogo empresarial, no ruta ya implementada ni permiso. Ciudades son globales y las empresas administran solo sucursales/tarifas propias. La ventana privada local de 8 h desde login online es independiente del JWT actual de 24 h; los detalles web están en [angular-pwa.md](angular-pwa.md).

El backend es origen editorial de los archivos compartidos enumerados en `version.json`. Se copian idénticos a los tres repositorios y se cotejan sus SHA-256. Los archivos específicos de Angular, en especial este README y `angular-pwa.md`, se conservan. Una modificación de protocolo debe contemplar la migración de pendientes IndexedDB por `version_esquema`; renumerar CU no cambia rutas ni IDs existentes.

Para trabajo de implementación rige la puerta del propietario descrita en [flujo-trabajo.md](flujo-trabajo.md). Esta revisión solo modifica documentación local. Los nombres nuevos TypeScript se proponen en español `camelCase`, salvo firmas obligatorias del framework.
