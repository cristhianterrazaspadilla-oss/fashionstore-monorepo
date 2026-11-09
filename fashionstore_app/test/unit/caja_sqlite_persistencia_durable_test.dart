import '../caja_fixture_aislada.dart';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/core/storage/local_database_service.dart';
import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/caja_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/caja_service.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('Persistencia SQLite Durable de Caja Offline (CU06 / CU07)', () {
    const testEmpresaId = '11111111-1111-4111-8111-111111111111';
    const testEmpresaIdB = '99999999-9999-4999-8999-999999999999';
    const testUsuarioId = '22222222-2222-4222-8222-222222222222';
    const testSucursalId = '33333333-3333-4333-8333-333333333333';
    const testVarianteId = '44444444-4444-4444-8444-444444444444';
    const testTurnoId = '55555555-5555-4555-8555-555555555555';
    const testDbName = 'caja_durable_test.db';

    late SessionManager sessionManager;
    late LocalDatabaseService storage;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await prepararCajaPrueba();
      sessionManager = SessionManager();
      await sessionManager.guardar(
        token: 'token-cajero-durable-test',
        usuario: ClientePerfilModel(
          id: testUsuarioId,
          usuarioId: testUsuarioId,
          empresaId: testEmpresaId,
          nombres: 'Cajero',
          apellidos: 'Durable',
          nombreCompleto: 'Cajero Durable',
          correoElectronico: 'cajero.durable@fashionstore.test',
          rol: 'CAJERO',
          estado: 'ACTIVO',
          preferencias: {},
          creadoEn: DateTime.now(),
        ),
      );

      storage = LocalDatabaseService(dbName: testDbName);
      await storage.limpiarTodo();
    });

    tearDown(() async {
      await storage.limpiarTodo();
      await storage.close();
    });

    test('Persistencia atómica de turno habilitado y recuperación transparente tras reinicio', () async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/cajas/turnos') && request.method == 'POST') {
          return http.Response(
            jsonEncode({
              'turno_id': testTurnoId,
              'habilitacion_id': testTurnoId,
              'caja_codigo': 'CAJA-TABLET-01',
              'dispositivo_id': dispositivoCajaPrueba,
              'sucursal_id': testSucursalId,
              'cajero_id': testUsuarioId,
              'estado': 'ABIERTO',
              'inicio_en': ahora.toIso8601String(),
              'vence_en': vence.toIso8601String(),
              'version_precios': 'v-precios-1',
              'revision': 1,
              'cupos': [
                {
                  'variante_id': testVarianteId,
                  'sku': 'SKU-VESTIDO-FIESTA',
                  'producto_nombre': 'Vestido de Fiesta',
                  'otorgado': 10,
                  'consumido': 0,
                  'liberado': 0,
                  'precio_autorizado_bob': '250.00',
                }
              ],
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaService1 = cajaDePrueba(api: api, sesiones: sessionManager, storage: storage);

      // 1. Habilitar turno online
      final turno = await cajaService1.habilitarTurno(TurnoCrearModel(
        cajaId: 'CAJA-TABLET-01',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cupos: [CupoItemModel(varianteId: testVarianteId, cantidad: 10)],
      ));

      expect(turno.turnoId, testTurnoId);
      expect(cajaService1.turnoActivoLocal, isNotNull);

      // 2. Simular que se mata la app (nueva instancia de servicio sin API, simulando offline)
      final cajaServiceReiniciada = cajaDePrueba(
        api: null,
        sesiones: sessionManager,
        storage: storage,
      );
      expect(cajaServiceReiniciada.turnoActivoLocal, isNull);

      // 3. Restaurar desde SQLite de forma transparente
      await cajaServiceReiniciada.restaurarDesdeStorage(
        empresaId: testEmpresaId,
        dispositivoId: dispositivoCajaPrueba,
      );

      final turnoRestaurado = cajaServiceReiniciada.turnoActivoLocal;
      expect(turnoRestaurado, isNotNull);
      expect(turnoRestaurado!.turnoId, testTurnoId);
      expect(turnoRestaurado.cajaCodigo, 'CAJA-TABLET-01');
      expect(turnoRestaurado.estado, 'ABIERTO');
      expect(turnoRestaurado.cupos.length, 1);
      expect(turnoRestaurado.cupos.first.otorgado, 10);
      expect(turnoRestaurado.cupos.first.disponible, 10);
      expect(turnoRestaurado.cupos.first.precioAutorizadoBob, 250.0);
    });

    test('Cobro de venta física offline en efectivo: comprobante inmediato y persistencia durable de cupos', () async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final cajaService = cajaDePrueba(sesiones: sessionManager, storage: storage);
      final turno = TurnoHabilitacionModel(
        empresaId: testEmpresaId,
        horaCentralEn: DateTime.now().toUtc().toIso8601String(),
        turnoId: testTurnoId,
        habilitacionId: testTurnoId,
        cajaCodigo: 'CAJA-TABLET-01',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cajeroId: testUsuarioId,
        estado: 'ABIERTO',
        inicioEn: ahora.toIso8601String(),
        venceEn: vence.toIso8601String(),
        versionPrecios: 'v-precios-1',
        revision: 1,
        cupos: [
          CupoRespuestaModel(
            varianteId: testVarianteId,
            sku: 'SKU-VESTIDO-FIESTA',
            productoNombre: 'Vestido de Fiesta',
            otorgado: 10,
            consumido: 0,
            precioAutorizadoBob: 250.0,
          )
        ],
      );

      await fijarTurnoPrueba(cajaService, turno, empresaId: testEmpresaId, usuarioId: testUsuarioId);

      // Cobrar 3 unidades en efectivo offline (3 * 250 = 750 Bs)
      final comprobante = await cajaService.registrarVentaFisicaOffline(
        lineas: [
          VentaOfflineLineaModel(
            varianteId: testVarianteId,
            cantidad: 3,
            precioAutorizadoBob: 250.0,
          )
        ],
        totalBob: 750.0,
        efectivoRecibidoBob: 800.0,
        cambioEntregadoBob: 50.0,
      );

      // Verificaciones del comprobante local emitido de inmediato
      expect(comprobante.comprobanteId, isNotEmpty);
      expect(comprobante.numeroComprobante.startsWith('COMP-LOC-'), isTrue);
      expect(comprobante.totalBob, 750.0);
      expect(comprobante.efectivoRecibidoBob, 800.0);
      expect(comprobante.cambioBob, 50.0);

      // Cupos descontados
      expect(cajaService.turnoActivoLocal!.cupos.first.consumido, 3);
      expect(cajaService.turnoActivoLocal!.cupos.first.disponible, 7);
      expect(cajaService.ventasOfflinePendientes.length, 1);

      // Comprobante registrado en SQLite
      final comprobantesLocales = await cajaService.listarComprobantesLocales(testTurnoId);
      expect(comprobantesLocales.length, 1);
      expect(comprobantesLocales.first.numeroComprobante, comprobante.numeroComprobante);

      // Simular reinicio de la aplicación y verificar que no se pierden ni la venta ni los cupos consumidos
      final cajaServiceReinicio = cajaDePrueba(sesiones: sessionManager, storage: storage);
      await cajaServiceReinicio.restaurarDesdeStorage(
        empresaId: testEmpresaId,
        dispositivoId: dispositivoCajaPrueba,
      );

      expect(cajaServiceReinicio.turnoActivoLocal, isNotNull);
      expect(cajaServiceReinicio.turnoActivoLocal!.cupos.first.consumido, 3);
      expect(cajaServiceReinicio.turnoActivoLocal!.cupos.first.disponible, 7);
      expect(cajaServiceReinicio.ventasOfflinePendientes.length, 1);
      expect(cajaServiceReinicio.ventasOfflinePendientes.first.operacionId, comprobante.operacionId);
    });

    test('Sincronización preserva estrictamente el UUID de operacion_id original', () async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      String? operacionIdEnviadoAlBackend;
      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/ventas') && request.method == 'POST') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          operacionIdEnviadoAlBackend = body['operacion_id'];

          return http.Response(
            jsonEncode({
              'resultado': 'REGISTRADA_CENTRAL',
              'operacion_id': operacionIdEnviadoAlBackend,
              'venta_id': '88888888-8888-4888-8888-888888888888',
              'numero': 'VNT-CENTRAL-0099',
              'total_bob': 500.0,
              'comprobante_id': '99999999-9999-4999-8999-999999999999',
              'recibida_central_en': ahora.toIso8601String(),
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaService = cajaDePrueba(api: api, sesiones: sessionManager, storage: storage);

      final turno = TurnoHabilitacionModel(
        empresaId: testEmpresaId,
        horaCentralEn: DateTime.now().toUtc().toIso8601String(),
        turnoId: testTurnoId,
        habilitacionId: testTurnoId,
        cajaCodigo: 'CAJA-TABLET-01',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cajeroId: testUsuarioId,
        estado: 'ABIERTO',
        inicioEn: ahora.toIso8601String(),
        venceEn: vence.toIso8601String(),
        versionPrecios: 'v-precios-1',
        revision: 1,
        cupos: [
          CupoRespuestaModel(
            varianteId: testVarianteId,
            sku: 'SKU-VESTIDO-FIESTA',
            productoNombre: 'Vestido de Fiesta',
            otorgado: 5,
            consumido: 0,
            precioAutorizadoBob: 250.0,
          )
        ],
      );

      await fijarTurnoPrueba(cajaService, turno, empresaId: testEmpresaId, usuarioId: testUsuarioId);

      final comp = await cajaService.registrarVentaFisicaOffline(
        lineas: [
          VentaOfflineLineaModel(
            varianteId: testVarianteId,
            cantidad: 2,
            precioAutorizadoBob: 250.0,
          )
        ],
        totalBob: 500.0,
        efectivoRecibidoBob: 500.0,
        cambioEntregadoBob: 0.0,
      );

      final originalOperacionId = comp.operacionId;

      // Sincronizar
      final sincronizadas = await cajaService.sincronizarVentasPendientes(testTurnoId);
      expect(sincronizadas, 1);
      expect(operacionIdEnviadoAlBackend, originalOperacionId);
      expect(cajaService.ventasOfflinePendientes.isEmpty, isTrue);

      // Comprobar que en SQLite ya no figura como pendiente
      final pendientesEnBd = await storage.listarVentasOfflinePendientes(
        empresaId: testEmpresaId,
        turnoId: testTurnoId,
        usuarioId: testUsuarioId, dispositivoId: dispositivoCajaPrueba,
      );
      expect(pendientesEnBd.isEmpty, isTrue);
    });

    test('Aislamiento estricto: empresa B no accede al turno ni a las ventas de empresa A', () async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final cajaServiceA = cajaDePrueba(sesiones: sessionManager, storage: storage);
      final turnoA = TurnoHabilitacionModel(
        empresaId: testEmpresaId,
        horaCentralEn: DateTime.now().toUtc().toIso8601String(),
        turnoId: testTurnoId,
        habilitacionId: testTurnoId,
        cajaCodigo: 'CAJA-EMPRESA-A',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cajeroId: testUsuarioId,
        estado: 'ABIERTO',
        inicioEn: ahora.toIso8601String(),
        venceEn: vence.toIso8601String(),
        versionPrecios: 'v-precios-1',
        revision: 1,
        cupos: [
          CupoRespuestaModel(
            varianteId: testVarianteId,
            otorgado: 5,
            consumido: 0,
            precioAutorizadoBob: 100.0,
          )
        ],
      );

      await fijarTurnoPrueba(cajaServiceA, turnoA, empresaId: testEmpresaId, usuarioId: testUsuarioId);
      await cajaServiceA.registrarVentaFisicaOffline(
        lineas: [VentaOfflineLineaModel(varianteId: testVarianteId, cantidad: 1, precioAutorizadoBob: 100.0)],
        totalBob: 100.0,
        efectivoRecibidoBob: 100.0,
        cambioEntregadoBob: 0.0,
      );

      // Ahora un cajero de Empresa B inicia servicio
      final perfilA = (await sessionManager.leerValida())!.usuario;
      const usuarioB = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
      await sessionManager.guardar(token: 'token-sintetico-B', usuario: ClientePerfilModel.fromJson({
        ...perfilA.toJson(), 'empresa_id': testEmpresaIdB, 'usuario_id': usuarioB, 'id': usuarioB,
      }));
      final cajaServiceB = cajaDePrueba(storage: storage);
      await cajaServiceB.restaurarDesdeStorage(
        empresaId: testEmpresaIdB,
        dispositivoId: dispositivoCajaPrueba,
      );

      // Empresa B no debe ver el turno ni las ventas de Empresa A
      expect(cajaServiceB.turnoActivoLocal, isNull);
      expect(cajaServiceB.ventasOfflinePendientes.isEmpty, isTrue);

      final pendientesB = await storage.listarVentasOfflinePendientes(empresaId: testEmpresaIdB, usuarioId: usuarioB, dispositivoId: dispositivoCajaPrueba);
      expect(pendientesB.isEmpty, isTrue);

      final pendientesA = await storage.listarVentasOfflinePendientes(empresaId: testEmpresaId, usuarioId: testUsuarioId, dispositivoId: dispositivoCajaPrueba);
      expect(pendientesA.length, 1);
    });

    test('CU06 / CU07 Adverso: Fallo de SQLite o falta de empresaId al habilitar turno no deja turno en memoria ni permite cobros', () async {
      // 1. Caso A: Falta de empresaId en la sesión
      final sessionSinEmpresa = SessionManager();
      await sessionSinEmpresa.guardar(
        token: 'token-sin-empresa',
        usuario: ClientePerfilModel(
          id: testUsuarioId,
          usuarioId: testUsuarioId,
          empresaId: '', // Vacío
          nombres: 'Cajero',
          apellidos: 'SinEmpresa',
          nombreCompleto: 'Cajero Sin Empresa',
          correoElectronico: 'sinempresa@test.com',
          rol: 'CAJERO',
          estado: 'ACTIVO',
          preferencias: {},
          creadoEn: DateTime.now(),
        ),
      );

      final cajaServiceSinEmpresa = cajaDePrueba(sesiones: sessionSinEmpresa, storage: storage);
      expect(
        () => cajaServiceSinEmpresa.habilitarTurno(TurnoCrearModel(
          cajaId: 'CAJA-ERR-01',
          dispositivoId: dispositivoCajaPrueba,
          sucursalId: testSucursalId,
          cupos: [CupoItemModel(varianteId: testVarianteId, cantidad: 5)],
        )),
        throwsStateError,
      );
      expect(cajaServiceSinEmpresa.turnoActivoLocal, isNull);
      expect(
        () => cajaServiceSinEmpresa.registrarVentaFisicaOffline(
          lineas: [VentaOfflineLineaModel(varianteId: testVarianteId, cantidad: 1, precioAutorizadoBob: 50.0)],
          totalBob: 50.0,
          efectivoRecibidoBob: 50.0,
          cambioEntregadoBob: 0.0,
        ),
        throwsStateError,
      );

      // 2. Caso B: Fallo en SQLite al guardar turno (con sesión de empresa válida)
      await sessionManager.guardar(
        token: 'token-cajero-durable-test',
        usuario: ClientePerfilModel(
          id: testUsuarioId,
          usuarioId: testUsuarioId,
          empresaId: testEmpresaId,
          nombres: 'Cajero',
          apellidos: 'Durable',
          nombreCompleto: 'Cajero Durable',
          correoElectronico: 'cajero.durable@fashionstore.test',
          rol: 'CAJERO',
          estado: 'ACTIVO',
          preferencias: {},
          creadoEn: DateTime.now(),
        ),
      );
      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/cajas/turnos') && request.method == 'POST') {
          return http.Response(
            jsonEncode({
              'turno_id': 'error-turno-id',
              'habilitacion_id': 'error-turno-id',
              'caja_codigo': 'CAJA-FAIL-01',
              'dispositivo_id': dispositivoCajaPrueba,
              'sucursal_id': testSucursalId,
              'cajero_id': testUsuarioId,
              'estado': 'ABIERTO',
              'inicio_en': DateTime.now().toUtc().toIso8601String(),
              'vence_en': DateTime.now().toUtc().add(const Duration(hours: 8)).toIso8601String(),
              'version_precios': 'v-precios-1',
              'revision': 1,
              'cupos': [
                {
                  'variante_id': testVarianteId,
                  'sku': 'SKU-ERR',
                  'otorgado': 5,
                  'consumido': 0,
                  'liberado': 0,
                  'precio_autorizado_bob': '100.00',
                }
              ],
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final failingStorage = FailingStorageMock(failGuardarTurno: true, dbName: 'fail_guardar.db');
      final api = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaServiceFailSqlite = cajaDePrueba(api: api, sesiones: sessionManager, storage: failingStorage);

      expect(
        () => cajaServiceFailSqlite.habilitarTurno(TurnoCrearModel(
          cajaId: 'CAJA-FAIL-01',
          dispositivoId: dispositivoCajaPrueba,
          sucursalId: testSucursalId,
          cupos: [CupoItemModel(varianteId: testVarianteId, cantidad: 5)],
        )),
        throwsA(isA<Exception>().having((e) => e.toString(), 'mensaje', contains('Fallo de I/O simulado en SQLite'))),
      );

      // El turno NO debe quedar en memoria
      expect(cajaServiceFailSqlite.turnoActivoLocal, isNull);
      // No se pueden cobrar ventas
      expect(
        () => cajaServiceFailSqlite.registrarVentaFisicaOffline(
          lineas: [VentaOfflineLineaModel(varianteId: testVarianteId, cantidad: 1, precioAutorizadoBob: 100.0)],
          totalBob: 100.0,
          efectivoRecibidoBob: 100.0,
          cambioEntregadoBob: 0.0,
        ),
        throwsStateError,
      );
      await failingStorage.close();
    });

    test('CU06 / CU07 Adverso: Turno revocado remotamente seguido de desconexión: se desactiva la autorizacion sin borrar historial; reconectar offline no resucita el turno', () async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      // 1. Habilitar turno online persistido en SQLite
      final mockHttpTurnoActivo = MockClient((request) async {
        if (request.url.path.contains('/cajas/turnos') && request.method == 'POST') {
          return http.Response(
            jsonEncode({
              'turno_id': testTurnoId,
              'habilitacion_id': testTurnoId,
              'caja_codigo': 'CAJA-REVOCAR-01',
              'dispositivo_id': dispositivoCajaPrueba,
              'sucursal_id': testSucursalId,
              'cajero_id': testUsuarioId,
              'estado': 'ABIERTO',
              'inicio_en': ahora.toIso8601String(),
              'vence_en': vence.toIso8601String(),
              'version_precios': 'v-precios-1',
              'revision': 1,
              'cupos': [
                {
                  'variante_id': testVarianteId,
                  'sku': 'SKU-REV',
                  'otorgado': 5,
                  'consumido': 0,
                  'liberado': 0,
                  'precio_autorizado_bob': '100.00',
                }
              ],
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api1 = apiCajaPrueba(httpClient: mockHttpTurnoActivo, sesiones: sessionManager);
      final cajaService = cajaDePrueba(api: api1, sesiones: sessionManager, storage: storage);

      await cajaService.habilitarTurno(TurnoCrearModel(
        cajaId: 'CAJA-REVOCAR-01',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cupos: [CupoItemModel(varianteId: testVarianteId, cantidad: 5)],
      ));

      expect(cajaService.turnoActivoLocal, isNotNull);
      final enDbAntes = await storage.obtenerTurnoActivoLocal(empresaId: testEmpresaId, usuarioId: testUsuarioId, dispositivoId: dispositivoCajaPrueba);
      expect(enDbAntes, isNotNull);
      expect(enDbAntes!.turnoId, testTurnoId);

      // 2. El servidor responde null en /cajas/turnos/activo (el turno fue cerrado/revocado remotamente)
      final mockHttpRevocado = MockClient((request) async {
        if (request.url.path.contains('/cajas/turnos/activo')) {
          return http.Response('null', 200, headers: {'content-type': 'application/json'});
        }
        return http.Response('Not found', 404);
      });

      final apiRevocado = apiCajaPrueba(httpClient: mockHttpRevocado, sesiones: sessionManager);
      final cajaServiceConRevocado = cajaDePrueba(api: apiRevocado, sesiones: sessionManager, storage: storage);
      await fijarTurnoPrueba(cajaServiceConRevocado, cajaService.turnoActivoLocal!);

      // Consultar online: detecta que el servidor lo cerró remotamente
      final turnoConsultado = await cajaServiceConRevocado.consultarTurnoActivo(dispositivoId: dispositivoCajaPrueba);
      expect(turnoConsultado, isNull);
      expect(cajaServiceConRevocado.turnoActivoLocal, isNull);

      // Comprobar que SQLite quedó limpio y no conserva el turno
      final enDbDespues = await storage.obtenerTurnoActivoLocal(empresaId: testEmpresaId, usuarioId: testUsuarioId, dispositivoId: dispositivoCajaPrueba);
      expect(enDbDespues, isNull);

      // 3. Simular desconexión inmediata posterior (falla de red)
      final mockHttpOffline = MockClient((request) async {
        throw http.ClientException('Sin conexión a internet');
      });

      final apiOffline = apiCajaPrueba(httpClient: mockHttpOffline, sesiones: sessionManager);
      final cajaServiceOffline = cajaDePrueba(api: apiOffline, sesiones: sessionManager, storage: storage);

      final turnoOffline = await cajaServiceOffline.consultarTurnoActivo(dispositivoId: dispositivoCajaPrueba);
      expect(turnoOffline, isNull);
      expect(cajaServiceOffline.turnoActivoLocal, isNull);

      // Restauración explícita desde storage tampoco debe resucitar el turno
      await cajaServiceOffline.restaurarDesdeStorage(empresaId: testEmpresaId);
      expect(cajaServiceOffline.turnoActivoLocal, isNull);
    });

    test('CU07 Adverso: Error al leer estadísticas locales propaga error e impide cierre con conteos 0,0', () async {
      final failingStorage = FailingStorageMock(failEstadisticas: true, dbName: 'fail_stats.db');
      final cajaService = cajaDePrueba(sesiones: sessionManager, storage: failingStorage);

      // Verificar que storage lanza la excepción y NO devuelve 0,0 silenciosamente
      expect(
        () => failingStorage.obtenerEstadisticasVentasCaja(testTurnoId),
        throwsA(isA<Exception>().having((e) => e.toString(), 'mensaje', contains('Error simulado al consultar estadísticas'))),
      );

      // Verificar que el servicio propaga la excepción
      expect(
        () => cajaService.obtenerEstadisticasVentasTurno(testTurnoId),
        throwsA(isA<Exception>().having((e) => e.toString(), 'mensaje', contains('Error simulado al consultar estadísticas'))),
      );

      await failingStorage.close();
    });

    test('CU07: Ciclo completo de cupos: cobro offline (1 de 3) -> sync con servidor no duplica consumo -> reinicio simulado -> segundo cobro descuenta a 1', () async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      // 1. Turno con 1 prenda y cupo otorgado = 3
      final turno = TurnoHabilitacionModel(
        empresaId: testEmpresaId,
        horaCentralEn: DateTime.now().toUtc().toIso8601String(),
        turnoId: testTurnoId,
        habilitacionId: testTurnoId,
        cajaCodigo: 'CAJA-CUPO-01',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cajeroId: testUsuarioId,
        estado: 'ABIERTO',
        inicioEn: ahora.toIso8601String(),
        venceEn: vence.toIso8601String(),
        versionPrecios: 'v-precios-1',
        revision: 1,
        cupos: [
          CupoRespuestaModel(
            varianteId: testVarianteId,
            sku: 'SKU-VESTIDO-FIESTA',
            productoNombre: 'Vestido de Fiesta',
            otorgado: 3,
            consumido: 0,
            precioAutorizadoBob: 150.0,
          )
        ],
      );

      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/ventas') && request.method == 'POST') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'resultado': 'REGISTRADA_CENTRAL',
              'operacion_id': body['operacion_id'],
              'venta_id': '88888888-8888-4888-8888-888888888888',
              'numero': 'VNT-SYNC-01',
              'total_bob': 150.0,
              'comprobante_id': '99999999-9999-4999-8999-999999999999',
              'recibida_central_en': ahora.toIso8601String(),
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaService = cajaDePrueba(api: api, sesiones: sessionManager, storage: storage);

      await fijarTurnoPrueba(cajaService, turno, empresaId: testEmpresaId, usuarioId: testUsuarioId);

      // Estado inicial: cupo otorgado 3, consumido 0, remanente disponible 3
      expect(cajaService.turnoActivoLocal!.cupos.first.disponible, 3);
      expect((await storage.obtenerCuposTurnoLocal(testTurnoId)).first.disponible, 3);

      // 2. Cobro offline de 1 unidad de cupo 3
      final comp1 = await cajaService.registrarVentaFisicaOffline(
        lineas: [
          VentaOfflineLineaModel(
            varianteId: testVarianteId,
            cantidad: 1,
            precioAutorizadoBob: 150.0,
          )
        ],
        totalBob: 150.0,
        efectivoRecibidoBob: 150.0,
        cambioEntregadoBob: 0.0,
      );

      expect(comp1.comprobanteId, isNotEmpty);
      // Cupo remanente 2 en memoria y SQLite
      expect(cajaService.turnoActivoLocal!.cupos.first.consumido, 1);
      expect(cajaService.turnoActivoLocal!.cupos.first.disponible, 2);
      final cuposSqlite1 = await storage.obtenerCuposTurnoLocal(testTurnoId);
      expect(cuposSqlite1.first.consumido, 1);
      expect(cuposSqlite1.first.disponible, 2);
      expect(cajaService.ventasOfflinePendientes.length, 1);

      // 3. Sincronización con servidor
      final sinc = await cajaService.sincronizarVentasPendientes(testTurnoId);
      expect(sinc, 1);
      expect(cajaService.ventasOfflinePendientes.isEmpty, isTrue);

      // EL CUPO REMANENTE EN MEMORIA SIGUE SIENDO EXACTAMENTE 2 (NO SE DUPLICA EL CONSUMO A 2 NI EL REMANENTE A 1)
      expect(cajaService.turnoActivoLocal!.cupos.first.consumido, 1);
      expect(cajaService.turnoActivoLocal!.cupos.first.disponible, 2);
      final cuposSqlitePostSync = await storage.obtenerCuposTurnoLocal(testTurnoId);
      expect(cuposSqlitePostSync.first.consumido, 1);
      expect(cuposSqlitePostSync.first.disponible, 2);

      // 4. Reinicio simulado de la aplicación
      final cajaServiceReinicio = cajaDePrueba(api: api, sesiones: sessionManager, storage: storage);
      expect(cajaServiceReinicio.turnoActivoLocal, isNull);

      await cajaServiceReinicio.restaurarDesdeStorage(
        empresaId: testEmpresaId,
        dispositivoId: dispositivoCajaPrueba,
      );

      // Cupo remanente sigue siendo 2 tras reinicio
      expect(cajaServiceReinicio.turnoActivoLocal, isNotNull);
      expect(cajaServiceReinicio.turnoActivoLocal!.cupos.first.consumido, 1);
      expect(cajaServiceReinicio.turnoActivoLocal!.cupos.first.disponible, 2);

      // 5. Segundo cobro descuenta a 1
      final comp2 = await cajaServiceReinicio.registrarVentaFisicaOffline(
        lineas: [
          VentaOfflineLineaModel(
            varianteId: testVarianteId,
            cantidad: 1,
            precioAutorizadoBob: 150.0,
          )
        ],
        totalBob: 150.0,
        efectivoRecibidoBob: 200.0,
        cambioEntregadoBob: 50.0,
      );

      expect(comp2.comprobanteId, isNotEmpty);
      expect(cajaServiceReinicio.turnoActivoLocal!.cupos.first.consumido, 2);
      expect(cajaServiceReinicio.turnoActivoLocal!.cupos.first.disponible, 1);
      final cuposSqlite2 = await storage.obtenerCuposTurnoLocal(testTurnoId);
      expect(cuposSqlite2.first.consumido, 2);
      expect(cuposSqlite2.first.disponible, 1);
      expect(cajaServiceReinicio.ventasOfflinePendientes.length, 1);
    });
  });
}

class FailingStorageMock extends LocalDatabaseService {
  final bool failGuardarTurno;
  final bool failEstadisticas;

  FailingStorageMock({
    this.failGuardarTurno = false,
    this.failEstadisticas = false,
    super.dbName,
  });

  @override
  Future<void> guardarTurnoActivoLocal(
    TurnoHabilitacionModel turno, {
    required String empresaId,
    required String usuarioId,
  }) async {
    if (failGuardarTurno) {
      throw Exception('Fallo de I/O simulado en SQLite al guardar turno');
    }
    return super.guardarTurnoActivoLocal(turno, empresaId: empresaId, usuarioId: usuarioId);
  }

  @override
  Future<Map<String, int>> obtenerEstadisticasVentasCaja(String turnoId, {String? empresaId, String? usuarioId, String? dispositivoId}) async {
    if (failEstadisticas) {
      throw Exception('Error simulado al consultar estadísticas en SQLite');
    }
    return super.obtenerEstadisticasVentasCaja(turnoId, empresaId: empresaId, usuarioId: usuarioId, dispositivoId: dispositivoId);
  }
}
