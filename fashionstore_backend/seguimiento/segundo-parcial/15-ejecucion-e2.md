# Ejecución de la segunda presentación — 13 CU

**Decisión del propietario, 04/11/2026:** continuar con la implementación de E2 usando subagentes para acelerar el trabajo. E1 tiene entrega técnica y commits; sus recorridos manuales PWA/Android y aceptación formal siguen abiertos en paralelo. Un defecto real de E1 se corrige y registra por separado, sin declararla aceptada por este encargo.

## Punto de partida verificable

| Repositorio | Rama E1 actual | HEAD al preparar este encargo | Observación local |
|---|---|---|---|
| `backend` | `feature/sp2-e1-b1-identidad` | `5a0d801` | `PROMPT_AGENTE_B_BACKEND_SEGUNDO_PARCIAL.md` sin seguimiento es un encargo antiguo 0.2.2; conservarlo fuera del alcance. |
| `frontend-web` | `feature/sp2-e1-b1-identidad` | `1efa89f` | Dos archivos `src/environments/environment*.ts` aparecen modificados por finales de línea, sin diff semántico; inspeccionar y preservar. |
| `app-movil` | `refactor/paquetes-cu` | `41463a7` | Sin cambios locales al preparar este encargo. Flutter E2 se implementa al final. |

El agente debe verificar de nuevo `git status --short`, `git branch --show-current` y `git rev-parse HEAD` en cada repositorio antes de actuar. Crear una rama de integración **`feature/sp2-e2-integral`** en cada repositorio que se vaya a modificar, basada en el HEAD E1 correspondiente. Las ramas E1 y sus commits se conservan. Si el estado local impide cambiar de rama sin mover trabajo ajeno, registrar el obstáculo y trabajar de forma que preserve los archivos; no usar `reset`, `clean`, `stash` ni sobrescribir cambios previos. Los nombres de rama por lote en `03-ramas-y-commits.md` eran propuestas para ejecución por lotes aislados; para este encargo integral se usa una rama E2 por repositorio y commits revisados por grupos de CU.

## Fuentes y prioridad

1. Instrucciones actuales del propietario y `AGENTS.md` del workspace.
2. Contrato `contratos/segundo-parcial` versión **0.3.2**, protocolo **0.4.0**: cada `casos/CUxx.md`, `api-casos.json`, `reglas-aprobadas.md`, `decisiones-0.3.1.md`, `estados-y-transiciones.md`, `integracion.md`, `modelo-datos-completo.md`, `plan-migracion-db.md`, `matriz-examen.md` y contratos por canal. Las fichas E2 son 0.3.1 dentro del paquete 0.3.2. No inventar reglas, estados, plazos, moneda ni permisos; las rutas propuestas se concretan mediante el registro ejecutable de abajo.
3. Código y migraciones reales en los tres repositorios; documentación funcional general cuando el contrato no resuelve una cuestión.
4. `fashionstore-ciclo-2` y `docu_general/plan-implementacion-ciclo-2-backend.md` para reservas, venta, pagos, devoluciones, mermas, expiración e inventario. Las reglas históricas de ese skill que contradigan el contrato vigente no cambian E1 ni E2: registrar la discrepancia y aplicar la decisión contractual actual. Para `frontend-web`, aplicar `fashionstore-frontend-continuity`.

`modelo-datos-completo.md` es diseño, no DDL ejecutable ni prueba de implementación. Comparar modelos SQLAlchemy, revisión Alembic 0013 y esquema PostgreSQL real antes de crear migraciones. Ensayar migraciones aditivas en copia con datos; no aplicar nuevas revisiones a `fashionstore_db` ni a un entorno remoto antes de la revisión del propietario.

### Interfaz ejecutable y dependencias externas

El contrato `integracion.md` advierte que `api-casos.json` contiene rutas propuestas o adaptaciones, no endpoints desplegados. CU08 y CU20 también nombran rutas «propuestas». Por ello, el agente debe crear al inicio un **registro de contrato ejecutable E2** en `seguimiento/segundo-parcial/` con una fila por CU: operación contractual, ruta existente o elegida, método, DTO de entrada/salida, estados, permisos, idempotencia, compatibilidad heredada y prueba OpenAPI. Las decisiones de nombre/DTO se toman contrastando routers y esquemas reales; no se inventan reglas de negocio. Si una ambigüedad cambia importes, plazos, derechos o seguridad, registrar el punto y continuar el trabajo independiente. Publicar el registro antes de conectar frontend y actualizarlo con el OpenAPI generado, sin presentar el JSON propuesto como API real.

La integración Stripe del proyecto anterior al segundo parcial **ya permite pagos online** según el propietario. En el repositorio hay backend de PaymentIntent, consulta y webhook firmado, además de pruebas de concurrencia, Angular con Stripe.js y Flutter con su puerto de pago. El agente debe conservar ese flujo y repetir primero sus pruebas de regresión. Para E2, comparar lo existente con las capacidades adicionales del contrato — método preparado mediante SetupIntent, intento posterior conectado y reembolso por cargo original — y ampliar sólo lo que falte; no reemplazar el checkout funcional sin una causa demostrada. El contrato también exige bandeja/outbox, registro de dispositivos y push FCM Android/Web Push, pero la configuración Android `google-services.json` no está presente en este checkout y no se observó un flujo push completo en el código E1. El agente debe inventariar capacidades reales sin imprimir secretos, implementar adaptadores y pruebas deterministas, y dejar configuración por entorno documentada. `backend/.env` existe, pero su mera presencia no demuestra credenciales válidas. Para CU24, verificar igualmente acceso Gemini y ofrecer un estado tipado cuando la dependencia no esté disponible; no sustituir la interpretación exigida por texto inventado.

**Criterio de cierre:** código, migraciones, pruebas locales y OpenAPI pueden completarse con dobles/fakes. La validación de extremo a extremo de Stripe Test con webhook firmado, push en destinos reales, Gemini si se usa, Android físico y despliegue requiere las cuentas, secretos, destinos y dispositivos correspondientes. El agente no debe pedirlos antes de avanzar en trabajo independiente ni incorporarlos al repositorio. Al final informa cada verificación como `probada con servicio real`, `probada con fake` o `no ejecutada`, con causa y paso exacto para completarla; nunca declara todo E2 aceptado por pruebas simuladas.

La [matriz del examen](../../contratos/segundo-parcial/matriz-examen.md) exige además evidencia ICONIX/UML coherente con código, PWA instalable, SQLite móvil, exportaciones, métricas ML, regresiones y documentación académica. El agente debe actualizar el inventario de evidencias y los artefactos que pueda construir desde el código real. Si crea o actualiza diagramas Communication/Sequence de Enterprise Architect, debe seguir exactamente `AGENTS.md` y el skill `ea-uml-generator`, validar/dry-run y nunca tocar la referencia `.qea`. No declarar «presentación académica completa» sin cotejar esta matriz. El despliegue público sigue fuera del encargo sin autorización específica; dejar estado y pasos de despliegue verificables.

## Lotes y puertas técnicas

El conjunto E2 es **CU05, CU08, CU09, CU10, CU11, CU19, CU20, CU21, CU22, CU23, CU24, CU25 y CU27**. El [plan de dependencias](14-entrega-e1-y-plan-e2.md) desarrolla las reglas; esta tabla fija la entrega del agente.

| Lote | CU y dependencia | Resultado mínimo verificable |
|---|---|
| **B1 Finanzas** | CU09 → CU22 → CU27. CU22 puede comenzar con la infraestructura de órdenes y contextos de pago existentes; su integración de pedido se completa al implementar CU21. | Libro de saldo reservado/consumido/restaurado una vez; orden Stripe Test y webhook firmado idempotentes; obligación de reembolso única por causa/medio original, sin mutar stock. |
| **B2 Compra y caja conectada** | CU21 sobre B1; CU19 sobre CU09/CU22; CU05 sobre CU21/CU22/CU27. | Pedido durable con pago y cumplimiento separados; venta presencial liquidada; compra offline v3 pendiente, reconexión con revalidación exacta e intento automático sólo con método preparado y consentimiento vigente. |
| **B3 Posventa** | CU20 sobre venta/entrega y CU27; CU08 sobre CU20 y liquidación de diferencia por CU09/CU22/CU27. | Custodia no vendible hasta inspección, reposición única; cambio con plazo, reemplazo y un solo destino financiero. |
| **B4 Información y modelos** | CU25 tras ventas centrales; CU23 tras pagos/posventa; CU24 tras consultas tipadas; CU10/CU11 con datasets y modelos versionados. | Ventas por sucursal y fecha Bolivia, dashboard conciliable, cuatro tipos de reporte sin SQL generado por IA, pronóstico y grupos reproducibles con métricas. |
| **M Flutter cliente** | Después de contratos/backend/web B1–B4: CU05, CU08, CU09, CU20, CU21, CU22, CU27. | Flujos cliente reales, estados y avisos; sin pantallas administrativas para CU10/11/19/23/24/25. |

**Puerta antes de cada frontend:** el responsable backend publica DTO, rutas, estados, permisos y OpenAPI real del CU; el responsable Angular/Flutter puede adelantar diseño y pruebas contra el contrato 0.3.2, pero no declarar integración cerrada hasta probar contra el backend ejecutable. Para cada lote, probar idempotencia, concurrencia, tenencia por empresa, transacciones, reintentos y regresión E1 pertinente. El procesamiento de compra **cobra conectado y luego intenta asignación completa de stock**; si falla stock, genera una obligación CU27 por todo el dinero aplicable. No emitir éxito ni push hasta que pago y cumplimiento estén completos.

## Subagentes y propiedad de archivos

El agente principal coordina **al menos tres subagentes** y mantiene una tabla de responsables de archivos en su bitácora de trabajo. Reparto inicial:

1. **Finanzas y persistencia backend:** CU09/CU22/CU27, diseño incremental, migraciones secuenciales y pruebas PostgreSQL. Es el único dueño de `alembic/versions` mientras existan revisiones pendientes; entrega contrato de integración al resto.
2. **Compras y posventa backend:** CU21/CU19/CU05 y después CU20/CU08, en archivos distintos de finanzas; coordina transacciones y estados compartidos antes de editar servicios comunes. Puede dividir investigación y pruebas, pero no crear migración paralela ni escribir el mismo archivo que el subagente 1.
3. **Angular/PWA:** vistas, servicios, colas offline y pruebas por rol, una vez publicada la puerta backend. Propietario exclusivo de `frontend-web/src/app` durante el lote; usa el skill de continuidad.
4. **QA/integración o analítica:** mientras B1/B2 avanzan, audita contrato/código real y prepara pruebas de concurrencia, OpenAPI, E1 y plan de datos B4. Después implementa B4 en archivos propios de analítica. No modifica archivos que otro subagente tiene asignados.

Cuando B1–B4 estén integrados, reasignar subagentes para **Flutter E2-M**: uno en compras/pagos CU05/21/22/09; otro en posventa CU08/20/27; el coordinador integra navegación, sesión, persistencia local, avisos y pruebas. Ningún subagente edita simultáneamente `lib/main.dart`, rutas compartidas o el mismo modelo. Si el entorno limita la cantidad de agentes, mantener al menos tres tareas activas donde haya independencia real; el coordinador puede asumir QA.

El agente principal resuelve conflictos de archivos, valida que ningún subagente invente contratos y ejecuta pruebas integradas. No paralelizar dos migraciones Alembic ni dos ediciones del mismo router/servicio. Publicar una matriz breve `archivo o carpeta → subagente → CU` al empezar y actualizarla al cambiar de lote.

## Regla de commits y reporte

El implementador y sus subagentes **no hacen commit, push, merge ni despliegue**. Al acabar cada grupo B1, B2, B3, B4 y M, entregan un checkpoint en `seguimiento/segundo-parcial` con CU, archivos, DTO/rutas, migración, pruebas exactas/resultados, límites y estado de ramas; pueden seguir con el grupo siguiente sin convertir el checkpoint en aceptación. Si el siguiente grupo depende de un contrato aún no verificado, integrar y probar primero el anterior. La aceptación y los commits de grupos revisados corresponden al propietario con Codex según `03-ramas-y-commits.md`. Se pueden registrar commits de avance backend/web para un CU móvil, pero el CU sigue abierto hasta E2-M.

Antes de informar «terminado», ejecutar pruebas de backend con PostgreSQL aislado y migración con datos, pruebas/build/TypeScript Angular, pruebas/análisis Flutter, comparación OpenAPI, `git diff --check` y revisión de secretos/archivos generados. Informar expresamente lo no ejecutable, en particular Stripe Test real, push y Android físico. Un test que no corrió no se cuenta como aprobado. El reporte final debe permitir revisar y hacer commits sin reconstruir el contexto en otro chat.
