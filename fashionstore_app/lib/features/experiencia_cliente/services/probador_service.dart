// Servicio Ciclo 3 — Probador virtual (CU17).
//
// - GET /variantes/{id}/prueba-virtual (compatibilidad y recurso)
// - POST /probador/autorizaciones (token cliente de 60 s, solo en memoria)
// Nunca expone ni guarda DECART_API_KEY.
import 'package:uuid/uuid.dart';

import '../models/probador_model.dart';
import '../../../core/network/api_client.dart';

class ProbadorService {
  final ApiClient _api;
  ProbadorService({ApiClient? api}) : _api = api ?? ApiClient();

  Future<RecursoPruebaVirtual> obtenerRecurso(String varianteId) {
    return _api.get<RecursoPruebaVirtual>(
      '/variantes/$varianteId/prueba-virtual',
      convertir: (j) =>
          RecursoPruebaVirtual.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<AutorizacionDecart> solicitarAutorizacion({
    required String varianteId,
    String consentimientoVersion = consentimientoDecartVigente,
    String? claveIdempotencia,
  }) {
    return _api.post<AutorizacionDecart>(
      '/probador/autorizaciones',
      cuerpo: {
        'variante_id': varianteId,
        'consentimiento_version': consentimientoVersion,
      },
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) =>
          AutorizacionDecart.fromJson((j as Map).cast<String, dynamic>()),
    );
  }
}
