# Cambios de revisión 0.2.0 — 24/10/2026

## Alcance de la actualización

Se revisaron los 18 archivos recibidos en contratos/segundo-parcial. Se conserva su información útil, reordenando fichas y referencias al catálogo académico de 26. Once funciones anteriores no prioritarias permanecen bajo códigos LB, con sus impactos transversales en trazabilidad-funciones-conservadas.md. No se modificó código de aplicación, ningún repositorio GitHub ni una base de datos.

- Ocho fichas priorizadas y actualizadas: CU01, CU02, CU03, CU04, CU13, CU15, CU16 y CU18. Autor vacío; fecha 24/10/2026.
- Nombres abreviados aplicados solo a CU04, CU13, CU16 y CU18; alcance funcional conservado. CU07/CU08/CU21 mantienen sus nombres hasta revisión posterior.
- Mapa completo de 26, equivalencias legibles/máquina y once funciones LB para conservar e-commerce/probador y otros flujos anteriores.
- Paquetes y trazabilidad globales, detalle prioritario de ocho y reparto A/B sin asignación personal; grupos académicos separados de módulos de código.
- Reglas C01/C07/C19/C21/C30 corregidas: contado offline Flutter obligatorio, con autorización de caja y SQLite. Las reglas de turno/cupo aplican a ambos clientes.
- Flujo y prompt actualizados al alcance actual; la antigua E1 con tasa no define la primera presentación. La tasa CU12 es posterior.
- Resultado JSON incluye CONFLICTO y TIEMPO_INCOHERENTE coherentes con fichas, reglas y ejemplos. version_esquema=1 y campos obligatorios de comandos se conservan. El cambio requiere actualización coordinada de clientes/validadores: no se garantiza compatibilidad automática por ser una adición al enum.
- Homogeneizada la referencia propuesta de aceptar precio mediante operacion_id. Las rutas públicas y DTO reales deben contrastarse con OpenAPI/código; no se renombraron APIs por la nueva numeración.
- Datos y respaldo local de 18/10 señalados como históricos; verificar estado real antes de migrar. Se conserva la condición original de trabajar con cambios locales y no publicar sin prueba manual/OK.

## Qué falta verificar con el código

La revisión original fue documental sobre el RAR y las decisiones de la conversación. Posteriormente se inspeccionó estáticamente el código de los tres repositorios y se registró el contraste en [alineacion-codigo.md](alineacion-codigo.md). No se ejecutaron pruebas de backend, Angular o Flutter, migraciones, servicios externos ni despliegue. Las rutas/firmas propuestas no se certifican como existentes.

Antes de implementar, Codex debe revisar el checkout actual y cerrar los schemas de alta de empresa/suscripción, identidad, sucursales y descarga con sus DTO/OpenAPI reales. Para las presentaciones posteriores, completar el detalle de caja móvil, cliente opcional de venta, comprobantes y recuperación autorizada, además de contratos de pagos/posventa/ML. Conservar reglas globales no significa tener esos módulos implementados ni cerrados en todos sus campos.

## Validación de esta entrega

Se comprobaron JSON válidos y esquemas Draft 2020-12, catálogo de 26 sin duplicados, equivalencias de las 37 fichas originales sin pérdida, selección de ocho con autor/fecha correctos, enlaces Markdown locales y huellas compartidas. Se validaron ejemplos de reserva aceptada y conflicto temporal contra los esquemas, además de rechazos estructurales de comandos inválidos. El informe automatizado está en validacion-documental.json.

No se pueden certificar los resultados funcionales de las pruebas previstas usando solo estos documentos.

## Contraste posterior con los proyectos — 24/10/2026

Se añadió [alineacion-codigo.md](alineacion-codigo.md) con evidencia estática por cada uno de los ocho CU prioritarios. Se corrigieron referencias que seguían afirmando que los tres proyectos no se habían inspeccionado y la mención residual a la versión 0.1.1. Las copias contractuales de Angular y Flutter se alinearon a 0.2.0 conservando `angular-pwa.md` y `flutter.md`; en esta última se retiró la exclusión antigua de caja móvil. No se cambiaron reglas de negocio, fichas prioritarias ni el protocolo JSON. La validación documental mencionada arriba corresponde a la entrega original: las copias y huellas posteriores se verifican por separado.
