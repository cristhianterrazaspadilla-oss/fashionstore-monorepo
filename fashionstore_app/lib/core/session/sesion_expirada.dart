import 'dart:async';

/// Manejo global de sesión expirada (401 del servidor).
///
/// Garantías para la auditoría del Ciclo 2:
/// - Un solo aviso visible aunque varios 401 lleguen a la vez.
/// - La sesión se limpia una sola vez por ráfaga de 401 concurrentes.
/// - El aviso se muestra vía [GlobalKey<ScaffoldMessengerState>] (asignada
///   a `MaterialApp.scaffoldMessengerKey`), nunca con un `BuildContext`
///   que pueda estar desmontado.
class ManejadorSesionExpirada {
  /// Ventana durante la cual los 401 repetidos se absorben sin nuevo aviso.
  final Duration ventanaAviso;
  final DateTime Function() _reloj;

  bool _gestionando = false;
  DateTime? _ultimoAviso;
  Future<void>? _limpiezaEnCurso;

  ManejadorSesionExpirada({
    this.ventanaAviso = const Duration(seconds: 5),
    DateTime Function()? reloj,
  }) : _reloj = reloj ?? DateTime.now;

  bool get gestionando => _gestionando;

  /// Punto de entrada del gancho `ApiClient.onNoAutorizadoGlobal`.
  ///
  /// [limpiarSesion] debe cerrar/limpiar la sesión (idempotente).
  /// [mostrarAviso] muestra el aviso (usa la key del ScaffoldMessenger).
  /// [irALogin] navega al login (setState en main).
  void manejar({
    required Future<void> Function() limpiarSesion,
    required void Function() mostrarAviso,
    required void Function() irALogin,
  }) {
    final ahora = _reloj();
    if (_gestionando) return;
    if (_ultimoAviso != null &&
        ahora.difference(_ultimoAviso!) < ventanaAviso) {
      return;
    }
    _gestionando = true;
    _ultimoAviso = ahora;
    () async {
      try {
        // Limpieza única: los 401 concurrentes comparten el mismo futuro.
        _limpiezaEnCurso ??= limpiarSesion();
        await _limpiezaEnCurso;
      } catch (_) {
        // La limpieza nunca debe romper la navegación al login.
      } finally {
        _limpiezaEnCurso = null;
      }
      try {
        irALogin();
      } catch (_) {
        // Contexto/state desmontado: no se propaga la excepción.
      }
      try {
        mostrarAviso();
      } catch (_) {
        // Sin ScaffoldMessenger disponible: se omite el aviso.
      } finally {
        // Se libera tras la ventana para absorber la ráfaga completa.
        unawaited(
          Future.delayed(ventanaAviso).then((_) => _gestionando = false),
        );
      }
    }();
  }

  /// Solo para pruebas: restablece el estado interno.
  void restablecerParaPruebas() {
    _gestionando = false;
    _ultimoAviso = null;
    _limpiezaEnCurso = null;
  }
}
