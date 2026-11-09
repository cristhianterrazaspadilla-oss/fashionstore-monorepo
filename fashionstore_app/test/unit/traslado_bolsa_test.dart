import 'package:fashionstore_movil/features/catalogo/models/catalogo_model.dart';
import 'package:fashionstore_movil/features/organizacion/models/organizacion_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/models/reserva_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/bolsa_store.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/origen_helper.dart';
import 'package:flutter_test/flutter_test.dart';

SucursalModel _sucursal(String id, [String nombre = 'Sucursal']) =>
    SucursalModel(
      id: id,
      ciudadId: 'ciudad-1',
      ciudadNombre: 'Santa Cruz',
      nombre: nombre,
      direccion: 'Av. Principal 123',
      tarifaBaseDelivery: 0,
      incrementoAnilloDelivery: 0,
      anilloMinimoDelivery: 1,
      anilloMaximoDelivery: 10,
      deliveryActivo: false,
      activa: true,
    );

DisponibilidadSucursal _disp(String sucursalId, int disponible) =>
    DisponibilidadSucursal(
      inventarioId: 'inv-$sucursalId',
      varianteId: 'v-1',
      sucursalId: sucursalId,
      sucursalNombre: 'Sucursal $sucursalId',
      ciudadId: 'ciudad-1',
      ciudadNombre: 'Santa Cruz',
      disponible: disponible,
      reservado: 0,
      comprometidoTraslado: 0,
      enTransito: 0,
    );

Reserva _reservaTerminada(String estado) => Reserva(
      id: 'r-1',
      clienteId: 'c-1',
      sucursalDestinoId: 'dest-1',
      codigo: 'FS-ABC123',
      estado: estado,
      detalles: [
        DetalleReserva(
          id: 'd-1',
          varianteId: 'v-1',
          cantidadSolicitada: 2,
          cantidadReservada: 0,
          cantidadPendienteTraslado: 2,
          cantidadVendida: 0,
          cantidadLiberada: 0,
          estadoLinea: 'PENDIENTE_TRASLADO',
        ),
      ],
      traslados: [
        TrasladoResumen(
            id: 't-1',
            origenId: 'origen-1',
            destinoId: 'dest-1',
            estado: 'DESPACHADO'),
      ],
    );

void main() {
  test('marcar traslado mantiene visible el selector aunque no haya origen',
      () {
    final item = ItemBolsa(
      varianteId: 'v-1',
      nombrePrenda: 'Camisa',
      sku: 'SKU-1',
      precio: 100,
    );
    expect(item.solicitaTraslado, isFalse);
    expect(item.necesitaTraslado, isFalse);

    item.fijarSolicitudTraslado(true);

    // La visibilidad depende de solicitaTraslado, no del origen.
    expect(item.necesitaTraslado, isTrue);
    expect(item.tieneOrigenValido, isFalse);
    expect(item.bloqueaConfirmacion, isTrue);
  });

  test('no confirma sin origen cuando se solicita traslado', () {
    final bolsa = BolsaStore.paraPruebas();
    bolsa.limpiar();
    bolsa.agregar(
        varianteId: 'v-1', nombrePrenda: 'Camisa', sku: 'SKU-1', precio: 100);
    bolsa.solicitarTraslado('v-1', true);

    expect(bolsa.puedeConfirmar, isFalse);
    expect(bolsa.lineasSinOrigen.length, 1);

    bolsa.definirOrigen('v-1', 'origen-1', 'Sucursal Norte');
    expect(bolsa.puedeConfirmar, isTrue);
  });

  test('desmarcar traslado limpia el origen', () {
    final bolsa = BolsaStore.paraPruebas();
    bolsa.limpiar();
    bolsa.agregar(
        varianteId: 'v-1', nombrePrenda: 'Camisa', sku: 'SKU-1', precio: 100);
    bolsa.solicitarTraslado('v-1', true);
    bolsa.definirOrigen('v-1', 'origen-1', 'Sucursal Norte');
    expect(bolsa.items.single.tieneOrigenValido, isTrue);

    bolsa.solicitarTraslado('v-1', false);

    final item = bolsa.items.single;
    expect(item.solicitaTraslado, isFalse);
    expect(item.origenId, isNull);
    expect(item.origenNombre, isNull);
    expect(bolsa.puedeConfirmar, isTrue);
  });

  test('no serializa sucursal_origen_id vacío', () {
    final sinOrigen = ItemBolsa(
      varianteId: 'v-1',
      nombrePrenda: 'Camisa',
      sku: 'SKU-1',
      precio: 100,
      cantidad: 2,
      solicitaTraslado: true,
    );
    expect(sinOrigen.toJson().containsKey('sucursal_origen_id'), isFalse);

    final conVacio = ItemBolsa(
      varianteId: 'v-1',
      nombrePrenda: 'Camisa',
      sku: 'SKU-1',
      precio: 100,
      solicitaTraslado: true,
      origenId: '   ',
    );
    expect(conVacio.toJson().containsKey('sucursal_origen_id'), isFalse);

    final local = ItemBolsa(
      varianteId: 'v-1',
      nombrePrenda: 'Camisa',
      sku: 'SKU-1',
      precio: 100,
    );
    expect(local.toJson(), {'variante_id': 'v-1', 'cantidad': 1});

    final conOrigen = ItemBolsa(
      varianteId: 'v-1',
      nombrePrenda: 'Camisa',
      sku: 'SKU-1',
      precio: 100,
      cantidad: 2,
      solicitaTraslado: true,
      origenId: 'origen-1',
    );
    expect(conOrigen.toJson()['sucursal_origen_id'], 'origen-1');
  });

  test('reserva local no envía origen', () {
    final bolsa = BolsaStore.paraPruebas();
    bolsa.limpiar();
    bolsa.agregar(
        varianteId: 'v-1',
        nombrePrenda: 'Camisa',
        sku: 'SKU-1',
        precio: 100,
        cantidad: 2);
    final json = bolsa.items.single.toJson();
    expect(json.containsKey('sucursal_origen_id'), isFalse);
    expect(bolsa.puedeConfirmar, isTrue);
  });

  test('cambio de destino invalida origen incompatible', () {
    final bolsa = BolsaStore.paraPruebas();
    bolsa.limpiar();
    bolsa.agregar(
        varianteId: 'v-1', nombrePrenda: 'Camisa', sku: 'SKU-1', precio: 100);
    bolsa.solicitarTraslado('v-1', true);
    bolsa.definirOrigen('v-1', 'suc-b', 'Sucursal Sur');
    expect(bolsa.puedeConfirmar, isTrue);

    bolsa.alCambiarDestino('suc-b');

    final item = bolsa.items.single;
    // El origen que coincide con el nuevo destino se descarta, pero la
    // solicitud de traslado se conserva (el selector sigue visible).
    expect(item.origenId, isNull);
    expect(item.solicitaTraslado, isTrue);
    expect(item.bloqueaConfirmacion, isTrue);

    // Cambiar a un destino distinto no toca el origen válido.
    bolsa.definirOrigen('v-1', 'suc-b', 'Sucursal Sur');
    bolsa.alCambiarDestino('suc-a');
    expect(bolsa.items.single.origenId, 'suc-b');
  });

  test('filtra orígenes sin stock suficiente', () {
    final sucs = [_sucursal('dest'), _sucursal('a'), _sucursal('b')];
    final disp = [_disp('dest', 0), _disp('a', 5), _disp('b', 1)];

    final opciones = origenesValidosParaLinea(
      disponibilidad: disp,
      sucursales: sucs,
      destinoId: 'dest',
      cantidadNecesaria: 2,
    );

    // Solo 'a' tiene 2 o más; el destino y 'b' (1 unidad) quedan fuera.
    expect(opciones.map((e) => e.sucursal.id), ['a']);
  });

  test('orígenes excluyen destino y origen rechazado, ordenan por stock', () {
    final sucs = [_sucursal('dest'), _sucursal('a'), _sucursal('b')];
    final disp = [_disp('dest', 9), _disp('a', 2), _disp('b', 4)];

    final opciones = origenesValidosParaLinea(
      disponibilidad: disp,
      sucursales: sucs,
      destinoId: 'dest',
      cantidadNecesaria: 2,
      excluirOrigenId: 'b',
    );

    expect(opciones.map((e) => e.sucursal.id), ['a']);

    final sinExclusion = origenesValidosParaLinea(
      disponibilidad: disp,
      sucursales: sucs,
      destinoId: 'dest',
      cantidadNecesaria: 2,
    );
    // Ordenados de mayor a menor disponibilidad.
    expect(sinExclusion.map((e) => e.sucursal.id).toList(), ['b', 'a']);
  });

  test('destino con stock suficiente usa reserva local', () {
    expect(disponibleEnDestino([_disp('dest', 3)], 'dest'), 3);
    expect(
      necesitaOrigenParaLinea(disponibleDestino: 3, cantidadSolicitada: 2),
      isFalse,
    );
    expect(
      necesitaOrigenParaLinea(disponibleDestino: 1, cantidadSolicitada: 2),
      isTrue,
    );
  });

  test('traslados visibles en reserva cancelada o vencida', () {
    for (final estado in ['CANCELADA', 'VENCIDA']) {
      // Con traslados en la respuesta.
      expect(
        AccionesReserva.puedeVerTraslados(estado, tieneTraslados: true),
        isTrue,
      );
      // Con líneas relacionadas con traslado.
      expect(
        AccionesReserva.puedeVerTraslados(estado, tieneLineasTraslado: true),
        isTrue,
      );
      // Por estado histórico (pudo existir traslado).
      expect(AccionesReserva.puedeVerTraslados(estado), isTrue);
      // Seguimiento histórico de sólo lectura.
      expect(
        AccionesReserva.admiteSeguimientoHistorico(_reservaTerminada(estado)),
        isTrue,
      );
    }
    // Sin evidencia ni estado histórico no se muestra.
    expect(AccionesReserva.puedeVerTraslados('DESCONOCIDO'), isFalse);
  });
}
