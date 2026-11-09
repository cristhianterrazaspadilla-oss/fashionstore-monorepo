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
import 'package:http/testing.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> _sucursalJson(String id, String nombre) => {
      'id': id,
      'ciudad_id': 'ciudad-1',
      'ciudad_nombre': 'Santa Cruz',
      'nombre': nombre,
      'direccion': 'Av. Principal 123',
      'activa': true,
    };

Map<String, dynamic> _dispJson(
        String varianteId, String sucursalId, String nombre, int disponible) =>
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

/// Cliente simulado: sucursales + disponibilidad + creación de reserva.
/// [disponibleDestino] controla si la línea es local o requiere traslado.
/// [disponibleOrigen] es el stock del origen válido; el resto no tiene.
MockClient _clienteSimulado({
  required int disponibleDestino,
  int disponibleOrigen = 5,
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

void _agregarPrenda() {
  BolsaStore.instancia.limpiar();
  BolsaStore.instancia.agregar(
    varianteId: 'v-1',
    nombrePrenda: 'Camisa Clásica',
    sku: 'SKU-1',
    precio: 120,
    cantidad: 2,
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

  testWidgets('Bolsa vacía muestra mensaje comprensible', (tester) async {
    BolsaStore.instancia.limpiar();
    await tester.pumpWidget(
      MaterialApp(
          home: Scaffold(
              body: _pantalla(_clienteSimulado(
        disponibleDestino: 5,
        posts: [],
      )))),
    );
    await tester.pump();
    expect(find.text('Tu bolsa está vacía'), findsOneWidget);
    expect(find.textContaining('Explora el catálogo'), findsOneWidget);
  });

  testWidgets('Destino con stock usa reserva local y oculta traslado',
      (tester) async {
    _agregarPrenda();
    addTearDown(BolsaStore.instancia.limpiar);
    await tester.pumpWidget(
      MaterialApp(
          home: Scaffold(
              body: _pantalla(_clienteSimulado(
        disponibleDestino: 5,
        posts: [],
      )))),
    );
    await tester.pumpAndSettle();

    // Selector de destino visible con las sucursales simuladas.
    expect(find.byKey(const ValueKey('bolsa-destino')), findsOneWidget);
    expect(find.text('Sucursal de destino'), findsOneWidget);
    // Reserva local: mensaje comprensible y sin indicación de traslado.
    expect(find.textContaining('se apartará localmente'), findsOneWidget);
    expect(find.byKey(const ValueKey('traslado-requerido-v-1')), findsNothing);
    expect(find.byKey(const ValueKey('traslado-origen-v-1')), findsNothing);
  });

  testWidgets('Sin stock en destino informa y ofrece orígenes con stock',
      (tester) async {
    _agregarPrenda();
    addTearDown(BolsaStore.instancia.limpiar);
    await tester.pumpWidget(
      MaterialApp(
          home: Scaffold(
              body: _pantalla(_clienteSimulado(
        disponibleDestino: 0,
        posts: [],
      )))),
    );
    await tester.pumpAndSettle();

    // Traslado obligatorio: se activa solo, sin checkbox.
    expect(
        find.byKey(const ValueKey('traslado-requerido-v-1')), findsOneWidget);
    expect(find.text('Requiere traslado'), findsOneWidget);
    // El selector aparece automáticamente (no hay que marcar nada).
    expect(find.byKey(const ValueKey('traslado-origen-v-1')), findsOneWidget);

    // Solo el origen con stock suficiente aparece como opción.
    final campoOrigen = find.byKey(const ValueKey('traslado-origen-v-1'));
    await tester.ensureVisible(campoOrigen);
    await tester.pumpAndSettle();
    await tester.tap(campoOrigen);
    await tester.pumpAndSettle();
    expect(find.text('Sucursal Norte · Santa Cruz (5)'), findsOneWidget);
    expect(find.textContaining('Sucursal Sur'), findsNothing);
  });

  testWidgets('Confirmación bloqueada si el traslado no tiene origen',
      (tester) async {
    _agregarPrenda();
    addTearDown(BolsaStore.instancia.limpiar);
    final posts = <Map<String, dynamic>>[];
    await tester.pumpWidget(
      MaterialApp(
          home: Scaffold(
              body: _pantalla(_clienteSimulado(
        disponibleDestino: 0,
        posts: posts,
      )))),
    );
    await tester.pumpAndSettle();

    // Sin elegir origen (traslado ya activo por falta de stock local).
    expect(
        find.byKey(const ValueKey('traslado-requerido-v-1')), findsOneWidget);

    final confirmar = find.byKey(const ValueKey('bolsa-confirmar'));
    await tester.ensureVisible(confirmar);
    await tester.pumpAndSettle();
    await tester.tap(confirmar);
    await tester.pumpAndSettle();

    // Mensaje comprensible y ninguna llamada de red.
    expect(find.textContaining('origen para confirmar'), findsWidgets);
    expect(posts, isEmpty);
  });

  testWidgets('Selección de destino descarta origen incompatible',
      (tester) async {
    _agregarPrenda();
    addTearDown(BolsaStore.instancia.limpiar);
    // Origen válido preexistente en otra sucursal.
    BolsaStore.instancia.solicitarTraslado('v-1', true);
    BolsaStore.instancia.definirOrigen('v-1', 'origen-1', 'Sucursal Norte');
    expect(BolsaStore.instancia.items.single.origenId, 'origen-1');

    await tester.pumpWidget(
      MaterialApp(
          home: Scaffold(
              body: _pantalla(_clienteSimulado(
        disponibleDestino: 0,
        posts: [],
      )))),
    );
    await tester.pumpAndSettle();

    // Cambiar el destino al origen actual invalida ese origen.
    await tester.tap(find.byKey(const ValueKey('bolsa-destino')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sucursal Norte · Santa Cruz').last);
    await tester.pumpAndSettle();

    expect(BolsaStore.instancia.items.single.origenId, isNot('origen-1'));
  });

  testWidgets('Confirmar con origen envía sucursal_origen_id', (tester) async {
    _agregarPrenda();
    addTearDown(BolsaStore.instancia.limpiar);
    final posts = <Map<String, dynamic>>[];
    await tester.pumpWidget(
      MaterialApp(
          home: Scaffold(
              body: _pantalla(_clienteSimulado(
        disponibleDestino: 0,
        posts: posts,
      )))),
    );
    await tester.pumpAndSettle();

    // Traslado ya obligatorio: solo falta elegir el origen válido.
    final campoOrigen2 = find.byKey(const ValueKey('traslado-origen-v-1'));
    await tester.ensureVisible(campoOrigen2);
    await tester.pumpAndSettle();
    await tester.tap(campoOrigen2);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sucursal Norte · Santa Cruz (5)'));
    await tester.pumpAndSettle();

    final confirmar = find.byKey(const ValueKey('bolsa-confirmar'));
    await tester.ensureVisible(confirmar);
    await tester.pumpAndSettle();
    await tester.tap(confirmar);
    await tester.pumpAndSettle();

    expect(posts.length, 1);
    final lineas = posts.single['lineas'] as List;
    expect(lineas.single['sucursal_origen_id'], 'origen-1');
    expect(find.textContaining('FS-ABC123'), findsOneWidget);
  });
}
