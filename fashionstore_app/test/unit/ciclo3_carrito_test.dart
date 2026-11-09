// Carrito separado de reserva: CRUD, idempotencia, doble toque,
// cobertura y limpieza de referencia local.
import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/carrito_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/ventas_pagos/carrito/carrito_store.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/bolsa_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> carritoJson({int cantidad = 1}) => {
      'id': 'car-1',
      'cliente_id': 'cli-1',
      'canal': 'MOVIL',
      'estado': 'ACTIVO',
      'creada_en': '2026-09-21T10:00:00Z',
      'actualizada_en': '2026-09-21T10:00:00Z',
      'lineas': cantidad == 0
          ? []
          : [
              {
                'id': 'l1',
                'variante_id': 'v1',
                'cantidad': cantidad,
                'precio_unitario': 100,
                'descuento_unitario': 0,
                'promocion_id': null,
                'subtotal': 100 * cantidad,
              },
            ],
      'subtotal': 100 * cantidad,
      'descuento_total': 0,
      'total': 100 * cantidad,
    };

ApiClient apiCon(MockClient mock) =>
    ApiClient(httpClient: mock, sesiones: SessionManager());

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('carrito vacío inicial y agregar línea', () async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((req) async {
      if (req.url.path.endsWith('/carritos/mio') && req.method == 'GET') {
        return httpResponse(carritoJson(cantidad: 0));
      }
      return httpResponse(carritoJson(cantidad: 2));
    });
    final srv = CarritoService(api: apiCon(mock));
    final vacio = await srv.obtenerOCrear();
    expect(vacio.estaVacio, isTrue);
    final lleno = await srv.agregar(varianteId: 'v1', cantidad: 2);
    expect(lleno.totalPrendas, 2);
  });

  test('modificar cantidad y eliminar línea', () async {
    SharedPreferences.setMockInitialValues({});
    var cantidad = 2;
    final canales = <String?>[];
    final mock = MockClient((req) async {
      canales.add(req.url.queryParameters['canal']);
      if (req.method == 'PATCH') cantidad = 5;
      if (req.method == 'DELETE') cantidad = 0;
      return httpResponse(carritoJson(cantidad: cantidad));
    });
    final srv = CarritoService(api: apiCon(mock));
    expect(
        (await srv.cambiarCantidad(varianteId: 'v1', cantidad: 5)).totalPrendas,
        5);
    expect((await srv.eliminarLinea(varianteId: 'v1')).estaVacio, isTrue);
    expect(canales, ['MOVIL', 'MOVIL']);
  });

  test('carrito y bolsa de reserva son independientes', () {
    final bolsa = BolsaStore.paraPruebas();
    final carrito = CarritoStore.paraPruebas();
    bolsa.agregar(
        varianteId: 'v-reserva', nombrePrenda: 'R', sku: 'R1', precio: 10);
    expect(bolsa.totalPrendas, 1);
    expect(carrito.totalPrendas, 0);
    expect(carrito.vacio, isTrue);
  });

  test('misma Idempotency-Key al reintentar agregar', () async {
    SharedPreferences.setMockInitialValues({});
    final claves = <String?>[];
    var llamadas = 0;
    final mock = MockClient((req) async {
      claves.add(req.headers['Idempotency-Key']);
      llamadas++;
      if (llamadas == 1) throw Exception('red caída');
      return httpResponse(carritoJson(cantidad: 1));
    });
    final srv = CarritoService(api: apiCon(mock));
    const clave = 'misma-clave-carrito';
    try {
      await srv.agregar(
          varianteId: 'v1', cantidad: 1, claveIdempotencia: clave);
      fail('debía fallar');
    } catch (_) {}
    final ok = await srv.agregar(
        varianteId: 'v1', cantidad: 1, claveIdempotencia: clave);
    expect(ok.totalPrendas, 1);
    expect(claves, ['misma-clave-carrito', 'misma-clave-carrito']);
  });

  test('protección de doble toque en el store', () async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async {
      await Future.delayed(const Duration(milliseconds: 50));
      return httpResponse(carritoJson(cantidad: 1));
    });
    final prefs = await SharedPreferences.getInstance();
    final store = CarritoStore.paraPruebas(
      servicio: CarritoService(api: apiCon(mock)),
      prefs: prefs,
    );
    final primero = store.agregar(varianteId: 'v1', cantidad: 1);
    final segundo = await store.agregar(varianteId: 'v1', cantidad: 1);
    expect(segundo, isFalse);
    expect(await primero, isTrue);
  });

  test('cobertura de sucursal y vaciado con clave', () async {
    SharedPreferences.setMockInitialValues({});
    String? claveVaciar;
    String? canalVaciar;
    final mock = MockClient((req) async {
      if (req.url.path.endsWith('/cobertura')) {
        return httpResponse({
          'sucursales': [
            {
              'sucursal_id': 's1',
              'sucursal_nombre': 'Centro',
              'cubre_todo': true,
              'faltantes': [],
            },
          ],
        });
      }
      claveVaciar = req.headers['Idempotency-Key'];
      canalVaciar = req.url.queryParameters['canal'];
      return httpResponse(carritoJson(cantidad: 0));
    });
    final srv = CarritoService(api: apiCon(mock));
    final cob = await srv.cobertura();
    expect(cob.queCubren.length, 1);
    await srv.vaciar();
    expect(claveVaciar, isNotNull);
    expect(canalVaciar, 'MOVIL');
  });

  test('limpiar referencia local borra metadata mínima', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final mock =
        MockClient((_) async => httpResponse(carritoJson(cantidad: 1)));
    final store = CarritoStore.paraPruebas(
      servicio: CarritoService(api: apiCon(mock)),
      prefs: prefs,
    );
    await store.cargar();
    expect(prefs.getString('fs_carrito_meta_v1'), isNotNull);
    await store.limpiarReferenciaLocal();
    expect(prefs.getString('fs_carrito_meta_v1'), isNull);
    expect(store.vacio, isTrue);
  });
}

httpResponse(Object json) => http.Response(
      jsonEncode(json),
      200,
      headers: {'content-type': 'application/json'},
    );
