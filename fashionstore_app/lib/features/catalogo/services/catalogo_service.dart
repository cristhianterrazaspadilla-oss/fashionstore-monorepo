import 'dart:async';
import 'package:http/http.dart' as http;
import '../models/catalogo_model.dart';
import '../models/catalogo_snapshot_model.dart';
import '../../ventas_pagos/models/caja_model.dart';
import '../../../core/config/api_config.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/storage/local_database_service.dart';
import '../../../core/session/session_manager.dart';

/// Catálogo del cliente (contrato real del backend).
///
/// Soporta:
/// - Online: GET /productos, GET /variantes, GET /variantes/{id}/disponibilidad
/// - CU03: GET /catalogo/descarga y guardado atómico en SQLite vía staging
/// - CU16: Consulta sobre snapshot SQLite cuando falla o no hay conexión de red
class CatalogoService {
  final ApiClient _api;
  final LocalDatabaseService _storage;
  bool usandoSnapshot = false;
  final Map<String, String> _etiquetasLocales = {};
  String etiquetaVariante(Variante variante) => _etiquetasLocales[variante.id] ?? variante.sku;

  Future<String> _ambitoLocal() async {
    final sesion = await SessionManager().leerValida();
    if (sesion == null) return ApiConfig.empresaCodigoDefecto;
    final empresa = sesion.usuario.empresaId;
    if (empresa == null || empresa.isEmpty) throw StateError('La sesión no identifica una empresa.');
    return empresa;
  }

  bool _falloRed(Object e) => e is http.ClientException || e is TimeoutException;

  CatalogoService({ApiClient? api, LocalDatabaseService? storage})
      : _api = api ?? ApiClient(),
        _storage = storage ?? LocalDatabaseService();

  LocalDatabaseService get storage => _storage;

  Future<List<Producto>> listarProductos({
    required FiltrosCatalogo filtros,
    int limit = 20,
    int offset = 0,
    String? empresaCodigo,
  }) {
    final query = filtros.toQuery(limit: limit, offset: offset);
    final emp = empresaCodigo ?? ApiConfig.empresaCodigoDefecto;
    if (emp.isNotEmpty) {
      query['empresa_codigo'] = emp;
    }
    return _api.get<List<Producto>>(
      '/productos',
      query: query,
      convertir: (j) => ((j as List?) ?? [])
          .whereType<Map>()
          .map((e) => Producto.fromJson(e.cast<String, dynamic>()))
          .toList(),
    );
  }

  Future<Producto> obtenerProducto(String id) {
    return _api.get<Producto>(
      '/productos/$id',
      convertir: (j) => Producto.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<List<Variante>> variantesPorProducto(String productoId) async {
    usandoSnapshot = false;
    _etiquetasLocales.clear();
    try {
      return await _api.get<List<Variante>>(
      '/variantes',
      query: {'producto_id': productoId, 'limit': '100', 'offset': '0'},
      convertir: (j) => ((j as List?) ?? [])
          .whereType<Map>()
          .map((e) => Variante.fromJson(e.cast<String, dynamic>()))
          .toList(),
      );
    } catch (e) {
      if (!_falloRed(e)) rethrow;
      final ambito = await _ambitoLocal();
      final rows = await _storage.variantesProductoLocal(productoId, ambito);
      if (rows.isEmpty) throw StateError('Esta prenda o sus variantes no están descargadas para la empresa actual. Conéctate y descarga el catálogo.');
      final variantes = <Variante>[];
      for (final row in rows) {
        final precio = double.tryParse('${row['precio_bob'] ?? ''}');
        if (precio == null || !precio.isFinite || precio < 0 ||
            '${row['id'] ?? ''}'.isEmpty || '${row['talla_id'] ?? ''}'.isEmpty ||
            '${row['color_id'] ?? ''}'.isEmpty || '${row['talla'] ?? ''}'.isEmpty || '${row['color'] ?? ''}'.isEmpty) {
          throw StateError('La descarga no contiene precio, talla y color completos. Actualiza el catálogo al reconectar.');
        }
        final id = row['id'].toString();
        variantes.add(Variante(id: id, productoId: productoId, tallaId: row['talla_id'].toString(),
          colorId: row['color_id'].toString(), sku: '${row['sku'] ?? ''}', precio: precio, activa: true));
        _etiquetasLocales[id] = '${row['talla']} · ${row['color']}';
      }
      if (await _ambitoLocal() != ambito) throw StateError('Cambió la empresa de la sesión. Vuelve a abrir la prenda.');
      usandoSnapshot = true;
      return variantes;
    }
  }

  Future<Variante> obtenerVariante(String id) {
    return _api.get<Variante>(
      '/variantes/$id',
      convertir: (j) => Variante.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<List<DisponibilidadSucursal>> disponibilidad(String varianteId) async {
    try {
      return await _api.get<List<DisponibilidadSucursal>>(
        '/variantes/$varianteId/disponibilidad',
        convertir: (j) => ((j as List?) ?? [])
            .whereType<Map>()
            .map((e) =>
                DisponibilidadSucursal.fromJson(e.cast<String, dynamic>()))
            .toList(),
      );
    } on ApiException {
      rethrow;
    } catch (e) {
      if (!_falloRed(e)) rethrow;
      // Fallback a SQLite local si no hay conexión
      final ambito = await _ambitoLocal();
      final local = await _storage.disponibilidadVarianteLocal(varianteId, empresaCodigoOId: ambito);
      if (await _ambitoLocal() != ambito) throw StateError('Cambió la empresa de la sesión. Vuelve a abrir la prenda.');
      usandoSnapshot = true;
      if (local.isNotEmpty) return local;
      throw StateError('No hay disponibilidad descargada para esta variante. Requiere consulta al reconectar.');
    }
  }

  Future<FiltrosOpciones> filtrosOpciones({String? empresaCodigo}) {
    final query = <String, String>{};
    final emp = empresaCodigo ?? ApiConfig.empresaCodigoDefecto;
    if (emp.isNotEmpty) query['empresa_codigo'] = emp;

    return _api.get<FiltrosOpciones>(
      '/catalogo/filtros-opciones',
      query: query.isEmpty ? null : query,
      convertir: (j) =>
          FiltrosOpciones.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  // -------------------------------------------------------------
  // CU03: DESCARGA DE CATÁLOGO OFFLINE (SQLITE)
  // -------------------------------------------------------------

  /// Descarga el snapshot completo del catálogo y lo persiste atómicamente en SQLite.
  Future<CatalogoSnapshotModel> descargarCatalogo({
    String? empresaCodigo,
    String? sucursalId,
    bool simularFalloAntesDeCommit = false,
  }) async {
    final codigo = empresaCodigo ?? ApiConfig.empresaCodigoDefecto;
    final query = <String, String>{
      'empresa_codigo': codigo,
    };
    if (sucursalId != null && sucursalId.isNotEmpty) {
      query['sucursal_id'] = sucursalId;
    }

    final snapshot = await _api.get<CatalogoSnapshotModel>(
      '/catalogo/descarga',
      query: query,
      convertir: (j) => CatalogoSnapshotModel.fromJson(
        (j as Map).cast<String, dynamic>(),
      ),
    );

    await _storage.guardarSnapshot(
      snapshot: snapshot,
      simularFalloAntesDeCommit: simularFalloAntesDeCommit,
    );

    return snapshot;
  }

  /// Obtiene los metadatos de la copia local activa desde SQLite.
  Future<SnapshotMetadata?> obtenerSnapshotActivo([String? empresaCodigoOId]) {
    final key = empresaCodigoOId ?? ApiConfig.empresaCodigoDefecto;
    return _storage.obtenerSnapshotActivo(key);
  }

  // -------------------------------------------------------------
  // CU16: CONSULTA LOCAL CON FILTROS EN SQLITE
  // -------------------------------------------------------------

  /// Consulta el catálogo localmente sobre SQLite cuando no hay conexión.
  Future<ResultadoConsultaLocal> consultarCatalogoLocal({
    String? empresaCodigoOId,
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
  }) {
    final key = empresaCodigoOId ?? ApiConfig.empresaCodigoDefecto;
    return _storage.consultarCatalogoLocal(
      empresaCodigoOId: key,
      texto: texto,
      categoriaId: categoriaId,
      tallaId: tallaId,
      colorId: colorId,
      componentesColor: componentesColor,
      modoColor: modoColor,
      precioMin: precioMin,
      precioMax: precioMax,
      limit: limit,
      offset: offset,
    );
  }

  /// Lista las variantes disponibles para habilitación de cupos en Caja Móvil.
  Future<List<VarianteCajaDisponibleModel>> listarVariantesParaCaja(
      {String? sucursalId}) async {
    if (sucursalId == null || sucursalId.isEmpty) return [];

    // Un turno nuevo requiere stock libre comprobado en la sucursal. El catalogo
    // offline no autoriza cupos; el backend vuelve a bloquear y validar el stock.
    final existencias = await _api.get<List<Map<String, dynamic>>>(
      '/inventario/existencias',
      query: {'sucursal_id': sucursalId},
      convertir: (j) => ((j as List?) ?? [])
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList(),
    );
    final variantes = await _api.get<List<Variante>>(
      '/variantes',
      query: {'solo_activas': 'true', 'limit': '100', 'offset': '0'},
      convertir: (j) => ((j as List?) ?? [])
          .whereType<Map>()
          .map((e) => Variante.fromJson(e.cast<String, dynamic>()))
          .toList(),
    );
    final idsActivos = variantes
        .where((variante) => variante.activa)
        .map((variante) => variante.id)
        .toSet();

    return existencias
        .where((fila) =>
            idsActivos.contains(fila['variante_id']?.toString()) &&
            ((fila['disponible'] as num?)?.toInt() ?? 0) > 0)
        .map(VarianteCajaDisponibleModel.fromJson)
        .toList();
  }
}
