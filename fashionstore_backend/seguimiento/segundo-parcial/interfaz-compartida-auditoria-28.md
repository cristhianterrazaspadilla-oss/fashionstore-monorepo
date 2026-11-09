# Interfaz Compartida y Acuerdos de Arquitectura — Auditoría 28

**Fecha de emisión:** 05/11/2026  
**Ámbito:** Coordinador, Subagente A (Backend CU19/Stripe), Subagente B (Angular/PWA), Subagente C (Flutter/Android).  
**Base contractual:** Contrato 0.3.2 / Protocolo 0.4.0 / `operacion.schema.json:394-468`.

---

## 1. Esquema v3 Exacto (`autorizacion_cobro`)

El objeto `datos.autorizacion_cobro` dentro de una operación `SOLICITAR_COMPRA` con `version_esquema: 3` debe contener **exactamente 15 campos contractuales**, sin alias ni campos adicionales:

| # | Campo | Tipo | Restricción / Formato |
|---|---|---|---|
| 1 | `consentimiento_id` | UUID string | Identificador único del consentimiento otorgado |
| 2 | `aceptado_local_en` | ISO 8601 datetime | Fecha/hora local con zona (UTC o -04:00) |
| 3 | `huella_compra` | SHA-256 hex | 64 caracteres hexadecimales en minúsculas |
| 4 | `base_bob` | Decimal string | Formato `"0.00"` |
| 5 | `descuento_bob` | Decimal string | Formato `"0.00"` |
| 6 | `envio_bob` | Decimal string | Formato `"0.00"` |
| 7 | `total_bob` | Decimal string | Formato `"0.00"` |
| 8 | `moneda_cobro` | Literal string | `"USD"` (**OBLIGATORIO** en DTO sin valor por defecto) |
| 9 | `importe_cobro` | Decimal string | Formato `"0.00"` equivalente en USD |
| 10 | `tasa_id` | UUID string | Identificador de la tasa de cambio vigente |
| 11 | `tasa_bob_por_usd` | Decimal string | Patrón numérico decimal positivo |
| 12 | `condiciones_version` | String | Versión de términos aceptados (no vacía) |
| 13 | `vigente_hasta` | ISO 8601 datetime | Vencimiento del consentimiento |
| 14 | `preparacion_pago_id` | UUID string | Identificador del método preparado `LISTO` |
| 15 | `permite_cobro_al_reconectar` | Boolean | `true` constante |

### Reglas estrictas:
- **Prohibido:** Cualquier campo extra (`consentimiento`, `metodo_preparado_id`, `huella_dispositivo`) debe ser rechazado con HTTP 422 (`extra="forbid"`).
- **Omisión de autorización:** Si el cliente no cuenta con método `LISTO`, tasa oficial vigente o consentimiento de la oferta, se encola la operación `SOLICITAR_COMPRA` con `version_esquema: 3` y sin la clave `autorizacion_cobro` (o `autorizacion_cobro: null`).
  - **PROHIBIDO** degradar a `version_esquema: 1`.
  - El backend persiste la solicitud en `PENDIENTE_INTERVENCION` sin intentar ningún cargo financiero.

---

## 2. Estados de Método, Orden y Venta

- **Método Preparado (`MetodoPreparado`):**
  - Estados: `PENDIENTE` → `LISTO` → `REVOCADO`.
- **Orden de Pago Stripe (`OrdenPago`):**
  - Estados: `PENDIENTE` → `REQUIERE_ACCION_CLIENTE` → `CAPTURADO` / `FALLIDO` / `CANCELADO`.
- **Venta Presencial (`Venta`):**
  - Ciclo Stripe: La venta se inicia en estado `PENDIENTE_PAGO` con sus líneas y total congelados.
  - La orden Stripe se emite para ese exacto `venta_id`.
  - Al capturar la orden Stripe, la liquidación valida que `orden.venta_id == venta.id` de forma inmutable.
  - La liquidación descuenta stock con bloqueo pesimista `with_for_update()`, pasa la venta a `PAGADA`, emite comprobante y registra Kardex `VENTA_PRESENCIAL`.
  - **PROHIBIDO:** Reasignar `orden_stripe.venta_id` a otra venta.

---

## 3. Endpoints de Caja y Stripe (CU19)

### 3.1. Iniciar Venta Presencial Stripe
- **Ruta:** `POST /api/v1/ventas/presenciales/iniciar-stripe`
- **Header:** `Idempotency-Key: <UUID>`
- **Cuerpo solicitud:**
  ```json
  {
    "sucursal_id": "UUID",
    "cliente_id": "UUID | null",
    "turno_caja_id": "UUID | null",
    "lineas": [
      {
        "variante_id": "UUID",
        "cantidad": 1,
        "precio_unitario_bob": 100.0,
        "descuento_bob": 0.0
      }
    ]
  }
  ```
- **Respuesta (201 Created):**
  ```json
  {
    "venta_id": "UUID",
    "orden_pago_id": "UUID",
    "stripe_payment_intent_id": "pi_...",
    "client_secret": "pi_..._secret_...",
    "monto_bob": "100.00",
    "monto_usd": "14.37",
    "centavos_usd": 1437,
    "tasa_bob_por_usd": "6.96",
    "estado_orden": "PENDIENTE"
  }
  ```

### 3.2. Liquidar Venta Presencial
- **Ruta:** `POST /api/v1/ventas/presenciales/liquidar`
- **Header:** `Idempotency-Key: <UUID>`
- **Cuerpo solicitud para STRIPE_TEST:**
  ```json
  {
    "venta_id": "UUID",
    "sucursal_id": "UUID",
    "cliente_id": "UUID | null",
    "turno_caja_id": "UUID | null",
    "lineas": [...],
    "medio_pago": "STRIPE_TEST",
    "orden_pago_id": "UUID",
    "stripe_payment_intent_id": "pi_..."
  }
  ```
- **Validación del backend:**
  - `orden_stripe.venta_id == venta.id` (estrictamente la misma venta; no reasignación).
  - `orden_stripe.estado == "CAPTURADO"`.
  - `orden_stripe.monto_bob == venta.total`.
  - Descuento de stock bajo `with_for_update()`, paso a `PAGADA`, comprobante y Kardex.
  - Para `EFECTIVO` y `SALDO`: continúa admitiendo venta directa o venta iniciada sin orden externa.

---

## 4. Resultado por Destino del Outbox

- **Aislamiento por destino:** Cada evento en `notificaciones.eventos_outbox` rastrea el resultado individual por destino en `detalles_entrega`.
- **Estados de evento global:**
  - Si todos los destinos resultan `ACEPTADO` → `estado = "ENVIADO"`.
  - Si un destino resulta `ACEPTADO` y otro falla:
    - Con `intentos < 3`: `estado = "REINTENTO"`. En reintentos posteriores, **SOLO** se despacha a los destinos que NO fueron aceptados. **PROHIBIDO re-enviar a destinos ya aceptados**.
    - Con `intentos >= 3`: `estado = "FALLIDO"` (con indicación de entrega parcial agotada y destino fallido identificado). **PROHIBIDO marcar `ENVIADO` si algún destino quedó sin entregar**.
  - Si todos fallan y agota reintentos → `estado = "FALLIDO"`.

---

## 5. Configuración Pública y Protocolo Web Push

- **Consulta de clave pública:**
  - `GET /api/v1/notificaciones/web-push/config` → `{"public_key": "<VAPID_PUBLIC_KEY>"}`
- **Registro de suscripción:**
  - `POST /api/v1/notificaciones/web-push/subscripcion`
  - Cuerpo: `{"endpoint": "https://...", "keys": {"p256dh": "...", "auth": "..."}}`
- **Protocolo de envío Web Push:**
  - Cabeceras VAPID firmadas con ES256 conforme a RFC 8292.
  - Cifrado del payload mediante RFC 8291 `aes128gcm` utilizando las claves `p256dh` y `auth`.
  - Validación de HTTPS y protección contra destinos privados/internos (SSRF).
  - Si falta configuración: retorno honesto de `PushResult(exito=False, codigo="NO_CONFIGURADO")`.
- **Protocolo de envío FCM:**
  - Autenticación OAuth2 de cuenta de servicio de Google con scope `https://www.googleapis.com/auth/firebase.messaging`.
  - Si falta configuración: retorno honesto de `PushResult(exito=False, codigo="NO_CONFIGURADO")`.
