/// Resolución de la URL base del backend y código de empresa (única fuente de verdad).
///
/// La app generada apunta por defecto al backend FastAPI desplegado en Render.
/// Para desarrollo local se puede sobrescribir sin cambiar el código:
///   `flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 --dart-define=EMPRESA_CODIGO=fashionstore`
/// Decart: la app nunca recibe ni guarda DECART_API_KEY; solo solicita al
/// backend `POST /api/v1/probador/autorizaciones` y usa el `client_token`
/// temporal en memoria con el modelo fijo `lucy-2.5`.
class ApiConfig {
  static const String _envKey = 'API_BASE_URL';
  static const String _envEmpresaKey = 'EMPRESA_CODIGO';
  static const String _renderUrl =
      'https://fashionstore-backend-natk.onrender.com/api/v1';

  /// URL definida por --dart-define, vacía si no se pasó.
  static const String _envUrl = String.fromEnvironment(_envKey);

  /// Código de empresa activo definido por --dart-define (por defecto fashionstore).
  static const String _envEmpresa =
      String.fromEnvironment(_envEmpresaKey, defaultValue: 'fashionstore');

  static String get baseUrl {
    final v = _envUrl.trim();
    if (v.isNotEmpty) return v.replaceAll(RegExp(r'/+$'), '');
    return _renderUrl;
  }

  static String get empresaCodigoDefecto {
    final e = _envEmpresa.trim();
    return e.isNotEmpty ? e : 'fashionstore';
  }

  /// Mensaje corto para pantallas de ayuda / diagnóstico.
  static String get origenDescripcion {
    if (_envUrl.trim().isNotEmpty) return 'configurada por la app ($_envKey)';
    return 'backend de producción en Render';
  }
}
