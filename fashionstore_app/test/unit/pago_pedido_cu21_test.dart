import 'package:fashionstore_movil/features/ventas_pagos/models/checkout_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pago/pago_pedido_screen.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pago/stripe_port.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/checkout_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/pago_service.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _CheckoutStub extends CheckoutService {
  bool pagoConfirmado = false;

  @override
  Future<CheckoutRespuesta> obtenerPedido(String pedidoId) async {
    expect(pedidoId, 'pedido-21');
    return CheckoutRespuesta(
      pedidoId: pedidoId,
      total: 130,
      estado: pagoConfirmado ? 'PAGADO' : 'BORRADOR',
      estadoPago: pagoConfirmado ? 'PAGADO' : 'SIN_PAGO',
      estadoCumplimiento: pagoConfirmado ? 'ASIGNADO' : 'SIN_ASIGNACION',
      ofertaRevision: 3,
    );
  }
}

class _PagoStub extends PagoService {
  _PagoStub(this.checkout);

  final _CheckoutStub checkout;
  String? contexto;
  String? recursoId;
  int? revisionOferta;
  int creaciones = 0;
  int confirmaciones = 0;

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
    creaciones++;
    this.contexto = contexto;
    this.recursoId = recursoId ?? pedidoCompraId;
    revisionOferta = ofertaRevision;
    return {
      'orden_pago_id': 'orden-22',
      'estado': 'PENDIENTE',
      'monto_bob': 130.0,
      'client_secret': 'pi_test_secret',
    };
  }

  @override
  Future<Map<String, dynamic>> confirmarOrdenPago(String ordenId) async {
    confirmaciones++;
    expect(ordenId, 'orden-22');
    checkout.pagoConfirmado = true;
    return {'orden_pago_id': ordenId, 'estado': 'CAPTURADO', 'monto_bob': 130.0};
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('CU21 durable parser conserva pedido, oferta, total y estados', () {
    final compra = CheckoutRespuesta.fromJson({
      'pedido_id': 'pedido-21',
      'total_bob': '130.00',
      'oferta_revision': 3,
      'estado': 'BORRADOR',
      'estado_pago': 'SIN_PAGO',
      'estado_cumplimiento': 'SIN_ASIGNACION',
    });
    expect(compra.esPedidoDurable, isTrue);
    expect(compra.pedidoId, 'pedido-21');
    expect(compra.ventaId, isEmpty);
    expect(compra.total, 130);
    expect(compra.ofertaRevision, 3);
    expect(compra.estadoPago, 'SIN_PAGO');
  });

  testWidgets('CU21 inicia Stripe con contexto PEDIDO y confirma con el backend', (tester) async {
    final checkout = _CheckoutStub();
    final pago = _PagoStub(checkout);
    final stripe = FakePuertoStripe(respuestas: [ResultadoHojaPago.completado]);

    await tester.pumpWidget(MaterialApp(
      home: PagoPedidoScreen(
        pedidoId: 'pedido-21',
        servicioCheckout: checkout,
        servicioPago: pago,
        puertoStripe: stripe,
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Total: Bs 130.00'), findsOneWidget);

    await tester.tap(find.byKey(const Key('btn_pagar_pedido_stripe')));
    await tester.pumpAndSettle();

    expect(pago.creaciones, 1);
    expect(pago.contexto, 'PEDIDO');
    expect(pago.recursoId, 'pedido-21');
    expect(pago.revisionOferta, 3);
    expect(pago.confirmaciones, 1);
    expect(stripe.ultimoClientSecret, 'pi_test_secret');
    expect(find.text('Pago aprobado'), findsOneWidget);
    expect(find.byKey(const Key('btn_pagar_pedido_stripe')), findsNothing);
  });

  testWidgets('Cancelar PaymentSheet deja el pedido sin pago y permite retomarlo', (tester) async {
    final checkout = _CheckoutStub();
    final pago = _PagoStub(checkout);
    final stripe = FakePuertoStripe(respuestas: [ResultadoHojaPago.cancelado]);

    await tester.pumpWidget(MaterialApp(
      home: PagoPedidoScreen(
        pedidoId: 'pedido-21',
        servicioCheckout: checkout,
        servicioPago: pago,
        puertoStripe: stripe,
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('btn_pagar_pedido_stripe')));
    await tester.pumpAndSettle();

    expect(find.text('Pendiente de confirmación'), findsOneWidget);
    expect(pago.confirmaciones, 0);
    expect(find.byKey(const Key('btn_pagar_pedido_stripe')), findsOneWidget);
  });
}
