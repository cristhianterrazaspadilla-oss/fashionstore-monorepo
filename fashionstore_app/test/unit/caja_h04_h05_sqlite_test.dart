import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:uuid/uuid.dart';
import 'package:fashionstore_movil/core/storage/local_database_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/core/session/dispositivo_helper.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/caja_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/caja_service.dart';

// SQLite FFI real; no se sustituye almacenamiento por mocks. HTTP siempre MockClient.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Database db;
  late LocalDatabaseService storage;
  const empresa = '11111111-1111-4111-8111-111111111111';
  const usuario = '22222222-2222-4222-8222-222222222222';
  late String dispositivo;
  const turnoId = '44444444-4444-4444-8444-444444444444';
  const variante = '55555555-5555-4555-8555-555555555555';
  const operacion = '66666666-6666-4666-8666-666666666666';

  TurnoHabilitacionModel turno({String id = turnoId, String? device, String estado = 'ABIERTO', bool vencido = false}) {
    final ahora = DateTime.now().toUtc();
    return TurnoHabilitacionModel(empresaId: empresa, horaCentralEn: ahora.toIso8601String(), turnoId: id, habilitacionId: id,
      cajaCodigo: 'CAJA-PRUEBA', dispositivoId: device ?? dispositivo, sucursalId: const Uuid().v4(), cajeroId: usuario, estado: estado,
      inicioEn: ahora.subtract(Duration(hours: vencido ? 9 : 0, seconds: 1)).toIso8601String(),
      venceEn: ahora.add(Duration(hours: vencido ? -1 : 8)).toIso8601String(), versionPrecios: 'v1', revision: 1,
      cupos: [CupoRespuestaModel(varianteId: variante, otorgado: 1, precioAutorizadoBob: 10)]);
  }
  VentaOfflineCrearModel venta({String id = operacion, int cantidad = 1}) {
    final fecha = DateTime.now().toUtc().toIso8601String();
    return VentaOfflineCrearModel(operacionId: id, secuenciaLocal: 0, vendidaLocalEn: fecha, entregadaLocalEn: fecha,
      versionPrecios: 'v1', lineas: [VentaOfflineLineaModel(varianteId: variante, cantidad: cantidad, precioAutorizadoBob: 10)],
      totalBob: 10.0 * cantidad, efectivoRecibidoBob: 10.0 * cantidad, cambioEntregadoBob: 0);
  }
  ComprobanteLocalModel recibo(VentaOfflineCrearModel v) => ComprobanteLocalModel(comprobanteId: const Uuid().v4(),
    operacionId: v.operacionId, turnoId: turnoId, empresaId: empresa, numeroComprobante: 'LOCAL', totalBob: v.totalBob,
    efectivoRecibidoBob: v.efectivoRecibidoBob, cambioBob: 0, emitidoEn: v.vendidaLocalEn);
  Future<VentaOfflineCrearModel> guardar(VentaOfflineCrearModel v, {bool fallar = false}) => storage.guardarVentaOfflineDurable(
    turnoId: turnoId, venta: v, empresaId: empresa, usuarioId: usuario, dispositivoId: dispositivo,
    rol: 'CAJERO', comprobante: recibo(v), simularFalloAntesDeCommit: fallar);
  Future<List<VentaOfflineCrearModel>> pendientes({String user = usuario, String company = empresa}) => storage.listarVentasOfflinePendientes(
    empresaId: company, usuarioId: user, dispositivoId: dispositivo);

  setUpAll(sqfliteFfiInit);
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    dispositivo = await DispositivoHelper.obtenerDispositivoId();
    db = await databaseFactoryFfiNoIsolate.openDatabase(inMemoryDatabasePath);
    storage = LocalDatabaseService(db: db);
    await storage.database;
    await storage.guardarTurnoActivoLocal(turno(), empresaId: empresa, usuarioId: usuario);
  });
  tearDown(() async { await db.close(); });

  test('cambio de identidad y segundo turno no borran ni reasignan pendientes', () async {
    await guardar(venta());
    expect(await pendientes(user: 'otro'), isEmpty);
    expect(await pendientes(company: 'otra'), isEmpty);
    await storage.guardarTurnoActivoLocal(turno(id: const Uuid().v4()), empresaId: empresa, usuarioId: usuario);
    final reinicio = LocalDatabaseService(db: db);
    final vs = await reinicio.listarVentasOfflinePendientes(empresaId: empresa, usuarioId: usuario, dispositivoId: dispositivo);
    expect(vs.single.turnoIdOrigen, turnoId);
    expect((await db.query('caja_turnos_activos')).length, 2);
  });

  test('mismo UUID no consume otra vez; cuerpo distinto da conflicto', () async {
    final v = venta();
    await guardar(v); await guardar(v);
    expect((await storage.obtenerCuposTurnoLocal(turnoId)).single.consumido, 1);
    expect((await db.query('caja_comprobantes_locales')).length, 1);
    await expectLater(guardar(venta(cantidad: 2)), throwsStateError);
    expect((await pendientes()).length, 1);
  });

  test('dos llamadas concurrentes por ultima unidad: solo una persiste', () async {
    final r = await Future.wait([guardar(venta()), guardar(venta(id: const Uuid().v4()))]
      .map((f) => f.then((_) => true).catchError((_) => false)));
    expect(r.where((ok) => ok).length, 1);
    expect((await storage.obtenerCuposTurnoLocal(turnoId)).single.consumido, 1);
    expect((await pendientes()).length, 1);
  });

  test('otro dispositivo, rol no autorizado y reloj atrasado no habilitan venta nueva', () async {
    final v = venta();
    await expectLater(storage.guardarVentaOfflineDurable(turnoId: turnoId, venta: v, empresaId: empresa,
      usuarioId: usuario, dispositivoId: 'otro-dispositivo', rol: 'CAJERO', comprobante: recibo(v)), throwsStateError);
    await expectLater(storage.guardarVentaOfflineDurable(turnoId: turnoId, venta: v, empresaId: empresa,
      usuarioId: usuario, dispositivoId: dispositivo, rol: 'CLIENTE', comprobante: recibo(v)), throwsStateError);
    await db.update('caja_turnos_activos', {'ultimo_reloj_ms': DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch},
      where: 'turno_id = ?', whereArgs: [turnoId]);
    await expectLater(guardar(v), throwsStateError);
    expect(await pendientes(), isEmpty);
    expect((await storage.obtenerCuposTurnoLocal(turnoId)).single.consumido, 0);
  });

  test('fallo intermedio revierte venta, cupo y comprobante', () async {
    final v = venta();
    await expectLater(guardar(v, fallar: true), throwsStateError);
    expect(await pendientes(), isEmpty);
    expect(await db.query('caja_comprobantes_locales'), isEmpty);
    expect((await storage.obtenerCuposTurnoLocal(turnoId)).single.consumido, 0);
    await guardar(v);
  });

  test('cupo insuficiente, conciliacion y vencimiento bloquean nuevas ventas', () async {
    await expectLater(guardar(venta(cantidad: 2)), throwsStateError);
    await storage.actualizarEstadoTurnoLocal(turnoId, 'CONCILIACION');
    await expectLater(guardar(venta()), throwsStateError);
    await storage.guardarTurnoActivoLocal(turno(vencido: true), empresaId: empresa, usuarioId: usuario);
    await expectLater(guardar(venta()), throwsStateError);
    expect((await storage.obtenerCuposTurnoLocal(turnoId)).single.liberado, 0);
  });

  test('cierre no destruye historial y pendiente impide devolver cupos', () async {
    await guardar(venta());
    expect(await storage.hayPendientesCajaTurno(turnoId, empresa), isTrue);
    await storage.limpiarTurnoActivoLocal(turnoId);
    expect((await pendientes()).length, 1);
    expect((await db.query('caja_cupos')).length, 1);
  });

  test('refresco central no vuelve a otorgar el consumo durable aunque falte el saldo anterior', () async {
    await guardar(venta());
    await db.delete('caja_cupos', where: 'turno_id = ?', whereArgs: [turnoId]);
    await storage.guardarTurnoActivoLocal(turno(), empresaId: empresa, usuarioId: usuario);
    expect((await storage.obtenerCuposTurnoLocal(turnoId)).single.consumido, 1);
    await expectLater(guardar(venta(id: const Uuid().v4())), throwsStateError);
  });

  test('legado incompleto queda diagnosticado, sin asignarse al usuario actual', () async {
    await db.insert('caja_ventas_offline', {'operacion_id': 'legado', 'empresa_id': null,
      'estado_sincronizacion': 'PENDIENTE_ENVIO', 'recuperacion_requerida': 1});
    expect(await pendientes(), isEmpty);
    expect(await storage.pendientesRecuperacionCaja(empresa, usuario, dispositivo), 1);
    expect((await db.query('caja_ventas_offline')).single['usuario_id'], isNull);
  });

  test('archivo SQLite v1 migra a v2 y conserva legado tras cerrar y reabrir', () async {
    final carpeta = await Directory.systemTemp.createTemp('fashionstore-caja-v1-');
    final ruta = '${carpeta.path}${Platform.pathSeparator}caja.db';
    LocalDatabaseService? migrado;
    try {
      final anterior = await databaseFactoryFfiNoIsolate.openDatabase(ruta, options: OpenDatabaseOptions(
        version: 1, onCreate: (bd, _) async {
          await bd.execute('''CREATE TABLE caja_turnos_activos (
            turno_id TEXT PRIMARY KEY, empresa_id TEXT, usuario_id TEXT, dispositivo_id TEXT,
            habilitacion_id TEXT, caja_codigo TEXT, sucursal_id TEXT, cajero_id TEXT, estado TEXT,
            inicio_en TEXT, vence_en TEXT, version_precios TEXT, revision INTEGER,
            snapshot_json TEXT, actualizado_en TEXT)''');
          await bd.execute('''CREATE TABLE caja_ventas_offline (
            operacion_id TEXT PRIMARY KEY, turno_id TEXT, empresa_id TEXT, usuario_id TEXT, dispositivo_id TEXT,
            secuencia_local INTEGER, vendida_local_en TEXT, entregada_local_en TEXT, version_precios TEXT,
            total_bob TEXT, efectivo_recibido_bob TEXT, cambio_entregado_bob TEXT, cliente_id TEXT,
            lineas_json TEXT, estado_sincronizacion TEXT, comprobante_local_id TEXT,
            sincronizada_en TEXT, resultado_json TEXT, error_mensaje TEXT)''');
          await bd.insert('caja_turnos_activos', {'turno_id': 'legado', 'empresa_id': empresa});
          await bd.insert('caja_ventas_offline', {'operacion_id': 'legado', 'turno_id': 'legado',
            'total_bob': '10.00', 'lineas_json': '[{"variante_id":"v","cantidad":1}]',
            'estado_sincronizacion': 'PENDIENTE_ENVIO'});
        }));
      await anterior.close();
      migrado = LocalDatabaseService(dbName: ruta);
      final bd = await migrado.database;
      expect(await bd.getVersion(), 2);
      expect((await bd.query('caja_turnos_activos')).single['origen_verificado'], 0);
      expect(await migrado.listarVentasOfflinePendientes(empresaId: empresa, usuarioId: usuario, dispositivoId: dispositivo), isEmpty);
      expect(await migrado.pendientesRecuperacionCaja(empresa, usuario, dispositivo), 1);
      await migrado.close();
      migrado = LocalDatabaseService(dbName: ruta);
      final fila = (await (await migrado.database).query('caja_ventas_offline')).single;
      expect(fila['total_bob'], '10.00');
      expect(fila['usuario_id'], isNull);
      expect(fila['cuerpo_json'], isNull);
      expect(fila['recuperacion_requerida'], 1);
    } finally {
      await migrado?.close();
      await carpeta.delete(recursive: true);
    }
  });

  test('respuesta perdida y cambio de usuario: reintento exacto bajo turno original', () async {
    final sesiones = SessionManager();
    Future<void> login(String user, String company) => sesiones.guardar(token: const Uuid().v4(), usuario: ClientePerfilModel(
      id: user, usuarioId: user, empresaId: company, nombres: 'Prueba', apellidos: 'Aislada', nombreCompleto: 'Prueba Aislada',
      correoElectronico: 'prueba@example.test', rol: 'CAJERO', estado: 'ACTIVO', preferencias: {}, creadoEn: DateTime.now()));
    await login(usuario, empresa);
    final d = await DispositivoHelper.obtenerDispositivoId();
    final cuerpos = <String>[], rutas = <String>[];
    bool perder = true;
    final cliente = MockClient((req) async {
      if (req.method == 'GET') return http.Response(jsonEncode(turno(device: d).toJson()), 200);
      rutas.add(req.url.path); cuerpos.add(req.body);
      if (perder) { perder = false; throw const SocketException('Respuesta perdida simulada'); }
      return http.Response(jsonEncode({'resultado': 'REGISTRADA_CENTRAL', 'operacion_id': operacion,
        'venta_id': operacion, 'numero': 'CENTRAL', 'total_bob': '10.00', 'comprobante_id': operacion,
        'recibida_central_en': DateTime.now().toUtc().toIso8601String()}), 200);
    });
    final caja = CajaService(api: ApiClient(httpClient: cliente, sesiones: sesiones), sesiones: sesiones, storage: storage);
    await caja.fijarYPersistirTurnoLocal(turno(device: d));
    await caja.registrarVentaFisicaOffline(operacionId: operacion,
      lineas: [VentaOfflineLineaModel(varianteId: variante, cantidad: 1, precioAutorizadoBob: 10)],
      totalBob: 10, efectivoRecibidoBob: 10, cambioEntregadoBob: 0);
    expect(await caja.sincronizarVentasPendientes(null), 0);
    await login('otro-usuario', 'otra-empresa');
    await caja.restaurarDesdeStorage(); expect(caja.ventasOfflinePendientes, isEmpty);
    expect(await caja.sincronizarVentasPendientes(null), 0);
    await login(usuario, empresa);
    await caja.restaurarDesdeStorage();
    expect(await caja.sincronizarVentasPendientes(null), 1);
    expect(cuerpos.length, 2); expect(cuerpos[0], cuerpos[1]);
    expect(rutas.every((r) => r.endsWith('/cajas/turnos/$turnoId/ventas')), isTrue);
    expect((await db.query('caja_ventas_offline', where: 'operacion_id = ?', whereArgs: [operacion])).single['resultado_json'], isNotNull);
  });
}
