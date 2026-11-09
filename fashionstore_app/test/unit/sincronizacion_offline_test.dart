import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/core/network/api_exception.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/core/storage/local_database_service.dart';
import 'package:fashionstore_movil/core/utils/bolivia_time.dart';
import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/models/sincronizacion_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/services/sincronizacion_offline_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/stripe_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfiNoIsolate;
  });

  group('SincronizacionOfflineService (CU04 & CU18)', () {
    late LocalDatabaseService storage;
    late SessionManager sessionManager;

    const testEmpresaId = '00000000-0000-4000-8000-000000000001';
    const testUsuarioId = '11111111-1111-4111-8111-111111111111';
    const testSucursalId = '22222222-2222-4222-8222-222222222222';
    const testVarianteId = '33333333-3333-4333-8333-333333333333';

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      storage = LocalDatabaseService(dbName: inMemoryDatabasePath);
      sessionManager = SessionManager();
      await sessionManager.guardar(
        token: 'token-jwt-test',
        usuario: ClientePerfilModel(
          id: testUsuarioId,
          usuarioId: testUsuarioId,
          empresaId: testEmpresaId,
          nombres: 'Cliente',
          apellidos: 'Prueba',
          nombreCompleto: 'Cliente Prueba',
          correoElectronico: 'cliente@prueba.com',
          rol: 'CLIENTE',
          estado: 'ACTIVO',
          preferencias: {},
          creadoEn: DateTime.now(),
        ),
      );
    });

    tearDown(() async {
      await storage.close();
    });

    test('obtiene y persiste referencia horaria central en SQLite', () async {
      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/sincronizacion/referencias-horarias')) {
          return http.Response(
            jsonEncode({
              'id': '44444444-4444-4444-8444-444444444444',
              'empresa_id': testEmpresaId,
              'usuario_id': testUsuarioId,
              'dispositivo_id': 'disp-android-1',
              'hora_central_en': '2026-11-01T15:30:00-04:00',
              'valida_hasta': '2030-11-01T23:30:00-04:00',
              'tolerancia_segundos': 120,
              'politica_version': 1,
              'emitida_en': '2026-11-01T15:30:00-04:00',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final apiClient = ApiClient(httpClient: mockHttp, sesiones: sessionManager);
      final service = SincronizacionOfflineService(
        api: apiClient,
        storage: storage,
        sesiones: sessionManager,
      );

      final ref = await service.obtenerOGenerarReferencia(
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: 'disp-android-1',
      );

      expect(ref.id, '44444444-4444-4444-8444-444444444444');
      expect(ref.toleranciaSegundos, 120);

      final refGuardada = await storage.obtenerReferenciaHorariaValida(empresaId: testEmpresaId);
      expect(refGuardada, isNotNull);
      expect(refGuardada!.id, '44444444-4444-4444-8444-444444444444');
      expect(refGuardada.empresaId, testEmpresaId);
    });

    test('rechaza registro offline si no existe referencia horaria válida en SQLite', () async {
      final service = SincronizacionOfflineService(
        storage: storage,
        sesiones: sessionManager,
      );

      expect(
        () => service.registrarReservaOffline(
          empresaId: testEmpresaId,
          usuarioId: testUsuarioId,
          dispositivoId: 'disp-uuid-99',
          sucursalId: testSucursalId,
          fechaVisitaEstimada: '2026-11-03T16:00:00-04:00',
          items: [
            {'variante_id': testVarianteId, 'cantidad': 2},
          ],
        ),
        throwsA(isA<ApiException>().having(
          (e) => e.statusCode,
          'statusCode',
          428,
        )),
      );
    });

    test('registra reserva offline en SQLite con cuerpo estricto 0.3.2 y hora Bolivia (-04:00)', () async {
      final ref = ReferenciaHorariaModel(
        id: '44444444-4444-4444-8444-444444444444',
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: 'disp-uuid-99',
        horaCentralEn: '2026-11-01T14:00:00-04:00',
        validaHasta: '2030-11-01T22:00:00-04:00',
        toleranciaSegundos: 60,
        politicaVersion: 1,
        emitidaEn: '2026-11-01T14:00:00-04:00',
      );
      await storage.guardarReferenciaHoraria(ref);

      final service = SincronizacionOfflineService(
        storage: storage,
        sesiones: sessionManager,
      );

      final op = await service.registrarReservaOffline(
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: 'disp-uuid-99',
        sucursalId: testSucursalId,
        fechaVisitaEstimada: '2026-11-03T16:00:00-04:00',
        items: [
          {'variante_id': testVarianteId, 'cantidad': 2},
        ],
        notas: 'Nota que no debe filtrarse a datos',
      );

      expect(op.operacionId, isNotEmpty);
      expect(op.estadoEnvio, 'PENDIENTE_ENVIO');
      expect(op.referenciaHorariaId, '44444444-4444-4444-8444-444444444444');
      expect(op.creadaLocalEn.contains('-04:00'), isTrue);

      final ops = await storage.listarOperacionesCola(empresaId: testEmpresaId);
      expect(ops.length, 1);
      expect(ops.first.operacionId, op.operacionId);

      // Verificación estricta de contrato 0.3.2: datos solo admite sucursal_id, visita_en, lineas
      final datos = ops.first.datos;
      expect(datos.containsKey('fecha_local'), isFalse, reason: 'fecha_local está prohibido en datos');
      expect(datos.containsKey('notas'), isFalse, reason: 'notas está prohibido en datos');
      expect(datos['sucursal_id'], testSucursalId);
      expect(datos['visita_en'], isNotNull);
      expect(datos['lineas'], isA<List>());
      expect((datos['lineas'] as List).first['variante_id'], testVarianteId);
      expect((datos['lineas'] as List).first['cantidad'], 2);

      // Verificación de toApiPayload contra estructura exacta de OperacionDTO
      final payload = op.toApiPayload();
      expect(payload['version_esquema'], 1);
      expect(payload['tipo'], 'SOLICITAR_RESERVA');
      expect(payload['operacion_id'], op.operacionId);
      expect(payload['empresa_id'], testEmpresaId);
      expect(payload['usuario_id'], testUsuarioId);
      expect(payload['dispositivo_id'], 'disp-uuid-99');
      expect(payload['secuencia_local'], 1);
      expect(payload['referencia_horaria_id'], '44444444-4444-4444-8444-444444444444');
      expect((payload['datos'] as Map).containsKey('fecha_local'), isFalse);
    });

    test('sincronización: si una operación quedó ENVIANDO consulta GET por UUID original antes de re-enviar', () async {
      final op = OperacionSincronizacionLocal(
        operacionId: '55555555-5555-4555-8555-555555555555',
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: 'disp-1',
        secuenciaLocal: 1,
        referenciaHorariaId: '44444444-4444-4444-8444-444444444444',
        creadaLocalEn: BoliviaTime.ahoraIso(),
        datosJson: jsonEncode({
          'sucursal_id': testSucursalId,
          'visita_en': '2026-11-02T10:00:00-04:00',
          'lineas': [
            {'variante_id': testVarianteId, 'cantidad': 1}
          ],
        }),
        estadoEnvio: 'ENVIANDO', // Quedó en enviando tras corte de conexión
        actualizadoEn: BoliviaTime.ahoraIso(),
      );
      await storage.encolarOperacion(op);

      bool consultoUuid = false;
      bool envioPost = false;

      final mockHttp = MockClient((request) async {
        if (request.method == 'GET' && request.url.path.contains('/sincronizacion/operaciones/55555555-5555-4555-8555-555555555555')) {
          consultoUuid = true;
          // Servidor ya la había procesado
          return http.Response(
            jsonEncode({
              'operacion_id': '55555555-5555-4555-8555-555555555555',
              'estado': 'ACEPTADA',
              'codigo': 'OK',
              'recibida_en': '2026-11-01T15:00:00-04:00',
              'detalle': 'Reserva aceptada previamente',
              'recurso_id': '66666666-6666-4666-8666-666666666666',
              'revision': 1,
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.method == 'POST' && request.url.path.contains('/sincronizacion/operaciones')) {
          envioPost = true;
          return http.Response('Unexpected POST', 500);
        }
        return http.Response('Not found', 404);
      });

      final apiClient = ApiClient(httpClient: mockHttp, sesiones: sessionManager);
      final service = SincronizacionOfflineService(
        api: apiClient,
        storage: storage,
        sesiones: sessionManager,
      );

      final resultados = await service.sincronizarCola(empresaId: testEmpresaId, usuarioId: testUsuarioId);

      expect(consultoUuid, isTrue);
      expect(envioPost, isFalse, reason: 'No debe hacer POST duplicado si el GET por UUID confirma recepción previa');
      expect(resultados.length, 1);
      expect(resultados.first.estado, 'ACEPTADA');

      // Persistencia durable en SQLite
      final opActualizada = await storage.obtenerOperacion('55555555-5555-4555-8555-555555555555');
      expect(opActualizada!.estadoEnvio, 'ACEPTADA');
      expect(opActualizada.resultado!['recurso_id'], '66666666-6666-4666-8666-666666666666');
    });

    test('sincronización: si GET devuelve 404 hace POST con UUID original y persiste resultado durable', () async {
      final op = OperacionSincronizacionLocal(
        operacionId: '77777777-7777-4777-8777-777777777777',
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: 'disp-1',
        secuenciaLocal: 1,
        referenciaHorariaId: '44444444-4444-4444-8444-444444444444',
        creadaLocalEn: BoliviaTime.ahoraIso(),
        datosJson: jsonEncode({
          'sucursal_id': testSucursalId,
          'visita_en': '2026-11-02T10:00:00-04:00',
          'lineas': [
            {'variante_id': testVarianteId, 'cantidad': 1}
          ],
        }),
        estadoEnvio: 'ENVIANDO',
        actualizadoEn: BoliviaTime.ahoraIso(),
      );
      await storage.encolarOperacion(op);

      bool consultoUuid = false;
      bool envioPost = false;
      String? uuidEnviadoEnPost;

      final mockHttp = MockClient((request) async {
        if (request.method == 'GET' && request.url.path.contains('/sincronizacion/operaciones/77777777-7777-4777-8777-777777777777')) {
          consultoUuid = true;
          return http.Response(jsonEncode({'detail': 'No encontrada'}), 404);
        }
        if (request.method == 'POST' && request.url.path.contains('/sincronizacion/operaciones')) {
          envioPost = true;
          final body = jsonDecode(request.body) as Map;
          uuidEnviadoEnPost = body['operacion_id'] as String?;
          return http.Response(
            jsonEncode({
              'operacion_id': '77777777-7777-4777-8777-777777777777',
              'estado': 'CONFLICTO',
              'codigo': 'SIN_STOCK',
              'recibida_en': '2026-11-01T15:00:00-04:00',
              'detalle': 'Stock no disponible al sincronizar',
              'revision': 0,
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final apiClient = ApiClient(httpClient: mockHttp, sesiones: sessionManager);
      final service = SincronizacionOfflineService(
        api: apiClient,
        storage: storage,
        sesiones: sessionManager,
      );

      final resultados = await service.sincronizarCola(empresaId: testEmpresaId, usuarioId: testUsuarioId);

      expect(consultoUuid, isTrue);
      expect(envioPost, isTrue);
      expect(uuidEnviadoEnPost, '77777777-7777-4777-8777-777777777777');
      expect(resultados.length, 1);
      expect(resultados.first.estado, 'CONFLICTO');

      final opDurable = await storage.obtenerOperacion('77777777-7777-4777-8777-777777777777');
      expect(opDurable!.estadoEnvio, 'CONFLICTO');
    });

    test('aislamiento de privacidad: usuario B no puede ver ni sincronizar pendientes de usuario A', () async {
      final opA = OperacionSincronizacionLocal(
        operacionId: '88888888-8888-4888-8888-888888888888',
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: 'disp-A',
        secuenciaLocal: 1,
        referenciaHorariaId: '44444444-4444-4444-8444-444444444444',
        creadaLocalEn: BoliviaTime.ahoraIso(),
        datosJson: jsonEncode({
          'sucursal_id': testSucursalId,
          'visita_en': '2026-11-02T10:00:00-04:00',
          'lineas': [
            {'variante_id': testVarianteId, 'cantidad': 1}
          ],
        }),
        estadoEnvio: 'PENDIENTE_ENVIO',
        actualizadoEn: BoliviaTime.ahoraIso(),
      );
      await storage.encolarOperacion(opA);

      // Cambiar sesión a Usuario B
      const usuarioBId = '99999999-9999-4999-8999-999999999999';
      await sessionManager.guardar(
        token: 'token-usr-b',
        usuario: ClientePerfilModel(
          id: usuarioBId,
          usuarioId: usuarioBId,
          empresaId: testEmpresaId,
          nombres: 'Usuario',
          apellidos: 'B',
          nombreCompleto: 'Usuario B',
          correoElectronico: 'b@empresa.com',
          rol: 'CLIENTE',
          estado: 'ACTIVO',
          preferencias: {},
          creadoEn: DateTime.now(),
        ),
      );

      final service = SincronizacionOfflineService(
        storage: storage,
        sesiones: sessionManager,
      );

      // Usuario B lista operaciones
      final opsB = await service.listarOperaciones();
      expect(opsB, isEmpty, reason: 'Usuario B no debe ver la cola de Usuario A');

      // Usuario B intenta sincronizar
      final resB = await service.sincronizarPendientes();
      expect(resB, isEmpty, reason: 'Usuario B no debe sincronizar operaciones de Usuario A');

      // La operación de A sigue intacta en la base de datos
      final opAIntacta = await storage.obtenerOperacion('88888888-8888-4888-8888-888888888888');
      expect(opAIntacta, isNotNull);
      expect(opAIntacta!.estadoEnvio, 'PENDIENTE_ENVIO');
    });

    test('ventana de 8 horas: sesión mayor a 8 horas no sincroniza ni lista', () async {
      // Guardar sesión guardada hace 9 horas
      await sessionManager.guardar(
        token: 'token-expirado',
        usuario: ClientePerfilModel(
          id: testUsuarioId,
          usuarioId: testUsuarioId,
          empresaId: testEmpresaId,
          nombres: 'Cliente',
          apellidos: 'Viejo',
          nombreCompleto: 'Cliente Viejo',
          correoElectronico: 'viejo@prueba.com',
          rol: 'CLIENTE',
          estado: 'ACTIVO',
          preferencias: {},
          creadoEn: DateTime.now().subtract(const Duration(hours: 10)),
        ),
        ahora: DateTime.now().subtract(const Duration(hours: 9)),
      );

      final service = SincronizacionOfflineService(
        storage: storage,
        sesiones: sessionManager,
      );

      final ops = await service.listarOperaciones();
      expect(ops, isEmpty, reason: 'Sesión mayor a 8 horas no debe listar operaciones');

      final res = await service.sincronizarPendientes();
      expect(res, isEmpty, reason: 'Sesión mayor a 8 horas no debe sincronizar');
    });

    test('BoliviaTime respeta ventana privada de 8 horas desde emitida_en', () {
      final ahora = DateTime.now();
      final hace4Horas = ahora.subtract(const Duration(hours: 4));
      final hace9Horas = ahora.subtract(const Duration(hours: 9));

      final strHace4Horas = BoliviaTime.aIso8601Bolivia(hace4Horas);
      final strHace9Horas = BoliviaTime.aIso8601Bolivia(hace9Horas);

      expect(BoliviaTime.estaDentroVentana8Horas(strHace4Horas), isTrue);
      expect(BoliviaTime.estaDentroVentana8Horas(strHace9Horas), isFalse);
    });

    test('Canonicalización exacta v3 (Vector 1 RECOJO y Vector 2 DELIVERY)', () {
      final h1 = calcularHuellaCompraCanonica(
        empresaId: '11111111-1111-1111-1111-111111111111',
        usuarioId: '55555555-5555-5555-5555-555555555555',
        sucursalId: '33333333-3333-3333-3333-333333333333',
        modalidad: 'RECOJO',
        lineas: [
          {
            'cantidad': 1,
            'precio_unitario_bob': '100.00',
            'variante_id': '22222222-2222-2222-2222-222222222222',
          }
        ],
        baseBob: 100.0,
        descuentoBob: 0.0,
        envioBob: 0.0,
        totalBob: 100.0,
        monedaCobro: 'USD',
        importeCobro: 14.37,
        tasaId: '44444444-4444-4444-4444-444444444444',
        tasaBobPorUsd: 6.96,
        condicionesVersion: 'v3',
        vigenteHasta: '2026-11-06T15:00:00Z',
      );
      expect(h1, equals('5249e0cea418ec6262f9f0ef7a71686d2d6cecf8c4083dafe77aa0d24c3eacee'));

      final h2 = calcularHuellaCompraCanonica(
        empresaId: '11111111-1111-1111-1111-111111111111',
        usuarioId: '55555555-5555-5555-5555-555555555555',
        sucursalId: '33333333-3333-3333-3333-333333333333',
        modalidad: 'DELIVERY',
        direccion: 'Av. Las Americas 123',
        lineas: [
          {
            'cantidad': 1,
            'precio_unitario_bob': '100.00',
            'variante_id': '22222222-2222-2222-2222-222222222222',
          }
        ],
        baseBob: 100.0,
        descuentoBob: 0.0,
        envioBob: 15.0,
        totalBob: 115.0,
        monedaCobro: 'USD',
        importeCobro: 16.52,
        tasaId: '44444444-4444-4444-4444-444444444444',
        tasaBobPorUsd: 6.96,
        condicionesVersion: 'v3',
        vigenteHasta: '2026-11-06T15:00:00Z',
      );
      expect(h2, equals('b095703bdd526b2a7da5d97f5e52dbe7ec7a118d72511c72b9602cd03fd98f07'));
    });

    test('encolarCompraOffline con autorizacionCobro == null omite autorizacion_cobro en SQLite (CU05 Bloqueo 3)', () async {
      final ref = ReferenciaHorariaModel(
        id: '44444444-4444-4444-8444-444444444444',
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: 'disp-android-1',
        horaCentralEn: '2026-11-01T14:00:00-04:00',
        validaHasta: '2030-11-01T22:00:00-04:00',
        toleranciaSegundos: 60,
        politicaVersion: 1,
        emitidaEn: '2026-11-01T14:00:00-04:00',
      );
      await storage.guardarReferenciaHoraria(ref);

      final service = SincronizacionOfflineService(
        storage: storage,
        sesiones: sessionManager,
      );

      final op = await service.encolarCompraOffline(
        sucursalId: testSucursalId,
        lineas: [
          {'variante_id': testVarianteId, 'cantidad': 1, 'precio_unitario_bob': 100.0}
        ],
        modalidad: 'RECOJO',
        autorizacionCobro: null,
        dispositivoId: 'disp-android-1',
      );

      final decoded = jsonDecode(op.datosJson) as Map<String, dynamic>;
      expect(decoded.containsKey('autorizacion_cobro'), isFalse);
      expect(decoded['sucursal_id'], equals(testSucursalId));
      expect(decoded['modalidad'], equals('RECOJO'));
    });

    test('encolarCompraOffline con autorizacionCobro completa de 15 campos persiste bloque en SQLite (CU05)', () async {
      final ref = ReferenciaHorariaModel(
        id: '44444444-4444-4444-8444-444444444444',
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: 'disp-android-1',
        horaCentralEn: '2026-11-01T14:00:00-04:00',
        validaHasta: '2030-11-01T22:00:00-04:00',
        toleranciaSegundos: 60,
        politicaVersion: 1,
        emitidaEn: '2026-11-01T14:00:00-04:00',
      );
      await storage.guardarReferenciaHoraria(ref);

      final service = SincronizacionOfflineService(
        storage: storage,
        sesiones: sessionManager,
      );

      final auth15Campos = {
        'consentimiento_id': '11111111-2222-3333-4444-555555555555',
        'aceptado_local_en': '2026-11-05T15:00:00-04:00',
        'huella_compra': 'a' * 64,
        'base_bob': '100.00',
        'descuento_bob': '0.00',
        'envio_bob': '0.00',
        'total_bob': '100.00',
        'moneda_cobro': 'USD',
        'importe_cobro': '14.37',
        'tasa_id': 'tasa-uuid-1',
        'tasa_bob_por_usd': '6.96',
        'condiciones_version': 'v3',
        'vigente_hasta': '2026-11-06T15:00:00Z',
        'preparacion_pago_id': 'prep-uuid-1',
        'permite_cobro_al_reconectar': true,
      };

      final op = await service.encolarCompraOffline(
        sucursalId: testSucursalId,
        lineas: [
          {'variante_id': testVarianteId, 'cantidad': 1, 'precio_unitario_bob': 100.0}
        ],
        modalidad: 'RECOJO',
        autorizacionCobro: auth15Campos,
        dispositivoId: 'disp-android-1',
      );

      final decoded = jsonDecode(op.datosJson) as Map<String, dynamic>;
      expect(decoded.containsKey('autorizacion_cobro'), isTrue);
      final persistedAuth = decoded['autorizacion_cobro'] as Map<String, dynamic>;
      expect(persistedAuth.keys.length, equals(15));
      expect(persistedAuth['permite_cobro_al_reconectar'], isTrue);
      expect(persistedAuth['preparacion_pago_id'], equals('prep-uuid-1'));
    });
  });
}
