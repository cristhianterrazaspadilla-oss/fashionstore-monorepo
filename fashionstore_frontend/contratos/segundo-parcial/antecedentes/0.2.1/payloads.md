# Payloads de integración propuestos

Versión 0.2.0. Son ejemplos normativos de **forma y significado**, con UUID/fechas/importes ilustrativos. No prueban que la ruta exista. Los campos de identidad en el cuerpo se contrastan con sesión, empresa y rol. Salvo indicación, cada escritura usa `Idempotency-Key` UUID, y un reintento idéntico conserva efecto y respuesta. Las operaciones de sincronización usan su `operacion_id` como clave estable.

## Reserva diferida

`POST /sincronizacion/operaciones`:

```json
{
  "version_esquema": 1,
  "operacion_id": "10000000-0000-4000-8000-000000000001",
  "tipo": "SOLICITAR_RESERVA",
  "creada_local_en": "2026-10-18T10:00:00-04:00",
  "empresa_id": "20000000-0000-4000-8000-000000000001",
  "usuario_id": "30000000-0000-4000-8000-000000000001",
  "dispositivo_id": "40000000-0000-4000-8000-000000000001",
  "secuencia_local": 1,
  "referencia_horaria_id": "50000000-0000-4000-8000-000000000001",
  "datos": {
    "sucursal_id": "60000000-0000-4000-8000-000000000001",
    "visita_en": "2026-10-18T14:00:00-04:00",
    "lineas": [{"variante_id": "70000000-0000-4000-8000-000000000001", "cantidad": 1}]
  }
}
```

Aceptada: `{"operacion_id":"10000000-0000-4000-8000-000000000001","estado":"ACEPTADA","codigo":"OK","recibida_en":"2026-10-18T10:02:00-04:00","aceptada_en":"2026-10-18T10:02:00-04:00","recurso_id":"80000000-0000-4000-8000-000000000001","detalle":"Reserva aceptada"}`. Vencida o sin stock: HTTP 200, `estado=RECHAZADA`, código respectivo, sin `recurso_id`. Incoherencia temporal: HTTP 200, `estado=CONFLICTO`, `codigo=TIEMPO_INCOHERENTE`, resultado durable sin apartado ni `recurso_id`. `GET /sincronizacion/operaciones/{operacion_id}` devuelve la misma respuesta durable al dueño autenticado.

## Compra diferida y pago

La compra usa el mismo envoltorio con `tipo=SOLICITAR_COMPRA` y `datos`:

```json
{
  "sucursal_id": "60000000-0000-4000-8000-000000000001",
  "lineas": [{"variante_id": "70000000-0000-4000-8000-000000000001", "cantidad": 1, "precio_visto_bob": "120.00"}]
}
```

Stock agotado: `estado=RECHAZADA`, `codigo=SIN_STOCK`, `faltantes=[{"variante_id":"...","cantidad_solicitada":1}]`; cliente muestra «Lo sentimos, el producto no se encuentra disponible». Precio cambiado: `estado=REQUIERE_ACEPTACION_PRECIO`, `codigo=PRECIO_CAMBIADO`, `revision`, `total_bob`, sin intención Stripe. `POST /compras/{operacion_id}/aceptar-precio`:

```json
{"revision": 2, "total_bob": "125.00"}
```

El backend revalida stock y revisión. Si todo sigue vigente responde `estado=PENDIENTE_PAGO`, `codigo=OK`, `venta_id`, `aceptada_en`, `total_bob`, `revision` y vencimiento del apartado; el apartado dura 60 minutos desde esa aceptación. Si cambió otra vez, devuelve precio/revisión nuevos sin cobrar. El cliente aplica saldo online si lo elige y confirma el importe restante. Solo entonces invoca el `POST /pagos/stripe/intenciones` existente con `venta_id` y muestra BOB, tasa BOB/USD y USD de la intención antes de confirmar. `GET /pagos/stripe/estado/{venta_id}` da el estado final confirmado por webhook/reconciliación; el retorno de Stripe no marca `PAGADA` por sí solo.

## Turno y venta de caja

`POST /cajas/turnos` (cajero/administrador de sucursal):

```json
{
  "caja_id": "90000000-0000-4000-8000-000000000001",
  "sucursal_id": "60000000-0000-4000-8000-000000000001",
  "cupos_solicitados": [{"variante_id": "70000000-0000-4000-8000-000000000001", "cantidad": 2}]
}
```

Respuesta 201: `turno_id`, `habilitacion_id`, `autorizada_en`, `vence_en` (ocho horas), `version_precios`, `cupos_concedidos` y `precios_autorizados` por variante/promoción. Solo se inicia venta offline tras guardar durablemente esta respuesta. Cada venta local pasa al comando `REGISTRAR_VENTA_CAJA` con `datos`:

```json
{
  "turno_id": "a0000000-0000-4000-8000-000000000001",
  "habilitacion_id": "b0000000-0000-4000-8000-000000000001",
  "version_precios": "turno-1",
  "vendida_local_en": "2026-10-18T11:00:00-04:00",
  "entregada_local_en": "2026-10-18T11:01:00-04:00",
  "lineas": [{"variante_id": "70000000-0000-4000-8000-000000000001", "cantidad": 1, "precio_autorizado_bob": "120.00"}],
  "total_bob": "120.00",
  "efectivo_recibido_bob": "120.00"
}
```

Si se recibe más efectivo, el cuerpo añade `cambio_entregado_bob`; su diferencia con `efectivo_recibido_bob` debe ser `total_bob`.

La respuesta central usa `estado=REGISTRADA_CENTRAL`, `codigo=OK`, `venta_id`, `aceptada_en` o `estado=CONCILIACION_REQUERIDA` con detalle de incidencia. Esta última **no** borra el registro local de efectivo/entrega. Cierre `POST /cajas/turnos/{turno_id}/cerrar` con `{ "revision": 3, "operaciones_sincronizadas": ["10000000-0000-4000-8000-000000000003"] }`; responde cupos usados/liberados y referencia de auditoría. Recuperación por pérdida de caja requiere ruta y operación supervisada de conteo, con actor, motivo, cantidades físicas y evidencia; no puede ser automática.

## Cambios, saldo y tasa

`POST /cambios`:

```json
{
  "venta_id": "c0000000-0000-4000-8000-000000000001",
  "sucursal_id": "60000000-0000-4000-8000-000000000001",
  "unidades_devueltas": [{"linea_venta_id": "d0000000-0000-4000-8000-000000000001", "cantidad": 1}],
  "reemplazos": [{"variante_id": "70000000-0000-4000-8000-000000000002", "cantidad": 1}]
}
```

Respuesta: `cambio_id`, `revision`, `valor_reconocido_bob`, `valor_reemplazo_bob`, `diferencia_bob`, `sentido_diferencia` (`CLIENTE_PAGA`, `SALDO_CLIENTE`, `SIN_DIFERENCIA`), estado y vencimiento del apartado de reemplazo. `POST /cambios/{id}/confirmar` recibe revisión aceptada y medio de pago; solo confirma entrega cuando diferencia a cargo del cliente está pagada. Si es favorable al cliente emite un movimiento de saldo personal una vez. `GET /saldos/mio` devuelve `{ "empresa_id": "...", "cliente_id": "...", "disponible_bob": "15.00", "movimientos": [...] }`; cada movimiento incluye ID, tipo, importe BOB, fecha y referencia. `POST /ventas/{id}/aplicar-saldo` recibe `{ "importe_bob": "10.00", "revision": 2 }` y responde importe reservado/usado/restante; saldo offline no se gasta.

`POST /plataforma/tasas-cambio` registra `{ "bob_por_usd": "6.9600", "vigente_desde": "...", "vigente_hasta": "...", "motivo": "..." }`. La cifra aquí es **ilustrativa**, no una cotización inicial aprobada. Una intención Stripe conserva `tasa_version`, `bob_por_usd`, `total_bob`, `total_usd`, fecha y redondeo. La configuración real debe cargarse antes de cobrar.

## Reportes, ML y notificaciones

`POST /reportes/consultar` y `/reportes/exportar` comparten consulta tipada:

```json
{
  "tipo": "VENTAS_SUCURSAL_PERIODO",
  "filtros": {"desde": "2026-10-01", "hasta": "2026-10-31", "sucursal_id": "60000000-0000-4000-8000-000000000001", "fecha_base": "ACEPTACION_CENTRAL"}
}
```

Tipos: `VENTAS_SUCURSAL_PERIODO`, `PRODUCTOS_MAS_MENOS`, `EVOLUCION_SEMANAL`, `VENTAS_CATEGORIA`. Respuesta común: `tipo`, `filtros_aplicados`, `generado_en`, `columnas`, `filas`, `totales` (`brutas_bob`, `descuentos_bob`, `cambios_devoluciones_bob`, `netas_bob`, `saldo_emitido_bob`, `saldo_usado_bob`). Exportar añade `formato` (`excel`, `csv`, `pdf`) y produce archivo del mismo conjunto de datos. `POST /reportes/interpretar` recibe `{ "texto": "..." }` (texto escrito o transcrito en web); devuelve `tipo` y filtros propuestos para revisión antes de consultar. Gemini nunca envía SQL ejecutable.

`GET /analitica/pronosticos` devuelve producto/sucursal, semana prevista, unidades, versión, periodo de entrenamiento, evaluación y origen de datos. `GET /analitica/grupos-productos` devuelve grupo, productos, rasgos y versión/métrica. Ambos responden `DATOS_INSUFICIENTES` en vez de inventar resultados cuando aplica. `GET /notificaciones/mias` devuelve elementos con `notificacion_id`, `tipo`, `recurso_id`, `creada_en`, `leida_en` opcional y enlace interno autorizado; FCM/Web Push transportan el ID, no el estado final ni datos sensibles. Los clientes reconsultan autenticados al abrir un aviso.

## Ejemplos y contratos que debe cerrar la primera presentación

La reserva diferida y su resultado de las secciones anteriores corresponden al actual CU04. TIEMPO_INCOHERENTE usa CONFLICTO; no se descarta el registro. La descarga CU03 debe exponer empresa/ámbito, fecha/versión y productos/variantes/precios/existencias conocidas. No incluir datos privados en la copia pública.

CU01 requiere datos de empresa y administrador inicial; CU02, plan/fechas/motivo y capacidades efectivas; CU13, registro de cliente o login por empresa; CU15, sucursales/tarifas autorizadas. Antes de fijar los campos concretos, cotejar sus schemas actuales y exportar OpenAPI desde el código implementado; estas entradas no contienen aún JSON Schema completo de esas APIs. No asumir que un texto de intención es un endpoint listo para consumir.

La reserva aceptada debe devolver vencimiento y referencia central consultable; una copia descargada de CU18 no confirma una cancelación. Añadir ejemplos reales de aceptación, rechazo, conflicto y reintento a partir de la implementación, sin secretos ni datos personales reales.
