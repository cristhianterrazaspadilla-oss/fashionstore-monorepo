/// Modelo de saldo personal del cliente (CU09).
class SaldoClienteModel {
  final String clienteId;
  final String empresaId;
  final double saldoDisponibleBob;
  final double saldoRetenidoBob;
  final String moneda;
  final List<MovimientoSaldoModel> movimientos;

  SaldoClienteModel({
    required this.clienteId,
    required this.empresaId,
    required this.saldoDisponibleBob,
    required this.saldoRetenidoBob,
    this.moneda = 'BOB',
    this.movimientos = const [],
  });

  factory SaldoClienteModel.fromJson(Map<String, dynamic> j) {
    var rawMovs = j['movimientos'];
    List<MovimientoSaldoModel> movs = [];
    if (rawMovs is List) {
      movs = rawMovs
          .map((m) => MovimientoSaldoModel.fromJson((m as Map).cast<String, dynamic>()))
          .toList();
    }
    return SaldoClienteModel(
      clienteId: '${j['cliente_id'] ?? ''}',
      empresaId: '${j['empresa_id'] ?? ''}',
      saldoDisponibleBob: double.tryParse('${j['saldo_disponible_bob']}') ?? 0.0,
      saldoRetenidoBob: double.tryParse('${j['saldo_retenido_bob']}') ?? 0.0,
      moneda: '${j['moneda'] ?? 'BOB'}',
      movimientos: movs,
    );
  }
}

/// Movimiento individual en el libro de saldo (CU09).
class MovimientoSaldoModel {
  final String id;
  final String tipo;
  final double montoBob;
  final double saldoResultanteBob;
  final String motivo;
  final String creadaEn;

  MovimientoSaldoModel({
    required this.id,
    required this.tipo,
    required this.montoBob,
    required this.saldoResultanteBob,
    required this.motivo,
    required this.creadaEn,
  });

  factory MovimientoSaldoModel.fromJson(Map<String, dynamic> j) {
    return MovimientoSaldoModel(
      id: '${j['id'] ?? ''}',
      tipo: '${j['tipo'] ?? ''}',
      montoBob: double.tryParse('${j['monto_bob']}') ?? 0.0,
      saldoResultanteBob: double.tryParse('${j['saldo_resultante_bob']}') ?? 0.0,
      motivo: '${j['motivo'] ?? ''}',
      creadaEn: '${j['creada_en'] ?? ''}',
    );
  }
}

/// Solicitud de devolución posventa (CU20).
class DevolucionModel {
  final String id;
  final String ventaId;
  final String estado;
  final String motivo;
  final String sucursalId;
  final String creadaEn;
  final List<Map<String, dynamic>> lineas;

  DevolucionModel({
    required this.id,
    required this.ventaId,
    required this.estado,
    required this.motivo,
    required this.sucursalId,
    required this.creadaEn,
    this.lineas = const [],
  });

  factory DevolucionModel.fromJson(Map<String, dynamic> j) {
    return DevolucionModel(
      id: '${j['id'] ?? ''}',
      ventaId: '${j['venta_id'] ?? ''}',
      estado: '${j['estado'] ?? ''}',
      motivo: '${j['motivo'] ?? j['motivo_descripcion'] ?? j['motivo_codigo'] ?? ''}',
      sucursalId: '${j['sucursal_id'] ?? ''}',
      creadaEn: '${j['creada_en'] ?? j['solicitada_en'] ?? ''}',
      lineas: ((j['lineas'] ?? j['detalles']) as List?)
              ?.whereType<Map>()
              .map((e) => e.cast<String, dynamic>())
              .toList() ??
          const [],
    );
  }
}

/// Solicitud de cambio de prenda (CU08).
class CambioModel {
  final String id;
  final String ventaId;
  final String estado;
  final double diferenciaBob;
  final String direccionDiferencia;
  final String notaVigenciaHasta;
  final String creadaEn;

  CambioModel({
    required this.id,
    required this.ventaId,
    required this.estado,
    required this.diferenciaBob,
    required this.direccionDiferencia,
    required this.notaVigenciaHasta,
    required this.creadaEn,
  });

  factory CambioModel.fromJson(Map<String, dynamic> j) {
    return CambioModel(
      id: '${j['cambio_id'] ?? j['id'] ?? ''}',
      ventaId: '${j['venta_id'] ?? ''}',
      estado: '${j['estado'] ?? ''}',
      diferenciaBob: double.tryParse('${j['diferencia_bob']}') ?? 0.0,
      direccionDiferencia: '${j['direccion_diferencia'] ?? 'CERO'}',
      notaVigenciaHasta: '${j['nota_vigencia_hasta'] ?? j['vence_espera_en'] ?? ''}',
      creadaEn: '${j['creada_en'] ?? j['creado_en'] ?? ''}',
    );
  }
}

/// Obligación de reembolso (CU27).
class ReembolsoModel {
  final String id;
  final String origenTipo;
  final String estado;
  final double montoTotalBob;
  final String creadaEn;

  ReembolsoModel({
    required this.id,
    required this.origenTipo,
    required this.estado,
    required this.montoTotalBob,
    required this.creadaEn,
  });

  factory ReembolsoModel.fromJson(Map<String, dynamic> j) {
    return ReembolsoModel(
      id: '${j['id'] ?? ''}',
      origenTipo: '${j['origen_tipo'] ?? ''}',
      estado: '${j['estado'] ?? ''}',
      montoTotalBob: double.tryParse('${j['monto_total_bob'] ?? j['monto_bob']}') ?? 0.0,
      creadaEn: '${j['creada_en'] ?? ''}',
    );
  }
}
