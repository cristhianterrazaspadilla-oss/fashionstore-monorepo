import '../../../core/network/api_client.dart';
import '../models/tasa_cambio_model.dart';

/// Servicio de Tasa de Cambio BOB/USD (CU12) para cotización y pagos.
class TasaCambioService {
  final ApiClient _api;

  TasaCambioService({ApiClient? api}) : _api = api ?? ApiClient();

  /// Obtiene la tasa de cambio BOB/USD vigente sin vigencias solapadas (CU12).
  Future<TasaCambioModel> obtenerTasaVigente() {
    return _api.get<TasaCambioModel>(
      '/plataforma/tasas-cambio/vigente',
      convertir: (j) =>
          TasaCambioModel.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  /// Cotiza un importe en Bolivianos a Dólares con redondeo central HALF_UP (CU12).
  Future<CotizacionMonedaModel> cotizar(double montoBob) {
    return _api.get<CotizacionMonedaModel>(
      '/plataforma/tasas-cambio/cotizar',
      query: {'monto_bob': montoBob.toStringAsFixed(2)},
      convertir: (j) =>
          CotizacionMonedaModel.fromJson((j as Map).cast<String, dynamic>()),
    );
  }
}
