// Widgets checkout: pasos, validaciones y cotización.
import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/carrito_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/checkout_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/entrega_service.dart';
import 'package:fashionstore_movil/features/organizacion/services/sucursal_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/ventas_pagos/checkout/checkout_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response ok(Object j, [int code = 200]) => http.Response(
      jsonEncode(j),
      code,
      headers: {'content-type': 'application/json'},
    );

Map<String, dynamic> sucursalJson(String id, String nombre) => {
      'id': id,
      'ciudad_id': 'ci1',
      'nombre': nombre,
      'direccion': 'Av. Central 123, Santa Cruz de la Sierra',
      'tarifa_base_delivery': 15,
      'incremento_anillo_delivery': 3,
      'anillo_minimo_delivery': 1,
      'anillo_maximo_delivery': 10,
      'delivery_activo': true,
      'activa': true,
    };

MockClient mockBase({bool sinCobertura = false}) => MockClient((req) async {
      final p = req.url.path;
      if (p.endsWith('/carritos/mio') && req.method == 'GET') {
        return ok({
          'id': 'car-1',
          'cliente_id': 'c1',
          'canal': 'MOVIL',
          'estado': 'ACTIVO',
          'lineas': [
            {
              'id': 'l1',
              'variante_id': 'v1',
              'cantidad': 1,
              'precio_unitario': 100,
              'descuento_unitario': 0,
              'subtotal': 100,
            },
          ],
          'subtotal': 100,
          'descuento_total': 0,
          'total': 100,
        });
      }
      if (p.endsWith('/sucursales')) {
        return ok([sucursalJson('s1', 'Sucursal Centro')]);
      }
      if (p.endsWith('/cobertura')) {
        return ok({
          'sucursales': sinCobertura
              ? []
              : [
                  {
                    'sucursal_id': 's1',
                    'sucursal_nombre': 'Sucursal Centro',
                    'cubre_todo': true,
                    'faltantes': [],
                  },
                ],
        });
      }
      if (p.endsWith('/cotizacion')) {
        return ok({
          'sucursal_id': 's1',
          'anillo_sucursal': 2,
          'anillo_destino': 3,
          'tarifa_base': 15,
          'incremento_anillo': 3,
          'costo_entrega': 18,
        });
      }
      return http.Response('no', 404);
    });

Widget app(MockClient mock) {
  final api = ApiClient(httpClient: mock, sesiones: SessionManager());
  return MaterialApp(
    home: CheckoutScreen(
      servicioCarrito: CarritoService(api: api),
      servicioCheckout: CheckoutService(api: api),
      servicioSucursal: SucursalService(api: api),
      servicioEntrega: EntregaService(api: api),
    ),
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('es');
  });
  testWidgets('muestra los pasos del checkout', (t) async {
    SharedPreferences.setMockInitialValues({});
    await t.pumpWidget(app(mockBase()));
    await t.pumpAndSettle();
    expect(find.textContaining('Revisa tus prendas'), findsOneWidget);
    expect(find.textContaining('Elige la sucursal'), findsOneWidget);
    expect(find.textContaining('Recojo o delivery'), findsOneWidget);
    expect(find.text('Confirmar y pagar con Stripe'), findsOneWidget);
  });

  testWidgets('impide continuar sin sucursal que cubra', (t) async {
    SharedPreferences.setMockInitialValues({});
    await t.pumpWidget(app(mockBase(sinCobertura: true)));
    await t.pumpAndSettle();
    await t.tap(find.text('Confirmar y pagar con Stripe'));
    await t.pumpAndSettle();
    expect(find.textContaining('Elige la sucursal'), findsWidgets);
  });

  testWidgets('delivery exige dirección', (t) async {
    SharedPreferences.setMockInitialValues({});
    await t.pumpWidget(app(mockBase()));
    await t.pumpAndSettle();
    await t.tap(find.text('Delivery en Santa Cruz'));
    await t.pumpAndSettle();
    expect(find.textContaining('Dirección de referencia'), findsOneWidget);
    await t.tap(find.text('Confirmar y pagar con Stripe'));
    await t.pumpAndSettle();
    expect(find.textContaining('dirección de referencia'), findsOneWidget);
  });
}
