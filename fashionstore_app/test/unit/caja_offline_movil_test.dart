import '../caja_fixture_aislada.dart';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/models/caja_model.dart';
import 'package:fashionstore_movil/features/ventas_pagos/services/caja_service.dart';

void main() {
  group('Caja Offline Móvil — CU06 y CU07 (Personal Autorizado)', () {
    late SessionManager sessionManager;
    const testEmpresaId = '11111111-1111-4111-8111-111111111111';
    const testUsuarioId = '22222222-2222-4222-8222-222222222222';
    const testSucursalId = '33333333-3333-4333-8333-333333333333';
    const testVarianteId = '44444444-4444-4444-8444-444444444444';
    const testTurnoId = '55555555-5555-4555-8555-555555555555';

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await prepararCajaPrueba();
      sessionManager = SessionManager();
      await sessionManager.guardar(
        token: 'token-cajero-test',
        usuario: ClientePerfilModel(
          id: testUsuarioId,
          usuarioId: testUsuarioId,
          empresaId: testEmpresaId,
          nombres: 'Cajero',
          apellidos: 'Móvil',
          nombreCompleto: 'Cajero Móvil',
          correoElectronico: 'cajero@fashionstore.test',
          rol: 'CAJERO',
          estado: 'ACTIVO',
          preferencias: {},
          creadoEn: DateTime.now(),
        ),
      );
    });

    test('CU06: Habilitar turno online con cupos exclusivos y vigencia de 8 horas', () async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/cajas/turnos') && request.method == 'POST') {
          expect(request.headers['Idempotency-Key'], isNotNull);
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['caja_id'], 'CAJA-MOVIL-01');
          expect(body['cupos'].length, 1);

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
                  'variante_id': testVarianteId,
                  'sku': 'SKU-VESTIDO-ROJO',
                  'producto_nombre': 'Vestido Rojo Elegante',
                  'otorgado': 5,
                  'consumido': 0,
                  'liberado': 0,
                  'precio_autorizado_bob': '150.00',
                }
              ],
              'snapshot': {
                'version': 'precios-v1',
                'productos': [],
              }
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final apiClient = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaService = cajaDePrueba(api: apiClient, sesiones: sessionManager);

      final turno = await cajaService.habilitarTurno(TurnoCrearModel(
        cajaId: 'CAJA-MOVIL-01',
        dispositivoId: dispositivoCajaPrueba,
        sucursalId: testSucursalId,
        cupos: [CupoItemModel(varianteId: testVarianteId, cantidad: 5)],
      ));

      expect(turno.turnoId, testTurnoId);
      expect(turno.estado, 'ABIERTO');
      expect(turno.estaVigente, isTrue);
      expect(turno.cupos.first.otorgado, 5);
      expect(turno.cupos.first.disponible, 5);
    });

    test('CU07: Encolar venta física offline en efectivo y descontar cupo local', () async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final cajaService = cajaDePrueba(sesiones: sessionManager);
      final turnoInicial = TurnoHabilitacionModel(
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
            sku: 'SKU-VESTIDO-ROJO',
            otorgado: 5,
            consumido: 0,
            precioAutorizadoBob: 150.0,
          )
        ],
      );

      await fijarTurnoPrueba(cajaService, turnoInicial);
      expect(cajaService.turnoActivoLocal!.cupos.first.disponible, 5);

      // Simular venta offline en efectivo de 2 unidades
      final ventaOffline = VentaOfflineCrearModel(
        operacionId: '66666666-6666-4666-8666-666666666666',
        secuenciaLocal: 1,
        vendidaLocalEn: ahora.toIso8601String(),
        entregadaLocalEn: ahora.toIso8601String(),
        versionPrecios: 'precios-v1',
        lineas: [
          VentaOfflineLineaModel(
            varianteId: testVarianteId,
            cantidad: 2,
            precioAutorizadoBob: 150.0,
          )
        ],
        totalBob: 300.0,
        efectivoRecibidoBob: 300.0,
        cambioEntregadoBob: 0.0,
      );

      await guardarVentaPrueba(cajaService, ventaOffline);

      // El cupo local debe descontarse en memoria
      expect(cajaService.turnoActivoLocal!.cupos.first.consumido, 2);
      expect(cajaService.turnoActivoLocal!.cupos.first.disponible, 3);
      expect(cajaService.ventasOfflinePendientes.length, 1);
    });

    test('CU07: Sincronizar venta offline al reconectar con el servidor', () async {
      final ahora = DateTime.now().toUtc();
      final vence = ahora.add(const Duration(hours: 8));

      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/ventas') && request.method == 'POST') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['operacion_id'], '66666666-6666-4666-8666-666666666666');
          expect(body['total_bob'], '300.00');

          return http.Response(
            jsonEncode({
              'resultado': 'REGISTRADA_CENTRAL',
              'operacion_id': '66666666-6666-4666-8666-666666666666',
              'venta_id': '77777777-7777-4777-8777-777777777777',
              'numero': 'VNT-OFF-123456',
              'total_bob': 300.0,
              'comprobante_id': '77777777-7777-4777-8777-777777777777',
              'recibida_central_en': ahora.toIso8601String(),
            }),
            201,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final apiClient = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaService = cajaDePrueba(api: apiClient, sesiones: sessionManager);

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
            sku: 'SKU-VESTIDO-ROJO',
            otorgado: 5,
            consumido: 0,
            precioAutorizadoBob: 150.0,
          )
        ],
      );
      await fijarTurnoPrueba(cajaService, turno);

      final venta = VentaOfflineCrearModel(
        operacionId: '66666666-6666-4666-8666-666666666666',
        secuenciaLocal: 1,
        vendidaLocalEn: ahora.toIso8601String(),
        entregadaLocalEn: ahora.toIso8601String(),
        versionPrecios: 'precios-v1',
        lineas: [
          VentaOfflineLineaModel(
            varianteId: testVarianteId,
            cantidad: 2,
            precioAutorizadoBob: 150.0,
          )
        ],
        totalBob: 300.0,
        efectivoRecibidoBob: 300.0,
        cambioEntregadoBob: 0.0,
      );

      await guardarVentaPrueba(cajaService, venta);
      expect(cajaService.ventasOfflinePendientes.length, 1);

      final totalSincronizadas = await cajaService.sincronizarVentasPendientes(testTurnoId);
      expect(totalSincronizadas, 1);
      expect(cajaService.ventasOfflinePendientes.isEmpty, isTrue);
    });

    test('CU06 / CU07: Cierre de turno supervisado y devolución de cupos no consumidos', () async {
      final ahora = DateTime.now().toUtc();

      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/cerrar') && request.method == 'POST') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['revision'], 1);

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
                  'consumido': 2,
                  'devuelto': 3,
                }
              ]
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final apiClient = apiCajaPrueba(httpClient: mockHttp, sesiones: sessionManager);
      final cajaService = cajaDePrueba(api: apiClient, sesiones: sessionManager);

      final resultado = await cajaService.cerrarTurno(
        testTurnoId,
        TurnoCerrarModel(revision: 1),
      );

      expect(resultado.estado, 'CERRADO');
      expect(resultado.revision, 2);
      expect(resultado.cuposDevueltos.first['devuelto'], 3);
      expect(cajaService.turnoActivoLocal, isNull);
    });
  });
}
