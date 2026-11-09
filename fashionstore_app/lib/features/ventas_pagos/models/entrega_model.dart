// Modelos Ciclo 3 — Delivery por anillos y pedidos (CU16).
//
// - GET /entregas/cotizacion?sucursal_id=&anillo_destino=
// - GET /entregas/mis-pedidos?limit=&offset=
// - GET /entregas/{pedido_id}
// - POST /entregas/{pedido_id}/cancelar
// La app solo consulta el estado; no avanza estados operativos.

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

class CotizacionDelivery {
  final String sucursalId;
  final int? anilloSucursal;
  final int anilloDestino;
  final double tarifaBase;
  final double incrementoAnillo;
  final double costoEntrega;

  CotizacionDelivery({
    required this.sucursalId,
    this.anilloSucursal,
    required this.anilloDestino,
    required this.tarifaBase,
    required this.incrementoAnillo,
    required this.costoEntrega,
  });

  factory CotizacionDelivery.fromJson(Map<String, dynamic> j) =>
      CotizacionDelivery(
        sucursalId: '${j['sucursal_id'] ?? ''}',
        anilloSucursal: (j['anillo_sucursal'] as num?)?.toInt(),
        anilloDestino: (j['anillo_destino'] as num?)?.toInt() ?? 1,
        tarifaBase: _aDouble(j['tarifa_base']),
        incrementoAnillo: _aDouble(j['incremento_anillo']),
        costoEntrega: _aDouble(j['costo_entrega']),
      );
}

class Pedido {
  final String id;
  final String ventaId;
  final String sucursalId;
  final String modalidad;
  final String estado;
  final int? anilloSucursal;
  final int? anilloDestino;
  final String? direccion;
  final double tarifaBase;
  final double incrementoAnillo;
  final double costoEntrega;
  final String? codigoRecojo;
  final DateTime? creadaEn;
  final bool puedeCancelar;
  final bool puedeTransicionar;
  final String? siguienteEstado;

  Pedido({
    required this.id,
    required this.ventaId,
    required this.sucursalId,
    required this.modalidad,
    required this.estado,
    this.anilloSucursal,
    this.anilloDestino,
    this.direccion,
    required this.tarifaBase,
    required this.incrementoAnillo,
    required this.costoEntrega,
    this.codigoRecojo,
    this.creadaEn,
    required this.puedeCancelar,
    required this.puedeTransicionar,
    this.siguienteEstado,
  });

  factory Pedido.fromJson(Map<String, dynamic> j) => Pedido(
        id: '${j['id'] ?? ''}',
        ventaId: '${j['venta_id'] ?? ''}',
        sucursalId: '${j['sucursal_id'] ?? ''}',
        modalidad: '${j['modalidad'] ?? ''}',
        estado: '${j['estado'] ?? ''}',
        anilloSucursal: (j['anillo_sucursal'] as num?)?.toInt(),
        anilloDestino: (j['anillo_destino'] as num?)?.toInt(),
        direccion: j['direccion']?.toString(),
        tarifaBase: _aDouble(j['tarifa_base']),
        incrementoAnillo: _aDouble(j['incremento_anillo']),
        costoEntrega: _aDouble(j['costo_entrega']),
        codigoRecojo: j['codigo_recojo']?.toString(),
        creadaEn: _aFecha(j['creada_en']),
        puedeCancelar: j['puede_cancelar'] == true,
        puedeTransicionar: j['puede_transicionar'] == true,
        siguienteEstado: j['siguiente_estado']?.toString(),
      );

  bool get esRecojo => modalidad == 'RECOJO';
  bool get esDelivery => modalidad == 'DELIVERY';
  bool get estaActivo =>
      estado == 'SOLICITADO' ||
      estado == 'PREPARADO' ||
      estado == 'LISTO_RECOJO' ||
      estado == 'EN_REPARTO';
  bool get estaCompletado => estado == 'RECOGIDO' || estado == 'ENTREGADO';
  bool get estaCancelado => estado == 'CANCELADO';

  /// Pasos de seguimiento según modalidad (solo lectura).
  List<String> get pasosSeguimiento => esRecojo
      ? const ['SOLICITADO', 'PREPARADO', 'LISTO_RECOJO', 'RECOGIDO']
      : const ['SOLICITADO', 'PREPARADO', 'EN_REPARTO', 'ENTREGADO'];

  int get indicePaso {
    final pasos = pasosSeguimiento;
    final i = pasos.indexOf(estado);
    return i < 0 ? 0 : i;
  }
}

class PedidoLista {
  final int total;
  final int limit;
  final int offset;
  final List<Pedido> items;

  PedidoLista({
    required this.total,
    required this.limit,
    required this.offset,
    required this.items,
  });

  factory PedidoLista.fromJson(Map<String, dynamic> j) => PedidoLista(
        total: (j['total'] as num?)?.toInt() ?? 0,
        limit: (j['limit'] as num?)?.toInt() ?? 0,
        offset: (j['offset'] as num?)?.toInt() ?? 0,
        items: ((j['items'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => Pedido.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );
}
