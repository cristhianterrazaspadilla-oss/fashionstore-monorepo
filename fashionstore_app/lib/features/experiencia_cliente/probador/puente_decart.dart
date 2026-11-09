// Puente Flutter <-> nativo Decart (CU17).
//
// Canales:
// - MethodChannel("fashionstore/decart_try_on"): initialize, connect,
//   setGarment, disconnect, release.
// - EventChannel("fashionstore/decart_try_on/events"): estado y errores.
// - PlatformView("fashionstore/decart_video"): video remoto (Android).
// Solo se transporta el token cliente de corta duración (memoria); nunca la
// API key permanente, SDP, Base64 ni video.
import 'package:flutter/services.dart';

class EventoDecart {
  final String tipo;
  final String? codigo;
  final String? mensaje;
  EventoDecart({required this.tipo, this.codigo, this.mensaje});

  factory EventoDecart.fromMap(Map<dynamic, dynamic> m) => EventoDecart(
        tipo: '${m['tipo'] ?? m['type'] ?? ''}',
        codigo: m['codigo']?.toString() ?? m['code']?.toString(),
        mensaje: m['mensaje']?.toString() ?? m['message']?.toString(),
      );
}

class PuenteDecart {
  static const String canalMetodos = 'fashionstore/decart_try_on';
  static const String canalEventos = 'fashionstore/decart_try_on/events';
  static const String vistaVideo = 'fashionstore/decart_video';

  final MethodChannel _metodos;
  final EventChannel _eventos;

  PuenteDecart({MethodChannel? metodos, EventChannel? eventos})
      : _metodos = metodos ?? const MethodChannel(canalMetodos),
        _eventos = eventos ?? const EventChannel(canalEventos);

  Stream<EventoDecart> eventos() => _eventos.receiveBroadcastStream().map(
        (e) => EventoDecart.fromMap((e as Map?) ?? {}),
      );

  Future<void> initialize() => _metodos.invokeMethod('initialize');

  Future<void> connect({
    required String tokenCliente,
    required String imagenPrendaUrl,
    required String promptPrenda,
  }) =>
      _metodos.invokeMethod('connect', {
        'token': tokenCliente,
        'imagenPrendaUrl': imagenPrendaUrl,
        'promptPrenda': promptPrenda,
        'modelo': 'lucy-2.5',
      });

  Future<void> setGarment({
    required String imagenPrendaUrl,
    required String promptPrenda,
  }) =>
      _metodos.invokeMethod('setGarment', {
        'imagenPrendaUrl': imagenPrendaUrl,
        'promptPrenda': promptPrenda,
      });

  /// Cierre idempotente: seguro llamar varias veces y ante errores.
  Future<void> disconnect() async {
    try {
      await _metodos.invokeMethod('disconnect');
    } catch (_) {}
  }

  Future<void> release() async {
    try {
      await _metodos.invokeMethod('release');
    } catch (_) {}
  }
}

/// Doble para pruebas y emulador: simula eventos sin Decart real.
class FakePuenteDecart extends PuenteDecart {
  final List<EventoDecart> eventosSimulados;
  final List<String> llamadas = [];
  String? ultimoToken;
  bool fallaConexion = false;

  FakePuenteDecart({this.eventosSimulados = const []})
      : super(
          metodos: const MethodChannel('test/decart'),
          eventos: const EventChannel('test/decart/events'),
        );

  @override
  Stream<EventoDecart> eventos() => Stream.fromIterable(eventosSimulados);

  @override
  Future<void> initialize() async {
    llamadas.add('initialize');
  }

  @override
  Future<void> connect({
    required String tokenCliente,
    required String imagenPrendaUrl,
    required String promptPrenda,
  }) async {
    llamadas.add('connect');
    ultimoToken = tokenCliente;
    if (fallaConexion) throw PlatformException(code: 'ERROR_CONEXION');
  }

  @override
  Future<void> setGarment({
    required String imagenPrendaUrl,
    required String promptPrenda,
  }) async {
    llamadas.add('setGarment');
  }

  @override
  Future<void> disconnect() async {
    llamadas.add('disconnect');
  }

  @override
  Future<void> release() async {
    llamadas.add('release');
  }
}
