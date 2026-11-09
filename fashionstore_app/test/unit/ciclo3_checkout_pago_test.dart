// Checkout recojo/delivery, cotización, pagos, reintento y pedidos.
import 'dart:convert';

import 'package:fashionstore_movil/features/ventas_pagos/models/checkout_model.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/checkout_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/entrega_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/pago_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pago/stripe_port.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

ApiClient apiCon(MockClient mock) =>
    ApiClient(httpClient: mock, sesiones: SessionManager());

http.Response ok(Object j, [int code = 200]) => http.Response(
      jsonEncode(j),
      code,
      headers: {'content-type': 'application/json'},
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('checkout recojo envía modalidad sin dirección', () async {
    SharedPreferences.setMockInitialValues({});
    Map<String, dynamic>? cuerpo;
    final mock = MockClient((req) async {
      cuerpo = jsonDecode(req.body) as Map<String, dynamic>;
      return ok({
        'venta_id': 'v1',
        'numero': 'FS-1',
        'estado': 'PENDIENTE_PAGO',
        'total': 100,
        'expira_en': '2026-09-21T12:00:00Z',
        'pedido_entrega_id': 'p1',
      }, 201);
    });
    final srv = CheckoutService(api: apiCon(mock));
    final r = await srv.confirmar(
      datos: CheckoutCrear(sucursalId: 's1', modalidad: 'RECOJO'),
    );
    expect(r.ventaId, 'v1');
    expect(cuerpo!['modalidad'], 'RECOJO');
    expect(cuerpo!.containsKey('direccion'), isFalse);
  });

  test('checkout delivery exige dirección y anillo', () async {
    SharedPreferences.setMockInitialValues({});
    Map<String, dynamic>? cuerpo;
    final mock = MockClient((req) async {
      cuerpo = jsonDecode(req.body) as Map<String, dynamic>;
      return ok({
        'venta_id': 'v2',
        'numero': 'FS-2',
        'estado': 'PENDIENTE_PAGO',
        'total': 124,
        'expira_en': '2026-09-21T12:00:00Z',
        'pedido_entrega_id': 'p2',
      }, 201);
    });
    final srv = CheckoutService(api: apiCon(mock));
    await srv.confirmar(
      datos: CheckoutCrear(
        sucursalId: 's1',
        modalidad: 'DELIVERY',
        direccion: 'Calle 1',
        anilloDestino: 5,
      ),
    );
    expect(cuerpo!['anillo_destino'], 5);
    expect(cuerpo!['direccion'], 'Calle 1');
  });

  test('cotización calcula tarifa separada del total', () async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async => ok({
          'sucursal_id': 's1',
          'anillo_sucursal': 2,
          'anillo_destino': 5,
          'tarifa_base': 15,
          'incremento_anillo': 3,
          'costo_entrega': 24,
        }));
    final srv = EntregaService(api: apiCon(mock));
    final c = await srv.cotizar(sucursalId: 's1', anilloDestino: 5);
    expect(c.costoEntrega, 24.0);
  });

  test('intención y reintento usan Idempotency-Key distintas', () async {
    SharedPreferences.setMockInitialValues({});
    final claves = <String?>[];
    final mock = MockClient((req) async {
      claves.add(req.headers['Idempotency-Key']);
      return ok({
        'payment_intent_id': 'pi_1',
        'venta_id': 'v1',
        'monto': 100,
        'moneda': 'BOB',
        'estado': 'REQUIERE_PAGO',
        'client_secret': 'sec_1',
      }, 201);
    });
    final srv = PagoService(api: apiCon(mock));
    await srv.crearIntencion(ventaId: 'v1');
    await srv.reintentar(ventaId: 'v1');
    expect(claves.length, 2);
    expect(claves[0], isNot(equals(claves[1])));
  });

  test('pago pendiente no confirma venta; aprobado sí', () async {
    SharedPreferences.setMockInitialValues({});
    var llamadas = 0;
    final mock = MockClient((_) async {
      llamadas++;
      final pago = llamadas < 3 ? 'PENDIENTE' : 'APROBADO';
      final venta = llamadas < 3 ? 'PENDIENTE_PAGO' : 'PAGADA';
      return ok({
        'venta_id': 'v1',
        'estado_venta': venta,
        'estado_pago': pago,
        'monto': 100,
      });
    });
    final srv = PagoService(api: apiCon(mock));
    final primero = await srv.consultarEstado('v1');
    expect(primero.pagoAprobado, isFalse);
    await srv.consultarEstado('v1');
    final tercero = await srv.consultarEstado('v1');
    expect(tercero.pagoAprobado, isTrue);
  });

  test('FakePuertoStripe registra secreto sin exponerlo', () async {
    final fake = FakePuertoStripe(respuestas: [ResultadoHojaPago.completado]);
    await fake.inicializarHoja(clientSecret: 'sec_test');
    expect(fake.inicializaciones, 1);
    expect(fake.ultimoClientSecret, 'sec_test');
    expect(await fake.presentarHoja(), ResultadoHojaPago.completado);
  });

  test('pedidos separan activo/completado/cancelado', () async {
    SharedPreferences.setMockInitialValues({});
    Map<String, dynamic> pedido(String id, String estado) => {
          'id': id,
          'venta_id': 'v-$id',
          'sucursal_id': 's1',
          'modalidad': 'RECOJO',
          'estado': estado,
          'tarifa_base': 0,
          'incremento_anillo': 0,
          'costo_entrega': 0,
          'creada_en': '2026-09-21T10:00:00Z',
          'puede_cancelar': estado == 'SOLICITADO',
          'puede_transicionar': false,
        };
    final mock = MockClient((_) async => ok({
          'total': 3,
          'limit': 50,
          'offset': 0,
          'items': [
            pedido('p1', 'SOLICITADO'),
            pedido('p2', 'ENTREGADO'),
            pedido('p3', 'CANCELADO'),
          ],
        }));
    final srv = EntregaService(api: apiCon(mock));
    final lista = await srv.misPedidos();
    expect(lista.items.where((p) => p.estaActivo).length, 1);
    expect(lista.items.where((p) => p.estaCompletado).length, 1);
    expect(lista.items.where((p) => p.estaCancelado).length, 1);
    expect(lista.items.first.puedeCancelar, isTrue);
  });
}
