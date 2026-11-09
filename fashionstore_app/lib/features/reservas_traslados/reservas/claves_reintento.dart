import 'package:uuid/uuid.dart';

import '../../../core/network/api_exception.dart';

/// Claves de idempotencia estables por línea reintentada.
///
/// - El reintento de la misma línea con el mismo origen reutiliza la clave.
/// - Si el usuario cambia el origen (o el backend responde 409 por payload
///   distinto con la misma clave), se genera una clave nueva.
class ClavesReintento {
  final Map<String, _EntradaClave> _entradas = {};
  final String Function() _generar;

  ClavesReintento({String Function()? generar})
      : _generar = generar ?? const Uuid().v4;

  /// Devuelve la clave estable para [lineaId]+[origenId].
  String clavePara({
    required String lineaId,
    required String origenId,
  }) {
    final previa = _entradas[lineaId];
    if (previa != null && previa.origenId == origenId) {
      return previa.clave;
    }
    final nueva = _generar();
    _entradas[lineaId] = _EntradaClave(origenId: origenId, clave: nueva);
    return nueva;
  }

  /// Observa la clave actual sin generar una nueva (para pruebas/UI).
  String? claveActual(String lineaId) => _entradas[lineaId]?.clave;

  /// Descarta la clave tras un 409 por reutilización con otro payload,
  /// para que el siguiente intento use una clave nueva.
  void invalidarPorConflicto(String lineaId) {
    _entradas.remove(lineaId);
  }

  void limpiar() => _entradas.clear();
}

class _EntradaClave {
  final String origenId;
  final String clave;
  _EntradaClave({required this.origenId, required this.clave});
}

/// true si el error es un 409 por reutilizar la misma
/// Idempotency-Key con un payload distinto.
bool esConflictoIdempotencia(Object error) {
  if (error is! ApiException) return false;
  if (error.statusCode != 409) return false;
  final detalle = (error.detalleTecnico ?? error.mensaje).toLowerCase();
  return detalle.contains('idempoten');
}
