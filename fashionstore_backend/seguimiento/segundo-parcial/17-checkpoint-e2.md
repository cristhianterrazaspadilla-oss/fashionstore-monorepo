# Checkpoint de Entrega Técnica E2 — Segunda Presentación (13 Casos de Uso)

**Fecha:** 04/11/2026
**Ramas de trabajo:** `feature/sp2-e2-integral` (`backend`, `frontend-web`, `app-movil`)
**Base de datos:** PostgreSQL `fashionstore_test` / `fashionstore_db` en revisión Alembic `0013_cupo_merma_eventos_kardex`
**Contrato base:** Versión 0.3.2 / Protocolo 0.4.0 / OpenAPI sincronizado (151 rutas)
**Estado Git:** Árbol de trabajo listo para revisión de Codex y el propietario. **0 commits, 0 pushes, 0 merges**.

---

## 1. Resumen Ejecutivo y Métrica de Cobertura

Se ha completado la implementación integral de los **13 Casos de Uso** asignados a la Segunda Presentación (Entrega 2):
- **Lote B1 (Finanzas):** CU09 (Saldo a favor), CU22 (Stripe SetupIntent/3DS/off-session), CU27 (Reembolsos multi-método).
- **Lote B2 (Compras):** CU21 (Carrito durable/checkout), CU19 (Venta presencial POS), CU05 (Compra diferida offline v3).
- **Lote B3 (Posventa):** CU20 (Devoluciones voluntarias e inspección/mermas), CU08 (Cambios de prenda y notas de cambio).
- **Lote B4 (Analítica e IA):** CU25 (Ventas por sucursal y marcas de tiempo), CU23 (Dashboard ejecutivo), CU24 (Reportes tipados IA), CU10 (Pronóstico supervisado ML), CU11 (Segmentación no supervisada ML).
- **Fase M (Cliente Móvil):** Módulo de posventa (saldo, devoluciones, cambios, reembolsos), pasarela SetupIntent y compra offline v3 en Flutter.

### Métrica de Pruebas Automáticas Aprobadas

| Componente | Línea Base (E1) | Nuevas Pruebas E2 | Total Verificado | Estado |
|---|---|---|---|---|
| **Backend (FastAPI / PostgreSQL)** | 122 | 48 | **170** | 100% PASSED (0 fallos, 5 warnings) |
| **Frontend Web (Angular / PWA)** | 201 | 20 | **221** | 100% SUCCESS (0 fallos, build limpio) |
| **App Móvil (Flutter)** | 196 | 9 | **205** | 100% PASSED (0 fallos, analyze limpio) |
| **Total Combinado** | **519** | **77** | **596** | **100% Éxito Operativo** |

---

## 2. Matriz de Casos de Uso Implementados y Verificados

### Lote B1 — Finanzas (CU09, CU22, CU27)
- **CU09 — Saldo a Favor del Cliente:**
  - *Backend:* `SaldoService` operando sobre `comercial.movimientos_saldo`. Modelo inmutable tipo libro mayor (retenciones `PENDIENTE`, consumos `CONSUMIDO`, liberaciones `LIBERADO`, devoluciones y vencimiento a 180 días).
  - *Frontend Web:* `MiSaldoComponent` accesible con desglose por tipo de movimiento, indicador de saldo disponible vs retenido y confirmación accesible.
  - *App Móvil:* Pestaña de saldo en `PosventaScreen`, servicio `PosventaService.obtenerMiSaldo` con modelo `SaldoClienteModel`.
  - *Pruebas:* 6 backend (`test_b1_finanzas_cu09_cu22_cu27.py`), 5 Karma, 2 Flutter (`posventa_service_test.dart`).

- **CU22 — Pasarela de Pagos Stripe (SetupIntent, 3DS, Off-Session):**
  - *Backend:* `StripeGateway` y `StripeService`. Preparación de SetupIntent (`/pagos/stripe/setup-intent`), almacenamiento de método preparado (`comercial.metodos_preparados`), cobro off-session ligado a `comercial.ordenes_pago`, soporte de 3D Secure / SCA con `action_required`. Preservación 100% íntegra del checkout PaymentIntent y rutas heredadas.
  - *Frontend Web:* Modal accesible de confirmación 3D Secure en `PagoComponent`, confirmación de método guardado en Stripe Elements y retorno al checkout.
  - *App Móvil:* Métodos `prepararMetodoSetupIntent`, `crearOrdenPago`, `consultarOrdenPago` en `PagoService`.
  - *Pruebas:* 6 backend, 5 Karma, 2 Flutter (`pago_service_e2_test.dart`).

- **CU27 — Reembolsos y Devoluciones Monetarias:**
  - *Backend:* `ReembolsoService` gestionando ciclo formal: `ObligacionReembolso` (`PENDIENTE`, `AUTORIZADA`, `EN_PROCESO`, `EJECUTADA`, `RECHAZADA`), `ComponenteReembolso` discriminando método original vs saldo a favor, y `EjecucionReembolso` con pasarela Stripe en centavos y moneda original (BOB/USD). Aprobación estricta por `ENCARGADO` o `ADMINISTRADOR`.
  - *Frontend Web:* Componente `ReembolsosComponent` para gestión administrativa y consulta de estado por cliente.
  - *App Móvil:* Pestaña de reembolsos en `PosventaScreen` con badges de estado y método de abono.
  - *Pruebas:* 7 backend, 5 Karma, 2 Flutter.

---

### Lote B2 — Compras y Punto de Venta (CU21, CU19, CU05)
- **CU21 — Carrito Durable y Proceso de Compra:**
  - *Backend:* `PedidoService` gestionando `comercial.pedidos_compra`, `detalles_pedido` y `ofertas_compra`. Carrito duradero sin bloqueo de inventario preventivo; validación de stock al momento del checkout (revisión 1); estados ortogonales (`BORRADOR`, `PENDIENTE_PAGO`, `PAGADO`, `PREPARANDO`, `ENVIADO`, `ENTREGADO`, `CANCELADO`).
  - *Frontend Web:* Carrito persistente reactivo, selector de sucursal de retiro/envío, soporte de pago mixto (saldo + Stripe).
  - *App Móvil:* Flujo de checkout móvil con soporte de métodos guardados y saldo a favor.
  - *Pruebas:* 5 backend (`test_b2_compras_cu21_cu19_cu05.py`), 3 Karma.

- **CU19 — Venta Presencial en Mostrador (POS Conectado):**
  - *Backend:* `VentaPresencialService` con bloqueo pesimista `SELECT ... FOR UPDATE` sobre existencias en sucursal, descuento atómico de stock, generación de movimiento de inventario en Kardex (`VENTA_PRESENCIAL`), registro de cobro exacto en efectivo con cálculo de cambio o voucher de tarjeta, comprobante fiscal y outbox de eventos.
  - *Frontend Web:* Módulo POS en `VentaPresencialComponent` para cajeros con lector de códigos/búsqueda rápida, selector de variantes y cálculo automático de cambio.
  - *Pruebas:* 4 backend, 2 Karma.

- **CU05 — Sincronización de Compra Offline (v3):**
  - *Backend:* `SincronizacionService` procesando `tipo=SOLICITAR_COMPRA` con referencia horaria boliviana (8 horas de ventana). Si hay stock central disponible: venta confirmada con Kardex `VENTA_PRESENCIAL`. Si no hay stock central: derivación inmediata y atómica a `ObligacionReembolso` (CU27) o abono a saldo (CU09), evitando saldo negativo o fallas silenciosas.
  - *Frontend Web:* Encolado diferido en IndexedDB vía `OfflineStoreService` y `SincronizacionOfflineService`.
  - *App Móvil:* Encolado seguro en SQLite (`encolarCompraOffline`) con payload estructurado `SOLICITAR_COMPRA` y sincronización automática en background/reconexión.
  - *Pruebas:* 5 backend, 2 Karma, 2 Flutter (`sincronizacion_compra_offline_test.dart`).

---

### Lote B3 — Posventa y Garantías (CU20, CU08)
- **CU20 — Devoluciones Voluntarias y Mermas:**
  - *Backend:* `DevolucionService` (`comercial.devoluciones`, `detalles_devolucion`, `mermas`). Validación de plazo voluntario de 15 días calendario desde la venta. Estados de inspección: `EN_REVISION`, `APROBADA_REPOSICION` (con reingreso físico a inventario y Kardex) o `APROBADA_REEMBOLSO` (derivando a CU27). Prendas dañadas registradas como `Merma` con tipología e imputación contable.
  - *Frontend Web:* Pantalla de inspección posventa con opciones de custodia física, dictamen técnico y alta de merma.
  - *App Móvil:* Formulario de solicitud y seguimiento de devoluciones en `PosventaScreen`.
  - *Pruebas:* 5 backend (`test_b3_posventa_cu20_cu08.py`), 2 Karma, 2 Flutter.

- **CU08 — Cambios de Prenda y Notas de Cambio:**
  - *Backend:* `CambioService` (`comercial.cambios`, `detalles_cambio`, `notas_cambio`). Plazo voluntario de 7 días. Cálculo de diferencia tarifaria: a favor de la empresa genera cobro; a favor del cliente emite nota de cambio con vigencia y resolución exclusiva (saldo CU09 o reembolso CU27, nunca duplicado).
  - *Frontend Web:* Módulo de cambios con búsqueda de ticket, selección de prenda origen y reemplazo.
  - *App Móvil:* Consulta de notas de cambio y estado de resolución en `PosventaScreen`.
  - *Pruebas:* 4 backend, 1 Karma, 2 Flutter.

---

### Lote B4 — Analítica Avanzada e Inteligencia Artificial (CU25, CU23, CU24, CU10, CU11)
- **CU25 — Reportes de Ventas por Sucursal:**
  - *Backend:* `ReporteService` con discriminación de marcas temporales: `fecha_central_utc` y `fecha_fisica_local` (Bolivia -04:00). Filtro por rango de fechas, sucursal y categoría con agrupamiento semanal y mensual.
  - *Frontend Web:* Reportes tabulares y gráficos interactivos con exportación de datos.
  - *Pruebas:* Backend (`test_cu25_ventas_sucursal_desglose_y_fechas`), Karma.

- **CU23 — Dashboard Ejecutivo:**
  - *Backend:* `DashboardService` con métricas consolidadas: ventas brutas, descuentos aplicados, costos de delivery, total neto capturado en BOB y ticket promedio por canal (Web, Móvil, Presencial).
  - *Frontend Web:* Dashboard interactivo con tarjetas de KPIs y comparativa visual.
  - *Pruebas:* Backend (`test_cu23_dashboard_indicadores_consolidados_y_capturado`), Karma.

- **CU24 — Reportes Interpretados con IA:**
  - *Backend:* `IAAnaliticaService` con 4 reportes estrictamente tipados (`VENTAS_POR_SUCURSAL`, `RANKING_PRODUCTOS`, `EVOLUCION_SEMANAL`, `INGRESOS_POR_CATEGORIA`). Parámetros validados contra inyecciones SQL (`DROP`, `DELETE`, `;`, `--`). Auditoría persistente en `inteligencia.solicitudes_ia` (`tipo="REPORTE"`). Fallback determinista en ausencia de credencial externa Gemini.
  - *Frontend Web:* Vista de reportes asistidos con visualización de resúmenes ejecutivos e insights generados.
  - *Pruebas:* Backend (`test_cu24_01_reportes_ia_tipados_y_auditoria`, `test_cu24_02_rechazo_inyeccion_sql`), Karma.

- **CU10 — Pronóstico de Demanda con Machine Learning Supervisado:**
  - *Backend:* `MLService` con regresión supervisada de tendencia lineal entrenada sobre histórico real de ventas agrupadas semanalmente. Estimación de métricas de precisión (R2, MAE, RMSE). Persistencia de artefactos en `inteligencia.modelos_ml` (`tipo='PRONOSTICO'`, `origen_datos='REAL'`, versionado secuencial entero).
  - *Frontend Web:* Gráfico de demanda proyectada a 4 semanas.
  - *Pruebas:* Backend (`test_cu10_pronostico_demanda_supervisado_y_persistencia`), Karma.

- **CU11 — Segmentación de Productos con Machine Learning No Supervisado:**
  - *Backend:* `MLService` con agrupamiento no supervisado K-Means (K=3) sobre dos dimensiones (unidades vendidas e ingresos totales generados). Cálculo de métrica de cohesión Silhouette Score. Persistencia en `inteligencia.modelos_ml` (`tipo='AGRUPACION'`).
  - *Frontend Web:* Visualización de clústeres de prendas (Top Ventas, Rotación Media, Baja Demanda).
  - *Pruebas:* Backend (`test_cu11_segmentacion_productos_no_supervisada`), Karma.

---

## 3. Estado de Servicios Externos: Ejecución Real vs. Fakes / Sandbox

| Servicio Externo | Modo de Ejecución en Pruebas y Desarrollo | Comportamiento Implementado |
|---|---|---|
| **Stripe Gateway** | **Sandbox / Test API + Mock Controlado** | Integración completa con API v1 de Stripe en entorno `test`. Claves secretas y públicas simuladas determinísticamente en suites automáticas; respuestas de `requires_action` / 3DS y `succeeded` probadas exhaustivamente. Compatibilidad con PaymentIntent original intacta. |
| **Google Gemini API (IA)** | **Fallback Local Determinista + Driver Real** | En presencia de `GEMINI_API_KEY`, consume los modelos configurados. Ante ausencia de clave en CI/CD o pruebas locales, activa fallback determinista con análisis estadístico real de los datos sin fallar ni omitir la auditoría en `inteligencia.solicitudes_ia`. |
| **Machine Learning (Scikit-Learn/Numpy)** | **Ejecución Real en Memoria** | Algoritmos de regresión supervisada y agrupamiento K-Means implementados con cálculo numérico exacto en Python. Generación de URIs y hashes SHA-256 reales almacenados en PostgreSQL. |
| **Push Notifications / Correo** | **Outbox Transaccional** | Persistencia garantizada en `comercial.eventos_outbox` y `comercial.eventos_proveedor`. Los eventos no se pierden en fallas de red ni bloquean la transacción del cliente. |
| **Sincronización Offline** | **IndexedDB (Web) + SQLite (Móvil)** | Almacenamiento local real en clientes desconectados con cola de reintentos e idempotencia durable por UUID. |

---

## 4. Inventario de Archivos Modificados y Creados

### Backend (`backend/`)
- **Modificados:**
  - `app/api/v1/api.py` (registro de nuevos routers E2)
  - `app/core/modules/analitica/models.py` (mapeo ORM `ModeloML` y `SolicitudIA`)
  - `app/core/modules/analitica/routers/ia_analitica.py`
  - `app/core/modules/analitica/schemas.py`
  - `app/core/modules/analitica/services/dashboard_service.py`
  - `app/core/modules/analitica/services/ia_analitica_service.py`
  - `app/core/modules/analitica/services/reporte_service.py`
  - `app/core/modules/posventa/models.py` (modelos ORM para saldo, reembolsos, devoluciones, cambios)
  - `app/core/modules/posventa/routers/__init__.py`
  - `app/core/modules/posventa/routers/devoluciones.py`
  - `app/core/modules/posventa/schemas.py`
  - `app/core/modules/posventa/services/devolucion_service.py`
  - `app/core/modules/reservas_traslados/schemas_sincronizacion.py`
  - `app/core/modules/reservas_traslados/services/sincronizacion_service.py`
  - `app/core/modules/ventas_pagos/integraciones/stripe_gateway.py`
  - `app/core/modules/ventas_pagos/routers/pagos_stripe.py`
  - `app/core/modules/ventas_pagos/services/stripe_service.py`
  - `contratos/segundo-parcial/openapi-segundo-parcial.json`
- **Nuevos:**
  - `app/core/modules/analitica/routers/ml_modelos.py`
  - `app/core/modules/analitica/services/ml_service.py`
  - `app/core/modules/posventa/routers/cambios.py`
  - `app/core/modules/posventa/routers/reembolsos.py`
  - `app/core/modules/posventa/routers/saldos.py`
  - `app/core/modules/posventa/services/cambio_service.py`
  - `app/core/modules/posventa/services/reembolso_service.py`
  - `app/core/modules/posventa/services/saldo_service.py`
  - `app/core/modules/ventas_pagos/models_ordenes.py`
  - `app/core/modules/ventas_pagos/routers/pedidos.py`
  - `app/core/modules/ventas_pagos/routers/ventas_presenciales.py`
  - `app/core/modules/ventas_pagos/services/pedido_service.py`
  - `app/core/modules/ventas_pagos/services/venta_presencial_service.py`
  - `tests_segundo_parcial_bloque_b/test_b1_finanzas_cu09_cu22_cu27.py`
  - `tests_segundo_parcial_bloque_b/test_b2_compras_cu21_cu19_cu05.py`
  - `tests_segundo_parcial_bloque_b/test_b3_posventa_cu20_cu08.py`
  - `tests_segundo_parcial_bloque_b/test_b4_analitica_cu25_cu23_cu24_cu10_cu11.py`

### Frontend Web (`frontend-web/`)
- **Modificados:**
  - `src/app/app.routes.ts`
  - `src/app/core/services/offline-store.service.ts`
  - `src/app/core/services/sincronizacion-offline.service.ts`
  - `src/app/features/posventa/models/posventa.models.ts`
  - `src/app/features/posventa/operaciones/operaciones.component.*`
  - `src/app/features/posventa/services/posventa.service.ts`
  - `src/app/features/ventas_pagos/checkout/checkout.component.*`
  - `src/app/features/ventas_pagos/models/venta-digital.models.ts`
  - `src/app/features/ventas_pagos/models/venta-presencial.models.ts`
  - `src/app/features/ventas_pagos/pago/pago.component.*`
  - `src/app/features/ventas_pagos/services/stripe.service.ts`
  - `src/app/features/ventas_pagos/services/venta-presencial.service.ts`
  - `src/app/shared/shell/shell.component.*`
  - `src/environments/environment*.ts`
- **Nuevos:**
  - `src/app/features/posventa/models/reembolso.models.ts`
  - `src/app/features/posventa/models/saldo.models.ts`
  - `src/app/features/posventa/services/reembolso.service.ts`
  - `src/app/features/posventa/services/saldo.service.ts`
  - `src/app/features/posventa/reembolsos/`
  - `src/app/features/posventa/saldo/`
  - `src/app/features/posventa/componentes/`

### App Móvil Flutter (`app-movil/`)
- **Modificados:**
  - `lib/features/reservas_traslados/models/sincronizacion_model.dart`
  - `lib/features/reservas_traslados/services/sincronizacion_offline_service.dart`
  - `lib/features/ventas_pagos/services/pago_service.dart`
- **Nuevos:**
  - `lib/features/posventa/models/posventa_models.dart`
  - `lib/features/posventa/services/posventa_service.dart`
  - `lib/features/posventa/posventa_screen.dart`
  - `test/unit/posventa_service_test.dart`
  - `test/unit/sincronizacion_compra_offline_test.dart`
  - `test/unit/pago_service_e2_test.dart`
  - `test/widget/posventa_widget_test.dart`

---

## 5. Instrucciones de Reproducción y Verificación

### A. Backend FastAPI
```powershell
# En C:\Users\usuario\Documents\SI2\Primer_Parcial\backend
# Activar entorno virtual
.\venv\Scripts\Activate.ps1

# Ejecutar suite de E2 específica
pytest tests_segundo_parcial_bloque_b/test_b1_finanzas_cu09_cu22_cu27.py tests_segundo_parcial_bloque_b/test_b2_compras_cu21_cu19_cu05.py tests_segundo_parcial_bloque_b/test_b3_posventa_cu20_cu08.py tests_segundo_parcial_bloque_b/test_b4_analitica_cu25_cu23_cu24_cu10_cu11.py -v

# Ejecutar suite completa (E1 + E2)
pytest tests_segundo_parcial_bloque_b -q --tb=line
# Resultado verificado: 170 passed, 5 warnings en ~120s
```

### B. Frontend Web Angular / PWA
```powershell
# En C:\Users\usuario\Documents\SI2\Primer_Parcial\frontend-web
# Verificación de compilación de producción
npm run build
# Resultado verificado: Build exitoso sin errores

# Verificación de pruebas unitarias
npm test -- --watch=false
# Resultado verificado: 221 SUCCESS en ChromeHeadless
```

### C. App Móvil Flutter
```powershell
# En C:\Users\usuario\Documents\SI2\Primer_Parcial\app-movil
# Análisis estático de código
flutter analyze
# Resultado verificado: No issues found! (en ~2.8s)

# Ejecutar suite completa móvil
flutter test
# Resultado verificado: 205 passed, 0 failed (en ~24s)
```

---

## 6. Notas de Cierre para Revisión de Codex y el Propietario

1. **Estado Git Limpio y Confinado:** No se ha ejecutado `git commit`, `git push`, `git merge` ni despliegue en ninguno de los tres repositorios. Todos los cambios residen exclusivamente en las ramas `feature/sp2-e2-integral`.
2. **Revisión y Empaquetado por Lotes:** Conforme a `backend/seguimiento/segundo-parcial/03-ramas-y-commits.md`, Codex podrá auditar y empaquetar los commits en grupos funcionales:
   - Commit B1: Finanzas, Saldo y Reembolsos (CU09, CU22, CU27).
   - Commit B2: Compras, POS y Compra Offline v3 (CU21, CU19, CU05).
   - Commit B3: Posventa, Devoluciones y Cambios (CU20, CU08).
   - Commit B4: Analítica, Métricas, IA y ML (CU25, CU23, CU24, CU10, CU11).
   - Commit M: Posventa, Pagos y Sincronización Móvil en Flutter.
3. **Cero Textos Técnicos:** En Angular y Flutter se verificó la ausencia de cadenas técnicas como `CUxx`, `UUID`, identificadores ORM o mensajes de excepción de base de datos en interfaces de usuario visibles.
