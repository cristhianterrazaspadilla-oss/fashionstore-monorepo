import 'package:flutter_test/flutter_test.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/pago_service.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';

class FakeApiClientPagosE2 extends ApiClient {
  @override
  Future<T> post<T>(
    String ruta, {
    Object? cuerpo,
    Map<String, String>? query,
    String? idempotencyKey,
    required T Function(dynamic) convertir,
  }) async {
    final map = (cuerpo as Map?) ?? {};
    if (ruta == '/pagos/stripe/metodos/preparar' ||
        ruta == '/pagos/stripe/metodos-preparados/setup-intent') {
      return convertir({
        'preparacion_pago_id': 'prep-123',
        'client_secret': 'seti_secret_123',
        'stripe_customer_id': 'cus_123',
        'estado': 'PENDIENTE',
        'proveedor': 'STRIPE',
      });
    } else if (ruta == '/pagos/stripe/ordenes') {
      return convertir({
        'orden_pago_id': 'ord-999',
        'orden_id': 'ord-999',
        'contexto': map['contexto'] ?? 'VENTA',
        'recurso_id': map['recurso_id'] ?? 'v-100',
        'estado': 'PAGADO',
        'monto_bob': 150.0,
      });
    } else if (ruta.endsWith('/continuar-accion')) {
      return convertir({
        'orden_pago_id': 'ord-999',
        'estado': 'CAPTURADO',
      });
    }
    throw UnimplementedError('Ruta POST no mockeada: $ruta');
  }

  @override
  Future<T> get<T>(
    String ruta, {
    Map<String, String>? query,
    required T Function(dynamic) convertir,
  }) async {
    if (ruta.startsWith('/pagos/stripe/ordenes/')) {
      return convertir({
        'orden_id': 'ord-999',
        'estado': 'PAGADO',
        'requiere_accion': false,
      });
    }
    throw UnimplementedError('Ruta GET no mockeada: $ruta');
  }
}

void main() {
  late PagoService service;

  setUp(() {
    service = PagoService(api: FakeApiClientPagosE2());
  });

  group('PagoService CU22 SetupIntent y Órdenes Móvil', () {
    test('prepararMetodoSetupIntent retorna client_secret de Stripe', () async {
      final res = await service.prepararMetodoSetupIntent();
      expect(res['client_secret'], equals('seti_secret_123'));
      expect(res['stripe_customer_id'], equals('cus_123'));
    });

    test('crearOrdenPago y consultarOrdenPago funcionan con método preparado', () async {
      final orden = await service.crearOrdenPago(
        ventaId: 'v-100',
        metodoPreparadoId: 'mp-55',
        montoBob: 200.0,
      );
      expect(orden['orden_id'], equals('ord-999'));
      expect(orden['estado'], equals('PAGADO'));

      final estado = await service.consultarOrdenPago('ord-999');
      expect(estado['estado'], equals('PAGADO'));
      expect(estado['requiere_accion'], isFalse);
    });
  });
}
