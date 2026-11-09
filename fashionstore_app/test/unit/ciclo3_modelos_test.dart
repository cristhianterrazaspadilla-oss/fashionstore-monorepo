// Serialización de modelos Ciclo 3 + importes String/número.
import 'package:fashionstore_movil/features/ventas_pagos/models/carrito_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/checkout_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/entrega_model.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/models/ia_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/pago_model.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/models/probador_model.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Carrito', () {
    test('lee importes del carrito durable CU21 sin mostrar cero', () {
      final c = CarritoCompra.fromJson({
        'id': 'car-2',
        'cliente_id': 'cli-2',
        'canal': 'MOVIL',
        'estado': 'ACTIVO',
        'total_estimado_bob': '130.00',
        'lineas': [
          {
            'id': 'l2',
            'variante_id': 'v2',
            'cantidad': 1,
            'precio_unitario_bob': '130.00',
            'subtotal_bob': '130.00',
          },
        ],
      });
      expect(c.lineas.single.precioUnitario, 130);
      expect(c.lineas.single.subtotal, 130);
      expect(c.total, 130);
    });

    test('vacío y totales del backend como String o número', () {
      final c = CarritoCompra.fromJson({
        'id': 'car-1',
        'cliente_id': 'cli-1',
        'canal': 'MOVIL',
        'estado': 'ACTIVO',
        'lineas': [
          {
            'id': 'l1',
            'variante_id': 'v1',
            'cantidad': 2,
            'precio_unitario': '150.50',
            'descuento_unitario': 10,
            'promocion_id': null,
            'subtotal': '281.00',
          },
        ],
        'subtotal': '301.00',
        'descuento_total': '20.00',
        'total': 281,
      });
      expect(c.estaVacio, isFalse);
      expect(c.totalPrendas, 2);
      expect(c.lineas.first.precioUnitario, 150.50);
      expect(c.total, 281.0);
      expect(c.tieneDescuento, isTrue);
      expect(CarritoCompra.vacio().estaVacio, isTrue);
    });

    test('cobertura distingue sucursales que cubren', () {
      final cob = CoberturaCarrito.fromJson({
        'sucursales': [
          {
            'sucursal_id': 's1',
            'sucursal_nombre': 'Centro',
            'cubre_todo': true,
            'faltantes': [],
          },
          {
            'sucursal_id': 's2',
            'sucursal_nombre': 'Norte',
            'cubre_todo': false,
            'faltantes': ['v9'],
          },
        ],
      });
      expect(cob.queCubren.length, 1);
      expect(cob.queCubren.first.sucursalId, 's1');
    });
  });

  group('Checkout y venta', () {
    test('checkout recojo serializa sin dirección ni anillo', () {
      final c = CheckoutCrear(
        sucursalId: 's1',
        modalidad: ModalidadEntrega.recojo,
      );
      final j = c.toJson();
      expect(j['sucursal_id'], 's1');
      expect(j['canal'], 'MOVIL');
      expect(j.containsKey('direccion'), isFalse);
      expect(j.containsKey('anillo_destino'), isFalse);
    });

    test('checkout delivery incluye dirección y anillo', () {
      final c = CheckoutCrear(
        sucursalId: 's1',
        modalidad: ModalidadEntrega.delivery,
        direccion: 'Av. Siempre Viva 123',
        anilloDestino: 4,
      );
      expect(c.toJson()['anillo_destino'], 4);
      final r = CheckoutRespuesta.fromJson({
        'venta_id': 'v1',
        'numero': 'FS-0001',
        'estado': 'PENDIENTE_PAGO',
        'total': '320.75',
        'expira_en': '2026-09-21T12:00:00Z',
        'pedido_entrega_id': 'p1',
      });
      expect(r.total, 320.75);
      expect(r.expiraEn, isNotNull);
    });

    test('venta digital con costo de entrega String', () {
      final v = VentaDigital.fromJson({
        'id': 'v1',
        'numero': 'FS-0001',
        'sucursal_id': 's1',
        'canal': 'MOVIL',
        'estado': 'PENDIENTE_PAGO',
        'subtotal': '300',
        'descuento': '20',
        'adelanto_descontado': 0,
        'costo_entrega': '15.00',
        'total': 295,
        'detalles': [],
      });
      expect(v.estaPendiente, isTrue);
      expect(v.costoEntrega, 15.0);
      expect(v.totalPrendas, 0);
    });
  });

  group('Pago Stripe', () {
    test('estados pendiente/aprobado/rechazado/vencido', () {
      EstadoPagoVenta e(String pv, String pp) => EstadoPagoVenta.fromJson({
            'venta_id': 'v1',
            'estado_venta': pv,
            'estado_pago': pp,
            'monto': '100.00',
          });
      expect(resultadoDesdeEstado(e('PENDIENTE_PAGO', 'PENDIENTE')),
          ResultadoPago.pendiente);
      expect(resultadoDesdeEstado(e('PAGADA', 'APROBADO')),
          ResultadoPago.aprobado);
      expect(resultadoDesdeEstado(e('PENDIENTE_PAGO', 'RECHAZADO')),
          ResultadoPago.rechazado);
      expect(resultadoDesdeEstado(e('CANCELADA', 'ANULADO')),
          ResultadoPago.vencido);
    });

    test('intención con client_secret opcional', () {
      final i = IntencionStripe.fromJson({
        'payment_intent_id': 'pi_1',
        'venta_id': 'v1',
        'monto': 100,
        'moneda': 'BOB',
        'estado': 'REQUIERE_PAGO',
      });
      expect(i.clientSecret, isNull);
      expect(i.monto, 100.0);
    });
  });

  group('Entrega y pedidos', () {
    test('cotización con importes String', () {
      final c = CotizacionDelivery.fromJson({
        'sucursal_id': 's1',
        'anillo_sucursal': 2,
        'anillo_destino': 5,
        'tarifa_base': '15.00',
        'incremento_anillo': '3.00',
        'costo_entrega': 24,
      });
      expect(c.costoEntrega, 24.0);
      expect(c.tarifaBase, 15.0);
    });

    test('seguimiento recojo vs delivery', () {
      Pedido p(String mod, String est) => Pedido.fromJson({
            'id': 'p1',
            'venta_id': 'v1',
            'sucursal_id': 's1',
            'modalidad': mod,
            'estado': est,
            'tarifa_base': 15,
            'incremento_anillo': 3,
            'costo_entrega': 0,
            'puede_cancelar': false,
            'puede_transicionar': false,
          });
      final recojo = p('RECOJO', 'LISTO_RECOJO');
      expect(recojo.pasosSeguimiento,
          ['SOLICITADO', 'PREPARADO', 'LISTO_RECOJO', 'RECOGIDO']);
      expect(recojo.indicePaso, 2);
      expect(recojo.estaActivo, isTrue);
      final delivery = p('DELIVERY', 'ENTREGADO');
      expect(delivery.pasosSeguimiento.last, 'ENTREGADO');
      expect(delivery.estaCompletado, isTrue);
      expect(p('RECOJO', 'CANCELADO').estaCancelado, isTrue);
    });
  });

  group('IA cliente', () {
    test('recomendación vacía y con productos', () {
      final vacia = RecomendacionRespuesta.fromJson(
          {'items': [], 'proveedor': 'DETERMINISTA'});
      expect(vacia.estaVacia, isTrue);
      final llena = RecomendacionRespuesta.fromJson({
        'items': [
          {
            'producto_id': 'p1',
            'variante_id': 'v1',
            'nombre': 'Vestido',
            'precio': '199.99',
            'disponible': 3,
            'motivo': 'Temporada actual',
          },
        ],
        'proveedor': 'DETERMINISTA',
      });
      expect(llena.estaVacia, isFalse);
      expect(llena.items.first.precio, 199.99);
    });

    test('búsqueda escrita sin coincidencias', () {
      final b = InterpretacionBusqueda.fromJson(
          {'filtros': {}, 'total': 0, 'items': []});
      expect(b.sinCoincidencias, isTrue);
    });
  });

  group('Probador', () {
    test('recurso y autorización con constantes fijadas', () {
      final r = RecursoPruebaVirtual.fromJson({
        'variante_id': 'v1',
        'compatible': true,
        'imagen_prenda_url': 'https://x/prenda.webp',
        'prompt_prenda': 'Replace top',
        'proveedor': 'DECART',
        'modelo': 'lucy-2.5',
        'aviso_orientativo': 'orientativo',
      });
      expect(r.compatible, isTrue);
      expect(r.modelo, modeloDecartFijado);
      final a = AutorizacionDecart.fromJson({
        'client_token': 'tok',
        'expires_at': DateTime.now()
            .toUtc()
            .add(const Duration(seconds: 60))
            .toIso8601String(),
        'modelo': 'lucy-2.5',
        'max_session_duration_seconds': 120,
        'imagen_prenda_url': 'https://x/prenda.webp',
        'prompt_prenda': 'Replace top',
      });
      expect(a.tokenVencido, isFalse);
      expect(a.duracionMaximaSegundos, duracionMaximaProbadorSegundos);
      expect(consentimientoDecartVigente, 'decart-v1');
      expect(avisoProbadorPermanente, contains('orientativa'));
    });

    test('token vencido se detecta', () {
      final a = AutorizacionDecart.fromJson({
        'client_token': 'tok',
        'expires_at': '2020-01-01T00:00:00Z',
        'modelo': 'lucy-2.5',
        'max_session_duration_seconds': 120,
        'imagen_prenda_url': 'https://x/p.webp',
        'prompt_prenda': 'p',
      });
      expect(a.tokenVencido, isTrue);
    });
  });
}
