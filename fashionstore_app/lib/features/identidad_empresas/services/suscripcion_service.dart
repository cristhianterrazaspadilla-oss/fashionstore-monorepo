import '../../../core/network/api_client.dart';
import '../models/suscripcion_model.dart';

/// Servicio de Suscripciones y Capacidades de Empresa (CU02).
class SuscripcionService {
  final ApiClient _api;

  SuscripcionService({ApiClient? api}) : _api = api ?? ApiClient();

  /// Consulta la suscripción vigente y capacidades activas de la empresa (CU02).
  Future<SuscripcionEmpresaModel> consultarMiPlan({String? empresaId}) async {
    final query = (empresaId != null && empresaId.isNotEmpty)
        ? {'empresa_id': empresaId}
        : null;

    return _api.get<SuscripcionEmpresaModel>(
      '/empresas/mi-plan',
      query: query,
      convertir: (j) =>
          SuscripcionEmpresaModel.fromJson((j as Map).cast<String, dynamic>()),
    );
  }
}
