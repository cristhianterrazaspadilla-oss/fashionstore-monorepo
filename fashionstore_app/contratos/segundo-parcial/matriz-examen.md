# Cobertura del enunciado y aclaraciones

| Exigencia | Contratos responsables | Evidencia exigida, aún pendiente |
|---|---|---|
| ICONIX, coherencia UML–código | Todos; fichas, trazabilidad y funciones conservadas | Modelos de dominio/robustez/secuencia/clases alineados a implementación real. Include no equivale a precondición ni extend a postcondición; loop depende del flujo y no se agrega mecánicamente. |
| PWA instalable y persistente | CU03/04/05/06/07/16; angular-pwa.md | Manifest, SW, IndexedDB, reinicio, consulta/cobro efectivo offline y resultados recuperables. |
| Flutter SQLite | CU03/04/05/06/07/16; flutter.md | Catálogo, reservas, ventas efectivo y líneas persistidas; reinicio, sincronización y resultados. |
| Stock, efectivo y conflictos | CU06/07/17/19/26 | Sin duplicación, conciliación, cupos exclusivos, carreras y recuperación de caja. |
| Cambios, notas y reembolsos (PDF7.2 + notas) | CU08/09/20/22/27 y LB09/LB16 | Inspección, plazo, falta de reemplazo, traslado, push, cobro diferencia, envío y comprobantes; no usar50% como regla. |
| Reportes generativos reales | CU24/23/25 | Cuatro tipos con filtros variables, consultas controladas, tabla/gráfico y exportación. |
| ML sintéticos/supervisado/no supervisado | CU10/11/23 | Preparación, entrenamiento, baseline, evaluación, artefactos e integración en dashboard. |
| SaaS PostgreSQL compartido | CU01/02/13/14/15 y todos los empresariales | Dos empresas y pruebas negativas API; sucursal no es tenant. |
| Límites y planes | CU02/15; reportes y ML | Básico2/Profesional10 configurable, offline ambos, IA generativa Pro; fechas y administración sin cobro recurrente obligatorio. |
| Preservación primer parcial | Todos adaptados y LB04/05/09/10/13/16/17/18/20/22/25 | Regresión inventario, catálogo, ventas, Stripe, Decart/RA y experiencia cliente. |
| Colores compuestos/promociones cantidad (notas) | CU03/16/19/21 y LB05/LB22 | Filtros online/offline, distintivos y prorrateo histórico consistente. |
| Anexo primer parcial / introducción una hoja (notas) | Documentación académica | Agregar anexo y ajustar extensión; no modifica contratos API. |
| RNF01/02 seguridad/aislamiento | Todos | Autorización por recurso, actor/empresa, no filtrado solo UI. |
| RNF03/05/06 persistencia/idempotencia/recuperación | Sync, pagos y posventa | Reinicio, UUID repetido, payload distinto, caída tras commit/webhook y reanudación. |
| RNF04 integridad transaccional | Inventario, reservas, ventas, caja, saldo/reembolso | Bloqueos y consistencia entre hechos físicos y financieros. |
| RNF07/08 mantenibilidad/compatibilidad | Paquetes/capas/clientes | DTO únicos, pruebas W/M y actualización sin perder pendientes. |
| RNF09/10 rendimiento/observabilidad | Catálogo/reportes/sync | Índices, paginación, correlación, estados, logs sin secretos. |
| RNF11/12 calidad/coherencia | guia-revision-manual.md + auditoría | Automatizar reglas críticas además de evidencias manuales; UML representa lo realmente construido. |
| Nube externamente accesible | Despliegue posterior | Registrar URLs/versión reales; no inventar proveedor backend/frontend. |

A-PAGO-01 fue confirmado por el compañero según comunicación del usuario en 0.3.1; la confirmación académica posterior sigue pendiente. El contrato mantiene cobro electrónico conectado antes de asignación final y CU27 si no se cumple. No se atribuye tarjeta offline al PDF ni se modifica silenciosamente la regla.
