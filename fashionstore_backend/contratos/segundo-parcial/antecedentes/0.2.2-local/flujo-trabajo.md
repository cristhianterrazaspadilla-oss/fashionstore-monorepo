# Trabajo y coordinación — primera presentación

Revisión documental 0.2.1 del protocolo 0.2.0. Los repositorios backend, Angular y Flutter tienen historias Git independientes. Se trabaja por **presentaciones**, con los ocho casos y bloques de [primera-presentacion.md](primera-presentacion.md). Las etapas técnicas históricas E1–E6 no definen el alcance de esta presentación ni obligan a repartir una persona por tecnología.

## Bloques de trabajo

| Bloque | Casos | Responsabilidades y canales |
|---|---|---|
| A | CU01, CU02, CU13, CU15 | Backend identidad/empresa/planes y organización; alta/plan/administración web; registro/login web y móvil, y consulta móvil de sucursales/capacidades. |
| B | CU03, CU04, CU16, CU18 | Backend catálogo/reservas y apoyo de inventario; PWA con IndexedDB, instalación y recursos offline; Flutter con SQLite; pendientes, resultados y sincronización de reservas. |

La asignación personal sigue pendiente. Ambos bloques tienen dependencias: A define identidad/empresa/sucursal, B las consume. A integra migraciones de base y cambios comunes de autorización; B coordina modelos locales y sincronizador. Si un archivo transversal es compartido, acordar su responsable e integrar cambios secuencialmente.

Decisiones ya cerradas para coordinar: enlace público empresarial `/tienda/{empresa_codigo}` como navegación propuesta sin permiso privado; ciudades globales administradas por plataforma, con sucursales/tarifas por empresa; Profesional administrativo para la empresa heredada **si** el conteo real confirma tres sucursales activas. Conteo y fechas de vigencia siguen siendo datos operativos por comprobar/capturar. A define el contexto que B conserva en catálogo y reservas. A coordina privacidad local de 8 h independiente del JWT actual de 24 h; B coordina origen temporal de reservas con adelantos y expiración, sin cambiar historial durante esta aclaración.

## Secuencia técnica

1. Revisar estado Git, AGENTS.md aplicables, arquitectura y contratos; preservar modificaciones existentes. Contrastar equivalencias de CU con nombres y código, sin modificar APIs por simple renumeración.
2. Acordar contexto de sesión, empresa/sucursal, DTO, permisos y errores. Diseñar migraciones aditivas y ensayarlas en base aislada conforme al plan. Los modelos existentes no prueban multitenencia.
3. Implementar bloque A y API mínima de catálogo/reservas; B puede avanzar almacenamiento/UI con dobles claramente identificados, sin declarar integración real.
4. Integrar catálogo descargado, consulta offline y reserva local; servidor aplica validación central y resultado durable. Reintentos conservan UUID, datos y tiempo de origen.
5. Verificar dos empresas, límites de plan, reinicio sin red, stock, plazos, conflicto temporal, respuesta perdida y cancelación idempotente. Ejecutar regresión proporcional a lo modificado.
6. Exportar OpenAPI desde la implementación, cotejar con mensajes documentados y registrar evidencia real por CU. Actualizar las discrepancias técnicas de forma coordinada; no alterar reglas acordadas sin fundamento.

CU12 tasa no se incorpora automáticamente al bloque A. Caja CU06/CU07 es posterior y debe existir en PWA/Flutter. Los demás casos conservan su planificación; estos documentos no asignan aún las otras presentaciones ni su reparto definitivo.

## Ramas y archivos compartidos

Puede usarse una rama por bloque y repositorio cuando sea seguro respecto de cambios locales existentes. No ejecutar reset/clean ni descartar cambios para cambiar de rama. Revisar routers, dependencias de autenticación, registro de modelos, Alembic, rutas web/configuración e interceptores, cliente API/sesión móvil: son puntos de coordinación.

Los grupos académicos no son necesariamente carpetas de código. Reutilizar paquetes existentes según paquetes-cu.md; el adaptador común de sincronización no posee las reglas de reserva, stock o dinero.

## Revisión y autorización de publicación

Se conserva la condición indicada en la documentación original del propietario: dejar cambios de implementación locales sin commit, push, PR ni despliegue hasta prueba manual y OK explícito para publicar. No ejecutar DDL sobre la base original. Esto no impide inspección, cambios locales autorizados ni pruebas en entorno aislado.

Cada bloque entrega diff, CU/requisito, versión de contrato, migraciones, pruebas/comandos/resultados y pasos manuales. No confundir previsto, implementado y verificado. Tras autorización del propietario, coordinar integración de contrato, backend/OpenAPI, clientes y pruebas finales.

## Contrato compartido

Los archivos enumerados en version.json deben coincidir byte a byte entre repositorios; actualizar sus huellas tras editar. El protocolo 0.2.0 requiere que los consumidores reconozcan CONFLICTO sin destruir pendientes antiguos. La revisión documental 0.2.1 no cambia `interfaz.json`, los JSON Schema, los campos de comandos ni `version_esquema=1`. Un cambio de mensaje debe describir impacto y migración; los esquemas/versiones estables incompatibles requieren cambio explícito y coordinación. La numeración académica por sí sola no cambia el protocolo.
