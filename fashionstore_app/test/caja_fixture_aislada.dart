// Fixtures de la suite heredada. Solo se sustituye HTTP; caja y SQLite son reales.
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/core/session/dispositivo_helper.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/core/storage/local_database_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/caja_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/caja_service.dart';

late String dispositivoCajaPrueba;
final _turnos = <String, Map<String, dynamic>>{};
Map<String, dynamic>? turnoCajaPrueba(String id) {
  final t = _turnos[id];
  return t == null || t['estado'] == 'CERRADO' ? null : t;
}

Future<void> prepararCajaPrueba() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfiNoIsolate;
  dispositivoCajaPrueba = await DispositivoHelper.obtenerDispositivoId();
  _turnos.clear();
}

ApiClient apiCajaPrueba({http.Client? httpClient, required SessionManager sesiones}) {
  // Ninguna ruta desconocida tiene respaldo de red ni conexion configurada.
  final interno = httpClient ?? MockClient((_) async => http.Response('Sin red simulada', 503));
  return ApiClient(sesiones: sesiones, httpClient: MockClient((req) async {
    final id = req.url.path.split('/').last;
    if (req.method == 'GET' && req.url.path.contains('/cajas/turnos/') && id != 'activo' && _turnos.containsKey(id)) {
      return http.Response(jsonEncode({..._turnos[id]!, 'hora_central_en': DateTime.now().toUtc().toIso8601String()}), 200);
    }
    final respuesta = await interno.send(req);
    final r = await http.Response.fromStream(respuesta);
    if (r.statusCode >= 200 && r.statusCode < 300) {
      dynamic j;
      try { j = jsonDecode(r.body); } catch (_) {}
      if (j is Map && j['habilitacion_id'] != null && j['inicio_en'] != null) {
        final s = await sesiones.leerValida();
        final dto = <String, dynamic>{...j.cast<String, dynamic>(),
          'empresa_id': j['empresa_id'] ?? s?.usuario.empresaId,
          'hora_central_en': DateTime.now().toUtc().toIso8601String()};
        _turnos[dto['turno_id'] as String] = dto;
        return http.Response(jsonEncode(dto), r.statusCode);
      }
      if (req.method == 'POST' && id == 'cerrar' && j is Map && j['estado'] == 'CERRADO') {
        final turno = _turnos[j['turno_id']];
        if (turno != null) turno['estado'] = 'CERRADO';
      }
    }
    return r;
  }));
}

CajaService cajaDePrueba({ApiClient? api, SessionManager? sesiones, LocalDatabaseService? storage}) {
  final s = sesiones ?? SessionManager();
  return CajaService(api: api ?? apiCajaPrueba(sesiones: s), sesiones: s, storage: storage);
}

Future<void> fijarTurnoPrueba(CajaService caja, TurnoHabilitacionModel turno, {String? empresaId, String? usuarioId}) async {
  _turnos[turno.turnoId] = turno.toJson();
  await caja.fijarYPersistirTurnoLocal(turno, empresaId: empresaId, usuarioId: usuarioId);
}

Future<void> guardarVentaPrueba(CajaService caja, VentaOfflineCrearModel venta) async {
  await caja.registrarVentaFisicaOffline(operacionId: venta.operacionId, fechaLocal: DateTime.parse(venta.vendidaLocalEn),
    lineas: venta.lineas, totalBob: venta.totalBob, efectivoRecibidoBob: venta.efectivoRecibidoBob,
    cambioEntregadoBob: venta.cambioEntregadoBob, clienteId: venta.clienteId);
}
