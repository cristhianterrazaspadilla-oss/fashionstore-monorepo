class CiudadModel {
  final String id;
  final String nombre;
  final bool activo;

  CiudadModel({
    required this.id,
    required this.nombre,
    required this.activo,
  });

  factory CiudadModel.fromJson(Map<String, dynamic> json) {
    return CiudadModel(
      id: json['id'] ?? '',
      nombre: json['nombre'] ?? '',
      activo: json['activo'] ?? true,
    );
  }
}

class SucursalModel {
  final String id;
  final String ciudadId;
  final String? ciudadNombre;
  final String nombre;
  final String direccion;
  final String? telefono;
  final int? numeroAnillo;
  final double tarifaBaseDelivery;
  final double incrementoAnilloDelivery;
  final int anilloMinimoDelivery;
  final int anilloMaximoDelivery;
  final bool deliveryActivo;
  final bool activa;

  SucursalModel({
    required this.id,
    required this.ciudadId,
    this.ciudadNombre,
    required this.nombre,
    required this.direccion,
    this.telefono,
    this.numeroAnillo,
    required this.tarifaBaseDelivery,
    required this.incrementoAnilloDelivery,
    required this.anilloMinimoDelivery,
    required this.anilloMaximoDelivery,
    required this.deliveryActivo,
    required this.activa,
  });

  factory SucursalModel.fromJson(Map<String, dynamic> json) {
    return SucursalModel(
      id: json['id'] ?? '',
      ciudadId: json['ciudad_id'] ?? '',
      ciudadNombre: json['ciudad_nombre'],
      nombre: json['nombre'] ?? '',
      direccion: json['direccion'] ?? '',
      telefono: json['telefono'],
      numeroAnillo: json['numero_anillo'],
      tarifaBaseDelivery:
          double.tryParse(json['tarifa_base_delivery']?.toString() ?? '0') ??
              0.0,
      incrementoAnilloDelivery: double.tryParse(
              json['incremento_anillo_delivery']?.toString() ?? '0') ??
          0.0,
      anilloMinimoDelivery: json['anillo_minimo_delivery'] ?? 1,
      anilloMaximoDelivery: json['anillo_maximo_delivery'] ?? 10,
      deliveryActivo: json['delivery_activo'] ?? true,
      activa: json['activa'] ?? true,
    );
  }
}
