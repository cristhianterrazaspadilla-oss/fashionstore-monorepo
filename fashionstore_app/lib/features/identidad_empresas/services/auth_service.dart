import 'dart:async';

import '../models/usuario_model.dart';
import 'notificacion_movil_service.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/session/session_manager.dart';

/// Autenticación del cliente (contrato real POST /clientes y POST /sesion).
///
/// Usa el cliente centralizado + sesión persistente con vencimiento.
class AuthService {
  static NotificacionMovilService? _pushService;
  static Future<void>? _pushInicializado;

  /// Reutiliza una sola suscripcion FCM tras login y restauracion de sesion.
  static Future<void> asegurarPushActivo() {
    final activo = _pushInicializado;
    if (activo != null) return activo;
    final servicio = _pushService ??= NotificacionMovilService();
    return _pushInicializado = servicio
        .inicializar(autoRegistrarEnBackend: true)
        .catchError((_) {
      _pushInicializado = null;
    });
  }

  final ApiClient _api;
  final SessionManager _sesiones;

  AuthService({ApiClient? api, SessionManager? sesiones})
      : _api = api ?? ApiClient(),
        _sesiones = sesiones ?? SessionManager() {
    _api.onNoAutorizado = null;
  }

  Future<ClientePerfilModel> registrarCliente({
    required String nombres,
    required String apellidos,
    required String correoElectronico,
    required String contrasenia,
    String? telefono,
    String? direccionReferencia,
    String? fechaNacimiento,
    Map<String, dynamic>? preferencias,
  }) async {
    try {
      return await _api.post<ClientePerfilModel>(
        '/clientes',
        cuerpo: {
          'nombres': nombres,
          'apellidos': apellidos,
          'correo_electronico': correoElectronico,
          'contrasenia': contrasenia,
          if (telefono != null && telefono.trim().isNotEmpty)
            'telefono': telefono.trim(),
          if (direccionReferencia != null &&
              direccionReferencia.trim().isNotEmpty)
            'direccion_referencia': direccionReferencia.trim(),
          if (fechaNacimiento != null && fechaNacimiento.trim().isNotEmpty)
            'fecha_nacimiento': fechaNacimiento.trim(),
          'preferencias': preferencias ?? {},
        },
        convertir: (j) =>
            ClientePerfilModel.fromJson((j as Map).cast<String, dynamic>()),
      );
    } on ApiException catch (e) {
      if (e.statusCode == 409) {
        throw const ApiException(
          statusCode: 409,
          mensaje: 'Ese correo ya tiene una cuenta. Inicia sesión.',
        );
      }
      rethrow;
    }
  }

  Future<TokenRespuestaModel> iniciarSesion({
    required String correoElectronico,
    required String contrasenia,
  }) async {
    try {
      final respuesta = await _api.post<TokenRespuestaModel>(
        '/sesion',
        cuerpo: {
          'correo_electronico': correoElectronico.trim(),
          'contrasenia': contrasenia,
        },
        convertir: (j) =>
            TokenRespuestaModel.fromJson((j as Map).cast<String, dynamic>()),
      );
      await _sesiones.guardar(
        token: respuesta.accessToken,
        usuario: respuesta.usuario,
      );
      // Vincula dispositivo móvil ante el backend (E2 Avisos)
      unawaited(asegurarPushActivo());
      return respuesta;
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        throw const ApiException(
          statusCode: 401,
          mensaje: 'Correo o contraseña incorrectos. Inténtalo de nuevo.',
        );
      }
      rethrow;
    }
  }

  Future<void> cerrarSesion() async {
    try {
      await (_pushService ?? NotificacionMovilService(api: _api))
          .revocarDispositivo();
    } catch (_) {
      // El cierre de sesion local sigue disponible sin red.
    }
    await _pushService?.dispose();
    _pushService = null;
    _pushInicializado = null;
    await _sesiones.limpiar();
  }

  Future<String?> obtenerToken() async {
    final s = await _sesiones.leerValida();
    return s?.token;
  }

  Future<bool> estaAutenticado() async {
    final s = await _sesiones.leerValida();
    return s != null;
  }

  Future<SesionPersistente?> sesionActual() => _sesiones.leerValida();
}
