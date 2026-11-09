import '../caja_fixture_aislada.dart';
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

void main() {
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  const empresaId = '11111111-1111-4111-8111-111111111111';
  const usuarioId = '22222222-2222-4222-8222-222222222222';
  const sucursalId = '33333333-3333-4333-8333-333333333333';
  const varianteId = '44444444-4444-4444-8444-444444444444';
  const turnoId = '55555555-5555-4555-8555-555555555555';

  late SessionManager sesiones;
  late LocalDatabaseService storage;

  Future<void> iniciarSesion(String rol) async {
    await sesiones.guardar(
      token: 'token-$rol',
      usuario: ClientePerfilModel(
        id: usuarioId,
        usuarioId: usuarioId,
        empresaId: empresaId,
        nombres: 'Personal',
        apellidos: 'Caja',
        nombreCompleto: 'Personal Caja',
        correoElectronico: 'caja@test.local',
        rol: rol,
        estado: 'ACTIVO',
        preferencias: {},
        creadoEn: DateTime.now(),
      ),
    );
  }

  TurnoHabilitacionModel crearTurno() {
    final ahora = DateTime.now().toUtc();
    return TurnoHabilitacionModel(
        empresaId: empresaId,
        horaCentralEn: DateTime.now().toUtc().toIso8601String(),
      turnoId: turnoId,
      habilitacionId: turnoId,
      cajaCodigo: 'CAJA-REVISION',
      dispositivoId: dispositivoCajaPrueba,
      sucursalId: sucursalId,
      cajeroId: usuarioId,
      estado: 'CONCILIACION',
      inicioEn: ahora.subtract(const Duration(hours: 2)).toIso8601String(),
      venceEn: ahora.add(const Duration(hours: 6)).toIso8601String(),
      versionPrecios: 'precios-v1',
      revision: 2,
      cupos: [
        CupoRespuestaModel(
          varianteId: varianteId,
          sku: 'SKU-CHAQUETA-M',
          productoNombre: 'Chaqueta azul',
          otorgado: 5,
          consumido: 0,
          liberado: 0,
          precioAutorizadoBob: 220,
        ),
      ],
    );
  }

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
      await prepararCajaPrueba();
    sesiones = SessionManager();
    storage = LocalDatabaseService(dbName: inMemoryDatabasePath);
    await storage.limpiarTodo();
  });

  tearDown(() async {
    await storage.limpiarTodo();
    await storage.close();
  });

  testWidgets('el cajero ve conciliación, pero no controles de supervisor',
      (tester) async {
    await iniciarSesion('CAJERO');
    final turno = crearTurno();
    await storage.guardarTurnoActivoLocal(
      turno,
      empresaId: empresaId,
      usuarioId: usuarioId,
    );
    final api = apiCajaPrueba(
      sesiones: sesiones,
      httpClient: MockClient((request) async => http.Response('[]', 500)),
    );
    final caja = cajaDePrueba(api: api, sesiones: sesiones, storage: storage);

    await tester.pumpWidget(MaterialApp(
      home: CajaOfflineScreen(
        servicioCaja: caja,
        servicioSucursal: SucursalService(api: api),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('CONCILIACION'), findsOneWidget);
    expect(
        find.byKey(const Key('tarjeta_resolucion_supervisada')), findsNothing);
  });

  testWidgets(
      'supervisor envía acta, conteo y faltante retenido; actualiza cupo desde servidor',
      (tester) async {
    await iniciarSesion('ADMINISTRADOR');
    final turno = crearTurno();
    await storage.guardarTurnoActivoLocal(
      turno,
      empresaId: empresaId,
      usuarioId: usuarioId,
    );

    Map<String, dynamic>? cierreEnviado;
    final turnoActualizado = {
      ...turno.toJson(),
      'revision': 3,
      'estado': 'CONCILIACION',
      'cupos': [
        {
          'variante_id': varianteId,
          'sku': 'SKU-CHAQUETA-M',
          'producto_nombre': 'Chaqueta azul',
          'otorgado': 5,
          'consumido': 0,
          'liberado': 4,
          'precio_autorizado_bob': '220.00',
        }
      ],
    };
    final api = apiCajaPrueba(
      sesiones: sesiones,
      httpClient: MockClient((request) async {
        if (request.url.path.endsWith('/cajas/turnos/activo')) {
          return http.Response('[]', 500);
        }
        if (request.url.path.endsWith('/sucursales')) {
          return http.Response('[]', 200,
              headers: {'content-type': 'application/json'});
        }
        if (request.url.path.endsWith('/cajas/turnos/$turnoId/cerrar')) {
          cierreEnviado = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'turno_id': turnoId,
              'estado': 'CONCILIACION',
              'cerrado_en': null,
              'revision': 3,
              'cupos_devueltos': [
                {'variante_id': varianteId, 'devuelto': 4},
              ],
              'cupos_retenidos': [
                {'variante_id': varianteId, 'retenido': 1},
              ],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.endsWith('/cajas/turnos/$turnoId')) {
          return http.Response(jsonEncode(turnoActualizado), 200,
              headers: {'content-type': 'application/json'});
        }
        return http.Response('[]', 200,
            headers: {'content-type': 'application/json'});
      }),
    );
    final caja = cajaDePrueba(api: api, sesiones: sesiones, storage: storage);

    await tester.pumpWidget(MaterialApp(
      home: CajaOfflineScreen(
        servicioCaja: caja,
        servicioSucursal: SucursalService(api: api),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('tarjeta_resolucion_supervisada')),
        findsOneWidget);
    final boton = tester.widget<ElevatedButton>(
      find.byKey(const Key('resolver_cierre_supervisado')),
    );
    expect(boton.onPressed, isNull,
        reason: 'Faltan acta, motivo, arqueo y decisión del faltante.');

    final count = find.byKey(const Key('conteo_fisico_$varianteId'));
    await tester.ensureVisible(count);
    await tester.enterText(count, '4');
    await tester.pumpAndSettle();

    final resolution = find.byKey(const Key('resolucion_$varianteId'));
    await tester.ensureVisible(resolution);
    await tester.tap(resolution);
    await tester.pumpAndSettle();
    await tester
        .tap(find.text('Mantener retenidas mientras se investiga').last);
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('motivo_faltante_$varianteId')),
      'Esperar transmisión de una venta de la caja',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Referencia del acta o registro físico'),
      'ACTA-CAJA-2026-04',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Motivo de la revisión supervisada'),
      'Cierre de caja tras conteo físico de fin de turno',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Efectivo contado físicamente (Bs)'),
      '0',
    );
    await tester.pumpAndSettle();

    final listo = tester.widget<ElevatedButton>(
      find.byKey(const Key('resolver_cierre_supervisado')),
    );
    expect(listo.onPressed, isNotNull);
    await tester
        .ensureVisible(find.byKey(const Key('resolver_cierre_supervisado')));
    await tester.tap(find.byKey(const Key('resolver_cierre_supervisado')));
    await tester.pumpAndSettle();

    expect(cierreEnviado, isNotNull);
    expect(cierreEnviado!['supervision_forzada'], isTrue);
    expect(cierreEnviado!['motivo_supervision'], contains('conteo físico'));
    expect(cierreEnviado!['arqueo_declarado_bob'], '0.00');
    expect(cierreEnviado!['evidencia_cierre']['referencia_acta'],
        'ACTA-CAJA-2026-04');
    expect(
      cierreEnviado!['evidencia_cierre']['conteo_fisico_por_variante'],
      [
        {'variante_id': varianteId, 'cantidad_encontrada': 4}
      ],
    );
    expect(
      cierreEnviado!['ajustes_inventario']['resoluciones_por_variante'],
      [
        {
          'variante_id': varianteId,
          'resolucion': 'PENDIENTE_SINCRONIZACION',
          'motivo': 'Esperar transmisión de una venta de la caja',
        }
      ],
    );
    expect(cierreEnviado!.containsKey('descarte_venta_fisica'), isFalse);
    expect(find.text('CONCILIACION'), findsOneWidget);
    expect(find.textContaining('1 unidades por conciliar'), findsOneWidget);
  });
}
