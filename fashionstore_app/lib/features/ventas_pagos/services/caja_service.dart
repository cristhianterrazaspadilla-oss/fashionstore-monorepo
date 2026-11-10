import 'dart:convert';
import 'package:uuid/uuid.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/session/dispositivo_helper.dart';
import '../../../core/session/session_manager.dart';
import '../../../core/storage/local_database_service.dart';
import '../models/caja_model.dart';

/// CU06/CU07: una venta durable conserva su habilitacion y cuerpo originales.
class CajaService {
  final ApiClient _api;
  final SessionManager _sesiones;
  final LocalDatabaseService _storage;
  SessionManager get sesiones => _sesiones;
  LocalDatabaseService get storage => _storage;
  ApiClient get api => _api;
  TurnoHabilitacionModel? _turnoActivoMemoria;
  final List<VentaOfflineCrearModel> _colaVentasMemoria = [];
  String? _ambitoMemoria;
  CajaService({ApiClient? api, SessionManager? sesiones, LocalDatabaseService? storage})
      : _sesiones = sesiones ?? SessionManager(), _storage = storage ?? LocalDatabaseService(),
        _api = api ?? ApiClient(sesiones: sesiones ?? SessionManager());

  Future<Map<String, String>> _obtenerContexto() async {
    final s = await _sesiones.leerValida();
    final ahora = DateTime.now();
    if (s == null || ahora.isBefore(s.guardadaEn) ||
        s.usuario.empresaId == null || s.usuario.empresaId!.isEmpty ||
        !['CAJERO', 'ADMINISTRADOR', 'ENCARGADO', 'PROPIETARIO'].contains(s.usuario.rol.toUpperCase())) {
      _turnoActivoMemoria = null; _colaVentasMemoria.clear(); _ambitoMemoria = null;
      throw StateError('Reautentique para acceder a la caja. Los pendientes no se borraron.');
    }
    final uid = s.usuario.usuarioId.isNotEmpty ? s.usuario.usuarioId : s.usuario.id;
    final d = await DispositivoHelper.obtenerDispositivoId();
    final ctx = {'empresa_id': s.usuario.empresaId!, 'usuario_id': uid, 'dispositivo_id': d, 'rol': s.usuario.rol.toUpperCase()};
    final clave = jsonEncode(ctx);
    if (_ambitoMemoria != clave) { _turnoActivoMemoria = null; _colaVentasMemoria.clear(); }
    _ambitoMemoria = clave;
    return ctx;
  }

  Future<void> restaurarDesdeStorage({String? empresaId, String? dispositivoId, String? usuarioId}) async {
    final c = await _obtenerContexto();
    if ((empresaId != null && empresaId != c['empresa_id']) || (usuarioId != null && usuarioId != c['usuario_id']) ||
        (dispositivoId != null && dispositivoId != c['dispositivo_id'])) throw StateError('Origen distinto de la identidad actual');
    _turnoActivoMemoria = await _storage.obtenerTurnoActivoLocal(empresaId: c['empresa_id']!, usuarioId: c['usuario_id'], dispositivoId: c['dispositivo_id']);
    final pendientes = await _storage.listarVentasOfflinePendientes(empresaId: c['empresa_id']!, usuarioId: c['usuario_id'], dispositivoId: c['dispositivo_id']);
    _colaVentasMemoria..clear()..addAll(pendientes);
  }

  Future<TurnoHabilitacionModel> _guardarOnline(TurnoHabilitacionModel turno, Map<String, String> ctx) async {
    // No anclar el reloj con una respuesta antigua de habilitación idempotente.
    final t = await _api.get<TurnoHabilitacionModel>(
      '/cajas/turnos/${turno.turnoId}', convertir: (j) => TurnoHabilitacionModel.fromJson((j as Map).cast<String, dynamic>()));
    if (jsonEncode(ctx) != jsonEncode(await _obtenerContexto())) throw StateError('Identidad modificada durante la consulta');
    if (t.empresaId != ctx['empresa_id'] || t.cajeroId != ctx['usuario_id'] || t.dispositivoId != ctx['dispositivo_id']) {
      throw StateError('La caja pertenece a otra autorizacion. Use recuperacion supervisada online.');
    }
    await _storage.guardarTurnoActivoLocal(t, empresaId: ctx['empresa_id']!, usuarioId: ctx['usuario_id']!);
    await restaurarDesdeStorage();
    return _turnoActivoMemoria ?? t;
  }

  Future<TurnoHabilitacionModel> habilitarTurno(TurnoCrearModel dto) async {
    final c = await _obtenerContexto();
    if (dto.dispositivoId != c['dispositivo_id']) throw StateError('Dispositivo distinto al registrado');
    final t = await _api.post<TurnoHabilitacionModel>('/cajas/turnos', cuerpo: dto.toJson(), idempotencyKey: const Uuid().v4(),
      convertir: (j) => TurnoHabilitacionModel.fromJson((j as Map).cast<String, dynamic>()));
    return _guardarOnline(t, c);
  }

  Future<TurnoHabilitacionModel?> consultarTurnoActivo({String? dispositivoId}) async {
    final c = await _obtenerContexto();
    if (dispositivoId != null && dispositivoId != c['dispositivo_id']) throw StateError('Dispositivo ajeno');
    TurnoHabilitacionModel? t;
    try {
      t = await _api.get<TurnoHabilitacionModel?>('/cajas/turnos/activo', query: {'dispositivo_id': c['dispositivo_id']!},
        convertir: (j) => j == null ? null : TurnoHabilitacionModel.fromJson((j as Map).cast<String, dynamic>()));
    } on ApiException catch (e) {
      if (e.statusCode != null && e.statusCode! >= 400 && e.statusCode! < 500) {
        if (_turnoActivoMemoria != null) await _storage.actualizarEstadoTurnoLocal(_turnoActivoMemoria!.turnoId, 'REQUIERE_REAUTORIZACION');
        _turnoActivoMemoria = null;
        rethrow;
      }
      await restaurarDesdeStorage();
      return _turnoActivoMemoria;
    } catch (_) {
      await restaurarDesdeStorage();
      return _turnoActivoMemoria;
    }
    if (t != null) return _guardarOnline(t, c);
    final anterior = _turnoActivoMemoria;
    if (anterior != null) await _storage.limpiarTurnoActivoLocal(anterior.turnoId);
    _turnoActivoMemoria = null;
    return null;
  }

  Future<TurnoHabilitacionModel> consultarTurno(String turnoId) async {
    final c = await _obtenerContexto();
    final t = await _api.get<TurnoHabilitacionModel>('/cajas/turnos/$turnoId',
      convertir: (j) => TurnoHabilitacionModel.fromJson((j as Map).cast<String, dynamic>()));
    return _guardarOnline(t, c);
  }

  Future<VentaOfflineResultadoModel> _enviarRegistro(Map<String, Object?> registro, Map<String, String> origen) async {
    final cuerpo = (jsonDecode(registro['cuerpo_json'] as String) as Map).cast<String, dynamic>();
    final respuesta = await _api.post<Map<String, dynamic>>('/cajas/turnos/${registro['turno_id']}/ventas', cuerpo: cuerpo,
      convertir: (j) => (j as Map).cast<String, dynamic>());
    final r = VentaOfflineResultadoModel.fromJson(respuesta);
    if (r.operacionId != registro['operacion_id'] || !['REGISTRADA_CENTRAL', 'CONCILIACION_REQUERIDA'].contains(r.resultado)) {
      throw StateError('Respuesta no confirmada; se conserva la venta original');
    }
    final totalOriginal = double.tryParse('${cuerpo['total_bob']}');
    if (r.resultado == 'REGISTRADA_CENTRAL' && (totalOriginal == null || !totalOriginal.isFinite ||
        (r.totalBob * 100).round() != (totalOriginal * 100).round())) {
      throw StateError('El total central no coincide con la venta original; se conserva el pendiente.');
    }
    await _storage.marcarVentaOfflineSincronizada(r.operacionId, empresaId: origen['empresa_id'], usuarioId: origen['usuario_id'], dispositivoId: origen['dispositivo_id'],
      resultadoJson: respuesta);
    return r;
  }

  Future<VentaOfflineResultadoModel> registrarVentaOffline(String turnoId, VentaOfflineCrearModel dto) async {
    final c = await _obtenerContexto();
    final r = await _storage.registroVentaCaja(dto.operacionId, empresaId: c['empresa_id']!, usuarioId: c['usuario_id']!, dispositivoId: c['dispositivo_id']!);
    if (r == null || r['turno_id'] != turnoId) throw StateError('Venta sin origen autorizado');
    // Se envia el cuerpo persistido; un argumento distinto no reemplaza la venta original.
    final original = VentaOfflineCrearModel.fromJson((jsonDecode(r['cuerpo_json'] as String) as Map).cast<String, dynamic>());
    if (jsonEncode(original.toJson()) != jsonEncode(dto.toJson())) throw StateError('CONFLICTO_OPERACION: contenido modificado');
    final resultado = await _enviarRegistro(r, c);
    await restaurarDesdeStorage();
    return resultado;
  }

  Future<TurnoCerradoModel> cerrarTurno(String turnoId, TurnoCerrarModel dto) async {
    final c = await _obtenerContexto();
    if (await _storage.hayPendientesCajaTurno(turnoId, c['empresa_id']!)) throw StateError('Hay ventas sin resolver; no se devuelven cupos.');
    final cerrado = await _api.post<TurnoCerradoModel>('/cajas/turnos/$turnoId/cerrar', cuerpo: dto.toJson(),
      convertir: (j) => TurnoCerradoModel.fromJson((j as Map).cast<String, dynamic>()));
    if (cerrado.estado == 'CERRADO') { await _storage.limpiarTurnoActivoLocal(turnoId); _turnoActivoMemoria = null; }
    else await _storage.actualizarEstadoTurnoLocal(turnoId, cerrado.estado, revision: cerrado.revision);
    return cerrado;
  }

  Future<Map<String, dynamic>> recuperarTurno(String turnoId, {required int revision, required String motivo}) async {
    await _obtenerContexto();
    final r = await _api.post<Map<String, dynamic>>('/cajas/turnos/$turnoId/recuperar', cuerpo: {'revision': revision, 'motivo': motivo},
      convertir: (j) => (j as Map).cast<String, dynamic>());
    await _storage.actualizarEstadoTurnoLocal(turnoId, 'RECUPERACION');
    _turnoActivoMemoria = null;
    return r;
  }

  Future<Map<String, int>> obtenerEstadisticasVentasTurno(String turnoId) async {
    final c = await _obtenerContexto();
    return _storage.obtenerEstadisticasVentasCaja(turnoId, empresaId: c['empresa_id'], usuarioId: c['usuario_id'], dispositivoId: c['dispositivo_id']);
  }
  TurnoHabilitacionModel? get turnoActivoLocal => _turnoActivoMemoria;
  List<VentaOfflineCrearModel> get ventasOfflinePendientes => List.unmodifiable(_colaVentasMemoria);
  void fijarTurnoLocal(TurnoHabilitacionModel turno) { throw StateError('Use fijarYPersistirTurnoLocal con await'); }
  void encolarVentaOffline(VentaOfflineCrearModel venta) { throw StateError('Use el registro transaccional de la venta'); }

  Future<void> fijarYPersistirTurnoLocal(TurnoHabilitacionModel turno, {String? empresaId, String? usuarioId}) async {
    final c = await _obtenerContexto();
    if ((empresaId != null && empresaId != c['empresa_id']) || (usuarioId != null && usuarioId != c['usuario_id'])) throw StateError('Origen ajeno');
    await _guardarOnline(turno, c);
  }

  Future<ComprobanteLocalModel> registrarVentaFisicaOffline({required List<VentaOfflineLineaModel> lineas,
    required double totalBob, required double efectivoRecibidoBob, required double cambioEntregadoBob,
    String? clienteId, String? operacionId, DateTime? fechaLocal}) async {
    final c = await _obtenerContexto();
    final turno = _turnoActivoMemoria;
    if (turno == null) throw StateError('No hay turno autorizado persistido');
    final id = operacionId ?? const Uuid().v4();
    final fecha = (fechaLocal ?? DateTime.now()).toUtc().toIso8601String();
    final venta = VentaOfflineCrearModel(operacionId: id, secuenciaLocal: 0, vendidaLocalEn: fecha, entregadaLocalEn: fecha,
      versionPrecios: turno.versionPrecios, lineas: lineas, totalBob: totalBob, efectivoRecibidoBob: efectivoRecibidoBob,
      cambioEntregadoBob: cambioEntregadoBob, clienteId: clienteId);
    final comprobante = ComprobanteLocalModel(comprobanteId: const Uuid().v4(), operacionId: id, turnoId: turno.turnoId,
      empresaId: c['empresa_id']!, numeroComprobante: 'COMP-LOC-${id.substring(0, 8).toUpperCase()}', totalBob: totalBob,
      efectivoRecibidoBob: efectivoRecibidoBob, cambioBob: cambioEntregadoBob, emitidoEn: fecha, lineas: lineas.map((l) => l.toJson()).toList());
    await _storage.guardarVentaOfflineDurable(turnoId: turno.turnoId, venta: venta, empresaId: c['empresa_id']!,
      usuarioId: c['usuario_id']!, dispositivoId: c['dispositivo_id']!, comprobante: comprobante, rol: c['rol']);
    final guardado = await _storage.obtenerComprobanteLocalPorOperacion(id, empresaId: c['empresa_id'], usuarioId: c['usuario_id'], dispositivoId: c['dispositivo_id']);
    if (guardado == null) throw StateError('No se pudo recuperar el comprobante durable');
    await restaurarDesdeStorage();
    return guardado;
  }

  Future<List<ComprobanteLocalModel>> listarComprobantesLocales(String turnoId) async {
    final c = await _obtenerContexto();
    return _storage.listarComprobantesLocales(turnoId, empresaId: c['empresa_id'], usuarioId: c['usuario_id'], dispositivoId: c['dispositivo_id']);
  }
  Future<int> diagnosticosRecuperacion() async {
    final c = await _obtenerContexto(); return _storage.pendientesRecuperacionCaja(c['empresa_id']!, c['usuario_id']!, c['dispositivo_id']!);
  }
  Future<int> sincronizarVentasPendientes(String? turnoId) async {
    final c = await _obtenerContexto();
    final pendientes = await _storage.listarVentasOfflinePendientes(empresaId: c['empresa_id']!, usuarioId: c['usuario_id'], dispositivoId: c['dispositivo_id'], turnoId: turnoId);
    int n = 0;
    for (final v in pendientes) {
      if (jsonEncode(c) != jsonEncode(await _obtenerContexto())) break;
      try { final r = await registrarVentaOffline(v.turnoIdOrigen!, v); if (r.resultado == 'REGISTRADA_CENTRAL') n++; } catch (_) { /* conserva cuerpo/UUID/origen ante resultado incierto */ }
    }
    await restaurarDesdeStorage();
    return n;
  }
  Future<void> sincronizarCuposMemoriaDesdeStorage(String turnoId) => restaurarDesdeStorage();

  /// Recuperacion deliberada online: permiso del servidor antes de leer otro titular.
  Future<int> recuperarPendientesSupervisados(String turnoId) async {
    final c = await _obtenerContexto();
    if (!['ADMINISTRADOR', 'ENCARGADO', 'PROPIETARIO'].contains(c['rol'])) throw StateError('Se requiere supervisor');
    final t = await _api.get<TurnoHabilitacionModel>('/cajas/turnos/$turnoId',
      convertir: (j) => TurnoHabilitacionModel.fromJson((j as Map).cast<String, dynamic>()));
    if (t.empresaId != c['empresa_id'] || t.horaCentralEn == null || jsonEncode(c) != jsonEncode(await _obtenerContexto())) throw StateError('Autorizacion de recuperacion invalida');
    // Conservar actor/dispositivo del servidor; nunca atribuir al supervisor actual.
    await _storage.guardarTurnoActivoLocal(t, empresaId: t.empresaId!, usuarioId: t.cajeroId);
    final origen = {'empresa_id': t.empresaId!, 'usuario_id': t.cajeroId, 'dispositivo_id': t.dispositivoId};
    final pendientes = await _storage.listarVentasOfflinePendientes(empresaId: t.empresaId!, usuarioId: t.cajeroId, dispositivoId: t.dispositivoId, turnoId: turnoId);
    int n = 0;
    for (final v in pendientes) {
      if (jsonEncode(c) != jsonEncode(await _obtenerContexto())) break;
      final reg = await _storage.registroVentaCaja(v.operacionId, empresaId: t.empresaId!, usuarioId: t.cajeroId, dispositivoId: t.dispositivoId);
      try { if (reg != null && (await _enviarRegistro(reg, origen)).resultado == 'REGISTRADA_CENTRAL') n++; } catch (_) { /* conciliacion pendiente, no borrar */ }
    }
    return n;
  }
}
