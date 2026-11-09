/// Excepción uniforme para errores HTTP del backend.
///
/// Traduce los códigos del contrato (400/401/403/404/409/422) a
/// mensajes comprensibles, sin exponer textos técnicos.
class ApiException implements Exception {
  final int? statusCode;
  final String mensaje;
  final String? detalleTecnico;

  const ApiException({
    this.statusCode,
    required this.mensaje,
    this.detalleTecnico,
  });

  /// Crea la excepción desde un status + cuerpo ya decodificado.
  factory ApiException.desdeRespuesta(int statusCode, dynamic cuerpo) {
    String? detalle;
    if (cuerpo is Map) {
      final d = cuerpo['detail'];
      if (d is String && d.trim().isNotEmpty) detalle = d;
      if (d is List && d.isNotEmpty) {
        // Error 422 de validación: resumir sin tecnicismos.
        detalle = d
            .map((e) {
              if (e is Map) {
                final loc = (e['loc'] as List?)?.join(' ') ?? '';
                return loc.isEmpty ? 'Dato no válido' : loc;
              }
              return 'Dato no válido';
            })
            .take(2)
            .join(', ');
      }
    }
    return ApiException(
      statusCode: statusCode,
      mensaje: traducir(statusCode, detalle),
      detalleTecnico: detalle,
    );
  }

  /// Mensajes comprensibles por código de estado.
  static String traducir(int? statusCode, [String? detalleServidor]) {
    switch (statusCode) {
      case 400:
        return 'Revisa los datos ingresados e inténtalo de nuevo.';
      case 401:
        return 'Tu sesión venció. Vuelve a iniciar sesión.';
      case 403:
        return 'No tienes permiso para realizar esta acción.';
      case 404:
        return 'No encontramos lo que buscabas. Puede que ya no esté disponible.';
      case 409:
        // El servidor suele explicar stock insuficiente o conflicto.
        if (detalleServidor != null && detalleServidor.trim().isNotEmpty) {
          final d = detalleServidor.trim();
          final lower = d.toLowerCase();
          if (lower.contains('stock') ||
              lower.contains('disponib') ||
              lower.contains('insuficiente')) {
            return 'No hay suficiente disponibilidad en esa sucursal. Prueba con otra cantidad u origen.';
          }
          if (lower.contains('idempoten')) {
            return 'Esta solicitud ya fue enviada con otros datos. Genera una nueva solicitud.';
          }
          if (lower.contains('estado') ||
              lower.contains('transici') ||
              lower.contains('cancel')) {
            return 'Esta reserva ya cambió de estado y no admite esa acción.';
          }
          // Recortar tecnicismos largos pero conservar la idea.
          if (d.length <= 140) return d;
          return 'Hay un conflicto con el estado actual. Actualiza la información e inténtalo de nuevo.';
        }
        return 'Hay un conflicto con el estado actual. Actualiza la información e inténtalo de nuevo.';
      case 422:
        return 'Algunos datos no son válidos. Revísalos e inténtalo de nuevo.';
      default:
        if (statusCode != null && statusCode >= 500) {
          return 'El servicio no está disponible por el momento. Inténtalo más tarde.';
        }
        return 'Ocurrió un problema inesperado. Inténtalo de nuevo.';
    }
  }

  @override
  String toString() => mensaje;
}
