// Servicio Ciclo 3 — IA de solo lectura para cliente (CU18/CU20).
//
// Recomendaciones y búsqueda por voz devuelven productos existentes con
// disponibilidad vigente. Nunca crean carrito, reserva ni venta.
import '../models/ia_model.dart';
import '../../../core/network/api_client.dart';

class IaService {
  final ApiClient _api;
  IaService({ApiClient? api}) : _api = api ?? ApiClient();

  Future<RecomendacionRespuesta> recomendaciones({
    int limite = 5,
    String? categoria,
    String? talla,
  }) {
    return _api.post<RecomendacionRespuesta>(
      '/ia/recomendaciones',
      cuerpo: {
        'limite': limite,
        if (categoria != null && categoria.isNotEmpty) 'categoria': categoria,
        if (talla != null && talla.isNotEmpty) 'talla': talla,
      },
      convertir: (j) =>
          RecomendacionRespuesta.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<InterpretacionBusqueda> interpretarBusqueda(String texto) {
    return _api.post<InterpretacionBusqueda>(
      '/ia/busqueda',
      cuerpo: {'texto': texto},
      convertir: (j) =>
          InterpretacionBusqueda.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<void> registrarNavegacion({
    required String evento,
    String? varianteId,
    String? productoId,
  }) async {
    await _api.post<Map<String, dynamic>>(
      '/ia/navegacion',
      cuerpo: {
        'evento': evento,
        if (varianteId != null) 'variante_id': varianteId,
        if (productoId != null) 'producto_id': productoId,
      },
      convertir: (j) => ((j as Map?) ?? {}).cast<String, dynamic>(),
    );
  }
}
