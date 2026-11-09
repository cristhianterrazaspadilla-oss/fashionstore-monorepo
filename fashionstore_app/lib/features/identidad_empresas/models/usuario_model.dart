class ClientePerfilModel {
  final String id;
  final String usuarioId;
  final String? empresaId;
  final String nombres;
  final String apellidos;
  final String nombreCompleto;
  final String correoElectronico;
  final String? telefono;
  final String rol;
  final String estado;
  final String? direccionReferencia;
  final String? fechaNacimiento;
  final Map<String, dynamic> preferencias;
  final DateTime creadoEn;

  ClientePerfilModel({
    required this.id,
    required this.usuarioId,
    this.empresaId,
    required this.nombres,
    required this.apellidos,
    required this.nombreCompleto,
    required this.correoElectronico,
    this.telefono,
    required this.rol,
    required this.estado,
    this.direccionReferencia,
    this.fechaNacimiento,
    required this.preferencias,
    required this.creadoEn,
  });

  factory ClientePerfilModel.fromJson(Map<String, dynamic> json) {
    return ClientePerfilModel(
      id: json['id'] ?? '',
      usuarioId: json['usuario_id'] ?? '',
      empresaId: json['empresa_id']?.toString(),
      nombres: json['nombres'] ?? '',
      apellidos: json['apellidos'] ?? '',
      nombreCompleto: json['nombre_completo'] ?? '',
      correoElectronico: json['correo_electronico'] ?? '',
      telefono: json['telefono'],
      rol: json['rol'] ?? 'CLIENTE',
      estado: json['estado'] ?? 'ACTIVO',
      direccionReferencia: json['direccion_referencia'],
      fechaNacimiento: json['fecha_nacimiento'],
      preferencias: json['preferencias'] != null
          ? Map<String, dynamic>.from(json['preferencias'])
          : {},
      creadoEn: DateTime.tryParse(json['creado_en'] ?? '') ?? DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'usuario_id': usuarioId,
      if (empresaId != null) 'empresa_id': empresaId,
      'nombres': nombres,
      'apellidos': apellidos,
      'nombre_completo': nombreCompleto,
      'correo_electronico': correoElectronico,
      'telefono': telefono,
      'rol': rol,
      'estado': estado,
      'direccion_referencia': direccionReferencia,
      'fecha_nacimiento': fechaNacimiento,
      'preferencias': preferencias,
      'creado_en': creadoEn.toIso8601String(),
    };
  }
}

class TokenRespuestaModel {
  final String accessToken;
  final String tokenType;
  final ClientePerfilModel usuario;

  TokenRespuestaModel({
    required this.accessToken,
    required this.tokenType,
    required this.usuario,
  });

  factory TokenRespuestaModel.fromJson(Map<String, dynamic> json) {
    return TokenRespuestaModel(
      accessToken: json['access_token'] ?? '',
      tokenType: json['token_type'] ?? 'bearer',
      usuario: ClientePerfilModel.fromJson(json['usuario'] ?? {}),
    );
  }
}
