/// Modelos para el registro de dispositivos móviles y bandeja de avisos push (E2).
class DispositivoRegistroModel {
  final String id;
  final String dispositivoId;
  final String canal;
  final String estado;
  final String creadoEn;

  DispositivoRegistroModel({
    required this.id,
    required this.dispositivoId,
    required this.canal,
    required this.estado,
    required this.creadoEn,
  });

  factory DispositivoRegistroModel.fromJson(Map<String, dynamic> j) {
    return DispositivoRegistroModel(
      id: '${j['id'] ?? ''}',
      dispositivoId: '${j['dispositivo_id'] ?? ''}',
      canal: '${j['canal'] ?? 'FLUTTER'}',
      estado: '${j['estado'] ?? 'ACTIVO'}',
      creadoEn: '${j['creado_en'] ?? ''}',
    );
  }
}

class NotificacionAvisoModel {
  final String id;
  final String tipo;
  final String titulo;
  final String cuerpo;
  final String? recursoTipo;
  final String? recursoId;
  final String creadaEn;
  final String? leidaEn;

  NotificacionAvisoModel({
    required this.id,
    required this.tipo,
    required this.titulo,
    required this.cuerpo,
    this.recursoTipo,
    this.recursoId,
    required this.creadaEn,
    this.leidaEn,
  });

  bool get estaLeida => leidaEn != null && leidaEn!.isNotEmpty;

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'tipo': tipo,
      'titulo': titulo,
      'cuerpo': cuerpo,
      'recurso_tipo': recursoTipo,
      'recurso_id': recursoId,
      'creada_en': creadaEn,
      'leida_en': leidaEn,
    };
  }

  NotificacionAvisoModel copyWith({
    String? id,
    String? tipo,
    String? titulo,
    String? cuerpo,
    String? recursoTipo,
    String? recursoId,
    String? creadaEn,
    String? leidaEn,
  }) {
    return NotificacionAvisoModel(
      id: id ?? this.id,
      tipo: tipo ?? this.tipo,
      titulo: titulo ?? this.titulo,
      cuerpo: cuerpo ?? this.cuerpo,
      recursoTipo: recursoTipo ?? this.recursoTipo,
      recursoId: recursoId ?? this.recursoId,
      creadaEn: creadaEn ?? this.creadaEn,
      leidaEn: leidaEn ?? this.leidaEn,
    );
  }

  factory NotificacionAvisoModel.fromJson(Map<String, dynamic> j) {
    return NotificacionAvisoModel(
      id: '${j['id'] ?? ''}',
      tipo: '${j['tipo'] ?? ''}',
      titulo: '${j['titulo'] ?? ''}',
      cuerpo: '${j['cuerpo'] ?? ''}',
      recursoTipo: j['recurso_tipo'] as String?,
      recursoId: j['recurso_id'] as String?,
      creadaEn: '${j['creada_en'] ?? ''}',
      leidaEn: j['leida_en'] as String?,
    );
  }
}

/// Estado de vinculación y disponibilidad de Firebase Cloud Messaging (FCM).
enum EstadoFcm {
  /// Firebase no configurado en entorno (google-services.json o plugin no presentes); fallback seguro.
  noConfigurado,

  /// Token simulado persistido en memoria o almacenamiento local para desarrollo y pruebas.
  simulado,

  /// Conectado con token real emitido por el servicio FCM de Google Play Services.
  activoReal,
}

/// Notificación push recibida en primer o segundo plano vía FCM.
class NotificacionMensajePush {
  final String id;
  final String titulo;
  final String cuerpo;
  final Map<String, dynamic> datos;
  final DateTime recibidaEn;

  NotificacionMensajePush({
    required this.id,
    required this.titulo,
    required this.cuerpo,
    Map<String, dynamic>? datos,
    DateTime? recibidaEn,
  })  : datos = datos ?? const {},
        recibidaEn = recibidaEn ?? DateTime.now();

  factory NotificacionMensajePush.fromMap(Map<String, dynamic> map) {
    return NotificacionMensajePush(
      id: '${map['id'] ?? map['messageId'] ?? DateTime.now().millisecondsSinceEpoch}',
      titulo: '${map['titulo'] ?? map['title'] ?? 'Aviso'}',
      cuerpo: '${map['cuerpo'] ?? map['body'] ?? ''}',
      datos: (map['datos'] as Map?)?.cast<String, dynamic>() ??
          (map['data'] as Map?)?.cast<String, dynamic>() ??
          {},
      recibidaEn: map['recibida_en'] != null
          ? DateTime.tryParse('${map['recibida_en']}') ?? DateTime.now()
          : DateTime.now(),
    );
  }

  NotificacionAvisoModel toAvisoModel() {
    return NotificacionAvisoModel(
      id: id,
      tipo: datos['tipo']?.toString() ?? 'AVISO_PUSH',
      titulo: titulo,
      cuerpo: cuerpo,
      recursoTipo: datos['recurso_tipo']?.toString(),
      recursoId: datos['recurso_id']?.toString(),
      creadaEn: recibidaEn.toUtc().toIso8601String(),
      leidaEn: null,
    );
  }
}
