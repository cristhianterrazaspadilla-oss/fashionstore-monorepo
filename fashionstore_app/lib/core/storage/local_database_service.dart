import 'dart:convert';
import 'dart:io' show Platform;
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../../features/catalogo/models/catalogo_model.dart';
import '../../features/catalogo/models/catalogo_snapshot_model.dart';
import '../../features/reservas_traslados/models/sincronizacion_model.dart';
import '../../features/ventas_pagos/models/caja_model.dart';

/// Servicio de almacenamiento local SQLite para CU03 (snapshot), CU16 (consulta offline),
/// CU04 (cola de sincronización de reservas) y CU06/CU07 (persistencia durable de caja offline).
///
/// Soporta Android/iOS y tests/escritorio vía sqflite_common_ffi.
class LocalDatabaseService {
  static const int _dbVersion = 2;
  static const String _defaultDbName = 'fashionstore.db';
  static bool _ffiInitialized = false;

  final Database? _overrideDb;
  final String? _dbName;
  Database? _db;
  Future<Database>? _apertura;

  LocalDatabaseService({Database? db, String? dbName})
      : _overrideDb = db,
        _dbName = dbName;

  DatabaseFactory get _activeFactory {
    if (!kIsWeb && (Platform.isWindows || Platform.isLinux || Platform.isMacOS)) {
      if (!_ffiInitialized) {
        sqfliteFfiInit();
        databaseFactory = databaseFactoryFfiNoIsolate;
        _ffiInitialized = true;
      }
      return databaseFactoryFfiNoIsolate;
    }
    return databaseFactory;
  }

  Future<void> close() async {
    if (_db != null && _db!.isOpen) {
      await _db!.close();
      _db = null;
      _apertura = null;
    }
  }

  Future<void> limpiarTodo() async {
    final db = await database;
    await db.delete('catalogo_snapshots');
    await db.delete('catalogo_productos');
    await db.delete('catalogo_variantes');
    await db.delete('catalogo_colores');
    await db.delete('catalogo_promociones');
    await db.delete('referencias_horarias');
    await db.delete('cola_sincronizacion');
    await db.delete('caja_turnos_activos');
    await db.delete('caja_cupos');
    await db.delete('caja_ventas_offline');
    await db.delete('caja_comprobantes_locales');
  }

  static bool get isTestEnvironment =>
      Platform.environment.containsKey('FLUTTER_TEST');

  Future<Database> get database => _apertura ??= _abrirDatabase();

  Future<Database> _abrirDatabase() async {
    if (_overrideDb != null) {
      await _crearTablasCaja(_overrideDb);
      return _overrideDb;
    }
    if (_db != null && _db!.isOpen) return _db!;

    final factory = _activeFactory;
    final name = _dbName ?? (isTestEnvironment ? inMemoryDatabasePath : _defaultDbName);

    if (name == inMemoryDatabasePath) {
      _db = await factory.openDatabase(
        inMemoryDatabasePath,
        options: OpenDatabaseOptions(
          version: _dbVersion,
          onCreate: _onCreate,
          onUpgrade: _onUpgrade,
        ),
      );
    } else {
      final dbPath = await factory.getDatabasesPath();
      final path = p.isAbsolute(name) ? name : p.join(dbPath, name);
      _db = await factory.openDatabase(
        path,
        options: OpenDatabaseOptions(
          version: _dbVersion,
          onCreate: _onCreate,
          onUpgrade: _onUpgrade,
        ),
      );
    }
    await _crearTablasCaja(_db!);
    return _db!;
  }

  Future<void> _onCreate(Database db, int version) async {
    // 1. Tablas principales de Catálogo (CU03 / CU16)
    await db.execute('''
      CREATE TABLE IF NOT EXISTS catalogo_snapshots (
        empresa_id TEXT PRIMARY KEY,
        empresa_codigo TEXT,
        catalogo_version INTEGER,
        generado_en TEXT,
        guardado_local_en TEXT,
        ambito_sucursales TEXT,
        valido INTEGER
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS catalogo_productos (
        id TEXT PRIMARY KEY,
        empresa_id TEXT,
        categoria_id TEXT,
        nombre TEXT,
        descripcion TEXT,
        precio_base_bob TEXT,
        imagenes_json TEXT
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS catalogo_variantes (
        id TEXT PRIMARY KEY,
        producto_id TEXT,
        sku TEXT,
        talla_id TEXT,
        talla TEXT,
        color_id TEXT,
        color TEXT,
        codigo_hex TEXT,
        precio_bob TEXT,
        disponibilidad INTEGER,
        disponibilidad_por_sucursal_json TEXT
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS catalogo_colores (
        id TEXT PRIMARY KEY,
        empresa_id TEXT,
        nombre TEXT,
        componentes_json TEXT
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS catalogo_promociones (
        id TEXT PRIMARY KEY,
        empresa_id TEXT,
        tipo TEXT,
        valor TEXT,
        cantidad_minima INTEGER,
        vigente_desde TEXT,
        vigente_hasta TEXT,
        variante_ids_json TEXT
      );
    ''');

    // 2. Tablas staging para escritura atómica (CU03)
    await db.execute('''
      CREATE TABLE IF NOT EXISTS staging_catalogo_snapshots (
        empresa_id TEXT PRIMARY KEY,
        empresa_codigo TEXT,
        catalogo_version INTEGER,
        generado_en TEXT,
        guardado_local_en TEXT,
        ambito_sucursales TEXT,
        valido INTEGER
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS staging_catalogo_productos (
        id TEXT PRIMARY KEY,
        empresa_id TEXT,
        categoria_id TEXT,
        nombre TEXT,
        descripcion TEXT,
        precio_base_bob TEXT,
        imagenes_json TEXT
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS staging_catalogo_variantes (
        id TEXT PRIMARY KEY,
        producto_id TEXT,
        sku TEXT,
        talla_id TEXT,
        talla TEXT,
        color_id TEXT,
        color TEXT,
        codigo_hex TEXT,
        precio_bob TEXT,
        disponibilidad INTEGER,
        disponibilidad_por_sucursal_json TEXT
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS staging_catalogo_colores (
        id TEXT PRIMARY KEY,
        empresa_id TEXT,
        nombre TEXT,
        componentes_json TEXT
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS staging_catalogo_promociones (
        id TEXT PRIMARY KEY,
        empresa_id TEXT,
        tipo TEXT,
        valor TEXT,
        cantidad_minima INTEGER,
        vigente_desde TEXT,
        vigente_hasta TEXT,
        variante_ids_json TEXT
      );
    ''');

    // 3. Tablas de Sincronización Offline (CU04)
    await db.execute('''
      CREATE TABLE IF NOT EXISTS referencias_horarias (
        id TEXT PRIMARY KEY,
        empresa_id TEXT,
        usuario_id TEXT,
        dispositivo_id TEXT,
        hora_central_en TEXT,
        valida_hasta TEXT,
        tolerancia_segundos INTEGER,
        politica_version INTEGER,
        emitida_en TEXT
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS cola_sincronizacion (
        operacion_id TEXT PRIMARY KEY,
        empresa_id TEXT,
        usuario_id TEXT,
        dispositivo_id TEXT,
        secuencia_local INTEGER,
        referencia_horaria_id TEXT,
        creada_local_en TEXT,
        datos_json TEXT,
        estado_envio TEXT,
        resultado_json TEXT,
        actualizado_en TEXT
      );
    ''');

    // Índices
    await db.execute('CREATE INDEX IF NOT EXISTS idx_prod_emp ON catalogo_productos(empresa_id);');
    await db.execute('CREATE INDEX IF NOT EXISTS idx_prod_cat ON catalogo_productos(categoria_id);');
    await db.execute('CREATE INDEX IF NOT EXISTS idx_var_prod ON catalogo_variantes(producto_id);');
    await db.execute('CREATE INDEX IF NOT EXISTS idx_var_col ON catalogo_variantes(color_id);');
    await db.execute('CREATE INDEX IF NOT EXISTS idx_cola_envio ON cola_sincronizacion(empresa_id, usuario_id, estado_envio);');
    await db.execute('CREATE INDEX IF NOT EXISTS idx_ref_usr ON referencias_horarias(empresa_id, usuario_id);');

    // 4. Tablas de Caja Offline (CU06 / CU07)
    await _crearTablasCaja(db);
  }

  Future<void> _crearTablasCaja(Database db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS caja_turnos_activos (
        turno_id TEXT PRIMARY KEY,
        empresa_id TEXT,
        usuario_id TEXT,
        dispositivo_id TEXT,
        habilitacion_id TEXT,
        caja_codigo TEXT,
        sucursal_id TEXT,
        cajero_id TEXT,
        estado TEXT,
        inicio_en TEXT,
        vence_en TEXT,
        version_precios TEXT,
        revision INTEGER,
        snapshot_json TEXT,
        actualizado_en TEXT
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS caja_cupos (
        turno_id TEXT,
        variante_id TEXT,
        sku TEXT,
        producto_nombre TEXT,
        otorgado INTEGER,
        consumido INTEGER,
        liberado INTEGER,
        precio_autorizado_bob TEXT,
        PRIMARY KEY (turno_id, variante_id)
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS caja_ventas_offline (
        operacion_id TEXT PRIMARY KEY,
        turno_id TEXT,
        empresa_id TEXT,
        usuario_id TEXT,
        dispositivo_id TEXT,
        secuencia_local INTEGER,
        vendida_local_en TEXT,
        entregada_local_en TEXT,
        version_precios TEXT,
        total_bob TEXT,
        efectivo_recibido_bob TEXT,
        cambio_entregado_bob TEXT,
        cliente_id TEXT,
        lineas_json TEXT,
        estado_sincronizacion TEXT,
        comprobante_local_id TEXT,
        sincronizada_en TEXT,
        resultado_json TEXT,
        error_mensaje TEXT
      );
    ''');

    await db.execute('''
      CREATE TABLE IF NOT EXISTS caja_comprobantes_locales (
        comprobante_id TEXT PRIMARY KEY,
        operacion_id TEXT,
        turno_id TEXT,
        empresa_id TEXT,
        numero_comprobante TEXT,
        total_bob TEXT,
        efectivo_recibido_bob TEXT,
        cambio_bob TEXT,
        emitido_en TEXT,
        lineas_resumen_json TEXT
      );
    ''');

    await db.execute('CREATE INDEX IF NOT EXISTS idx_caja_turno_emp_disp ON caja_turnos_activos(empresa_id, dispositivo_id);');
    await db.execute('CREATE INDEX IF NOT EXISTS idx_caja_cupo_turno ON caja_cupos(turno_id);');
    await db.execute('CREATE INDEX IF NOT EXISTS idx_caja_ventas_cola ON caja_ventas_offline(empresa_id, estado_sincronizacion);');
    await db.execute('CREATE INDEX IF NOT EXISTS idx_caja_comp_turno ON caja_comprobantes_locales(turno_id);');
    await _migrarCajaV2(db);
  }

  Future<void> _migrarCajaV2(Database db) async {
    final columnas = <String, Map<String, String>>{
      'caja_turnos_activos': {'desfase_ms': 'INTEGER', 'ultimo_reloj_ms': 'INTEGER', 'hora_central_ms': 'INTEGER',
        'origen_verificado': 'INTEGER NOT NULL DEFAULT 0', 'activo_local': 'INTEGER NOT NULL DEFAULT 1'},
      'caja_cupos': {'mermado': 'INTEGER NOT NULL DEFAULT 0'},
      'caja_ventas_offline': {'cuerpo_json': 'TEXT', 'huella': 'TEXT',
        'recuperacion_requerida': 'INTEGER NOT NULL DEFAULT 1', 'diagnostico': 'TEXT'},
    };
    for (final tabla in columnas.entries) {
      final existentes = (await db.rawQuery('PRAGMA table_info(${tabla.key})')).map((r) => r['name']).toSet();
      for (final columna in tabla.value.entries) {
        if (!existentes.contains(columna.key)) await db.execute('ALTER TABLE ${tabla.key} ADD COLUMN ${columna.key} ${columna.value}');
      }
    }
  }

  String _canonicoCaja(dynamic valor) {
    dynamic ordenar(dynamic v) {
      if (v is Map) { final claves = v.keys.map((k) => k.toString()).toList()..sort(); return {for (final k in claves) k: ordenar(v[k])}; }
      if (v is List) return v.map(ordenar).toList();
      return v;
    }
    return jsonEncode(ordenar(valor));
  }

  void _exigirContextoCaja(String empresa, String? usuario, String? dispositivo) {
    if (empresa.isEmpty || usuario == null || usuario.isEmpty || dispositivo == null || dispositivo.isEmpty) {
      throw StateError('Caja requiere empresa, usuario y dispositivo originales.');
    }
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    // Las migraciones locales NUNCA eliminan la tabla cola_sincronizacion ni referencias_horarias.
    // Preservan los pendientes existentes de los usuarios.
    await _crearTablasCaja(db);
  }

  // -------------------------------------------------------------
  // CU03: GUARDADO ATÓMICO DE SNAPSHOT VÍA STAGING
  // -------------------------------------------------------------

  /// Guarda el snapshot completo en staging y activa la nueva versión atómicamente.
  /// Si ocurre un fallo antes del commit, la copia previa permanece activa e intacta.
  Future<void> guardarSnapshot({
    required CatalogoSnapshotModel snapshot,
    bool simularFalloAntesDeCommit = false,
  }) async {
    final db = await database;

    // 1. Limpiar staging previo para esta empresa
    await db.delete('staging_catalogo_snapshots', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
    await db.rawDelete(
      'DELETE FROM staging_catalogo_variantes WHERE producto_id IN (SELECT id FROM staging_catalogo_productos WHERE empresa_id = ?)',
      [snapshot.empresaId],
    );
    await db.delete('staging_catalogo_productos', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
    await db.delete('staging_catalogo_colores', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
    await db.delete('staging_catalogo_promociones', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);

    // 2. Insertar en tablas de staging
    await db.insert('staging_catalogo_snapshots', snapshot.toDbMap());

    for (final prod in snapshot.productos) {
      await db.insert('staging_catalogo_productos', prod.toDbMap());
      for (final v in prod.variantes) {
        await db.insert('staging_catalogo_variantes', v.toDbMap());
      }
    }

    for (final col in snapshot.colores) {
      await db.insert('staging_catalogo_colores', col.toDbMap());
    }

    for (final promo in snapshot.promociones) {
      await db.insert('staging_catalogo_promociones', promo.toDbMap());
    }

    if (simularFalloAntesDeCommit) {
      throw Exception('Fallo simulado antes de activar snapshot.');
    }

    // 3. Transacción atómica de activación
    final ahoraUtc = DateTime.now().toUtc().toIso8601String();
    await db.transaction((txn) async {
      // Eliminar registros vigentes anteriores de esta empresa
      await txn.delete('catalogo_snapshots', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
      await txn.rawDelete(
        'DELETE FROM catalogo_variantes WHERE producto_id IN (SELECT id FROM catalogo_productos WHERE empresa_id = ?)',
        [snapshot.empresaId],
      );
      await txn.delete('catalogo_productos', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
      await txn.delete('catalogo_colores', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
      await txn.delete('catalogo_promociones', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);

      // Copiar staging a tablas principales y marcar como válido
      await txn.rawInsert('''
        INSERT INTO catalogo_snapshots (empresa_id, empresa_codigo, catalogo_version, generado_en, guardado_local_en, ambito_sucursales, valido)
        SELECT empresa_id, empresa_codigo, catalogo_version, generado_en, ?, ambito_sucursales, 1
        FROM staging_catalogo_snapshots WHERE empresa_id = ?;
      ''', [ahoraUtc, snapshot.empresaId]);

      await txn.rawInsert('''
        INSERT INTO catalogo_productos (id, empresa_id, categoria_id, nombre, descripcion, precio_base_bob, imagenes_json)
        SELECT id, empresa_id, categoria_id, nombre, descripcion, precio_base_bob, imagenes_json
        FROM staging_catalogo_productos WHERE empresa_id = ?;
      ''', [snapshot.empresaId]);

      await txn.rawInsert('''
        INSERT INTO catalogo_variantes (id, producto_id, sku, talla_id, talla, color_id, color, codigo_hex, precio_bob, disponibilidad, disponibilidad_por_sucursal_json)
        SELECT id, producto_id, sku, talla_id, talla, color_id, color, codigo_hex, precio_bob, disponibilidad, disponibilidad_por_sucursal_json
        FROM staging_catalogo_variantes WHERE producto_id IN (SELECT id FROM staging_catalogo_productos WHERE empresa_id = ?);
      ''', [snapshot.empresaId]);

      await txn.rawInsert('''
        INSERT INTO catalogo_colores (id, empresa_id, nombre, componentes_json)
        SELECT id, empresa_id, nombre, componentes_json
        FROM staging_catalogo_colores WHERE empresa_id = ?;
      ''', [snapshot.empresaId]);

      await txn.rawInsert('''
        INSERT INTO catalogo_promociones (id, empresa_id, tipo, valor, cantidad_minima, vigente_desde, vigente_hasta, variante_ids_json)
        SELECT id, empresa_id, tipo, valor, cantidad_minima, vigente_desde, vigente_hasta, variante_ids_json
        FROM staging_catalogo_promociones WHERE empresa_id = ?;
      ''', [snapshot.empresaId]);

      // Limpiar staging tras activación confirmada
      await txn.delete('staging_catalogo_snapshots', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
      await txn.rawDelete(
        'DELETE FROM staging_catalogo_variantes WHERE producto_id IN (SELECT id FROM staging_catalogo_productos WHERE empresa_id = ?)',
        [snapshot.empresaId],
      );
      await txn.delete('staging_catalogo_productos', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
      await txn.delete('staging_catalogo_colores', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
      await txn.delete('staging_catalogo_promociones', where: 'empresa_id = ?', whereArgs: [snapshot.empresaId]);
    });
  }

  /// Obtiene los metadatos de la copia local activa para la empresa (por ID o código).
  Future<SnapshotMetadata?> obtenerSnapshotActivo(String empresaCodigoOId) async {
    final db = await database;
    final res = await db.query(
      'catalogo_snapshots',
      where: '(empresa_id = ? OR empresa_codigo = ?) AND valido = 1',
      whereArgs: [empresaCodigoOId, empresaCodigoOId],
      limit: 1,
    );
    if (res.isEmpty) return null;
    return SnapshotMetadata.fromDb(res.first);
  }

  // -------------------------------------------------------------
  // CU16: CONSULTAR CATÁLOGO Y DISPONIBILIDAD OFFLINE (SQLITE)
  // -------------------------------------------------------------

  /// Ejecuta los mismos filtros del catálogo online sobre el snapshot local en SQLite.
  Future<ResultadoConsultaLocal> consultarCatalogoLocal({
    required String empresaCodigoOId,
    String? texto,
    String? categoriaId,
    String? tallaId,
    String? colorId,
    List<String>? componentesColor,
    String modoColor = 'EXACTO',
    double? precioMin,
    double? precioMax,
    int limit = 20,
    int offset = 0,
  }) async {
    final meta = await obtenerSnapshotActivo(empresaCodigoOId);
    if (meta == null) {
      return ResultadoConsultaLocal.sinSnapshot();
    }

    final db = await database;
    final empresaId = meta.empresaId;

    // Cargar colores de la empresa para resolver componentes compuestos si aplica
    final coloresRows = await db.query('catalogo_colores', where: 'empresa_id = ?', whereArgs: [empresaId]);
    final mapaColoresComponentes = <String, List<String>>{};
    for (final r in coloresRows) {
      final cid = '${r['id']}';
      final compStr = '${r['componentes_json'] ?? '[]'}';
      try {
        final decoded = jsonDecode(compStr);
        if (decoded is List) {
          final comps = <String>[];
          for (final item in decoded) {
            if (item is Map && item['color_id'] != null) {
              comps.add('${item['color_id']}');
            } else if (item is String) {
              comps.add(item);
            }
          }
          mapaColoresComponentes[cid] = comps;
        }
      } catch (_) {}
    }

    // Consulta de productos para esta empresa
    final whereClauses = <String>['empresa_id = ?', 'origen_verificado = 1', 'activo_local = 1'];
    final whereArgs = <dynamic>[empresaId];

    if (categoriaId != null && categoriaId.isNotEmpty) {
      whereClauses.add('categoria_id = ?');
      whereArgs.add(categoriaId);
    }

    if (texto != null && texto.trim().isNotEmpty) {
      whereClauses.add('(nombre LIKE ? OR descripcion LIKE ?)');
      final likePattern = '%${texto.trim()}%';
      whereArgs.add(likePattern);
      whereArgs.add(likePattern);
    }

    final prodRows = await db.query(
      'catalogo_productos',
      where: whereClauses.join(' AND '),
      whereArgs: whereArgs,
      orderBy: 'nombre ASC',
    );

    // Filtrar y armar productos con sus variantes
    final listaProductosFiltrados = <Producto>[];

    for (final pRow in prodRows) {
      final prodId = '${pRow['id']}';
      final varRows = await db.query(
        'catalogo_variantes',
        where: 'producto_id = ?',
        whereArgs: [prodId],
      );

      // Evaluar variantes según filtros de talla, color y precio
      final variantesCoincidentes = <Variante>[];
      for (final vRow in varRows) {
        final vPrecio = double.tryParse('${vRow['precio_bob']}') ?? 0.0;
        if (precioMin != null && vPrecio < precioMin) continue;
        if (precioMax != null && vPrecio > precioMax) continue;

        if (tallaId != null && tallaId.isNotEmpty) {
          if ('${vRow['talla_id']}' != tallaId) continue;
        }

        final vColorId = '${vRow['color_id']}';
        if (modoColor == 'TODOS_COMPONENTES' && componentesColor != null && componentesColor.isNotEmpty) {
          final comps = mapaColoresComponentes[vColorId] ?? [vColorId];
          final tieneTodos = componentesColor.every((req) => comps.contains(req));
          if (!tieneTodos) continue;
        } else if (colorId != null && colorId.isNotEmpty) {
          if (vColorId != colorId) continue;
        }

        variantesCoincidentes.add(
          Variante(
            id: '${vRow['id']}',
            productoId: prodId,
            tallaId: '${vRow['talla_id']}',
            colorId: vColorId,
            sku: '${vRow['sku']}',
            codigoBarras: vRow['codigo_hex']?.toString(),
            precio: vPrecio,
            activa: true,
          ),
        );
      }

      // Si se aplicaron filtros de variante y ninguna variante coincide, omitir producto
      final tieneFiltrosVariante = (tallaId != null && tallaId.isNotEmpty) ||
          (colorId != null && colorId.isNotEmpty) ||
          (componentesColor != null && componentesColor.isNotEmpty) ||
          precioMin != null ||
          precioMax != null;

      if (tieneFiltrosVariante && variantesCoincidentes.isEmpty) {
        continue;
      }

      // Deserializar imágenes
      final imgsJson = '${pRow['imagenes_json'] ?? '[]'}';
      final imagenes = <ImagenProducto>[];
      try {
        final decoded = jsonDecode(imgsJson);
        if (decoded is List) {
          for (final im in decoded) {
            if (im is Map) {
              imagenes.add(ImagenProducto.fromJson(im.cast<String, dynamic>()));
            }
          }
        }
      } catch (_) {}

      final basePrecio = double.tryParse('${pRow['precio_base_bob']}') ?? 0.0;

      listaProductosFiltrados.add(
        Producto(
          id: prodId,
          categoriaId: pRow['categoria_id']?.toString(),
          nombre: '${pRow['nombre']}',
          descripcion: pRow['descripcion']?.toString(),
          precioBase: basePrecio,
          activo: true,
          imagenes: imagenes,
          temporadaIds: const [],
          coleccionIds: const [],
        ),
      );
    }

    final total = listaProductosFiltrados.length;
    final paginados = listaProductosFiltrados.skip(offset).take(limit).toList();

    return ResultadoConsultaLocal(
      total: total,
      limit: limit,
      offset: offset,
      items: paginados,
      snapshot: meta,
      haySnapshot: true,
    );
  }

  /// Obtiene la disponibilidad conocida por sucursal de una variante desde SQLite.
  Future<List<DisponibilidadSucursal>> disponibilidadVarianteLocal(String varianteId) async {
    final db = await database;
    final rows = await db.query(
      'catalogo_variantes',
      where: 'id = ?',
      whereArgs: [varianteId],
      limit: 1,
    );
    if (rows.isEmpty) return const [];
    final jsonStr = '${rows.first['disponibilidad_por_sucursal_json'] ?? '[]'}';
    try {
      final decoded = jsonDecode(jsonStr);
      if (decoded is List) {
        return decoded
            .whereType<Map>()
            .map((e) => DisponibilidadSucursal.fromJson(e.cast<String, dynamic>()))
            .toList();
      }
    } catch (_) {}
    return const [];
  }

  // -------------------------------------------------------------
  // CU04: REFERENCIAS HORARIAS Y COLA DE SINCRONIZACIÓN OFFLINE
  // -------------------------------------------------------------

  Future<void> guardarReferenciaHoraria(ReferenciaHorariaModel ref) async {
    final db = await database;
    await db.insert(
      'referencias_horarias',
      ref.toDbMap(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<ReferenciaHorariaModel?> obtenerReferenciaHorariaValida({
    required String empresaId,
    String? usuarioId,
  }) async {
    final db = await database;
    String where = 'empresa_id = ?';
    final args = <dynamic>[empresaId];
    if (usuarioId != null && usuarioId.isNotEmpty) {
      where += ' AND usuario_id = ?';
      args.add(usuarioId);
    }
    final rows = await db.query(
      'referencias_horarias',
      where: where,
      whereArgs: args,
      orderBy: 'emitida_en DESC',
      limit: 1,
    );
    if (rows.isEmpty) return null;
    final r = ReferenciaHorariaModel.fromDb(rows.first);
    if (r.estaVencida) return null;
    return r;
  }

  Future<void> encolarOperacion(OperacionSincronizacionLocal op) async {
    final db = await database;
    await db.transaction((txn) async {
      await txn.insert(
        'cola_sincronizacion',
        op.toDbMap(),
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
    });
  }

  Future<List<OperacionSincronizacionLocal>> listarOperacionesCola({
    required String empresaId,
    String? usuarioId,
    List<String>? estados,
  }) async {
    final db = await database;
    String where = 'empresa_id = ?';
    final args = <dynamic>[empresaId];
    if (usuarioId != null && usuarioId.isNotEmpty) {
      where += ' AND usuario_id = ?';
      args.add(usuarioId);
    }

    if (estados != null && estados.isNotEmpty) {
      final placeholders = List.filled(estados.length, '?').join(', ');
      where += ' AND estado_envio IN ($placeholders)';
      args.addAll(estados);
    }

    final rows = await db.query(
      'cola_sincronizacion',
      where: where,
      whereArgs: args,
      orderBy: 'secuencia_local ASC',
    );
    return rows.map((m) => OperacionSincronizacionLocal.fromDb(m)).toList();
  }

  Future<OperacionSincronizacionLocal?> obtenerOperacion(String operacionId) async {
    final db = await database;
    final rows = await db.query(
      'cola_sincronizacion',
      where: 'operacion_id = ?',
      whereArgs: [operacionId],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    return OperacionSincronizacionLocal.fromDb(rows.first);
  }

  Future<void> actualizarEstadoOperacion(
    String operacionId,
    String nuevoEstado, {
    Map<String, dynamic>? resultadoJson,
    String? empresaId, String? usuarioId, String? dispositivoId,
  }) async {
    _exigirContextoCaja(empresaId ?? '', usuarioId, dispositivoId);
    final db = await database;
    final values = <String, dynamic>{
      'estado_envio': nuevoEstado,
      'actualizado_en': DateTime.now().toUtc().toIso8601String(),
    };
    if (resultadoJson != null) {
      values['resultado_json'] = jsonEncode(resultadoJson);
    }
    await db.update(
      'cola_sincronizacion',
      values,
      where: 'operacion_id = ?',
      whereArgs: [operacionId],
    );
  }

  Future<int> obtenerSiguienteSecuencia({
    required String dispositivoId,
    required String usuarioId,
  }) async {
    final db = await database;
    final res = await db.rawQuery('''
      SELECT MAX(secuencia_local) as max_sec
      FROM cola_sincronizacion
      WHERE dispositivo_id = ? AND usuario_id = ?;
    ''', [dispositivoId, usuarioId]);
    final maxSec = res.first['max_sec'];
    if (maxSec == null) return 1;
    return (maxSec as num).toInt() + 1;
  }

  // -------------------------------------------------------------
  // CU06 / CU07: PERSISTENCIA DURABLE DE CAJA OFFLINE (SQLITE)
  // -------------------------------------------------------------

  Future<void> guardarTurnoActivoLocal(
    TurnoHabilitacionModel turno, {
    required String empresaId,
    required String usuarioId,
  }) async {
    final db = await database;
    final ahoraUtc = DateTime.now().toUtc().toIso8601String();
    await db.transaction((txn) async {
      final anteriores = await txn.query('caja_turnos_activos', where: 'turno_id = ?', whereArgs: [turno.turnoId]);
      final previo = anteriores.isEmpty ? null : anteriores.first;
      if (previo != null && previo['origen_verificado'] == 1 &&
          (previo['empresa_id'] != empresaId || previo['usuario_id'] != usuarioId || previo['dispositivo_id'] != turno.dispositivoId)) {
        throw StateError('La autorizacion persistida pertenece a otro origen');
      }
      if (turno.empresaId != empresaId || turno.cajeroId != usuarioId || turno.dispositivoId.isEmpty || turno.horaCentralEn == null) {
        throw StateError('Habilitacion sin origen verificable: consulte el turno online con la identidad original.');
      }
      final ancla = DateTime.parse(turno.horaCentralEn!).toUtc();
      final reloj = DateTime.now().toUtc().millisecondsSinceEpoch;
      final nuevaReferencia = previo == null || ancla.millisecondsSinceEpoch > ((previo['hora_central_ms'] as num?)?.toInt() ?? 0);
      await txn.insert('caja_turnos_activos', {
        'hora_central_ms': nuevaReferencia ? ancla.millisecondsSinceEpoch : previo!['hora_central_ms'],
        'desfase_ms': nuevaReferencia ? ancla.millisecondsSinceEpoch - reloj : previo!['desfase_ms'],
        'ultimo_reloj_ms': nuevaReferencia ? reloj : previo!['ultimo_reloj_ms'],
        'origen_verificado': 1,
        'activo_local': 1,
        'turno_id': turno.turnoId,
        'empresa_id': empresaId,
        'usuario_id': usuarioId,
        'dispositivo_id': turno.dispositivoId,
        'habilitacion_id': turno.habilitacionId,
        'caja_codigo': turno.cajaCodigo,
        'sucursal_id': turno.sucursalId,
        'cajero_id': turno.cajeroId,
        'estado': nuevaReferencia ? turno.estado : previo!['estado'],
        'inicio_en': turno.inicioEn,
        'vence_en': turno.venceEn,
        'version_precios': turno.versionPrecios,
        'revision': turno.revision,
        'snapshot_json': turno.snapshot != null ? jsonEncode(turno.snapshot) : null,
        'actualizado_en': ahoraUtc,
      }, conflictAlgorithm: ConflictAlgorithm.replace);

      final legado = await txn.query('caja_ventas_offline', where: 'turno_id = ? AND empresa_id = ? AND usuario_id = ? AND dispositivo_id = ? AND recuperacion_requerida = 1',
        whereArgs: [turno.turnoId, empresaId, usuarioId, turno.dispositivoId]);
      for (final v in legado) {
        try {
          final fecha = DateTime.parse(v['vendida_local_en'] as String).toUtc();
          final entrega = DateTime.parse(v['entregada_local_en'] as String).toUtc();
          final ini = DateTime.parse(turno.inicioEn).toUtc(), fin = DateTime.parse(turno.venceEn).toUtc();
          if (fecha.isBefore(ini) || !fecha.isBefore(fin) || entrega.isBefore(ini) || !entrega.isBefore(fin) || v['version_precios'] != turno.versionPrecios) continue;
          final cuerpo = <String, dynamic>{
            'operacion_id': v['operacion_id'], 'secuencia_local': v['secuencia_local'],
            'vendida_local_en': v['vendida_local_en'], 'entregada_local_en': v['entregada_local_en'], 'version_precios': v['version_precios'],
            'lineas': jsonDecode(v['lineas_json'] as String), 'total_bob': v['total_bob'], 'efectivo_recibido_bob': v['efectivo_recibido_bob'],
            'cambio_entregado_bob': v['cambio_entregado_bob'], if (v['cliente_id'] != null) 'cliente_id': v['cliente_id'],
          };
          final solicitud = Map<String, dynamic>.from(cuerpo)..['secuencia_local'] = 0;
          await txn.update('caja_ventas_offline', {'cuerpo_json': jsonEncode(cuerpo), 'huella': _canonicoCaja(solicitud), 'recuperacion_requerida': 0,
            'diagnostico': 'Origen persistido revalidado online; el resultado central sigue pendiente'}, where: 'operacion_id = ?', whereArgs: [v['operacion_id']]);
        } catch (_) { /* Legado da?ado conservado sin atribuir ni enviar. */ }
      }
      // Si falta un saldo antiguo, las ventas durables siguen siendo un limite
      // inferior del consumo. No volver a otorgar unidades por un refresco.
      final ventasTurno = await txn.query('caja_ventas_offline', where: 'turno_id = ?', whereArgs: [turno.turnoId]);
      final consumoDurable = <String, int>{};
      bool requiereConciliacion = false;
      for (final v in ventasTurno) {
        final pendiente = v['estado_sincronizacion'] != 'SINCRONIZADA';
        if (v['recuperacion_requerida'] != 0) {
          if (pendiente) requiereConciliacion = true;
          continue;
        }
        try {
          for (final linea in jsonDecode(v['lineas_json'] as String) as List) {
            final cantidad = linea['cantidad'] as int;
            final variante = linea['variante_id'] as String;
            if (cantidad <= 0) throw StateError('Cantidad durable invalida');
            consumoDurable[variante] = (consumoDurable[variante] ?? 0) + cantidad;
          }
        } catch (_) { if (pendiente) requiereConciliacion = true; }
      }
      if (requiereConciliacion) await txn.update('caja_turnos_activos', {'estado': 'CONCILIACION'}, where: 'turno_id = ?', whereArgs: [turno.turnoId]);
      for (final cupo in turno.cupos) {
        final prev = await txn.query('caja_cupos', where: 'turno_id = ? AND variante_id = ?', whereArgs: [turno.turnoId, cupo.varianteId]);
        final saldoPrevio = prev.isEmpty ? 0 : (prev.first['consumido'] as num?)?.toInt() ?? 0;
        final conocido = consumoDurable[cupo.varianteId] ?? 0;
        final consumoPrevio = saldoPrevio > conocido ? saldoPrevio : conocido;
        final mermaPrevia = prev.isEmpty ? 0 : (prev.first['mermado'] as num?)?.toInt() ?? 0;
        final liberadoPrevio = prev.isEmpty ? 0 : (prev.first['liberado'] as num?)?.toInt() ?? 0;
        await txn.insert('caja_cupos', {
          'turno_id': turno.turnoId,
          'variante_id': cupo.varianteId,
          'sku': cupo.sku,
          'producto_nombre': cupo.productoNombre,
          'otorgado': cupo.otorgado,
          'consumido': cupo.consumido > consumoPrevio ? cupo.consumido : consumoPrevio,
          'mermado': cupo.mermado > mermaPrevia ? cupo.mermado : mermaPrevia,
          'liberado': cupo.liberado > liberadoPrevio ? cupo.liberado : liberadoPrevio,
          'precio_autorizado_bob': cupo.precioAutorizadoBob.toStringAsFixed(2),
        }, conflictAlgorithm: ConflictAlgorithm.replace);
      }
    });
  }

  Future<TurnoHabilitacionModel?> obtenerTurnoActivoLocal({
    required String empresaId,
    String? dispositivoId,
    String? usuarioId,
  }) async {
    _exigirContextoCaja(empresaId, usuarioId, dispositivoId);
    final db = await database;
    final whereClauses = <String>['empresa_id = ?', 'origen_verificado = 1', 'activo_local = 1'];
    final whereArgs = <dynamic>[empresaId];

    if (dispositivoId != null && dispositivoId.isNotEmpty) {
      whereClauses.add('dispositivo_id = ?');
      whereArgs.add(dispositivoId);
    }
    if (usuarioId != null && usuarioId.isNotEmpty) {
      whereClauses.add('usuario_id = ?');
      whereArgs.add(usuarioId);
    }

    final rows = await db.query(
      'caja_turnos_activos',
      where: whereClauses.join(' AND '),
      whereArgs: whereArgs,
      orderBy: 'actualizado_en DESC',
      limit: 1,
    );
    if (rows.isEmpty) return null;
    final r = rows.first;
    final turnoId = '${r['turno_id']}';

    final cupos = await obtenerCuposTurnoLocal(turnoId);

    Map<String, dynamic>? snapshot;
    final snapStr = r['snapshot_json']?.toString();
    if (snapStr != null && snapStr.isNotEmpty) {
      try {
        snapshot = jsonDecode(snapStr) as Map<String, dynamic>;
      } catch (_) {}
    }

    return TurnoHabilitacionModel(
      empresaId: r['empresa_id']?.toString(),
      desfaseMs: (r['desfase_ms'] as num?)?.toInt(),
      ultimoRelojMs: (r['ultimo_reloj_ms'] as num?)?.toInt(),
      turnoId: turnoId,
      habilitacionId: '${r['habilitacion_id']}',
      cajaCodigo: '${r['caja_codigo']}',
      dispositivoId: '${r['dispositivo_id']}',
      sucursalId: '${r['sucursal_id']}',
      cajeroId: '${r['cajero_id']}',
      estado: '${r['estado']}',
      inicioEn: '${r['inicio_en']}',
      venceEn: '${r['vence_en']}',
      versionPrecios: '${r['version_precios']}',
      revision: (r['revision'] as num).toInt(),
      cupos: cupos,
      snapshot: snapshot,
    );
  }

  Future<void> actualizarEstadoTurnoLocal(
    String turnoId,
    String nuevoEstado, {
    int? revision,
  }) async {
    final db = await database;
    final values = <String, dynamic>{
      'estado': nuevoEstado,
      'actualizado_en': DateTime.now().toUtc().toIso8601String(),
    };
    if (revision != null) {
      values['revision'] = revision;
    }
    await db.update(
      'caja_turnos_activos',
      values,
      where: 'turno_id = ?',
      whereArgs: [turnoId],
    );
  }

  Future<List<CupoRespuestaModel>> obtenerCuposTurnoLocal(String turnoId) async {
    final db = await database;
    final cuposRows = await db.query(
      'caja_cupos',
      where: 'turno_id = ?',
      whereArgs: [turnoId],
    );

    return cuposRows.map((c) {
      return CupoRespuestaModel(
        varianteId: '${c['variante_id']}',
        sku: c['sku']?.toString(),
        productoNombre: c['producto_nombre']?.toString(),
        otorgado: (c['otorgado'] as num).toInt(),
        consumido: (c['consumido'] as num?)?.toInt() ?? 0,
        liberado: (c['liberado'] as num?)?.toInt() ?? 0,
        mermado: (c['mermado'] as num?)?.toInt() ?? 0,
        precioAutorizadoBob: double.tryParse('${c['precio_autorizado_bob']}') ?? 0.0,
      );
    }).toList();
  }

  Future<void> limpiarTurnoActivoLocal(String turnoId, {String? empresaId}) async {
    if (turnoId.isEmpty) return;
    final db = await database;
    await db.update('caja_turnos_activos', {'activo_local': 0}, where: 'turno_id = ?', whereArgs: [turnoId]);
    // No eliminar cupos, autorizacion, resultados o ventas pendientes.
  }

  Future<VentaOfflineCrearModel> guardarVentaOfflineDurable({
    required String turnoId, required VentaOfflineCrearModel venta,
    required String empresaId, required String usuarioId, required String dispositivoId,
    required ComprobanteLocalModel comprobante, String? rol,
    bool simularFalloAntesDeCommit = false,
  }) async {
    _exigirContextoCaja(empresaId, usuarioId, dispositivoId);
    if (!['CAJERO', 'ADMINISTRADOR', 'ENCARGADO', 'PROPIETARIO'].contains(rol)) throw StateError('Rol de caja no autorizado');
    final db = await database;
    return db.transaction((txn) async {
      final solicitud = venta.toJson()..['secuencia_local'] = 0;
      final huella = _canonicoCaja(solicitud);
      final previas = await txn.query('caja_ventas_offline', where: 'operacion_id = ?', whereArgs: [venta.operacionId]);
      if (previas.isNotEmpty) {
        final p = previas.first;
        final mismoCuerpo = p['cuerpo_json'] == null ? false : _canonicoCaja((jsonDecode(p['cuerpo_json'] as String) as Map)..['secuencia_local'] = 0) == huella;
        if (p['turno_id'] != turnoId || p['empresa_id'] != empresaId || p['usuario_id'] != usuarioId || p['dispositivo_id'] != dispositivoId ||
            p['recuperacion_requerida'] != 0 || (p['huella'] != huella && !mismoCuerpo) ||
            (venta.secuenciaLocal != 0 && venta.secuenciaLocal != p['secuencia_local'])) {
          throw StateError('CONFLICTO_OPERACION: UUID con otro contenido/origen o legado sin validar');
        }
        return VentaOfflineCrearModel.fromJson((jsonDecode(p['cuerpo_json'] as String) as Map).cast<String, dynamic>());
      }
      final ts = await txn.query('caja_turnos_activos', where: 'turno_id = ? AND empresa_id = ? AND usuario_id = ? AND dispositivo_id = ?',
        whereArgs: [turnoId, empresaId, usuarioId, dispositivoId]);
      if (ts.isEmpty) throw StateError('Turno fuera del ambito original');
      final t = ts.first;
      final local = DateTime.now().toUtc().millisecondsSinceEpoch;
      final inicio = DateTime.parse(t['inicio_en'] as String).toUtc().millisecondsSinceEpoch;
      final finDeclarado = DateTime.parse(t['vence_en'] as String).toUtc().millisecondsSinceEpoch;
      final fin = finDeclarado < inicio + 8 * 3600000 ? finDeclarado : inicio + 8 * 3600000;
      final desfase = (t['desfase_ms'] as num?)?.toInt();
      final central = local + (desfase ?? 0);
      if (t['origen_verificado'] != 1 || t['activo_local'] != 1 || t['cajero_id'] != usuarioId || t['habilitacion_id'] != turnoId ||
          t['estado'] != 'ABIERTO' || desfase == null || local < ((t['ultimo_reloj_ms'] as num?)?.toInt() ?? local) || central < inicio || central >= fin) {
        throw StateError('Turno vencido, en conciliacion, no autorizado o reloj incoherente. Conserve pendientes.');
      }
      if (venta.versionPrecios != t['version_precios'] || venta.lineas.isEmpty) throw StateError('Snapshot de caja invalido');
      final variantes = <String>{};
      int total = 0;
      for (final l in venta.lineas) {
        final cs = await txn.query('caja_cupos', where: 'turno_id = ? AND variante_id = ?', whereArgs: [turnoId, l.varianteId]);
        if (cs.isEmpty || !variantes.add(l.varianteId) || l.cantidad <= 0) throw StateError('Linea de caja invalida');
        final c = cs.first;
        final precio = (double.parse(c['precio_autorizado_bob'] as String) * 100).round();
        if ((l.precioAutorizadoBob * 100).round() != precio) throw StateError('Precio distinto al autorizado');
        final modificadas = await txn.rawUpdate('UPDATE caja_cupos SET consumido = consumido + ? WHERE turno_id = ? AND variante_id = ? AND otorgado - consumido - liberado - mermado >= ?',
          [l.cantidad, turnoId, l.varianteId, l.cantidad]);
        if (modificadas != 1) throw StateError('Cupo insuficiente');
        total += precio * l.cantidad;
      }
      if ((venta.totalBob * 100).round() != total || (venta.efectivoRecibidoBob * 100).round() < total ||
          (venta.cambioEntregadoBob * 100).round() != (venta.efectivoRecibidoBob * 100).round() - total) throw StateError('Importes de efectivo inconsistentes');
      final sec = await txn.rawQuery('SELECT COALESCE(MAX(secuencia_local), 0) AS n FROM caja_ventas_offline WHERE turno_id = ?', [turnoId]);
      final cuerpo = venta.toJson();
      cuerpo['secuencia_local'] = (sec.first['n'] as num).toInt() + 1;
      cuerpo['vendida_local_en'] = DateTime.fromMillisecondsSinceEpoch(central, isUtc: true).toIso8601String();
      cuerpo['entregada_local_en'] = cuerpo['vendida_local_en'];
      await txn.insert('caja_ventas_offline', {
        'operacion_id': venta.operacionId, 'turno_id': turnoId, 'empresa_id': empresaId, 'usuario_id': usuarioId, 'dispositivo_id': dispositivoId,
        'secuencia_local': cuerpo['secuencia_local'], 'vendida_local_en': cuerpo['vendida_local_en'], 'entregada_local_en': cuerpo['entregada_local_en'],
        'version_precios': venta.versionPrecios, 'total_bob': venta.totalBob.toStringAsFixed(2), 'efectivo_recibido_bob': venta.efectivoRecibidoBob.toStringAsFixed(2),
        'cambio_entregado_bob': venta.cambioEntregadoBob.toStringAsFixed(2), 'cliente_id': venta.clienteId,
        'lineas_json': jsonEncode(cuerpo['lineas']), 'cuerpo_json': jsonEncode(cuerpo), 'huella': huella, 'recuperacion_requerida': 0,
        'estado_sincronizacion': 'PENDIENTE_ENVIO', 'comprobante_local_id': comprobante.comprobanteId,
      });
      if (simularFalloAntesDeCommit) throw StateError('Fallo intermedio simulado');
      await txn.insert('caja_comprobantes_locales', {
        'comprobante_id': comprobante.comprobanteId, 'operacion_id': venta.operacionId, 'turno_id': turnoId, 'empresa_id': empresaId,
        'numero_comprobante': comprobante.numeroComprobante, 'total_bob': venta.totalBob.toStringAsFixed(2),
        'efectivo_recibido_bob': venta.efectivoRecibidoBob.toStringAsFixed(2), 'cambio_bob': venta.cambioEntregadoBob.toStringAsFixed(2),
        'emitido_en': cuerpo['vendida_local_en'], 'lineas_resumen_json': jsonEncode(cuerpo['lineas']),
      });
      await txn.update('caja_turnos_activos', {'ultimo_reloj_ms': local}, where: 'turno_id = ?', whereArgs: [turnoId]);
      return VentaOfflineCrearModel.fromJson(cuerpo);
    });
  }

  Future<List<VentaOfflineCrearModel>> listarVentasOfflinePendientes({
    required String empresaId,
    String? turnoId,
    String? usuarioId,
    String? dispositivoId,
  }) async {
    _exigirContextoCaja(empresaId, usuarioId, dispositivoId);
    final db = await database;
    final whereClauses = <String>['empresa_id = ?', "COALESCE(estado_sincronizacion, 'RECUPERACION_REQUERIDA') != 'SINCRONIZADA'", 'recuperacion_requerida = 0'];
    final whereArgs = <dynamic>[empresaId];

    if (turnoId != null && turnoId.isNotEmpty) {
      whereClauses.add('turno_id = ?');
      whereArgs.add(turnoId);
    }
    if (usuarioId != null && usuarioId.isNotEmpty) {
      whereClauses.add('usuario_id = ?');
      whereArgs.add(usuarioId);
    }
    if (dispositivoId != null && dispositivoId.isNotEmpty) {
      whereClauses.add('dispositivo_id = ?');
      whereArgs.add(dispositivoId);
    }

    final rows = await db.query(
      'caja_ventas_offline',
      where: whereClauses.join(' AND '),
      whereArgs: whereArgs,
      orderBy: 'secuencia_local ASC',
    );

    return rows.map((r) {
      List<VentaOfflineLineaModel> lineas = [];
      final lineasStr = r['lineas_json']?.toString();
      if (lineasStr != null && lineasStr.isNotEmpty) {
        try {
          final decoded = jsonDecode(lineasStr) as List;
          lineas = decoded.map((e) => VentaOfflineLineaModel.fromJson(e as Map<String, dynamic>)).toList();
        } catch (_) {}
      }

      return VentaOfflineCrearModel(
        turnoIdOrigen: r['turno_id']?.toString(),
        operacionId: '${r['operacion_id']}',
        secuenciaLocal: (r['secuencia_local'] as num).toInt(),
        vendidaLocalEn: '${r['vendida_local_en']}',
        entregadaLocalEn: '${r['entregada_local_en']}',
        versionPrecios: '${r['version_precios']}',
        lineas: lineas,
        totalBob: double.tryParse('${r['total_bob']}') ?? 0.0,
        efectivoRecibidoBob: double.tryParse('${r['efectivo_recibido_bob']}') ?? 0.0,
        cambioEntregadoBob: double.tryParse('${r['cambio_entregado_bob']}') ?? 0.0,
        clienteId: r['cliente_id']?.toString(),
      );
    }).toList();
  }

  Future<Map<String, Object?>?> registroVentaCaja(String operacionId, {required String empresaId, required String usuarioId, required String dispositivoId}) async {
    _exigirContextoCaja(empresaId, usuarioId, dispositivoId);
    final db = await database;
    final rs = await db.query('caja_ventas_offline', where: 'operacion_id = ? AND empresa_id = ? AND usuario_id = ? AND dispositivo_id = ? AND recuperacion_requerida = 0',
      whereArgs: [operacionId, empresaId, usuarioId, dispositivoId]);
    return rs.isEmpty ? null : rs.first;
  }

  Future<bool> hayPendientesCajaTurno(String turnoId, String empresaId) async {
    final db = await database;
    final rs = await db.rawQuery("SELECT COUNT(*) AS n FROM caja_ventas_offline WHERE COALESCE(estado_sincronizacion, 'RECUPERACION_REQUERIDA') != 'SINCRONIZADA' AND (turno_id = ? OR turno_id IS NULL OR turno_id = '') AND (empresa_id = ? OR empresa_id IS NULL OR empresa_id = '')", [turnoId, empresaId]);
    return (rs.first['n'] as num).toInt() > 0;
  }

  Future<int> pendientesRecuperacionCaja(String empresaId, String usuarioId, String dispositivoId) async {
    _exigirContextoCaja(empresaId, usuarioId, dispositivoId);
    final db = await database;
    final rs = await db.rawQuery("SELECT COUNT(*) AS n FROM caja_ventas_offline WHERE recuperacion_requerida = 1 AND (empresa_id IS NULL OR empresa_id = '' OR (empresa_id = ? AND (usuario_id IS NULL OR usuario_id = '' OR dispositivo_id IS NULL OR dispositivo_id = '' OR (usuario_id = ? AND dispositivo_id = ?))))", [empresaId, usuarioId, dispositivoId]);
    return (rs.first['n'] as num).toInt();
  }

  Future<void> marcarVentaOfflineSincronizada(
    String operacionId, {
    Map<String, dynamic>? resultadoJson,
    String? empresaId,
    String? usuarioId,
    String? dispositivoId,
  }) async {
    _exigirContextoCaja(empresaId ?? '', usuarioId, dispositivoId);
    final db = await database;
    final values = <String, dynamic>{
      'estado_sincronizacion': resultadoJson?['resultado'] == 'REGISTRADA_CENTRAL' ? 'SINCRONIZADA' : 'CONCILIACION_REQUERIDA',
      'sincronizada_en': DateTime.now().toUtc().toIso8601String(),
    };
    if (resultadoJson != null) {
      values['resultado_json'] = jsonEncode(resultadoJson);
    }
    await db.update(
      'caja_ventas_offline',
      values,
      where: 'operacion_id = ? AND empresa_id = ? AND usuario_id = ? AND dispositivo_id = ?',
      whereArgs: [operacionId, empresaId, usuarioId, dispositivoId],
    );
  }

  Future<ComprobanteLocalModel?> obtenerComprobanteLocalPorOperacion(String operacionId, {String? empresaId, String? usuarioId, String? dispositivoId}) async {
    if (empresaId == null || usuarioId == null || dispositivoId == null) return null;
    if (await registroVentaCaja(operacionId, empresaId: empresaId, usuarioId: usuarioId, dispositivoId: dispositivoId) == null) return null;
    final db = await database;
    final rows = await db.query(
      'caja_comprobantes_locales',
      where: 'operacion_id = ?',
      whereArgs: [operacionId],
      limit: 1,
    );
    if (rows.isEmpty) return null;
    final r = rows.first;
    List<Map<String, dynamic>> lineas = [];
    final lStr = r['lineas_resumen_json']?.toString();
    if (lStr != null && lStr.isNotEmpty) {
      try {
        final decoded = jsonDecode(lStr) as List;
        lineas = decoded.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
      } catch (_) {}
    }
    return ComprobanteLocalModel(
      comprobanteId: '${r['comprobante_id']}',
      operacionId: '${r['operacion_id']}',
      turnoId: '${r['turno_id']}',
      empresaId: '${r['empresa_id']}',
      numeroComprobante: '${r['numero_comprobante']}',
      totalBob: double.tryParse('${r['total_bob']}') ?? 0.0,
      efectivoRecibidoBob: double.tryParse('${r['efectivo_recibido_bob']}') ?? 0.0,
      cambioBob: double.tryParse('${r['cambio_bob']}') ?? 0.0,
      emitidoEn: '${r['emitido_en']}',
      lineas: lineas,
    );
  }

  Future<List<ComprobanteLocalModel>> listarComprobantesLocales(String turnoId, {String? empresaId, String? usuarioId, String? dispositivoId}) async {
    _exigirContextoCaja(empresaId ?? '', usuarioId, dispositivoId);
    final db = await database;
    final rows = await db.rawQuery('SELECT c.* FROM caja_comprobantes_locales c JOIN caja_ventas_offline v ON v.operacion_id = c.operacion_id WHERE c.turno_id = ? AND v.empresa_id = ? AND v.usuario_id = ? AND v.dispositivo_id = ?',
      [turnoId, empresaId, usuarioId, dispositivoId]);
    return rows.map((r) {
      List<Map<String, dynamic>> lineas = [];
      final lStr = r['lineas_resumen_json']?.toString();
      if (lStr != null && lStr.isNotEmpty) {
        try {
          final decoded = jsonDecode(lStr) as List;
          lineas = decoded.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
        } catch (_) {}
      }
      return ComprobanteLocalModel(
        comprobanteId: '${r['comprobante_id']}',
        operacionId: '${r['operacion_id']}',
        turnoId: '${r['turno_id']}',
        empresaId: '${r['empresa_id']}',
        numeroComprobante: '${r['numero_comprobante']}',
        totalBob: double.tryParse('${r['total_bob']}') ?? 0.0,
        efectivoRecibidoBob: double.tryParse('${r['efectivo_recibido_bob']}') ?? 0.0,
        cambioBob: double.tryParse('${r['cambio_bob']}') ?? 0.0,
        emitidoEn: '${r['emitido_en']}',
        lineas: lineas,
      );
    }).toList();
  }

  Future<int> obtenerSiguienteSecuenciaVentaCaja({
    required String turnoId,
    required String dispositivoId,
  }) async {
    final db = await database;
    final res = await db.rawQuery('''
      SELECT MAX(secuencia_local) as max_sec
      FROM caja_ventas_offline
      WHERE turno_id = ? AND dispositivo_id = ?;
    ''', [turnoId, dispositivoId]);
    final maxSec = res.first['max_sec'];
    if (maxSec == null) return 1;
    return (maxSec as num).toInt() + 1;
  }

  Future<Map<String, int>> obtenerEstadisticasVentasCaja(String turnoId, {String? empresaId, String? usuarioId, String? dispositivoId}) async {
    _exigirContextoCaja(empresaId ?? '', usuarioId, dispositivoId);
    final db = await database;
    try {
      final res = await db.rawQuery('''
        SELECT MAX(secuencia_local) as max_sec, COUNT(*) as total
        FROM caja_ventas_offline
        WHERE turno_id = ? AND empresa_id = ? AND usuario_id = ? AND dispositivo_id = ?;
      ''', [turnoId, empresaId, usuarioId, dispositivoId]);
      if (res.isEmpty) {
        return {'ultima_secuencia': 0, 'total_operaciones': 0};
      }
      final maxSec = res.first['max_sec'] as num?;
      final total = res.first['total'] as num?;
      return {
        'ultima_secuencia': maxSec?.toInt() ?? 0,
        'total_operaciones': total?.toInt() ?? 0,
      };
    } catch (_) {
      // Relanzar la excepción para evitar cierres inseguros basados en conteos falsos de 0
      rethrow;
    }
  }

  Future<List<Map<String, dynamic>>> listarVariantesParaCaja({String? sucursalId}) async {
    final db = await database;
    try {
      final rows = await db.rawQuery('''
        SELECT v.id as variante_id, v.producto_id, v.sku, v.talla, v.color, v.precio_bob,
               v.disponibilidad, v.disponibilidad_por_sucursal_json,
               p.nombre as producto_nombre
        FROM catalogo_variantes v
        LEFT JOIN catalogo_productos p ON p.id = v.producto_id
      ''');
      return rows;
    } catch (_) {
      return [];
    }
  }
}

class ResultadoConsultaLocal {
  final int total;
  final int limit;
  final int offset;
  final List<Producto> items;
  final SnapshotMetadata? snapshot;
  final bool haySnapshot;

  ResultadoConsultaLocal({
    required this.total,
    required this.limit,
    required this.offset,
    required this.items,
    this.snapshot,
    required this.haySnapshot,
  });

  factory ResultadoConsultaLocal.sinSnapshot() {
    return ResultadoConsultaLocal(
      total: 0,
      limit: 0,
      offset: 0,
      items: const [],
      snapshot: null,
      haySnapshot: false,
    );
  }
}
