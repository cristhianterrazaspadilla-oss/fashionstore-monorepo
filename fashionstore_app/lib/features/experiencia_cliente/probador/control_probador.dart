// Control del probador virtual (CU17): máquina de estados, consentimiento,
// cámara, token en memoria, sesión de 120 s y cleanup idempotente.
//
// No guarda ni registra cámara, video, frames, rostro, token, API key, SDP,
// Base64, URLs firmadas ni contenido WebRTC. Solo metadatos sanitizados.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:permission_handler/permission_handler.dart';

import '../models/probador_model.dart';
import '../services/ia_service.dart';
import '../services/probador_service.dart';
import 'puente_decart.dart';

class ControlProbador extends ChangeNotifier {
  final ProbadorService _servicio;
  final IaService _navegacion;
  final PuenteDecart _puente;
  final Future<PermissionStatus> Function()? _permisoCamaraMock;

  ControlProbador({
    ProbadorService? servicio,
    IaService? navegacion,
    PuenteDecart? puente,
    Future<PermissionStatus> Function()? permisoCamaraMock,
  })  : _servicio = servicio ?? ProbadorService(),
        _navegacion = navegacion ?? IaService(),
        _puente = puente ?? PuenteDecart(),
        _permisoCamaraMock = permisoCamaraMock;

  EstadoProbador estado = EstadoProbador.idle;
  String? error;
  String? codigoError;
  RecursoPruebaVirtual? recurso;
  bool consentimiento = false;
  bool primeraTransformacion = false;
  bool streamRemotoRecibido = false;
  bool vistaLocalDisponible = false;
  String etapaDiagnostico = 'Sin iniciar';
  int? vigenciaTokenAlConectarSegundos;
  int segundosRestantes = duracionMaximaProbadorSegundos;
  Timer? _conteo;
  Timer? _timeoutConexion;
  StreamSubscription? _subEventos;
  String? _varianteId;

  // Token solo en memoria; se borra en cleanup.
  String? _tokenCliente;
  bool _cambiandoPrenda = false;
  Future<void>? _cierreEnCurso;
  int _secuenciaPrenda = 0;
  DateTime? _inicioSesion;
  bool _disposed = false;
  // GENERATING visto (procesando): solo entonces un frame confirma visibilidad.
  bool _generandoVisto = false;

  bool get enVivo => estado == EstadoProbador.live;
  bool get ocupado =>
      estado == EstadoProbador.connecting ||
      estado == EstadoProbador.remoteStream ||
      estado == EstadoProbador.generating ||
      estado == EstadoProbador.switchingGarment ||
      estado == EstadoProbador.authorizing ||
      estado == EstadoProbador.closing;

  void _notificarSeguro() {
    if (_disposed) return;
    try {
      notifyListeners();
    } catch (_) {}
  }

  Future<void> cargarRecurso(String varianteId) async {
    _varianteId = varianteId;
    estado = EstadoProbador.idle;
    error = null;
    _notificarSeguro();
    try {
      recurso = await _servicio.obtenerRecurso(varianteId);
    } catch (e) {
      estado = EstadoProbador.error;
      error = e.toString();
    }
    _notificarSeguro();
  }

  void aceptarConsentimiento(bool acepta) {
    consentimiento = acepta;
    _notificarSeguro();
  }

  Future<bool> _permisoCamara() async {
    estado = EstadoProbador.requestingPermission;
    _notificarSeguro();
    PermissionStatus p;
    try {
      final mock = _permisoCamaraMock;
      p = mock != null ? await mock() : await Permission.camera.request();
    } catch (_) {
      estado = EstadoProbador.error;
      error = 'No pudimos solicitar el permiso de cámara.';
      _notificarSeguro();
      return false;
    }
    if (!p.isGranted) {
      estado = EstadoProbador.error;
      codigoError = 'CAMARA_DENEGADA';
      error = 'Permiso de cámara denegado. Actívalo para usar el probador.';
      _notificarSeguro();
      return false;
    }
    estado = EstadoProbador.cameraReady;
    _notificarSeguro();
    return true;
  }

  bool _cerrandoOCerrado = false;
  bool get _estaCerrado =>
      _cerrandoOCerrado ||
      estado == EstadoProbador.closing ||
      estado == EstadoProbador.disconnected;

  Future<void> iniciar() async {
    _cerrandoOCerrado = false;
    codigoError = null;
    error = null;
    etapaDiagnostico = 'Solicitando permiso de cámara';
    if (!consentimiento || _varianteId == null) return;
    final rec = recurso;
    if (rec != null && !rec.compatible) {
      estado = EstadoProbador.error;
      codigoError = 'VARIANTE_INCOMPATIBLE';
      error = 'Esta prenda no es compatible con el probador virtual.';
      _notificarSeguro();
      return;
    }
    final camaraOk = await _permisoCamara();
    if (!camaraOk || _estaCerrado) return;
    estado = EstadoProbador.authorizing;
    _notificarSeguro();
    try {
      final aut =
          await _servicio.solicitarAutorizacion(varianteId: _varianteId!);
      if (_estaCerrado) return;
      if (aut.tokenVencido) {
        throw Exception('TOKEN_VENCIDO');
      }
      _tokenCliente = aut.tokenCliente;
      vigenciaTokenAlConectarSegundos =
          aut.expiraEn?.toUtc().difference(DateTime.now().toUtc()).inSeconds;
      etapaDiagnostico = 'Token temporal recibido';
      if (_estaCerrado) return;
      await _conectar(
        imagenUrl: aut.imagenPrendaUrl,
        prompt: aut.promptPrenda,
      );
      if (_estaCerrado) return;
      try {
        await _navegacion.registrarNavegacion(
          evento: 'PRUEBA_VIRTUAL',
          varianteId: _varianteId,
        );
      } catch (_) {}
    } catch (e) {
      if (_estaCerrado) return;
      await cerrar();
      estado = EstadoProbador.error;
      codigoError = _clasificarError(e.toString());
      error = _mensajeAmable(codigoError!, e.toString());
      _notificarSeguro();
    }
  }

  Future<void> _conectar(
      {required String imagenUrl, required String prompt}) async {
    if (_estaCerrado) return;
    estado = EstadoProbador.connecting;
    primeraTransformacion = false;
    streamRemotoRecibido = false;
    vistaLocalDisponible = false;
    etapaDiagnostico = 'Abriendo conexión realtime';
    _generandoVisto = false;
    _notificarSeguro();
    _escucharEventos();
    _timeoutConexion?.cancel();
    _timeoutConexion = Timer(const Duration(seconds: 35), () {
      if (_disposed || primeraTransformacion || _estaCerrado) return;
      estado = EstadoProbador.error;
      codigoError = 'TIMEOUT_CONEXION_DECART';
      error = streamRemotoRecibido
          ? 'Decart envió el stream, pero no llegó ningún frame transformado.'
          : 'Decart no entregó un stream remoto dentro de 35 segundos.';
      etapaDiagnostico = streamRemotoRecibido
          ? 'Stream sin frame transformado'
          : 'Sin stream remoto';
      _notificarSeguro();
    });
    try {
      await _puente.initialize();
      if (_estaCerrado) {
        await _puente.disconnect();
        await _puente.release();
        return;
      }
      await _puente.connect(
        tokenCliente: _tokenCliente ?? '',
        imagenPrendaUrl: imagenUrl,
        promptPrenda: prompt,
      );
      if (_estaCerrado) {
        await _puente.disconnect();
        await _puente.release();
        return;
      }
    } catch (e) {
      if (_estaCerrado) return;
      estado = EstadoProbador.error;
      codigoError = _clasificarError(e.toString());
      error = _mensajeAmable(codigoError!, e.toString());
      _notificarSeguro();
      rethrow;
    }
  }

  void _escucharEventos() {
    _subEventos?.cancel();
    _subEventos = _puente.eventos().listen((ev) {
      if (_estaCerrado || _disposed) return;
      switch (ev.tipo) {
        case 'camaraLista':
          etapaDiagnostico = 'Cámara abierta; esperando a Decart';
          // Cámara preparada: aún sin stream ni transformación.
          if (estado == EstadoProbador.connecting ||
              estado == EstadoProbador.authorizing) {
            estado = EstadoProbador.cameraReady;
          }
          break;
        case 'vistaLocal':
          vistaLocalDisponible = true;
          etapaDiagnostico =
              'Vista previa activa; Decart está preparando la prenda';
          if (estado == EstadoProbador.connecting ||
              estado == EstadoProbador.cameraReady) {
            estado = EstadoProbador.cameraReady;
          }
          break;
        case 'conectando':
          etapaDiagnostico = 'WebSocket/LiveKit conectando';
          if (estado != EstadoProbador.switchingGarment) {
            estado = EstadoProbador.connecting;
          }
          break;
        case 'conectado':
          codigoError = null;
          error = null;
          etapaDiagnostico = 'Decart conectado; esperando stream remoto';
          break;
        case 'live':
        case 'CONNECTED':
          // CONNECTED / live sin primeraTransformacion NO implica resultado
          // visible: se trata como stream disponible y se conserva cubierta.
          if (estado == EstadoProbador.switchingGarment) {
            break;
          }
          if (primeraTransformacion) {
            estado = EstadoProbador.live;
            _inicioSesion ??= DateTime.now();
            _iniciarConteo();
          } else if (estado != EstadoProbador.generating) {
            estado = EstadoProbador.remoteStream;
          }
          break;
        case 'streamRemoto':
          streamRemotoRecibido = true;
          etapaDiagnostico = 'Stream remoto recibido; esperando transformación';
          // Stream remoto disponible; mantiene la cubierta hasta
          // primeraTransformacion. Nunca pasa a live aquí.
          if (_generandoVisto && estado != EstadoProbador.switchingGarment) {
            // initialImage + initialPrompt hacen que el stream remoto inicial
            // ya sea transformado. No depender del callback bitmap, que puede
            // no ejecutarse cuando Android compone una PlatformView.
            primeraTransformacion = true;
            estado = EstadoProbador.live;
            etapaDiagnostico = 'Video transformado recibido';
            _timeoutConexion?.cancel();
            _inicioSesion ??= DateTime.now();
            _iniciarConteo();
          } else if (estado != EstadoProbador.switchingGarment &&
              estado != EstadoProbador.live &&
              estado != EstadoProbador.generating) {
            estado = EstadoProbador.remoteStream;
          }
          break;
        case 'generando':
        case 'GENERATING':
          etapaDiagnostico = 'Decart generando la transformación';
          // GENERATING = procesando, no transformación confirmada.
          // No activa primeraTransformacion ni retira la cubierta.
          _generandoVisto = true;
          if (streamRemotoRecibido &&
              estado != EstadoProbador.switchingGarment) {
            primeraTransformacion = true;
            estado = EstadoProbador.live;
            etapaDiagnostico = 'Video transformado recibido';
            _timeoutConexion?.cancel();
            _inicioSesion ??= DateTime.now();
            _iniciarConteo();
          } else if (estado != EstadoProbador.switchingGarment &&
              !primeraTransformacion) {
            estado = EstadoProbador.generating;
          }
          break;
        case 'primeraTransformacion':
          _timeoutConexion?.cancel();
          etapaDiagnostico = 'Transformación visible';
          // Único evento que confirma frame visible: primer frame remoto
          // posterior a GENERATING (ver puente nativo). Retira la cubierta.
          if (_generandoVisto || primeraTransformacion) {
            primeraTransformacion = true;
            estado = EstadoProbador.live;
            _inicioSesion ??= DateTime.now();
            _iniciarConteo();
          } else {
            // Frame previo a GENERATING (cámara cruda): ignorar, conservar
            // cubierta en stream disponible.
            if (estado != EstadoProbador.switchingGarment) {
              estado = EstadoProbador.remoteStream;
            }
          }
          break;
        case 'prendaAplicada':
          if (estado == EstadoProbador.switchingGarment) {
            final seq = int.tryParse(ev.codigo ?? '');
            if (seq == null || seq == _secuenciaPrenda) {
              estado = EstadoProbador.live;
              primeraTransformacion = true;
            }
            // Secuencia atrasada de una prenda anterior: se ignora.
          }
          break;
        case 'cambiandoPrenda':
          // El nativo notifica el inicio del cambio con su secuencia.
          break;
        case 'error':
          _timeoutConexion?.cancel();
          estado = EstadoProbador.error;
          codigoError = _clasificarError(ev.codigo ?? ev.mensaje ?? '');
          error =
              _mensajeAmable(codigoError!, ev.mensaje ?? 'Error del probador.');
          etapaDiagnostico = 'Error nativo: ${ev.codigo ?? 'SIN_CODIGO'}';
          break;
        case 'disconnected':
        case 'DISCONNECTED':
          if (estado != EstadoProbador.closing) {
            _timeoutConexion?.cancel();
            estado = EstadoProbador.error;
            codigoError = ev.codigo ?? 'DECART_DESCONECTADO';
            error = ev.mensaje?.isNotEmpty == true
                ? ev.mensaje
                : 'Decart cerró la conexión antes de mostrar el video.';
            etapaDiagnostico = 'Conexión cerrada por Decart';
          }
          break;
      }
      _notificarSeguro();
    });
  }

  Future<void> cambiarPrenda(
      {required String imagenUrl, required String prompt}) async {
    // Sin conexiones simultáneas: una sola operación de cambio a la vez.
    if (_cambiandoPrenda || !enVivo) return;
    _cambiandoPrenda = true;
    final seqActual = ++_secuenciaPrenda;
    estado = EstadoProbador.switchingGarment;
    _notificarSeguro();
    try {
      await _puente.setGarment(
          imagenPrendaUrl: imagenUrl, promptPrenda: prompt);
      // No se vuelve a live aquí: la cubierta de transición se mantiene
      // hasta que el nativo confirme el frame posterior de esta secuencia
      // vía `prendaAplicada`. Los callbacks atrasados se ignoran por seq.
    } catch (e) {
      if (seqActual == _secuenciaPrenda) {
        estado = EstadoProbador.error;
        codigoError = _clasificarError(e.toString());
        error = _mensajeAmable(codigoError!, e.toString());
        _notificarSeguro();
      }
    } finally {
      _cambiandoPrenda = false;
      // Sin transición automática a live: permanecer en switchingGarment
      // hasta confirmación (`prendaAplicada`), error o cierre.
    }
  }

  void _iniciarConteo() {
    _conteo?.cancel();
    segundosRestantes = duracionMaximaProbadorSegundos;
    _conteo = Timer.periodic(const Duration(seconds: 1), (t) {
      segundosRestantes--;
      if (segundosRestantes <= 0) {
        cerrar();
      } else {
        _notificarSeguro();
      }
    });
  }

  /// Respaldo explícito de ciclo de vida ante pausa, bloqueo o minimizado.
  Future<void> pausar() async {
    await cerrar();
  }

  /// Cleanup idempotente: disconnect, liberar vista, release, borrar token
  /// e imagen, limpiar referencias. Seguro ante errores y llamadas concurrentes/duplicadas.
  /// Tolerante a `dispose()`: nunca notifica tras la liberación.
  Future<void> cerrar() async {
    _cerrandoOCerrado = true;
    if (_cierreEnCurso != null) {
      return _cierreEnCurso!;
    }
    final completer = Completer<void>();
    _cierreEnCurso = completer.future;
    try {
      estado = EstadoProbador.closing;
      _notificarSeguro();
      _conteo?.cancel();
      _timeoutConexion?.cancel();
      _conteo = null;
      try {
        await _subEventos?.cancel();
      } catch (_) {}
      _subEventos = null;
      try {
        await _puente.disconnect();
      } catch (_) {}
      try {
        await _puente.release();
      } catch (_) {}
      _tokenCliente = null;
      _inicioSesion = null;
      primeraTransformacion = false;
      vistaLocalDisponible = false;
      _generandoVisto = false;
      _cambiandoPrenda = false;
      estado = EstadoProbador.disconnected;
      _notificarSeguro();
    } finally {
      _cierreEnCurso = null;
      completer.complete();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _cerrandoOCerrado = true;
    _conteo?.cancel();
    _timeoutConexion?.cancel();
    _conteo = null;
    // Cancelación síncrona segura: no notifica ni espera al nativo.
    // El cierre nativo (disconnect/release) debe haberse iniciado antes vía
    // `cerrar()` (pantalla/lifecycle); aquí solo se liberan referencias
    // para no usar el control después de `dispose()`.
    try {
      _subEventos?.cancel();
    } catch (_) {}
    _subEventos = null;
    _tokenCliente = null;
    _inicioSesion = null;
    super.dispose();
  }

  String _clasificarError(String crudo) {
    final t = crudo.toUpperCase();
    if (t.contains('TOKEN') || t.contains('401') || t.contains('403')) {
      return 'AUTORIZACION_FALLIDA';
    }
    if (t.contains('MODERAC')) return 'MODERACION';
    if (t.contains('ICE')) return 'ERROR_RED_ICE';
    if (t.contains('TIMEOUT') || t.contains('TIEMPO')) return 'TIMEOUT';
    if (t.contains('RED') || t.contains('NETWORK') || t.contains('WEBRTC')) {
      return 'ERROR_RED';
    }
    if (t.contains('CAMARA') || t.contains('CAMERA') || t.contains('PERMISO')) {
      return 'CAMARA_DENEGADA';
    }
    if (t.contains('INCOMPATIBLE') || t.contains('409')) {
      return 'VARIANTE_INCOMPATIBLE';
    }
    return 'ERROR_GENERICO';
  }

  String _mensajeAmable(String codigo, String detalle) {
    switch (codigo) {
      case 'AUTORIZACION_FALLIDA':
        return 'No pudimos autorizar tu prueba. Vuelve al producto e inténtalo de nuevo.';
      case 'MODERACION':
        return 'La imagen fue observada por el proveedor. Prueba con otra prenda.';
      case 'ERROR_RED_ICE':
      case 'ERROR_RED':
        return 'Se perdió la conexión de video. Revisa tu red y reintenta.';
      case 'TIMEOUT':
        return 'La conexión tardó demasiado. Inténtalo de nuevo.';
      case 'CAMARA_DENEGADA':
        return detalle;
      case 'VARIANTE_INCOMPATIBLE':
        return 'Esta prenda no es compatible con el probador virtual.';
      default:
        return 'No pudimos iniciar el probador. Vuelve al producto.';
    }
  }
}
