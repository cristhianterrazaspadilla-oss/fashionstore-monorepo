# Checkpoint E2 Post-Auditoría 18 — Corrección Integral y Superación de Bloqueos

**Fecha:** 04/11/2026
**Rama de trabajo:** `feature/sp2-e2-integral` (en los 3 repositorios: `backend`, `frontend-web`, `app-movil`)
**Base de datos:** `fashionstore_test` / `fashionstore_db` (PostgreSQL 17, Alembic `0013_cupo_merma_eventos_kardex`)
**Versión de Protocolo:** `0.4.0` | **Contrato OpenAPI:** `0.3.2` (151 endpoints coincidentes)
**Referencia auditada superada:** [18-auditoria-independiente-e2.md](18-auditoria-independiente-e2.md)
**Estado Git:** Todos los cambios permanecen estrictamente confinados en el árbol de trabajo local (**cero commits, pushes, merges ni despliegues**, conforme a las directrices obligatorias).

---

## 1. Resumen Ejecutivo y Resultados de Verificación

La Auditoría Independiente 18 identificó que las 596 pruebas automáticas del Checkpoint 17 no cubrían flujos contractuales esenciales de pagos reales con Stripe, compra offline v3 con autorización de cobro, liquidación en caja física con medios de pago múltiples, cálculo de plazos de 15 días en posventa desde entrega física, métricas formales de aprendizaje automático (ML) y navegación móvil hacia posventa.

En respuesta a la instrucción técnica de la auditoría 18, se implementaron suites de contraejemplo, se corrigió la lógica en los tres repositorios respetando la asignación exclusiva de archivos y se ejecutó la suite completa.

### Matriz Tri-Repo de Verificación Automatizada

| Repositorio | Herramienta de Verificación | Resultado Previo (Auditoría 18) | Resultado Final Post-Corrección | Estado |
|---|---|---|---|---|
| **Backend (FastAPI)** | `pytest backend/tests_segundo_parcial_bloque_b` | 170 passed | **194 passed, 5 warnings** (+24 contraejemplos) | **100% SUCCESS** |
| **Frontend Web (Angular)** | `npm test -- --watch=false --progress=false` | 221 passed | **242 passed, 0 failed** (+21 pruebas unitarias) | **100% SUCCESS** |
| **Frontend Web (Build)** | `npm run build` | Compilación exitosa | **Exit code 0** (compilación limpia en 13.4s) | **100% SUCCESS** |
| **App Móvil (Flutter)** | `flutter analyze --no-pub` | No issues | **No issues found!** (análisis estático limpio) | **100% SUCCESS** |
| **App Móvil (Tests)** | `flutter test --no-pub` | 205 passed | **213 passed, 0 failed** (+8 pruebas nuevas) | **100% SUCCESS** |
| **Contrato OpenAPI** | `test_openapi_segundo_parcial.py` | 151 rutas | **3/3 passed** (151 rutas coincidentes, 0 deltas) | **100% SUCCESS** |
| **Total General** | **Suites automáticas integradas** | **596 aprobadas** | **649 pruebas automatizadas aprobadas** | **100% SUCCESS** |

---

## 2. Organización del Equipo de Subagentes Especializados

Para garantizar la integridad y evitar colisiones de archivos en el árbol de trabajo, se orquestó un equipo de 6 subagentes con propiedad exclusiva declarada previamente en [matriz-responsabilidades-e2.md](matriz-responsabilidades-e2.md):

1. **Subagente 1 (`0e39de3a-f649-46a3-a7fe-9cd051fecce4`) — Backend Pagos y Compras (P0/P1)**
   - *Ámbito exclusivo:* Stripe gateway, órdenes de pago, SetupIntent, compras offline v3 en backend, suites `test_b1` y `test_b2`.
2. **Subagente 2 (`c34b4064-d878-442b-95b2-1e7ba8cb80a0`) — Backend Caja y Posventa (P0/P1)**
   - *Ámbito exclusivo:* Liquidación presencial CU19, devoluciones CU20, cambios CU08, reembolsos CU27, saldo CU09, outbox notificaciones, suites `test_cu19`, `test_b3`, `test_notificaciones_outbox_e2`.
3. **Subagente 3 (`35b1bece-eb8b-467f-8c85-e4ff8e58caf0`) — Backend Analítica y Machine Learning (P0/P1/P2)**
   - *Ámbito exclusivo:* Pronóstico supervisado CU10, segmentación K-Means CU11, dashboard CU23, reportes interpretados CU24, ventas sucursal CU25, suite `test_b4`.
4. **Subagente 4 (`3331c4e2-be8f-43fe-ad79-ceb000daf907`) — Frontend Angular Compra y Caja (P0/P1)**
   - *Ámbito exclusivo:* Servicios de sincronización offline v3, tienda IndexedDB, módulo `ventas_pagos` (caja, checkout, pago, Stripe), pruebas unitarias Karma asociadas.
5. **Subagente 5 (`3dcba31d-68a0-4a7a-a8de-805a1a05db2f`) — App Móvil Flutter (P0/P1)**
   - *Ámbito exclusivo:* `lib/features/ventas_pagos/**`, `lib/features/posventa/**`, `lib/features/reservas_traslados/**`, navegación `CuentaScreen`, sincronización v3, notificaciones push, pruebas unitarias y de widgets.
6. **Subagente 6 (`58de47f7-2d61-4331-b748-7cba92c09a08`) — Frontend Angular Analítica y Posventa (P0/P1/P2)**
   - *Ámbito exclusivo:* Módulo `analitica` (inteligencia, dashboard, reportes), módulo `posventa` (operaciones, reembolsos, saldo), modelos y pruebas Karma correspondientes.

---

## 3. Resolución Detallada por Bloqueo de la Auditoría 18

### A. Bloqueo 1: Pagos Stripe (CU22) y SetupIntent Conectado
- **Observación de Auditoría 18:** Pagos simulados con bypass o client secrets ficticios sin persistencia durable de métodos ni cálculo de deuda en el servidor.
- **Correcciones implementadas:**
  - En `backend/app/core/modules/ventas_pagos/services/stripe_service.py` y `routers/pagos_stripe.py`:
    - Endpoint `POST /api/v1/pagos/stripe/metodos/preparar` emite un SetupIntent real (`seti_...`) asociado al cliente y huella de dispositivo, persistido en `comercial.metodos_preparados`.
    - Endpoint `POST /api/v1/pagos/stripe/ordenes` calcula la deuda real íntegramente en el servidor a partir de la venta o pedido, congela la tasa oficial vigente desde `plataforma.tasas_cambio`, y calcula los centavos exactos en USD sin confiar en valores aportados por el frontend.
    - Soporte off-session utilizando `metodo_preparado_id` con confirmación directa o transición contractual a `REQUIERE_ACCION_CLIENTE` (3DS).
    - Webhook `/api/v1/stripe/webhook` con firma HMAC-SHA256 y deduplicación idempotente en `comercial.eventos_proveedor`.
  - En `app-movil` (`checkout_screen.dart`, `pago_screen.dart`, `pago_service.dart`):
    - Conexión real con SetupIntent y órdenes de pago sin generación de aprobaciones locales artificiales.
  - En `frontend-web` (`checkout.component.ts`, `pago.component.ts`, `stripe.service.ts`):
    - Preparación de método de pago con almacenamiento seguro y modal de confirmación 3DS.
- **Contraejemplos verificados:** `test_cu22_01` a `test_cu22_07` en `test_b1_finanzas_cu09_cu22_cu27.py`.

### B. Bloqueo 2: Compra Offline v3 (CU05) y Protocolo 0.4.0
- **Observación de Auditoría 18:** La app móvil y web emitían `version_esquema: 1`, ignorando el esquema contractual v3 y la autorización de cobro diferido.
- **Correcciones implementadas:**
  - En `backend/app/core/modules/reservas_traslados/services/sincronizacion_service.py`:
    - Procesamiento de `SOLICITAR_COMPRA` bajo `version_esquema: 3`. Validación estricta del objeto `autorizacion_cobro` (consentimiento, método preparado, huella de dispositivo, vigencia).
    - Respuestas normalizadas: `ACEPTADA`, `PENDIENTE_INTERVENCION`, `REQUIERE_NUEVA_ACEPTACION` (si varió el precio de catálogo) y `REQUIERE_ACCION_CLIENTE`.
    - Si al sincronizar la compra no hay existencias físicas suficientes en la sucursal, se rechaza la venta sin registrar saldo negativo y se deriva inmediatamente una obligación de reembolso íntegro en CU27.
  - En `app-movil` (`sincronizacion_model.dart`, `sincronizacion_offline_service.dart`):
    - `SincronizacionModel` evalúa la presencia de `autorizacion_cobro` y emite dinámicamente `version_esquema: 3`.
  - En `frontend-web` (`sincronizacion-offline.service.ts`):
    - Generación de `version_esquema: 3` en compras diferidas con cola durable en IndexedDB.
- **Contraejemplos verificados:** `test_cu05_01` a `test_cu05_06` en `test_b2_compras_cu21_cu19_cu05.py`, `sincronizacion-offline.service.spec.ts` (8 passed) y `sincronizacion_compra_offline_test.dart`.

### C. Bloqueo 3: Liquidación en Caja Presencial (CU19)
- **Observación de Auditoría 18:** Liquidación presencial conectada confiaba en precios del cliente y carecía de medios de pago múltiples.
- **Correcciones implementadas:**
  - En `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py` y `routers/ventas_presenciales.py`:
    - `POST /api/v1/ventas/presenciales/liquidar` ejecuta bloqueo pesimista `with_for_update` sobre `inventario.inventario_sucursal` por cada variante.
    - El backend calcula precios vigentes, descuentos y promociones; no confía en precios del cliente.
    - Soporte pleno de medios de pago: `EFECTIVO` (con cálculo de vuelto exacto), `SALDO` (validando saldo personal disponible del cliente con retención/débito atómico) y `STRIPE_TEST`.
    - Emisión inmediata de comprobante comercial y movimiento de Kardex `VENTA_PRESENCIAL`.
  - En `frontend-web` (`caja.component.ts`, `caja.component.html`, `venta-presencial.models.ts`):
    - Selector de medios de pago `EFECTIVO`, `SALDO` y `STRIPE_TEST`. Actualización de totales y cambio a partir de la respuesta oficial del servidor (`VentaLiquidadaDTO`).
- **Contraejemplos verificados:** `test_cu19_01` a `test_cu19_06` en `test_cu19_caja_liquidacion.py` y suites de `caja.component.spec.ts`.

### D. Bloqueo 4: Plazos de Posventa (CU20, CU08) y Resolución Financiera
- **Observación de Auditoría 18:** El cómputo de 15 días se realizaba desde la fecha de creación de la venta y no desde la fecha de entrega efectiva, y no se admitían reclamos por defecto fuera de plazo.
- **Correcciones implementadas:**
  - En `backend/app/core/modules/posventa/services/devolucion_service.py` y `cambio_service.py`:
    - Validación del plazo voluntario de 15 días calculando la diferencia contra `entregada_en` (fecha de entrega efectiva) en lugar de `creada_en`.
    - Admisión de reclamos por vicio oculto o incumplimiento de entrega (`DEFECTO_FABRICACION`, `PRODUCTO_INCORRECTO`) fuera de los 15 días en estado `PENDIENTE_EVALUACION` sin rechazo automático.
    - En cambios (CU08), la resolución de la diferencia monetaria a favor del cliente es estrictamente excluyente: o `SALDO` o `REEMBOLSO`. Se rechaza con HTTP 400 cualquier intento de combinar ambos destinos simultáneamente.
  - En `frontend-web` (`operaciones.component.ts`, `operaciones.component.html`):
    - Método `diasDesdeEntrega(comp)` basado en `entregada_en`. Banner informativo cuando un reclamo por garantía ingresa en evaluación técnica autorizada.
- **Contraejemplos verificados:** `test_cu20_01` a `test_cu20_06` y `test_cu08_01` a `test_cu08_05` en `test_b3_posventa_cu20_cu08.py`.

### E. Bloqueo 5: Reembolsos Formales (CU27) y Conciliación
- **Observación de Auditoría 18:** Reembolsos no derivaban los pagos originales del servidor y podían mutar stock indebidamente.
- **Correcciones implementadas:**
  - En `backend/app/core/modules/posventa/services/reembolso_service.py`:
    - El servidor analiza los pagos originales de la venta (`comercial.pagos`) y deriva los componentes a reembolsar sin intervención manual del cliente.
    - La ejecución de reembolso Stripe opera en centavos sobre el cargo original (`pi_...`).
    - En ventas pagadas con saldo personal o mixtas, la porción de saldo se restaura exclusivamente como crédito en `comercial.movimientos_saldo` y no se convierte a efectivo.
    - No se muta el stock físico durante el reembolso (el inventario lo gestiona la inspección técnica o merma en CU20).
- **Contraejemplos verificados:** `test_cu27_01` a `test_cu27_06` en `test_b1_finanzas_cu09_cu22_cu27.py`.

### F. Bloqueo 6: Modelos ML y Analítica Comercial (CU10, CU11, CU23, CU24, CU25)
- **Observación de Auditoría 18:** Faltaban métricas formales de bondad de ajuste en ML (MAE, RMSE, R² y baseline), Silhouette Score en segmentación y desglose de dinero capturado en dashboard.
- **Correcciones implementadas:**
  - En `backend/app/core/modules/analitica/services/ml_service.py`:
    - CU10: Regresión lineal con cálculo de `mae`, `rmse`, `r2`, comparación contra `baseline_mae` persistente y porcentaje de mejora. Si no existen suficientes ventas históricas, devuelve estado honesto `DATOS_INSUFICIENTES` sin inventar proyecciones ficticias.
    - CU11: Agrupamiento K-Means con cálculo de inercia intra-clúster y Silhouette Score en rango [-1.0, 1.0].
    - Persistencia versionada de artefactos en `inteligencia.modelos_ml`.
  - En `dashboard_service.py` y `reporte_service.py`:
    - CU23: Indicador de `dinero_capturado` real, ventas brutas, descuentos, devoluciones y neto comercial.
    - CU24: 4 tipos tipados inmutables (`VENTAS_POR_SUCURSAL`, `RANKING_PRODUCTOS`, `EVOLUCION_SEMANAL`, `INGRESOS_POR_CATEGORIA`) con trazabilidad en `inteligencia.solicitudes_ia`.
    - CU25: Desglose por sucursal en huso horario boliviano (`America/La_Paz`, UTC-4).
  - En `frontend-web` (`inteligencia.component.ts`, `dashboard.component.ts`):
    - Pestañas editoriales de Pronóstico supervisado y Segmentación con métricas visibles y alertas transparentes de precisión.
- **Contraejemplos verificados:** `test_cu10_...`, `test_cu11_...`, `test_cu23_...`, `test_cu24_...`, `test_cu25_...` en `test_b4_analitica_cu25_cu23_cu24_cu10_cu11.py`.

### G. Bloqueo 7: Navegación Móvil hacia Posventa y Notificaciones
- **Observación de Auditoría 18:** Falta de enlace a posventa desde `CuentaScreen` y ausencia de modelos de notificación para el outbox.
- **Correcciones implementadas:**
  - En `app-movil`:
    - Enlace directo en `CuentaScreen` (`cuenta_screen.dart`) identificado con `Key('btn_posventa_garantias')` que navega a la ruta `/posventa`.
    - `PosventaScreen` (`posventa_screen.dart`) con pestañas para Saldo Personal (CU09), Devoluciones (CU20) y Cambios (CU08).
    - Modelos y servicio `NotificacionMovilService` para registro de dispositivos (`/api/v1/notificaciones/dispositivos`) y consumo de bandeja de avisos.
- **Contraejemplos verificados:** `posventa_widget_test.dart`, `notificacion_movil_service_test.dart` y `pago_service_e2_test.dart`.

---

## 4. Evidencia de Ejecución de Pruebas

### 4.1 Backend Pytest (FastAPI)
```powershell
$env:FASHIONSTORE_TEST_DATABASE_URL="postgresql+asyncpg://postgres:CLAVE_LOCAL@127.0.0.1:5432/fashionstore_test"
backend\venv\Scripts\python.exe -m pytest backend/tests_segundo_parcial_bloque_b -q
```
**Resultado:** `194 passed, 5 warnings in 155.36s (0:02:35)`
*Desglose:*
- `test_b1_finanzas_cu09_cu22_cu27.py`: 20 passed (Saldo, Stripe, Reembolsos)
- `test_b2_compras_cu21_cu19_cu05.py`: 17 passed (Pedidos, Sincronización v3, Reembolso derivado)
- `test_b3_posventa_cu20_cu08.py`: 15 passed (Plazos 15 días, Inspecciones, Notas de cambio)
- `test_b4_analitica_cu25_cu23_cu24_cu10_cu11.py`: 16 passed (ML supervisado/no supervisado, Dashboard, IA tipada)
- `test_cu19_caja_liquidacion.py`: 6 passed (Liquidación directa pesimista y medios mixtos)
- `test_notificaciones_outbox_e2.py`: 4 passed (Registro dispositivos y outbox)
- Suites preexistentes E1 Bloque B: 116 passed
- **Total Backend:** **194 passed (100%)**

### 4.2 Frontend Angular Karma y Build
```powershell
cd frontend-web
npm.cmd test -- --watch=false --progress=false
npm.cmd run build
```
**Resultado de pruebas:** `TOTAL: 242 SUCCESS` (242 pruebas unitarias pasando en ChromeHeadless).
**Resultado de build:** `Application bundle generation complete. [13.421 seconds]`, exit code 0, 0 errores de compilación TypeScript.

### 4.3 App Móvil Flutter
```powershell
cd app-movil
flutter analyze --no-pub
flutter test --no-pub
```
**Resultado de análisis:** `No issues found! (ran in 3.7s)`
**Resultado de pruebas:** `00:33 +213: All tests passed!` (213 pruebas unitarias y de widgets aprobadas).

---

## 5. Limitaciones Conocidas y Prerrequisitos Operativos

1. **Hardware físico Android para probador virtual Decart (CU17 / Ciclo 3):**
   - Aunque la arquitectura y los puentes nativos están fijados, la validación final de streaming bidireccional de baja latencia con Decart `lucy-2.5` requiere un dispositivo físico Android conectado vía ADB para evaluar la captura de cámara en tiempo real.
2. **Credenciales en vivo de Pasarela Stripe:**
   - En el entorno de pruebas automatizadas se utiliza `FakeStripeGateway` y las claves de prueba `STRIPE_TEST`. Para transacciones en producción o pruebas en navegadores reales, se requiere suministrar en `.env` una API key válida de Stripe (`sk_test_...`) y el secreto de webhook correspondiente (`whsec_...`).
3. **Persistencia de Sesión de Prueba en PostgreSQL:**
   - Los tests de backend asumen que la base de datos `fashionstore_test` contiene los roles del sistema (`seguridad.roles`), al menos una ciudad (`organizacion.ciudades`), los planes comerciales (`plataforma.planes`) y la empresa por defecto (`codigo = 'fashionstore'`).

---

## 6. Estado de los Casos de Uso del Segundo Parcial

De acuerdo con el ciclo de vida del proyecto, todos los 13 Casos de Uso de la Entrega 2 han superado las pruebas técnicas y quedan en estado **«Entregado para revisión / Canales verificados»**, a la espera de la inspección formal y aceptación por parte del propietario y auditoría Codex:

- **CU09 Saldo Personal:** Entregado para revisión / Canales verificados (B, W, M)
- **CU22 Pasarela Stripe Test:** Entregado para revisión / Canales verificados (B, W, M)
- **CU27 Reembolsos y Obligaciones:** Entregado para revisión / Canales verificados (B, W, M)
- **CU21 Carrito Durable y Pedidos:** Entregado para revisión / Canales verificados (B, W, M)
- **CU19 Venta Presencial Conectada:** Entregado para revisión / Canales verificados (B, W)
- **CU05 Compra Digital Diferida v3:** Entregado para revisión / Canales verificados (B, W, M)
- **CU20 Devoluciones e Inspección:** Entregado para revisión / Canales verificados (B, W, M)
- **CU08 Cambios de Prenda:** Entregado para revisión / Canales verificados (B, W, M)
- **CU25 Reporte Ventas por Sucursal:** Entregado para revisión / Canales verificados (B, W)
- **CU23 Dashboard Comercial Ejecutivo:** Entregado para revisión / Canales verificados (B, W)
- **CU24 Reportes Interpretados Asistidos:** Entregado para revisión / Canales verificados (B, W)
- **CU10 Pronóstico de Demanda Supervisado:** Entregado para revisión / Canales verificados (B, W)
- **CU11 Segmentación de Catálogo No Supervisada:** Entregado para revisión / Canales verificados (B, W)

---

## 7. Conformidad con Restricciones del Usuario

- **No commits:** No se realizó `git commit` en ningún repositorio.
- **No push / merge / deploy:** Ninguna rama fue enviada a remotos, fusionada ni desplegada.
- **Conservación de código:** Los cambios permanecen en el árbol de trabajo local en la rama `feature/sp2-e2-integral`.
- **Limpieza de diffs:** `git diff --check` ejecutado con éxito en los tres repositorios (cero errores de espacios en blanco).
