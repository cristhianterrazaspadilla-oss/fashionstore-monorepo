import 'package:flutter_test/flutter_test.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:fashionstore_movil/features/identidad_empresas/models/notificacion_model.dart';
import 'package:fashionstore_movil/features/identidad_empresas/services/notificacion_movil_service.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';

class FakeApiClientNotificaciones extends ApiClient {
  final List<String> llamadas = [];

  @override
  Future<T> post<T>(
    String ruta, {
    Object? cuerpo,
    Map<String, String>? query,
    String? idempotencyKey,
    required T Function(dynamic) convertir,
  }) async {
    llamadas.add('POST $ruta: $cuerpo');
    if (ruta == '/notificaciones/dispositivos') {
      final map = (cuerpo as Map?) ?? {};
      return convertir({
        'id': 'reg-1',
        'dispositivo_id': map['dispositivo_id'] ?? 'disp-1',
        'canal': map['canal'] ?? 'FLUTTER',
        'estado': 'ACTIVO',
        'creado_en': '2026-11-04T12:00:00Z',
      });
    }
    throw UnimplementedError('Ruta POST no mockeada: $ruta');
  }

  @override
  Future<T> delete<T>(
    String ruta, {
    Map<String, String>? query,
    String? idempotencyKey,
    required T Function(dynamic) convertir,
  }) async {
    llamadas.add('DELETE $ruta');
    if (ruta.startsWith('/notificaciones/dispositivos/')) {
      return convertir(null);
    }
    throw UnimplementedError('Ruta DELETE no mockeada: $ruta');
  }

  @override
  Future<T> get<T>(
    String ruta, {
    Map<String, String>? query,
    required T Function(dynamic) convertir,
  }) async {
    llamadas.add('GET $ruta');
    if (ruta == '/notificaciones/bandeja') {
      return convertir([
        {
          'id': 'notif-1',
          'tipo': 'COMPRA_CONFIRMADA',
          'titulo': '¡Pago recibido!',
          'cuerpo': 'Tu pedido fue capturado con éxito tras confirmación Stripe.',
          'recurso_tipo': 'PEDIDO',
          'recurso_id': 'ped-100',
          'creada_en': '2026-11-04T12:01:00Z',
          'leida_en': null,
        }
      ]);
    }
    throw UnimplementedError('Ruta GET no mockeada: $ruta');
  }

  @override
  Future<T> patch<T>(
    String ruta, {
    Object? cuerpo,
    Map<String, String>? query,
    String? idempotencyKey,
    required T Function(dynamic) convertir,
  }) async {
    llamadas.add('PATCH $ruta');
    if (ruta.startsWith('/notificaciones/bandeja/') && ruta.endsWith('/leer')) {
      return convertir({
        'id': 'notif-1',
        'tipo': 'COMPRA_CONFIRMADA',
        'titulo': '¡Pago recibido!',
        'cuerpo': 'Tu pedido fue capturado con éxito tras confirmación Stripe.',
        'recurso_tipo': 'PEDIDO',
        'recurso_id': 'ped-100',
        'creada_en': '2026-11-04T12:01:00Z',
        'leida_en': '2026-11-04T12:05:00Z',
      });
    }
    throw UnimplementedError('Ruta PATCH no mockeada: $ruta');
  }
}

/// Adapter que simula fallas de plugin o ausencia de Google Services
class FailingFcmAdapter implements FcmAdapter {
  @override
  Future<String?> obtenerToken() async => null;

  @override
  Future<bool> requestPermission() async => false;

  @override
  Future<NotificacionMensajePush?> getInitialMessage() async => null;

  @override
  Stream<String> get onTokenRefresh => const Stream.empty();

  @override
  Stream<NotificacionMensajePush> get onMessage => const Stream.empty();

  @override
  Stream<NotificacionMensajePush> get onMessageOpenedApp => const Stream.empty();

  @override
  void setBackgroundMessageHandler(
      Future<void> Function(NotificacionMensajePush mensaje) handler) {}

  @override
  Future<void> dispose() async {}
}

void main() {
  setUpAll(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  late FakeApiClientNotificaciones fakeApi;
  late NotificacionMovilService service;

  setUp(() {
    fakeApi = FakeApiClientNotificaciones();
    service = NotificacionMovilService(api: fakeApi);
    NotificacionMovilService.tokenMockConfigurado = null;
  });

  tearDown(() async {
    await service.dispose();
  });

  group('NotificacionMovilService E2 Dispositivos y Bandeja Móvil', () {
    test('registrarDispositivo envía payload con canal FLUTTER y persiste vinculación', () async {
      final res = await service.registrarDispositivo(
        dispositivoId: 'disp-test-uuid',
        pushToken: 'token-fcm-test',
      );

      expect(res.id, equals('reg-1'));
      expect(res.dispositivoId, equals('disp-test-uuid'));
      expect(res.canal, equals('FLUTTER'));
      expect(res.estado, equals('ACTIVO'));
      expect(fakeApi.llamadas.first, contains('POST /notificaciones/dispositivos'));
      expect(fakeApi.llamadas.first, contains('canal: FLUTTER'));
    });

    test('revocarDispositivo invoca endpoint DELETE correspondiente', () async {
      await service.revocarDispositivo(dispositivoId: 'disp-test-uuid');
      expect(fakeApi.llamadas.any((l) => l.contains('DELETE /notificaciones/dispositivos/disp-test-uuid')), isTrue);
    });

    test('consultarBandeja y marcarLeida consumen avisos de negocio', () async {
      final lista = await service.consultarBandeja(limite: 10);
      expect(lista.length, equals(1));
      expect(lista.first.tipo, equals('COMPRA_CONFIRMADA'));
      expect(lista.first.estaLeida, isFalse);

      final leida = await service.marcarLeida('notif-1');
      expect(leida.id, equals('notif-1'));
      expect(leida.estaLeida, isTrue);
    });
  });

  group('Puerta D — Ciclo de Vida y Fallback FCM', () {
    test('inicialización con SimulatedFcmAdapter obtiene token inicial y activa listeners', () async {
      final adapter = SimulatedFcmAdapter(tokenInicial: 'token-fcm-valido-123');

      await service.inicializar(
        fcmAdapter: adapter,
        dispositivoId: 'disp-mock-01',
        autoRegistrarEnBackend: true,
      );

      expect(service.estadoFcm, equals(EstadoFcm.simulado));
      expect(service.tokenActual, equals('token-fcm-valido-123'));
      expect(service.ultimoDiagnostico, contains('Token FCM obtenido'));
      expect(fakeApi.llamadas.any((l) => l.contains('token-fcm-valido-123')), isTrue);
    });

    test('inicialización sin configuración (FailingFcmAdapter) recurre a fallback limpio', () async {
      final adapter = FailingFcmAdapter();

      await service.inicializar(
        fcmAdapter: adapter,
        dispositivoId: 'disp-sin-google-services',
        autoRegistrarEnBackend: false,
      );

      expect(service.estadoFcm, equals(EstadoFcm.noConfigurado));
      expect(service.tokenActual, startsWith('sim-fcm-disp-sin'));
      expect(service.ultimoDiagnostico, contains('Firebase no configurado'));
    });

    test('sin --dart-define ni token externo, el servicio no crashea y registra fallback válido', () async {
      final res = await service.registrarDispositivo(
        dispositivoId: 'disp-autonomo-99',
      );

      expect(res.id, equals('reg-1'));
      expect(service.tokenActual, startsWith('sim-fcm-disp-aut'));
      expect(fakeApi.llamadas.last, contains('push_token: sim-fcm-disp-aut'));
    });

    test('tokenMockConfigurado permite inyección global de pruebas en tiempo de ejecución', () async {
      NotificacionMovilService.tokenMockConfigurado = 'token-global-runtime-qa';

      final res = await service.registrarDispositivo(
        dispositivoId: 'disp-qa-02',
      );

      expect(res.id, equals('reg-1'));
      expect(service.tokenActual, equals('token-global-runtime-qa'));
      expect(fakeApi.llamadas.last, contains('token-global-runtime-qa'));
    });

    test('onTokenRefresh del adapter actualiza token interno y re-registra automáticamente en backend', () async {
      final adapter = SimulatedFcmAdapter(tokenInicial: 'token-original-001');

      await service.inicializar(
        fcmAdapter: adapter,
        dispositivoId: 'disp-sync-03',
        autoRegistrarEnBackend: false,
      );

      expect(service.tokenActual, equals('token-original-001'));
      fakeApi.llamadas.clear();

      String? tokenEmitidoEnStream;
      final sub = service.onTokenRefresh.listen((t) {
        tokenEmitidoEnStream = t;
      });

      // Simular que Firebase renueva el token
      adapter.simularTokenRefresh('token-renovado-002');
      await Future<void>.delayed(const Duration(milliseconds: 50));

      expect(tokenEmitidoEnStream, equals('token-renovado-002'));
      expect(service.tokenActual, equals('token-renovado-002'));
      expect(fakeApi.llamadas.any((l) => l.contains('POST /notificaciones/dispositivos') && l.contains('token-renovado-002')), isTrue);

      await sub.cancel();
    });

    test('notificación en primer plano (foreground) ingresa en bandejaOffline y emite por stream', () async {
      final adapter = SimulatedFcmAdapter(tokenInicial: 'token-foreground');

      await service.inicializar(
        fcmAdapter: adapter,
        dispositivoId: 'disp-foreground-04',
      );

      NotificacionMensajePush? pushRecibido;
      final sub = service.onMensajeRecibido.listen((m) {
        pushRecibido = m;
      });

      final mensaje = NotificacionMensajePush(
        id: 'msg-push-10',
        titulo: '¡Pedido Despachado!',
        cuerpo: 'Tu envío #101 va en camino.',
        datos: {'tipo': 'PEDIDO_DESPACHADO', 'recurso_id': 'ped-101'},
      );

      adapter.simularMensaje(mensaje);
      await Future<void>.delayed(const Duration(milliseconds: 20));

      expect(pushRecibido, isNotNull);
      expect(pushRecibido!.id, equals('msg-push-10'));
      expect(pushRecibido!.titulo, equals('¡Pedido Despachado!'));

      // Verificar que se guardó en la bandeja offline local
      final offline = service.obtenerBandejaOffline();
      expect(offline.length, equals(1));
      expect(offline.first.id, equals('msg-push-10'));
      expect(offline.first.titulo, equals('¡Pedido Despachado!'));
      expect(offline.first.tipo, equals('PEDIDO_DESPACHADO'));

      await sub.cancel();
    });

    test('notificación abierta desde la barra del sistema (onMessageOpenedApp) se almacena offline', () async {
      final adapter = SimulatedFcmAdapter(tokenInicial: 'token-opened');

      await service.inicializar(
        fcmAdapter: adapter,
        dispositivoId: 'disp-opened-05',
      );

      final mensaje = NotificacionMensajePush(
        id: 'msg-opened-20',
        titulo: '¡Descuento Flash!',
        cuerpo: '20% en abrigos por hoy.',
        datos: {'tipo': 'PROMOCION_FLASH'},
      );

      adapter.simularMensajeOpenedApp(mensaje);
      await Future<void>.delayed(const Duration(milliseconds: 20));

      final offline = service.obtenerBandejaOffline();
      expect(offline.any((n) => n.id == 'msg-opened-20'), isTrue);
    });

    test('notificación en background invoca callback registrado y actualiza bandeja offline', () async {
      final adapter = SimulatedFcmAdapter(tokenInicial: 'token-bg');

      await service.inicializar(
        fcmAdapter: adapter,
        dispositivoId: 'disp-bg-06',
      );

      bool callbackEjecutado = false;
      service.onBackgroundMessage((msg) async {
        callbackEjecutado = true;
        expect(msg.id, equals('msg-bg-30'));
      });

      final mensaje = NotificacionMensajePush(
        id: 'msg-bg-30',
        titulo: 'Stock Actualizado',
        cuerpo: 'Nueva reposición en tienda.',
        datos: {'tipo': 'STOCK_ALERTA'},
      );

      await adapter.simularMensajeBackground(mensaje);

      expect(callbackEjecutado, isTrue);
      expect(service.obtenerBandejaOffline().any((n) => n.id == 'msg-bg-30'), isTrue);
    });

    test('consultarBandeja fusiona avisos del backend con la bandeja local offline', () async {
      // Pre-cargar una notificación offline
      service.agregarNotificacionOffline(NotificacionAvisoModel(
        id: 'offline-previa',
        tipo: 'AVISO_LOCAL',
        titulo: 'Aviso local almacenado',
        cuerpo: 'Guardado offline.',
        creadaEn: '2026-11-04T10:00:00Z',
      ));

      final lista = await service.consultarBandeja();
      expect(lista.length, equals(1)); // 1 remota
      expect(lista.first.id, equals('notif-1'));

      // La bandeja offline ahora contiene tanto la previa como la remota
      final totalOffline = service.obtenerBandejaOffline();
      expect(totalOffline.length, equals(2));
      expect(totalOffline.any((n) => n.id == 'offline-previa'), isTrue);
      expect(totalOffline.any((n) => n.id == 'notif-1'), isTrue);
    });

    test('marcarLeida actualiza estado tanto en backend como en bandejaOffline local', () async {
      service.agregarNotificacionOffline(NotificacionAvisoModel(
        id: 'notif-1',
        tipo: 'COMPRA_CONFIRMADA',
        titulo: '¡Pago recibido!',
        cuerpo: 'Tu pedido fue capturado.',
        creadaEn: '2026-11-04T12:01:00Z',
        leidaEn: null,
      ));

      expect(service.obtenerBandejaOffline().first.estaLeida, isFalse);

      final leida = await service.marcarLeida('notif-1');
      expect(leida.id, equals('notif-1'));
      expect(leida.estaLeida, isTrue);

      expect(service.obtenerBandejaOffline().first.estaLeida, isTrue);
    });

    test('constructor permite inyectar FcmAdapter directamente', () async {
      final adapter = SimulatedFcmAdapter(tokenInicial: 'token-inyectado-ctor');
      final servicioInyectado = NotificacionMovilService(api: fakeApi, adapter: adapter);

      expect(servicioInyectado.adapter, equals(adapter));
      await servicioInyectado.inicializar(dispositivoId: 'disp-ctor');

      expect(servicioInyectado.tokenActual, equals('token-inyectado-ctor'));
      expect(servicioInyectado.estadoFcm, equals(EstadoFcm.simulado));
      await servicioInyectado.dispose();
    });

    test('cold start: getInitialMessage ingresa notificación previa en bandeja offline', () async {
      final adapter = SimulatedFcmAdapter(tokenInicial: 'token-cold');
      final coldPush = NotificacionMensajePush(
        id: 'cold-start-99',
        titulo: 'Entrega en Camino',
        cuerpo: 'Tu repartidor está cerca',
        datos: {'tipo': 'DELIVERY_STATUS'},
      );
      adapter.simularInitialMessage(coldPush);

      await service.inicializar(fcmAdapter: adapter, dispositivoId: 'disp-cold');

      final offline = service.obtenerBandejaOffline();
      expect(offline.any((n) => n.id == 'cold-start-99'), isTrue);
      final leida = await service.obtenerNotificacionInicial();
      expect(leida?.id, equals('cold-start-99'));
    });

    test('solicitarPermisos delega al adapter y retorna estado booleano', () async {
      final adapter = SimulatedFcmAdapter();
      adapter.permisoConcedido = true;
      await service.inicializar(fcmAdapter: adapter, dispositivoId: 'disp-perm');
      expect(await service.solicitarPermisos(), isTrue);

      adapter.permisoConcedido = false;
      expect(await service.solicitarPermisos(), isFalse);
    });

    test('NativePlatformFcmAdapter opera defensivamente cuando Firebase no está inicializado', () async {
      final native = NativePlatformFcmAdapter();

      // En entorno de prueba unitaria sin Firebase.initializeApp() de plataforma,
      // las llamadas no deben crashear sino retornar valores defensivos nulos/falsos.
      final token = await native.obtenerToken();
      expect(token, isNull);

      final perm = await native.requestPermission();
      expect(perm, isFalse);

      final initMsg = await native.getInitialMessage();
      expect(initMsg, isNull);

      // NotificacionMovilService inicializado con el adaptador nativo sin Firebase
      // entra de manera segura y limpia en modo EstadoFcm.noConfigurado con fallback local
      await service.inicializar(
        fcmAdapter: native,
        dispositivoId: 'disp-defensivo-native',
      );
      expect(service.estadoFcm, equals(EstadoFcm.noConfigurado));
      expect(service.tokenActual, startsWith('sim-fcm-disp-def'));
      expect(service.ultimoDiagnostico, contains('Firebase no configurado'));

      await native.dispose();
    });

    test('NativePlatformFcmAdapter.remoteMessageToPush mapea payload oficial de RemoteMessage', () {
      const remoteMsg = RemoteMessage(
        messageId: 'fcm-oficial-100',
        notification: RemoteNotification(
          title: 'Notificación Oficial FlutterFire',
          body: 'Cuerpo del mensaje recibido',
        ),
        data: {'tipo': 'PROMOCION_EXCLUSIVA', 'cupon': 'VERANO2026'},
      );

      final push = NativePlatformFcmAdapter.remoteMessageToPush(remoteMsg);
      expect(push.id, equals('fcm-oficial-100'));
      expect(push.titulo, equals('Notificación Oficial FlutterFire'));
      expect(push.cuerpo, equals('Cuerpo del mensaje recibido'));
      expect(push.datos['tipo'], equals('PROMOCION_EXCLUSIVA'));
      expect(push.datos['cupon'], equals('VERANO2026'));
    });
  });
}
