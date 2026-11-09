class TasaCambioModel {
  final String id;
  final int version;
  final double tasaBobPorUsd;
  final DateTime? vigenteDesde;
  final DateTime? vigenteHasta;
  final String motivo;

  TasaCambioModel({
    required this.id,
    required this.version,
    required this.tasaBobPorUsd,
    this.vigenteDesde,
    this.vigenteHasta,
    required this.motivo,
  });

  factory TasaCambioModel.fromJson(Map<String, dynamic> j) {
    return TasaCambioModel(
      id: '${j['id'] ?? ''}',
      version: (j['version'] as num?)?.toInt() ?? 1,
      tasaBobPorUsd:
          double.tryParse('${j['tasa_bob_por_usd']}') ?? 6.96,
      vigenteDesde: DateTime.tryParse('${j['vigente_desde']}'),
      vigenteHasta: DateTime.tryParse('${j['vigente_hasta']}'),
      motivo: '${j['motivo'] ?? ''}',
    );
  }
}

class CotizacionMonedaModel {
  final double montoBob;
  final double montoUsd;
  final int centavosUsd;

  CotizacionMonedaModel({
    required this.montoBob,
    required this.montoUsd,
    required this.centavosUsd,
  });

  factory CotizacionMonedaModel.fromJson(Map<String, dynamic> j) {
    return CotizacionMonedaModel(
      montoBob: double.tryParse('${j['monto_bob']}') ?? 0.0,
      montoUsd: double.tryParse('${j['monto_usd']}') ?? 0.0,
      centavosUsd: (j['centavos_usd'] as num?)?.toInt() ?? 0,
    );
  }
}
