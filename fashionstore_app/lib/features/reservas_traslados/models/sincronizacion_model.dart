import 'dart:convert';

/// Referencia horaria emitida por el backend central para operaciones offline (CU04).
class ReferenciaHorariaModel {
  final String id;
  final String empresaId;
  final String usuarioId;
  final String dispositivoId;
  final String horaCentralEn;
  final String validaHasta;
  final int toleranciaSegundos;
  final int politicaVersion;
  final String emitidaEn;

  ReferenciaHorariaModel({
    required this.id,
    required this.empresaId,
    required this.usuarioId,
    required this.dispositivoId,
    required this.horaCentralEn,
    required this.validaHasta,
    this.toleranciaSegundos = 300,
    this.politicaVersion = 1,
    required this.emitidaEn,
  });

  factory ReferenciaHorariaModel.fromJson(
    Map<String, dynamic> j, {
    String? fallbackEmpresaId,
    String? fallbackUsuarioId,
    String? fallbackDispositivoId,
  }) {
    return ReferenciaHorariaModel(
      id: '${j['referencia_horaria_id'] ?? j['id'] ?? ''}',
      empresaId: '${j['empresa_id'] ?? fallbackEmpresaId ?? ''}',
      usuarioId: '${j['usuario_id'] ?? fallbackUsuarioId ?? ''}',
      dispositivoId: '${j['dispositivo_id'] ?? fallbackDispositivoId ?? ''}',
      horaCentralEn: '${j['hora_central_en'] ?? j['emitida_en'] ?? ''}',
      validaHasta: '${j['valida_hasta'] ?? j['vence_en'] ?? ''}',
      toleranciaSegundos: (j['tolerancia_segundos'] as num?)?.toInt() ?? 300,
      politicaVersion: (j['politica_version'] as num?)?.toInt() ?? 1,
      emitidaEn: '${j['emitida_en'] ?? j['hora_central_en'] ?? ''}',
    );
  }

  factory ReferenciaHorariaModel.fromDb(Map<String, dynamic> m) {
    return ReferenciaHorariaModel(
      id: '${m['id'] ?? ''}',
      empresaId: '${m['empresa_id'] ?? ''}',
      usuarioId: '${m['usuario_id'] ?? ''}',
      dispositivoId: '${m['dispositivo_id'] ?? ''}',
      horaCentralEn: '${m['hora_central_en'] ?? ''}',
      validaHasta: '${m['valida_hasta'] ?? ''}',
      toleranciaSegundos: (m['tolerancia_segundos'] as num?)?.toInt() ?? 300,
      politicaVersion: (m['politica_version'] as num?)?.toInt() ?? 1,
      emitidaEn: '${m['emitida_en'] ?? ''}',
    );
  }

  Map<String, dynamic> toDbMap() => {
        'id': id,
        'empresa_id': empresaId,
        'usuario_id': usuarioId,
        'dispositivo_id': dispositivoId,
        'hora_central_en': horaCentralEn,
        'valida_hasta': validaHasta,
        'tolerancia_segundos': toleranciaSegundos,
        'politica_version': politicaVersion,
        'emitida_en': emitidaEn,
      };

  bool get estaVencida {
    final v = DateTime.tryParse(validaHasta);
    if (v == null || DateTime.tryParse(horaCentralEn) == null) return true;
    return !DateTime.now().toUtc().isBefore(v.toUtc());
  }
}

/// Registro en la cola de sincronización offline SQLite (CU04).
class OperacionSincronizacionLocal {
  final String operacionId;
  final String empresaId;
  final String usuarioId;
  final String dispositivoId;
  final int secuenciaLocal;
  final String? referenciaHorariaId;
  final String creadaLocalEn;
  final String datosJson;
  final String estadoEnvio; // PENDIENTE_ENVIO, ENVIANDO, ACEPTADA, RECHAZADA, CONFLICTO
  final String? resultadoJson;
  final String actualizadoEn;

  OperacionSincronizacionLocal({
    required this.operacionId,
    required this.empresaId,
    required this.usuarioId,
    required this.dispositivoId,
    required this.secuenciaLocal,
    this.referenciaHorariaId,
    required this.creadaLocalEn,
    required this.datosJson,
    this.estadoEnvio = 'PENDIENTE_ENVIO',
    this.resultadoJson,
    required this.actualizadoEn,
  });

  factory OperacionSincronizacionLocal.fromDb(Map<String, dynamic> m) {
    return OperacionSincronizacionLocal(
      operacionId: '${m['operacion_id'] ?? ''}',
      empresaId: '${m['empresa_id'] ?? ''}',
      usuarioId: '${m['usuario_id'] ?? ''}',
      dispositivoId: '${m['dispositivo_id'] ?? ''}',
      secuenciaLocal: (m['secuencia_local'] as num?)?.toInt() ?? 1,
      referenciaHorariaId: m['referencia_horaria_id'] as String?,
      creadaLocalEn: '${m['creada_local_en'] ?? ''}',
      datosJson: '${m['datos_json'] ?? '{}'}',
      estadoEnvio: '${m['estado_envio'] ?? 'PENDIENTE_ENVIO'}',
      resultadoJson: m['resultado_json'] as String?,
      actualizadoEn: '${m['actualizado_en'] ?? ''}',
    );
  }

  Map<String, dynamic> toDbMap() => {
        'operacion_id': operacionId,
        'empresa_id': empresaId,
        'usuario_id': usuarioId,
        'dispositivo_id': dispositivoId,
        'secuencia_local': secuenciaLocal,
        'referencia_horaria_id': referenciaHorariaId,
        'creada_local_en': creadaLocalEn,
        'datos_json': datosJson,
        'estado_envio': estadoEnvio,
        'resultado_json': resultadoJson,
        'actualizado_en': actualizadoEn,
      };

  Map<String, dynamic> toApiPayload() {
    Map<String, dynamic> datos = {};
    try {
      datos = jsonDecode(datosJson) as Map<String, dynamic>;
    } catch (_) {
      throw StateError('Contenido original ilegible; la solicitud se conserva sin enviar.');
    }

    final tipo = datos['_tipo_operacion']?.toString() ?? 'SOLICITAR_RESERVA';
    final datosClean = Map<String, dynamic>.from(datos)..remove('_tipo_operacion');

    int versionEsquema = 1;
    if (datos.containsKey('_version_esquema')) {
      versionEsquema = (datos['_version_esquema'] as num).toInt();
    } else if (datosClean.containsKey('version_esquema')) {
      versionEsquema = (datosClean['version_esquema'] as num).toInt();
    } else if (tipo == 'SOLICITAR_COMPRA') {
      if (datosClean.containsKey('autorizacion_cobro') && datosClean['autorizacion_cobro'] != null) {
        versionEsquema = 3;
      } else if (datosClean.containsKey('modalidad')) {
        versionEsquema = 2;
      }
    }
    datosClean.remove('_version_esquema');
    datosClean.remove('version_esquema');

    return {
      'version_esquema': versionEsquema,
      'operacion_id': operacionId,
      'tipo': tipo,
      'creada_local_en': creadaLocalEn,
      'empresa_id': empresaId,
      'usuario_id': usuarioId,
      'dispositivo_id': dispositivoId,
      'secuencia_local': secuenciaLocal,
      if (referenciaHorariaId != null && referenciaHorariaId!.isNotEmpty)
        'referencia_horaria_id': referenciaHorariaId,
      'datos': datosClean,
    };
  }

  Map<String, dynamic> get datos {
    try {
      return jsonDecode(datosJson) as Map<String, dynamic>;
    } catch (_) {
      return {};
    }
  }

  Map<String, dynamic>? get resultado {
    if (resultadoJson == null || resultadoJson!.isEmpty) return null;
    try {
      return jsonDecode(resultadoJson!) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  ResultadoOperacionDTO? get resultadoParsed {
    if (resultadoJson == null || resultadoJson!.isEmpty) return null;
    try {
      final j = jsonDecode(resultadoJson!) as Map<String, dynamic>;
      return ResultadoOperacionDTO.fromJson(j);
    } catch (_) {
      return null;
    }
  }
}

/// DTO del resultado recibido del servidor para una operación sincronizada (CU04 / CU18).
class ResultadoOperacionDTO {
  final String operacionId;
  final String estado; // ACEPTADA, RECHAZADA, CONFLICTO
  final String codigo; // OK, SIN_STOCK, SOLICITUD_VENCIDA, TIEMPO_INCOHERENTE, etc.
  final String recibidaEn;
  final String detalle;
  final String? aceptadaEn;
  final String? venceEn;
  final String? recursoId;
  final int revision;

  ResultadoOperacionDTO({
    required this.operacionId,
    required this.estado,
    required this.codigo,
    required this.recibidaEn,
    required this.detalle,
    this.aceptadaEn,
    this.venceEn,
    this.recursoId,
    this.revision = 1,
  });

  factory ResultadoOperacionDTO.fromJson(Map<String, dynamic> j) {
    return ResultadoOperacionDTO(
      operacionId: '${j['operacion_id'] ?? ''}',
      estado: '${j['estado'] ?? ''}',
      codigo: '${j['codigo'] ?? 'OK'}',
      recibidaEn: '${j['recibida_en'] ?? ''}',
      detalle: '${j['detalle'] ?? j['mensaje'] ?? ''}',
      aceptadaEn: (j['aceptada_en'] ?? j['creada_en'])?.toString(),
      venceEn: j['vence_en'] as String?,
      recursoId: (j['recurso_id'] ?? j['reserva_id'])?.toString(),
      revision: (j['revision'] as num?)?.toInt() ?? 1,
    );
  }

  Map<String, dynamic> toJson() => {
        'operacion_id': operacionId,
        'estado': estado,
        'codigo': codigo,
        'recibida_en': recibidaEn,
        'detalle': detalle,
        if (aceptadaEn != null) 'aceptada_en': aceptadaEn,
        if (venceEn != null) 'vence_en': venceEn,
        if (recursoId != null) 'recurso_id': recursoId,
        if (recursoId != null) 'reserva_id': recursoId,
        'revision': revision,
      };
}
