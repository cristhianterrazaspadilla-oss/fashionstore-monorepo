// Modelos Ciclo 3 — Carrito de compra (contrato real CU14).
//
// Endpoints:
// - GET /carritos/mio?canal=MOVIL
// - POST /carritos/mio/lineas?canal (Idempotency-Key)
// - PATCH /carritos/mio/lineas/{variante_id} (Idempotency-Key)
// - DELETE /carritos/mio/lineas/{variante_id} (Idempotency-Key)
// - DELETE /carritos/mio (Idempotency-Key)
// - GET /carritos/mio/cobertura?canal
//
// Reserva y carrito son flujos distintos: nunca mezclar IDs, estados,
// almacenamiento ni contadores con la bolsa de reserva (BolsaStore).

double _aDouble(dynamic v) {
  final n = v is num ? v.toDouble() : double.tryParse(v?.toString() ?? '');
  if (n == null || !n.isFinite || n < 0) {
    throw const FormatException('Importe de carrito desconocido o inválido. Actualiza el carrito.');
  }
  return n;
}

DateTime? _aFecha(dynamic v) {
  if (v == null) return null;
  if (v is DateTime) return v;
  return DateTime.tryParse(v.toString());
}

/// Línea del carrito de compra (LineaCarritoDTO del backend).
class LineaCarrito {
  final String id;
  final String varianteId;
  final int cantidad;
  final double precioUnitario;
  final double descuentoUnitario;
  final String? promocionId;
  final double subtotal;

  LineaCarrito({
    required this.id,
    required this.varianteId,
    required this.cantidad,
    required this.precioUnitario,
    required this.descuentoUnitario,
    this.promocionId,
    required this.subtotal,
  });

  factory LineaCarrito.fromJson(Map<String, dynamic> j) => LineaCarrito(
        id: '${j['id'] ?? ''}',
        varianteId: '${j['variante_id'] ?? ''}',
        cantidad: (j['cantidad'] as num?)?.toInt() ?? 0,
        precioUnitario: _aDouble(j['precio_unitario_bob'] ?? j['precio_unitario']),
        descuentoUnitario: _aDouble(j['descuento_unitario'] ?? (j.containsKey('precio_unitario_bob') ? 0 : null)),
        promocionId: j['promocion_id']?.toString(),
        subtotal: _aDouble(j['subtotal_bob'] ?? j['subtotal']),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'variante_id': varianteId,
        'cantidad': cantidad,
        'precio_unitario': precioUnitario,
        'descuento_unitario': descuentoUnitario,
        'promocion_id': promocionId,
        'subtotal': subtotal,
      };
}

/// Carrito activo del canal MOVIL (CarritoDTO del backend).
///
/// Los totales definitivos siempre provienen del backend; Flutter nunca
/// calcula un total definitivo localmente.
class CarritoCompra {
  final String id;
  final String clienteId;
  final String canal;
  final String estado;
  final DateTime? creadaEn;
  final DateTime? actualizadaEn;
  final List<LineaCarrito> lineas;
  final double subtotal;
  final double descuentoTotal;
  final double total;

  CarritoCompra({
    required this.id,
    required this.clienteId,
    required this.canal,
    required this.estado,
    this.creadaEn,
    this.actualizadaEn,
    required this.lineas,
    required this.subtotal,
    required this.descuentoTotal,
    required this.total,
  });

  factory CarritoCompra.vacio() => CarritoCompra(
        id: '',
        clienteId: '',
        canal: 'MOVIL',
        estado: 'ACTIVO',
        lineas: const [],
        subtotal: 0,
        descuentoTotal: 0,
        total: 0,
      );

  factory CarritoCompra.fromJson(Map<String, dynamic> j) => CarritoCompra(
        id: '${j['id'] ?? ''}',
        clienteId: '${j['cliente_id'] ?? ''}',
        canal: '${j['canal'] ?? 'MOVIL'}',
        estado: '${j['estado'] ?? 'ACTIVO'}',
        creadaEn: _aFecha(j['creada_en']),
        actualizadaEn: _aFecha(j['actualizada_en']),
        lineas: ((j['lineas'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => LineaCarrito.fromJson(e.cast<String, dynamic>()))
            .toList(),
        subtotal: _aDouble(j['subtotal'] ?? j['total_estimado_bob']),
        descuentoTotal: _aDouble(j['descuento_total'] ?? (j.containsKey('total_estimado_bob') ? 0 : null)),
        total: _aDouble(j['total'] ?? j['total_estimado_bob']),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'cliente_id': clienteId,
        'canal': canal,
        'estado': estado,
        'creada_en': creadaEn?.toIso8601String(),
        'actualizada_en': actualizadaEn?.toIso8601String(),
        'lineas': lineas.map((e) => e.toJson()).toList(),
        'subtotal': subtotal,
        'descuento_total': descuentoTotal,
        'total': total,
      };

  bool get estaVacio => lineas.isEmpty;
  int get totalPrendas => lineas.fold(0, (a, e) => a + e.cantidad);
  bool get tieneDescuento => descuentoTotal > 0;
}

/// Cobertura de una sucursal para el carrito completo.
class CoberturaSucursal {
  final String sucursalId;
  final String sucursalNombre;
  final bool cubreTodo;
  final List<String> faltantes;

  CoberturaSucursal({
    required this.sucursalId,
    required this.sucursalNombre,
    required this.cubreTodo,
    required this.faltantes,
  });

  factory CoberturaSucursal.fromJson(Map<String, dynamic> j) =>
      CoberturaSucursal(
        sucursalId: '${j['sucursal_id'] ?? ''}',
        sucursalNombre: '${j['sucursal_nombre'] ?? 'Sucursal'}',
        cubreTodo: j['cubre_todo'] == true,
        faltantes: ((j['faltantes'] as List?) ?? []).map((e) => '$e').toList(),
      );

  Map<String, dynamic> toJson() => {
        'sucursal_id': sucursalId,
        'sucursal_nombre': sucursalNombre,
        'cubre_todo': cubreTodo,
        'faltantes': faltantes,
      };
}

class CoberturaCarrito {
  final List<CoberturaSucursal> sucursales;

  CoberturaCarrito({required this.sucursales});

  factory CoberturaCarrito.fromJson(Map<String, dynamic> j) => CoberturaCarrito(
        sucursales: ((j['sucursales'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => CoberturaSucursal.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );

  List<CoberturaSucursal> get queCubren =>
      sucursales.where((e) => e.cubreTodo).toList();
}
