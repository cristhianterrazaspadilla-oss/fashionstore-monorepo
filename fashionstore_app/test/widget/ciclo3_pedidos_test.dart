// Widgets pedidos: lista con filtros, detalle, seguimiento y textos largos.
import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/checkout_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/entrega_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/pago_service.dart';
import 'package:fashionstore_movil/features/organizacion/services/sucursal_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pedidos/pedido_detalle_screen.dart';
import 'package:fashionstore_movil/features/ventas_pagos/pedidos/pedidos_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response ok(Object j) => http.Response(
      jsonEncode(j),
      200,
      headers: {'content-type': 'application/json'},
    );

Map<String, dynamic> pedido(String id, String estado, String mod) => {
      'id': id,
      'venta_id': 'v-$id',
      'sucursal_id': 's1',
      'modalidad': mod,
      'estado': estado,
      'anillo_sucursal': 2,
      'anillo_destino': 4,
      'direccion': 'Av. Principal 456, Barrio Equipetrol, Santa Cruz',
      'tarifa_base': 15,
      'incremento_anillo': 3,
      'costo_entrega': 21,
      'codigo_recojo': 'RC-1234',
      'creada_en': '2026-09-21T10:00:00Z',
      'puede_cancelar': false,
      'puede_transicionar': false,
    };

MockClient mockLista() => MockClient((_) async => ok({
      'total': 3,
      'limit': 50,
      'offset': 0,
      'items': [
        pedido('p1', 'SOLICITADO', 'RECOJO'),
        pedido('p2', 'EN_REPARTO', 'DELIVERY'),
        pedido('p3', 'CANCELADO', 'RECOJO'),
      ],
    }));

MockClient mockDetalle() => MockClient((req) async {
      final p = req.url.path;
      if (p.contains('mis-pedidos')) {
        return ok({'total': 0, 'limit': 50, 'offset': 0, 'items': []});
      }
      if (p.contains('/entregas/p1')) {
        return ok(pedido('p1', 'LISTO_RECOJO', 'RECOJO'));
      }
      if (p.contains('/ventas/')) {
        return ok({
          'id': 'v-p1',
          'numero': 'FS-2026-000123456789',
          'sucursal_id': 's1',
          'canal': 'MOVIL',
          'estado': 'PAGADA',
          'subtotal': 200,
          'descuento': 10,
          'adelanto_descontado': 0,
          'costo_entrega': 0,
          'total': 190,
          'creada_en': '2026-09-21T10:00:00Z',
          'detalles': [
            {
              'id': 'd1',
              'variante_id': 'v1',
              'cantidad': 1,
              'precio_unitario': 200,
              'descuento': 10,
            },
          ],
        });
      }
      if (p.contains('estado')) {
        return ok({
          'venta_id': 'v-p1',
          'estado_venta': 'PAGADA',
          'estado_pago': 'APROBADO',
          'monto': 190,
        });
      }
      if (p.contains('/sucursales')) {
        return ok([
          {
            'id': 's1',
            'ciudad_id': 'c1',
            'nombre':
                'Sucursal Central con nombre muy largo para probar overflow en pantallas compactas',
            'direccion':
                'Dirección extensa número 1234, zona comercial, Santa Cruz de la Sierra, Bolivia',
            'tarifa_base_delivery': 15,
            'incremento_anillo_delivery': 3,
            'anillo_minimo_delivery': 1,
            'anillo_maximo_delivery': 10,
            'delivery_activo': true,
            'activa': true,
          },
        ]);
      }
      return http.Response('no', 404);
    });

void main() {
  setUpAll(() async {
    await initializeDateFormatting('es');
  });
  testWidgets('lista separa activos, completados y cancelados', (t) async {
    SharedPreferences.setMockInitialValues({});
    final api = ApiClient(httpClient: mockLista(), sesiones: SessionManager());
    await t.pumpWidget(MaterialApp(
      home: Scaffold(body: PedidosScreen(servicio: EntregaService(api: api))),
    ));
    await t.pumpAndSettle();
    expect(find.textContaining('Recojo'), findsWidgets);
    await t.tap(find.text('Todos'));
    await t.pumpAndSettle();
    expect(find.textContaining('Cancelado'), findsWidgets);
    expect(find.text('Recojo · Cancelado'), findsOneWidget);
  });

  testWidgets('detalle muestra seguimiento y código de recojo', (t) async {
    SharedPreferences.setMockInitialValues({});
    final api =
        ApiClient(httpClient: mockDetalle(), sesiones: SessionManager());
    await t.pumpWidget(MaterialApp(
      home: PedidoDetalleScreen(
        pedidoId: 'p1',
        servicioEntrega: EntregaService(api: api),
        servicioCheckout: CheckoutService(api: api),
        servicioPago: PagoService(api: api),
        servicioSucursal: SucursalService(api: api),
      ),
    ));
    await t.pumpAndSettle();
    expect(find.text('Seguimiento'), findsOneWidget);
    expect(find.textContaining('Listo para recojo'), findsWidgets);
    expect(find.textContaining('Código de recojo'), findsOneWidget);
    expect(find.textContaining('FS-2026-000123456789'), findsOneWidget);
    expect(t.takeException(), isNull);
  });

  testWidgets('estados de carga, vacío y error', (t) async {
    SharedPreferences.setMockInitialValues({});
    final vacio = MockClient((_) async => ok({
          'total': 0,
          'limit': 50,
          'offset': 0,
          'items': [],
        }));
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PedidosScreen(
          servicio: EntregaService(
              api: ApiClient(httpClient: vacio, sesiones: SessionManager())),
        ),
      ),
    ));
    await t.pumpAndSettle();
    expect(find.text('Aún no tienes pedidos'), findsOneWidget);

    final falla = MockClient((_) async => http.Response('x', 500));
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: PedidosScreen(
          key: UniqueKey(),
          servicio: EntregaService(
              api: ApiClient(httpClient: falla, sesiones: SessionManager())),
        ),
      ),
    ));
    await t.pumpAndSettle();
    expect(find.text('Reintentar'), findsOneWidget);
  });
}
