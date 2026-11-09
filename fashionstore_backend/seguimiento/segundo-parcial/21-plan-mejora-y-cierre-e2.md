# Plan de mejora y cierre del segundo parcial

**Corte:** 05/11/2026. **Fuente de bloqueos:** [auditoría 20](20-auditoria-independiente-post-checkpoint-19.md). **Alcance:** los 13 CU de E2 en backend, Angular/PWA y Flutter según su contrato. El commit de este corte es una **línea base de avance observado**, no aceptación ni cierre.

**Commits de código de la línea base:** backend `d548b94`, frontend-web `9992cdc`, app-movil `7880a15`, todos en `feature/sp2-e2-integral`. El commit de este documento en backend queda registrado en `git log` al terminar la operación.

## Orden de ejecución

| Grupo | CU y canales | Trabajo que debe terminar | Puerta para avanzar |
|---|---|---|---|
| **C1. Dinero y stock** | CU22, CU05, CU21, CU27, CU19; backend primero | Preparar método Stripe con SetupIntent confirmado y PaymentMethod real; vincular cada orden y PaymentIntent a un solo recurso, cliente y empresa; verificar estado, importe, moneda y captura antes de declarar pago o entregar stock. Mantener reembolso CU27 sólo sobre dinero capturado. | Pruebas que reproduzcan los cuatro P0 de auditoría 20: setup incompleto, intención ajena/reutilizada, autorización v3 incompleta y 3DS sin captura. Stripe Test real con webhook firmado y 3DS cuando haya credenciales. Regresión E1 de Stripe/caja. |
| **C2. Contrato offline completo** | CU05, CU21, CU22, CU27; backend + PWA + Flutter | Hacer obligatorios y contrastar los quince campos de autorización v3 cuando se solicita cobro posterior; huella SHA-256 canónica, tasa real y condiciones. Sin autorización, conservar solicitud sin cobrar. Añadir transición durable para reautorizar `PENDIENTE_INTERVENCION`/`REQUIERE_NUEVA_ACEPTACION` y continuar una operación sin duplicarla. Conectar checkout Flutter a consentimiento, método preparado y cola v3; PWA usa tasa/huella reales. | Prueba de payload desde cada pantalla hasta FastAPI; reintento, reinicio, caída de red, cambio de oferta y autorización vencida; ninguna operación v1/v2 cobra automáticamente. |
| **C3. Resultado y avisos** | CU05 y estados de CU20/CU08/CU27; backend + PWA + Flutter | Actualizar estado consultable de operación/pedido tras webhook; emitir evento de negocio transaccional sólo tras captura y asignación completa; procesar outbox y enviar FCM/Web Push con deduplicación, reintentos y bandeja. El fallo de push no revierte pago. | Tests de webhook repetido/desordenado, un solo aviso por resultado, recuperación por polling/bandeja y baja de dispositivo. Prueba externa de push en Android físico/PWA cuando haya credenciales. |
| **C4. Revisión funcional restante** | CU09, CU20, CU08, CU10, CU11, CU23, CU24, CU25; canales del contrato | Revisar reembolso mixto y exclusividad financiera; 15 días desde entrega, nota 7 días y oferta 48 h; dataset y artefactos ML reproducibles; Gemini real sólo cuando esté configurado; cifras, filtros, fechas de Bolivia, exportaciones, roles y accesibilidad de Angular. | Contraejemplos de cantidades/estados/concurrencia, métricas recomputables, pruebas de proveedor fake y revisión visual 360/390/440/768/1024/1440 px. |
| **C5. Cierre técnico** | Todos los CU E2 | Comparar modelos con PostgreSQL y Alembic 0013; migración aditiva si se necesita, ensayada en copia `_test` con datos. Ejecutar backend E2 y regresiones E1/Ciclo 3, Angular typecheck/build/Karma, Flutter analyze/test, OpenAPI y `git diff --check`. Verificar flujos reales en navegador y Android físico, anotando límites de credenciales/dispositivos. | Auditoría independiente sin P0/P1, estado por CU y canal respaldado por evidencia, checkpoint final y commits de grupos revisados. Sólo entonces proponer aceptación/cierre; push/merge/despliegue quedan como decisión separada del propietario. |

## Coordinación y registro

1. Trabajar en las ramas `feature/sp2-e2-integral` ya abiertas en los tres repositorios. Preservar el checkpoint de este corte y no reescribirlo; cada corrección agrega prueba y entrada de bitácora.
2. Si se usan subagentes, asignar archivos exclusivos antes de editar. C1 backend financiero y C4 analítica pueden avanzar en paralelo; C2 consume DTO/OpenAPI de C1; C3 consume estados confirmados de C1/C2. El coordinador posee modelos compartidos, migraciones y registro OpenAPI.
3. Tras cada grupo, registrar en `02-estado-cu.md` archivos, prueba que antes fallaba, resultado nuevo, canal y commit real. Un commit intermedio registra avance; sólo la auditoría final permite pasar de `Avance sin aceptar` a `Aceptado`.
4. No versionar claves, contraseñas, bases locales, artefactos ML generados por pruebas ni reportes de salida temporales. Usar variables de entorno para credenciales de prueba.

## Criterio de finalización

Los 13 CU alcanzan el contrato 0.3.2/protocolo 0.4.0 en sus canales asignados, las rutas críticas de dinero e inventario tienen evidencia de captura/uso único y pruebas de reintento, y los límites de integración externa están expresados con exactitud. El proyecto queda listo para solicitar aceptación del propietario cuando no existan bloqueos funcionales abiertos.
