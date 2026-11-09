import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/reservas_traslados/services/reserva_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/core/ui/estado_chip.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/reservas_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> _reservaJson(String id, String codigo, String estado) => {
      'id': id,
      'cliente_id': 'cliente-1',
      'sucursal_destino_id': 'dest-1',
      'codigo': codigo,
      'estado': estado,
      'fecha_creacion': '2026-09-15T10:00:00Z',
      'vence_en': '2026-09-16T10:00:00Z',
      'detalles': [],
      'traslados': [],
    };

MockClient _clienteSimulado(List<Map<String, dynamic>> reservas) {
  return MockClient((req) async {
    if (req.method == 'GET' && req.url.path.endsWith('/reservas')) {
      return http.Response(
        jsonEncode({
          'total': reservas.length,
          'limit': 20,
          'offset': 0,
          'items': reservas,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    return http.Response('No encontrado', 404);
  });
}

ReservasScreen _pantalla(MockClient mock) => ReservasScreen(
      servicio: ReservaService(
          api: ApiClient(httpClient: mock, sesiones: SessionManager())),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    await initializeDateFormatting('es');
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('Reservas muestra carga inicial', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ReservasScreen()));
    expect(find.text('Buscando tus reservas…'), findsOneWidget);
  });

  testWidgets('Reservas muestra respuesta simulada', (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: _pantalla(_clienteSimulado([
      _reservaJson('r-1', 'FS-ABC123', 'PENDIENTE'),
      _reservaJson('r-2', 'FS-XYZ789', 'PREPARADA'),
    ])))));
    await tester.pumpAndSettle();

    expect(find.textContaining('FS-ABC123'), findsOneWidget);
    expect(find.textContaining('FS-XYZ789'), findsOneWidget);
  });

  testWidgets('Reservas vacías muestran mensaje comprensible', (tester) async {
    await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: _pantalla(_clienteSimulado([])))));
    await tester.pumpAndSettle();

    expect(find.text('Aún no tienes reservas'), findsOneWidget);
  });

  testWidgets('Chip de estado es legible y con contraste', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              EstadoChip.reserva('Lista para tu visita', 'PREPARADA'),
              EstadoChip.reserva('Esperando traslado', 'PENDIENTE_TRASLADO'),
            ],
          ),
        ),
      ),
    );
    expect(find.text('Lista para tu visita'), findsOneWidget);
    expect(find.text('Esperando traslado'), findsOneWidget);
  });
}
