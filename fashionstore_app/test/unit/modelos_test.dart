import 'package:fashionstore_movil/features/catalogo/models/catalogo_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/compra_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/models/reserva_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/models/traslado_model.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Producto fromJson/toJson conserva contrato', () {
    final json = {
      'id': '11111111-1111-1111-1111-111111111111',
      'categoria_id': null,
      'nombre': 'Camisa Clásica',
      'descripcion': 'Algodón',
      'genero': 'HOMBRE',
      'marca': 'FashionStore',
      'precio_base': '120.00',
      'activo': true,
      'imagenes': [
        {
          'id': '22222222-2222-2222-2222-222222222222',
          'producto_id': '11111111-1111-1111-1111-111111111111',
          'enlace_imagen': 'https://cdn.test/camisa.jpg',
          'orden': 0,
          'es_principal': true,
        }
      ],
      'temporada_ids': [],
      'coleccion_ids': [],
    };
    final p = Producto.fromJson(json);
    expect(p.nombre, 'Camisa Clásica');
    expect(p.precioBase, 120.0);
    expect(p.imagenPrincipal, 'https://cdn.test/camisa.jpg');
    final out = p.toJson();
    expect(out['nombre'], 'Camisa Clásica');
  });

  test('Disponibilidad fromJson conserva cantidades separadas', () {
    final json = {
      'inventario_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      'variante_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      'sucursal_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
      'sucursal_nombre': 'Sucursal Centro',
      'ciudad_id': 'dddddddd-dddd-dddd-dddd-dddddddddddd',
      'ciudad_nombre': 'Santa Cruz',
      'direccion': 'Av Principal 123',
      'telefono': '+591 70000000',
      'disponible': 15,
      'reservado': 3,
      'comprometido_traslado': 2,
      'en_transito': 1,
      'actualizado_en': '2026-09-01T12:00:00Z',
    };
    final d = DisponibilidadSucursal.fromJson(json);
    expect(d.disponible, 15);
    expect(d.reservado, 3);
    expect(d.comprometidoTraslado, 2);
    expect(d.enTransito, 1);
    expect(d.toJson()['sucursal_nombre'], 'Sucursal Centro');
  });

  test('FiltrosOpciones fromJson conserva listas', () {
    final json = {
      'categorias': [
        {'id': '11111111-1111-1111-1111-111111111111', 'nombre': 'Camisas'}
      ],
      'tallas': [
        {
          'id': '22222222-2222-2222-2222-222222222222',
          'nombre': 'M',
          'orden': 2
        }
      ],
      'colores': [
        {
          'id': '33333333-3333-3333-3333-333333333333',
          'nombre': 'Rojo',
          'codigo_hex': '#FF0000'
        }
      ],
      'temporadas': [],
      'colecciones': [],
      'generos': ['HOMBRE'],
      'marcas': ['FashionStore'],
    };
    final f = FiltrosOpciones.fromJson(json);
    expect(f.categorias.first.nombre, 'Camisas');
    expect(f.colores.first.codigoHex, '#FF0000');
    expect(f.generos, ['HOMBRE']);
  });

  test('Reserva fromJson: código, vigencia y estados', () {
    final json = {
      'id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      'cliente_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      'sucursal_destino_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
      'codigo': 'FS-ABC123',
      'estado': 'PENDIENTE',
      'fecha_creacion': '2026-09-15T10:00:00Z',
      'vence_en': '2026-09-16T10:00:00Z',
      'detalles': [
        {
          'id': 'dddddddd-dddd-dddd-dddd-dddddddddddd',
          'variante_id': 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
          'cantidad_solicitada': 2,
          'cantidad_reservada': 2,
          'cantidad_pendiente_traslado': 0,
          'cantidad_vendida': 0,
          'cantidad_liberada': 0,
          'estado_linea': 'RESERVADA',
        }
      ],
      'traslados': [],
    };
    final r = Reserva.fromJson(json);
    expect(r.codigo, 'FS-ABC123');
    expect(r.estadoLegible, 'Lista para preparar');
    expect(r.permiteCancelar, isTrue);
    expect(r.totalPrendas, 2);
  });

  test('Traslado fromJson: estado legible', () {
    final json = {
      'id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      'reserva_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      'sucursal_origen_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
      'sucursal_destino_id': 'dddddddd-dddd-dddd-dddd-dddddddddddd',
      'estado': 'DESPACHADO',
      'solicitado_por_id': 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
      'fecha_solicitud': '2026-09-15T10:00:00Z',
      'detalles': [],
    };
    final t = Traslado.fromJson(json);
    expect(t.estadoLegible, 'En camino');
  });

  test('Compra fromJson: totales', () {
    final json = {
      'id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
      'numero': 'V-0001',
      'sucursal_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
      'canal': 'PRESENCIAL',
      'estado': 'PAGADA',
      'subtotal': '200.00',
      'descuento': '0.00',
      'total': '200.00',
      'creada_en': '2026-09-10T10:00:00Z',
      'detalles': [
        {
          'id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
          'variante_id': 'dddddddd-dddd-dddd-dddd-dddddddddddd',
          'cantidad': 2,
          'precio_unitario': '100.00',
          'descuento': '0.00',
        }
      ],
    };
    final c = Compra.fromJson(json);
    expect(c.numero, 'V-0001');
    expect(c.total, 200.0);
    expect(c.totalPrendas, 2);
  });
}
