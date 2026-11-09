// Servicio Ciclo 3 — Stripe Test como único pago (CU15).
//
// - Crear intención y reintento requieren Idempotency-Key.
// - Consultar estado es solo lectura con polling acotado desde la UI.
// - La aprobación definitiva proviene del webhook y se refleja en backend.
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../models/pago_model.dart';
import '../../../core/network/api_client.dart';

class PagoService {
  final ApiClient _api;
  PagoService({ApiClient? api}) : _api = api ?? ApiClient();

  Future<IntencionStripe> crearIntencion({
    required String ventaId,
    String? claveIdempotencia,
  }) {
    return _api.post<IntencionStripe>(
      '/pagos/stripe/intenciones',
      cuerpo: {'venta_id': ventaId},
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) =>
          IntencionStripe.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<IntencionStripe> reintentar({
    required String ventaId,
    String? claveIdempotencia,
  }) {
    return _api.post<IntencionStripe>(
      '/pagos/stripe/intenciones/reintento',
      cuerpo: {'venta_id': ventaId},
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) =>
          IntencionStripe.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<EstadoPagoVenta> consultarEstado(String ventaId) {
    return _api.get<EstadoPagoVenta>(
      '/pagos/stripe/estado/$ventaId',
      convertir: (j) =>
          EstadoPagoVenta.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  /// Prepara método con SetupIntent para cobros off-session (CU22).
  Future<Map<String, dynamic>> prepararMetodoSetupIntent({
    String? huellaDispositivo,
    String? claveIdempotencia,
  }) {
    return _api.post<Map<String, dynamic>>(
      '/pagos/stripe/metodos/preparar',
      cuerpo: {
        if (huellaDispositivo != null && huellaDispositivo.isNotEmpty)
          'huella_dispositivo': huellaDispositivo,
      },
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) => (j as Map).cast<String, dynamic>(),
    );
  }

  /// Crea orden de pago off-session o conectada Stripe (CU22).
  Future<Map<String, dynamic>> crearOrdenPago({
    String? contexto,
    String? recursoId,
    String? ventaId,
    String? pedidoCompraId,
    String? metodoPreparadoId,
    int? ofertaRevision,
    bool consentimientoCobroPosterior = false,
    double? montoBob,
    String? claveIdempotencia,
  }) {
    final ctx = contexto ?? (ventaId != null ? 'VENTA' : (pedidoCompraId != null ? 'PEDIDO' : 'VENTA'));
    final recId = recursoId ?? ventaId ?? pedidoCompraId ?? '';
    return _api.post<Map<String, dynamic>>(
      '/pagos/stripe/ordenes',
      cuerpo: {
        'contexto': ctx,
        'recurso_id': recId,
        'oferta_revision': ofertaRevision ?? 1,
        if (metodoPreparadoId != null && metodoPreparadoId.isNotEmpty)
          'metodo_preparado_id': metodoPreparadoId,
        'consentimiento_cobro_posterior': consentimientoCobroPosterior,
      },
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) => (j as Map).cast<String, dynamic>(),
    );
  }

  /// Consulta estado de una orden de pago (CU22).
  Future<Map<String, dynamic>> consultarOrdenPago(String ordenId) {
    return _api.get<Map<String, dynamic>>(
      '/pagos/stripe/ordenes/$ordenId',
      convertir: (j) => (j as Map).cast<String, dynamic>(),
    );
  }

  /// Recupera el PaymentIntent existente de una orden sin crear otro cargo.
  Future<Map<String, dynamic>> reanudarOrdenPago(String ordenId) {
    return _api.post<Map<String, dynamic>>(
      '/pagos/stripe/ordenes/$ordenId/reanudar',
      cuerpo: const {},
      convertir: (j) => (j as Map).cast<String, dynamic>(),
    );
  }

  /// Pide al backend consultar Stripe y aplicar la transición durable del pago.
  Future<Map<String, dynamic>> confirmarOrdenPago(String ordenId) {
    return _api.post<Map<String, dynamic>>(
      '/pagos/stripe/ordenes/$ordenId/confirmar',
      cuerpo: const {},
      convertir: (j) => (j as Map).cast<String, dynamic>(),
    );
  }

  /// Continúa una orden de pago tras confirmación de acción 3DS (CU22).
  Future<Map<String, dynamic>> continuarAccionOrden({
    required String ordenId,
    String? paymentIntentId,
    String? claveIdempotencia,
  }) {
    return _api.post<Map<String, dynamic>>(
      '/pagos/stripe/ordenes/$ordenId/continuar-accion',
      cuerpo: {
        if (paymentIntentId != null && paymentIntentId.isNotEmpty)
          'payment_intent_id': paymentIntentId,
      },
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) => (j as Map).cast<String, dynamic>(),
    );
  }

  /// Consulta un método preparado previamente online (CU22).
  Future<Map<String, dynamic>> consultarMetodoPreparado(String metodoId) {
    return _api.get<Map<String, dynamic>>(
      '/pagos/stripe/metodos/$metodoId',
      convertir: (j) => (j as Map).cast<String, dynamic>(),
    );
  }

  /// Confirma un método preparado en el backend (CU22).
  Future<Map<String, dynamic>> confirmarMetodoPreparado({
    required String metodoId,
    String? paymentMethodId,
  }) {
    return _api.post<Map<String, dynamic>>(
      '/pagos/stripe/metodos/$metodoId/confirmar',
      cuerpo: {
        if (paymentMethodId != null && paymentMethodId.isNotEmpty)
          'payment_method_id': paymentMethodId,
      },
      convertir: (j) => (j as Map).cast<String, dynamic>(),
    );
  }

  static const String kKeyMetodoPreparadoId = 'fs_metodo_preparado_id';
  static const String kKeyMetodoPreparadoEstado = 'fs_metodo_preparado_estado';

  /// Guarda localmente la referencia al método preparado verificado del cliente.
  Future<void> guardarMetodoPreparado({
    required String metodoId,
    required String estado,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(kKeyMetodoPreparadoId, metodoId);
    await prefs.setString(kKeyMetodoPreparadoEstado, estado);
  }

  /// Recupera el ID del método preparado guardado localmente.
  Future<String?> obtenerMetodoPreparadoIdLocal() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(kKeyMetodoPreparadoId);
  }

  /// Recupera el último estado guardado localmente del método preparado.
  Future<String?> obtenerMetodoPreparadoEstadoLocal() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(kKeyMetodoPreparadoEstado);
  }

  /// Limpia la referencia al método preparado guardado localmente.
  Future<void> limpiarMetodoPreparadoLocal() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(kKeyMetodoPreparadoId);
    await prefs.remove(kKeyMetodoPreparadoEstado);
  }

  /// Verifica si el método está LISTO en backend (online) o recupera el estado guardado.
  Future<Map<String, dynamic>?> verificarMetodoPreparadoCliente({String? metodoId}) async {
    try {
      final id = metodoId ?? await obtenerMetodoPreparadoIdLocal();
      if (id == null || id.isEmpty) return null;
      final info = await consultarMetodoPreparado(id);
      final estado = info['estado']?.toString();
      if (estado == 'LISTO') {
        await guardarMetodoPreparado(metodoId: id, estado: 'LISTO');
      }
      return info;
    } catch (_) {
      final id = metodoId ?? await obtenerMetodoPreparadoIdLocal();
      final estado = await obtenerMetodoPreparadoEstadoLocal();
      if (id != null && estado != null) {
        return {'preparacion_pago_id': id, 'estado': estado};
      }
      return null;
    }
  }
}
