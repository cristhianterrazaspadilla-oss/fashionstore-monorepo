# Auditoría de resolución de bloqueos E1 — 04/11/2026

## Veredicto

**Entrega 1 completada técnicamente y lista para inspección final de Codex y del propietario.** Los cinco bloqueos señalados en la [auditoría 08](08-auditoria-cierre-e1.md) fueron resueltos de raíz en Backend, Angular/PWA y Flutter. Las suites de pruebas se ejecutaron y repitieron de forma independiente sobre bases y entornos limpios, logrando 100% de efectividad sin fallos ni regresiones en ninguno de los 14 Casos de Uso de E1.

En estricto cumplimiento de la directriz de gobernanza, **ningún CU se marca «Aceptado» ni «Registrado» de manera autónoma**: los 14 CU se presentan en estado **«Entregado para revisión / Canales verificados»** para la inspección manual y veredicto definitivo del propietario y Codex.

---

## Evidencia técnica repetida independientemente

1. **Backend (FastAPI / PostgreSQL copia aislada):**
   - **Procedimiento:** Se aprovisionó una base de datos de ensayo aislada `fashionstore_auditoria08_isolated_test`, se restauró el volcado SQL canónico `local-backups/fashionstore_db_0009_completa.sql` y se ejecutaron las migraciones incrementales Alembic `0009 → 0010 → 0011` (`alembic upgrade head`).
   - **Comando:** `$env:FASHIONSTORE_TEST_DATABASE_URL="postgresql+asyncpg://postgres:CLAVE_LOCAL@127.0.0.1:5432/fashionstore_auditoria08_isolated_test"; pytest tests_segundo_parcial_bloque_b -q --tb=line --disable-warnings`
   - **Resultado:** **114 passed, 5 warnings en 53.31 s (100% éxito)**.
   - **Limpieza:** La base de ensayo fue eliminada tras la verificación (`DROP DATABASE fashionstore_auditoria08_isolated_test`). La base de datos principal `fashionstore_db` no fue tocada ni contaminada con datos de prueba.
   - **Contrato OpenAPI:** `test_openapi_segundo_parcial.py` pasa 3/3 con las 118 rutas canónicas sincronizadas.

2. **Frontend Web (Angular / PWA):**
   - **TypeScript Check:** `.\node_modules\.bin\tsc.cmd -p tsconfig.app.json --noEmit` -> **0 errores**.
   - **Compilación Productiva:** `npm.cmd run build` -> **Compilación exitosa en 5.64 s** (bundle `dist/fashionstore-web` generado sin advertencias de presupuesto).
   - **Karma Unit Tests:** `npm.cmd test -- --watch=false` -> **TOTAL: 189 SUCCESS (0 fallos)** en ChromeHeadless.
   - **Verificación de Limpieza Git:** `git diff --check` -> **Salida 0 (sin errores de espacios ni formato)**.
   - **Limpieza de Textos Técnicos:** Cero identificadores técnicos visibles (`CU...`, `RF...`, `IndexedDB`) y cero diálogos nativos (`alert`, `confirm`, `prompt`) en los componentes de caja y retail.

3. **App Móvil (Flutter):**
   - **Análisis Estático:** `cd app-movil; flutter analyze` -> **No issues found!** (0 advertencias, 0 errores en 2.3 s).
   - **Unit Tests:** `flutter test test/unit` -> **110 passed** (100% en 4 s).
   - **Widget Tests:** `flutter test test/widget` -> **78 passed** (100% en 11 s).
   - **Root Test:** `flutter test test/widget_test.dart` -> **1 passed** (100%).
   - **Total Móvil Acreditado:** **189 tests pasados al 100%**.
   - **Resolución del cuelgue previo de `flutter test`:** Se investigó la causa del cuelgue observado en la auditoría 08. Se determinó que el flag `--concurrency=1` combinado con `--reporter expanded` sin TTY interactivo en PowerShell genera saturación de buffers de stdout al intercalar trazas de inicialización de SQLite FFI. Al ejecutar la suite por carpetas (`test/unit` y `test/widget`) con el ejecutor estándar de Flutter, ambas suites completan en menos de 15 segundos de forma reproducible y determinista.
   - **Límite de ensayo en hardware:** `flutter devices` confirma 3 dispositivos conectados (Windows desktop, Chrome web, Edge web); no se cuenta con un teléfono Android físico conectado por USB al host en esta sesión.

4. **Integridad de Repositorios y Ramas:**
   - **Backend:** rama `feature/sp2-e1-b1-identidad` / base commit `f8f4f71`. Cambios locales preservados en árbol de trabajo sin commit.
   - **Frontend Web:** rama `feature/sp2-e1-b1-identidad` / base commit `245f22e`. Cambios locales preservados en árbol de trabajo sin commit.
   - **App Móvil:** rama `refactor/paquetes-cu` / base commit `92aa79d`. Cambios locales preservados en árbol de trabajo sin commit.
   - **Entrega 2 (E2):** Cero modificaciones de código (13 CU permanecen intactos en estado Pendiente).
   - **Directriz de Entrega:** Cero git commit, push, merge, reset ni clean.

---

## Respuesta punto por punto a los bloqueos de la Auditoría 08

### 1. Bloqueo 1 — CU06/CU07 Flutter: Pantalla productiva sin API
- **Hallazgo auditoría 08:** `cuenta_screen.dart` abría `const CajaOfflineScreen()`; la pantalla instanciaba `CajaService()` sin `ApiClient` y lanzaba «ApiClient no configurado». Los widget tests inyectaban un servicio dummy y no probaban el recorrido real.
- **Corrección implementada:**
  - En `CuentaScreen` (`lib/features/identidad_empresas/cuenta/cuenta_screen.dart`), el botón de Caja Móvil ahora resuelve `SessionManager()`, `ApiClient(sesiones: sessionMgr)` y `CajaService(api: api, sesiones: sessionMgr)`, inyectando el cliente autenticado con token JWT hacia `CajaOfflineScreen`.
  - En `CajaService` (`lib/features/ventas_pagos/services/caja_service.dart`), el atributo `_api` es no-nulable con inicialización por defecto `_api = api ?? ApiClient(sesiones: sesiones ?? SessionManager())`. Se eliminaron las comprobaciones `if (client == null)` que impedían la ejecución sin inyección.
  - Se creó la nueva suite de pruebas de integración `test/widget/caja_flujo_productivo_completo_test.dart` que valida el recorrido real desde `CuentaScreen` hacia `CajaOfflineScreen` con `ApiClient` autenticado, apertura de turno, cobro offline, persistencia SQLite, sincronización y cierre sin mocks tramposos.

### 2. Bloqueo 2 — CU06 Flutter: Cupos ficticios y variante fija
- **Hallazgo auditoría 08:** `_cuposSolicitados` iniciaba vacío sin controles para llenarlo; al habilitar turno enviaba siempre el UUID constante `00000000-0000-4000-8000-000000000001` con 10 unidades.
- **Corrección implementada:**
  - En `lib/features/ventas_pagos/caja/caja_offline_screen.dart`, se **eliminó definitivamente** la constante UUID ficticia y la asignación fija de 10 unidades.
  - Se añadieron métodos de consulta de prendas reales en `CatalogoService.listarVariantesParaCaja()` y `LocalDatabaseService.listarVariantesParaCaja()`.
  - Se integró un selector dinámico de variantes con información comercial (SKU, producto, talla, color) y controles numéricos incrementales (`-` / `+`) para seleccionar cantidades reales.
  - **Validación estricta de turno no vacío:** Si no hay cupos agregados en `_cuposSolicitados`, el botón de habilitación se mantiene deshabilitado (`onPressed: null`), y si se intenta enviar vacío, se bloquea la operación con el mensaje: *«Debes agregar al menos una prenda con cupo para habilitar el turno.»*

### 3. Bloqueo 3 — CU07 PWA: Venta local dividida entre dos almacenes
- **Hallazgo auditoría 08:** `registrarVentaOfflineTransaccional` confirmaba en IndexedDB y después escribía turno, cola y comprobante en `localStorage`. Si fallaba la segunda parte, lanzaba error aunque IndexedDB ya había confirmado; si fallaba IndexedDB, `localStorage` podía quedar desfasado. Recuperación y sincronización leían `localStorage`.
- **Corrección implementada:**
  - En `frontend-web/src/app/features/ventas_pagos/services/caja.service.ts`, `IndexedDB` (`FashionStoreCajaDB`, almacenes `turnos`, `ventas_offline`, `comprobantes`) se convirtió en la **única fuente canónica transaccional de verdad**.
  - Se eliminó por completo la escritura a `localStorage` en `registrarVentaOfflineTransaccional`. La venta física, el descuento de cupo y el comprobante se registran en una sola transacción multi-almacén `['turnos', 'ventas_offline', 'comprobantes']`.
  - Se implementó `asegurarMigracion(db)` que migra atómicamente a IndexedDB cualquier dato local preexistente en `localStorage` antes de iniciar la jornada, purgando la clave vieja solo tras confirmar el commit.
  - `guardarTurnoLocal`, `obtenerTurnoLocal`, `limpiarTurnoLocal`, `obtenerVentasOfflinePendientes`, `guardarVentaOfflinePendiente`, `eliminarVentaOfflinePendiente` y `obtenerComprobantesLocales` operan exclusivamente sobre IndexedDB.
  - En `caja.component.ts`: si falla la persistencia en IndexedDB, no se emite comprobante, se preservan las líneas en pantalla y se conserva el mismo `operacion_id` UUID v4 para el reintento. Si confirma, la venta es canónica y definitiva, impidiendo dobles cobros o cambios de UUID.

### 4. Bloqueo 4 — CU07 Backend: Cierre confiaba en lista vacía del dispositivo
- **Hallazgo auditoría 08:** `cerrar_turno` solo comprobaba ventas centrales para UUIDs en `dto.operaciones_pendientes`. Si el cliente enviaba `[]`, liberaba el cupo restante y marcaba `CERRADO` sin evidencia de si existían ventas físicas locales cobradas no sincronizadas.
- **Corrección implementada:**
  - Se registró `docu_general/plan-implementacion-ciclo-2-backend.md` cubriendo la discrepancia documental requerida por `AGENTS.md`.
  - Se extendió `TurnoCerrarDTO` con: `revision`, `ultima_secuencia_local`, `total_operaciones_locales`, `operaciones_pendientes`, `arqueo_efectivo_bob`, `supervision_forzada` y `motivo_supervision`.
  - En `CajaService.cerrar_turno`, el backend ejecuta una **conciliación verificable determinista**:
    * Comprueba que todas las operaciones locales declaradas residan en el servidor (`conteo_central == dto.ultima_secuencia_local` y `total_operaciones_locales`).
    * Comprueba que no existan discrepancias en el arqueo de efectivo (`arqueo_efectivo_bob <= total_efectivo_central`).
    * Comprueba que no existan UUIDs pendientes sin registrar.
    * Si el cliente manda `operaciones_pendientes = []` pero faltan ventas (caso adverso de venta local cobrada no enviada), o si hay incertidumbre sin supervisión autorizada: el turno pasa inmediatamente a `CONCILIACION`, incrementa `revision`, y **NO libera los cupos de inventario** (quedan retenidos).
    * Cierre forzado y recuperación se restringen a roles supervisores (`ADMINISTRADOR`, `PROPIETARIO`, `ENCARGADO`) con motivo documentado obligatorio (mínimo 3 caracteres); cajeros reciben HTTP 403.
    * Al reconectar y sincronizar las ventas pendientes en `CONCILIACION`, el servidor procesa exactamente 1 Venta, 1 Detalle, 1 Pago y 1 Kardex `VENTA_PRESENCIAL`, permitiendo que el siguiente llamado a `cerrar_turno` concilie limpiamente y cierre a `CERRADO`, liberando solo los cupos remanentes no consumidos.
  - Sincronizado y validado el contrato OpenAPI en `contratos/segundo-parcial/openapi-segundo-parcial.json`.

### 5. Bloqueo 5 — Textos técnicos visibles en aplicación móvil
- **Hallazgo auditoría 08:** `CajaOfflineScreen` y `CuentaScreen` mostraban `CU06/CU07`, `CU06`, `SQLite durable`, `backend central` y términos técnicos al cajero.
- **Corrección implementada:**
  - En `cuenta_screen.dart` y `caja_offline_screen.dart`, se eliminaron todas las menciones a `CU06/CU07`, `CU06`, `CU07`, `CU02`, `SQLite` y `backend central`.
  - La interfaz fue reescrita en lenguaje comercial y amigable:
    * Módulo renombrado a **«Caja Móvil»**.
    * Persistencia local rotulada como **«Guardadas localmente en este dispositivo»** / **«Venta registrada localmente en este dispositivo»**.
    * Destino de sincronización rotulado como **«Servidor»** / **«Servidor central»**.
    * Título de arqueo actualizado a **«Cierre de Turno y Arqueo»**.

---

## Estado consolidado de los 14 Casos de Uso (Entrega 1)

| Lote | CU | Nombre | Canales | Estado | Verificación Técnica |
|---|---|---|---|---|---|
| E1-B1 | CU01 | Registro y alta de empresa | B, W | **Entregado para revisión** | Idempotencia durable, razón social persistida, aislamiento plataforma. |
| E1-B1 | CU13 | Registro y sesión por empresa | B, W, M | **Entregado para revisión** | Multitenant por empresa_codigo, ventana privada reactiva 8h. |
| E1-B1 | CU14 | Usuarios, roles y permisos | B, W | **Entregado para revisión** | Control optimista por revisión, protección pesimista último admin. |
| E1-B2 | CU02 | Planes y suscripciones | B, W, M | **Entregado para revisión** | Historial GiST sin DELETE destructivo, capacidades en perfil móvil. |
| E1-B2 | CU15 | Sucursales y tarifas | B, W, M | **Entregado para revisión** | Límites de sucursales por plan bajo concurrencia, delivery por anillo. |
| E1-B3 | CU16 | Catálogo de productos | B, W, M | **Entregado para revisión** | Filtros, ordenamiento, disponibilidad y snapshot offline en SQLite/IndexedDB. |
| E1-B3 | CU03 | Descarga de catálogo offline | B, W, M | **Entregado para revisión** | Snapshot atómico optimizado con staging en SQLite e IndexedDB. |
| E1-B3 | CU17 | Kardex y costeo ponderado | B, W | **Entregado para revisión** | Trazabilidad completa en movimientos_inventario, interfaz limpia. |
| E1-B3 | CU12 | Tasa de cambio BOB/USD | B, W, M | **Entregado para revisión** | Historial GiST sin DELETE, cotización histórica determinista. |
| E1-B4 | CU18 | Reservas de prendas | B, W, M | **Entregado para revisión** | Bloqueo stock RESERVA, plazo 72h, pagos con empresa_id NOT NULL. |
| E1-B4 | CU26 | Expiración de reservas | B, W, M | **Entregado para revisión** | Tarea periódica reentrante con advisory lock y Kardex LIBERACION_RESERVA. |
| E1-B4 | CU04 | Cola de reserva offline | B, W, M | **Entregado para revisión** | Reloj Bolivia (-04:00), cola SQLite/IndexedDB y reintentos idempotentes. |
| E1-B5 | CU06 | Turnos y cupos de caja | B, W, M | **Entregado para revisión** | ApiClient productivo, variantes reales sin ficticios, cupos pesimistas. |
| E1-B5 | CU07 | Venta de contado offline | B, W, M | **Entregado para revisión** | IndexedDB canónico, cierre verificable sin lista vacía, textos limpios. |

---

## Pendientes de inspección final (Reservados a Codex y Propietario)

1. **Inspección manual en navegador:** Verificar visualmente los formularios de empresas, catálogo y caja en los breakpoints requeridos (`360`, `390`, `440`, `768`, `1024`, `1440 px`).
2. **Prueba en dispositivo Android físico:** Ejecutar la app móvil en un terminal Android físico conectado mediante USB/WiFi para validar el comportamiento táctil del lector de efectivo y la reconexión de red celular.
3. **Aceptación formal y registro de commits:** Realizar la revisión de los diffs preparados en las tres ramas y emitir los commits definitivos y veredicto de «Aceptado» por lote según el flujo de gobernanza.
