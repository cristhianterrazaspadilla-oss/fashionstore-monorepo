// Widgets probador: incompatible, indisponibilidad fuera de Android,
// aviso permanente y canales exactos.
import 'dart:convert';
import 'dart:io';

import 'package:fashionstore_movil/features/experiencia_cliente/models/probador_model.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/carrito_service.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/services/ia_service.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/services/probador_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/ventas_pagos/carrito/carrito_store.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/probador/probador_screen.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/probador/puente_decart.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/bolsa_store.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response ok(Object j, [int code = 200]) => http.Response(
      jsonEncode(j),
      code,
      headers: {'content-type': 'application/json'},
    );

Map<String, dynamic> recursoJson(bool compatible) => {
      'variante_id': 'v1',
      'compatible': compatible,
      'imagen_prenda_url': 'https://x/prenda.webp',
      'prompt_prenda': 'Replace top',
      'proveedor': 'DECART',
      'modelo': 'lucy-2.5',
      'aviso_orientativo': avisoProbadorPermanente,
    };

Widget app(MockClient mock, {FakePuenteDecart? puente}) {
  final api = ApiClient(httpClient: mock, sesiones: SessionManager());
  return MaterialApp(
    home: ProbadorScreen(
      varianteId: 'v1',
      servicio: ProbadorService(api: api),
      navegacion: IaService(api: api),
      puente: puente ?? FakePuenteDecart(),
    ),
  );
}

void main() {
  testWidgets('variante incompatible explica y vuelve', (t) async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async => ok(recursoJson(false)));
    await t.pumpWidget(app(mock));
    await t.pumpAndSettle();
    expect(find.text('Prenda no compatible'), findsOneWidget);
    expect(find.text('Volver al producto'), findsOneWidget);
  });

  testWidgets('fuera de Android informa indisponibilidad', (t) async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async => ok(recursoJson(true)));
    await t.pumpWidget(app(mock));
    await t.pumpAndSettle();
    if (!kIsWeb && !Platform.isAndroid) {
      expect(find.textContaining('solo en Android'), findsOneWidget);
    } else {
      expect(find.textContaining('Visualización orientativa'), findsWidgets);
    }
  });

  testWidgets('aviso permanente y consentimiento versionado', (t) async {
    // Constantes y contrato visibles sin cámara real.
    expect(avisoProbadorPermanente, contains('orientativa'));
    expect(consentimientoDecartVigente, 'decart-v1');
    expect(modeloDecartFijado, 'lucy-2.5');
    expect(duracionMaximaProbadorSegundos, 120);

    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async => ok(recursoJson(true)));
    await t.pumpWidget(app(mock));
    await t.pumpAndSettle();
    // La pantalla existe y resuelve compatibilidad sin Decart real.
    expect(find.byType(ProbadorScreen), findsOneWidget);
    expect(find.text('Probador virtual'), findsOneWidget);
  });

  test('puente expone canales y métodos exactos', () {
    expect(PuenteDecart.canalMetodos, 'fashionstore/decart_try_on');
    expect(PuenteDecart.canalEventos, 'fashionstore/decart_try_on/events');
    expect(PuenteDecart.vistaVideo, 'fashionstore/decart_video');
    expect(PermissionStatus.granted.isGranted, isTrue);
  });

  testWidgets('soporta navegación secuencial de 1 a 5 prendas en probador',
      (t) async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async => ok(recursoJson(true)));
    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final puente = FakePuenteDecart();

    final prendas = [
      PrendaProbador(
        varianteId: 'v1',
        nombre: 'Camisa Oxford',
        sku: 'CAM-001',
        precio: 120.0,
        primeraImagenUrl: 'https://img.fashionstore.com/camisa.webp',
      ),
      PrendaProbador(
        varianteId: 'v2',
        nombre: 'Pantalón Chino',
        sku: 'PAN-002',
        precio: 180.0,
        primeraImagenUrl: 'https://img.fashionstore.com/pantalon.webp',
      ),
      PrendaProbador(
        varianteId: 'v3',
        nombre: 'Blusa Seda',
        sku: 'BLU-003',
        precio: 150.0,
        primeraImagenUrl: 'https://img.fashionstore.com/blusa.webp',
      ),
    ];

    await t.pumpWidget(
      MaterialApp(
        home: ProbadorScreen(
          prendas: prendas,
          servicio: ProbadorService(api: api),
          navegacion: IaService(api: api),
          puente: puente,
          forzarAndroid: true,
        ),
      ),
    );
    await t.pumpAndSettle();

    // Inicia en Prenda 1 de 3 con nombre real
    expect(find.text('Prenda 1 de 3'), findsOneWidget);
    expect(find.text('Camisa Oxford'), findsOneWidget);
    expect(find.text('SKU: CAM-001'), findsOneWidget);

    // Navegar a Prenda 2
    final botonSiguiente = find.byTooltip('Prenda siguiente');
    expect(botonSiguiente, findsOneWidget);
    await t.tap(botonSiguiente);
    await t.pumpAndSettle();

    expect(find.text('Prenda 2 de 3'), findsOneWidget);
    expect(find.text('Pantalón Chino'), findsOneWidget);
    expect(find.text('SKU: PAN-002'), findsOneWidget);

    // Navegar a Prenda 3
    await t.tap(botonSiguiente);
    await t.pumpAndSettle();

    expect(find.text('Prenda 3 de 3'), findsOneWidget);
    expect(find.text('Blusa Seda'), findsOneWidget);
    expect(find.text('SKU: BLU-003'), findsOneWidget);

    // Navegar de regreso a Prenda 2
    final botonAnterior = find.byTooltip('Prenda anterior');
    expect(botonAnterior, findsOneWidget);
    await t.tap(botonAnterior);
    await t.pumpAndSettle();

    expect(find.text('Prenda 2 de 3'), findsOneWidget);
    expect(find.text('Pantalón Chino'), findsOneWidget);
  });

  testWidgets(
      'acciones de compra y reserva usan datos reales y nunca ficticios',
      (t) async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((req) async {
      if (req.url.path.contains('/carritos')) {
        return ok({
          'id': 'car-1',
          'cliente_id': 'cli-1',
          'canal': 'MOVIL',
          'estado': 'ACTIVO',
          'lineas': [
            {
              'id': 'l-1',
              'variante_id': 'v-real-1',
              'cantidad': 1,
              'precio_unitario': 250.00,
              'descuento_unitario': 0.00,
              'subtotal': 250.00,
            }
          ],
          'subtotal': 250.00,
          'descuento_total': 0.00,
          'total': 250.00,
        });
      }
      return ok(recursoJson(true));
    });
    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final puente = FakePuenteDecart();

    t.view.physicalSize = const Size(800, 1600);
    t.view.devicePixelRatio = 1.0;
    addTearDown(() {
      t.view.resetPhysicalSize();
      t.view.resetDevicePixelRatio();
    });

    final prendaReal = PrendaProbador(
      varianteId: 'v-real-1',
      nombre: 'Vestido Seda Real',
      sku: 'VES-REAL-01',
      precio: 250.0,
      primeraImagenUrl: 'https://img.fashionstore.com/vestido.webp',
    );

    final prefs = await SharedPreferences.getInstance();
    final carritoStore = CarritoStore.paraPruebas(
      servicio: CarritoService(api: api),
      prefs: prefs,
    );
    final bolsaStore = BolsaStore.paraPruebas();

    await t.pumpWidget(
      MaterialApp(
        home: ProbadorScreen(
          prendas: [prendaReal],
          servicio: ProbadorService(api: api),
          navegacion: IaService(api: api),
          puente: puente,
          forzarAndroid: true,
          carritoStore: carritoStore,
          bolsaStore: bolsaStore,
        ),
      ),
    );
    await t.pumpAndSettle();

    expect(find.text('Vestido Seda Real'), findsOneWidget);
    expect(find.text('SKU: VES-REAL-01'), findsOneWidget);
    expect(find.textContaining('250,00'), findsOneWidget);

    // Reserva usa datos reales y los añade a BolsaStore
    final botonReservar = find.text('Reservar para probar');
    await t.scrollUntilVisible(botonReservar, 200);
    await t.pumpAndSettle();
    expect(botonReservar, findsOneWidget);
    await t.tap(botonReservar);
    await t.pumpAndSettle();

    expect(bolsaStore.items.length, 1);
    expect(bolsaStore.items.first.varianteId, 'v-real-1');
    expect(bolsaStore.items.first.nombrePrenda, 'Vestido Seda Real');
    expect(bolsaStore.items.first.sku, 'VES-REAL-01');
    expect(bolsaStore.items.first.precio, 250.0);

    // Limpiar snackbar previo antes de añadir al carrito
    ScaffoldMessenger.of(t.element(find.byType(ProbadorScreen)))
        .clearSnackBars();
    await t.pumpAndSettle();

    // Añadir al carrito usa varianteId y datos reales
    final botonCarrito = find.text('Agregar al carrito');
    expect(botonCarrito, findsOneWidget);
    await t.tap(botonCarrito);
    await t.pumpAndSettle();

    expect(find.textContaining('Agregamos Vestido Seda Real a tu carrito'),
        findsOneWidget);
    expect(carritoStore.carrito.lineas.length, 1);
    expect(carritoStore.carrito.lineas.first.varianteId, 'v-real-1');

    // El botón Volver al producto detiene y cierra el puente
    final botonVolver = find.text('Volver al producto');
    expect(botonVolver, findsOneWidget);
    await t.tap(botonVolver);
    await t.pumpAndSettle();

    expect(puente.llamadas.contains('disconnect'), isTrue);
    expect(puente.llamadas.contains('release'), isTrue);
  });
}
