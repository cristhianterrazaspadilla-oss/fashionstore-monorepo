import 'dart:convert';

import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/identidad_empresas/services/auth_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/historial_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/core/ui/async_view.dart';
import 'package:fashionstore_movil/features/ventas_pagos/historial/historial_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

ClientePerfilModel _usuario() => ClientePerfilModel(
      id: 'cliente-1',
      usuarioId: 'usuario-1',
      nombres: 'Ana',
      apellidos: 'Pérez',
      nombreCompleto: 'Ana Pérez',
      correoElectronico: 'ana@test.com',
      rol: 'CLIENTE',
      estado: 'ACTIVO',
      preferencias: const {},
      creadoEn: DateTime.utc(2026, 1, 1),
    );

Map<String, dynamic> _compraJson(String id, String numero) => {
      'id': id,
      'numero': numero,
      'sucursal_id': 'dest-1',
      'canal': 'PRESENCIAL',
      'estado': 'PAGADA',
      'subtotal': '200.00',
      'descuento': '0.00',
      'total': '200.00',
      'creada_en': '2026-09-10T10:00:00Z',
      'detalles': [
        {
          'id': 'd-1',
          'variante_id': 'v-1',
          'cantidad': 2,
          'precio_unitario': '100.00',
          'descuento': '0.00',
        }
      ],
    };

Future<AuthService> _authConSesion() async {
  final sesiones = SessionManager();
  await sesiones.guardar(token: 'tok-123', usuario: _usuario());
  return AuthService(
    api: ApiClient(
        httpClient: MockClient((_) async => http.Response('[]', 200)),
        sesiones: SessionManager()),
    sesiones: sesiones,
  );
}

HistorialScreen _pantalla(MockClient mock, AuthService auth) => HistorialScreen(
      servicioHistorial: HistorialService(
          api: ApiClient(httpClient: mock, sesiones: SessionManager())),
      servicioAuth: auth,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    await initializeDateFormatting('es');
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('Historial muestra carga inicial', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: HistorialScreen()));
    expect(find.text('Buscando tus compras…'), findsOneWidget);
  });

  testWidgets('Historial muestra compras simuladas', (tester) async {
    final auth = await _authConSesion();
    final mock = MockClient((req) async {
      if (req.method == 'GET' && req.url.path.contains('/compras')) {
        return http.Response(
          jsonEncode({
            'total': 1,
            'limit': 20,
            'offset': 0,
            'items': [_compraJson('c-1', 'V-0001')],
          }),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('No encontrado', 404);
    });
    await tester
        .pumpWidget(MaterialApp(home: Scaffold(body: _pantalla(mock, auth))));
    await tester.pumpAndSettle();

    expect(find.textContaining('V-0001'), findsOneWidget);
  });

  testWidgets('Historial vacío muestra mensaje comprensible', (tester) async {
    final auth = await _authConSesion();
    final mock = MockClient((_) async => http.Response(
          jsonEncode({'total': 0, 'limit': 20, 'offset': 0, 'items': []}),
          200,
          headers: {'content-type': 'application/json'},
        ));
    await tester
        .pumpWidget(MaterialApp(home: Scaffold(body: _pantalla(mock, auth))));
    await tester.pumpAndSettle();

    expect(find.text('Aún no tienes compras'), findsOneWidget);
  });

  testWidgets('VistaError ofrece reintento', (tester) async {
    var reintentos = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: VistaError(
            mensaje: 'Sin conexión',
            onReintentar: () => reintentos++,
          ),
        ),
      ),
    );
    expect(find.text('Reintentar'), findsOneWidget);
    await tester.tap(find.text('Reintentar'));
    expect(reintentos, 1);
  });
}
