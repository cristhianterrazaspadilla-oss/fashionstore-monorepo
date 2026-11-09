// Modelos Ciclo 3 — Stripe Test como único método de pago (CU15).
//
// - POST /pagos/stripe/intenciones (Idempotency-Key) {venta_id}
// - POST /pagos/stripe/intenciones/reintento (Idempotency-Key) {venta_id}
// - GET /pagos/stripe/estado/{venta_id} (solo consulta, nunca confirma)
// La confirmación definitiva proviene del webhook y se refleja en el
// estado informado por backend. PaymentSheet nunca sustituye al backend.

double _aDouble(dynamic v, [double fb = 0]) {
  if (v == null) return fb;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? fb;
}

DateTime? _aFecha(dynamic v) {
  if (v == null) return null;
  if (v is DateTime) return v;
  return DateTime.tryParse(v.toString());
}

/// Estado del pago informado por backend (EstadoPagoDTO).
class EstadoPagoVenta {
  final String ventaId;
  final String estadoVenta;
  final String estadoPago;
  final String? paymentIntentId;
  final double monto;
  final DateTime? expiraEn;

  EstadoPagoVenta({
    required this.ventaId,
    required this.estadoVenta,
    required this.estadoPago,
    this.paymentIntentId,
    required this.monto,
    this.expiraEn,
  });

  factory EstadoPagoVenta.fromJson(Map<String, dynamic> j) => EstadoPagoVenta(
        ventaId: '${j['venta_id'] ?? ''}',
        estadoVenta: '${j['estado_venta'] ?? ''}',
        estadoPago: '${j['estado_pago'] ?? ''}',
        paymentIntentId: j['payment_intent_id']?.toString(),
        monto: _aDouble(j['monto']),
        expiraEn: _aFecha(j['expira_en']),
      );

  bool get pagoAprobado => estadoPago == 'APROBADO' || estadoVenta == 'PAGADA';
  bool get pagoRechazado => estadoPago == 'RECHAZADO';
  bool get pagoPendiente => estadoPago == 'PENDIENTE';
  bool get pagoAnulado => estadoPago == 'ANULADO';
  bool get ventaVencida =>
      estadoVenta == 'CANCELADA' || estadoPago == 'ANULADO';
}

/// Intención Stripe creada por backend (IntencionDTO).
class IntencionStripe {
  final String paymentIntentId;
  final String ventaId;
  final double monto;
  final String moneda;
  final String estado;
  final String? clientSecret;

  IntencionStripe({
    required this.paymentIntentId,
    required this.ventaId,
    required this.monto,
    required this.moneda,
    required this.estado,
    this.clientSecret,
  });

  factory IntencionStripe.fromJson(Map<String, dynamic> j) => IntencionStripe(
        paymentIntentId: '${j['payment_intent_id'] ?? ''}',
        ventaId: '${j['venta_id'] ?? ''}',
        monto: _aDouble(j['monto']),
        moneda: '${j['moneda'] ?? 'BOB'}',
        estado: '${j['estado'] ?? ''}',
        clientSecret: j['client_secret']?.toString(),
      );
}

/// Resultado visual del pago para la interfaz (derivado del backend).
enum ResultadoPago { pendiente, aprobado, rechazado, vencido }

ResultadoPago resultadoDesdeEstado(EstadoPagoVenta e) {
  if (e.pagoAprobado) return ResultadoPago.aprobado;
  if (e.pagoRechazado) return ResultadoPago.rechazado;
  if (e.ventaVencida) return ResultadoPago.vencido;
  return ResultadoPago.pendiente;
}
