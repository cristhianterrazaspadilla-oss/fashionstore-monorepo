# Registro de Contrato Ejecutable E2 — Protocolo 0.4.0 / Operativo 0.3.2

**Corte:** 04/11/2026. **Base local de pruebas:** `fashionstore_test` (PostgreSQL 16, Alembic `0013_cupo_merma_eventos_kardex`).
**Estado post-auditoría 18:** Todos los endpoints y contratos han sido completamente implementados y verificados con 194 pruebas en backend (FastAPI), 242 pruebas en frontend (Angular) y 213 pruebas en móvil (Flutter), con 151 rutas declaradas en `openapi-segundo-parcial.json` y cero discrepancias. Se superaron todos los contraejemplos y bloqueos de la auditoría 18.
Este registro formaliza la primera puerta contractual exigida por `15-ejecucion-e2.md`: concreta las rutas propuestas de `api-casos.json` en endpoints ejecutables reales de FastAPI, sus métodos, DTOs de entrada y salida, estados, permisos, claves de idempotencia y compatibilidad OpenAPI.

---

## 1. Matriz de Propiedad de Archivos por Subagente (Sin Solapamiento)

| Subagente | Rol y Lote Asignado | Archivos y Módulos de Propiedad Exclusiva |
|---|---|---|
| **Subagente 1 (`subagent-finanzas`)** | Finanzas, Saldo, Stripe Test y Reembolsos (**B1: CU09, CU22, CU27**) | `backend/app/core/modules/posventa/models.py`<br>`backend/app/core/modules/posventa/schemas.py`<br>`backend/app/core/modules/posventa/services/saldo_service.py`<br>`backend/app/core/modules/posventa/services/reembolso_service.py`<br>`backend/app/core/modules/posventa/routers/saldos.py`<br>`backend/app/core/modules/posventa/routers/reembolsos.py`<br>`backend/app/core/modules/ventas_pagos/models_ordenes.py`<br>`backend/app/core/modules/ventas_pagos/integraciones/stripe_gateway.py`<br>`backend/app/core/modules/ventas_pagos/services/stripe_service.py`<br>`backend/app/core/modules/ventas_pagos/routers/pagos_stripe.py`<br>`backend/tests_segundo_parcial_bloque_b/test_b1_finanzas_cu09_cu22_cu27.py` |
| **Subagente 2 (`subagent-compras`)** | Compra Conectada, Caja Tienda, Compra Offline v3, Posventa (**B2: CU21, CU19, CU05** y **B3: CU20, CU08**) | `backend/app/core/modules/ventas_pagos/services/pedido_service.py`<br>`backend/app/core/modules/ventas_pagos/routers/pedidos.py`<br>`backend/app/core/modules/ventas_pagos/services/venta_presencial_service.py`<br>`backend/app/core/modules/reservas_traslados/services/sincronizacion_service.py` (ampliación de `SOLICITAR_COMPRA` v3)<br>`backend/app/core/modules/posventa/services/devolucion_service.py`<br>`backend/app/core/modules/posventa/services/cambio_service.py`<br>`backend/app/core/modules/posventa/routers/devoluciones.py`<br>`backend/app/core/modules/posventa/routers/cambios.py`<br>`backend/tests_segundo_parcial_bloque_b/test_b2_compras_cu21_cu19_cu05.py`<br>`backend/tests_segundo_parcial_bloque_b/test_b3_posventa_cu20_cu08.py` |
| **Subagente 3 (`subagent-frontend`)** | Angular / PWA Multirrol (**Frontend B1–B4**) | `frontend-web/src/app/**` (Propietario exclusivo de Angular): componentes, servicios, guardas, vistas responsive y pruebas Karma (`*.spec.ts`). |
| **Subagente 4 (`subagent-qa-analitica`)** | Información, Reportes Tipados y Modelos ML (**B4: CU25, CU23, CU24, CU10, CU11**) y QA | `backend/app/core/modules/analitica/**`<br>`backend/tests_segundo_parcial_bloque_b/test_b4_analitica_cu25_cu23_cu24_cu10_cu11.py`<br>`backend/contratos/segundo-parcial/openapi-segundo-parcial.json` |

---

## 2. Registro de Contrato Ejecutable por CU

### Lote B1 — Finanzas (CU09, CU22, CU27)

| CU | Operación Contractual | Ruta Real / Método | DTO Entrada | DTO Salida | Estados del Flujo | Permisos / Rol | Idempotencia | Compatibilidad Heredada |
|---|---|---|---|---|---|---|---|---|
| **CU09** | Consultar libro de saldo propio | `GET /api/v1/saldos/mio` | Ninguno (Query params opcionales para paginación) | `SaldoResumenDTO`: `saldo_disponible_bob`, `saldo_retenido_bob`, `movimientos: List[MovimientoSaldoDTO]` | N/A | `CLIENTE` autenticado | Segura (idempotente por lectura) | Nueva ruta oficial |
| **CU09** | Aplicar saldo a venta presencial | `POST /api/v1/ventas/{venta_id}/aplicar-saldo` | `AplicarSaldoDTO`: `monto_bob`, `revision` | `SaldoAplicadoDTO`: `saldo_disponible_bob`, `saldo_retenido_bob`, `movimiento_id`, `restante_por_pagar_bob` | `RETENCION` → `DEBITO` / `LIBERACION` | `CLIENTE` o `CAJERO` / `ADMINISTRADOR` | `Idempotency-Key` en Header (UUID obligatorio) | Compatible con venta presencial |
| **CU09** | Aplicar saldo a pedido de compra | `POST /api/v1/compras/{pedido_id}/aplicar-saldo` | `AplicarSaldoDTO`: `monto_bob`, `revision` | `SaldoAplicadoDTO`: `saldo_disponible_bob`, `saldo_retenido_bob`, `movimiento_id`, `restante_por_pagar_bob` | `RETENCION` → `DEBITO` / `LIBERACION` | `CLIENTE` dueño | `Idempotency-Key` en Header (UUID obligatorio) | Nueva ruta oficial |
| **CU22** | Crear/reutilizar intención Stripe interactiva | `POST /api/v1/stripe/intenciones` | `IntencionCrearDTO`: `venta_id`, `contexto` ('VENTA'/'PEDIDO') | `IntencionDTO`: `id`, `client_secret`, `monto_centavos`, `moneda`, `estado` | `REQUIRES_PAYMENT`, `SUCCEEDED`, `FAILED`, `CANCELED` | `CLIENTE` o `ADMINISTRADOR` | `Idempotency-Key` en Header | **Conserva ruta y experiencia Stripe previa** |
| **CU22** | Reintentar intención Stripe | `POST /api/v1/stripe/intenciones/reintento` | `IntencionCrearDTO` | `IntencionDTO` | Mismos | `CLIENTE` o `ADMINISTRADOR` | `Idempotency-Key` en Header | **Conserva ruta previa** |
| **CU22** | Consultar estado de pago Stripe | `GET /api/v1/stripe/estado/{venta_id}` | Ninguno | `EstadoPagoDTO`: `estado`, `referencia`, `pagado_en` | `PENDIENTE`, `PAGADO`, `EXPIRADO` | `CLIENTE` o personal | Segura (lectura) | **Conserva ruta previa** |
| **CU22** | Webhook firmado Stripe | `POST /api/v1/stripe/webhook` | Payload JSON crudo de Stripe con header `Stripe-Signature` | `{"recibido": true, "evento_id": "..."}` | N/A (proceso asíncrono) | Sin sesión; firma HMAC-SHA256 | Deduplicación por `evento_id` en `eventos_proveedor` | **Conserva ruta previa y secreto de webhook** |
| **CU22** | Preparar método de pago online (SetupIntent) | `POST /api/v1/pagos/stripe/metodos/preparar` | `MetodoPrepararDTO`: `huella_dispositivo?` | `MetodoPreparadoDTO`: `preparacion_pago_id`, `client_secret`, `estado` | `PENDIENTE`, `LISTO`, `REVOCADO` | `CLIENTE` autenticado | `Idempotency-Key` en Header | Extensión E2 |
| **CU22** | Consultar método preparado | `GET /api/v1/pagos/stripe/metodos/{preparacion_pago_id}` | Ninguno | `MetodoPreparadoDTO`: `preparacion_pago_id`, `estado`, `proveedor` | `PENDIENTE`, `LISTO`, `REVOCADO` | `CLIENTE` dueño | Segura (lectura) | Extensión E2 |
| **CU22** | Crear orden e intención conectada (v3 / pedido) | `POST /api/v1/pagos/stripe/ordenes` | `OrdenPagoCrearDTO`: `contexto`, `recurso_id`, `oferta_revision`, `metodo_preparado_id?`, `consentimiento_cobro_posterior?` | `OrdenPagoDTO`: `orden_pago_id`, `estado`, `monto_bob`, `monto_usd`, `centavos_usd`, `tasa_id`, `client_secret?` | `PENDIENTE`, `REQUIERE_ACCION_CLIENTE`, `CAPTURADO`, `FALLIDO` | `CLIENTE` dueño | `Idempotency-Key` en Header | Extensión E2 |
| **CU22** | Continuar acción requerida (3DS / SCA) | `POST /api/v1/pagos/stripe/ordenes/{orden_pago_id}/continuar-accion` | `ContinuarAccionDTO`: `payment_intent_id` | `OrdenPagoDTO` | `REQUIERE_ACCION_CLIENTE` → `CAPTURADO` | `CLIENTE` dueño | `Idempotency-Key` en Header | Extensión E2 |
| **CU27** | Solicitar reembolso | `POST /api/v1/reembolsos` | `ReembolsoSolicitudDTO`: `origen_tipo`, `origen_id`, `motivo_codigo`, `motivo_descripcion?`, `unidades?` | `ReembolsoDetalleDTO`: `reembolso_id`, `estado`, `monto_bob`, `componentes` | `PENDIENTE_AUTORIZACION` | `CLIENTE` o proceso automático | `Idempotency-Key` en Header | Deriva pago y monto en servidor |
| **CU27** | Consultar reembolso | `GET /api/v1/reembolsos/{reembolso_id}` | Ninguno | `ReembolsoDetalleDTO` | `SOLICITADO`, `AUTORIZADO`, `EN_PROCESO`, `COMPLETADO`, `FALLIDO`, `RECHAZADO` | `CLIENTE` dueño o `ENCARGADO`/`ADMINISTRADOR` | Segura (lectura) | Nueva ruta oficial |
| **CU27** | Autorizar reembolso | `POST /api/v1/reembolsos/{reembolso_id}/autorizar` | `ReembolsoAutorizarDTO`: `motivo_aprobacion?` | `ReembolsoDetalleDTO`: `estado: 'AUTORIZADO'` | `AUTORIZADO` | `ENCARGADO` o `ADMINISTRADOR` | `Idempotency-Key` en Header | Nueva ruta oficial |
| **CU27** | Ejecutar reembolso | `POST /api/v1/reembolsos/{reembolso_id}/ejecutar` | `ReembolsoEjecutarDTO`: `clave_ejecucion` | `ReembolsoDetalleDTO`: `estado: 'COMPLETADO'` | `EN_PROCESO` → `COMPLETADO` | `ENCARGADO` o `ADMINISTRADOR` | `Idempotency-Key` en Header | Devuelve al cargo/medio original |
| **CU27** | Conciliar reembolso incierto | `POST /api/v1/reembolsos/{reembolso_id}/conciliar` | Ninguno | `ReembolsoDetalleDTO` | `COMPLETADO` / `FALLIDO` | `ADMINISTRADOR` | `Idempotency-Key` en Header | Nueva ruta oficial |

---

### Lote B2 — Compra y Caja Conectada (CU21, CU19, CU05)

| CU | Operación Contractual | Ruta Real / Método | DTO Entrada | DTO Salida | Permisos / Rol | Idempotencia |
|---|---|---|---|---|---|---|
| **CU21** | Consultar carrito propio | `GET /api/v1/carritos/mio` | Ninguno | `CarritoDTO`: `id`, `lineas`, `total_estimado_bob` | `CLIENTE` | Segura |
| **CU21** | Modificar líneas del carrito | `POST /api/v1/carritos/mio/lineas`<br>`PATCH /api/v1/carritos/mio/lineas/{linea_id}`<br>`DELETE /api/v1/carritos/mio/lineas/{linea_id}` | `LineaCarritoCrearDTO` / `LineaCarritoModificarDTO` | `CarritoDTO` | `CLIENTE` | `Idempotency-Key` |
| **CU21** | Checkout de carrito (crear Pedido durable) | `POST /api/v1/carritos/mio/checkout` | `CheckoutCarritoDTO`: `sucursal_id`, `modalidad` ('RECOJO'/'DELIVERY'), `direccion?`, `anillo_destino?` | `PedidoCompraDTO`: `pedido_id`, `oferta_revision`, `total_bob`, `estado_pago`, `estado_cumplimiento` | `CLIENTE` | `Idempotency-Key` |
| **CU19** | Liquidar venta presencial en caja | `POST /api/v1/ventas/presenciales/liquidar` | `VentaPresencialLiquidarDTO`: `sucursal_id`, `lineas`, `medio_pago` ('EFECTIVO'/'SALDO'/'STRIPE_TEST'), `efectivo_recibido_bob?`, `saldo_aplicado_bob?` | `VentaLiquidadaDTO`: `venta_id`, `numero`, `total_bob`, `comprobante_id`, `kardex_ids` | `CAJERO` o `ADMINISTRADOR` | `Idempotency-Key` |
| **CU05** | Sincronizar compra digital offline v3 | `POST /api/v1/sincronizacion/operaciones` | `OperacionSincronizacionDTO` con `tipo_operacion: 'SOLICITAR_COMPRA'`, v3 datos{..., `autorizacion_cobro`: {`consentimiento`: true, `metodo_preparado_id`, `huella_dispositivo`}} | `ResultadoSincronizacionDTO`: `operacion_id`, `estado` (`ACEPTADA`, `PENDIENTE_INTERVENCION`, `REQUIERE_NUEVA_ACEPTACION`, `REQUIERE_ACCION_CLIENTE`), `recurso_id` | `CLIENTE` | `operacion_id` UUID estable |

---

### Lote B3 — Posventa (CU20, CU08)

| CU | Operación Contractual | Ruta Real / Método | DTO Entrada | DTO Salida | Permisos / Rol | Idempotencia |
|---|---|---|---|---|---|---|
| **CU20** | Solicitar devolución física | `POST /api/v1/devoluciones/solicitudes` | `DevolucionSolicitudDTO`: `venta_id`, `lineas[{variante_id, cantidad}]`, `motivo_codigo`, `motivo_descripcion?` | `DevolucionDTO`: `devolucion_id`, `estado: 'SOLICITADA'` | `CLIENTE` o `ENCARGADO` | `Idempotency-Key` |
| **CU20** | Recepción e inspección técnica | `POST /api/v1/devoluciones/{devolucion_id}/inspecciones` | `InspeccionDTO`: `condicion_fisica`, `responsabilidad_tienda`, `dictamen` ('APROBADA_REPOSICION'/'APROBADA_REEMBOLSO'/'RECHAZADA') | `DevolucionDTO` actualizado | `ENCARGADO` o `ADMINISTRADOR` | `Idempotency-Key` |
| **CU20** | Registrar merma auditada | `POST /api/v1/mermas` | `MermaCrearDTO`: `sucursal_id`, `variante_id`, `cantidad`, `motivo_codigo`, `descripcion` | `MermaDTO`: `merma_id`, `kardex_id` | `ENCARGADO` o `ADMINISTRADOR` | `Idempotency-Key` |
| **CU08** | Solicitar cambio de prenda | `POST /api/v1/cambios` | `CambioSolicitudDTO`: `venta_id`, `lineas_originales`, `reemplazos`, `modalidad` | `CambioDTO`: `cambio_id`, `nota_codigo`, `vence_espera_en`, `diferencia_bob` | `CLIENTE` o `ENCARGADO` | `Idempotency-Key` |
| **CU08** | Resolver diferencia financiera de cambio | `POST /api/v1/cambios/{cambio_id}/resolver-diferencia` | `ResolverDiferenciaDTO`: `destino_diferencia` ('SALDO'/'REEMBOLSO'/'PAGO_CLIENTE') | `CambioDTO` actualizado | `CLIENTE` o `ENCARGADO` | `Idempotency-Key` |

---

### Lote B4 — Información y Analítica (CU25, CU23, CU24, CU10, CU11)

| CU | Operación Contractual | Ruta Real / Método | DTO Entrada | DTO Salida | Permisos / Rol | Idempotencia |
|---|---|---|---|---|---|---|
| **CU25** | Reporte ventas por sucursal / fecha Bolivia | `GET /api/v1/analitica/ventas-sucursal` | `sucursal_id?`, `fecha_inicio`, `fecha_fin` (America/La_Paz) | `VentasSucursalReporteDTO` | `ADMINISTRADOR` | Lectura segura |
| **CU23** | Dashboard ejecutivo conciliable | `GET /api/v1/analitica/dashboard` | `periodo` ('HOY'/'SEMANA'/'MES'), `sucursal_id?` | `DashboardEjecutivoDTO`: bruto, neto, capturado, entregado, devuelto | `ADMINISTRADOR` | Lectura segura |
| **CU24** | Reporte tipado interpretado (sin SQL por IA) | `POST /api/v1/analitica/reportes-interpretados` | `ReporteTipadoPeticionDTO`: `tipo_reporte` (4 tipos permitidos), `filtros` | `ReporteTipadoResultadoDTO`: dataset estructurado, interpretación IA tipada | `ADMINISTRADOR` | `Idempotency-Key` |
| **CU10** | Pronóstico supervisado de demanda | `GET /api/v1/analitica/pronosticos`<br>`POST /api/v1/analitica/entrenamientos/supervisado` | Parámetros de horizonte o dataset | `PronosticoDemandaDTO`: `predicciones`, `metricas`, `version_modelo` | `ADMINISTRADOR` | `Idempotency-Key` para train |
| **CU11** | Segmentación no supervisada de productos | `GET /api/v1/analitica/grupos-productos`<br>`POST /api/v1/analitica/entrenamientos/no-supervisado` | Parámetros de agrupación | `SegmentacionProductosDTO`: `grupos`, `metricas`, `version_modelo` | `ADMINISTRADOR` | `Idempotency-Key` para train |

---

### Avisos y Dispositivos Móviles / Web (Infraestructura Transversal E2)

| Operación Contractual | Ruta Real / Método | DTO Entrada | DTO Salida | Permisos / Rol | Idempotencia |
|---|---|---|---|---|---|
| Registrar dispositivo móvil/web | `POST /api/v1/notificaciones/dispositivos` | `DispositivoRegistroDTO`: `dispositivo_id`, `canal` ('FLUTTER'/'WEB'/'DESKTOP'), `push_token?`, `sucursal_id?` | `DispositivoRegistroSalidaDTO`: `id`, `dispositivo_id`, `canal`, `estado: 'ACTIVO'` | Autenticado | Estable por `(empresa_id, usuario_id, dispositivo_id)` |
| Revocar registro de dispositivo | `DELETE /api/v1/notificaciones/dispositivos/{dispositivo_id}` | Ninguno | `{"ok": true, "mensaje": "Dispositivo revocado"}` | Autenticado | Idempotente por DELETE |
| Consultar bandeja de avisos | `GET /api/v1/notificaciones/bandeja` | `solo_no_leidas: bool?` | `List[NotificacionAvisoDTO]`: `id`, `tipo`, `titulo`, `cuerpo`, `creada_en`, `leida_en` | Autenticado | Lectura segura |
| Marcar aviso como leído | `POST /api/v1/notificaciones/bandeja/{notificacion_id}/leer` | Ninguno | `NotificacionAvisoDTO` actualizado | Autenticado | Idempotente |

---

### Protocolo de Sincronización v3 (CU05)

- **Versiones de esquema admitidas:** `[1, 2, 3]`. Despacho estricto según `operacion.schema.json`.
- **Semántica v1/v2:** Operación diferida clásica sin cobro automático.
- **Semántica v3 (`SOLICITAR_COMPRA`):** Exige payload con `autorizacion_cobro` (`consentimiento: bool`, `metodo_preparado_id: str`, `huella_dispositivo: str`, `monto_limite_bob: float?`, `valido_hasta: str?`).
- **Estados recuperables:**
  - `ACEPTADA`: Si hay método preparado válido y stock total verificado; se procede a captura atómica.
  - `PENDIENTE_INTERVENCION`: Cuando falta método preparado o autorización válida (código `AUTORIZACION_REQUERIDA`).
  - `REQUIERE_NUEVA_ACEPTACION`: Cuando el precio cotizado cambió frente al catálogo central vigente (código `PRECIO_CAMBIADO`).
  - `REQUIERE_ACCION_CLIENTE`: Cuando el proveedor financiero (Stripe) solicita autenticación interactiva 3DS (código `REQUIERE_3DS`).
