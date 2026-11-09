import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/reservas_traslados/services/traslado_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> _trasladoJson() => {
      'id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      'reserva_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      'sucursal_origen_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
      'sucursal_destino_id': 'dddddddd-dddd-dddd-dddd-dddddddddddd',
      'estado': 'SOLICITADO',
      'fecha_solicitud': '2026-09-15T10:00:00Z',
      'detalles': [],
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('reintento de traslado reutiliza la misma Idempotency-Key', () async {
    SharedPreferences.setMockInitialValues({});
    final clavesEnviadas = <String?>[];
    var llamadas = 0;
    final mock = MockClient((req) async {
      llamadas++;
      clavesEnviadas.add(req.headers['Idempotency-Key']);
      expect(req.headers['Idempotency-Key'], 'clave-reintento-1');
      final cuerpo = jsonDecode(req.body) as Map<String, dynamic>;
      expect(cuerpo['detalle_reserva_id'], 'linea-1');
      expect(cuerpo['sucursal_origen_id'], isNotEmpty);
      if (llamadas == 1) {
        throw http.ClientException('red caída');
      }
      return http.Response(
        jsonEncode(_trasladoJson()),
        201,
        headers: {'content-type': 'application/json'},
      );
    });

    final srv = TrasladoService(
        api: ApiClient(httpClient: mock, sesiones: SessionManager()));

    try {
      await srv.reintentarLinea(
        detalleReservaId: 'linea-1',
        nuevoOrigenId: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
        claveIdempotencia: 'clave-reintento-1',
      );
      fail('el primer intento debía fallar');
    } catch (_) {}

    final t = await srv.reintentarLinea(
      detalleReservaId: 'linea-1',
      nuevoOrigenId: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
      claveIdempotencia: 'clave-reintento-1',
    );
    expect(t.estado, 'SOLICITADO');
    expect(clavesEnviadas, ['clave-reintento-1', 'clave-reintento-1']);
  });

  test('ApiClient notifica 401 global una vez por respuesta 401', () async {
    SharedPreferences.setMockInitialValues({});
    final anterior = ApiClient.onNoAutorizadoGlobal;
    var avisos = 0;
    ApiClient.onNoAutorizadoGlobal = () => avisos++;
    addTearDown(() => ApiClient.onNoAutorizadoGlobal = anterior);

    final mock = MockClient((req) async => http.Response(
          jsonEncode({'detail': 'No autenticado'}),
          401,
          headers: {'content-type': 'application/json'},
        ));
    final api = ApiClient(httpClient: mock, sesiones: SessionManager());

    await expectLater(
      api.get<dynamic>('/reservas', convertir: (j) => j),
      throwsA(isNotNull),
    );
    expect(avisos, 1);
  });
}
