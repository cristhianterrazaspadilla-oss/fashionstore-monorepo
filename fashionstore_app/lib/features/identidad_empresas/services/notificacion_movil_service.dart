import 'dart:async';
import 'package:flutter/services.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import '../../../core/network/api_client.dart';
import '../../../core/session/dispositivo_helper.dart';
import '../models/notificacion_model.dart';

/// Token FCM provisto por variable de entorno (--dart-define=FCM_PUSH_TOKEN=...)
/// Opcional / legacy: no es obligatorio en producción ni en desarrollo.
const String kEnvFcmPushToken = String.fromEnvironment('FCM_PUSH_TOKEN');

/// Handler top-level estático requerido por FirebaseMessaging.onBackgroundMessage.
/// Debe estar fuera de cualquier clase y anotado con @pragma('vm:entry-point').
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  if (NativePlatformFcmAdapter.backgroundMessageHandler != null) {
    await NativePlatformFcmAdapter.backgroundMessageHandler!(
      NativePlatformFcmAdapter.remoteMessageToPush(message),
    );
  }
}

/// Contrato para adaptadores de Firebase Cloud Messaging.
/// Desacopla la lógica de negocio de la implementación de plataforma (nativa o simulada).
abstract class FcmAdapter {
  /// Obtiene el token FCM actual del dispositivo o null si no está disponible.
  Future<String?> obtenerToken();

  /// Solicita permisos de notificación al sistema operativo (Android 13+ / iOS).
  Future<bool> requestPermission();

  /// Obtiene la notificación inicial si la aplicación fue abierta desde estado cerrado.
  Future<NotificacionMensajePush?> getInitialMessage();

  /// Stream emitido cuando Firebase renueva el token FCM.
  Stream<String> get onTokenRefresh;

  /// Stream de notificaciones recibidas con la aplicación en primer plano (foreground).
  Stream<NotificacionMensajePush> get onMessage;

  /// Stream de notificaciones abiertas por el usuario desde la barra de estado.
  Stream<NotificacionMensajePush> get onMessageOpenedApp;

  /// Registra el handler para mensajes push recibidos en background / reposo.
  void setBackgroundMessageHandler(
      Future<void> Function(NotificacionMensajePush mensaje) handler);

  /// Libera recursos y listeners asociados.
  Future<void> dispose();
}

/// Adaptador nativo oficial basado en FlutterFire (firebase_core y firebase_messaging).
/// Conecta directamente con las APIs oficiales de Google Play Services / Firebase en dispositivos móviles,
/// con inicialización defensiva y manejo seguro sin crashear en entornos donde Firebase no está configurado.
class NativePlatformFcmAdapter implements FcmAdapter {
  /// Handler estático para delegación de mensajes en segundo plano
  static Future<void> Function(NotificacionMensajePush mensaje)?
      backgroundMessageHandler;

  final StreamController<String> _tokenRefreshController =
      StreamController<String>.broadcast();
  final StreamController<NotificacionMensajePush> _messageController =
      StreamController<NotificacionMensajePush>.broadcast();
  final StreamController<NotificacionMensajePush> _messageOpenedController =
      StreamController<NotificacionMensajePush>.broadcast();

  StreamSubscription<String>? _tokenRefreshSub;
  StreamSubscription<RemoteMessage>? _messageSub;
  StreamSubscription<RemoteMessage>? _messageOpenedSub;

  bool _initialized = false;
  bool _initializing = false;

  NativePlatformFcmAdapter() {
    _initSafely();
  }

  /// Convierte un RemoteMessage oficial de Firebase en NotificacionMensajePush
  static NotificacionMensajePush remoteMessageToPush(RemoteMessage message) {
    final notif = message.notification;
    final data = message.data;
    final titulo = notif?.title ??
        data['titulo']?.toString() ??
        data['title']?.toString() ??
        'Aviso';
    final cuerpo = notif?.body ??
        data['cuerpo']?.toString() ??
        data['body']?.toString() ??
        '';
    final id = message.messageId ??
        data['id']?.toString() ??
        '${DateTime.now().millisecondsSinceEpoch}';

    return NotificacionMensajePush(
      id: id,
      titulo: titulo,
      cuerpo: cuerpo,
      datos: data,
      recibidaEn: message.sentTime ?? DateTime.now(),
    );
  }

  /// Inicialización segura y defensiva de Firebase Core y Firebase Messaging.
  /// Si no hay google-services.json, servicios de Google Play o entorno desktop/test,
  /// retorna false limpiamente sin crashear.
  Future<bool> _asegurarFirebase() async {
    if (_initialized) return true;
    if (_initializing) {
      for (int i = 0; i < 20; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 50));
        if (_initialized) return true;
        if (!_initializing) break;
      }
    }
    _initializing = true;
    try {
      if (Firebase.apps.isEmpty) {
        await Firebase.initializeApp();
      }
      _initialized = true;
      return true;
    } catch (_) {
      // MissingPluginException, PlatformException, FirebaseException, etc.
      _initialized = false;
      return false;
    } finally {
      _initializing = false;
    }
  }

  Future<void> _initSafely() async {
    final ready = await _asegurarFirebase();
    if (!ready) return;

    try {
      // 1. Stream de notificaciones en primer plano
      _messageSub = FirebaseMessaging.onMessage.listen((RemoteMessage message) {
        if (!_messageController.isClosed) {
          _messageController.add(remoteMessageToPush(message));
        }
      }, onError: (_) {});

      // 2. Stream de notificaciones pulsadas desde segundo plano
      _messageOpenedSub =
          FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
        if (!_messageOpenedController.isClosed) {
          _messageOpenedController.add(remoteMessageToPush(message));
        }
      }, onError: (_) {});

      // 3. Stream de renovación reactiva de token
      // ignore: deprecated_member_use
      _tokenRefreshSub =
          // ignore: deprecated_member_use
          FirebaseMessaging.instance.onTokenRefresh.listen((String token) {
        if (token.isNotEmpty && !_tokenRefreshController.isClosed) {
          _tokenRefreshController.add(token);
        }
      }, onError: (_) {});

      // 4. Notificación inicial que abrió la aplicación desde estado cerrado (cold start)
      final initialMsg = await FirebaseMessaging.instance.getInitialMessage();
      if (initialMsg != null && !_messageOpenedController.isClosed) {
        _messageOpenedController.add(remoteMessageToPush(initialMsg));
      }
    } catch (_) {
      // Fallback limpio en entornos sin Google Play Services
    }
  }

  @override
  Future<bool> requestPermission() async {
    try {
      final ready = await _asegurarFirebase();
      if (!ready) return false;
      final settings = await FirebaseMessaging.instance.requestPermission(
        alert: true,
        announcement: false,
        badge: true,
        carPlay: false,
        criticalAlert: false,
        provisional: false,
        sound: true,
      );
      return settings.authorizationStatus == AuthorizationStatus.authorized ||
          settings.authorizationStatus == AuthorizationStatus.provisional;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<String?> obtenerToken() async {
    try {
      final ready = await _asegurarFirebase();
      if (!ready) return null;

      await requestPermission();

      // ignore: deprecated_member_use
      final token = await FirebaseMessaging.instance.getToken();
      return token;
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    } on FirebaseException {
      return null;
    } catch (_) {
      return null;
    }
  }

  @override
  Future<NotificacionMensajePush?> getInitialMessage() async {
    try {
      final ready = await _asegurarFirebase();
      if (!ready) return null;
      final msg = await FirebaseMessaging.instance.getInitialMessage();
      return msg != null ? remoteMessageToPush(msg) : null;
    } catch (_) {
      return null;
    }
  }

  @override
  Stream<String> get onTokenRefresh => _tokenRefreshController.stream;

  @override
  Stream<NotificacionMensajePush> get onMessage => _messageController.stream;

  @override
  Stream<NotificacionMensajePush> get onMessageOpenedApp =>
      _messageOpenedController.stream;

  @override
  void setBackgroundMessageHandler(
      Future<void> Function(NotificacionMensajePush mensaje) handler) {
    backgroundMessageHandler = handler;
    if (!_initialized) return;
    try {
      runZonedGuarded(() {
        FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
      }, (error, stack) {
        // Ignorar fallos de canal nativo en plataformas sin soporte
      });
    } catch (_) {
      // Ignorar si el background handler no puede registrarse en esta plataforma
    }
  }

  @override
  Future<void> dispose() async {
    await _tokenRefreshSub?.cancel();
    await _messageSub?.cancel();
    await _messageOpenedSub?.cancel();
    await _tokenRefreshController.close();
    await _messageController.close();
    await _messageOpenedController.close();
  }
}

/// Adaptador simulado para pruebas unitarias, integración y desarrollo sin dependencias de Google Services.
class SimulatedFcmAdapter implements FcmAdapter {
  String? _token;
  bool permisoConcedido = true;
  NotificacionMensajePush? _initialMessage;

  final StreamController<String> _tokenRefreshController =
      StreamController<String>.broadcast();
  final StreamController<NotificacionMensajePush> _messageController =
      StreamController<NotificacionMensajePush>.broadcast();
  final StreamController<NotificacionMensajePush> _messageOpenedController =
      StreamController<NotificacionMensajePush>.broadcast();

  Future<void> Function(NotificacionMensajePush)? _backgroundHandler;

  SimulatedFcmAdapter({String? tokenInicial}) : _token = tokenInicial;

  @override
  Future<String?> obtenerToken() async => _token;

  @override
  Future<bool> requestPermission() async => permisoConcedido;

  @override
  Future<NotificacionMensajePush?> getInitialMessage() async => _initialMessage;

  /// Simula la notificación con la que la app fue abierta en frío
  void simularInitialMessage(NotificacionMensajePush? mensaje) {
    _initialMessage = mensaje;
  }

  @override
  Stream<String> get onTokenRefresh => _tokenRefreshController.stream;

  @override
  Stream<NotificacionMensajePush> get onMessage => _messageController.stream;

  @override
  Stream<NotificacionMensajePush> get onMessageOpenedApp =>
      _messageOpenedController.stream;

  @override
  void setBackgroundMessageHandler(
      Future<void> Function(NotificacionMensajePush mensaje) handler) {
    _backgroundHandler = handler;
  }

  /// Dispara una renovación de token hacia los listeners.
  void simularTokenRefresh(String nuevoToken) {
    _token = nuevoToken;
    _tokenRefreshController.add(nuevoToken);
  }

  /// Dispara un mensaje push en primer plano (foreground).
  void simularMensaje(NotificacionMensajePush mensaje) {
    _messageController.add(mensaje);
  }

  /// Dispara un mensaje push abierto por el usuario.
  void simularMensajeOpenedApp(NotificacionMensajePush mensaje) {
    _messageOpenedController.add(mensaje);
  }

  /// Dispara un mensaje push en background llamando al handler registrado.
  Future<void> simularMensajeBackground(NotificacionMensajePush mensaje) async {
    if (_backgroundHandler != null) {
      await _backgroundHandler!(mensaje);
    }
  }

  @override
  Future<void> dispose() async {
    await _tokenRefreshController.close();
    await _messageController.close();
    await _messageOpenedController.close();
  }
}

/// Servicio de Notificaciones y Registro de Dispositivos Móviles (E2 Avisos Push).
///
/// Gestiona el ciclo de vida completo de notificaciones FCM:
/// - Inicialización con adapter real (FlutterFire) o fallback limpio y descriptivo.
/// - Inyección flexible de FcmAdapter en constructor o método inicializar.
/// - Renovación automática de token con actualización directa en el backend (`POST /notificaciones/dispositivos`).
/// - Recepción en primer y segundo plano con bandeja local offline consultable.
/// - Consulta durable de avisos de negocio y marcado como leída.
class NotificacionMovilService {
  final ApiClient _api;
  FcmAdapter? _adapter;

  EstadoFcm _estadoFcm = EstadoFcm.noConfigurado;
  String? _tokenActual;
  String? _ultimoDiagnostico;
  String? _dispositivoIdActual;
  String? _sucursalIdActual;

  final List<NotificacionAvisoModel> _bandejaOffline = [];
  final StreamController<String> _tokenRefreshController =
      StreamController<String>.broadcast();
  final StreamController<NotificacionMensajePush> _mensajeRecibidoController =
      StreamController<NotificacionMensajePush>.broadcast();

  StreamSubscription<String>? _subToken;
  StreamSubscription<NotificacionMensajePush>? _subMsg;
  StreamSubscription<NotificacionMensajePush>? _subOpened;
  Future<void> Function(NotificacionMensajePush)? _backgroundHandler;

  /// Token mock o de entorno que puede ser fijado globalmente en runtime o pruebas.
  static String? tokenMockConfigurado;

  /// Permite inyectar opcionalmente ApiClient y FcmAdapter desde el constructor.
  NotificacionMovilService({ApiClient? api, FcmAdapter? adapter})
      : _api = api ?? ApiClient(),
        _adapter = adapter;

  /// Adaptador FCM configurado (nativo oficial o simulado).
  FcmAdapter? get adapter => _adapter;

  /// Estado de disponibilidad de FCM.
  EstadoFcm get estadoFcm => _estadoFcm;

  /// Token push actualmente activo y conocido en el dispositivo.
  String? get tokenActual => _tokenActual;

  /// Diagnóstico legible del estado de vinculación FCM.
  String? get ultimoDiagnostico => _ultimoDiagnostico;

  /// Stream público de tokens renovados.
  Stream<String> get onTokenRefresh => _tokenRefreshController.stream;

  /// Stream público de notificaciones recibidas en primer plano.
  Stream<NotificacionMensajePush> get onMensajeRecibido =>
      _mensajeRecibidoController.stream;

  /// Bandeja local de notificaciones para consulta offline.
  List<NotificacionAvisoModel> get bandejaOffline =>
      List.unmodifiable(_bandejaOffline);

  /// Solicita permisos de notificación al sistema operativo (Android 13+ / iOS).
  Future<bool> solicitarPermisos() async {
    if (_adapter != null) {
      return await _adapter!.requestPermission();
    }
    return false;
  }

  /// Consulta la notificación que inició la aplicación en frío (getInitialMessage).
  Future<NotificacionMensajePush?> obtenerNotificacionInicial() async {
    if (_adapter != null) {
      final push = await _adapter!.getInitialMessage();
      if (push != null) {
        _ingresarNotificacionOffline(push.toAvisoModel());
      }
      return push;
    }
    return null;
  }

  /// Inicializa el servicio de notificaciones móviles con el adapter proporcionado
  /// o recurre al adaptador inyectado previamente o al adaptador nativo de plataforma con fallback seguro.
  Future<void> inicializar({
    FcmAdapter? fcmAdapter,
    bool autoRegistrarEnBackend = false,
    String? sucursalId,
    String? dispositivoId,
  }) async {
    _adapter = fcmAdapter ?? _adapter ?? NativePlatformFcmAdapter();
    _dispositivoIdActual =
        dispositivoId ?? await DispositivoHelper.obtenerDispositivoId();
    _sucursalIdActual = sucursalId;

    await _resolverTokenInicial(dispositivoId: _dispositivoIdActual);

    // Cancelar suscripciones previas si existieran
    await _subToken?.cancel();
    await _subMsg?.cancel();
    await _subOpened?.cancel();

    // 1. Listener de renovación de token: actualiza el estado y sincroniza automáticamente con el backend
    _subToken = _adapter!.onTokenRefresh.listen((nuevoToken) async {
      _tokenActual = nuevoToken.trim();
      _tokenRefreshController.add(_tokenActual!);
      try {
        await actualizarToken(
          pushToken: _tokenActual!,
          sucursalId: _sucursalIdActual,
          dispositivoId: _dispositivoIdActual,
        );
      } catch (e) {
        _ultimoDiagnostico =
            'Aviso: Token renovado localmente pero el backend no respondió: $e';
      }
    });

    // 2. Listener de mensajes en primer plano: ingresa a la bandeja local y emite al stream
    _subMsg = _adapter!.onMessage.listen((push) {
      _ingresarNotificacionOffline(push.toAvisoModel());
      _mensajeRecibidoController.add(push);
    });

    // 3. Listener de mensajes abiertos desde notificación del sistema
    _subOpened = _adapter!.onMessageOpenedApp.listen((push) {
      _ingresarNotificacionOffline(push.toAvisoModel());
      _mensajeRecibidoController.add(push);
    });

    // 4. Configurar handler de background en el adapter
    _adapter!.setBackgroundMessageHandler((push) async {
      _ingresarNotificacionOffline(push.toAvisoModel());
      if (_backgroundHandler != null) {
        await _backgroundHandler!(push);
      }
    });

    // 5. Procesar notificación inicial si la app fue abierta desde estado cerrado
    final initPush = await _adapter!.getInitialMessage();
    if (initPush != null) {
      _ingresarNotificacionOffline(initPush.toAvisoModel());
      _mensajeRecibidoController.add(initPush);
    }

    if (autoRegistrarEnBackend && _estadoFcm != EstadoFcm.noConfigurado) {
      await registrarDispositivo(
        pushToken: _tokenActual,
        sucursalId: _sucursalIdActual,
        dispositivoId: _dispositivoIdActual,
      );
    }
  }

  /// Resuelve el token inicial consultando el adapter o activando el fallback seguro.
  Future<void> _resolverTokenInicial({String? dispositivoId}) async {
    final dispId =
        dispositivoId ?? await DispositivoHelper.obtenerDispositivoId();

    String? tokenObtenido;
    try {
      tokenObtenido = await _adapter?.obtenerToken();
    } catch (_) {
      tokenObtenido = null;
    }

    if (tokenObtenido != null && tokenObtenido.trim().isNotEmpty) {
      _tokenActual = tokenObtenido.trim();
      _estadoFcm = (_adapter is SimulatedFcmAdapter)
          ? EstadoFcm.simulado
          : EstadoFcm.activoReal;
      _ultimoDiagnostico = 'Token FCM obtenido exitosamente del proveedor.';
      return;
    }

    if (tokenMockConfigurado != null &&
        tokenMockConfigurado!.trim().isNotEmpty) {
      _tokenActual = tokenMockConfigurado!.trim();
      _estadoFcm = EstadoFcm.simulado;
      _ultimoDiagnostico =
          'Token FCM obtenido de tokenMockConfigurado en runtime.';
      return;
    }

    if (kEnvFcmPushToken.trim().isNotEmpty) {
      _tokenActual = kEnvFcmPushToken.trim();
      _estadoFcm = EstadoFcm.simulado;
      _ultimoDiagnostico =
          'Token FCM obtenido de variable de entorno FCM_PUSH_TOKEN (legacy).';
      return;
    }

    // Fallback limpio y descriptivo sin dependencia forzada de --dart-define
    _tokenActual =
        'sim-fcm-${dispId.length >= 8 ? dispId.substring(0, 8) : dispId}';
    _estadoFcm = EstadoFcm.noConfigurado;
    _ultimoDiagnostico =
        'Firebase no configurado (falta google-services.json o plugin nativo). Modo contingencia con token local descriptivo.';
  }

  /// Configura el callback para procesamiento en background de notificaciones.
  void onBackgroundMessage(
      Future<void> Function(NotificacionMensajePush mensaje) handler) {
    _backgroundHandler = handler;
  }

  /// Registra o actualiza el dispositivo móvil activo ante el backend `/notificaciones/dispositivos`.
  Future<DispositivoRegistroModel> registrarDispositivo({
    String? pushToken,
    String? sucursalId,
    String? dispositivoId,
  }) async {
    final dispId =
        dispositivoId ?? await DispositivoHelper.obtenerDispositivoId();
    _dispositivoIdActual = dispId;
    if (sucursalId != null) _sucursalIdActual = sucursalId;

    if (pushToken != null && pushToken.trim().isNotEmpty) {
      _tokenActual = pushToken.trim();
    } else if (_tokenActual == null) {
      await _resolverTokenInicial(dispositivoId: dispId);
    }

    final tokenFinal = _tokenActual;

    return _api.post<DispositivoRegistroModel>(
      '/notificaciones/dispositivos',
      cuerpo: {
        'dispositivo_id': dispId,
        'canal': 'FLUTTER',
        if (tokenFinal != null) 'push_token': tokenFinal,
        if (sucursalId != null && sucursalId.trim().isNotEmpty)
          'sucursal_id': sucursalId.trim(),
      },
      convertir: (j) =>
          DispositivoRegistroModel.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  /// Actualiza explícitamente el token FCM del dispositivo contra `/api/v1/notificaciones/dispositivos`.
  Future<DispositivoRegistroModel> actualizarToken({
    required String pushToken,
    String? sucursalId,
    String? dispositivoId,
  }) {
    _tokenActual = pushToken.trim();
    return registrarDispositivo(
      pushToken: _tokenActual,
      sucursalId: sucursalId,
      dispositivoId: dispositivoId,
    );
  }

  /// Revoca el registro del dispositivo al cerrar sesión contra `/api/v1/notificaciones/dispositivos/{id}`.
  Future<void> revocarDispositivo({String? dispositivoId}) async {
    final dispId =
        dispositivoId ?? _dispositivoIdActual ?? await DispositivoHelper.obtenerDispositivoId();
    try {
      await _api.delete(
        '/notificaciones/dispositivos/$dispId',
        convertir: (_) => null,
      );
    } catch (_) {
      // Defensivo: no bloquear el cierre de sesión si no hay red
    }
  }

  /// Consulta la bandeja de notificaciones propia del usuario en el backend y fusiona con la local.
  Future<List<NotificacionAvisoModel>> consultarBandeja(
      {int limite = 50}) async {
    final remotas = await _api.get<List<NotificacionAvisoModel>>(
      '/notificaciones/bandeja',
      query: {'limite': '$limite'},
      convertir: (j) => (j as List)
          .map((e) =>
              NotificacionAvisoModel.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
    );

    for (final remota in remotas) {
      final idx = _bandejaOffline.indexWhere((o) => o.id == remota.id);
      if (idx >= 0) {
        _bandejaOffline[idx] = remota;
      } else {
        _bandejaOffline.add(remota);
      }
    }

    return remotas;
  }

  /// Marca una notificación como leída tanto en el backend como en la bandeja local offline.
  Future<NotificacionAvisoModel> marcarLeida(String notificacionId) async {
    final leida = await _api.patch<NotificacionAvisoModel>(
      '/notificaciones/bandeja/$notificacionId/leer',
      convertir: (j) =>
          NotificacionAvisoModel.fromJson((j as Map).cast<String, dynamic>()),
    );

    final idx = _bandejaOffline.indexWhere((o) => o.id == notificacionId);
    if (idx >= 0) {
      _bandejaOffline[idx] = _bandejaOffline[idx].copyWith(
        leidaEn: leida.leidaEn ?? DateTime.now().toUtc().toIso8601String(),
      );
    }

    return leida;
  }

  /// Obtiene la bandeja local offline de avisos push.
  List<NotificacionAvisoModel> obtenerBandejaOffline() {
    return List.unmodifiable(_bandejaOffline);
  }

  /// Inserta una notificación en la bandeja local sin duplicar por ID.
  void _ingresarNotificacionOffline(NotificacionAvisoModel notif) {
    final idx = _bandejaOffline.indexWhere((o) => o.id == notif.id);
    if (idx >= 0) {
      _bandejaOffline[idx] = notif;
    } else {
      _bandejaOffline.insert(0, notif);
    }
  }

  /// Agrega directamente una notificación a la bandeja offline (útil para pruebas o sync).
  void agregarNotificacionOffline(NotificacionAvisoModel notif) {
    _ingresarNotificacionOffline(notif);
  }

  /// Limpia la bandeja offline en memoria.
  void limpiarBandejaOffline() {
    _bandejaOffline.clear();
  }

  /// Libera recursos y suscripciones activas.
  Future<void> dispose() async {
    await _subToken?.cancel();
    await _subMsg?.cancel();
    await _subOpened?.cancel();
    await _adapter?.dispose();
    await _tokenRefreshController.close();
    await _mensajeRecibidoController.close();
  }
}
