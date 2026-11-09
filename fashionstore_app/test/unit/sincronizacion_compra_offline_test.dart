import 'package:flutter_test/flutter_test.dart';
import 'package:fashionstore_movil/features/reservas_traslados/models/sincronizacion_model.dart';

void main() {
  group('Sincronización Offline CU05 v3 Móvil', () {
    test('OperacionSincronizacionLocal genera payload con tipo SOLICITAR_COMPRA', () {
      final op = OperacionSincronizacionLocal(
        operacionId: 'op-compra-1',
        empresaId: 'emp-1',
        usuarioId: 'usr-1',
        dispositivoId: 'disp-1',
        secuenciaLocal: 5,
        referenciaHorariaId: 'ref-1',
        creadaLocalEn: '2026-11-04T15:00:00-04:00',
        datosJson: '''
        {
          "_tipo_operacion": "SOLICITAR_COMPRA",
          "sucursal_id": "suc-1",
          "modalidad": "RECOJO",
          "lineas": [{"variante_id": "var-1", "cantidad": 2}],
          "autorizacion_cobro": {
            "consentimiento": true,
            "metodo_preparado_id": "mp-1",
            "importe_bob": 300.0,
            "importe_usd": 43.10,
            "tasa": 6.96
          }
        }
        ''',
        estadoEnvio: 'PENDIENTE_ENVIO',
        actualizadoEn: '2026-11-04T15:00:00Z',
      );

      final payload = op.toApiPayload();

      expect(payload['version_esquema'], equals(3));
      expect(payload['operacion_id'], equals('op-compra-1'));
      expect(payload['tipo'], equals('SOLICITAR_COMPRA'));
      expect(payload['datos']['_tipo_operacion'], isNull);
      expect(payload['datos']['sucursal_id'], equals('suc-1'));
      expect(payload['datos']['lineas'].length, equals(1));
      expect(payload['datos']['autorizacion_cobro']['consentimiento'], isTrue);
    });

    test('OperacionSincronizacionLocal genera version_esquema 2 para SOLICITAR_COMPRA con modalidad sin cobro', () {
      final op = OperacionSincronizacionLocal(
        operacionId: 'op-compra-2',
        empresaId: 'emp-1',
        usuarioId: 'usr-1',
        dispositivoId: 'disp-1',
        secuenciaLocal: 2,
        creadaLocalEn: '2026-11-04T15:00:00-04:00',
        datosJson: '''
        {
          "_tipo_operacion": "SOLICITAR_COMPRA",
          "sucursal_id": "suc-1",
          "modalidad": "RECOJO",
          "lineas": [{"variante_id": "var-1", "cantidad": 1}]
        }
        ''',
        actualizadoEn: '2026-11-04T15:00:00Z',
      );

      final payload = op.toApiPayload();
      expect(payload['version_esquema'], equals(2));
      expect(payload['tipo'], equals('SOLICITAR_COMPRA'));
    });

    test('OperacionSincronizacionLocal por defecto mantiene SOLICITAR_RESERVA v1', () {
      final op = OperacionSincronizacionLocal(
        operacionId: 'op-reserva-1',
        empresaId: 'emp-1',
        usuarioId: 'usr-1',
        dispositivoId: 'disp-1',
        secuenciaLocal: 1,
        creadaLocalEn: '2026-11-04T15:00:00-04:00',
        datosJson: '{"sucursal_id": "suc-1", "lineas": []}',
        actualizadoEn: '2026-11-04T15:00:00Z',
      );

      final payload = op.toApiPayload();
      expect(payload['tipo'], equals('SOLICITAR_RESERVA'));
    });
  });
}
