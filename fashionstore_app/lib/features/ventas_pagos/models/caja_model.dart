class CupoItemModel {
  final String varianteId;
  final int cantidad;

  CupoItemModel({required this.varianteId, required this.cantidad});

  Map<String, dynamic> toJson() => {
        'variante_id': varianteId,
        'cantidad': cantidad,
      };

  factory CupoItemModel.fromJson(Map<String, dynamic> json) => CupoItemModel(
        varianteId: json['variante_id'] as String,
        cantidad: (json['cantidad'] as num).toInt(),
      );
}

class TurnoCrearModel {
  final String cajaId;
  final String dispositivoId;
  final String sucursalId;
  final List<CupoItemModel> cupos;
  final int revision;

  TurnoCrearModel({
    required this.cajaId,
    required this.dispositivoId,
    required this.sucursalId,
    required this.cupos,
    this.revision = 1,
  });

  Map<String, dynamic> toJson() => {
        'caja_id': cajaId,
        'dispositivo_id': dispositivoId,
        'sucursal_id': sucursalId,
        'cupos': cupos.map((c) => c.toJson()).toList(),
        'revision': revision,
      };
}

class CupoRespuestaModel {
  final String varianteId;
  final String? sku;
  final String? productoNombre;
  final int otorgado;
  int consumido;
  int liberado;
  int mermado;
  final double precioAutorizadoBob;

  CupoRespuestaModel({
    required this.varianteId,
    this.sku,
    this.productoNombre,
    required this.otorgado,
    this.consumido = 0,
    this.liberado = 0,
    this.mermado = 0,
    required this.precioAutorizadoBob,
  });

  int get disponible => otorgado - consumido - liberado - mermado;

  factory CupoRespuestaModel.fromJson(Map<String, dynamic> json) =>
      CupoRespuestaModel(
        varianteId: json['variante_id'] as String,
        sku: json['sku'] as String?,
        productoNombre: json['producto_nombre'] as String?,
        otorgado: (json['otorgado'] as num).toInt(),
        consumido: (json['consumido'] as num?)?.toInt() ?? 0,
        liberado: (json['liberado'] as num?)?.toInt() ?? 0,
        mermado: (json['mermado'] as num?)?.toInt() ?? 0,
        precioAutorizadoBob:
            double.tryParse('${json['precio_autorizado_bob']}') ?? 0.0,
      );

  Map<String, dynamic> toJson() => {
        'variante_id': varianteId,
        'sku': sku,
        'producto_nombre': productoNombre,
        'otorgado': otorgado,
        'consumido': consumido,
        'liberado': liberado,
        'mermado': mermado,
        'precio_autorizado_bob': precioAutorizadoBob.toStringAsFixed(2),
      };
}

class TurnoHabilitacionModel {
  final String? empresaId;
  final String? horaCentralEn;
  final int? desfaseMs;
  final int? ultimoRelojMs;
  final String turnoId;
  final String habilitacionId;
  final String cajaCodigo;
  final String dispositivoId;
  final String sucursalId;
  final String cajeroId;
  String estado;
  final String inicioEn;
  final String venceEn;
  final String versionPrecios;
  int revision;
  final List<CupoRespuestaModel> cupos;
  final Map<String, dynamic>? snapshot;

  TurnoHabilitacionModel({
    this.empresaId,
    this.horaCentralEn,
    this.desfaseMs,
    this.ultimoRelojMs,
    required this.turnoId,
    required this.habilitacionId,
    required this.cajaCodigo,
    required this.dispositivoId,
    required this.sucursalId,
    required this.cajeroId,
    required this.estado,
    required this.inicioEn,
    required this.venceEn,
    required this.versionPrecios,
    required this.revision,
    required this.cupos,
    this.snapshot,
  });

  bool get estaVigente {
    final inicio = DateTime.tryParse(inicioEn), vence = DateTime.tryParse(venceEn);
    if (estado != 'ABIERTO' || inicio == null || vence == null) return false;
    final local = DateTime.now().toUtc().millisecondsSinceEpoch;
    final central = local + (desfaseMs ?? 0);
    final inicioMs = inicio.toUtc().millisecondsSinceEpoch;
    final fin = vence.toUtc().millisecondsSinceEpoch < inicioMs + 8 * 3600000 ? vence.toUtc().millisecondsSinceEpoch : inicioMs + 8 * 3600000;
    return local >= (ultimoRelojMs ?? local) && central >= inicioMs && central < fin;
  }

  factory TurnoHabilitacionModel.fromJson(Map<String, dynamic> json) {
    return TurnoHabilitacionModel(
      empresaId: json['empresa_id']?.toString(),
      horaCentralEn: json['hora_central_en']?.toString(),
      turnoId: json['turno_id'] as String,
      habilitacionId: json['habilitacion_id'] as String,
      cajaCodigo: json['caja_codigo'] as String,
      dispositivoId: json['dispositivo_id'] as String,
      sucursalId: json['sucursal_id'] as String,
      cajeroId: json['cajero_id'] as String,
      estado: json['estado'] as String,
      inicioEn: json['inicio_en'] as String,
      venceEn: json['vence_en'] as String,
      versionPrecios: json['version_precios'] as String,
      revision: (json['revision'] as num).toInt(),
      cupos: (json['cupos'] as List<dynamic>?)
              ?.map(
                  (c) => CupoRespuestaModel.fromJson(c as Map<String, dynamic>))
              .toList() ??
          [],
      snapshot: json['snapshot'] as Map<String, dynamic>?,
    );
  }

  Map<String, dynamic> toJson() => {
        'empresa_id': empresaId,
        'hora_central_en': horaCentralEn,
        'turno_id': turnoId,
        'habilitacion_id': habilitacionId,
        'caja_codigo': cajaCodigo,
        'dispositivo_id': dispositivoId,
        'sucursal_id': sucursalId,
        'cajero_id': cajeroId,
        'estado': estado,
        'inicio_en': inicioEn,
        'vence_en': venceEn,
        'version_precios': versionPrecios,
        'revision': revision,
        'cupos': cupos.map((c) => c.toJson()).toList(),
        'snapshot': snapshot,
      };
}

class VentaOfflineLineaModel {
  final String varianteId;
  final int cantidad;
  final double precioAutorizadoBob;

  VentaOfflineLineaModel({
    required this.varianteId,
    required this.cantidad,
    required this.precioAutorizadoBob,
  });

  Map<String, dynamic> toJson() => {
        'variante_id': varianteId,
        'cantidad': cantidad,
        'precio_autorizado_bob': precioAutorizadoBob.toStringAsFixed(2),
      };

  factory VentaOfflineLineaModel.fromJson(Map<String, dynamic> json) =>
      VentaOfflineLineaModel(
        varianteId: json['variante_id'] as String,
        cantidad: (json['cantidad'] as num).toInt(),
        precioAutorizadoBob:
            double.tryParse('${json['precio_autorizado_bob']}') ?? 0.0,
      );
}

class VentaOfflineCrearModel {
  final String? turnoIdOrigen;
  final String operacionId;
  final int secuenciaLocal;
  final String vendidaLocalEn;
  final String entregadaLocalEn;
  final String versionPrecios;
  final List<VentaOfflineLineaModel> lineas;
  final double totalBob;
  final double efectivoRecibidoBob;
  final double cambioEntregadoBob;
  final String? clienteId;

  VentaOfflineCrearModel({
    this.turnoIdOrigen,
    required this.operacionId,
    required this.secuenciaLocal,
    required this.vendidaLocalEn,
    required this.entregadaLocalEn,
    required this.versionPrecios,
    required this.lineas,
    required this.totalBob,
    required this.efectivoRecibidoBob,
    required this.cambioEntregadoBob,
    this.clienteId,
  });

  Map<String, dynamic> toJson() => {
        'operacion_id': operacionId,
        'secuencia_local': secuenciaLocal,
        'vendida_local_en': vendidaLocalEn,
        'entregada_local_en': entregadaLocalEn,
        'version_precios': versionPrecios,
        'lineas': lineas.map((l) => l.toJson()).toList(),
        'total_bob': totalBob.toStringAsFixed(2),
        'efectivo_recibido_bob': efectivoRecibidoBob.toStringAsFixed(2),
        'cambio_entregado_bob': cambioEntregadoBob.toStringAsFixed(2),
        if (clienteId != null) 'cliente_id': clienteId,
      };

  factory VentaOfflineCrearModel.fromJson(Map<String, dynamic> json, {String? turnoIdOrigen}) =>
      VentaOfflineCrearModel(
        turnoIdOrigen: turnoIdOrigen,
        operacionId: json['operacion_id'] as String,
        secuenciaLocal: (json['secuencia_local'] as num).toInt(),
        vendidaLocalEn: json['vendida_local_en'] as String,
        entregadaLocalEn: json['entregada_local_en'] as String,
        versionPrecios: json['version_precios'] as String,
        lineas: (json['lineas'] as List<dynamic>)
            .map((l) =>
                VentaOfflineLineaModel.fromJson(l as Map<String, dynamic>))
            .toList(),
        totalBob: double.tryParse('${json['total_bob']}') ?? 0.0,
        efectivoRecibidoBob:
            double.tryParse('${json['efectivo_recibido_bob']}') ?? 0.0,
        cambioEntregadoBob:
            double.tryParse('${json['cambio_entregado_bob']}') ?? 0.0,
        clienteId: json['cliente_id'] as String?,
      );
}

class VentaOfflineResultadoModel {
  final String resultado;
  final String operacionId;
  final String ventaId;
  final String numero;
  final double totalBob;
  final String comprobanteId;
  final String recibidaCentralEn;

  VentaOfflineResultadoModel({
    required this.resultado,
    required this.operacionId,
    required this.ventaId,
    required this.numero,
    required this.totalBob,
    required this.comprobanteId,
    required this.recibidaCentralEn,
  });

  factory VentaOfflineResultadoModel.fromJson(Map<String, dynamic> json) {
    if (json['resultado'] == 'REGISTRADA_CENTRAL') {
      final uuid = RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', caseSensitive: false);
      final total = double.tryParse('${json['total_bob']}');
      final fecha = json['recibida_central_en'];
      if (!uuid.hasMatch(json['venta_id']?.toString() ?? '') ||
          !uuid.hasMatch(json['comprobante_id']?.toString() ?? '') ||
          json['numero'] is! String || (json['numero'] as String).trim().isEmpty ||
          fecha is! String || DateTime.tryParse(fecha) == null ||
          !RegExp(r'(Z|[+-]\d{2}:\d{2})$', caseSensitive: false).hasMatch(fecha) ||
          total == null || !total.isFinite || total < 0) {
        throw const FormatException('Confirmacion central incompleta; la venta sigue pendiente.');
      }
    }
    return VentaOfflineResultadoModel(
        resultado: json['resultado'] as String? ?? 'RESPUESTA_NO_CONFIRMADA',
        operacionId: json['operacion_id'] as String,
        ventaId: json['venta_id'] as String,
        numero: json['numero'] as String,
        totalBob: double.tryParse('${json['total_bob']}') ?? 0.0,
        comprobanteId: json['comprobante_id'] as String,
        recibidaCentralEn: json['recibida_central_en'] as String,
      );
  }
}

class TurnoCerrarModel {
  final int revision;
  final int? ultimaSecuenciaLocal;
  final int? totalOperacionesLocales;
  final List<String>? operacionesPendientes;
  final double? arqueoEfectivoBob;
  final double? arqueoDeclaradoBob;
  final bool? supervisionForzada;
  final String? motivoSupervision;
  final bool? descarteVentaFisica;
  final Map<String, dynamic>? evidenciaCierre;
  final Map<String, dynamic>? ajustesInventario;

  TurnoCerrarModel({
    required this.revision,
    this.ultimaSecuenciaLocal,
    this.totalOperacionesLocales,
    this.operacionesPendientes,
    this.arqueoEfectivoBob,
    this.arqueoDeclaradoBob,
    this.supervisionForzada,
    this.motivoSupervision,
    this.descarteVentaFisica,
    this.evidenciaCierre,
    this.ajustesInventario,
  });

  Map<String, dynamic> toJson() => {
        'revision': revision,
        if (ultimaSecuenciaLocal != null)
          'ultima_secuencia_local': ultimaSecuenciaLocal,
        if (totalOperacionesLocales != null)
          'total_operaciones_locales': totalOperacionesLocales,
        if (operacionesPendientes != null)
          'operaciones_pendientes': operacionesPendientes,
        if (arqueoEfectivoBob != null)
          'arqueo_efectivo_bob': arqueoEfectivoBob!.toStringAsFixed(2),
        if (arqueoDeclaradoBob != null)
          'arqueo_declarado_bob': arqueoDeclaradoBob!.toStringAsFixed(2),
        if (supervisionForzada != null)
          'supervision_forzada': supervisionForzada,
        if (motivoSupervision != null) 'motivo_supervision': motivoSupervision,
        if (descarteVentaFisica != null)
          'descarte_venta_fisica': descarteVentaFisica,
        if (evidenciaCierre != null) 'evidencia_cierre': evidenciaCierre,
        if (ajustesInventario != null) 'ajustes_inventario': ajustesInventario,
      };
}

class TurnoCerradoModel {
  final String turnoId;
  final String estado;
  final String cerradoEn;
  final int revision;
  final List<dynamic> cuposDevueltos;
  final List<dynamic> cuposRetenidos;

  TurnoCerradoModel({
    required this.turnoId,
    required this.estado,
    required this.cerradoEn,
    required this.revision,
    required this.cuposDevueltos,
    this.cuposRetenidos = const [],
  });

  factory TurnoCerradoModel.fromJson(Map<String, dynamic> json) =>
      TurnoCerradoModel(
        turnoId: json['turno_id'] as String,
        estado: json['estado'] as String,
        cerradoEn: json['cerrado_en'] as String? ?? '',
        revision: (json['revision'] as num).toInt(),
        cuposDevueltos: json['cupos_devueltos'] as List<dynamic>? ?? [],
        cuposRetenidos: json['cupos_retenidos'] as List<dynamic>? ?? [],
      );
}

class ComprobanteLocalModel {
  final String comprobanteId;
  final String operacionId;
  final String turnoId;
  final String empresaId;
  final String numeroComprobante;
  final double totalBob;
  final double efectivoRecibidoBob;
  final double cambioBob;
  final String emitidoEn;
  final List<Map<String, dynamic>> lineas;

  ComprobanteLocalModel({
    required this.comprobanteId,
    required this.operacionId,
    required this.turnoId,
    required this.empresaId,
    required this.numeroComprobante,
    required this.totalBob,
    required this.efectivoRecibidoBob,
    required this.cambioBob,
    required this.emitidoEn,
    this.lineas = const [],
  });

  Map<String, dynamic> toJson() => {
        'comprobante_id': comprobanteId,
        'operacion_id': operacionId,
        'turno_id': turnoId,
        'empresa_id': empresaId,
        'numero_comprobante': numeroComprobante,
        'total_bob': totalBob.toStringAsFixed(2),
        'efectivo_recibido_bob': efectivoRecibidoBob.toStringAsFixed(2),
        'cambio_bob': cambioBob.toStringAsFixed(2),
        'emitido_en': emitidoEn,
        'lineas': lineas,
      };

  factory ComprobanteLocalModel.fromJson(Map<String, dynamic> j) =>
      ComprobanteLocalModel(
        comprobanteId: '${j['comprobante_id']}',
        operacionId: '${j['operacion_id']}',
        turnoId: '${j['turno_id']}',
        empresaId: '${j['empresa_id']}',
        numeroComprobante: '${j['numero_comprobante']}',
        totalBob: double.tryParse('${j['total_bob']}') ?? 0.0,
        efectivoRecibidoBob:
            double.tryParse('${j['efectivo_recibido_bob']}') ?? 0.0,
        cambioBob: double.tryParse('${j['cambio_bob']}') ?? 0.0,
        emitidoEn: '${j['emitido_en']}',
        lineas: ((j['lineas'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList(),
      );
}

class VarianteCajaDisponibleModel {
  final String varianteId;
  final String? productoId;
  final String sku;
  final String productoNombre;
  final String? talla;
  final String? color;
  final double precioBob;
  final int stockDisponible;

  VarianteCajaDisponibleModel({
    required this.varianteId,
    this.productoId,
    required this.sku,
    required this.productoNombre,
    this.talla,
    this.color,
    required this.precioBob,
    this.stockDisponible = 0,
  });

  factory VarianteCajaDisponibleModel.fromJson(Map<String, dynamic> json) =>
      VarianteCajaDisponibleModel(
        varianteId:
            json['variante_id']?.toString() ?? json['id']?.toString() ?? '',
        productoId: json['producto_id']?.toString(),
        sku: json['sku']?.toString() ?? 'SKU',
        productoNombre: json['producto_nombre']?.toString() ??
            json['nombre']?.toString() ??
            'Prenda',
        talla: json['talla']?.toString(),
        color: json['color']?.toString(),
        precioBob: double.tryParse(json['precio_bob']?.toString() ??
                json['precio']?.toString() ??
                '0.0') ??
            0.0,
        stockDisponible: (json['disponible'] as num?)?.toInt() ??
            (json['disponibilidad'] as num?)?.toInt() ??
            (json['stock_disponible'] as num?)?.toInt() ??
            0,
      );

  Map<String, dynamic> toJson() => {
        'variante_id': varianteId,
        if (productoId != null) 'producto_id': productoId,
        'sku': sku,
        'producto_nombre': productoNombre,
        if (talla != null) 'talla': talla,
        if (color != null) 'color': color,
        'precio_bob': precioBob,
        'stock_disponible': stockDisponible,
      };
}
