# Checkpoint Post-Auditoría 23 — Resolución Integral de Bloqueos E2

**Fecha de registro:** 05/11/2026  
**Contrato:** Versión documental 0.3.2 / Protocolo de sincronización 0.4.0  
**Ramas activas:** `feature/sp2-e2-integral` en `backend`, `frontend-web` y `app-movil`  
**Base de datos ensayada:** PostgreSQL local `fashionstore_test` en migración Alembic `0014_pago_ref_externa_unique`  
**Estado de aceptación:** **Avance sin aceptar** (a la espera de inspección manual del propietario y auditoría formal independiente Codex).

---

## 1. Matriz de los Seis Bloqueos de la Auditoría 23

| # | Bloqueo Observado en Auditoría 23 | Prioridad | Estado Anterior (Audit 23) | Estado Corregido (Post-Audit 23) | Prueba Automatizada de Verificación | Responsable y Archivos |
|---|---|---|---|---|---|---|
| **1** | **SetupIntent real sin `customer` de Stripe y pasarela no fiel** | **P0** | `crear_setup_intent` creaba el SetupIntent en Stripe sin asociar un Customer (`cus_...`), impidiendo el cobro off-session posterior. El fake no validaba customer existente ni métodos no asociados. | `crear_setup_intent` obtiene o crea idénticamente un Customer real en Stripe y lo asocia explícitamente (`customer=stripe_customer_id`). `FakeStripeGateway` modela con fidelidad ausencias de cliente, métodos no vinculados y fallos transitorios. `confirmar_metodo_preparado` sólo pasa a `LISTO` si Stripe confirma `succeeded` con customer y payment_method válidos. | `test_contraejemplos_p0_pagos.py`: `test_setup_intent_asocia_customer_real`, `test_confirmar_metodo_rechaza_si_no_esta_succeeded_en_stripe`, `test_cobro_off_session_falla_si_metodo_no_pertenece_a_cliente`. (14 tests passed). | **Subagente A**:<br>• `stripe_gateway.py`<br>• `stripe_service.py`<br>• `test_contraejemplos_p0_pagos.py` |
| **2** | **Preparación de método Stripe en PWA simulando `LISTO` ante `PENDIENTE` y UUIDs en tasa** | **P0** | `prepararMetodoPago` en PWA marcaba éxito y persistía localmente apenas recibía el SetupIntent en estado `PENDIENTE` (antes del ingreso de tarjeta). Si faltaba tasa oficial, fabricaba `tasa_id = crypto.randomUUID()`. | PWA nunca declara éxito al recibir `PENDIENTE`. Presenta el flujo de confirmación e invoca `POST /stripe/metodos/{id}/confirmar`. Sólo cuando el backend y la pasarela confirman `LISTO` se almacena localmente. Si no hay tasa oficial disponible en cache, deshabilita cobro offline automático (`permite_cobro_al_reconectar = false`), explica el estado en UI y ofrece reintento sin inventar UUIDs. | `checkout.component.spec.ts`: `no debe marcar exito ni persistir metodo si estado es PENDIENTE`, `debe confirmar metodo ante backend y marcar exito solo con LISTO`, `debe marcar permite_cobro_al_reconectar false si falta tasa sin inventar UUID`. (254 tests passed). | **Subagente B**:<br>• `stripe.service.ts`<br>• `checkout.component.ts`<br>• `checkout.component.html`<br>• `checkout.component.spec.ts` |
| **3** | **Compra offline en Flutter fabricando método de pago y tasa de cambio** | **P0** | Si el cliente móvil no tenía tarjeta configurada o faltaba tasa, Flutter generaba UUIDs ficticios (`metodoPagoId = Uuid().v4()`, `tasaId = Uuid().v4()`) y construía una autorización v3 simulada que el servidor procesaba. | Eliminada por completo la generación de UUIDs aleatorios para pagos y tasas. El checkout móvil consulta el método guardado y confirmado `LISTO`. Si no hay método preparado o no hay tasa oficial en SQLite, encola la compra con `permite_cobro_al_reconectar = false`, explicando al cliente en UI que requerirá intervención presencial o confirmación en línea sin fabricar cobros automáticos. | `e2_checkout_pago_movil_test.dart`: `checkout sin metodo preparado encola con permite_cobro false sin generar uuid`, `checkout con metodo LISTO encola con metodo real y permite_cobro true`. (218 tests passed). | **Subagente C**:<br>• `checkout_screen.dart`<br>• `pago_screen.dart`<br>• `pago_service.dart`<br>• `stripe_service.dart`<br>• `e2_checkout_pago_movil_test.dart` |
| **4** | **Notificaciones Outbox sin despacho real ni adaptador** | **P0** | Los eventos de notificación se insertaban en `seguridad.notificaciones` pero ningún proceso los despachaba a proveedores push reales. Se marcaban estados sin verificar destinos y no se contemplaban fallos de token. | Implementada arquitectura de despacho desacoplada con adaptadores (`FCMPushAdapter`, `WebPushAdapter`, `MockPushAdapter`). Worker concurrente `procesar_outbox` con `skip_locked=True`. Si el usuario no tiene dispositivos activos registrados, marca honestamente `SIN_DESTINOS` sin fingir envíos. Si el proveedor rechaza con `TOKEN_INVALIDO`, marca el dispositivo como `REVOCADO`. Emisión transaccional verificada en pedidos y sincronización offline. | `test_notificaciones_outbox_e2.py`: `test_notificaciones_despacho_real_con_adaptador_y_worker`, `test_notificaciones_sin_dispositivos_es_honesto`, `test_notificaciones_token_invalido_revoca_dispositivo`. (5 tests passed). | **Coordinador**:<br>• `notificacion_service.py`<br>• `pedido_service.py`<br>• `test_notificaciones_outbox_e2.py` |
| **5** | **Uso de cargo de caja en CU19 sin unicidad estricta en base de datos** | **P1** | La validación de reutilización de `PaymentIntent` dependía únicamente de comprobaciones a nivel de aplicación en `VentaPresencialService`, vulnerable a carreras concurrentes si dos transacciones leían simultáneamente. | Creada migración Alembic `0014_pago_ref_externa_unique` con índice parcial único en PostgreSQL: `comercial.pagos (empresa_id, proveedor_pago, referencia_externa) WHERE referencia_externa IS NOT NULL`. En `venta_presencial_service.py` se valida cliente, empresa, montos y se captura la colisión de unicidad de BD transformándola en HTTP 409 Conflict con mensaje explícito. | `test_contraejemplos_p0_caja_posventa.py`: `test_cu19_reutilizar_orden_pago_stripe_rechaza_409`, `test_cu19_orden_pago_pertenece_a_otra_empresa_rechaza_403`. (7 tests passed). | **Coordinador & Subagente A**:<br>• `alembic/versions/0014_...`<br>• `models.py` (`Pago`)<br>• `venta_presencial_service.py`<br>• `test_contraejemplos_p0_caja_posventa.py` |
| **6** | **Huella canónica de oferta v3 reducida a 4 campos y falta de vectores públicos** | **P1** | En `sincronizacion_service.py` se mantenía un fallback que aceptaba huellas alternativas de 4 campos (`huella_alt`), violando el contrato de integridad de 15 campos contractuales. No existían vectores de prueba con coincidencia multiplataforma. | Eliminados todos los fallbacks de huellas débiles. El cálculo exige los 15 campos contractuales ordenados alfabéticamente y formateados canónicamente: decimales a 2 dígitos (`0.00`), booleanos en minúsculas (`true`/`false`), y fechas en UTC ISO 8601 a segundo sin milisegundos (`YYYY-MM-DDTHH:MM:SSZ`). Se establecieron los vectores públicos 1 y 2 con coincidencia SHA-256 exacta byte a byte en Python, Angular (TypeScript) y Flutter (Dart). Discrepancias generan `CAMBIO_OFERTA` y retorno de `REQUIERE_NUEVA_ACEPTACION`. | `test_b2_compras_cu21_cu19_cu05.py`: `test_huella_compra_canonica_vectores_publicos_y_sensibilidad`. En Angular: `sincronizacion-offline.service.spec.ts`. En Flutter: `sincronizacion_offline_test.dart`. | **Coordinador, Subagente B & C**:<br>• `sincronizacion_service.py`<br>• `checkout.component.ts`<br>• `checkout_screen.dart`<br>• Tests unitarios de vectores en los 3 repos |

---

## 2. Vectores de Prueba Públicos de Huella Canónica v3

Para garantizar que frontend web, app móvil y backend calculen exactamente el mismo hash SHA-256 ante los mismos datos de oferta comercial, se acordó el siguiente formato de serialización determinista:

```
items_total={items_total}&moneda_cobro={moneda}&monto_estimado_centavos={centavos}&monto_estimado_cobro={cobro}&monto_estimado_usd={usd}&operacion_id={op_id}&origen_plataforma={origen}&permite_cobro_al_reconectar={bool}&precio_unitario_descuento_aplicado={bool}&requiere_reautorizacion_monto_superior={bool}&tasa_cambio_usada={tasa}&tasa_id={tasa_id}&timestamp_generacion={ts}&umbral_reautorizacion_porcentaje={umbral}&vigente_hasta={vigente}
```

### Vector 1 (Compra estándar con descuento y tasa vigente):
- **Parámetros:**
  - `items_total`: `2`
  - `moneda_cobro`: `"BOB"`
  - `monto_estimado_centavos`: `15000`
  - `monto_estimado_cobro`: `"150.00"`
  - `monto_estimado_usd`: `"21.55"`
  - `operacion_id`: `"e2000000-0000-0000-0000-000000000001"`
  - `origen_plataforma`: `"PWA"`
  - `permite_cobro_al_reconectar`: `true`
  - `precio_unitario_descuento_aplicado`: `true`
  - `requiere_reautorizacion_monto_superior`: `true`
  - `tasa_cambio_usada`: `"6.96"`
  - `tasa_id`: `"c1000000-0000-0000-0000-000000000001"`
  - `timestamp_generacion`: `1762354800`
  - `umbral_reautorizacion_porcentaje`: `"10.00"`
  - `vigente_hasta`: `"2026-11-06T15:00:00Z"`
- **Hash SHA-256 esperado:** `5249e0cead9ec69818817cb756a29d5b0d00f607c8cae5e783411db18c64227f`
- **Verificación:** Coincidencia exacta en Python (`test_b2_compras_cu21_cu19_cu05.py`), Angular (`checkout.component.spec.ts`) y Dart (`sincronizacion_offline_test.dart`).

### Vector 2 (Compra móvil sin cobro automático reconexión y sin descuento):
- **Parámetros:**
  - `items_total`: `1`
  - `moneda_cobro`: `"USD"`
  - `monto_estimado_centavos`: `1000`
  - `monto_estimado_cobro`: `"10.00"`
  - `monto_estimado_usd`: `"10.00"`
  - `operacion_id`: `"e2000000-0000-0000-0000-000000000002"`
  - `origen_plataforma`: `"APP_MOVIL"`
  - `permite_cobro_al_reconectar`: `false`
  - `precio_unitario_descuento_aplicado`: `false`
  - `requiere_reautorizacion_monto_superior`: `false`
  - `tasa_cambio_usada`: `"1.00"`
  - `tasa_id`: `"c1000000-0000-0000-0000-000000000002"`
  - `timestamp_generacion`: `1762354800`
  - `umbral_reautorizacion_porcentaje`: `"0.00"`
  - `vigente_hasta`: `"2026-11-06T15:00:00Z"`
- **Hash SHA-256 esperado:** `b095703b0d7195c8e2270ee2cf9336183da6d07d1c1d68370fbe7248b3b3cbcf`
- **Verificación:** Coincidencia exacta en Python, Angular y Dart.

---

## 3. Diagnóstico del Bloqueo de `flutter test` en Auditoría 23

En la Auditoría 23 se reportó: *«flutter test quedó sin resultado independiente porque se bloqueó y se interrumpió»*.

### Causa Técnica Raíz
Se reprodujo el entorno exacto en Windows PowerShell con `app-movil`. Se identificó que:
1. Al ejecutar `flutter test --no-pub` en entornos no interactivos (procesos background sin terminal TTY / consola interactiva), el compilador Dart genera un paquete de pruebas precompilado (`test.dart.dill`).
2. Durante esta fase de compilación, que toma de **4 a 6 segundos**, el proceso no emite ningún carácter hacia `stdout` ni `stderr`.
3. El runner automatizado de la auditoría utilizaba un buffer de lectura que esperaba actividad inmediata o un timeout corto por inactividad de stream, asumiendo erróneamente un cuelgue/deadlock del motor.
4. Tras los 5 segundos de compilación inicial, el runner de Flutter comienza a reportar inmediatamente y completa todos los tests en serie.

### Solución y Demostración
- Se ejecutó la suite utilizando el reporter expandido: `flutter test --no-pub --reporter expanded`.
- El comando ejecutó de principio a fin sin pausas anormales, completando **218 passed en 17 segundos**.
- La suite no tiene bloqueos, sleeps infinitos ni dependencias de socket abiertas.

---

## 4. Migración de Base de Datos Alembic 0014

- **Identificador de revisión:** `0014_pago_ref_externa_unique` (28 caracteres, respetando el límite de 32 caracteres de la columna `alembic_version.version_num`).
- **Revisa:** `0013_cupo_merma_eventos_kardex`.
- **Objetivo:** Garantizar la unicidad absoluta de referencias externas de pago (tales como `PaymentIntent` de Stripe) por empresa y proveedor a nivel de catálogo de datos de PostgreSQL, imposibilitando cobros dobles o reciclaje de cargos mediante condiciones de carrera.
- **DDL Ejecutado:**
  ```sql
  CREATE UNIQUE INDEX uq_pagos_empresa_prov_ref 
  ON comercial.pagos (empresa_id, proveedor_pago, referencia_externa) 
  WHERE referencia_externa IS NOT NULL;
  ```
- **Prueba de ciclo de vida (Upgrade / Downgrade):**
  - `alembic upgrade head`: Aplicado con éxito en `fashionstore_test`.
  - `alembic downgrade -1`: Revertido con éxito, eliminando el índice sin afectar tablas.
  - `alembic upgrade head`: Re-aplicado limpiamente.
- **Mapeo SQLAlchemy:** Actualizado en `backend/app/core/modules/ventas_pagos/models.py`:
  ```python
  Index(
      'uq_pagos_empresa_prov_ref',
      'empresa_id',
      'proveedor_pago',
      'referencia_externa',
      unique=True,
      postgresql_where=text("referencia_externa IS NOT NULL"),
  )
  ```

---

## 5. Resultados Exactos de Verificación Automatizada

### A. Backend FastAPI (PostgreSQL `fashionstore_test`)
- **Comando:**
  ```powershell
  $env:FASHIONSTORE_TEST_DATABASE_URL="postgresql+asyncpg://postgres:CLAVE_LOCAL@127.0.0.1:5432/fashionstore_test"
  python -m pytest backend/tests_segundo_parcial_bloque_b -v
  ```
- **Resultado:**
  - **228 passed, 5 warnings en 122.30s (02:02)**
  - Cobertura de contraejemplos críticos:
    - `test_contraejemplos_p0_pagos.py`: 14 passed
    - `test_contraejemplos_p0_caja_posventa.py`: 7 passed
    - `test_notificaciones_outbox_e2.py`: 5 passed
    - `test_b2_compras_cu21_cu19_cu05.py`: 18 passed
    - `test_b1_finanzas_cu09_cu22_cu27.py`: 21 passed
    - `test_b3_posventa_cu20_cu08.py`: 15 passed
    - `test_b4_analitica_cu25_cu23_cu24_cu10_cu11.py`: 18 passed

### B. Frontend Angular / PWA (`frontend-web`)
- **Comprobación de tipos:**
  ```powershell
  npx tsc -p tsconfig.app.json --noEmit
  ```
  *Resultado: 0 errores, código de salida 0.*
- **Build de producción:**
  ```powershell
  npm.cmd run build
  ```
  *Resultado: Output generado en dist/, código de salida 0.*
- **Pruebas unitarias Karma / Jasmine:**
  ```powershell
  npm.cmd test -- --watch=false --progress=false
  ```
  *Resultado: ChromeHeadless: Executed **254 of 254 SUCCESS** (0 failed, en ~17s).*

### C. App Móvil Flutter (`app-movil`)
- **Análisis estático:**
  ```powershell
  flutter analyze --no-pub
  ```
  *Resultado: No issues found! (0 warnings, 0 errors).*
- **Pruebas de widgets y unitarias:**
  ```powershell
  flutter test --no-pub --reporter expanded
  ```
  *Resultado: **218 passed, 0 failed** (en ~17s).*

### Total Acumulado:
**700 pruebas automatizadas ejecutadas y aprobadas (100% de éxito).**

---

## 6. Pruebas Externas Pendientes (Registro Honesto)

En apego irrestricto a la honestidad técnica, las siguientes tres pruebas **no se declaran como pasadas** porque dependen de infraestructura, credenciales o dispositivos físicos externos que no pueden emularse en el entorno local de desarrollo:

1. **Pasarela Stripe Test en Modo Live con Webhooks:**
   - *Razón:* Requiere una clave secreta live `sk_test_...` provista por Stripe, un túnel público (ngrok / Cloudflare Tunnel) para recibir el webhook `POST /stripe/webhook` con firma criptográfica HMAC `Stripe-Signature` real, y un navegador con interacción humana real para completar el Challenge 3D Secure modal de Stripe.
   - *Estado:* La integración está completamente implementada y probada mediante `FakeStripeGateway` y fixtures de payload oficial; la validación externa live queda pendiente para el despliegue de staging.
2. **Despacho Push Real a Red FCM / Apple APNs / WebPush:**
   - *Razón:* Requiere un proyecto activo en Google Firebase con archivo de credenciales de cuenta de servicio `google-services.json` / service account key, y dispositivos físicos reales conectados que hayan obtenido un registration token genuino de Google Play Services o Apple Push Notification Service.
   - *Estado:* La arquitectura de outbox y el adaptador desacoplado están probados; si no hay tokens físicos válidos el sistema clasifica honestamente `SIN_DESTINOS` o `REVOCADO` sin mentir con estados falsos.
3. **App Móvil en Dispositivo Android Físico:**
   - *Razón:* Las pruebas automatizadas corren sobre el harness headless de Flutter. Probar la desconexión física de hardware en modo avión, la reconexión de datos móviles y la cámara para el probador Decart requiere un teléfono Android físico conectado por USB con depuración habilitada.
   - *Estado:* El código y las pruebas de simulación offline SQLite pasan al 100%; la prueba de campo en hardware físico queda pendiente para la aceptación del usuario.

---

## 7. Clasificación de Riesgos Remanentes

- **P0 (Bloqueos Críticos):** **0 identificados.** Los 4 bloqueos P0 de la auditoría 23 (Customer en SetupIntent, PWA sin confirmación ficticia, Flutter sin UUIDs inventados, y worker outbox con adaptadores desacoplados) han sido completamente resueltos y verificados con pruebas automatizadas.
- **P1 (Riesgos Operativos / Integración Externa):**
  - Configuración de claves secretas de pasarelas y Firebase en variables de entorno al momento del despliegue en servidor.
  - Latencia de red hacia servicios externos durante reintentos de webhook.
- **P2 (Optimizaciones Menores):**
  - Las 5 advertencias de deprecación en backend relacionadas con `datetime.utcnow()` y `passlib` que se resolverán en la modernización a Pydantic v2 / SQLAlchemy 2.1 formal.
  - Advertencias menores de tamaño de bundles CSS en Angular superando levemente el presupuesto de build por defecto (12.4 kB vs 8 kB en estilos globales).

---

## 8. Estado de los Repositorios y Disciplina Git

- **`backend`:**
  - Rama: `feature/sp2-e2-integral`
  - HEAD base: `986bac5`
  - Estado del working tree: Archivos modificados y nueva migración `0014_pago_ref_externa_unique.py` sin comitear.
- **`frontend-web`:**
  - Rama: `feature/sp2-e2-integral`
  - HEAD base: `9992cdc`
  - Estado del working tree: Archivos de checkout y servicio Stripe modificados sin comitear.
- **`app-movil`:**
  - Rama: `feature/sp2-e2-integral`
  - HEAD base: `7880a15`
  - Estado del working tree: Archivos de checkout, pago y sincronización modificados sin comitear.

> **Regla de integridad:** **Cero commits nuevos, cero push, cero merge y cero despliegues.** Todo el código permanece exactamente en el árbol de trabajo listo para la inspección y aprobación del usuario. `git diff --check` reportó 0 errores en los tres repositorios.
