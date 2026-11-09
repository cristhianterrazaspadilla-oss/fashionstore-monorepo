// Navegación principal Ciclo 3: 5 destinos, badges independientes y estado.
import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/carrito_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/ventas_pagos/carrito/carrito_store.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/home/home_screen.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/bolsa_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

Widget app() => MaterialApp(
      home: HomeScreen(onSesionCerrada: () {}),
    );

void main() {
  setUpAll(() async {
    await initializeDateFormatting('es');
  });
  testWidgets('cinco destinos sin bolsa como pestaña', (t) async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async => http.Response(
          jsonEncode({
            'id': 'car-1',
            'cliente_id': 'c1',
            'canal': 'MOVIL',
            'estado': 'ACTIVO',
            'lineas': [],
            'subtotal': 0,
            'descuento_total': 0,
            'total': 0,
          }),
          200,
          headers: {'content-type': 'application/json'},
        ));
    CarritoStore.instancia.configurarParaPruebas(
      servicio: CarritoService(
          api: ApiClient(httpClient: mock, sesiones: SessionManager())),
    );
    await t.pumpWidget(app());
    await t.pump(const Duration(milliseconds: 100));
    expect(find.text('Catálogo'), findsWidgets);
    expect(find.text('Carrito'), findsOneWidget);
    expect(find.text('Pedidos'), findsOneWidget);
    expect(find.text('Reservas'), findsWidgets);
    expect(find.text('Cuenta'), findsOneWidget);
    // La bolsa ya no es pestaña principal.
    expect(find.text('Bolsa'), findsNothing);

    // Alternar pestañas conserva estado y cambia títulos.
    await t.tap(find.text('Carrito'));
    await t.pumpAndSettle();
    expect(find.text('Carrito de compra'), findsOneWidget);
    await t.tap(find.text('Pedidos'));
    await t.pumpAndSettle();
    expect(find.text('Mis pedidos'), findsOneWidget);
    await t.tap(find.text('Reservas'));
    await t.pumpAndSettle();
    expect(find.text('Mis reservas'), findsOneWidget);
  });

  testWidgets('indicadores de carrito y reservas son independientes',
      (t) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final mock = MockClient((_) async => http.Response(
          jsonEncode({
            'id': 'car-1',
            'cliente_id': 'c1',
            'canal': 'MOVIL',
            'estado': 'ACTIVO',
            'lineas': [
              {
                'id': 'l1',
                'variante_id': 'v1',
                'cantidad': 3,
                'precio_unitario': 50,
                'descuento_unitario': 0,
                'subtotal': 150,
              },
            ],
            'subtotal': 150,
            'descuento_total': 0,
            'total': 150,
          }),
          200,
          headers: {'content-type': 'application/json'},
        ));
    final store = CarritoStore.paraPruebas(
      servicio: CarritoService(
          api: ApiClient(httpClient: mock, sesiones: SessionManager())),
      prefs: prefs,
    );
    await store.cargar();
    expect(store.totalPrendas, 3);
    final bolsa = BolsaStore.paraPruebas();
    bolsa.agregar(varianteId: 'v9', nombrePrenda: 'R', sku: 'R9', precio: 10);
    expect(bolsa.totalPrendas, 1);
    // Stores distintos: contadores no se mezclan.
    expect(store.totalPrendas, isNot(equals(bolsa.totalPrendas)));
  });
}
