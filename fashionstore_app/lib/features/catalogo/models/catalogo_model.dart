// Modelos del catálogo (contrato real del backend, Ciclo 1 + CU06).

double _aDouble(dynamic v, [double fb = 0]) {
  if (v == null) return fb;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? fb;
}

DateTime? _aFecha(dynamic v) {
  if (v == null) return null;
  if (v is DateTime) return v;
  return DateTime.tryParse(v.toString());
}

class ImagenProducto {
  final String id;
  final String productoId;
  final String enlace;
  final String? textoAlternativo;
  final int orden;
  final bool esPrincipal;

  ImagenProducto({
    required this.id,
    required this.productoId,
    required this.enlace,
    this.textoAlternativo,
    required this.orden,
    required this.esPrincipal,
  });

  factory ImagenProducto.fromJson(Map<String, dynamic> j) => ImagenProducto(
        id: '${j['id'] ?? ''}',
        productoId: '${j['producto_id'] ?? ''}',
        enlace: '${j['enlace_imagen'] ?? ''}',
        textoAlternativo: j['texto_alternativo'] as String?,
        orden: (j['orden'] as num?)?.toInt() ?? 0,
        esPrincipal: j['es_principal'] == true,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'producto_id': productoId,
        'enlace_imagen': enlace,
        'texto_alternativo': textoAlternativo,
        'orden': orden,
        'es_principal': esPrincipal,
      };
}

class Producto {
  final String id;
  final String? categoriaId;
  final String nombre;
  final String? descripcion;
  final String? genero;
  final String? marca;
  final double precioBase;
  final bool activo;
  final List<ImagenProducto> imagenes;
  final List<String> temporadaIds;
  final List<String> coleccionIds;

  Producto({
    required this.id,
    this.categoriaId,
    required this.nombre,
    this.descripcion,
    this.genero,
    this.marca,
    required this.precioBase,
    required this.activo,
    required this.imagenes,
    required this.temporadaIds,
    required this.coleccionIds,
  });

  factory Producto.fromJson(Map<String, dynamic> j) => Producto(
        id: '${j['id'] ?? ''}',
        categoriaId: j['categoria_id']?.toString(),
        nombre: '${j['nombre'] ?? 'Prenda'}',
        descripcion: j['descripcion'] as String?,
        genero: j['genero'] as String?,
        marca: j['marca'] as String?,
        precioBase: _aDouble(j['precio_base']),
        activo: j['activo'] != false,
        imagenes: ((j['imagenes'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => ImagenProducto.fromJson(e.cast<String, dynamic>()))
            .toList(),
        temporadaIds:
            ((j['temporada_ids'] as List?) ?? []).map((e) => '$e').toList(),
        coleccionIds:
            ((j['coleccion_ids'] as List?) ?? []).map((e) => '$e').toList(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'categoria_id': categoriaId,
        'nombre': nombre,
        'descripcion': descripcion,
        'genero': genero,
        'marca': marca,
        'precio_base': precioBase,
        'activo': activo,
        'imagenes': imagenes.map((e) => e.toJson()).toList(),
        'temporada_ids': temporadaIds,
        'coleccion_ids': coleccionIds,
      };

  String get imagenPrincipal {
    if (imagenes.isEmpty) return '';
    final p = imagenes.where((e) => e.esPrincipal);
    return (p.isNotEmpty ? p.first : imagenes.first).enlace;
  }

  /// Primera imagen de la galería ordenada de la prenda (CU17 / Decart):
  /// 1. Si existe imagen principal, ocupa la primera posición.
  /// 2. Si hay propiedad de orden, utiliza el menor orden.
  /// 3. Exclusivamente HTTPS; retorna null si no cumple para no enviar datos inválidos.
  String? get primeraImagenOrdenada {
    if (imagenes.isEmpty) return null;
    final ordenadas = List<ImagenProducto>.from(imagenes);
    ordenadas.sort((a, b) {
      if (a.esPrincipal != b.esPrincipal) {
        return a.esPrincipal ? -1 : 1;
      }
      return a.orden.compareTo(b.orden);
    });
    final enlace = ordenadas.first.enlace.trim();
    if (enlace.toLowerCase().startsWith('https://')) {
      return enlace;
    }
    return null;
  }
}

class Variante {
  final String id;
  final String productoId;
  final String tallaId;
  final String colorId;
  final String sku;
  final String? codigoBarras;
  final double precio;
  final bool activa;

  Variante({
    required this.id,
    required this.productoId,
    required this.tallaId,
    required this.colorId,
    required this.sku,
    this.codigoBarras,
    required this.precio,
    required this.activa,
  });

  factory Variante.fromJson(Map<String, dynamic> j) => Variante(
        id: '${j['id'] ?? ''}',
        productoId: '${j['producto_id'] ?? ''}',
        tallaId: '${j['talla_id'] ?? ''}',
        colorId: '${j['color_id'] ?? ''}',
        sku: '${j['sku'] ?? ''}',
        codigoBarras: j['codigo_barras']?.toString(),
        precio: _aDouble(j['precio']),
        activa: j['activa'] != false,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'producto_id': productoId,
        'talla_id': tallaId,
        'color_id': colorId,
        'sku': sku,
        'codigo_barras': codigoBarras,
        'precio': precio,
        'activa': activa,
      };
}

class OpcionSimple {
  final String id;
  final String nombre;
  OpcionSimple({required this.id, required this.nombre});
  factory OpcionSimple.fromJson(Map<String, dynamic> j) =>
      OpcionSimple(id: '${j['id'] ?? ''}', nombre: '${j['nombre'] ?? ''}');
  Map<String, dynamic> toJson() => {'id': id, 'nombre': nombre};
}

class OpcionTalla extends OpcionSimple {
  final int orden;
  OpcionTalla({required super.id, required super.nombre, required this.orden});
  factory OpcionTalla.fromJson(Map<String, dynamic> j) => OpcionTalla(
        id: '${j['id'] ?? ''}',
        nombre: '${j['nombre'] ?? ''}',
        orden: (j['orden'] as num?)?.toInt() ?? 0,
      );
  @override
  Map<String, dynamic> toJson() => {'id': id, 'nombre': nombre, 'orden': orden};
}

class OpcionColor extends OpcionSimple {
  final String? codigoHex;
  OpcionColor({required super.id, required super.nombre, this.codigoHex});
  factory OpcionColor.fromJson(Map<String, dynamic> j) => OpcionColor(
        id: '${j['id'] ?? ''}',
        nombre: '${j['nombre'] ?? ''}',
        codigoHex: j['codigo_hex'] as String?,
      );
  @override
  Map<String, dynamic> toJson() =>
      {'id': id, 'nombre': nombre, 'codigo_hex': codigoHex};
}

/// Opciones de filtros del catálogo (GET /catalogo/filtros-opciones).
class FiltrosOpciones {
  final List<OpcionSimple> categorias;
  final List<OpcionTalla> tallas;
  final List<OpcionColor> colores;
  final List<OpcionSimple> temporadas;
  final List<OpcionSimple> colecciones;
  final List<String> generos;
  final List<String> marcas;

  FiltrosOpciones({
    required this.categorias,
    required this.tallas,
    required this.colores,
    required this.temporadas,
    required this.colecciones,
    required this.generos,
    required this.marcas,
  });

  factory FiltrosOpciones.vacio() => FiltrosOpciones(
        categorias: const [],
        tallas: const [],
        colores: const [],
        temporadas: const [],
        colecciones: const [],
        generos: const [],
        marcas: const [],
      );

  factory FiltrosOpciones.fromJson(Map<String, dynamic> j) => FiltrosOpciones(
        categorias: ((j['categorias'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => OpcionSimple.fromJson(e.cast<String, dynamic>()))
            .toList(),
        tallas: ((j['tallas'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => OpcionTalla.fromJson(e.cast<String, dynamic>()))
            .toList(),
        colores: ((j['colores'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => OpcionColor.fromJson(e.cast<String, dynamic>()))
            .toList(),
        temporadas: ((j['temporadas'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => OpcionSimple.fromJson(e.cast<String, dynamic>()))
            .toList(),
        colecciones: ((j['colecciones'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => OpcionSimple.fromJson(e.cast<String, dynamic>()))
            .toList(),
        generos: ((j['generos'] as List?) ?? []).map((e) => '$e').toList(),
        marcas: ((j['marcas'] as List?) ?? []).map((e) => '$e').toList(),
      );

  Map<String, dynamic> toJson() => {
        'categorias': categorias.map((e) => e.toJson()).toList(),
        'tallas': tallas.map((e) => e.toJson()).toList(),
        'colores': colores.map((e) => e.toJson()).toList(),
        'temporadas': temporadas.map((e) => e.toJson()).toList(),
        'colecciones': colecciones.map((e) => e.toJson()).toList(),
        'generos': generos,
        'marcas': marcas,
      };
}

/// Disponibilidad por sucursal (GET /variantes/{id}/disponibilidad y alias).
class DisponibilidadSucursal {
  final String inventarioId;
  final String varianteId;
  final String sucursalId;
  final String sucursalNombre;
  final String ciudadId;
  final String ciudadNombre;
  final String? direccion;
  final String? telefono;
  final int disponible;
  final int reservado;
  final int comprometidoTraslado;
  final int enTransito;
  final DateTime? actualizadoEn;

  DisponibilidadSucursal({
    required this.inventarioId,
    required this.varianteId,
    required this.sucursalId,
    required this.sucursalNombre,
    required this.ciudadId,
    required this.ciudadNombre,
    this.direccion,
    this.telefono,
    required this.disponible,
    required this.reservado,
    required this.comprometidoTraslado,
    required this.enTransito,
    this.actualizadoEn,
  });

  factory DisponibilidadSucursal.fromJson(Map<String, dynamic> j) =>
      DisponibilidadSucursal(
        inventarioId: '${j['inventario_id'] ?? ''}',
        varianteId: '${j['variante_id'] ?? ''}',
        sucursalId: '${j['sucursal_id'] ?? ''}',
        sucursalNombre: '${j['sucursal_nombre'] ?? 'Sucursal'}',
        ciudadId: '${j['ciudad_id'] ?? ''}',
        ciudadNombre: '${j['ciudad_nombre'] ?? ''}',
        direccion: j['direccion'] as String?,
        telefono: j['telefono'] as String?,
        disponible: (j['disponible'] as num?)?.toInt() ?? 0,
        reservado: (j['reservado'] as num?)?.toInt() ?? 0,
        comprometidoTraslado:
            (j['comprometido_traslado'] as num?)?.toInt() ?? 0,
        enTransito: (j['en_transito'] as num?)?.toInt() ?? 0,
        actualizadoEn: _aFecha(j['actualizado_en']),
      );

  Map<String, dynamic> toJson() => {
        'inventario_id': inventarioId,
        'variante_id': varianteId,
        'sucursal_id': sucursalId,
        'sucursal_nombre': sucursalNombre,
        'ciudad_id': ciudadId,
        'ciudad_nombre': ciudadNombre,
        'direccion': direccion,
        'telefono': telefono,
        'disponible': disponible,
        'reservado': reservado,
        'comprometido_traslado': comprometidoTraslado,
        'en_transito': enTransito,
        'actualizado_en': actualizadoEn?.toIso8601String(),
      };
}

/// Filtros del catálogo para la búsqueda.
class FiltrosCatalogo {
  String texto;
  String? categoriaId;
  String? tallaId;
  String? colorId;
  String? temporadaId;
  String? coleccionId;
  String? marca;
  String? genero;
  double? precioMin;
  double? precioMax;

  FiltrosCatalogo({
    this.texto = '',
    this.categoriaId,
    this.tallaId,
    this.colorId,
    this.temporadaId,
    this.coleccionId,
    this.marca,
    this.genero,
    this.precioMin,
    this.precioMax,
  });

  bool get tieneFiltros =>
      texto.trim().isNotEmpty ||
      categoriaId != null ||
      tallaId != null ||
      colorId != null ||
      temporadaId != null ||
      coleccionId != null ||
      (marca != null && marca!.isNotEmpty) ||
      (genero != null && genero!.isNotEmpty) ||
      precioMin != null ||
      precioMax != null;

  Map<String, String> toQuery({required int limit, required int offset}) {
    final q = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
    };
    if (texto.trim().isNotEmpty) q['texto'] = texto.trim();
    if (categoriaId != null) q['categoria_id'] = categoriaId!;
    if (tallaId != null) q['talla_id'] = tallaId!;
    if (colorId != null) q['color_id'] = colorId!;
    if (temporadaId != null) q['temporada_id'] = temporadaId!;
    if (coleccionId != null) q['coleccion_id'] = coleccionId!;
    if (marca != null && marca!.isNotEmpty) q['marca'] = marca!;
    if (genero != null && genero!.isNotEmpty) q['genero'] = genero!;
    if (precioMin != null) q['precio_min'] = '${precioMin!}';
    if (precioMax != null) q['precio_max'] = '${precioMax!}';
    return q;
  }
}
