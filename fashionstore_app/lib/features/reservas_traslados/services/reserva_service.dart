import 'package:uuid/uuid.dart';

import '../models/reserva_model.dart';
import '../../../core/network/api_client.dart';

/// Reservas del cliente (contrato real CU18 y adaptadores).
///
/// - POST /reservas (con Idempotency-Key)
/// - GET /reservas (paginado, propias)
/// - GET /reservas/{id} y /reservas/codigo/{codigo}
/// - PATCH /reservas/{id}/cancelar (con Idempotency-Key y {revision})
class ReservaService {
  final ApiClient _api;
  ReservaService({ApiClient? api}) : _api = api ?? ApiClient();

  static String nuevaClaveIdempotencia() => const Uuid().v4();

  /// Crea la reserva online. [clave] debe mantenerse estable durante el reintento
  /// de la misma bolsa (la genera la pantalla una vez por confirmación).
  Future<Reserva> crear({
    required String sucursalDestinoId,
    required List<ItemBolsa> items,
    DateTime? fechaVisita,
    String? observacion,
    String? claveIdempotencia,
  }) {
    final clave = claveIdempotencia ?? nuevaClaveIdempotencia();
    return _api.post<Reserva>(
      '/reservas',
      idempotencyKey: clave,
      cuerpo: {
        'sucursal_destino_id': sucursalDestinoId,
        if (fechaVisita != null)
          'fecha_visita': fechaVisita.toUtc().toIso8601String(),
        if (observacion != null && observacion.trim().isNotEmpty)
          'observacion': observacion.trim(),
        'lineas': items.map((e) => e.toJson()).toList(),
      },
      convertir: (j) => Reserva.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<ReservaLista> listarMias({int limit = 20, int offset = 0}) {
    return _api.get<ReservaLista>(
      '/reservas',
      query: {'limit': '$limit', 'offset': '$offset'},
      convertir: (j) =>
          ReservaLista.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<Reserva> obtener(String id) {
    return _api.get<Reserva>(
      '/reservas/$id',
      convertir: (j) => Reserva.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<Reserva> obtenerPorCodigo(String codigo) {
    return _api.get<Reserva>(
      '/reservas/codigo/${codigo.trim()}',
      convertir: (j) => Reserva.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  /// Cancela la reserva con clave de idempotencia y revisión concurrente (CU18).
  Future<Reserva> cancelar(String id, {int revision = 1, String? claveIdempotencia}) {
    final clave = claveIdempotencia ?? nuevaClaveIdempotencia();
    return _api.patch<Reserva>(
      '/reservas/$id/cancelar',
      idempotencyKey: clave,
      cuerpo: {
        'revision': revision,
      },
      convertir: (j) => Reserva.fromJson((j as Map).cast<String, dynamic>()),
    );
  }
}
