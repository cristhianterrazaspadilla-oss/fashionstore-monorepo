# Encargo integral para cerrar FashionStore — plan C1–C5 con subagentes

Trabaja en `C:\Users\usuario\Documents\SI2\Primer_Parcial` hasta completar **todos los trabajos técnicamente ejecutables** del [plan C1–C5](../21-plan-mejora-y-cierre-e2.md), resolver cada bloqueo de la [auditoría independiente 20](../20-auditoria-independiente-post-checkpoint-19.md) y preparar los 13 CU de E2 para una nueva auditoría. Considera además los 14 CU de E1 como regresión y cierre de integración del proyecto completo de 27 CU. **Implementa código, pruebas y documentación; no termines tras formular otro plan.** No declares aceptado un CU por tests verdes o por tu propio informe.

## Fuentes y estado inicial

1. Lee `AGENTS.md` del workspace, `backend/seguimiento/segundo-parcial/README.md`, `02-estado-cu.md`, `03-ramas-y-commits.md`, `05-reanudacion.md`, `20-auditoria-independiente-post-checkpoint-19.md` y `21-plan-mejora-y-cierre-e2.md`. Los checkpoints 17/19 son informes históricos del implementador; la auditoría 20 y el plan 21 rigen el trabajo pendiente.
2. Lee `backend/contratos/segundo-parcial/version.json`, `operacion.schema.json`, `integracion.md`, `estados-y-transiciones.md`, `modelo-datos-completo.md`, `api-casos.json`, las fichas `casos/CUxx.md` y los contratos por canal de los CU afectados. Contrato vigente: **0.3.2; protocolo 0.4.0**. Conserva el reparto acordado **E1 14 CU + E2 13 CU**. No uses `backend/PROMPT_AGENTE_B_BACKEND_SEGUNDO_PARCIAL.md`: es un prompt antiguo 0.2.2 ajeno a E2.
3. Para backend de pagos, caja y posventa aplica el skill `fashionstore-ciclo-2` y `docu_general/plan-implementacion-ciclo-2-backend.md`. Para `frontend-web` aplica `fashionstore-frontend-continuity`. Si una modificación alcanza CU17 de probador Decart según las instrucciones locales, lee primero el skill y la arquitectura exigidos por `AGENTS.md`; no conviertas el número de CU de otra numeración en un cambio implícito de alcance.
4. Comprueba `git status --short`, rama y HEAD **por separado** en `backend`, `frontend-web` y `app-movil`. Hay commits WIP autorizados: backend código `d548b94` y seguimiento `986bac5`, web `9992cdc`, móvil `7880a15`, en `feature/sp2-e2-integral`. Son línea base observada, no aceptación. Conserva cualquier trabajo posterior. No hagas `reset`, `clean`, `stash`, cambio de rama, rebase ni sobrescritura de cambios ajenos.

## Organización obligatoria para acelerar

**Trabaja con al menos tres subagentes** desde el inicio, hasta el máximo que permita tu entorno. Publica antes de editar una matriz `archivo o carpeta → responsable → CU → dependencia`. Cada archivo tiene un único escritor en cada oleada. El coordinador integra, resuelve contratos cruzados y posee `backend/app/api/v1/api.py`, esquemas/modelos compartidos, OpenAPI, Alembic y el seguimiento. No generen dos migraciones a la vez ni editen simultáneamente un router o servicio compartido.

Oleada inicial, con trabajo paralelo y archivos exclusivos:

- **Subagente pagos y compra backend:** C1 de CU22/CU05/CU21/CU27: Stripe gateway/service, SetupIntent y método real, órdenes, captura/webhook, reembolso y pruebas financieras. Coordina cualquier servicio compartido de CU27 con posventa.
- **Subagente caja y posventa backend:** C1 de CU19 y C4 de CU09/CU20/CU08: uso único de cargo, saldo, entrega/Kardex, plazos, cantidades y resolución financiera; pruebas respectivas. No cambia Stripe gateway sin acuerdo explícito.
- **Subagente analítica backend:** C4 de CU10/CU11/CU23/CU24/CU25: datasets, modelos, métricas, Gemini, cifras y pruebas; no edita API raíz ni modelos compartidos a la vez que el coordinador.

Tras congelar DTO y OpenAPI de C1, reasigna subagentes a **Angular/PWA** (Stripe.js, caja, compra offline, analítica/posventa en carpetas separadas), **Flutter** (SetupIntent, consentimiento, cola v3, posventa/notificaciones) y **avisos/outbox + QA**. Puedes iniciar partes independientes antes, pero la integración de canales depende del contrato backend verificado. Da actualizaciones breves de avance y conserva la matriz cuando cambien propietarios.

## Trabajo obligatorio por puertas

### C1 — Dinero y stock: resolver P0 primero

1. CU22: `preparar_metodo` no puede marcar `LISTO` al **crear** SetupIntent ni fabricar referencias `cus_...`/`pm_card_...`. Completa confirmación del SetupIntent con Stripe.js/SDK, consulta proveedor, vincula cliente/empresa y guarda referencias reales protegidas. El PaymentIntent off-session debe recibir `customer` y `payment_method` verdaderos. Mantén Stripe Test y el flujo interactivo ya funcional.
2. CU22 3DS: `continuar_accion` opera sólo sobre la referencia de su orden. Verifica estado `succeeded`, importe, moneda, cliente/recurso y captura real; HTTP 2xx o un `payment_intent_id` enviado por cliente no equivalen a pago. Webhook firmado, eventos repetidos/desordenados y consulta de conciliación deben ser idempotentes.
3. CU19: ningún PaymentIntent puede liquidar dos ventas. Liga orden/cargo a una sola venta y al mismo cliente/empresa; compara importe, moneda y centavos, y rechaza cargo ajeno/reutilizado. La caja no entrega ni descuenta stock antes de liquidación verificable. Conserva efectivo E1, saldo CU09, promociones calculadas por servidor y un solo Kardex.
4. CU05/CU21/CU27: no se asigna stock, no se emite éxito ni obligación monetaria antes de captura. Tras captura, asignación completa/atómica o único CU27 por dinero realmente cobrado; restaura por separado la porción de saldo. Un pago incierto se concilia sin segundo cargo.
5. Añade pruebas de contraejemplo que **fallen antes y pasen después** para setup no confirmado, falta de método real, 3DS pendiente, intención ajena/reutilizada, moneda/importe distintos, webhook duplicado, reembolso sin captura y concurrencia de venta/stock. No reemplaces estas pruebas por aserciones del estado actual.

### C2 — Compra offline contractual en PWA y Flutter

1. Si `SOLICITAR_COMPRA` v3 trae `autorizacion_cobro` para cobro automático, valida los **quince campos requeridos** en `operacion.schema.json` y su equivalencia con oferta central: huella SHA-256 canónica, líneas, base/descuento/envío/total, USD, tasa real e ID, condiciones, vigencia, aceptación local, consentimiento y método preparado del mismo cliente/dispositivo/empresa. Campos ausentes o no coincidentes impiden cobro y producen el estado contractual adecuado. v1/v2 nunca activan pago automático.
2. Diseña e implementa transición durable para `PENDIENTE_INTERVENCION` y `REQUIERE_NUEVA_ACEPTACION`: nuevo consentimiento/revisión correlacionado con la solicitud original, sin violar idempotencia ni duplicar pedido/cargo. Define y prueba también cancelación/conciliación cuando el cobro es incierto.
3. PWA: usa tasa/ID provenientes del backend y Web Crypto SHA-256 sobre el mismo documento canónico; no inventes `tasa_id`. Confirma SetupIntent real antes de ofrecer método preparado, guarda cola durable, reanuda tras reinicio y presenta espera, acción 3DS, nueva aceptación, éxito y fallo.
4. Flutter: desde la **pantalla accesible de checkout**, obtiene o prepara método real, recoge consentimiento específico y pasa `autorizacionCobro` completa a `encolarCompraOffline`; persiste v3 en SQLite. Al recuperar red intenta el cobro automáticamente cuando la autorización es válida y espera resultado central/push. Prueba el payload emitido por la pantalla, no sólo que se llamó al fake.

### C3 — Resultado recuperable y avisos

1. Tras webhook/conciliación, actualiza pedido y resultado consultable de la operación offline. Reconsultar la misma operación debe mostrar el estado **actual** sin modificar el cuerpo/idempotencia original.
2. Emite outbox y bandeja transaccionales en las transiciones de negocio relevantes. Aviso de **compra exitosa** sólo después de captura y asignación íntegra; 3DS, precio cambiado y falta de stock llevan mensajes distintos. Un consumidor real procesa outbox con reintentos/deduplicación y entrega FCM/Web Push a dispositivos registrados; fallo de push jamás revierte pago/stock.
3. Conecta registro/revocación de token nativo o navegador y consulta de bandeja en UI. Prueba repetición y orden de eventos, reinicio, fallo temporal del proveedor, una sola notificación por resultado y recuperación por polling. Si no hay credenciales/dispositivo físico, completa código y fakes y registra la prueba externa como pendiente, sin afirmar que el push real pasó.

### C4 — Resto de E2 y regresión de E1

1. CU09/CU20/CU08/CU27: saldo y reembolso mixto sin doble devolución; 15 días **desde entrega real**, excepción por defecto/incumplimiento tardío para evaluación autorizada, custodia e inspección, cantidades por línea, nota 7 días, oferta 48 horas y destino financiero exclusivo. Verifica carreras entre inspección, reembolso y stock.
2. CU10/CU11: dataset real o sintético etiquetado/reproducible, partición temporal y baseline, métricas recomputables, clustering y artefactos existentes con hash válido; datos insuficientes dan estado honesto. No incluyas artefactos generados por tests en Git.
3. CU23/CU24/CU25: dinero capturado y neto coherentes, fechas de Bolivia, filtros y exportación; Gemini se invoca cuando está configurado, su salida sólo selecciona consultas tipadas permitidas y el proveedor auditado refleja la llamada real. Sin clave, comunica indisponibilidad/fallback contractual sin simular Gemini.
4. Angular: confirma roles/guards, estados loading/vacío/error/éxito, teclado, foco y diseño responsive en **360/390/440/768/1024/1440 px**, sin scroll global. Elimina textos técnicos visibles al usuario. Flutter: navegación real desde cuenta/checkout a posventa, estados recuperables y pruebas de widget desde ruta accesible. Repite regresiones E1 de los 14 CU; sólo reabre un CU E1 si falla integración verificable.

### C5 — Base de datos, verificación y reporte final

1. Compara modelos/constraints con PostgreSQL `fashionstore_db` en Alembic `0013_cupo_merma_eventos_kardex`. Ensaya cualquier migración **aditiva** en una copia con nombre `_test` y datos; verifica upgrade y consultas de los tres canales. No apliques a la base principal ni borres datos sin autorización separada. No uses SQLite como sustituto de PostgreSQL para el cierre.
2. Ejecuta y registra resultados exactos: `tests_segundo_parcial_bloque_b` completo y regresión backend E1/Ciclo 3/Stripe; OpenAPI exportado frente a `app.openapi()`; Angular `tsc --noEmit`, build y Karma; Flutter analyze y test unit/widget; `git diff --check` en los tres repositorios. **Diagnostica el bloqueo de `flutter test` observado en auditoría 20** antes de atribuirle las 213 pruebas del checkpoint 19. Ejecuta pruebas de recorrido real en navegador y Android físico cuando estén disponibles.
3. Antes de declarar listo, revisa contra fichas los **27 CU por canal**. Identifica por separado: verificado automatizado, recorrido manual verificado, pendiente externo y bloqueo de código. Ningún P0/P1 puede quedar oculto como «detalle menor». Si faltan Stripe Test, FCM, Gemini, Android físico o credenciales, deja implementación completa y pasos reproducibles para validar esas dependencias; no inventes resultados.
4. Actualiza `02-estado-cu.md`, `04-bitacora.md`, `05-reanudacion.md`, registro de contrato ejecutable y crea un nuevo checkpoint posterior al 21 con matriz CU/canal, archivos, migraciones, pruebas que antes fallaban y ahora pasan, comandos/resultados exactos y límites. Conserva auditorías/checkpoints anteriores como historial. El informe debe explicar explícitamente cómo se resolvió **cada fila de la auditoría 20**.

## Git y entrega

El propietario autorizó los commits WIP de la línea base, **no** aceptó E2. Deja los nuevos cambios sin commit para revisión de Codex; **no hagas commit, push, merge ni despliegue**. No incluyas `.env`, contraseñas, llaves, dumps, bases locales ni `backend/artefactos/`. Al terminar, informa ramas/HEAD de los tres repositorios, matriz final de subagentes, diff por grupo, pruebas pasadas/fallidas/no ejecutadas y bloqueos externos. Codex revisará, repetirá pruebas y registrará commits de los grupos realmente corregidos. El objetivo es que la revisión pueda cerrar E2 con evidencia, no una nueva declaración de cierre sin recorrido verificable.
