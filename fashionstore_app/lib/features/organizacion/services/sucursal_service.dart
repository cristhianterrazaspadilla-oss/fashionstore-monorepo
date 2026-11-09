import '../models/organizacion_model.dart';
import '../../../core/network/api_client.dart';

/// Sucursales para elección de destino/origen (GET /sucursales).
class SucursalService {
  final ApiClient _api;
  SucursalService({ApiClient? api}) : _api = api ?? ApiClient();

  Future<List<SucursalModel>> listar() {
    return _api.get<List<SucursalModel>>(
      '/sucursales',
      convertir: (j) => ((j as List?) ?? [])
          .whereType<Map>()
          .map((e) => SucursalModel.fromJson(e.cast<String, dynamic>()))
          .toList(),
    );
  }
}
