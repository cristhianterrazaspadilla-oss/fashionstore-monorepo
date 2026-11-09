import 'package:fashionstore_movil/features/reservas_traslados/models/reserva_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/bolsa_store.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Bolsa multiítem: agregar, acumular, cambiar y quitar', () {
    final bolsa = BolsaStore.paraPruebas();
    bolsa.limpiar();
    bolsa.agregar(
        varianteId: 'v1', nombrePrenda: 'Camisa', sku: 'SKU-1', precio: 100);
    bolsa.agregar(
        varianteId: 'v2', nombrePrenda: 'Pantalón', sku: 'SKU-2', precio: 200);
    expect(bolsa.items.length, 2);
    expect(bolsa.totalPrendas, 2);

    bolsa.agregar(
        varianteId: 'v1',
        nombrePrenda: 'Camisa',
        sku: 'SKU-1',
        precio: 100,
        cantidad: 2);
    expect(bolsa.totalPrendas, 4);
    expect(bolsa.totalEstimado, 100 * 3 + 200);

    bolsa.cambiarCantidad('v1', 1);
    expect(bolsa.totalPrendas, 2);

    bolsa.definirOrigen('v2', 'origen-1', 'Sucursal Norte');
    expect(bolsa.items.last.necesitaTraslado, isTrue);

    bolsa.quitar('v1');
    expect(bolsa.items.length, 1);
    bolsa.limpiar();
    expect(bolsa.vacia, isTrue);
  });

  test('Acciones permitidas por estado de reserva', () {
    expect(AccionesReserva.puedeCancelar('PENDIENTE'), isTrue);
    expect(AccionesReserva.puedeCancelar('PENDIENTE_TRASLADO'), isTrue);
    expect(AccionesReserva.puedeCancelar('PREPARADA'), isTrue);
    expect(AccionesReserva.puedeCancelar('ATENDIDA'), isFalse);
    expect(AccionesReserva.puedeCancelar('COMPLETADA'), isFalse);
    expect(AccionesReserva.puedeCancelar('CANCELADA'), isFalse);
    expect(AccionesReserva.puedeCancelar('VENCIDA'), isFalse);

    expect(
      AccionesReserva.puedeReintentarLinea(
          estadoReserva: 'PENDIENTE_TRASLADO', estadoLinea: 'RECHAZADA'),
      isTrue,
    );
    expect(
      AccionesReserva.puedeReintentarLinea(
          estadoReserva: 'CANCELADA', estadoLinea: 'RECHAZADA'),
      isFalse,
    );
    expect(
      AccionesReserva.puedeReintentarLinea(
          estadoReserva: 'PENDIENTE', estadoLinea: 'RESERVADA'),
      isFalse,
    );
  });
}
