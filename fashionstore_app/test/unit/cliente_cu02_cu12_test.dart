import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/identidad_empresas/services/suscripcion_service.dart';
import 'package:fashionstore_movil/features/organizacion/services/tasa_cambio_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('Consumo Cliente CU02 y CU12', () {
    test('CU02: SuscripcionService consume capacidades y plan de la empresa', () async {
      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/empresas/mi-plan')) {
          return http.Response(
            jsonEncode({
              'suscripcion_id': 'susc-12345',
              'empresa_id': 'emp-999',
              'plan_id': 'plan-premium-id',
              'plan_codigo': 'PLAN-PREMIUM',
              'plan_nombre': 'Plan Corporativo Pro',
              'version': 1,
              'revision': 1,
              'inicio_en': '2026-11-01T00:00:00Z',
              'vence_en': '2027-11-01T00:00:00Z',
              'gracia_hasta': '2027-11-15T00:00:00Z',
              'estado_efectivo': 'ACTIVO',
              'capacidades': ['PROBADOR_VIRTUAL', 'CAJA_OFFLINE', 'DELIVERY_MULTIZONA'],
              'sucursales_activas': 3,
              'limite_sucursales': 5,
              'permite_offline': true,
              'creada_en': '2026-11-01T00:00:00Z',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = ApiClient(httpClient: mockHttp);
      final srv = SuscripcionService(api: api);

      final plan = await srv.consultarMiPlan(empresaId: 'emp-999');

      expect(plan.planNombre, 'Plan Corporativo Pro');
      expect(plan.planCodigo, 'PLAN-PREMIUM');
      expect(plan.estadoEfectivo, 'ACTIVO');
      expect(plan.permiteOffline, isTrue);
      expect(plan.sucursalesActivas, 3);
      expect(plan.limiteSucursales, 5);
      expect(plan.capacidades, contains('PROBADOR_VIRTUAL'));
      expect(plan.capacidades, contains('CAJA_OFFLINE'));
    });

    test('CU12: TasaCambioService consume tasa vigente BOB/USD y cotización oficial', () async {
      final mockHttp = MockClient((request) async {
        if (request.url.path.contains('/plataforma/tasas-cambio/vigente')) {
          return http.Response(
            jsonEncode({
              'id': 'tasa-vigente-id',
              'version': 3,
              'tasa_bob_por_usd': '6.96',
              'vigente_desde': '2026-11-01T00:00:00Z',
              'vigente_hasta': null,
              'motivo': 'Tasa oficial fijada por plataforma',
              'creada_en': '2026-11-01T00:00:00Z',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.contains('/plataforma/tasas-cambio/cotizar')) {
          expect(request.url.queryParameters['monto_bob'], '139.20');
          return http.Response(
            jsonEncode({
              'monto_bob': '139.20',
              'monto_usd': '20.00',
              'centavos_usd': 2000,
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = ApiClient(httpClient: mockHttp);
      final srv = TasaCambioService(api: api);

      final tasa = await srv.obtenerTasaVigente();
      expect(tasa.tasaBobPorUsd, 6.96);
      expect(tasa.version, 3);
      expect(tasa.motivo, 'Tasa oficial fijada por plataforma');

      final cot = await srv.cotizar(139.20);
      expect(cot.montoBob, 139.20);
      expect(cot.montoUsd, 20.00);
      expect(cot.centavosUsd, 2000);
    });
  });
}
