// Widgets pago Stripe: pendiente, aprobado, rechazado, vencido y polling.
import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/entrega_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/pago_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pago/pago_screen.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pago/stripe_port.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response ok(Object j) => http.Response(
      jsonEncode(j),
      200,
      headers: {'content-type': 'application/json'},
    );

Map<String, dynamic> estadoJson(String venta, String pago) => {
      'venta_id': 'v1',
      'estado_venta': venta,
      'estado_pago': pago,
      'monto': 100,
    };

Widget app(MockClient mock, {FakePuertoStripe? puerto}) {
  final api = ApiClient(httpClient: mock, sesiones: SessionManager());
  return MaterialApp(
    home: PagoScreen(
      ventaId: 'v1',
      servicioPago: PagoService(api: api),
      servicioEntrega: EntregaService(api: api),
      puertoStripe: puerto ?? FakePuertoStripe(respuestas: []),
    ),
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('es');
  });
  testWidgets('pago pendiente invita a pagar sin otro método', (t) async {
    SharedPreferences.setMockInitialValues({});
    final mock =
        MockClient((_) async => ok(estadoJson('PENDIENTE_PAGO', 'PENDIENTE')));
    await t.pumpWidget(app(mock));
    await t.pumpAndSettle();
    expect(find.textContaining('Stripe (modo prueba)'), findsOneWidget);
    expect(find.text('Pagar ahora'), findsOneWidget);
    expect(find.textContaining('efectivo'), findsNothing);
    expect(find.textContaining('transferencia'), findsNothing);
  });

  testWidgets('pago aprobado ofrece ver el pedido', (t) async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((req) async {
      if (req.url.path.contains('mis-pedidos')) {
        return ok({'total': 0, 'limit': 50, 'offset': 0, 'items': []});
      }
      return ok(estadoJson('PAGADA', 'APROBADO'));
    });
    await t.pumpWidget(app(mock));
    await t.pumpAndSettle();
    expect(find.text('Ver mi pedido'), findsOneWidget);
    expect(find.textContaining('aprobado'), findsWidgets);
  });

  testWidgets('pago rechazado permite reintento', (t) async {
    SharedPreferences.setMockInitialValues({});
    final mock =
        MockClient((_) async => ok(estadoJson('PENDIENTE_PAGO', 'RECHAZADO')));
    await t.pumpWidget(app(mock));
    await t.pumpAndSettle();
    expect(find.textContaining('rechazado'), findsWidgets);
  });

  testWidgets('pago vencido impide nuevos intentos', (t) async {
    SharedPreferences.setMockInitialValues({});
    final mock =
        MockClient((_) async => ok(estadoJson('CANCELADA', 'ANULADO')));
    await t.pumpWidget(app(mock));
    await t.pumpAndSettle();
    expect(find.textContaining('venc'), findsWidgets);
    expect(find.text('Pagar ahora'), findsNothing);
    expect(find.text('Volver al carrito'), findsOneWidget);
  });

  testWidgets('polling se cancela al salir sin errores', (t) async {
    SharedPreferences.setMockInitialValues({});
    var consultas = 0;
    final mock = MockClient((_) async {
      consultas++;
      return ok(estadoJson('PENDIENTE_PAGO', 'PENDIENTE'));
    });
    await t.pumpWidget(app(mock));
    await t.pumpAndSettle();
    await t.pumpWidget(const MaterialApp(home: Scaffold()));
    await t.pumpAndSettle();
    expect(consultas, greaterThanOrEqualTo(1));
    expect(t.takeException(), isNull);
  });
}
