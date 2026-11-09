import '../models/compra_model.dart';
import '../../../core/network/api_client.dart';

/// Historial de compras del cliente (GET /clientes/{id}/compras, paginado).
class HistorialService {
  final ApiClient _api;
  HistorialService({ApiClient? api}) : _api = api ?? ApiClient();

  Future<HistorialCompras> historial({
    required String clienteId,
    int limit = 20,
    int offset = 0,
  }) {
    return _api.get<HistorialCompras>(
      '/clientes/$clienteId/compras',
      query: {'limit': '$limit', 'offset': '$offset'},
      convertir: (j) =>
          HistorialCompras.fromJson((j as Map).cast<String, dynamic>()),
    );
  }
}
