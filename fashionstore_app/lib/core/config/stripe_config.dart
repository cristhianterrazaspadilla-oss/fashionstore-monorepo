// Configuración Stripe Test (CU15) y entorno general Ciclo 3.
//
// - STRIPE_PUBLISHABLE_KEY por --dart-define (clave publicable, sin secretos).
// - Nunca secret key, webhook secret ni credenciales privadas en Flutter.
// - API_BASE_URL ya resuelto por ApiConfig.

/// Clave publicable de Stripe Test inyectada por entorno.
///
/// Uso:
/// ```
/// flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 \
///   --dart-define=STRIPE_PUBLISHABLE_KEY=pk_test_...
/// ```
class StripeConfig {
  static const String _envKey = 'STRIPE_PUBLISHABLE_KEY';
  static const String _envValue = String.fromEnvironment(_envKey);
  // Clave publicable de Stripe Test usada también por el frontend web.
  // Es segura para distribuir en el cliente; las claves secretas permanecen
  // exclusivamente en Render.
  static const String _testDefault =
      'pk_test_51UGrdtGvKFMGR2Rolqypr0T3r3XPA9alWLXLa8KZTe7mZxSq1phaOJom0nNMhe1H8bFxtxEibeZkcrjhHhA3UYJQ00sDRKwAhw';

  static String get publishableKey =>
      _envValue.trim().isNotEmpty ? _envValue.trim() : _testDefault;

  static bool get estaConfigurada => publishableKey.isNotEmpty;
}
