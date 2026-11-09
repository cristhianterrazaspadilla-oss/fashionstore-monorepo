import '../config/api_config.dart';

/// Compatibilidad con código del Ciclo 1.
/// La URL se resuelve desde --dart-define=API_BASE_URL con
/// valores automáticos por plataforma (ver [ApiConfig]).
class ApiConstants {
  static String get baseUrl => ApiConfig.baseUrl;

  static String get endpointClientes => '$baseUrl/clientes';
  static String get endpointSesion => '$baseUrl/sesion';
}
