import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../session/session_manager.dart';
import 'api_exception.dart';

/// Cliente HTTP centralizado.
///
/// - Agrega `Authorization: Bearer` automáticamente.
/// - Soporta `Idempotency-Key` para reintentos seguros.
/// - Traduce 400/401/403/404/409/422 a mensajes comprensibles.
/// - Notifica 401 mediante [onNoAutorizado] para cierre de sesión controlado.
class ApiClient {
  final http.Client _http;
  final SessionManager _sesiones;
  final Future<Map<String, String>> Function()? _cabecerasExtra;

  /// Se invoca una vez por cada 401 real del servidor.
  void Function()? onNoAutorizado;

  /// Gancho global (lo configura main.dart una vez).
  static void Function()? onNoAutorizadoGlobal;

  ApiClient({
    http.Client? httpClient,
    SessionManager? sesiones,
    Future<Map<String, String>> Function()? cabecerasExtra,
    this.onNoAutorizado,
  })  : _http = httpClient ?? http.Client(),
        _sesiones = sesiones ?? SessionManager(),
        _cabecerasExtra = cabecerasExtra;

  String get baseUrl => ApiConfig.baseUrl;

  Future<Map<String, String>> _cabeceras({String? idempotencyKey}) async {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    final sesion = await _sesiones.leerValida();
    if (sesion != null && sesion.token.isNotEmpty) {
      headers['Authorization'] = 'Bearer ${sesion.token}';
    }
    if (idempotencyKey != null && idempotencyKey.isNotEmpty) {
      headers['Idempotency-Key'] = idempotencyKey;
    }
    final extra = _cabecerasExtra;
    if (extra != null) {
      headers.addAll(await extra());
    }
    return headers;
  }

  Uri _uri(String ruta, [Map<String, String>? query]) {
    final base = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    final path = ruta.startsWith('/') ? ruta : '/$ruta';
    final uri = Uri.parse('$base$path');
    if (query == null || query.isEmpty) return uri;
    return uri.replace(
      queryParameters: {...uri.queryParameters, ...query},
    );
  }

  dynamic _decodificar(http.Response r) {
    if (r.body.isEmpty) return null;
    try {
      return jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      return null;
    }
  }

  Future<T> _procesar<T>(
    http.Response r,
    T Function(dynamic json) convertir,
  ) async {
    if (r.statusCode >= 200 && r.statusCode < 300) {
      final cuerpo = _decodificar(r);
      return convertir(cuerpo);
    }
    if (r.statusCode == 401) {
      try {
        (onNoAutorizado ?? onNoAutorizadoGlobal)?.call();
      } catch (_) {}
    }
    throw ApiException.desdeRespuesta(r.statusCode, _decodificar(r));
  }

  Future<T> get<T>(
    String ruta, {
    Map<String, String>? query,
    required T Function(dynamic json) convertir,
  }) async {
    final r = await _http.get(
      _uri(ruta, query),
      headers: await _cabeceras(),
    );
    return _procesar(r, convertir);
  }

  Future<T> post<T>(
    String ruta, {
    Object? cuerpo,
    Map<String, String>? query,
    String? idempotencyKey,
    required T Function(dynamic json) convertir,
  }) async {
    final r = await _http.post(
      _uri(ruta, query),
      headers: await _cabeceras(idempotencyKey: idempotencyKey),
      body: cuerpo == null ? null : jsonEncode(cuerpo),
    );
    return _procesar(r, convertir);
  }

  Future<T> patch<T>(
    String ruta, {
    Object? cuerpo,
    Map<String, String>? query,
    String? idempotencyKey,
    required T Function(dynamic json) convertir,
  }) async {
    final r = await _http.patch(
      _uri(ruta, query),
      headers: await _cabeceras(idempotencyKey: idempotencyKey),
      body: cuerpo == null ? null : jsonEncode(cuerpo),
    );
    return _procesar(r, convertir);
  }

  Future<T> delete<T>(
    String ruta, {
    Map<String, String>? query,
    String? idempotencyKey,
    required T Function(dynamic json) convertir,
  }) async {
    final r = await _http.delete(
      _uri(ruta, query),
      headers: await _cabeceras(idempotencyKey: idempotencyKey),
    );
    return _procesar(r, convertir);
  }

  void cerrar() => _http.close();
}
