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
import 'package:fashionstore_movil/features/reservas_traslados/models/reserva_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/models/sincronizacion_model.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/reserva_detalle_screen.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/reservas_screen.dart';
import 'package:fashionstore_movil/features/reservas_traslados/services/reserva_service.dart';
import 'package:fashionstore_movil/features/reservas_traslados/services/sincronizacion_offline_service.dart';

Widget _crearApp(Widget child) => MaterialApp(
      home: Scaffold(body: child),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfiNoIsolate;
  });

  group('CU18 & CU04: Reservas Detalle y Sincronización', () {
    late LocalDatabaseService storage;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      storage = LocalDatabaseService(dbName: inMemoryDatabasePath);
    });

    tearDown(() async {
      await storage.close();
    });

    testWidgets('CU18: detalle muestra revisión, origen plazo, badge 72h adelanto y origen offline', (tester) async {
      final reserva = Reserva(
        id: 'res-offline-101',
        empresaId: 'emp-fs',
        sucursalDestinoId: 'suc-central',
        clienteId: 'usr-44',
        codigo: 'RES-OFF-101',
        creadaEn: DateTime.parse('2026-11-01T10:00:00-04:00'),
        fechaVisita: DateTime.parse('2026-11-03T16:00:00-04:00'),
        venceEn: DateTime.parse('2026-11-04T10:00:00-04:00'),
        origenPlazoEn: DateTime.parse('2026-11-01T10:00:00-04:00'),
        estado: 'PENDIENTE',
        revision: 4,
        adelantoMonto: '50.0',
        operacionSincronizacionId: 'uuid-op-99',
        detalles: [
          DetalleReserva(
            id: 'det-1',
            varianteId: 'var-elegante',
            cantidadSolicitada: 2,
            cantidadReservada: 2,
            cantidadPendienteTraslado: 0,
            cantidadVendida: 0,
            cantidadLiberada: 0,
            estadoLinea: 'RESERVADA',
          ),
        ],
        traslados: [],
      );

      final mock = MockClient((request) async {
        if (request.url.path.contains('/reservas/res-offline-101')) {
          return http.Response(
            jsonEncode(reserva.toJson()),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = ApiClient(httpClient: mock, sesiones: SessionManager());
      final servicio = ReservaService(api: api);

      await tester.pumpWidget(_crearApp(ReservaDetalleScreen(
        reservaId: 'res-offline-101',
        servicioReservas: servicio,
      )));
      await tester.pumpAndSettle();

      // Revisión y metadatos CU18
      expect(find.text('Revisión'), findsOneWidget);
      expect(find.text('v4'), findsOneWidget);
      expect(find.textContaining('72 h'), findsOneWidget);
      expect(find.text('Reserva offline aceptada (CU04)'), findsOneWidget);
      expect(find.text('Origen del plazo'), findsOneWidget);
      expect(find.text('Apartada'), findsOneWidget);
    });

    testWidgets('CU18: cancelar envía revisión y maneja 409 recargando reserva', (tester) async {
      int cancelIntentos = 0;
      int reloadIntentos = 0;
      int revisionEnviada = 0;

      final reservaInicial = Reserva(
        id: 'res-cancel-1',
        empresaId: 'emp-fs',
        sucursalDestinoId: 'suc-central',
        clienteId: 'usr-1',
        codigo: 'RES-CAN-1',
        creadaEn: DateTime.parse('2026-11-01T10:00:00-04:00'),
        fechaVisita: DateTime.parse('2026-11-02T10:00:00-04:00'),
        venceEn: DateTime.parse('2026-11-02T16:00:00-04:00'),
        estado: 'PENDIENTE',
        revision: 2,
        detalles: [
          DetalleReserva(
            id: 'det-1',
            varianteId: 'v1',
            cantidadSolicitada: 1,
            cantidadReservada: 1,
            cantidadPendienteTraslado: 0,
            cantidadVendida: 0,
            cantidadLiberada: 0,
            estadoLinea: 'RESERVADA',
          )
        ],
        traslados: [],
      );

      final reservaActualizada = Reserva(
        id: 'res-cancel-1',
        empresaId: 'emp-fs',
        sucursalDestinoId: 'suc-central',
        clienteId: 'usr-1',
        codigo: 'RES-CAN-1',
        creadaEn: DateTime.parse('2026-11-01T10:00:00-04:00'),
        fechaVisita: DateTime.parse('2026-11-02T10:00:00-04:00'),
        venceEn: DateTime.parse('2026-11-02T16:00:00-04:00'),
        estado: 'PENDIENTE',
        revision: 3, // Revisión incrementada tras 409
        detalles: reservaInicial.detalles,
        traslados: [],
      );

      final mock = MockClient((request) async {
        if (request.method == 'GET' && request.url.path.contains('/reservas/res-cancel-1')) {
          reloadIntentos++;
          final r = reloadIntentos == 1 ? reservaInicial : reservaActualizada;
          return http.Response(
            jsonEncode(r.toJson()),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.method == 'PATCH' && request.url.path.contains('/reservas/res-cancel-1/cancelar')) {
          cancelIntentos++;
          final body = jsonDecode(request.body) as Map;
          revisionEnviada = (body['revision'] as num).toInt();
          // El primer intento devuelve 409 por conflicto de revisión
          return http.Response(
            jsonEncode({'detail': 'Revisión obsoleta. Conflicto de concurrencia.'}),
            409,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = ApiClient(httpClient: mock, sesiones: SessionManager());
      final servicio = ReservaService(api: api);

      await tester.pumpWidget(_crearApp(ReservaDetalleScreen(
        reservaId: 'res-cancel-1',
        servicioReservas: servicio,
      )));
      await tester.pumpAndSettle();

      final btnCancelar = find.text('Cancelar reserva');
      expect(btnCancelar, findsOneWidget);
      await tester.ensureVisible(btnCancelar);
      await tester.tap(btnCancelar);
      await tester.pumpAndSettle();

      // Debe abrir el diálogo de confirmación
      expect(find.text('Cancelar reserva'), findsWidgets);
      // Confirmar en el AlertDialog con ElevatedButton
      await tester.tap(find.widgetWithText(ElevatedButton, 'Sí, cancelar'));
      await tester.pumpAndSettle();

      expect(cancelIntentos, 1);
      expect(revisionEnviada, 2, reason: 'Debe enviar la revisión actual en el body de cancelación');
      // Debe haber recargado la reserva tras el 409 y mostrar la revisión 3
      expect(reloadIntentos, 2);
      expect(find.text('v3'), findsOneWidget);
    });

    testWidgets('CU04 en ReservasScreen: muestra banner de operaciones pendientes de sincronización', (tester) async {
      final sesionMgr = SessionManager();
      const testEmpresaId = '00000000-0000-4000-8000-000000000001';
      const testUsuarioId = 'usr-banner';

      await sesionMgr.guardar(
        token: 'token-usr-banner',
        usuario: ClientePerfilModel(
          id: testUsuarioId,
          usuarioId: testUsuarioId,
          empresaId: testEmpresaId,
          nombres: 'Banner',
          apellidos: 'Test',
          nombreCompleto: 'Banner Test',
          correoElectronico: 'banner@test.com',
          rol: 'CLIENTE',
          estado: 'ACTIVO',
          preferencias: {},
          creadoEn: DateTime.now(),
        ),
      );

      // Guardar una operación offline en la cola para la empresa y usuario activo
      final op = OperacionSincronizacionLocal(
        operacionId: 'uuid-banner-1',
        empresaId: testEmpresaId,
        usuarioId: testUsuarioId,
        dispositivoId: 'disp-1',
        secuenciaLocal: 1,
        creadaLocalEn: '2026-11-01T15:00:00-04:00',
        datosJson: jsonEncode({
          'sucursal_id': 'suc-1',
          'visita_en': '2026-11-02T10:00:00-04:00',
          'lineas': [
            {'variante_id': 'v-1', 'cantidad': 2}
          ]
        }),
        estadoEnvio: 'PENDIENTE_ENVIO',
        actualizadoEn: '2026-11-01T15:00:00-04:00',
      );
      await storage.encolarOperacion(op);

      final mock = MockClient((request) async {
        if (request.url.path.contains('/reservas/mias') || request.url.path.contains('/reservas')) {
          return http.Response(
            jsonEncode({'total': 0, 'limit': 20, 'offset': 0, 'items': []}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = ApiClient(httpClient: mock, sesiones: sesionMgr);
      final servicio = ReservaService(api: api);
      final offlineSrv = SincronizacionOfflineService(api: api, storage: storage, sesiones: sesionMgr);

      await tester.pumpWidget(_crearApp(ReservasScreen(
        servicio: servicio,
        servicioOffline: offlineSrv,
      )));
      await tester.pumpAndSettle();

      // Debe mostrar el banner con las reservas pendientes offline
      expect(find.textContaining('1 solicitud(es) offline pendiente(s)'), findsOneWidget);
      expect(find.widgetWithText(ElevatedButton, 'Sincronizar'), findsOneWidget);
    });
  });
}
