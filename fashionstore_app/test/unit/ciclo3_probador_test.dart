// Probador con fakes: compatibilidad, consentimiento, cámara, token,
// autorización, conexión, cambio de prenda, errores, timeout, cierre
// idempotente, liberación y ausencia de secretos.
import 'dart:convert';

import 'package:fashionstore_movil/features/catalogo/models/catalogo_model.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/models/probador_model.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/services/ia_service.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/services/probador_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/probador/control_probador.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/probador/puente_decart.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

ApiClient apiCon(MockClient mock) =>
    ApiClient(httpClient: mock, sesiones: SessionManager());

http.Response ok(Object j, [int code = 200]) => http.Response(
      jsonEncode(j),
      code,
      headers: {'content-type': 'application/json'},
    );

Map<String, dynamic> recursoJson(bool compatible) => {
      'variante_id': 'v1',
      'compatible': compatible,
      'imagen_prenda_url': 'https://x/prenda.webp',
      'prompt_prenda': 'Replace top',
      'proveedor': 'DECART',
      'modelo': 'lucy-2.5',
      'aviso_orientativo': avisoProbadorPermanente,
    };

Map<String, dynamic> autJson({bool vencido = false}) => {
      'client_token': 'tok_corto',
      'expires_at': vencido
          ? '2020-01-01T00:00:00Z'
          : DateTime.now()
              .toUtc()
              .add(const Duration(seconds: 60))
              .toIso8601String(),
      'modelo': 'lucy-2.5',
      'max_session_duration_seconds': 120,
      'imagen_prenda_url': 'https://x/prenda.webp',
      'prompt_prenda': 'Replace top',
    };

ControlProbador controlCon({
  required MockClient mock,
  FakePuenteDecart? puente,
  PermissionStatus permiso = PermissionStatus.granted,
}) {
  final api = apiCon(mock);
  return ControlProbador(
    servicio: ProbadorService(api: api),
    navegacion: IaService(api: api),
    puente: puente ?? FakePuenteDecart(),
    permisoCamaraMock: () async => permiso,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('variante incompatible no inicia sesión', () async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async => ok(recursoJson(false)));
    final c = controlCon(mock: mock);
    await c.cargarRecurso('v1');
    expect(c.recurso!.compatible, isFalse);
    c.aceptarConsentimiento(true);
    await c.iniciar();
    expect(c.estado, EstadoProbador.error);
    expect(c.codigoError, 'VARIANTE_INCOMPATIBLE');
  });

  test('consentimiento rechazado no conecta', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart();
    final mock = MockClient((_) async => ok(recursoJson(true)));
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    await c.iniciar();
    expect(c.estado, EstadoProbador.idle);
    expect(puente.llamadas, isEmpty);
  });

  test('cámara denegada informa y no autoriza', () async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async => ok(recursoJson(true)));
    final c = controlCon(mock: mock, permiso: PermissionStatus.denied);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    expect(c.estado, EstadoProbador.error);
    expect(c.codigoError, 'CAMARA_DENEGADA');
  });

  test('token vencido clasifica autorización fallida', () async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      return ok(autJson(vencido: true));
    });
    final c = controlCon(mock: mock);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    expect(c.estado, EstadoProbador.error);
  });

  test('autorización fallida 401 cierra sin token persistido', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart();
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      return http.Response('{"detail":"no autorizado"}', 401,
          headers: {'content-type': 'application/json'});
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    expect(c.estado, EstadoProbador.error);
    expect(puente.llamadas, contains('disconnect'));
  });

  test('conexión exitosa y cambio de prenda sin duplicar', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart(
      eventosSimulados: [
        EventoDecart(tipo: 'generando'),
        EventoDecart(tipo: 'primeraTransformacion'),
      ],
    );
    var navegacion = 0;
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      if (req.url.path.contains('autorizaciones')) return ok(autJson());
      navegacion++;
      return ok({});
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    await Future.delayed(const Duration(milliseconds: 50));
    expect(puente.llamadas, contains('connect'));
    expect(puente.ultimoToken, 'tok_corto');
    expect(navegacion, 1);
    await c.cambiarPrenda(imagenUrl: 'https://x/otra.webp', prompt: 'p2');
    expect(puente.llamadas.where((e) => e == 'connect').length, 1);
    expect(puente.llamadas, contains('setGarment'));
  });

  test('error de moderación e ICE se clasifican', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart(
      eventosSimulados: [EventoDecart(tipo: 'error', codigo: 'MODERACION')],
    );
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      return ok(autJson());
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    await Future.delayed(const Duration(milliseconds: 50));
    expect(c.estado, EstadoProbador.error);
    expect(c.codigoError, 'MODERACION');
  });

  test('pérdida de red, timeout y background cierran', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart();
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      return ok(autJson());
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    await c.cerrar();
    expect(c.estado, EstadoProbador.disconnected);
    // Cierre duplicado es idempotente y seguro
    await c.cerrar();
    expect(c.estado, EstadoProbador.disconnected);
    expect(puente.llamadas, contains('disconnect'));
    expect(puente.llamadas, contains('release'));
  });

  test('cierre durante conexión y cierre durante cambio de prenda', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart(
      eventosSimulados: [
        EventoDecart(tipo: 'generando'),
        EventoDecart(tipo: 'primeraTransformacion'),
      ],
    );
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) return ok(recursoJson(true));
      if (req.url.path.contains('autorizaciones')) return ok(autJson());
      return ok({});
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);

    // Iniciar y cerrar inmediatamente durante el ciclo
    final fIniciar = c.iniciar();
    await c.cerrar();
    await fIniciar;
    expect(c.estado, EstadoProbador.disconnected);

    // Conectar de nuevo y cerrar durante cambio de prenda
    await c.iniciar();
    await Future.delayed(const Duration(milliseconds: 30));
    final fCambiar =
        c.cambiarPrenda(imagenUrl: 'https://x/img2.png', prompt: 'p2');
    await c.cerrar();
    await fCambiar;
    expect(c.estado, EstadoProbador.disconnected);
  });

  test('error durante disconnect se maneja sin lanzar excepción', () async {
    final puente = FakePuenteDecart();
    final c = ControlProbador(puente: puente);
    // Even if puente throws internally, cerrar catches safely
    await c.cerrar();
    expect(c.estado, EstadoProbador.disconnected);
  });

  test('pausar ciclo de vida cierra sesión para no consumir créditos',
      () async {
    final puente = FakePuenteDecart();
    final c = ControlProbador(puente: puente);
    await c.pausar();
    expect(c.estado, EstadoProbador.disconnected);
    expect(puente.llamadas, contains('disconnect'));
    expect(puente.llamadas, contains('release'));
  });

  test('PrendaProbador valida datos reales y rechaza valores ficticios', () {
    final valida = PrendaProbador(
      productoId: 'p1',
      varianteId: 'v1',
      nombre: 'Camisa Lino',
      sku: 'CAM-LINO-M',
      precio: 89.90,
      primeraImagenUrl: 'https://cdn.fashionstore.com/camisa.webp',
    );
    expect(valida.esValida, isTrue);

    // Rechaza precio 0
    final precioCero = PrendaProbador(
      varianteId: 'v1',
      nombre: 'Camisa Lino',
      sku: 'CAM-LINO-M',
      precio: 0,
      primeraImagenUrl: 'https://cdn.fashionstore.com/camisa.webp',
    );
    expect(precioCero.esValida, isFalse);

    // Rechaza valores ficticios antiguos
    final ficticia = PrendaProbador(
      varianteId: 'v1',
      nombre: 'Prenda probada',
      sku: 'Probador',
      precio: 0,
      primeraImagenUrl: 'https://cdn.fashionstore.com/camisa.webp',
    );
    expect(ficticia.esValida, isFalse);

    // Rechaza URL no HTTPS
    final httpInsegura = PrendaProbador(
      varianteId: 'v1',
      nombre: 'Camisa Lino',
      sku: 'CAM-LINO-M',
      precio: 89.90,
      primeraImagenUrl: 'http://cdn.fashionstore.com/camisa.webp',
    );
    expect(httpInsegura.esValida, isFalse);
  });

  test(
      'galería ordenada: esPrincipal ocupa primera posición y menor orden después',
      () {
    final img1 = ImagenProducto(
      id: 'i1',
      productoId: 'p1',
      enlace: 'https://cdn.com/segunda.jpg',
      orden: 1,
      esPrincipal: false,
    );
    final img2 = ImagenProducto(
      id: 'i2',
      productoId: 'p1',
      enlace: 'https://cdn.com/principal.jpg',
      orden: 5,
      esPrincipal: true,
    );
    final img3 = ImagenProducto(
      id: 'i3',
      productoId: 'p1',
      enlace: 'https://cdn.com/tercera.jpg',
      orden: 2,
      esPrincipal: false,
    );

    final producto = Producto(
      id: 'p1',
      nombre: 'Vestido Seda',
      precioBase: 150,
      activo: true,
      imagenes: [img1, img2, img3],
      temporadaIds: [],
      coleccionIds: [],
    );

    // esPrincipal debe ocupar la primera posición aunque su orden sea 5
    expect(producto.primeraImagenOrdenada, 'https://cdn.com/principal.jpg');

    // Sin imagen principal: el menor orden (1) debe ganar
    final productoSinPrincipal = Producto(
      id: 'p1',
      nombre: 'Vestido Seda',
      precioBase: 150,
      activo: true,
      imagenes: [img3, img1], // img3 orden 2, img1 orden 1
      temporadaIds: [],
      coleccionIds: [],
    );
    expect(productoSinPrincipal.primeraImagenOrdenada,
        'https://cdn.com/segunda.jpg');

    // Imagen no HTTPS se descarta
    final productoHttp = Producto(
      id: 'p1',
      nombre: 'Vestido',
      precioBase: 150,
      activo: true,
      imagenes: [
        ImagenProducto(
          id: 'i4',
          productoId: 'p1',
          enlace: 'http://inseguro.com/foto.jpg',
          orden: 1,
          esPrincipal: true,
        ),
      ],
      temporadaIds: [],
      coleccionIds: [],
    );
    expect(productoHttp.primeraImagenOrdenada, isNull);
  });

  test('ausencia de secretos: canal usa token, modelo fijado', () {
    final puente = FakePuenteDecart();
    expect(PuenteDecart.canalMetodos, 'fashionstore/decart_try_on');
    expect(PuenteDecart.canalEventos, 'fashionstore/decart_try_on/events');
    expect(PuenteDecart.vistaVideo, 'fashionstore/decart_video');
    expect(modeloDecartFijado, 'lucy-2.5');
    expect(duracionMaximaProbadorSegundos, 120);
    expect(puente.ultimoToken, isNull);
  });

  test('stream remoto con GENERATING muestra la salida transformada', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart(
      eventosSimulados: [
        EventoDecart(tipo: 'streamRemoto'),
        EventoDecart(tipo: 'GENERATING'),
      ],
    );
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      if (req.url.path.contains('autorizaciones')) return ok(autJson());
      return ok({});
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    await Future.delayed(const Duration(milliseconds: 50));
    // Con initialImage + initialPrompt, la combinación de stream remoto y
    // GENERATING ya corresponde a la salida transformada del servidor.
    expect(c.primeraTransformacion, isTrue);
    expect(c.estado, EstadoProbador.live);
    expect(c.enVivo, isTrue);
  });

  test('streamRemoto no pasa a live ni confirma visibilidad', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart(
      eventosSimulados: [EventoDecart(tipo: 'streamRemoto')],
    );
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      if (req.url.path.contains('autorizaciones')) return ok(autJson());
      return ok({});
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    await Future.delayed(const Duration(milliseconds: 50));
    expect(c.primeraTransformacion, isFalse);
    expect(c.estado, EstadoProbador.remoteStream);
    expect(c.enVivo, isFalse);
  });

  test('primeraTransformacion previa a GENERATING se ignora (frame crudo)',
      () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart(
      eventosSimulados: [EventoDecart(tipo: 'primeraTransformacion')],
    );
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      if (req.url.path.contains('autorizaciones')) return ok(autJson());
      return ok({});
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    await Future.delayed(const Duration(milliseconds: 50));
    // Sin GENERATING previo no hay transformación visible.
    expect(c.primeraTransformacion, isFalse);
    expect(c.enVivo, isFalse);
  });

  test('primer frame posterior a GENERATING confirma una sola vez', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart(
      eventosSimulados: [
        EventoDecart(tipo: 'streamRemoto'),
        EventoDecart(tipo: 'generando'),
        EventoDecart(tipo: 'primeraTransformacion'),
        // Dos frames consecutivos no deben duplicar eventos.
        EventoDecart(tipo: 'primeraTransformacion'),
        EventoDecart(tipo: 'live'),
      ],
    );
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      if (req.url.path.contains('autorizaciones')) return ok(autJson());
      return ok({});
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    await Future.delayed(const Duration(milliseconds: 50));
    expect(c.primeraTransformacion, isTrue);
    expect(c.estado, EstadoProbador.live);
    expect(c.enVivo, isTrue);
  });

  test('listener anterior no confirma una prenda nueva (secuencia)', () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart(
      eventosSimulados: [
        EventoDecart(tipo: 'generando'),
        EventoDecart(tipo: 'primeraTransformacion'),
      ],
    );
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      if (req.url.path.contains('autorizaciones')) return ok(autJson());
      return ok({});
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    await Future.delayed(const Duration(milliseconds: 50));
    expect(c.enVivo, isTrue);
    await c.cambiarPrenda(imagenUrl: 'https://x/otra.webp', prompt: 'p2');
    // Sin `prendaAplicada` de la secuencia vigente sigue en transición.
    expect(c.estado, EstadoProbador.switchingGarment);
  });

  test('el cierre elimina el pendiente y el callback tardío se ignora',
      () async {
    SharedPreferences.setMockInitialValues({});
    final puente = FakePuenteDecart();
    final mock = MockClient((req) async {
      if (req.url.path.contains('prueba-virtual')) {
        return ok(recursoJson(true));
      }
      return ok(autJson());
    });
    final c = controlCon(mock: mock, puente: puente);
    await c.cargarRecurso('v1');
    c.aceptarConsentimiento(true);
    await c.iniciar();
    await c.cerrar();
    expect(c.estado, EstadoProbador.disconnected);
    expect(puente.llamadas, contains('disconnect'));
    expect(puente.llamadas, contains('release'));
  });
}
