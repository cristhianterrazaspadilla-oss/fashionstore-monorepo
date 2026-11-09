// Modelos de reservas (contrato real POST/GET /reservas y adaptadores CU18).

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

class DetalleReserva {
  final String id;
  final String varianteId;
  final int cantidadSolicitada;
  final int cantidadReservada;
  final int cantidadPendienteTraslado;
  final int cantidadVendida;
  final int cantidadLiberada;
  final String estadoLinea;

  DetalleReserva({
    required this.id,
    required this.varianteId,
    required this.cantidadSolicitada,
    required this.cantidadReservada,
    required this.cantidadPendienteTraslado,
    required this.cantidadVendida,
    required this.cantidadLiberada,
    required this.estadoLinea,
  });

  factory DetalleReserva.fromJson(Map<String, dynamic> j) => DetalleReserva(
        id: '${j['id'] ?? ''}',
        varianteId: '${j['variante_id'] ?? ''}',
        cantidadSolicitada: (j['cantidad_solicitada'] as num?)?.toInt() ?? 0,
        cantidadReservada: (j['cantidad_reservada'] as num?)?.toInt() ?? 0,
        cantidadPendienteTraslado:
            (j['cantidad_pendiente_traslado'] as num?)?.toInt() ?? 0,
        cantidadVendida: (j['cantidad_vendida'] as num?)?.toInt() ?? 0,
        cantidadLiberada: (j['cantidad_liberada'] as num?)?.toInt() ?? 0,
        estadoLinea: '${j['estado_linea'] ?? ''}',
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'variante_id': varianteId,
        'cantidad_solicitada': cantidadSolicitada,
        'cantidad_reservada': cantidadReservada,
        'cantidad_pendiente_traslado': cantidadPendienteTraslado,
        'cantidad_vendida': cantidadVendida,
        'cantidad_liberada': cantidadLiberada,
        'estado_linea': estadoLinea,
      };

  bool get estaRechazada => estadoLinea == 'RECHAZADA';
  bool get esperaTraslado => estadoLinea == 'PENDIENTE_TRASLADO';

  String get estadoLegible {
    switch (estadoLinea) {
      case 'RESERVADA':
        return 'Apartada';
      case 'PENDIENTE_TRASLADO':
        return 'Esperando traslado';
      case 'RECHAZADA':
        return 'Rechazada';
      case 'VENDIDA':
        return 'Comprada';
      case 'VENDIDA_PARCIAL':
        return 'Comprada en parte';
      case 'LIBERADA':
        return 'Liberada';
      default:
        return estadoLinea.isEmpty ? 'En proceso' : estadoLinea;
    }
  }
}

class TrasladoResumen {
  final String id;
  final String origenId;
  final String destinoId;
  final String estado;

  TrasladoResumen({
    required this.id,
    required this.origenId,
    required this.destinoId,
    required this.estado,
  });

  factory TrasladoResumen.fromJson(Map<String, dynamic> j) => TrasladoResumen(
        id: '${j['id'] ?? ''}',
        origenId: '${j['sucursal_origen_id'] ?? ''}',
        destinoId: '${j['sucursal_destino_id'] ?? ''}',
        estado: '${j['estado'] ?? ''}',
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'sucursal_origen_id': origenId,
        'sucursal_destino_id': destinoId,
        'estado': estado,
      };
}

class Reserva {
  final String id;
  final String? empresaId;
  final String clienteId;
  final String sucursalDestinoId;
  final String codigo;
  final String estado;
  final int revision;
  final DateTime? creadaEn;
  final DateTime? origenPlazoEn;
  final DateTime? fechaVisita;
  final DateTime? venceEn;
  final String? observacion;
  final String? adelantoMonto;
  final String? operacionSincronizacionId;
  final List<DetalleReserva> detalles;
  final List<TrasladoResumen> traslados;

  Reserva({
    required this.id,
    this.empresaId,
    required this.clienteId,
    required this.sucursalDestinoId,
    required this.codigo,
    required this.estado,
    this.revision = 1,
    this.creadaEn,
    this.origenPlazoEn,
    this.fechaVisita,
    this.venceEn,
    this.observacion,
    this.adelantoMonto,
    this.operacionSincronizacionId,
    required this.detalles,
    required this.traslados,
  });

  factory Reserva.fromJson(Map<String, dynamic> j) => Reserva(
        id: '${j['id'] ?? ''}',
        empresaId: j['empresa_id']?.toString(),
        clienteId: '${j['cliente_id'] ?? ''}',
        sucursalDestinoId: '${j['sucursal_destino_id'] ?? ''}',
        codigo: '${j['codigo'] ?? ''}',
        estado: '${j['estado'] ?? ''}',
        revision: (j['revision'] as num?)?.toInt() ?? 1,
        creadaEn: _aFecha(j['fecha_creacion']),
        origenPlazoEn: _aFecha(j['origen_plazo_en']),
        fechaVisita: _aFecha(j['fecha_visita']),
        venceEn: _aFecha(j['vence_en']),
        observacion: j['observacion'] as String?,
        adelantoMonto: j['adelanto_monto']?.toString(),
        operacionSincronizacionId: j['operacion_sincronizacion_id']?.toString(),
        detalles: ((j['detalles'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => DetalleReserva.fromJson(e.cast<String, dynamic>()))
            .toList(),
        traslados: ((j['traslados'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => TrasladoResumen.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        if (empresaId != null) 'empresa_id': empresaId,
        'cliente_id': clienteId,
        'sucursal_destino_id': sucursalDestinoId,
        'codigo': codigo,
        'estado': estado,
        'revision': revision,
        'fecha_creacion': creadaEn?.toIso8601String(),
        if (origenPlazoEn != null)
          'origen_plazo_en': origenPlazoEn?.toIso8601String(),
        'fecha_visita': fechaVisita?.toIso8601String(),
        'vence_en': venceEn?.toIso8601String(),
        'observacion': observacion,
        if (adelantoMonto != null) 'adelanto_monto': adelantoMonto,
        if (operacionSincronizacionId != null)
          'operacion_sincronizacion_id': operacionSincronizacionId,
        'detalles': detalles.map((e) => e.toJson()).toList(),
        'traslados': traslados.map((e) => e.toJson()).toList(),
      };

  bool get esOrigenOffline =>
      operacionSincronizacionId != null &&
      operacionSincronizacionId!.isNotEmpty;

  bool get tieneAdelanto =>
      adelantoMonto != null && adelantoMonto!.isNotEmpty;

  /// Texto comprensible del estado (sin códigos internos).
  String get estadoLegible {
    switch (estado) {
      case 'PENDIENTE_TRASLADO':
        return 'Esperando traslado';
      case 'PENDIENTE':
        return 'Lista para preparar';
      case 'PREPARADA':
        return 'Lista para tu visita';
      case 'ATENDIDA':
        return 'En atención en tienda';
      case 'COMPLETADA':
        return 'Completada';
      case 'CANCELADA':
        return 'Cancelada';
      case 'VENCIDA':
        return 'Vencida';
      default:
        return estado.isEmpty ? 'En proceso' : estado;
    }
  }

  /// La app solo permite cancelar en estos estados (regla del backend).
  bool get permiteCancelar =>
      estado == 'PENDIENTE_TRASLADO' ||
      estado == 'PENDIENTE' ||
      estado == 'PREPARADA';

  List<DetalleReserva> get lineasRechazadas =>
      detalles.where((d) => d.estaRechazada).toList();

  int get totalPrendas => detalles.fold(0, (a, d) => a + d.cantidadSolicitada);
}

class ReservaLista {
  final int total;
  final int limit;
  final int offset;
  final List<Reserva> items;

  ReservaLista({
    required this.total,
    required this.limit,
    required this.offset,
    required this.items,
  });

  factory ReservaLista.fromJson(Map<String, dynamic> j) => ReservaLista(
        total: (j['total'] as num?)?.toInt() ?? 0,
        limit: (j['limit'] as num?)?.toInt() ?? 0,
        offset: (j['offset'] as num?)?.toInt() ?? 0,
        items: ((j['items'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => Reserva.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'total': total,
        'limit': limit,
        'offset': offset,
        'items': items.map((e) => e.toJson()).toList(),
      };
}

/// Calcula las acciones permitidas por estado (para UI y pruebas).
class AccionesReserva {
  static bool puedeCancelar(String estado) =>
      estado == 'PENDIENTE_TRASLADO' ||
      estado == 'PENDIENTE' ||
      estado == 'PREPARADA';

  static bool puedeReintentarLinea({
    required String estadoReserva,
    required String estadoLinea,
  }) {
    if (estadoLinea != 'RECHAZADA') return false;
    // No tiene sentido reintentar si la reserva ya terminó.
    if (estadoReserva == 'CANCELADA' ||
        estadoReserva == 'VENCIDA' ||
        estadoReserva == 'COMPLETADA') {
      return false;
    }
    return true;
  }

  /// Seguimiento de traslados como información de sólo lectura.
  ///
  /// No se oculta en reservas CANCELADA/VENCIDA: un traslado despachado
  /// puede seguir en tránsito hasta destino después del cierre de la
  /// reserva (RN-02/RN-04). Por eso, además del estado, se aceptan
  /// evidencias directas ([tieneTraslados] o [tieneLineasTraslado]).
  static bool puedeVerTraslados(
    String estado, {
    bool tieneTraslados = false,
    bool tieneLineasTraslado = false,
  }) {
    if (tieneTraslados || tieneLineasTraslado) return true;
    switch (estado) {
      case 'PENDIENTE_TRASLADO':
      case 'PENDIENTE':
      case 'PREPARADA':
      case 'ATENDIDA':
      case 'COMPLETADA':
      case 'CANCELADA':
      case 'VENCIDA':
        return true;
      default:
        return false;
    }
  }

  /// Indica si una reserva admite consulta de seguimiento aunque haya
  /// terminado (traslados en tránsito tras cancelación/vencimiento).
  static bool admiteSeguimientoHistorico(Reserva reserva) {
    if (reserva.traslados.isNotEmpty) return true;
    for (final d in reserva.detalles) {
      if (d.esperaTraslado ||
          d.estaRechazada ||
          d.cantidadPendienteTraslado > 0) {
        return true;
      }
    }
    return puedeVerTraslados(reserva.estado);
  }
}

/// Ítem local de la bolsa antes de confirmar.
class ItemBolsa {
  final String varianteId;
  final String nombrePrenda;
  final String sku;
  final double precio;
  int cantidad;
  bool solicitaTraslado;
  String? origenId;
  String? origenNombre;

  ItemBolsa({
    required this.varianteId,
    required this.nombrePrenda,
    required this.sku,
    required this.precio,
    this.cantidad = 1,
    this.solicitaTraslado = false,
    this.origenId,
    this.origenNombre,
  });

  /// true si el usuario marcó que esta línea llegará por traslado.
  bool get necesitaTraslado => solicitaTraslado;

  /// Origen con valor real (no nulo ni vacío).
  bool get tieneOrigenValido => origenId != null && origenId!.trim().isNotEmpty;

  /// Bloquea la confirmación: pide traslado pero aún no eligió origen.
  bool get bloqueaConfirmacion => solicitaTraslado && !tieneOrigenValido;

  /// Marca o desmarca el traslado. Al desmarcar se limpia el origen.
  void fijarSolicitudTraslado(bool value) {
    solicitaTraslado = value;
    if (!value) {
      origenId = null;
      origenNombre = null;
    }
  }

  /// Serialización al contrato POST /reservas.
  /// Nunca envía `sucursal_origen_id` con cadena vacía.
  Map<String, dynamic> toJson() => {
        'variante_id': varianteId,
        'cantidad': cantidad,
        if (solicitaTraslado && tieneOrigenValido)
          'sucursal_origen_id': origenId!.trim(),
      };

  factory ItemBolsa.fromJson(Map<String, dynamic> j) {
    final crudo = (j['sucursal_origen_id'] ?? j['origen_id'])?.toString();
    final limpio = crudo == null || crudo.trim().isEmpty ? null : crudo.trim();
    return ItemBolsa(
      varianteId: '${j['variante_id'] ?? ''}',
      nombrePrenda: '${j['nombre_prenda'] ?? 'Prenda'}',
      sku: '${j['sku'] ?? ''}',
      precio: _aDouble(j['precio']),
      cantidad: (j['cantidad'] as num?)?.toInt() ?? 1,
      solicitaTraslado: (j['solicita_traslado'] == true) || limpio != null,
      origenId: limpio,
      origenNombre: j['origen_nombre']?.toString(),
    );
  }
}
