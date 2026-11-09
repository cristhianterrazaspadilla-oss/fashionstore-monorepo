// Widgets carrito: vacío, carga, error, líneas y totales del backend.
import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/carrito_service.dart';
import 'package:fashionstore_movil/features/catalogo/services/catalogo_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/ventas_pagos/carrito/carrito_screen.dart';
import 'package:fashionstore_movil/features/ventas_pagos/carrito/carrito_store.dart';
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

Map<String, dynamic> carritoJson(int n) => {
      'id': 'car-1',
      'cliente_id': 'c1',
      'canal': 'MOVIL',
      'estado': 'ACTIVO',
      'lineas': n == 0
          ? []
          : [
              {
                'id': 'l1',
                'variante_id': 'v1',
                'cantidad': n,
                'precio_unitario': 100,
                'descuento_unitario': 5,
                'promocion_id': 'promo-1',
                'subtotal': 95 * n,
              },
            ],
      'subtotal': 100 * n,
      'descuento_total': 5 * n,
      'total': 95 * n,
    };

MockClient mockCarrito(int n, {bool error = false}) => MockClient((req) async {
      final p = req.url.path;
      if (error) return http.Response('falla', 500);
      if (p.contains('/variantes/v1')) {
        return ok({
          'id': 'v1',
          'producto_id': 'p1',
          'talla_id': 't1',
          'color_id': 'c1',
          'sku': 'SKU-001-M-NEGRO',
          'precio': 100,
          'activa': true,
        });
      }
      if (p.contains('/productos/p1')) {
        return ok({
          'id': 'p1',
          'nombre': 'Camisa Urbana de Algodón Premium Edición Limitada',
          'precio_base': 100,
          'activo': true,
          'imagenes': [],
          'temporada_ids': [],
          'coleccion_ids': [],
        });
      }
      if (p.contains('filtros-opciones')) {
        return ok({
          'categorias': [],
          'tallas': [
            {'id': 't1', 'nombre': 'M', 'orden': 1},
          ],
          'colores': [
            {'id': 'c1', 'nombre': 'Negro', 'codigo_hex': '#000000'},
          ],
          'temporadas': [],
          'colecciones': [],
          'generos': [],
          'marcas': [],
        });
      }
      return ok(carritoJson(n));
    });

Widget app(CarritoStore store, MockClient mock) {
  final api = ApiClient(httpClient: mock, sesiones: SessionManager());
  return MaterialApp(
    home: Scaffold(
      body: CarritoScreen(
        store: store,
        servicio: CarritoService(api: api),
        servicioCatalogo: CatalogoService(api: api),
      ),
    ),
  );
}

void main() {
  setUpAll(() async {
    await initializeDateFormatting('es');
  });
  testWidgets('carrito vacío con siguiente acción', (t) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final mock = mockCarrito(0);
    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final store = CarritoStore.paraPruebas(
        servicio: CarritoService(api: api), prefs: prefs);
    await t.pumpWidget(app(store, mock));
    await t.pumpAndSettle();
    expect(find.text('Tu carrito está vacío'), findsOneWidget);
  });

  testWidgets('muestra líneas, descuento y total del backend', (t) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final mock = mockCarrito(2);
    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final store = CarritoStore.paraPruebas(
        servicio: CarritoService(api: api), prefs: prefs);
    await t.pumpWidget(app(store, mock));
    await t.pumpAndSettle();
    await t.pump(const Duration(milliseconds: 200));
    expect(find.textContaining('Total a pagar'), findsOneWidget);
    expect(find.textContaining('promociones aplicadas'), findsOneWidget);
    expect(find.text('Continuar con la compra'), findsOneWidget);
  });

  testWidgets('error de red con reintento', (t) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final mock = mockCarrito(0, error: true);
    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final store = CarritoStore.paraPruebas(
        servicio: CarritoService(api: api), prefs: prefs);
    await t.pumpWidget(app(store, mock));
    await t.pumpAndSettle();
    expect(find.text('Reintentar'), findsOneWidget);
  });

  testWidgets('nombres largos no provocan overflow', (t) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final mock = mockCarrito(1);
    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final store = CarritoStore.paraPruebas(
        servicio: CarritoService(api: api), prefs: prefs);
    await t.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(size: Size(320, 600)),
        child: app(store, mock),
      ),
    );
    await t.pumpAndSettle();
    expect(t.takeException(), isNull);
  });

  testWidgets(
      'botón Probar prendas seleccionadas visible y no altera el carrito',
      (t) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final mock = mockCarrito(2);
    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final store = CarritoStore.paraPruebas(
        servicio: CarritoService(api: api), prefs: prefs);
    await t.pumpWidget(app(store, mock));
    await t.pumpAndSettle();

    expect(find.text('Probar prendas seleccionadas'), findsOneWidget);

    // Carrito conserva exactamente sus 2 unidades y total
    expect(store.carrito.totalPrendas, 2);
    expect(store.carrito.lineas.length, 1);
  });
}
