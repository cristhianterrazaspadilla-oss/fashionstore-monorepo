class SuscripcionEmpresaModel {
  final String suscripcionId;
  final String empresaId;
  final String planId;
  final String planCodigo;
  final String planNombre;
  final String estadoEfectivo;
  final List<String> capacidades;
  final int sucursalesActivas;
  final int limiteSucursales;
  final bool permiteOffline;
  final DateTime? venceEn;

  SuscripcionEmpresaModel({
    required this.suscripcionId,
    required this.empresaId,
    required this.planId,
    required this.planCodigo,
    required this.planNombre,
    required this.estadoEfectivo,
    required this.capacidades,
    required this.sucursalesActivas,
    required this.limiteSucursales,
    required this.permiteOffline,
    this.venceEn,
  });

  factory SuscripcionEmpresaModel.fromJson(Map<String, dynamic> j) {
    return SuscripcionEmpresaModel(
      suscripcionId: '${j['suscripcion_id'] ?? ''}',
      empresaId: '${j['empresa_id'] ?? ''}',
      planId: '${j['plan_id'] ?? ''}',
      planCodigo: '${j['plan_codigo'] ?? ''}',
      planNombre: '${j['plan_nombre'] ?? 'Plan FashionStore'}',
      estadoEfectivo: '${j['estado_efectivo'] ?? 'ACTIVO'}',
      capacidades: ((j['capacidades'] as List?) ?? [])
          .map((e) => e.toString())
          .toList(),
      sucursalesActivas: (j['sucursales_activas'] as num?)?.toInt() ?? 0,
      limiteSucursales: (j['limite_sucursales'] as num?)?.toInt() ?? 1,
      permiteOffline: j['permite_offline'] == true,
      venceEn: DateTime.tryParse('${j['vence_en']}'),
    );
  }
}
