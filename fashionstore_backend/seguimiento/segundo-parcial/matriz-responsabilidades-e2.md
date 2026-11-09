# Matriz de Asignación y Responsabilidad E2 — Post Auditoría 18

**Fecha:** 04/11/2026
**Objetivo:** Distribución exclusiva de archivos y casos de uso entre subagentes para resolver los bloqueos P0/P1/P2 identificados en la Auditoría 18 sin colisiones de escritura.

---

## Coordinador General
- **Archivos/Carpetas Propias:**
  - `backend/app/core/modules/reservas_traslados/schemas_sincronizacion.py`
  - `backend/app/api/v1/api.py`
  - `backend/contratos/segundo-parcial/openapi-segundo-parcial.json`
  - `backend/seguimiento/segundo-parcial/16-registro-contrato-ejecutable-e2.md`
  - `backend/seguimiento/segundo-parcial/02-estado-cu.md`
  - `backend/seguimiento/segundo-parcial/04-bitacora.md`
  - `backend/seguimiento/segundo-parcial/19-checkpoint-e2-post-auditoria-18.md`
- **Responsabilidad:** Registro de contratos, orquestación de subagentes, OpenAPI unificado, control de revisiones y verificación integral.

---

## Oleada 1: Backend Core y Correcciones Críticas P0/P1/P2

| Subagente | Casos de Uso | Archivos / Carpetas Exclusivas | Responsabilidad Técnica |
|---|---|---|---|
| **Subagente 1**<br>*(Pagos y Compra Digital Backend - P0)* | CU05, CU21, CU22, CU27 | - `backend/app/core/modules/reservas_traslados/services/sincronizacion_service.py`<br>- `backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>- `backend/app/core/modules/ventas_pagos/integraciones/stripe_gateway.py`<br>- `backend/app/core/modules/ventas_pagos/services/pedido_service.py`<br>- `backend/tests_segundo_parcial_bloque_b/test_b1_finanzas_cu09_cu22_cu27.py`<br>- `backend/tests_segundo_parcial_bloque_b/test_b2_compras_cu21_cu19_cu05.py` (secciones CU05/CU21) | Eliminar cobro inventado en sincronización v3. Integrar orden CU22 con método preparado y consentimiento; antes de captura, pedido pendiente sin compromiso de stock; tras captura, compromiso atómico o CU27 con saldo restaurado separadamente. Despacho v1/v2/v3 sin conversión automática de v1/v2. Pruebas que antes fallaban y ahora pasan. |
| **Subagente 2**<br>*(Caja y Posventa Backend - P0/P2)* | CU19, CU20, CU08, CU09 | - `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>- `backend/app/core/modules/posventa/services/devolucion_service.py`<br>- `backend/app/core/modules/posventa/services/cambio_service.py`<br>- `backend/app/core/modules/posventa/services/saldo_service.py`<br>- `backend/app/core/modules/posventa/services/reembolso_service.py`<br>- `backend/tests_segundo_parcial_bloque_b/test_b3_posventa_cu20_cu08.py`<br>- Pruebas CU19 (en suite o archivo complementario) | Liquidación real en CU19: eliminar `pass` en SALDO y STRIPE_TEST, calcular precios/descuentos en servidor (rechazar precios adulterados), esperar liquidación antes de entregar y emitir Kardex. En CU20/CU08: 15 días desde entrega real, registrar defecto/incumplimiento tardío para evaluación autorizada sin rechazo o reembolso automático. Nota 7 días y oferta 48h. |
| **Subagente 3**<br>*(Analítica y ML Backend - P0/P1)* | CU10, CU11, CU24, CU23, CU25 | - `backend/app/core/modules/analitica/services/ml_service.py`<br>- `backend/app/core/modules/analitica/services/ia_analitica_service.py`<br>- `backend/app/core/modules/analitica/routers/ml_modelos.py`<br>- `backend/app/core/modules/analitica/routers/ia_analitica.py`<br>- `backend/app/core/modules/analitica/services/reporte_service.py`<br>- `backend/app/core/modules/analitica/services/dashboard_service.py`<br>- `backend/tests_segundo_parcial_bloque_b/test_b4_analitica_cu25_cu23_cu24_cu10_cu11.py` | Eliminar métricas constantes y agrupación `i % k`. Regresor supervisado con baseline y validación temporal para CU10; clustering K-Means / estandarización real para CU11; dataset sintético versionado reproducible con semilla; persistencia de artefactos reales. Integración real con Gemini en CU24 si hay clave (1 de 4 tipos) o estado honesto si no; no auditar GEMINI sin llamada. |

---

## Oleada 2: Canales Frontend Web (Angular/PWA) y Móvil (Flutter)

| Subagente | Casos de Uso | Archivos / Carpetas Exclusivas | Responsabilidad Técnica |
|---|---|---|---|
| **Subagente 4**<br>*(Angular Compra y Caja)* | CU05, CU21, CU19, CU22 | - `frontend-web/src/app/features/ventas_pagos/**`<br>- `frontend-web/src/app/core/services/sincronizacion-offline.service.ts`<br>- `frontend-web/src/app/core/services/offline-store.service.ts` | PWA emite protocolo v3 con consentimiento, huella y método preparado; soporte cola durable y PENDIENTE_INTERVENCION; caja presencial conectada respetando precios calculados por servidor. |
| **Subagente 5**<br>*(Flutter Cliente y Navegación)* | CU05, CU08, CU09, CU20, CU21, CU22, CU27 | - `app-movil/lib/features/**`<br>- `app-movil/lib/main.dart`<br>- `app-movil/test/**` | Conectar PosventaScreen a navegación accesible (`CuentaScreen` / `main.dart`); checkout y pago móvil usando métodos reales; compra offline v3; bandeja/outbox/registro y push fake/código con reporte honesto. |
| **Subagente 6**<br>*(Angular Analítica y Posventa)* | CU10, CU11, CU23, CU24, CU25, CU20, CU08 | - `frontend-web/src/app/features/analitica/**`<br>- `frontend-web/src/app/features/posventa/**` | Conectar dashboard, pronóstico y segmentación a rutas E2 reales; filtros, fechas Bolivia, visualización de versiones/métricas ML, exportación y reportes IA. |
