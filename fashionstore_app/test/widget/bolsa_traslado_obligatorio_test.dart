import 'dart:async';
import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/catalogo/services/catalogo_service.dart';
import 'package:fashionstore_movil/features/reservas_traslados/services/reserva_service.dart';
import 'package:fashionstore_movil/features/organizacion/services/sucursal_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/bolsa_screen.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/bolsa_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Pruebas obligatorias de la corrección Ciclo 2:
/// 1. Sin stock local el traslado se activa obligatoriamente.
/// 2. Sin origen válido no se puede confirmar.
/// 3. Al disminuir y volver a cubrir, se limpia traslado y origen.
/// 4. Si el origen deja de ser válido al cambiar cantidad, se limpia.
/// 5. Sin traslado no se serializa origen.
/// 6. Flujo local normal sigue funcionando.
/// 7. Flujo con traslado válido envía el origen correcto.
/// 8. error de disponibilidad bloquea sin reintentos automáticos.
/// 9. reintento fallido controlado hace una sola consulta adicional.
/// 10. reintento exitoso con stock local permite confirmar sin origen.
/// 11. reintento exitoso con traslado exige origen y envía origen.
/// 12. carga pendiente deshabilita confirmar hasta completar.
/// 13. cambio de cantidad invalida y recarga con reconciliación.
/// 14. cambio de destino invalida y reconcilia al nuevo destino.
/// 15. respuesta fuera de orden no sobrescribe estado vigente.

Map<String, dynamic> _sucursalJson(String id, String nombre) => {
      'id': id,
      'ciudad_id': 'ciudad-1',
      'ciudad_nombre': 'Santa Cruz',
      'nombre': nombre,
      'direccion': 'Av. Principal 123',
      'activa': true,
    };

Map<String, dynamic> _dispJson(
  String varianteId,
  String sucursalId,
  String nombre,
  int disponible,
) =>
    {
      'inventario_id': 'inv-$sucursalId',
      'variante_id': varianteId,
      'sucursal_id': sucursalId,
      'sucursal_nombre': nombre,
      'ciudad_id': 'ciudad-1',
      'ciudad_nombre': 'Santa Cruz',
      'disponible': disponible,
      'reservado': 0,
      'comprometido_traslado': 0,
      'en_transito': 0,
    };

Map<String, dynamic> _reservaJson() => {
      'id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      'cliente_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      'sucursal_destino_id': 'dest-1',
      'codigo': 'FS-ABC123',
      'estado': 'PENDIENTE',
      'fecha_creacion': '2026-09-15T10:00:00Z',
      'vence_en': '2026-09-16T10:00:00Z',
      'detalles': [],
      'traslados': [],
    };

http.Response _okDisponibilidad({
  required int disponibleDestino,
  required int disponibleOrigen,
}) {
  return http.Response(
    jsonEncode([
      _dispJson('v-1', 'dest-1', 'Sucursal Centro', disponibleDestino),
      _dispJson('v-1', 'origen-1', 'Sucursal Norte', disponibleOrigen),
      _dispJson('v-1', 'origen-2', 'Sucursal Sur', 0),
    ]),
    200,
    headers: {'content-type': 'application/json'},
  );
}

MockClient _clienteSimulado({
  required int disponibleDestino,
  required int disponibleOrigen,
  required List<Map<String, dynamic>> posts,
}) {
  return MockClient((req) async {
    final path = req.url.path;
    if (req.method == 'GET' && path.endsWith('/sucursales')) {
      return http.Response(
        jsonEncode([
          _sucursalJson('dest-1', 'Sucursal Centro'),
          _sucursalJson('origen-1', 'Sucursal Norte'),
          _sucursalJson('origen-2', 'Sucursal Sur'),
        ]),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (req.method == 'GET' && path.contains('/variantes/')) {
      return http.Response(
        jsonEncode([
          _dispJson('v-1', 'dest-1', 'Sucursal Centro', disponibleDestino),
          _dispJson('v-1', 'origen-1', 'Sucursal Norte', disponibleOrigen),
          _dispJson('v-1', 'origen-2', 'Sucursal Sur', 0),
        ]),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (req.method == 'POST' && path.endsWith('/reservas')) {
      posts.add(jsonDecode(req.body) as Map<String, dynamic>);
      return http.Response(
        jsonEncode(_reservaJson()),
        201,
        headers: {'content-type': 'application/json'},
      );
    }
    return http.Response('No encontrado', 404);
  });
}

BolsaScreen _pantalla(MockClient mock) {
  final api = ApiClient(httpClient: mock, sesiones: SessionManager());
  return BolsaScreen(
    servicioSucursales: SucursalService(api: api),
    servicioReservas: ReservaService(api: api),
    servicioCatalogo: CatalogoService(api: api),
  );
}

void _agregarPrenda({int cantidad = 2}) {
  BolsaStore.instancia.limpiar();
  BolsaStore.instancia.agregar(
    varianteId: 'v-1',
    nombrePrenda: 'Camisa Clásica',
    sku: 'SKU-1',
    precio: 120,
    cantidad: cantidad,
  );
}

Future<void> _elegirOrigenNorte(WidgetTester tester) async {
  final campo = find.byKey(const ValueKey('traslado-origen-v-1'));
  await tester.ensureVisible(campo);
  await tester.pumpAndSettle();
  await tester.tap(campo);
  await tester.pumpAndSettle();
  await tester.tap(find.text('Sucursal Norte · Santa Cruz (2)').first);
  await tester.pumpAndSettle();
}

ElevatedButton _botonConfirmar(WidgetTester tester) {
  return tester.widget<ElevatedButton>(
    find.byKey(const ValueKey('bolsa-confirmar')),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  tearDown(() {
    BolsaStore.instancia.limpiar();
  });

  testWidgets('1. Sin stock local activa obligatoriamente el traslado', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: _pantalla(
            _clienteSimulado(
              disponibleDestino: 0,
              disponibleOrigen: 5,
              posts: [],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Sin tocar ningún checkbox (ya no existe): el traslado está activo.
    expect(
      find.byKey(const ValueKey('traslado-requerido-v-1')),
      findsOneWidget,
    );
    expect(find.text('Requiere traslado'), findsOneWidget);
    expect(find.byKey(const ValueKey('traslado-check-v-1')), findsNothing);
    final item = BolsaStore.instancia.items.single;
    expect(item.solicitaTraslado, isTrue);
    // Sin origen aún: bloquea la confirmación.
    expect(item.bloqueaConfirmacion, isTrue);
  });

  testWidgets('2. No se puede confirmar sin escoger un origen válido', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    final posts = <Map<String, dynamic>>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: _pantalla(
            _clienteSimulado(
              disponibleDestino: 0,
              disponibleOrigen: 5,
              posts: posts,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final confirmar = find.byKey(const ValueKey('bolsa-confirmar'));
    await tester.ensureVisible(confirmar);
    await tester.pumpAndSettle();
    // Botón deshabilitado por falta de origen válido.
    expect(_botonConfirmar(tester).onPressed, isNull);
    await tester.tap(confirmar);
    await tester.pumpAndSettle();

    expect(find.textContaining('requiere traslado'), findsWidgets);
    expect(find.textContaining('origen para confirmar'), findsWidgets);
    expect(posts, isEmpty);
  });

  testWidgets(
    '3. Al disminuir y volver a cubrir se desactiva traslado y se limpia origen',
    (tester) async {
      // Destino 1, cantidad 2 => requiere traslado. Al bajar a 1 => local.
      _agregarPrenda(cantidad: 2);
      addTearDown(BolsaStore.instancia.limpiar);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: _pantalla(
              _clienteSimulado(
                disponibleDestino: 1,
                disponibleOrigen: 5,
                posts: [],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey('traslado-requerido-v-1')),
        findsOneWidget,
      );
      // Elegir origen para partir de un estado con traslado + origen.
      final campoOrigen3 = find.byKey(
        const ValueKey('traslado-origen-v-1'),
      );
      await tester.ensureVisible(campoOrigen3);
      await tester.pumpAndSettle();
      await tester.tap(campoOrigen3);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Sucursal Norte · Santa Cruz (5)'));
      await tester.pumpAndSettle();
      expect(BolsaStore.instancia.items.single.origenId, 'origen-1');
      expect(BolsaStore.instancia.items.single.solicitaTraslado, isTrue);

      // Disminuir de 2 a 1 con el botón centralizado (recarga + reconcilia).
      final menos = find.byKey(const ValueKey('cantidad-menos-v-1'));
      await tester.ensureVisible(menos);
      await tester.pumpAndSettle();
      await tester.tap(menos);
      await tester.pumpAndSettle();

      final item = BolsaStore.instancia.items.single;
      expect(item.cantidad, 1);
      expect(item.solicitaTraslado, isFalse);
      expect(item.origenId, isNull);
      expect(item.origenNombre, isNull);
      // UI vuelve a local.
      expect(find.textContaining('se apartará localmente'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('traslado-requerido-v-1')),
        findsNothing,
      );
    },
  );

  testWidgets(
      '4. Si el origen deja de ser válido al cambiar cantidad se limpia', (
    tester,
  ) async {
    // Origen con 2, cantidad 2 => válido. Al subir a 3 => inválido.
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: _pantalla(
            _clienteSimulado(
              disponibleDestino: 0,
              disponibleOrigen: 2,
              posts: [],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await _elegirOrigenNorte(tester);
    expect(BolsaStore.instancia.items.single.origenId, 'origen-1');

    // Aumentar de 2 a 3: el origen (2) ya no cubre.
    final mas = find.byKey(const ValueKey('cantidad-mas-v-1'));
    await tester.ensureVisible(mas);
    await tester.pumpAndSettle();
    await tester.tap(mas);
    await tester.pumpAndSettle();

    final item = BolsaStore.instancia.items.single;
    expect(item.cantidad, 3);
    // Traslado sigue necesario, pero el origen obsoleto se limpió.
    expect(item.solicitaTraslado, isTrue);
    expect(item.origenId, isNull);
    expect(item.bloqueaConfirmacion, isTrue);
    expect(
      find.byKey(const ValueKey('traslado-requerido-v-1')),
      findsOneWidget,
    );
  });

  test('5. La confirmación no serializa origen cuando no hay traslado', () {
    final local = BolsaStore.paraPruebas();
    local.limpiar();
    local.agregar(
      varianteId: 'v-1',
      nombrePrenda: 'Camisa',
      sku: 'SKU-1',
      precio: 100,
      cantidad: 2,
    );
    final json = local.items.single.toJson();
    expect(json, {'variante_id': 'v-1', 'cantidad': 2});
    expect(json.containsKey('sucursal_origen_id'), isFalse);
  });

  testWidgets('6. Flujo normal con stock local sigue funcionando', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    final posts = <Map<String, dynamic>>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: _pantalla(
            _clienteSimulado(
              disponibleDestino: 5,
              disponibleOrigen: 5,
              posts: posts,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('se apartará localmente'), findsOneWidget);
    expect(BolsaStore.instancia.items.single.solicitaTraslado, isFalse);

    final confirmar = find.byKey(const ValueKey('bolsa-confirmar'));
    await tester.ensureVisible(confirmar);
    await tester.pumpAndSettle();
    expect(_botonConfirmar(tester).onPressed, isNotNull);
    await tester.tap(confirmar);
    await tester.pumpAndSettle();

    expect(posts.length, 1);
    final lineas = posts.single['lineas'] as List;
    expect((lineas.single as Map).containsKey('sucursal_origen_id'), isFalse);
    expect(find.textContaining('FS-ABC123'), findsOneWidget);
  });

  testWidgets('7. Flujo con traslado válido envía el origen correcto', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    final posts = <Map<String, dynamic>>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: _pantalla(
            _clienteSimulado(
              disponibleDestino: 0,
              disponibleOrigen: 5,
              posts: posts,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final campoOrigen7 = find.byKey(const ValueKey('traslado-origen-v-1'));
    await tester.ensureVisible(campoOrigen7);
    await tester.pumpAndSettle();
    await tester.tap(campoOrigen7);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sucursal Norte · Santa Cruz (5)'));
    await tester.pumpAndSettle();

    final confirmar = find.byKey(const ValueKey('bolsa-confirmar'));
    await tester.ensureVisible(confirmar);
    await tester.pumpAndSettle();
    expect(_botonConfirmar(tester).onPressed, isNotNull);
    await tester.tap(confirmar);
    await tester.pumpAndSettle();

    expect(posts.length, 1);
    final lineas = posts.single['lineas'] as List;
    expect((lineas.single as Map)['sucursal_origen_id'], 'origen-1');
    expect(find.textContaining('FS-ABC123'), findsOneWidget);
  });

  testWidgets(
    '8. error de disponibilidad bloquea confirmar sin reintentos automáticos',
    (tester) async {
      _agregarPrenda(cantidad: 2);
      addTearDown(BolsaStore.instancia.limpiar);
      var gets = 0;
      final posts = <Map<String, dynamic>>[];
      final mock = MockClient((req) async {
        final path = req.url.path;
        if (req.method == 'GET' && path.endsWith('/sucursales')) {
          return http.Response(
            jsonEncode([
              _sucursalJson('dest-1', 'Sucursal Centro'),
              _sucursalJson('origen-1', 'Sucursal Norte'),
              _sucursalJson('origen-2', 'Sucursal Sur'),
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (req.method == 'GET' && path.contains('/variantes/')) {
          gets++;
          return http.Response('Error interno', 500);
        }
        if (req.method == 'POST' && path.endsWith('/reservas')) {
          posts.add(jsonDecode(req.body) as Map<String, dynamic>);
          return http.Response(
            jsonEncode(_reservaJson()),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('No encontrado', 404);
      });
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: _pantalla(mock))),
      );
      await tester.pumpAndSettle();

      expect(gets, 1);
      expect(
        find.text(
          'No pudimos verificar la disponibilidad. Reintenta antes de confirmar.',
        ),
        findsOneWidget,
      );
      expect(
        find.widgetWithText(TextButton, 'Reintentar'),
        findsOneWidget,
      );
      expect(_botonConfirmar(tester).onPressed, isNull);
      expect(find.text('Revisa la disponibilidad'), findsOneWidget);
      expect(posts, isEmpty);
      // Sin POST previo no se muestra reintento de misma solicitud.
      expect(
        find.text('Reintentar con la misma solicitud'),
        findsNothing,
      );

      // Varios pumps no deben generar nuevas consultas automáticas.
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));
      expect(gets, 1);
      expect(posts, isEmpty);
    },
  );

  testWidgets(
      '9. reintento fallido controlado hace una sola consulta adicional', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    var gets = 0;
    final posts = <Map<String, dynamic>>[];
    final mock = MockClient((req) async {
      final path = req.url.path;
      if (req.method == 'GET' && path.endsWith('/sucursales')) {
        return http.Response(
          jsonEncode([
            _sucursalJson('dest-1', 'Sucursal Centro'),
            _sucursalJson('origen-1', 'Sucursal Norte'),
            _sucursalJson('origen-2', 'Sucursal Sur'),
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (req.method == 'GET' && path.contains('/variantes/')) {
        gets++;
        return http.Response('Error interno', 500);
      }
      if (req.method == 'POST' && path.endsWith('/reservas')) {
        posts.add(jsonDecode(req.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode(_reservaJson()),
          201,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('No encontrado', 404);
    });
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: _pantalla(mock))),
    );
    await tester.pumpAndSettle();
    expect(gets, 1);

    await tester.tap(find.widgetWithText(TextButton, 'Reintentar'));
    await tester.pumpAndSettle();
    expect(gets, 2);
    expect(
      find.text(
        'No pudimos verificar la disponibilidad. Reintenta antes de confirmar.',
      ),
      findsOneWidget,
    );
    expect(_botonConfirmar(tester).onPressed, isNull);

    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 100));
    expect(gets, 2);
    expect(posts, isEmpty);
  });

  testWidgets(
      '10. reintento exitoso con stock local permite confirmar sin origen', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    var gets = 0;
    final posts = <Map<String, dynamic>>[];
    final mock = MockClient((req) async {
      final path = req.url.path;
      if (req.method == 'GET' && path.endsWith('/sucursales')) {
        return http.Response(
          jsonEncode([
            _sucursalJson('dest-1', 'Sucursal Centro'),
            _sucursalJson('origen-1', 'Sucursal Norte'),
            _sucursalJson('origen-2', 'Sucursal Sur'),
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (req.method == 'GET' && path.contains('/variantes/')) {
        gets++;
        if (gets == 1) return http.Response('Error interno', 500);
        return _okDisponibilidad(
          disponibleDestino: 5,
          disponibleOrigen: 5,
        );
      }
      if (req.method == 'POST' && path.endsWith('/reservas')) {
        posts.add(jsonDecode(req.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode(_reservaJson()),
          201,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('No encontrado', 404);
    });
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: _pantalla(mock))),
    );
    await tester.pumpAndSettle();
    expect(gets, 1);
    expect(_botonConfirmar(tester).onPressed, isNull);

    await tester.tap(find.widgetWithText(TextButton, 'Reintentar'));
    await tester.pumpAndSettle();
    expect(gets, 2);
    expect(find.textContaining('se apartará localmente'), findsOneWidget);
    expect(_botonConfirmar(tester).onPressed, isNotNull);

    final confirmar = find.byKey(const ValueKey('bolsa-confirmar'));
    await tester.ensureVisible(confirmar);
    await tester.pumpAndSettle();
    await tester.tap(confirmar);
    await tester.pumpAndSettle();

    expect(posts.length, 1);
    final lineas = posts.single['lineas'] as List;
    expect((lineas.single as Map).containsKey('sucursal_origen_id'), isFalse);
    expect(find.textContaining('FS-ABC123'), findsOneWidget);
  });

  testWidgets('11. reintento exitoso con traslado exige origen y envía origen',
      (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    var gets = 0;
    final posts = <Map<String, dynamic>>[];
    final mock = MockClient((req) async {
      final path = req.url.path;
      if (req.method == 'GET' && path.endsWith('/sucursales')) {
        return http.Response(
          jsonEncode([
            _sucursalJson('dest-1', 'Sucursal Centro'),
            _sucursalJson('origen-1', 'Sucursal Norte'),
            _sucursalJson('origen-2', 'Sucursal Sur'),
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (req.method == 'GET' && path.contains('/variantes/')) {
        gets++;
        if (gets == 1) return http.Response('Error interno', 500);
        return _okDisponibilidad(
          disponibleDestino: 0,
          disponibleOrigen: 5,
        );
      }
      if (req.method == 'POST' && path.endsWith('/reservas')) {
        posts.add(jsonDecode(req.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode(_reservaJson()),
          201,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('No encontrado', 404);
    });
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: _pantalla(mock))),
    );
    await tester.pumpAndSettle();
    expect(_botonConfirmar(tester).onPressed, isNull);

    await tester.tap(find.widgetWithText(TextButton, 'Reintentar'));
    await tester.pumpAndSettle();
    expect(gets, 2);
    expect(
      find.byKey(const ValueKey('traslado-requerido-v-1')),
      findsOneWidget,
    );
    // Sigue bloqueado hasta elegir origen.
    expect(_botonConfirmar(tester).onPressed, isNull);

    final campo = find.byKey(const ValueKey('traslado-origen-v-1'));
    await tester.ensureVisible(campo);
    await tester.pumpAndSettle();
    await tester.tap(campo);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sucursal Norte · Santa Cruz (5)'));
    await tester.pumpAndSettle();

    expect(_botonConfirmar(tester).onPressed, isNotNull);
    final confirmar = find.byKey(const ValueKey('bolsa-confirmar'));
    await tester.ensureVisible(confirmar);
    await tester.pumpAndSettle();
    await tester.tap(confirmar);
    await tester.pumpAndSettle();

    expect(posts.length, 1);
    final lineas = posts.single['lineas'] as List;
    expect((lineas.single as Map)['sucursal_origen_id'], 'origen-1');
  });

  testWidgets('12. carga pendiente deshabilita confirmar hasta completar', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    var gets = 0;
    final posts = <Map<String, dynamic>>[];
    final pendiente = Completer<http.Response>();
    final mock = MockClient((req) async {
      final path = req.url.path;
      if (req.method == 'GET' && path.endsWith('/sucursales')) {
        return http.Response(
          jsonEncode([
            _sucursalJson('dest-1', 'Sucursal Centro'),
            _sucursalJson('origen-1', 'Sucursal Norte'),
            _sucursalJson('origen-2', 'Sucursal Sur'),
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (req.method == 'GET' && path.contains('/variantes/')) {
        gets++;
        return pendiente.future;
      }
      if (req.method == 'POST' && path.endsWith('/reservas')) {
        posts.add(jsonDecode(req.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode(_reservaJson()),
          201,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('No encontrado', 404);
    });
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: _pantalla(mock))),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(gets, 1);
    expect(find.text('Verificando disponibilidad…'), findsWidgets);
    expect(_botonConfirmar(tester).onPressed, isNull);
    expect(posts, isEmpty);

    pendiente.complete(
      _okDisponibilidad(disponibleDestino: 5, disponibleOrigen: 5),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('se apartará localmente'), findsOneWidget);
    expect(_botonConfirmar(tester).onPressed, isNotNull);
    expect(posts, isEmpty);
  });

  testWidgets('13. cambio de cantidad invalida y recarga con reconciliación', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    var llamadas = 0;
    final posts = <Map<String, dynamic>>[];
    Completer<http.Response>? segunda;
    final mock = MockClient((req) async {
      final path = req.url.path;
      if (req.method == 'GET' && path.endsWith('/sucursales')) {
        return http.Response(
          jsonEncode([
            _sucursalJson('dest-1', 'Sucursal Centro'),
            _sucursalJson('origen-1', 'Sucursal Norte'),
            _sucursalJson('origen-2', 'Sucursal Sur'),
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (req.method == 'GET' && path.contains('/variantes/')) {
        llamadas++;
        if (llamadas == 1) {
          return _okDisponibilidad(
            disponibleDestino: 2,
            disponibleOrigen: 5,
          );
        }
        return segunda!.future;
      }
      if (req.method == 'POST' && path.endsWith('/reservas')) {
        posts.add(jsonDecode(req.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode(_reservaJson()),
          201,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('No encontrado', 404);
    });
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: _pantalla(mock))),
    );
    await tester.pumpAndSettle();
    expect(llamadas, 1);
    // Cantidad 2 con destino 2: local.
    expect(find.textContaining('se apartará localmente'), findsOneWidget);
    expect(_botonConfirmar(tester).onPressed, isNotNull);

    segunda = Completer<http.Response>();
    final mas = find.byKey(const ValueKey('cantidad-mas-v-1'));
    await tester.ensureVisible(mas);
    await tester.pumpAndSettle();
    await tester.tap(mas);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // Nueva consulta pendiente: botón deshabilitado de inmediato.
    expect(llamadas, 2);
    expect(BolsaStore.instancia.items.single.cantidad, 3);
    expect(find.text('Verificando disponibilidad…'), findsWidgets);
    expect(_botonConfirmar(tester).onPressed, isNull);
    expect(posts, isEmpty);

    segunda.complete(
      _okDisponibilidad(disponibleDestino: 2, disponibleOrigen: 5),
    );
    await tester.pumpAndSettle();

    // Destino 2 ya no cubre 3: requiere traslado y limpia origen.
    expect(
      find.byKey(const ValueKey('traslado-requerido-v-1')),
      findsOneWidget,
    );
    expect(_botonConfirmar(tester).onPressed, isNull);
    expect(posts, isEmpty);
  });

  testWidgets('14. cambio de destino invalida y reconcilia al nuevo destino', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    var llamadas = 0;
    final posts = <Map<String, dynamic>>[];
    Completer<http.Response>? siguientes;
    http.Response respuestaBase() => _okDisponibilidad(
          disponibleDestino: 5,
          disponibleOrigen: 0,
        );
    final mock = MockClient((req) async {
      final path = req.url.path;
      if (req.method == 'GET' && path.endsWith('/sucursales')) {
        return http.Response(
          jsonEncode([
            _sucursalJson('dest-1', 'Sucursal Centro'),
            _sucursalJson('origen-1', 'Sucursal Norte'),
            _sucursalJson('origen-2', 'Sucursal Sur'),
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (req.method == 'GET' && path.contains('/variantes/')) {
        llamadas++;
        if (llamadas == 1) return respuestaBase();
        return siguientes!.future;
      }
      if (req.method == 'POST' && path.endsWith('/reservas')) {
        posts.add(jsonDecode(req.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode(_reservaJson()),
          201,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('No encontrado', 404);
    });
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: _pantalla(mock))),
    );
    await tester.pumpAndSettle();
    expect(llamadas, 1);
    expect(find.textContaining('se apartará localmente'), findsOneWidget);
    expect(_botonConfirmar(tester).onPressed, isNotNull);

    siguientes = Completer<http.Response>();
    await tester.tap(find.byKey(const ValueKey('bolsa-destino')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sucursal Norte · Santa Cruz').last);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(llamadas, 2);
    expect(find.text('Verificando disponibilidad…'), findsWidgets);
    expect(_botonConfirmar(tester).onPressed, isNull);

    siguientes.complete(respuestaBase());
    await tester.pumpAndSettle();

    // Nuevo destino origen-1 tiene 0: requiere traslado desde dest-1.
    expect(
      find.byKey(const ValueKey('traslado-requerido-v-1')),
      findsOneWidget,
    );
    final campo = find.byKey(const ValueKey('traslado-origen-v-1'));
    await tester.ensureVisible(campo);
    await tester.pumpAndSettle();
    await tester.tap(campo);
    await tester.pumpAndSettle();
    // Origen válido para el nuevo destino: Centro con 5.
    expect(
      find.text('Sucursal Centro · Santa Cruz (5)'),
      findsOneWidget,
    );
    expect(posts, isEmpty);
  });

  testWidgets('15. respuesta fuera de orden no sobrescribe estado vigente', (
    tester,
  ) async {
    _agregarPrenda(cantidad: 2);
    addTearDown(BolsaStore.instancia.limpiar);
    var llamadas = 0;
    final posts = <Map<String, dynamic>>[];
    final primera = Completer<http.Response>();
    final segunda = Completer<http.Response>();
    final mock = MockClient((req) async {
      final path = req.url.path;
      if (req.method == 'GET' && path.endsWith('/sucursales')) {
        return http.Response(
          jsonEncode([
            _sucursalJson('dest-1', 'Sucursal Centro'),
            _sucursalJson('origen-1', 'Sucursal Norte'),
            _sucursalJson('origen-2', 'Sucursal Sur'),
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (req.method == 'GET' && path.contains('/variantes/')) {
        llamadas++;
        if (llamadas == 1) return primera.future;
        return segunda.future;
      }
      if (req.method == 'POST' && path.endsWith('/reservas')) {
        posts.add(jsonDecode(req.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode(_reservaJson()),
          201,
          headers: {'content-type': 'application/json'},
        );
      }
      return http.Response('No encontrado', 404);
    });
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: _pantalla(mock))),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(llamadas, 1);
    expect(_botonConfirmar(tester).onPressed, isNull);

    // Segunda consulta por cambio de cantidad antes de completar la primera.
    final mas = find.byKey(const ValueKey('cantidad-mas-v-1'));
    await tester.ensureVisible(mas);
    await tester.pump();
    await tester.tap(mas);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(llamadas, 2);
    expect(BolsaStore.instancia.items.single.cantidad, 3);

    // Completar primero la más reciente (destino 0: requiere traslado).
    segunda.complete(
      _okDisponibilidad(disponibleDestino: 0, disponibleOrigen: 5),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(
      find.byKey(const ValueKey('traslado-requerido-v-1')),
      findsOneWidget,
    );

    // Completar después la antigua (destino 5: local). Debe ignorarse.
    primera.complete(
      _okDisponibilidad(disponibleDestino: 5, disponibleOrigen: 5),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(milliseconds: 50));

    expect(
      find.byKey(const ValueKey('traslado-requerido-v-1')),
      findsOneWidget,
    );
    expect(find.textContaining('se apartará localmente'), findsNothing);
    expect(posts, isEmpty);
  });
}
