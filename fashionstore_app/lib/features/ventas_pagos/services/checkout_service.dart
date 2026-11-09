// Servicio Ciclo 3 — Checkout digital MOVIL (CU14) y venta pendiente.
//
// POST /carritos/mio/checkout?canal=MOVIL crea venta PENDIENTE_PAGO con
// compromiso de 60 minutos. GET /ventas/{id} consulta la venta.
import 'package:uuid/uuid.dart';

import '../models/checkout_model.dart';
import '../../../core/network/api_client.dart';

class CheckoutService {
  final ApiClient _api;
  CheckoutService({ApiClient? api}) : _api = api ?? ApiClient();

  Future<CheckoutRespuesta> confirmar({
    required CheckoutCrear datos,
    String? claveIdempotencia,
  }) {
    return _api.post<CheckoutRespuesta>(
      '/carritos/mio/checkout',
      query: const {'canal': 'MOVIL'},
      cuerpo: datos.toJson(),
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) =>
          CheckoutRespuesta.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  /// Consulta el pedido durable creado por CU21. El cliente nunca transforma
  /// este identificador en un venta_id: CU22 cobra el recurso PEDIDO.
  Future<CheckoutRespuesta> obtenerPedido(String pedidoId) {
    return _api.get<CheckoutRespuesta>(
      '/compras/$pedidoId',
      convertir: (j) =>
          CheckoutRespuesta.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<VentaDigital> obtenerVenta(String ventaId) {
    return _api.get<VentaDigital>(
      '/ventas/$ventaId',
      convertir: (j) =>
          VentaDigital.fromJson((j as Map).cast<String, dynamic>()),
    );
  }
}
