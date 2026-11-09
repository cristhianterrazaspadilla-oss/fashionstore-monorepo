# Checkpoint 22: Cierre Integral E2 y Levantamiento de Bloqueos de Auditoría 20

**Fecha de corte:** 05/11/2026  
**Ramas activas:** `feature/sp2-e2-integral` en `backend`, `frontend-web` y `app-movil`.  
**Base de datos local:** PostgreSQL `fashionstore_db` / `fashionstore_test` en revisión Alembic `0013_cupo_merma_eventos_kardex`.  
**Política de entrega y control de versiones:**  
- Se preservan intactos los commits autorizados de línea base (`backend`: `d548b94` / `986bac5`, `frontend-web`: `9992cdc`, `app-movil`: `7880a15`).  
- **Cero commits nuevos, cero push, cero merge, cero despliegues.** Todas las correcciones de este checkpoint quedan desestibadas en el árbol de trabajo (*working tree*) para revisión e inspección manual del usuario y la auditoría independiente.  
- Ningún caso de uso se declara "Aceptado" de manera autónoma; se acreditan formalmente como **«Entregado para revisión / Canales verificados»** con suites automáticas en verde y contraejemplos reproducibles.

---

## 1. Matriz de Levantamiento de Hallazgos de Auditoría 20

A continuación se detalla la resolución técnica, archivo modificado, regla de negocio implementada y contraejemplo automatizado para cada fila de la Auditoría Independiente 20 (`20-auditoria-independiente-post-checkpoint-19.md`):

| Prioridad | Caso de Uso | Hallazgo Original Auditoría 20 | Corrección Implementada | Archivos Modificados | Contraejemplo Automatizado |
|---|---|---|---|---|---|
| **P0** | **CU22, CU05** | `stripe_service.py` marcaba `MetodoPreparado` como `LISTO` apenas se creaba el SetupIntent, simulando IDs sin confirmar con Stripe ni recuperar un `PaymentMethod` real. `stripe_gateway.py` creaba PaymentIntent off-session sin enviar `payment_method` ni `customer`. | Se implementó el flujo real de SetupIntent: el método queda en `REQUIERE_CONFIRMACION_CLIENTE` o `PROCESANDO`. Se agregó endpoint `POST /stripe/metodos/{id}/confirmar` que consulta y verifica el estado real del SetupIntent ante Stripe, extrae el `payment_method_id` y `customer_id` reales antes de marcarlo como `LISTO`. El cobro off-session envía obligatoriamente `payment_method` y `customer` reales. | `backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/modules/ventas_pagos/integraciones/stripe_gateway.py`<br>`backend/app/core/modules/ventas_pagos/routers/pagos_stripe.py` | `test_contraejemplos_p0_pagos.py` |
| **P0** | **CU19, CU22** | `venta_presencial_service.py` aceptaba cualquier PaymentIntent `SUCCEEDED` sin validar cliente, empresa, moneda o centavos, y permitía que una misma orden capturada fuera reutilizada para liquidar múltiples ventas presenciales. | Se implementó validación estricta de orden en caja: verificación de titularidad por cliente y empresa, validación exacta de moneda (`BOB`), centavos y monto total. Se impone unicidad absoluta: si la orden de pago ya tiene asociada una venta (`orden.venta_id is not null`), se rechaza con HTTP 409 Conflict. Además, el stock sólo se descuenta tras verificar la captura exitosa y asociar la orden a la venta. | `backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>`backend/app/core/modules/ventas_pagos/models_ordenes.py` | `test_contraejemplos_p0_caja_posventa.py` (`test_caja_rechaza_reutilizacion_de_payment_intent_capturado`, `test_caja_valida_cliente_empresa_y_moneda_de_orden_stripe`) |
| **P0** | **CU05** | `schemas_sincronizacion.py` y `sincronizacion_service.py` aceptaban autorizaciones offline v3 parciales con campos omitidos, ignorando los 15 campos obligatorios del contrato JSON Schema `operacion.schema.json:394-468` y sin verificar `huella_compra`, cotización vigente o correspondencia con la oferta central. | Validación estricta de los 15 campos contractuales de `AutorizacionCobroV3DTO`. `sincronizacion_service.py` valida la huella SHA-256 canónica contra los datos del pedido y la tasa vigente. Valida que el `tasa_id` exista y esté vigente en la empresa. Si la autorización está incompleta o la huella/tasa no coinciden, la operación se clasifica en `PENDIENTE_INTERVENCION` sin ejecutar cobro ni descontar inventario. | `backend/app/core/modules/reservas_traslados/schemas_sincronizacion.py`<br>`backend/app/core/modules/reservas_traslados/services/sincronizacion_service.py` | `test_contraejemplos_p0_pagos.py` |
| **P0** | **CU22** | `stripe_service.py` permitía `payment_intent_id` alternativo ajeno a la orden y marcaba `CAPTURADO` sin verificar si Stripe devolvía `requires_action` (3DS). `stripe_gateway.py` devolvía `SUCCEEDED` fijo tras HTTP 2xx. | La confirmación exige coincidencia exacta con `orden.referencia_externa`. Se inspecciona exhaustivamente el campo `status` del gateway: si el estado es `requires_action`, la orden pasa a `REQUIERE_ACCION_CLIENTE` y no se muta el inventario ni el pedido. Sólo ante `succeeded` comprobado y monto exacto en centavos se transiciona a `CAPTURADO`. | `backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/modules/ventas_pagos/integraciones/stripe_gateway.py` | `test_contraejemplos_p0_pagos.py` |
| **P1** | **CU05 Móvil** | `checkout_screen.dart` en Flutter llamaba a `encolarCompraOffline` sin suministrar el objeto `autorizacionCobro`, provocando que `sincronizacion_model.dart` omitiera la emisión de la estructura v3. | Se actualizó `checkout_screen.dart` para construir los 15 campos requeridos de `autorizacionCobro` (incluyendo `tasa_id` real, cálculo canónico SHA-256 usando el paquete estándar `crypto`, desglose en Bs y USD, consentimientos y versión de condiciones). Se persiste en SQLite y se emite la operación v3 completa. | `app-movil/lib/features/ventas_pagos/checkout/checkout_screen.dart`<br>`app-movil/pubspec.yaml` | `app-movil/test/widget/e2_checkout_pago_movil_test.dart` |
| **P1** | **CU05 PWA** | `checkout.component.ts` en Angular utilizaba una función de dispersión no estándar autodenominada SHA-256 e inventaba el `tasa_id` con `crypto.randomUUID()`. | Se incorporó `obtenerTasaVigente()` en `OrganizacionService` para obtener el `tasa_id` y factor real del backend. Se implementó una función sincrónica estándar FIPS 180-4 SHA-256 en TypeScript para la generación de la huella canónica, vinculando los 15 campos v3 con la tasa oficial. | `frontend-web/src/app/features/organizacion/services/organizacion.service.ts`<br>`frontend-web/src/app/features/ventas_pagos/checkout/checkout.component.ts`<br>`frontend-web/src/app/features/ventas_pagos/checkout/checkout.component.spec.ts` | `npm test` (`checkout.component.spec.ts`) |
| **P1** | **CU05, CU22, Avisos** | `pedido_service.py` confirmaba pedidos sin notificaciones transaccionales; no existía consumidor del outbox transaccional para procesar avisos push y la operación durable no actualizaba su estado consultable tras resolución asíncrona. | Se implementó el consumidor `procesar_outbox()` en `NotificacionService` con bloqueo transaccional `with_for_update(skip_locked=True)`, control de reintentos, deduplicación e idempotencia. Se expuso `POST /api/v1/notificaciones/procesar-outbox`. Al confirmarse el pedido o derivarse a reembolso, se emiten eventos en outbox y se actualiza el estado durable de la operación consultable. | `backend/app/core/modules/identidad_empresas/services/notificacion_service.py`<br>`backend/app/core/modules/identidad_empresas/routers/notificaciones.py`<br>`backend/app/core/modules/ventas_pagos/services/pedido_service.py` | `test_notificaciones_outbox_e2.py` |
| **P1** | **CU05 Continuación** | `sincronizacion_service.py` respondía HTTP 409 ante cambios en el payload con el mismo `operacion_id`, impidiendo la reautorización tras `PENDIENTE_INTERVENCION` o `REQUIERE_NUEVA_ACEPTACION`. | Se habilitó la transición autorizada para operaciones en estado de intervención o requerimiento de nueva aceptación mediante correlación y versionado de revisión (`revision_operacion`), permitiendo resolver la compra sin duplicar cobros ni pedidos. | `backend/app/core/modules/reservas_traslados/services/sincronizacion_service.py` | `test_contraejemplos_p0_pagos.py` |
| **P1** | **CU20, CU08** | Reglas de posventa permisivas o mezcladas: cómputo de plazos desde venta y no desde entrega, falta de evaluación para defectos, y resolución simultánea no permitida de saldo y reembolso. | Cómputo estricto de 15 días desde `entregada_en`. Solicitudes por defecto técnico fuera de plazo entran obligatoriamente en `PENDIENTE_EVALUACION`. Las notas de cambio se limitan a 7 días y oferta de sustitución a 48h. Se impone exclusividad absoluta: o `SALDO` o `REEMBOLSO` (HTTP 400 en combinaciones mixtas simultáneas en la misma resolución de cambio). | `backend/app/core/modules/posventa/services/devolucion_service.py`<br>`backend/app/core/modules/posventa/services/cambio_service.py` | `test_contraejemplos_p0_caja_posventa.py` (`test_posventa_computa_plazo_estrictamente_desde_entrega_fisica`, `test_cambio_rechaza_resolucion_mixta_simultanea_saldo_y_reembolso`, `test_devolucion_por_defecto_pasa_a_pendiente_evaluacion`) |
| **P1** | **CU10, CU11, CU23, CU24, CU25** | Analítica con métricas fijas o no reproducibles, sin aislamiento de artefactos y simulación no declarada de Gemini. | Métricas recomputables y reproducibles (MAE, RMSE, R² y Silhouette Score entre -1 y 1). Estado honesto `DATOS_INSUFICIENTES` cuando las muestras son insuficientes. Proveedor honesto `GEMINI` vs `DETERMINISTA` sin simulación ficticia. Aislamiento estricto de artefactos temporales sin tocar `backend/artefactos/`. Agrupación temporal con zona horaria de Bolivia (`-04:00`). | `backend/app/core/modules/analitica/services/ml_service.py`<br>`backend/app/core/modules/analitica/services/ia_analitica_service.py`<br>`backend/app/core/modules/analitica/services/dashboard_service.py`<br>`backend/app/core/modules/analitica/services/reporte_service.py` | `test_analitica_reproducible.py` (8 pruebas reproducibles) |

---

## 2. Estado de Cierre de los 27 Casos de Uso

A continuación se resume el estado de los 27 casos de uso del sistema FashionStore al cierre de la intervención:

### Entrega 1 (14 Casos de Uso) — Línea Base Acreditada
1. **CU01 (Empresa):** B, W — Entregado para revisión / Canales verificados.
2. **CU13 (Sesión por empresa / Multitenant):** B, W, M — Entregado para revisión / Canales verificados.
3. **CU14 (Usuarios y roles):** B, W — Entregado para revisión / Canales verificados.
4. **CU02 (Suscripción y capacidades):** B, W, M — Entregado para revisión / Canales verificados.
5. **CU15 (Sucursales y tarifas delivery):** B, W, M — Entregado para revisión / Canales verificados.
6. **CU16 (Catálogo omnicanal):** B, W, M — Entregado para revisión / Canales verificados.
7. **CU03 (Descarga offline catálogo):** B, W, M — Entregado para revisión / Canales verificados.
8. **CU17 (Kardex físico y valoración CMP):** B, W — Entregado para revisión / Canales verificados.
9. **CU12 (Tasa BOB/USD determinista):** B, W, M — Entregado para revisión / Canales verificados.
10. **CU18 (Reservas presenciales):** B, W, M — Entregado para revisión / Canales verificados.
11. **CU26 (Expiración automática reservas):** B, W, M — Entregado para revisión / Canales verificados.
12. **CU04 (Reserva offline diferida):** B, W, M — Entregado para revisión / Canales verificados.
13. **CU06 (Turnos y cupos de caja):** B, W, M — Entregado para revisión / Canales verificados.
14. **CU07 (Ventas contado offline y arqueo):** B, W, M — Entregado para revisión / Canales verificados.

### Entrega 2 (13 Casos de Uso) — Bloqueos Levantados y Canales Verificados
15. **CU09 (Saldo a favor y monedero cliente):** B, W, M — Entregado para revisión / Canales verificados.
16. **CU22 (Pasarela Stripe off-session y 3DS):** B, W, M — Entregado para revisión / Canales verificados.
17. **CU27 (Reembolsos estructurados y reversiones):** B, W, M — Entregado para revisión / Canales verificados.
18. **CU21 (Carrito durable y ofertas versionadas):** B, W, M — Entregado para revisión / Canales verificados.
19. **CU19 (Venta presencial caja y liquidación):** B, W — Entregado para revisión / Canales verificados.
20. **CU05 (Compra offline diferida v3):** B, W, M — Entregado para revisión / Canales verificados.
21. **CU20 (Devoluciones, inspección y mermas):** B, W, M — Entregado para revisión / Canales verificados.
22. **CU08 (Cambios, notas de reemplazo y resolución):** B, W, M — Entregado para revisión / Canales verificados.
23. **CU25 (Reporte ventas por sucursal hora local):** B, W — Entregado para revisión / Canales verificados.
24. **CU23 (Dashboard gerencial dinero capturado):** B, W — Entregado para revisión / Canales verificados.
25. **CU24 (Reportes interpretados IA y fallback):** B, W — Entregado para revisión / Canales verificados.
26. **CU10 (Pronóstico demanda ML supervisado):** B, W — Entregado para revisión / Canales verificados.
27. **CU11 (Segmentación clientes/productos K-Means):** B, W — Entregado para revisión / Canales verificados.

---

## 3. Dependencias Externas Pendientes

Conforme al rigor de la auditoría y la honestidad técnica requerida, se declaran explícitamente las dependencias de infraestructura y terceros que no pueden completarse en entorno aislado local:

1. **Stripe Live / Webhooks con Clave Secreta en Tiempo Real:** Las pruebas automáticas validan la integración con `StripeGateway` en modo test y fakes que reproducen fielmente los contratos de `SetupIntent`, `PaymentMethod`, `PaymentIntent` con `succeeded`, `requires_action` y 3DS. La recepción de webhooks de producción con firma criptográfica HMAC en vivo (`Stripe-Signature`) requiere el servicio de pasarela real accesible vía webhook URL pública.
2. **Firebase Cloud Messaging (FCM) / Notificaciones Push Nativas:** El mecanismo durable de outbox transaccional (`comercial.eventos_outbox` y `comercial.notificaciones`) y su consumidor concurrente `procesar_outbox(skip_locked=True)` están implementados y verificados en backend. El despacho final a dispositivos físicos depende de credenciales FCM de producción y dispositivos con Google Play Services activos.
3. **Cuota y Conexión de Producción de Google Gemini API:** El servicio de IA analítica (`ia_analitica_service.py`) y sus 4 modalidades contractuales cuentan con sanitización, auditoría y fallback determinista riguroso. El modo `GEMINI` en vivo requiere una clave `GEMINI_API_KEY` con cuota disponible y conectividad hacia Google AI Studio.
4. **Pruebas en Hardware Móvil Físico (Android/iOS):** Las 213 pruebas unitarias y de widgets de Flutter verifican completamente la persistencia en SQLite, el hashing SHA-256 canónico, la formulación de los 15 campos de la autorización v3 y la navegación hacia el checkout y la posventa. La prueba con cámara en tiempo real para el probador Decart (CU17) y la reconexión de red celular física requieren un terminal físico.

---

## 4. Estado del Contrato OpenAPI

El archivo de contrato `backend/contratos/segundo-parcial/openapi-segundo-parcial.json` refleja con exactitud las rutas y esquemas de la aplicación FastAPI, registrando cero discrepancias frente a `app.openapi()`.


---

## 5. Evidencia de Verificación Técnica Integrada

1. **Backend FastAPI (`backend`):**
   - **Comando:** `python -m pytest tests_segundo_parcial_bloque_b -q` con `$env:FASHIONSTORE_TEST_DATABASE_URL="postgresql+asyncpg://postgres:CLAVE_LOCAL@127.0.0.1:5432/fashionstore_test"`.
   - **Resultado:** **218 passed, 4 warnings en 135.91s (100% de éxito)**.
   - **Nuevas suites:** `test_contraejemplos_p0_pagos.py` (9 passed), `test_contraejemplos_p0_caja_posventa.py` (6 passed), `test_analitica_reproducible.py` (8 passed), `test_notificaciones_outbox_e2.py` (3 passed).
2. **Frontend Web Angular / PWA (`frontend-web`):**
   - **TypeScript:** `npx.cmd tsc --noEmit` -> **0 errores**.
   - **Pruebas unitarias Karma:** `npm.cmd test -- --watch=false --progress=false` -> **242 SUCCESS, 0 FAILED** en ChromeHeadless.
   - **Compilación de producción:** `npm.cmd run build` -> **Application bundle generation complete (9.38s)** con Exit code 0.
3. **App Móvil Flutter (`app-movil`):**
   - **Análisis estático:** `flutter analyze --no-pub` -> **No issues found! (ran in 4.3s)**.
   - **Pruebas automáticas:** `flutter test --no-pub` -> **213 passed, 0 failed** (126 unit + 87 widget en 24s).
4. **Total acumulado del sistema:** **673 pruebas automáticas superadas al 100%**.
