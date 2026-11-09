import 'package:uuid/uuid.dart';

import '../models/traslado_model.dart';
import '../../../core/network/api_client.dart';

/// Traslados visibles para el cliente (contrato real).
///
/// - GET /traslados?reserva_id= (seguimiento)
/// - POST /traslados/solicitudes (reintento de línea rechazada con otro origen)
class TrasladoService {
  final ApiClient _api;
  TrasladoService({ApiClient? api}) : _api = api ?? ApiClient();

  Future<TrasladoLista> porReserva(String reservaId) {
    return _api.get<TrasladoLista>(
      '/traslados',
      query: {'reserva_id': reservaId, 'limit': '50', 'offset': '0'},
      convertir: (j) =>
          TrasladoLista.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  /// Reintenta una línea rechazada indicando otro origen.
  /// [clave] estable durante el reintento de esa línea.
  Future<Traslado> reintentarLinea({
    required String detalleReservaId,
    required String nuevoOrigenId,
    String? claveIdempotencia,
  }) {
    final clave = claveIdempotencia ?? const Uuid().v4();
    return _api.post<Traslado>(
      '/traslados/solicitudes',
      idempotencyKey: clave,
      cuerpo: {
        'detalle_reserva_id': detalleReservaId,
        'sucursal_origen_id': nuevoOrigenId,
      },
      convertir: (j) => Traslado.fromJson((j as Map).cast<String, dynamic>()),
    );
  }
}
