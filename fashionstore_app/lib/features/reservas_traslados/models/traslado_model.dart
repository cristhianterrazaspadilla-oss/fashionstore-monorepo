// Modelos de traslados (contrato real GET /traslados y POST /traslados/solicitudes).

DateTime? _aFecha(dynamic v) {
  if (v == null) return null;
  if (v is DateTime) return v;
  return DateTime.tryParse(v.toString());
}

class DetalleTraslado {
  final String id;
  final String trasladoId;
  final String? detalleReservaId;
  final String varianteId;
  final int cantidad;

  DetalleTraslado({
    required this.id,
    required this.trasladoId,
    this.detalleReservaId,
    required this.varianteId,
    required this.cantidad,
  });

  factory DetalleTraslado.fromJson(Map<String, dynamic> j) => DetalleTraslado(
        id: '${j['id'] ?? ''}',
        trasladoId: '${j['traslado_id'] ?? ''}',
        detalleReservaId: j['detalle_reserva_id']?.toString(),
        varianteId: '${j['variante_id'] ?? ''}',
        cantidad: (j['cantidad'] as num?)?.toInt() ?? 0,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'traslado_id': trasladoId,
        'detalle_reserva_id': detalleReservaId,
        'variante_id': varianteId,
        'cantidad': cantidad,
      };
}

class Traslado {
  final String id;
  final String? reservaId;
  final String origenId;
  final String destinoId;
  final String estado;
  final DateTime? fechaSolicitud;
  final DateTime? fechaAprobacion;
  final DateTime? fechaDespacho;
  final DateTime? fechaRecepcion;
  final String? motivoRechazo;
  final List<DetalleTraslado> detalles;

  Traslado({
    required this.id,
    this.reservaId,
    required this.origenId,
    required this.destinoId,
    required this.estado,
    this.fechaSolicitud,
    this.fechaAprobacion,
    this.fechaDespacho,
    this.fechaRecepcion,
    this.motivoRechazo,
    required this.detalles,
  });

  factory Traslado.fromJson(Map<String, dynamic> j) => Traslado(
        id: '${j['id'] ?? ''}',
        reservaId: j['reserva_id']?.toString(),
        origenId: '${j['sucursal_origen_id'] ?? ''}',
        destinoId: '${j['sucursal_destino_id'] ?? ''}',
        estado: '${j['estado'] ?? ''}',
        fechaSolicitud: _aFecha(j['fecha_solicitud']),
        fechaAprobacion: _aFecha(j['fecha_aprobacion']),
        fechaDespacho: _aFecha(j['fecha_despacho']),
        fechaRecepcion: _aFecha(j['fecha_recepcion']),
        motivoRechazo: j['motivo_rechazo'] as String?,
        detalles: ((j['detalles'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => DetalleTraslado.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'reserva_id': reservaId,
        'sucursal_origen_id': origenId,
        'sucursal_destino_id': destinoId,
        'estado': estado,
        'fecha_solicitud': fechaSolicitud?.toIso8601String(),
        'fecha_aprobacion': fechaAprobacion?.toIso8601String(),
        'fecha_despacho': fechaDespacho?.toIso8601String(),
        'fecha_recepcion': fechaRecepcion?.toIso8601String(),
        'motivo_rechazo': motivoRechazo,
        'detalles': detalles.map((e) => e.toJson()).toList(),
      };

  String get estadoLegible {
    switch (estado) {
      case 'SOLICITADO':
        return 'Solicitado';
      case 'APROBADO':
        return 'Aprobado en origen';
      case 'DESPACHADO':
        return 'En camino';
      case 'RECIBIDO':
        return 'Recibido en destino';
      case 'RECHAZADO':
        return 'Rechazado';
      default:
        return estado.isEmpty ? 'En proceso' : estado;
    }
  }
}

class TrasladoLista {
  final int total;
  final int limit;
  final int offset;
  final List<Traslado> items;

  TrasladoLista({
    required this.total,
    required this.limit,
    required this.offset,
    required this.items,
  });

  factory TrasladoLista.fromJson(Map<String, dynamic> j) => TrasladoLista(
        total: (j['total'] as num?)?.toInt() ?? 0,
        limit: (j['limit'] as num?)?.toInt() ?? 0,
        offset: (j['offset'] as num?)?.toInt() ?? 0,
        items: ((j['items'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => Traslado.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'total': total,
        'limit': limit,
        'offset': offset,
        'items': items.map((e) => e.toJson()).toList(),
      };
}
