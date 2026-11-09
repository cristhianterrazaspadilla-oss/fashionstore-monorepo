// Modelos Ciclo 3 — Checkout digital y venta pendiente (CU14).
//
// POST /carritos/mio/checkout?canal=MOVIL (Idempotency-Key)
// Body: CheckoutCrearDTO{sucursal_id, canal, modalidad, direccion?, anillo_destino?}
// Resp: CheckoutRespuestaDTO{venta_id, numero, estado, total, expira_en, pedido_entrega_id}
// Venta: GET /ventas/{venta_id} -> VentaDTO con costo_entrega y expira_en.

double _aDouble(dynamic v, [double fb = 0]) {
  if (v == null) return fb;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? fb;
}

DateTime? _aFecha(dynamic v) {
  if (v == null) return null;
  if (v is DateTime) return v;
  return DateTime.tryParse(v.toString());
}

/// Modalidad de entrega del checkout (valores exactos del backend).
class ModalidadEntrega {
  static const recojo = 'RECOJO';
  static const delivery = 'DELIVERY';
}

class CheckoutCrear {
  final String sucursalId;
  final String canal;
  final String modalidad;
  final String? direccion;
  final int? anilloDestino;

  CheckoutCrear({
    required this.sucursalId,
    this.canal = 'MOVIL',
    required this.modalidad,
    this.direccion,
    this.anilloDestino,
  });

  Map<String, dynamic> toJson() => {
        'sucursal_id': sucursalId,
        'canal': canal,
        'modalidad': modalidad,
        if (direccion != null) 'direccion': direccion,
        if (anilloDestino != null) 'anillo_destino': anilloDestino,
      };
}

class CheckoutRespuesta {
  /// ID del pedido durable CU21. Vacío solo al hablar con un backend CU14 legado.
  final String pedidoId;
  final String ventaId;
  final String numero;
  final String estado;
  final double total;
  final String estadoPago;
  final String estadoCumplimiento;
  final int ofertaRevision;
  final DateTime? expiraEn;
  final String pedidoEntregaId;

  CheckoutRespuesta({
    this.pedidoId = '',
    this.ventaId = '',
    this.numero = '',
    this.estado = '',
    this.total = 0,
    this.estadoPago = '',
    this.estadoCumplimiento = '',
    this.ofertaRevision = 1,
    this.expiraEn,
    this.pedidoEntregaId = '',
  });

  factory CheckoutRespuesta.fromJson(Map<String, dynamic> j) =>
      CheckoutRespuesta(
        pedidoId: '${j['pedido_id'] ?? ''}',
        ventaId: '${j['venta_id'] ?? ''}',
        numero: '${j['numero'] ?? j['pedido_id'] ?? ''}',
        estado: '${j['estado'] ?? ''}',
        total: _aDouble(j['total_bob'] ?? j['total']),
        estadoPago: '${j['estado_pago'] ?? ''}',
        estadoCumplimiento: '${j['estado_cumplimiento'] ?? ''}',
        ofertaRevision: (j['oferta_revision'] as num?)?.toInt() ?? 1,
        expiraEn: _aFecha(j['vigente_hasta'] ?? j['expira_en']),
        pedidoEntregaId: '${j['pedido_entrega_id'] ?? ''}',
      );

  bool get esPedidoDurable => pedidoId.isNotEmpty;
}

class DetalleVentaDigital {
  final String id;
  final String? detalleReservaId;
  final String varianteId;
  final int cantidad;
  final double precioUnitario;
  final double descuento;
  final String? promocionId;
  final double? costoPromedio;

  DetalleVentaDigital({
    required this.id,
    this.detalleReservaId,
    required this.varianteId,
    required this.cantidad,
    required this.precioUnitario,
    required this.descuento,
    this.promocionId,
    this.costoPromedio,
  });

  factory DetalleVentaDigital.fromJson(Map<String, dynamic> j) =>
      DetalleVentaDigital(
        id: '${j['id'] ?? ''}',
        detalleReservaId: j['detalle_reserva_id']?.toString(),
        varianteId: '${j['variante_id'] ?? ''}',
        cantidad: (j['cantidad'] as num?)?.toInt() ?? 0,
        precioUnitario: _aDouble(j['precio_unitario']),
        descuento: _aDouble(j['descuento']),
        promocionId: j['promocion_id']?.toString(),
        costoPromedio:
            j['costo_promedio'] == null ? null : _aDouble(j['costo_promedio']),
      );
}

/// Venta digital pendiente de pago (VentaDTO del backend, canal MOVIL).
class VentaDigital {
  final String id;
  final String numero;
  final String? clienteId;
  final String? reservaId;
  final String sucursalId;
  final String? cajeroId;
  final String canal;
  final String estado;
  final double subtotal;
  final double descuento;
  final double adelantoDescontado;
  final double costoEntrega;
  final double total;
  final DateTime? creadaEn;
  final DateTime? confirmadaEn;
  final DateTime? expiraEn;
  final List<DetalleVentaDigital> detalles;

  VentaDigital({
    required this.id,
    required this.numero,
    this.clienteId,
    this.reservaId,
    required this.sucursalId,
    this.cajeroId,
    required this.canal,
    required this.estado,
    required this.subtotal,
    required this.descuento,
    required this.adelantoDescontado,
    required this.costoEntrega,
    required this.total,
    this.creadaEn,
    this.confirmadaEn,
    this.expiraEn,
    required this.detalles,
  });

  factory VentaDigital.fromJson(Map<String, dynamic> j) => VentaDigital(
        id: '${j['id'] ?? ''}',
        numero: '${j['numero'] ?? ''}',
        clienteId: j['cliente_id']?.toString(),
        reservaId: j['reserva_id']?.toString(),
        sucursalId: '${j['sucursal_id'] ?? ''}',
        cajeroId: j['cajero_id']?.toString(),
        canal: '${j['canal'] ?? 'MOVIL'}',
        estado: '${j['estado'] ?? ''}',
        subtotal: _aDouble(j['subtotal']),
        descuento: _aDouble(j['descuento']),
        adelantoDescontado: _aDouble(j['adelanto_descontado']),
        costoEntrega: _aDouble(j['costo_entrega']),
        total: _aDouble(j['total']),
        creadaEn: _aFecha(j['creada_en']),
        confirmadaEn: _aFecha(j['confirmada_en']),
        expiraEn: _aFecha(j['expira_en']),
        detalles: ((j['detalles'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => DetalleVentaDigital.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );

  bool get estaPendiente => estado == 'PENDIENTE_PAGO';
  bool get estaPagada => estado == 'PAGADA';
  bool get estaCancelada => estado == 'CANCELADA';
  int get totalPrendas => detalles.fold(0, (a, d) => a + d.cantidad);
}
