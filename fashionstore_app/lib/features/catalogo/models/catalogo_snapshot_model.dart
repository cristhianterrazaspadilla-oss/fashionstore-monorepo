import 'dart:convert';

/// Modelo de un snapshot descargado del catálogo para persistencia local en SQLite (CU03 / CU16).
class CatalogoSnapshotModel {
  final String empresaId;
  final String empresaCodigo;
  final int catalogoVersion;
  final String generadoEn;
  final String? guardadoLocalEn;
  final List<String> ambitoSucursales;
  final bool valido;
  final List<CatalogoProductoLocal> productos;
  final List<CatalogoColorLocal> colores;
  final List<CatalogoPromocionLocal> promociones;

  CatalogoSnapshotModel({
    required this.empresaId,
    required this.empresaCodigo,
    required this.catalogoVersion,
    required this.generadoEn,
    this.guardadoLocalEn,
    this.ambitoSucursales = const [],
    this.valido = true,
    this.productos = const [],
    this.colores = const [],
    this.promociones = const [],
  });

  factory CatalogoSnapshotModel.fromJson(Map<String, dynamic> j) {
    final empId = '${j['empresa_id'] ?? ''}';
    final empCodigo = '${j['empresa_codigo'] ?? ''}';

    // Parsear ambito_sucursales que puede ser List<dynamic> o String
    List<String> ambitos = [];
    if (j['ambito_sucursales'] is List) {
      ambitos = (j['ambito_sucursales'] as List).map((e) => '$e').toList();
    } else if (j['ambito_sucursales'] is String) {
      ambitos = ['$j[\'ambito_sucursales\']'];
    }

    final fechaGen = '${j['generado_en'] ?? j['descargado_en'] ?? DateTime.now().toUtc().toIso8601String()}';

    // Parsear productos
    final prodsRaw = (j['productos'] as List?) ?? [];
    final prods = <CatalogoProductoLocal>[];
    for (final p in prodsRaw) {
      if (p is Map) {
        prods.add(CatalogoProductoLocal.fromJson(p.cast<String, dynamic>(), empresaId: empId));
      }
    }

    // Parsear colores
    final coloresRaw = (j['colores'] as List?) ?? [];
    final cols = <CatalogoColorLocal>[];
    for (final c in coloresRaw) {
      if (c is Map) {
        cols.add(CatalogoColorLocal.fromJson(c.cast<String, dynamic>(), empresaId: empId));
      }
    }

    // Parsear promociones
    final promosRaw = (j['promociones'] as List?) ?? [];
    final promos = <CatalogoPromocionLocal>[];
    for (final pr in promosRaw) {
      if (pr is Map) {
        promos.add(CatalogoPromocionLocal.fromJson(pr.cast<String, dynamic>(), empresaId: empId));
      }
    }

    return CatalogoSnapshotModel(
      empresaId: empId,
      empresaCodigo: empCodigo,
      catalogoVersion: (j['catalogo_version'] as num?)?.toInt() ?? 1,
      generadoEn: fechaGen,
      guardadoLocalEn: j['guardado_local_en'] as String?,
      ambitoSucursales: ambitos,
      valido: j['valido'] != false,
      productos: prods,
      colores: cols,
      promociones: promos,
    );
  }

  Map<String, dynamic> toDbMap() => {
        'empresa_id': empresaId,
        'empresa_codigo': empresaCodigo,
        'catalogo_version': catalogoVersion,
        'generado_en': generadoEn,
        'guardado_local_en': guardadoLocalEn ?? DateTime.now().toUtc().toIso8601String(),
        'ambito_sucursales': jsonEncode(ambitoSucursales),
        'valido': valido ? 1 : 0,
      };
}

class CatalogoProductoLocal {
  final String id;
  final String empresaId;
  final String? categoriaId;
  final String nombre;
  final String? descripcion;
  final String precioBaseBob;
  final String imagenesJson;
  final List<CatalogoVarianteLocal> variantes;

  CatalogoProductoLocal({
    required this.id,
    required this.empresaId,
    this.categoriaId,
    required this.nombre,
    this.descripcion,
    required this.precioBaseBob,
    required this.imagenesJson,
    this.variantes = const [],
  });

  factory CatalogoProductoLocal.fromJson(Map<String, dynamic> j, {required String empresaId}) {
    final prodId = '${j['id'] ?? ''}';
    final varsRaw = (j['variantes'] as List?) ?? [];
    final vars = <CatalogoVarianteLocal>[];
    for (final v in varsRaw) {
      if (v is Map) {
        vars.add(CatalogoVarianteLocal.fromJson(v.cast<String, dynamic>(), productoId: prodId));
      }
    }

    String imgJson = '[]';
    if (j['imagenes'] != null) {
      if (j['imagenes'] is String) {
        imgJson = j['imagenes'] as String;
      } else {
        imgJson = jsonEncode(j['imagenes']);
      }
    }

    return CatalogoProductoLocal(
      id: prodId,
      empresaId: empresaId,
      categoriaId: j['categoria_id']?.toString(),
      nombre: '${j['nombre'] ?? 'Prenda'}',
      descripcion: j['descripcion'] as String?,
      precioBaseBob: '${j['precio_base_bob'] ?? j['precio_base'] ?? '0.00'}',
      imagenesJson: imgJson,
      variantes: vars,
    );
  }

  Map<String, dynamic> toDbMap() => {
        'id': id,
        'empresa_id': empresaId,
        'categoria_id': categoriaId,
        'nombre': nombre,
        'descripcion': descripcion,
        'precio_base_bob': precioBaseBob,
        'imagenes_json': imagenesJson,
      };
}

class CatalogoVarianteLocal {
  final String id;
  final String productoId;
  final String sku;
  final String tallaId;
  final String talla;
  final String colorId;
  final String color;
  final String? codigoHex;
  final String precioBob;
  final int disponibilidad;
  final String disponibilidadPorSucursalJson;

  CatalogoVarianteLocal({
    required this.id,
    required this.productoId,
    required this.sku,
    required this.tallaId,
    required this.talla,
    required this.colorId,
    required this.color,
    this.codigoHex,
    required this.precioBob,
    this.disponibilidad = 0,
    required this.disponibilidadPorSucursalJson,
  });

  factory CatalogoVarianteLocal.fromJson(Map<String, dynamic> j, {required String productoId}) {
    String dispJson = '[]';
    if (j['disponibilidad_por_sucursal'] != null) {
      if (j['disponibilidad_por_sucursal'] is String) {
        dispJson = j['disponibilidad_por_sucursal'] as String;
      } else {
        dispJson = jsonEncode(j['disponibilidad_por_sucursal']);
      }
    }

    return CatalogoVarianteLocal(
      id: '${j['id'] ?? ''}',
      productoId: productoId,
      sku: '${j['sku'] ?? ''}',
      tallaId: '${j['talla_id'] ?? ''}',
      talla: '${j['talla'] ?? ''}',
      colorId: '${j['color_id'] ?? ''}',
      color: '${j['color'] ?? ''}',
      codigoHex: j['codigo_hex'] as String?,
      precioBob: '${j['precio_bob'] ?? j['precio'] ?? '0.00'}',
      disponibilidad: (j['disponibilidad'] as num?)?.toInt() ?? 0,
      disponibilidadPorSucursalJson: dispJson,
    );
  }

  Map<String, dynamic> toDbMap() => {
        'id': id,
        'producto_id': productoId,
        'sku': sku,
        'talla_id': tallaId,
        'talla': talla,
        'color_id': colorId,
        'color': color,
        'codigo_hex': codigoHex,
        'precio_bob': precioBob,
        'disponibilidad': disponibilidad,
        'disponibilidad_por_sucursal_json': disponibilidadPorSucursalJson,
      };
}

class CatalogoColorLocal {
  final String id;
  final String empresaId;
  final String nombre;
  final String componentesJson;

  CatalogoColorLocal({
    required this.id,
    required this.empresaId,
    required this.nombre,
    required this.componentesJson,
  });

  factory CatalogoColorLocal.fromJson(Map<String, dynamic> j, {required String empresaId}) {
    String compJson = '[]';
    if (j['componentes'] != null) {
      if (j['componentes'] is String) {
        compJson = j['componentes'] as String;
      } else {
        compJson = jsonEncode(j['componentes']);
      }
    }

    return CatalogoColorLocal(
      id: '${j['id'] ?? ''}',
      empresaId: empresaId,
      nombre: '${j['nombre'] ?? ''}',
      componentesJson: compJson,
    );
  }

  Map<String, dynamic> toDbMap() => {
        'id': id,
        'empresa_id': empresaId,
        'nombre': nombre,
        'componentes_json': componentesJson,
      };
}

class CatalogoPromocionLocal {
  final String id;
  final String empresaId;
  final String tipo;
  final String valor;
  final int cantidadMinima;
  final String? vigenteDesde;
  final String? vigenteHasta;
  final String varianteIdsJson;

  CatalogoPromocionLocal({
    required this.id,
    required this.empresaId,
    required this.tipo,
    required this.valor,
    required this.cantidadMinima,
    this.vigenteDesde,
    this.vigenteHasta,
    required this.varianteIdsJson,
  });

  factory CatalogoPromocionLocal.fromJson(Map<String, dynamic> j, {required String empresaId}) {
    String varsJson = '[]';
    if (j['variante_ids'] != null) {
      if (j['variante_ids'] is String) {
        varsJson = j['variante_ids'] as String;
      } else {
        varsJson = jsonEncode(j['variante_ids']);
      }
    }

    return CatalogoPromocionLocal(
      id: '${j['id'] ?? ''}',
      empresaId: empresaId,
      tipo: '${j['tipo'] ?? 'PORCENTAJE'}',
      valor: '${j['valor'] ?? '0.00'}',
      cantidadMinima: (j['cantidad_minima'] as num?)?.toInt() ?? 1,
      vigenteDesde: j['vigente_desde'] as String?,
      vigenteHasta: j['vigente_hasta'] as String?,
      varianteIdsJson: varsJson,
    );
  }

  Map<String, dynamic> toDbMap() => {
        'id': id,
        'empresa_id': empresaId,
        'tipo': tipo,
        'valor': valor,
        'cantidad_minima': cantidadMinima,
        'vigente_desde': vigenteDesde,
        'vigente_hasta': vigenteHasta,
        'variante_ids_json': varianteIdsJson,
      };
}

/// Metadatos del snapshot activo retornado de SQLite
class SnapshotMetadata {
  final String empresaId;
  final String empresaCodigo;
  final int catalogoVersion;
  final String generadoEn;
  final String guardadoLocalEn;
  final List<String> ambitoSucursales;
  final bool valido;

  SnapshotMetadata({
    required this.empresaId,
    required this.empresaCodigo,
    required this.catalogoVersion,
    required this.generadoEn,
    required this.guardadoLocalEn,
    required this.ambitoSucursales,
    required this.valido,
  });

  factory SnapshotMetadata.fromDb(Map<String, dynamic> m) {
    List<String> ambitos = [];
    if (m['ambito_sucursales'] is String && (m['ambito_sucursales'] as String).isNotEmpty) {
      try {
        final decoded = jsonDecode(m['ambito_sucursales'] as String);
        if (decoded is List) {
          ambitos = decoded.map((e) => '$e').toList();
        }
      } catch (_) {}
    }

    return SnapshotMetadata(
      empresaId: '${m['empresa_id'] ?? ''}',
      empresaCodigo: '${m['empresa_codigo'] ?? ''}',
      catalogoVersion: (m['catalogo_version'] as num?)?.toInt() ?? 1,
      generadoEn: '${m['generado_en'] ?? ''}',
      guardadoLocalEn: '${m['guardado_local_en'] ?? ''}',
      ambitoSucursales: ambitos,
      valido: (m['valido'] as num?)?.toInt() == 1,
    );
  }
}
