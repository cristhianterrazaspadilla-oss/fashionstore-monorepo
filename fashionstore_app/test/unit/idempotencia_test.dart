import 'dart:convert';

import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/reservas_traslados/services/reserva_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Idempotency-Key estable al reintentar la misma bolsa', () async {
    SharedPreferences.setMockInitialValues({});
    final enviadas = <String?>[];
    final mock = MockClient((req) async {
      enviadas.add(req.headers['Idempotency-Key']);
      // Primera vez falla por red, segunda responde reserva creada.
      if (enviadas.length == 1) {
        throw http.ClientException('red caída');
      }
      return http.Response(
        jsonEncode({
          'id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
          'cliente_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
          'sucursal_destino_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
          'codigo': 'FS-ABC123',
          'estado': 'PENDIENTE',
          'fecha_creacion': '2026-09-15T10:00:00Z',
          'vence_en': '2026-09-16T10:00:00Z',
          'detalles': [],
          'traslados': [],
        }),
        201,
        headers: {'content-type': 'application/json'},
      );
    });

    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final srv = ReservaService(api: api);
    const clave = 'clave-estable-123';

    // Primer intento falla.
    try {
      await srv.crear(
        sucursalDestinoId: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
        items: [],
        claveIdempotencia: clave,
      );
      fail('debía fallar el primer intento');
    } catch (_) {}

    // Reintento con la MISMA clave.
    final r = await srv.crear(
      sucursalDestinoId: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
      items: [],
      claveIdempotencia: clave,
    );
    expect(r.codigo, 'FS-ABC123');
    expect(enviadas, ['clave-estable-123', 'clave-estable-123']);
  });

  test('ApiClient envía Bearer automáticamente cuando hay sesión', () async {
    SharedPreferences.setMockInitialValues({});
    final mgr = SessionManager();
    await mgr.guardar(
      token: 'mi-token',
      usuario: ClientePerfilModel(
        id: 'c1',
        usuarioId: 'u1',
        nombres: 'A',
        apellidos: 'B',
        nombreCompleto: 'A B',
        correoElectronico: 'a@b.com',
        rol: 'CLIENTE',
        estado: 'ACTIVO',
        preferencias: const {},
        creadoEn: DateTime.utc(2026, 1, 1),
      ),
      ahora: DateTime.now(),
    );
    String? auth;
    final mock = MockClient((req) async {
      auth = req.headers['Authorization'];
      return http.Response('[]', 200,
          headers: {'content-type': 'application/json'});
    });
    final api = ApiClient(httpClient: mock, sesiones: mgr);
    await api.get<List>('/productos', convertir: (j) => (j as List?) ?? []);
    expect(auth, 'Bearer mi-token');
  });

  test('nuevaClaveIdempotencia genera UUID distintos', () {
    final a = ReservaService.nuevaClaveIdempotencia();
    final b = ReservaService.nuevaClaveIdempotencia();
    expect(a, isNot(equals(b)));
    expect(a.length, greaterThanOrEqualTo(36));
  });
}
