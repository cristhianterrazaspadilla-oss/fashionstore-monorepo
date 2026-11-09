import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/core/storage/local_database_service.dart';
import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/features/organizacion/services/sucursal_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/caja/caja_offline_screen.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/caja_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/caja_service.dart';

import '../caja_fixture_aislada.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('Widget Tests: CajaOfflineScreen (CU06 / CU07)', () {
    const testEmpresaId = '11111111-1111-4111-8111-111111111111';
    const testUsuarioId = '22222222-2222-4222-8222-222222222222';
    const testSucursalId = '33333333-3333-4333-8333-333333333333';
    const testVarianteId = '44444444-4444-4444-8444-444444444444';
    const testTurnoId = '55555555-5555-4555-8555-555555555555';

    late SessionManager sessionManager;
    late LocalDatabaseService storage;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await prepararCajaPrueba();
      sessionManager = SessionManager();
      await sessionManager.guardar(
        token: 'token-cajero-widget',
        usuario: ClientePerfilModel(
          id: testUsuarioId,
          usuarioId: testUsuarioId,
          empresaId: testEmpresaId,
          nombres: 'Cajero',
          apellidos: 'Widget',
          nombreCompleto: 'Cajero Widget',
          correoElectronico: 'cajero@widget.test',
          rol: 'CAJERO',
          estado: 'ACTIVO',
          preferencias: {},
          creadoEn: DateTime.now(),
        ),
      );

      storage = LocalDatabaseService(dbName: inMemoryDatabasePath);
      await storage.limpiarTodo();
    });

    tearDown(() async {
      await storage.limpiarTodo();
      await storage.close();
    });

    testWidgets('Muestra formulario de habilitación cuando no hay turno activo',
        (tester) async {
      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/sucursales')) {
          return http.Response(
            jsonEncode([
              {
                'id': testSucursalId,
                'ciudad_id': 'cbba',
                'nombre': 'Sucursal Central Cochabamba',
                'direccion': 'Av. Heroínas 123',
                'activa': true,
              }
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.contains('/cajas/turnos/activo')) {
          return http.Response('null', 200,
              headers: {'content-type': 'application/json'});
        }
        return http.Response('Not found', 404);
      });

      final api = ApiClient(httpClient: mockHttp, sesiones: sessionManager);
      final cajaSrv =
          CajaService(api: api, sesiones: sessionManager, storage: storage);
      final sucursalSrv = SucursalService(api: api);

      await tester.pumpWidget(
        MaterialApp(
          home: CajaOfflineScreen(
            servicioCaja: cajaSrv,
            servicioSucursal: sucursalSrv,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Habilitar Turno de Caja'), findsOneWidget);
      expect(find.text('Habilitar Turno Online'), findsOneWidget);
      expect(find.text('Código de Caja / Dispositivo'), findsOneWidget);
    });

    testWidgets(
        'Con turno activo: permite cobrar en efectivo, emitir comprobante local y ver banner de pendientes',
        (tester) async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final mockHttp = MockClient((request) async {
        if (request.url.path.endsWith('/cajas/turnos/activo')) {
          return http.Response(jsonEncode(turnoCajaPrueba(testTurnoId)), 200,
              headers: {'content-type': 'application/json'});
        }
        return http.Response('[]', 200,
            headers: {'content-type': 'application/json'});
      });
      final api = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final sucursalSrv = SucursalService(api: api);

      final cajaSrv =
          CajaService(api: api, sesiones: sessionManager, storage: storage);
      final turno = TurnoHabilitacionModel(
        empresaId: testEmpresaId,
        horaCentralEn: DateTime.now().toUtc().toIso8601String(),
        turnoId: testTurnoId,
        habilitacionId: testTurnoId,
        cajaCodigo: 'CAJA-MOVIL-01',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cajeroId: testUsuarioId,
        estado: 'ABIERTO',
        inicioEn: ahora.toIso8601String(),
        venceEn: vence.toIso8601String(),
        versionPrecios: 'precios-v1',
        revision: 1,
        cupos: [
          CupoRespuestaModel(
            varianteId: testVarianteId,
            sku: 'SKU-JEAN-AZUL',
            productoNombre: 'Jean Azul Clásico',
            otorgado: 5,
            consumido: 0,
            precioAutorizadoBob: 180.0,
          )
        ],
      );

      await fijarTurnoPrueba(cajaSrv, turno,
          empresaId: testEmpresaId, usuarioId: testUsuarioId);

      await tester.pumpWidget(
        MaterialApp(
          home: CajaOfflineScreen(
            servicioCaja: cajaSrv,
            servicioSucursal: sucursalSrv,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verificar que muestra la tarjeta del turno activo
      expect(find.text('CAJA-MOVIL-01'), findsOneWidget);
      expect(find.text('ABIERTO'), findsOneWidget);
      expect(find.text('Cobrar Venta en Efectivo (Offline)'), findsOneWidget);
      expect(
          find.text('Cobrar en Efectivo y Emitir Comprobante'), findsOneWidget);
      final selectorPrenda = find.byKey(
        const ValueKey('cupo_venta_${testTurnoId}_$testVarianteId'),
      );
      await tester.ensureVisible(selectorPrenda);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      // Ingresar efectivo recibido
      await tester.enterText(find.byType(TextField).first, '200');
      await tester.pumpAndSettle();

      // Presionar cobrar
      await tester.tap(find.text('Cobrar en Efectivo y Emitir Comprobante'));
      await tester.pumpAndSettle();

      // Debe abrir diálogo con el comprobante local emitido
      expect(find.text('Comprobante Emitido'), findsOneWidget);
      expect(find.textContaining('COMP-LOC-'), findsWidgets);
      expect(find.text('Total Pagado: Bs 180.00'), findsOneWidget);
      expect(find.text('Cambio Entregado: Bs 20.00'), findsOneWidget);

      // Cerrar modal de comprobante
      await tester.tap(find.text('Aceptar'));
      await tester.pumpAndSettle();

      // La UI debe mostrar el banner de 1 venta pendiente
      expect(find.textContaining('1 venta(s) pendientes de sincronizar'),
          findsOneWidget);
      expect(find.text('Sincronizar'), findsOneWidget);
      expect(find.text('Disp: 4 / 5 (Bs 180.00)'), findsOneWidget);
    });

    testWidgets(
        'Cierre de turno con arqueo devuelve cupos y limpia el turno activo',
        (tester) async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final mockHttp = MockClient((request) async {
        if (request.url.path.endsWith('/cajas/turnos/activo')) {
          return http.Response(jsonEncode(turnoCajaPrueba(testTurnoId)), 200,
              headers: {'content-type': 'application/json'});
        }
        if (request.url.path.contains('/cerrar') && request.method == 'POST') {
          return http.Response(
            jsonEncode({
              'turno_id': testTurnoId,
              'estado': 'CERRADO',
              'cerrado_en': ahora.toIso8601String(),
              'revision': 2,
              'cupos_devueltos': [
                {
                  'variante_id': testVarianteId,
                  'otorgado': 5,
                  'consumido': 0,
                  'devuelto': 5,
                }
              ],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('[]', 200,
            headers: {'content-type': 'application/json'});
      });

      final api = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaSrv =
          CajaService(api: api, sesiones: sessionManager, storage: storage);
      final sucursalSrv = SucursalService(api: api);

      final turno = TurnoHabilitacionModel(
        empresaId: testEmpresaId,
        horaCentralEn: DateTime.now().toUtc().toIso8601String(),
        turnoId: testTurnoId,
        habilitacionId: testTurnoId,
        cajaCodigo: 'CAJA-MOVIL-01',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cajeroId: testUsuarioId,
        estado: 'ABIERTO',
        inicioEn: ahora.toIso8601String(),
        venceEn: vence.toIso8601String(),
        versionPrecios: 'precios-v1',
        revision: 1,
        cupos: [
          CupoRespuestaModel(
            varianteId: testVarianteId,
            sku: 'SKU-JEAN-AZUL',
            productoNombre: 'Jean Azul Clásico',
            otorgado: 5,
            consumido: 0,
            precioAutorizadoBob: 180.0,
          )
        ],
      );

      await fijarTurnoPrueba(cajaSrv, turno,
          empresaId: testEmpresaId, usuarioId: testUsuarioId);

      await tester.pumpWidget(
        MaterialApp(
          home: CajaOfflineScreen(
            servicioCaja: cajaSrv,
            servicioSucursal: sucursalSrv,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Cierre de Turno y Arqueo'), findsWidgets);

      // Ingresar arqueo
      final arqueoFinder = find.widgetWithText(
          TextField, 'Arqueo de Efectivo Final en Caja (Bs)');
      await tester.ensureVisible(arqueoFinder);
      await tester.enterText(arqueoFinder, '500');
      await tester.pumpAndSettle();

      // Tap cerrar turno
      final btnCerrar = find.text('Cerrar Turno y Devolver Cupos');
      await tester.ensureVisible(btnCerrar);
      await tester.tap(btnCerrar);
      await tester.pumpAndSettle();

      // Diálogo de confirmación
      expect(find.text('Cierre de Turno y Arqueo'), findsWidgets);
      expect(find.text('Confirmar Cierre'), findsOneWidget);

      await tester.tap(find.text('Confirmar Cierre'));
      await tester.pumpAndSettle();

      // Debe volver a la vista sin turno
      expect(find.text('Habilitar Turno de Caja'), findsOneWidget);
      expect(cajaSrv.turnoActivoLocal, isNull);
    });

    testWidgets(
        'CU07: Error al leer estadísticas locales en pantalla muestra advertencia y bloquea el botón de cierre',
        (tester) async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final failingStorage = FailingStatsStorage();
      final mockHttp = MockClient((request) async {
        if (request.url.path.endsWith('/cajas/turnos/activo')) {
          return http.Response(jsonEncode(turnoCajaPrueba(testTurnoId)), 200,
              headers: {'content-type': 'application/json'});
        }
        return http.Response('[]', 200,
            headers: {'content-type': 'application/json'});
      });

      final api = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaSrv = CajaService(
          api: api, sesiones: sessionManager, storage: failingStorage);
      final sucursalSrv = SucursalService(api: api);

      final turno = TurnoHabilitacionModel(
        empresaId: testEmpresaId,
        horaCentralEn: DateTime.now().toUtc().toIso8601String(),
        turnoId: testTurnoId,
        habilitacionId: testTurnoId,
        cajaCodigo: 'CAJA-MOVIL-01',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cajeroId: testUsuarioId,
        estado: 'ABIERTO',
        inicioEn: ahora.toIso8601String(),
        venceEn: vence.toIso8601String(),
        versionPrecios: 'precios-v1',
        revision: 1,
        cupos: [
          CupoRespuestaModel(
            varianteId: testVarianteId,
            sku: 'SKU-JEAN-AZUL',
            productoNombre: 'Jean Azul Clásico',
            otorgado: 5,
            consumido: 0,
            precioAutorizadoBob: 180.0,
          )
        ],
      );

      await fijarTurnoPrueba(cajaSrv, turno);

      await tester.pumpWidget(
        MaterialApp(
          home: CajaOfflineScreen(
            servicioCaja: cajaSrv,
            servicioSucursal: sucursalSrv,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verificar que muestra advertencia
      expect(find.textContaining('Cierre de turno bloqueado por seguridad'),
          findsOneWidget);

      // Verificar que el botón de cierre está deshabilitado (onPressed == null)
      final btnFinder =
          find.widgetWithText(OutlinedButton, 'Cerrar Turno y Devolver Cupos');
      expect(btnFinder, findsOneWidget);
      final OutlinedButton btn = tester.widget(btnFinder);
      expect(btn.onPressed, isNull);
    });
  });
}

class FailingStatsStorage extends LocalDatabaseService {
  FailingStatsStorage() : super(dbName: inMemoryDatabasePath);

  @override
  Future<Map<String, int>> obtenerEstadisticasVentasCaja(String turnoId,
      {String? empresaId, String? usuarioId, String? dispositivoId}) async {
    throw Exception('Error simulado en lectura de SQLite');
  }
}
