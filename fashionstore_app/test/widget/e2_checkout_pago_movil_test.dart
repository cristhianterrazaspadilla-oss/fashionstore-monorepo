import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fashionstore_movil/features/ventas_pagos/checkout/checkout_screen.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pago/pago_screen.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pago/stripe_port.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pago/stripe_adapter.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/pago_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/stripe_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/carrito_service.dart';
import 'package:fashionstore_movil/features/organizacion/services/sucursal_service.dart';
import 'package:fashionstore_movil/features/organizacion/models/organizacion_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/carrito_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/services/sincronizacion_offline_service.dart';
import 'package:fashionstore_movil/features/reservas_traslados/models/sincronizacion_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/entrega_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/entrega_model.dart';
import 'package:fashionstore_movil/features/organizacion/services/tasa_cambio_service.dart';
import 'package:fashionstore_movil/features/organizacion/models/tasa_cambio_model.dart';

class FakeEntregaService extends EntregaService {
  @override
  Future<CotizacionDelivery> cotizar({required String sucursalId, required int anilloDestino}) async {
    return CotizacionDelivery.fromJson({
      'tarifa_delivery_bob': 15.0,
      'anillo_destino': anilloDestino,
      'sucursal_id': sucursalId,
      'cubre': true,
    });
  }
}

class FakeTasaService extends TasaCambioService {
  @override
  Future<TasaCambioModel> obtenerTasaVigente() async {
    return TasaCambioModel.fromJson({
      'id': 'tasa-1',
      'tasa_bob_por_usd': 6.96,
      'activa': true,
      'creado_en': DateTime.now().toUtc().toIso8601String(),
    });
  }
}

class FakeCarritoService extends CarritoService {
  @override
  Future<CarritoCompra> obtenerOCrear({String canal = 'MOVIL'}) async {
    return CarritoCompra.fromJson({
      'id': 'car-1',
      'cliente_id': 'cli-1',
      'canal': 'MOVIL',
      'estado': 'ACTIVO',
      'subtotal': 180.0,
      'descuento_total': 0.0,
      'total': 180.0,
      'lineas': [
        {
          'id': 'lin-1',
          'variante_id': 'var-10',
          'cantidad': 2,
          'precio_unitario': 90.0,
          'descuento_unitario': 0.0,
          'subtotal': 180.0,
        }
      ],
    });
  }

  @override
  Future<CoberturaCarrito> cobertura({String canal = 'MOVIL'}) async {
    return CoberturaCarrito.fromJson({
      'sucursales': [
        {
          'sucursal_id': 'suc-1',
          'sucursal_nombre': 'Sucursal Centro',
          'cubre_todo': true,
          'faltantes': [],
        }
      ],
    });
  }
}

class FakeSucursalService extends SucursalService {
  @override
  Future<List<SucursalModel>> listar() async {
    return [
      SucursalModel.fromJson({
        'id': 'suc-1',
        'nombre': 'Sucursal Centro',
        'ciudad_id': 'ciu-1',
        'direccion': 'Av. Principal 123',
        'activa': true,
      }),
    ];
  }
}

class FakeSincronizacionOfflineService extends SincronizacionOfflineService {
  bool compraEncolada = false;
  String? ultimaSucursal;
  int lineasEncoladas = 0;
  Map<String, dynamic>? ultimaAutorizacion;

  @override
  Future<OperacionSincronizacionLocal> encolarCompraOffline({
    required String sucursalId,
    required List<Map<String, dynamic>> lineas,
    String modalidad = 'RECOJO',
    String? direccion,
    int? anilloDestino,
    Map<String, dynamic>? autorizacionCobro,
    String? empresaId,
    String? usuarioId,
    String? dispositivoId,
  }) async {
    compraEncolada = true;
    ultimaSucursal = sucursalId;
    lineasEncoladas = lineas.length;
    ultimaAutorizacion = autorizacionCobro;

    return OperacionSincronizacionLocal(
      operacionId: 'op-offline-mock-12345678',
      empresaId: 'emp-1',
      usuarioId: 'usr-1',
      dispositivoId: 'disp-1',
      secuenciaLocal: 1,
      creadaLocalEn: '2026-11-04T12:00:00Z',
      datosJson: '{}',
      actualizadoEn: '2026-11-04T12:00:00Z',
    );
  }
}

class FakePagoServiceE2 extends PagoService {
  bool ordenCreada = false;
  bool setupIntentPreparado = false;

  @override
  Future<EstadoPagoVenta> consultarEstado(String ventaId) async {
    return EstadoPagoVenta.fromJson({
      'venta_id': ventaId,
      'estado': 'PENDIENTE_PAGO',
      'monto_total_bob': 180.0,
      'pago_aprobado': false,
      'venta_vencida': false,
      'puede_reintentar': true,
      'monto_formateado': 'Bs 180.00',
    });
  }

  @override
  Future<Map<String, dynamic>> crearOrdenPago({
    String? contexto,
    String? recursoId,
    String? ventaId,
    String? pedidoCompraId,
    String? metodoPreparadoId,
    int? ofertaRevision,
    bool consentimientoCobroPosterior = false,
    double? montoBob,
    String? claveIdempotencia,
  }) async {
    ordenCreada = true;
    return {
      'orden_pago_id': 'ord-cu22-123',
      'client_secret': 'pi_secret_mock_cu22',
      'estado': 'PENDIENTE',
    };
  }

  @override
  Future<Map<String, dynamic>> prepararMetodoSetupIntent({
    String? huellaDispositivo,
    String? claveIdempotencia,
  }) async {
    setupIntentPreparado = true;
    return {
      'preparacion_pago_id': 'prep-mock-cu22',
      'client_secret': 'seti_secret_mock_cu22',
      'estado': 'PENDIENTE',
    };
  }

  @override
  Future<Map<String, dynamic>> consultarOrdenPago(String ordenId) async {
    return {'orden_pago_id': ordenId, 'estado': 'PENDIENTE'};
  }

  @override
  Future<Map<String, dynamic>> consultarMetodoPreparado(String metodoId) async {
    return {'preparacion_pago_id': metodoId, 'estado': 'LISTO'};
  }

  bool metodoConfirmado = false;
  String? ultimoMetodoConfirmadoId;

  @override
  Future<Map<String, dynamic>> confirmarMetodoPreparado({
    required String metodoId,
    String? paymentMethodId,
  }) async {
    metodoConfirmado = true;
    ultimoMetodoConfirmadoId = metodoId;
    return {'preparacion_pago_id': metodoId, 'estado': 'LISTO'};
  }
}

class FakePagoServiceConErrorConfirmacion extends FakePagoServiceE2 {
  @override
  Future<Map<String, dynamic>> confirmarMetodoPreparado({
    required String metodoId,
    String? paymentMethodId,
  }) async {
    throw Exception('Error 500: Falló confirmación del SetupIntent en backend');
  }
}

class FakePagoServiceConEstadoPendiente extends FakePagoServiceE2 {
  @override
  Future<Map<String, dynamic>> consultarMetodoPreparado(String metodoId) async {
    return {'preparacion_pago_id': metodoId, 'estado': 'PENDIENTE'};
  }
}

void main() {
  group('Vectores canónicos Huella v3 (CU05)', () {
    test('Vector 1 (RECOJO) coincide exactamente con hash esperado', () {
      final huella = calcularHuellaCompraCanonica(
        empresaId: '11111111-1111-1111-1111-111111111111',
        usuarioId: '55555555-5555-5555-5555-555555555555',
        sucursalId: '33333333-3333-3333-3333-333333333333',
        modalidad: 'RECOJO',
        lineas: [
          {
            'cantidad': 1,
            'precio_unitario_bob': '100.00',
            'variante_id': '22222222-2222-2222-2222-222222222222',
          }
        ],
        baseBob: 100.0,
        descuentoBob: 0.0,
        envioBob: 0.0,
        totalBob: 100.0,
        monedaCobro: 'USD',
        importeCobro: 14.37,
        tasaId: '44444444-4444-4444-4444-444444444444',
        tasaBobPorUsd: 6.96,
        condicionesVersion: 'v3',
        vigenteHasta: '2026-11-06T15:00:00Z',
      );
      expect(
        huella,
        equals('5249e0cea418ec6262f9f0ef7a71686d2d6cecf8c4083dafe77aa0d24c3eacee'),
      );
    });

    test('Vector 2 (DELIVERY con dirección y envío) coincide exactamente con hash esperado', () {
      final huella = calcularHuellaCompraCanonica(
        empresaId: '11111111-1111-1111-1111-111111111111',
        usuarioId: '55555555-5555-5555-5555-555555555555',
        sucursalId: '33333333-3333-3333-3333-333333333333',
        modalidad: 'DELIVERY',
        direccion: 'Av. Las Americas 123',
        lineas: [
          {
            'cantidad': 1,
            'precio_unitario_bob': '100.00',
            'variante_id': '22222222-2222-2222-2222-222222222222',
          }
        ],
        baseBob: 100.0,
        descuentoBob: 0.0,
        envioBob: 15.0,
        totalBob: 115.0,
        monedaCobro: 'USD',
        importeCobro: 16.52,
        tasaId: '44444444-4444-4444-4444-444444444444',
        tasaBobPorUsd: 6.96,
        condicionesVersion: 'v3',
        vigenteHasta: '2026-11-06T15:00:00Z',
      );
      expect(
        huella,
        equals('b095703bdd526b2a7da5d97f5e52dbe7ec7a118d72511c72b9602cd03fd98f07'),
      );
    });
  });

  testWidgets('CheckoutScreen con método real LISTO y tasa vigente encola con cobro automático y huella canónica', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final fakeSync = FakeSincronizacionOfflineService();
    final fakePago = FakePagoServiceE2();

    await tester.pumpWidget(
      MaterialApp(
        home: CheckoutScreen(
          servicioCarrito: FakeCarritoService(),
          servicioSucursal: FakeSucursalService(),
          servicioEntrega: FakeEntregaService(),
          servicioTasa: FakeTasaService(),
          servicioSincronizacion: fakeSync,
          servicioPago: fakePago,
          metodoPreparadoId: 'prep-listo-101',
          empresaId: '11111111-1111-1111-1111-111111111111',
          usuarioId: '55555555-5555-5555-5555-555555555555',
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Scroll hasta el botón de compra offline
    final btnOffline = find.byKey(const Key('btn_compra_offline_cu05'));
    await tester.scrollUntilVisible(btnOffline, 300);
    await tester.drag(find.byType(ListView), const Offset(0, -150));
    await tester.pumpAndSettle();
    expect(btnOffline, findsOneWidget);

    // Toca botón para guardar offline
    await tester.tap(btnOffline);
    await tester.pumpAndSettle();

    // Se invocó el servicio de sincronización y se autoriza cobro automático
    expect(fakeSync.compraEncolada, isTrue);
    expect(fakeSync.ultimaSucursal, equals('suc-1'));
    expect(fakeSync.lineasEncoladas, equals(1));
    expect(fakeSync.ultimaAutorizacion, isNotNull);
    expect(fakeSync.ultimaAutorizacion!['moneda_cobro'], equals('USD'));
    expect(fakeSync.ultimaAutorizacion!['tasa_id'], equals('tasa-1'));
    expect(fakeSync.ultimaAutorizacion!['tasa_bob_por_usd'], equals('6.96'));
    expect(fakeSync.ultimaAutorizacion!['preparacion_pago_id'], equals('prep-listo-101'));
    expect(fakeSync.ultimaAutorizacion!['permite_cobro_al_reconectar'], isTrue);
    expect(fakeSync.ultimaAutorizacion!['condiciones_version'], equals('v3'));
    expect(fakeSync.ultimaAutorizacion!['huella_compra'], hasLength(64));
    expect(find.text('Compra guardada offline (CU05 v3)'), findsOneWidget);
  });

  testWidgets('CheckoutScreen sin método preparado desactiva cobro automático y omite autorizacionCobro (null)', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final fakeSync = FakeSincronizacionOfflineService();

    await tester.pumpWidget(
      MaterialApp(
        home: CheckoutScreen(
          servicioCarrito: FakeCarritoService(),
          servicioSucursal: FakeSucursalService(),
          servicioEntrega: FakeEntregaService(),
          servicioTasa: FakeTasaService(),
          servicioSincronizacion: fakeSync,
          // No se pasa método preparado
        ),
      ),
    );
    await tester.pumpAndSettle();

    final btnOffline = find.byKey(const Key('btn_compra_offline_cu05'));
    await tester.scrollUntilVisible(btnOffline, 300);
    await tester.drag(find.byType(ListView), const Offset(0, -150));
    await tester.pumpAndSettle();
    expect(btnOffline, findsOneWidget);

    await tester.tap(btnOffline);
    await tester.pumpAndSettle();

    expect(fakeSync.compraEncolada, isTrue);
    // D1 CU05: Se omite completamente autorizacionCobro (es null)
    expect(fakeSync.ultimaAutorizacion, isNull);
    expect(find.text('Compra guardada offline (CU05 v3)'), findsOneWidget);
    expect(find.textContaining('PENDIENTE_INTERVENCION'), findsOneWidget);
  });

  testWidgets('CheckoutScreen sin tasa vigente real desactiva cobro automático y omite autorizacionCobro (null)', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final fakeSync = FakeSincronizacionOfflineService();
    final fakePago = FakePagoServiceE2();

    await tester.pumpWidget(
      MaterialApp(
        home: CheckoutScreen(
          servicioCarrito: FakeCarritoService(),
          servicioSucursal: FakeSucursalService(),
          servicioEntrega: FakeEntregaService(),
          servicioTasa: null, // Sin tasa
          servicioSincronizacion: fakeSync,
          servicioPago: fakePago,
          metodoPreparadoId: 'prep-listo-101',
        ),
      ),
    );
    await tester.pumpAndSettle();

    final btnOffline = find.byKey(const Key('btn_compra_offline_cu05'));
    await tester.scrollUntilVisible(btnOffline, 300);
    await tester.drag(find.byType(ListView), const Offset(0, -150));
    await tester.pumpAndSettle();

    await tester.tap(btnOffline);
    await tester.pumpAndSettle();

    expect(fakeSync.compraEncolada, isTrue);
    // D1 CU05: Sin tasa oficial vigente, se omite completamente autorizacionCobro (es null)
    expect(fakeSync.ultimaAutorizacion, isNull);
    expect(find.text('Compra guardada offline (CU05 v3)'), findsOneWidget);
    expect(find.textContaining('PENDIENTE_INTERVENCION'), findsOneWidget);
  });

  test('AdaptadorStripe diferencia SetupIntent (seti_...) de PaymentIntent (pi_...) asignando setupIntentClientSecret', () {
    // D2 CU22: SetupIntent debe usar setupIntentClientSecret y dejar paymentIntentClientSecret en null
    final paramsSetup = AdaptadorStripe.construirParametros(clientSecret: 'seti_12345_secret');
    expect(paramsSetup.setupIntentClientSecret, equals('seti_12345_secret'));
    expect(paramsSetup.paymentIntentClientSecret, isNull);

    // PaymentIntent debe usar paymentIntentClientSecret y dejar setupIntentClientSecret en null
    final paramsPayment = AdaptadorStripe.construirParametros(clientSecret: 'pi_67890_secret');
    expect(paramsPayment.paymentIntentClientSecret, equals('pi_67890_secret'));
    expect(paramsSetup.paymentIntentClientSecret, isNull);
  });

  testWidgets('PagoScreen expone acciones CU22 de Orden de Pago y SetupIntent', (tester) async {
    final fakePago = FakePagoServiceE2();
    final fakeStripe = FakePuertoStripe(respuestas: [
      ResultadoHojaPago.completado,
      ResultadoHojaPago.completado,
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: PagoScreen(
          ventaId: 'v-test-100',
          servicioPago: fakePago,
          puertoStripe: fakeStripe,
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Botones CU22 presentes
    expect(find.byKey(const Key('btn_pagar_orden_cu22')), findsOneWidget);
    expect(find.byKey(const Key('btn_preparar_metodo_cu22')), findsOneWidget);

    // Pagar con orden de pago CU22
    await tester.tap(find.byKey(const Key('btn_pagar_orden_cu22')));
    await tester.pumpAndSettle();
    expect(fakePago.ordenCreada, isTrue);

    // Preparar método SetupIntent CU22
    await tester.tap(find.byKey(const Key('btn_preparar_metodo_cu22')));
    await tester.pumpAndSettle();
    expect(fakePago.setupIntentPreparado, isTrue);
  });

  testWidgets('PagoScreen CU22: Error en confirmación no habilita cobro ni muestra vinculación exitosa', (tester) async {
    final fakePagoError = FakePagoServiceConErrorConfirmacion();
    final fakeStripe = FakePuertoStripe(respuestas: [
      ResultadoHojaPago.completado,
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: PagoScreen(
          ventaId: 'v-test-error-1',
          servicioPago: fakePagoError,
          puertoStripe: fakeStripe,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('btn_preparar_metodo_cu22')));
    await tester.pumpAndSettle();

    // No se muestra vinculación exitosa
    expect(find.text('Método de pago vinculado con éxito (SetupIntent CU22).'), findsNothing);
    // Se muestra mensaje de error visible al usuario (en tarjeta de error y/o SnackBar)
    expect(find.textContaining('Falló confirmación del SetupIntent en backend'), findsWidgets);
  });

  testWidgets('PagoScreen CU22: Estado PENDIENTE tras confirmación no muestra vinculación exitosa ni guarda método LISTO', (tester) async {
    final fakePagoPendiente = FakePagoServiceConEstadoPendiente();
    final fakeStripe = FakePuertoStripe(respuestas: [
      ResultadoHojaPago.completado,
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: PagoScreen(
          ventaId: 'v-test-pend-1',
          servicioPago: fakePagoPendiente,
          puertoStripe: fakeStripe,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('btn_preparar_metodo_cu22')));
    await tester.pumpAndSettle();

    // No se muestra vinculación exitosa
    expect(find.text('Método de pago vinculado con éxito (SetupIntent CU22).'), findsNothing);
    // Se muestra advertencia de que quedó en estado PENDIENTE (en tarjeta y/o SnackBar)
    expect(find.textContaining('El método de pago no quedó listo en el servidor (estado: PENDIENTE)'), findsWidgets);
  });

  testWidgets('PagoScreen CU22: Flujo exitoso confirma método, verifica estado LISTO y muestra vinculación exitosa', (tester) async {
    final fakePago = FakePagoServiceE2();
    final fakeStripe = FakePuertoStripe(respuestas: [
      ResultadoHojaPago.completado,
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: PagoScreen(
          ventaId: 'v-test-ok-1',
          servicioPago: fakePago,
          puertoStripe: fakeStripe,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('btn_preparar_metodo_cu22')));
    await tester.pumpAndSettle();

    // Se confirma el método en backend
    expect(fakePago.metodoConfirmado, isTrue);
    expect(fakePago.ultimoMetodoConfirmadoId, equals('prep-mock-cu22'));
    // SetupIntent pasó clientSecret 'seti_...'
    expect(fakeStripe.ultimoClientSecret, startsWith('seti_'));
    // Se muestra SnackBar exitoso
    expect(find.text('Método de pago vinculado con éxito (SetupIntent CU22).'), findsOneWidget);
  });
}
