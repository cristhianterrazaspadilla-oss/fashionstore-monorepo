// Limpieza al cerrar sesión: carrito, probador y 401 concurrente único.
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/carrito_service.dart';
import 'package:fashionstore_movil/core/session/sesion_expirada.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/ventas_pagos/carrito/carrito_store.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/probador/control_probador.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/probador/puente_decart.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'dart:convert';

import 'package:http/http.dart' as http;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('cerrar sesión limpia referencia del carrito', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
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
    final store = CarritoStore.paraPruebas(
      servicio: CarritoService(
          api: ApiClient(httpClient: mock, sesiones: SessionManager())),
      prefs: prefs,
    );
    await store.cargar();
    await store.limpiarReferenciaLocal();
    expect(prefs.getString('fs_carrito_meta_v1'), isNull);
  });

  test('cerrar probador libera todo y es idempotente', () async {
    final puente = FakePuenteDecart();
    final c = ControlProbador(puente: puente);
    await c.cerrar();
    await c.cerrar();
    expect(c.estado, isNotNull);
    expect(puente.llamadas.where((e) => e == 'release').length, 2);
  });

  test('401 concurrente cierra sesión una sola vez', () async {
    SharedPreferences.setMockInitialValues({});
    final manejador = ManejadorSesionExpirada();
    var limpiezas = 0;
    var avisos = 0;
    Future<void> limpiar() async => limpiezas++;
    void avisar() => avisos++;
    void irLogin() {}
    for (var i = 0; i < 5; i++) {
      manejador.manejar(
          limpiarSesion: limpiar, mostrarAviso: avisar, irALogin: irLogin);
    }
    await Future.delayed(const Duration(milliseconds: 100));
    expect(limpiezas, 1);
    expect(avisos, 1);
    manejador.restablecerParaPruebas();
  });
}
