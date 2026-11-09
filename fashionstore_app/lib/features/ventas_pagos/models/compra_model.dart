// Historial de compras (contrato real GET /clientes/{id}/compras).

DateTime? _aFecha(dynamic v) {
  if (v == null) return null;
  if (v is DateTime) return v;
  return DateTime.tryParse(v.toString());
}

double _aDouble(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? 0;
}

class DetalleCompra {
  final String id;
  final String varianteId;
  final int cantidad;
  final double precioUnitario;
  final double descuento;

  DetalleCompra({
    required this.id,
    required this.varianteId,
    required this.cantidad,
    required this.precioUnitario,
    required this.descuento,
  });

  factory DetalleCompra.fromJson(Map<String, dynamic> j) => DetalleCompra(
        id: '${j['id'] ?? ''}',
        varianteId: '${j['variante_id'] ?? ''}',
        cantidad: (j['cantidad'] as num?)?.toInt() ?? 0,
        precioUnitario: _aDouble(j['precio_unitario']),
        descuento: _aDouble(j['descuento']),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'variante_id': varianteId,
        'cantidad': cantidad,
        'precio_unitario': precioUnitario,
        'descuento': descuento,
      };
}

class Compra {
  final String id;
  final String numero;
  final String? reservaId;
  final String sucursalId;
  final String canal;
  final String estado;
  final double subtotal;
  final double descuento;
  final double total;
  final DateTime? creadaEn;
  final List<DetalleCompra> detalles;

  Compra({
    required this.id,
    required this.numero,
    this.reservaId,
    required this.sucursalId,
    required this.canal,
    required this.estado,
    required this.subtotal,
    required this.descuento,
    required this.total,
    this.creadaEn,
    required this.detalles,
  });

  factory Compra.fromJson(Map<String, dynamic> j) => Compra(
        id: '${j['id'] ?? ''}',
        numero: '${j['numero'] ?? ''}',
        reservaId: j['reserva_id']?.toString(),
        sucursalId: '${j['sucursal_id'] ?? ''}',
        canal: '${j['canal'] ?? ''}',
        estado: '${j['estado'] ?? ''}',
        subtotal: _aDouble(j['subtotal']),
        descuento: _aDouble(j['descuento']),
        total: _aDouble(j['total']),
        creadaEn: _aFecha(j['creada_en']),
        detalles: ((j['detalles'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => DetalleCompra.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'numero': numero,
        'reserva_id': reservaId,
        'sucursal_id': sucursalId,
        'canal': canal,
        'estado': estado,
        'subtotal': subtotal,
        'descuento': descuento,
        'total': total,
        'creada_en': creadaEn?.toIso8601String(),
        'detalles': detalles.map((e) => e.toJson()).toList(),
      };

  int get totalPrendas => detalles.fold(0, (a, d) => a + d.cantidad);
}

class HistorialCompras {
  final int total;
  final int limit;
  final int offset;
  final List<Compra> items;

  HistorialCompras({
    required this.total,
    required this.limit,
    required this.offset,
    required this.items,
  });

  factory HistorialCompras.fromJson(Map<String, dynamic> j) => HistorialCompras(
        total: (j['total'] as num?)?.toInt() ?? 0,
        limit: (j['limit'] as num?)?.toInt() ?? 0,
        offset: (j['offset'] as num?)?.toInt() ?? 0,
        items: ((j['items'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => Compra.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'total': total,
        'limit': limit,
        'offset': offset,
        'items': items.map((e) => e.toJson()).toList(),
      };
}
