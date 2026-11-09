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
import 'package:fashionstore_movil/features/catalogo/services/catalogo_service.dart';
import 'package:fashionstore_movil/features/identidad_empresas/cuenta/cuenta_screen.dart';
import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/features/identidad_empresas/services/suscripcion_service.dart';
import 'package:fashionstore_movil/features/organizacion/services/sucursal_service.dart';
import 'package:fashionstore_movil/features/ventas_pagos/caja/caja_offline_screen.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/caja_service.dart';

import '../caja_fixture_aislada.dart';

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  group('Pruebas Productivas CU06 / CU07: Caja Móvil End-to-End', () {
    const testEmpresaId = '11111111-1111-4111-8111-111111111111';
    const testUsuarioId = '22222222-2222-4222-8222-222222222222';
    const testSucursalId = '33333333-3333-4333-8333-333333333333';
    const testVarianteRealId = '77777777-7777-4777-8777-777777777777';
    const testTurnoId = '88888888-8888-4888-8888-888888888888';

    late SessionManager sessionManager;
    late LocalDatabaseService storage;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await prepararCajaPrueba();
      sessionManager = SessionManager();
      await sessionManager.guardar(
        token: 'jwt-token-cajero-productivo',
        usuario: ClientePerfilModel(
          id: testUsuarioId,
          usuarioId: testUsuarioId,
          empresaId: testEmpresaId,
          nombres: 'Cajero',
          apellidos: 'Productivo',
          nombreCompleto: 'Cajero Productivo',
          correoElectronico: 'cajero.prod@fashionstore.test',
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

    testWidgets(
        'Bloqueo 1 & 5: CuentaScreen abre Caja Móvil con ApiClient autenticado y textos limpios',
        (tester) async {
      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/empresas/mi-plan')) {
          return http.Response(
            jsonEncode({
              'empresa_id': testEmpresaId,
              'plan_codigo': 'pro',
              'plan_nombre': 'Plan Profesional',
              'estado_efectivo': 'ACTIVA',
              'sucursales_activas': 1,
              'limite_sucursales': 3,
              'capacidades': ['caja_movil', 'catalogo_offline'],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.contains('/cajas/turnos/activo')) {
          return http.Response('null', 200,
              headers: {'content-type': 'application/json'});
        }
        if (request.url.path.contains('/sucursales')) {
          return http.Response('[]', 200,
              headers: {'content-type': 'application/json'});
        }
        if (request.url.path.contains('/variantes')) {
          return http.Response('[]', 200,
              headers: {'content-type': 'application/json'});
        }
        return http.Response('Not found', 404);
      });

      final api = ApiClient(httpClient: mockHttp, sesiones: sessionManager);
      final suscripcionSrv = SuscripcionService(api: api);

      await tester.pumpWidget(
        MaterialApp(
          home: CuentaScreen(
            onSesionCerrada: () {},
            servicioSuscripcion: suscripcionSrv,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verificar limpieza de textos técnicos (Bloqueo 5)
      expect(find.text('Caja Móvil'), findsOneWidget);
      expect(find.textContaining('CU06'), findsNothing);
      expect(find.textContaining('CU07'), findsNothing);
      expect(find.textContaining('CU02'), findsNothing);
      expect(find.text('Capacidades habilitadas:'), findsOneWidget);

      // Abrir Módulo de Caja
      await tester.tap(find.text('Abrir Módulo de Caja'));
      await tester.pumpAndSettle();

      // Debe abrir CajaOfflineScreen
      expect(find.text('Habilitar Turno de Caja'), findsOneWidget);
    });

    testWidgets(
        'Bloqueo 2: Habilitar turno requiere variantes reales y no acepta ficticias ni vacías',
        (tester) async {
      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/sucursales')) {
          return http.Response(
            jsonEncode([
              {
                'id': testSucursalId,
                'ciudad_id': 'cbba',
                'nombre': 'Sucursal Central',
                'direccion': 'Av. Heroínas 100',
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
        if (request.url.path.contains('/inventario/existencias')) {
          return http.Response(
            jsonEncode([
              {
                'variante_id': testVarianteRealId,
                'producto_id': 'prod-vestido-01',
                'sku': 'SKU-VES-ROJO-M',
                'producto_nombre': 'Vestido Fiesta Rojo',
                'disponible': 5,
                'precio': 220.0,
              }
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.contains('/variantes')) {
          return http.Response(
            jsonEncode([
              {
                'id': testVarianteRealId,
                'producto_id': 'prod-vestido-01',
                'sku': 'SKU-VES-ROJO-M',
                'talla_id': 'talla-m',
                'color_id': 'color-rojo',
                'precio': 220.0,
                'activa': true,
              }
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.contains('/productos')) {
          return http.Response(
            jsonEncode([
              {
                'id': 'prod-vestido-01',
                'nombre': 'Vestido Fiesta Rojo',
                'codigo': 'VEST-01',
                'precio_bob': '220.00',
                'activo': true,
              }
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = ApiClient(httpClient: mockHttp, sesiones: sessionManager);
      final cajaSrv =
          CajaService(api: api, sesiones: sessionManager, storage: storage);
      final sucursalSrv = SucursalService(api: api);
      final catalogoSrv = CatalogoService(api: api, storage: storage);

      await tester.pumpWidget(
        MaterialApp(
          home: CajaOfflineScreen(
            servicioCaja: cajaSrv,
            servicioSucursal: sucursalSrv,
            servicioCatalogo: catalogoSrv,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Debe mostrar mensaje de error si no hay prendas agregadas al turno
      expect(
          find.text(
              'Debes agregar al menos una prenda con cupo para habilitar el turno.'),
          findsOneWidget);

      // El botón Habilitar Turno Online debe estar deshabilitado cuando _cuposSolicitados está vacío
      final btnHabilitar = tester.widget<ElevatedButton>(
          find.widgetWithText(ElevatedButton, 'Habilitar Turno Online'));
      expect(btnHabilitar.onPressed, isNull);

      // Ahora agregamos la variante real mediante el botón 'Agregar prenda'
      expect(find.textContaining('Vestido Fiesta Rojo'), findsOneWidget);
      await tester.tap(find.text('Agregar prenda'));
      await tester.pumpAndSettle();

      // La variante real agregada ahora debe estar visible en la lista
      expect(find.text('Prendas agregadas al turno:'), findsOneWidget);
      expect(find.text('Vestido Fiesta Rojo (SKU-VES-ROJO-M)'), findsOneWidget);

      // Y el botón de habilitar debe estar activo
      final btnHabilitarActivo = tester.widget<ElevatedButton>(
          find.widgetWithText(ElevatedButton, 'Habilitar Turno Online'));
      expect(btnHabilitarActivo.onPressed, isNotNull);
    });

    testWidgets(
        'Recorrido productivo E2E: Apertura con variante real -> Cobro sin red -> Reinicio -> Reconexión/Sync preservando operacion_id -> Cierre con conciliación',
        (tester) async {
      String? operacionIdCapturadaEnSync;
      Map<String, dynamic>? cuerpoCierreCapturado;
      bool redDisponible = true;
      int stockLibreEnSucursal = 1;

      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final mockHttp = MockClient((request) async {
        if (!redDisponible) {
          throw http.ClientException('Sin conexión a internet');
        }

        // 1. Sucursales
        if (request.url.path.contains('/sucursales')) {
          return http.Response(
            jsonEncode([
              {
                'id': testSucursalId,
                'ciudad_id': 'cbba',
                'nombre': 'Sucursal Central',
                'direccion': 'Av. Heroínas 100',
                'activa': true,
              }
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }

        // 2. Turno Activo
        if (request.url.path.endsWith('/cajas/turnos/activo')) {
          // Antes de abrir no hay turno; tras abrir se conserva hasta el cierre.
          return http.Response(jsonEncode(turnoCajaPrueba(testTurnoId)), 200,
              headers: {'content-type': 'application/json'});
        }

        // 3. Variantes y Productos
        if (request.url.path.contains('/inventario/existencias')) {
          return http.Response(
            jsonEncode([
              {
                'variante_id': testVarianteRealId,
                'producto_id': 'prod-vestido-01',
                'sku': 'SKU-VES-ROJO-M',
                'producto_nombre': 'Vestido Fiesta Rojo',
                'disponible': stockLibreEnSucursal,
                'precio': 220.0,
              }
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.endsWith('/variantes')) {
          return http.Response(
            jsonEncode([
              {
                'id': testVarianteRealId,
                'producto_id': 'prod-vestido-01',
                'sku': 'SKU-VES-ROJO-M',
                'talla_id': 'talla-m',
                'color_id': 'color-rojo',
                'precio': 220.0,
                'activa': true,
              }
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.endsWith('/productos')) {
          return http.Response(
            jsonEncode([
              {
                'id': 'prod-vestido-01',
                'nombre': 'Vestido Fiesta Rojo',
                'codigo': 'VEST-01',
                'precio_bob': '220.00',
                'activo': true,
              }
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }

        // 4. Habilitar Turno Online (POST /cajas/turnos)
        if (request.url.path.endsWith('/cajas/turnos') &&
            request.method == 'POST') {
          expect(request.headers['Idempotency-Key'], isNotNull);
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['sucursal_id'], testSucursalId);
          final cupos = body['cupos'] as List;
          expect(cupos.length, 1);
          // Garantizar que la variante enviada es la real, NUNCA la ficticia 00000000-0000-4000-8000-000000000001
          expect(cupos.first['variante_id'], testVarianteRealId);
          expect(cupos.first['variante_id'],
              isNot('00000000-0000-4000-8000-000000000001'));
          expect(cupos.first['cantidad'], 1);

          stockLibreEnSucursal = 0;

          return http.Response(
            jsonEncode({
              'turno_id': testTurnoId,
              'habilitacion_id': testTurnoId,
              'caja_codigo': 'CAJA-MOVIL-01',
              'dispositivo_id': dispositivoCajaPrueba,
              'sucursal_id': testSucursalId,
              'cajero_id': testUsuarioId,
              'estado': 'ABIERTO',
              'inicio_en': ahora.toIso8601String(),
              'vence_en': vence.toIso8601String(),
              'version_precios': 'precios-v1',
              'revision': 1,
              'cupos': [
                {
                  'variante_id': testVarianteRealId,
                  'sku': 'SKU-VES-ROJO-M',
                  'producto_nombre': 'Vestido Fiesta Rojo',
                  'otorgado': 1,
                  'consumido': 0,
                  'precio_autorizado_bob': 220.0,
                }
              ]
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }

        // 5. Sincronizar Venta Offline (POST /cajas/turnos/{turno_id}/ventas)
        if (request.url.path.contains('/ventas') && request.method == 'POST') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          operacionIdCapturadaEnSync = body['operacion_id'] as String;
          return http.Response(
            jsonEncode({
              'resultado': 'REGISTRADA_CENTRAL',
              'operacion_id': operacionIdCapturadaEnSync,
              'venta_id': '99999999-9999-4999-8999-999999999999',
              'numero': 'V-001',
              'total_bob': 220.0,
              'comprobante_id': 'comp-uuid-central',
              'recibida_central_en': DateTime.now().toUtc().toIso8601String(),
              'cupos_restantes': [],
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }

        // 6. Cerrar Turno (POST /cajas/turnos/{turno_id}/cerrar)
        if (request.url.path.contains('/cerrar') && request.method == 'POST') {
          cuerpoCierreCapturado =
              jsonDecode(request.body) as Map<String, dynamic>;
          stockLibreEnSucursal = 0;
          return http.Response(
            jsonEncode({
              'turno_id': testTurnoId,
              'estado': 'CERRADO',
              'cerrado_en': DateTime.now().toUtc().toIso8601String(),
              'revision': 2,
              'cupos_devueltos': [
                {
                  'variante_id': testVarianteRealId,
                  'otorgado': 1,
                  'consumido': 1,
                  'devuelto': 0,
                }
              ],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }

        return http.Response('Not found', 404);
      });

      // Simula la revalidación online sin sustituir CajaService ni SQLite.
      final api = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaSrv =
          CajaService(api: api, sesiones: sessionManager, storage: storage);
      final sucursalSrv = SucursalService(api: api);
      final catalogoSrv = CatalogoService(api: api, storage: storage);

      // --- PASO 1: Apertura de Turno con Variante Real ---
      await tester.pumpWidget(
        MaterialApp(
          home: CajaOfflineScreen(
            servicioCaja: cajaSrv,
            servicioSucursal: sucursalSrv,
            servicioCatalogo: catalogoSrv,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Habilitar Turno de Caja'), findsOneWidget);

      // Agregar variante real con cupo
      await tester.tap(find.text('Agregar prenda'));
      await tester.pumpAndSettle();

      // Habilitar turno online
      final btnHabilitar = find.text('Habilitar Turno Online');
      await tester.ensureVisible(btnHabilitar);
      await tester.tap(btnHabilitar);
      await tester.pumpAndSettle();

      // Debe mostrar la vista de Turno Activo
      expect(find.text('CAJA-MOVIL-01'), findsOneWidget);
      expect(find.text('ABIERTO'), findsOneWidget);
      expect(find.text('Disp: 1 / 1 (Bs 220.00)'), findsOneWidget);

      // Verificar que el turno fue guardado de forma durable en SQLite
      final turnoEnSqlite = await storage.obtenerTurnoActivoLocal(
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: dispositivoCajaPrueba,
      );
      expect(turnoEnSqlite, isNotNull);
      expect(turnoEnSqlite!.turnoId, testTurnoId);

      // --- PASO 2: Cobro Físico sin Red (Offline) ---
      // Desconectamos la red
      redDisponible = false;

      // Ingresar efectivo recibido
      final efectivoFinder =
          find.widgetWithText(TextField, 'Efectivo Recibido (Bs)');
      await tester.ensureVisible(efectivoFinder);
      await tester.enterText(efectivoFinder, '250');
      await tester.pumpAndSettle();

      // Cobrar en efectivo sin conexión
      final btnCobrar = find.text('Cobrar en Efectivo y Emitir Comprobante');
      await tester.ensureVisible(btnCobrar);
      await tester.tap(btnCobrar);
      await tester.pumpAndSettle();

      // Se emite comprobante local inmediato
      expect(find.text('Comprobante Emitido'), findsOneWidget);
      expect(find.text('Total Pagado: Bs 220.00'), findsOneWidget);
      expect(find.text('Cambio Entregado: Bs 30.00'), findsOneWidget);
      expect(
          find.text(
              'Venta registrada localmente en este dispositivo. Lista para sincronizar al conectarse al servidor.'),
          findsOneWidget);

      // Aceptar modal
      await tester.tap(find.text('Aceptar'));
      await tester.pumpAndSettle();

      // La unica unidad asignada se consume sin red.
      expect(find.text('Disp: 0 / 1 (Bs 220.00)'), findsOneWidget);
      expect(find.text('1 venta(s) pendientes de sincronizar'), findsOneWidget);

      // Verificar persistencia durable en SQLite de la venta offline antes de sincronizar
      final ventasPendientesSqlite =
          await storage.listarVentasOfflinePendientes(
        empresaId: testEmpresaId,
        turnoId: testTurnoId,
        usuarioId: testUsuarioId,
        dispositivoId: dispositivoCajaPrueba,
      );
      expect(ventasPendientesSqlite.length, 1);
      final ventaGuardadaDurable = ventasPendientesSqlite.first;
      final operacionIdOriginal = ventaGuardadaDurable.operacionId;
      expect(operacionIdOriginal, isNotEmpty);
      expect(ventaGuardadaDurable.secuenciaLocal, 1);
      expect(ventaGuardadaDurable.totalBob, 220.0);

      // --- PASO 3: Reinicio de la App (Restauración transparente desde SQLite) ---
      // Matamos la app: creamos una nueva instancia del servicio y de la pantalla,
      // con la red aún caída, demostrando restauración transparente desde SQLite
      final cajaSrvReinicio = CajaService(
        api: api,
        sesiones: sessionManager,
        storage: storage,
      );

      // Desmontar la pantalla para ejecutar initState con el servicio nuevo.
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pumpWidget(
        MaterialApp(
          home: CajaOfflineScreen(
            servicioCaja: cajaSrvReinicio,
            servicioSucursal: sucursalSrv,
            servicioCatalogo: catalogoSrv,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // La app reiniciada restauró el turno y la venta pendiente desde SQLite sin red
      expect(cajaSrvReinicio.turnoActivoLocal?.turnoId, testTurnoId);
      expect(cajaSrvReinicio.ventasOfflinePendientes.single.operacionId,
          operacionIdOriginal);
      expect(find.text('CAJA-MOVIL-01'), findsOneWidget);
      expect(find.text('ABIERTO'), findsOneWidget);
      expect(find.text('1 venta(s) pendientes de sincronizar'), findsOneWidget);
      expect(find.text('Disp: 0 / 1 (Bs 220.00)'), findsOneWidget);

      // --- PASO 4: Reconexión y Sincronización preservando el operacion_id ---
      // Vuelve la red
      redDisponible = true;

      // Presionar Sincronizar
      final btnSync = find.text('Sincronizar');
      await tester.ensureVisible(btnSync);
      await tester.tap(btnSync);
      await tester.pumpAndSettle();

      // Verificar que el backend recibió la sincronización con el EXACTO operacion_id original
      expect(operacionIdCapturadaEnSync, equals(operacionIdOriginal));

      // La venta ya no está pendiente
      expect(find.text('1 venta(s) pendientes de sincronizar'), findsNothing);

      // --- PASO 5: Cierre de Turno y Conciliación ---
      // Ingresar arqueo
      final arqueoFinder = find.widgetWithText(
          TextField, 'Arqueo de Efectivo Final en Caja (Bs)');
      await tester.ensureVisible(arqueoFinder);
      await tester.enterText(arqueoFinder, '220');
      await tester.pumpAndSettle();

      // Tap Cerrar Turno
      final btnCerrar = find.text('Cerrar Turno y Devolver Cupos');
      await tester.ensureVisible(btnCerrar);
      await tester.tap(btnCerrar);
      await tester.pumpAndSettle();

      // Diálogo de confirmación
      expect(find.text('Confirmar Cierre'), findsOneWidget);
      await tester.tap(find.text('Confirmar Cierre'));
      await tester.pumpAndSettle();

      // Verificar que el backend recibió el DTO de cierre con todos los campos requeridos:
      // revision, ultima_secuencia_local, total_operaciones_locales, operaciones_pendientes, arqueo_efectivo_bob
      expect(cuerpoCierreCapturado, isNotNull);
      expect(cuerpoCierreCapturado!['revision'], 1);
      expect(cuerpoCierreCapturado!['ultima_secuencia_local'], 1);
      expect(cuerpoCierreCapturado!['total_operaciones_locales'], 1);
      expect(cuerpoCierreCapturado!['operaciones_pendientes'], isEmpty);
      expect(cuerpoCierreCapturado!['arqueo_efectivo_bob'], '220.00');

      // Vuelve al formulario sin turno y SQLite queda limpio
      expect(find.text('Habilitar Turno de Caja'), findsOneWidget);
      expect(
        find.text(
          'No hay prendas con disponibilidad confirmada en esta sucursal. '
          'Con?ctate y vuelve a cargar.',
        ),
        findsOneWidget,
      );
      final turnoSqliteFinal = await storage.obtenerTurnoActivoLocal(
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: dispositivoCajaPrueba,
      );
      expect(turnoSqliteFinal, isNull);
    });
  });
}
