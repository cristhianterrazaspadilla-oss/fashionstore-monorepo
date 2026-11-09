import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/features/identidad_empresas/cuenta/cuenta_screen.dart';
import 'package:fashionstore_movil/features/posventa/posventa_screen.dart';
import 'package:fashionstore_movil/features/posventa/services/posventa_service.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';

class FakeApiClientWidget extends ApiClient {
  @override
  Future<T> get<T>(
    String ruta, {
    Map<String, String>? query,
    required T Function(dynamic) convertir,
  }) async {
    if (ruta == '/saldos/mio') {
      return convertir({
        'cliente_id': 'cli-101',
        'empresa_id': 'emp-202',
        'saldo_disponible_bob': 250.00,
        'saldo_retenido_bob': 0.0,
        'moneda': 'BOB',
        'movimientos': [
          {
            'id': 'm-1',
            'tipo': 'ABONO_COMPENSACION',
            'monto_bob': 250.0,
            'saldo_resultante_bob': 250.0,
            'motivo': 'Abono de cortesía comercial',
            'creada_en': '2026-11-04T12:00:00Z',
          }
        ],
      });
    } else if (ruta == '/devoluciones/mias') {
      return convertir([
        {
          'id': 'd-1',
          'venta_id': 'v-1',
          'estado': 'EN_CUSTODIA',
          'motivo_codigo': 'TALLA',
          'motivo_descripcion': 'Talla incorrecta',
          'sucursal_id': 's-1',
          'solicitada_en': '2026-11-04T10:00:00Z',
          'detalles': [],
        }
      ]);
    } else if (ruta == '/cambios/mios') {
      return convertir([
        {
          'cambio_id': 'c-1',
          'venta_id': 'v-2',
          'estado': 'REGISTRADO',
          'diferencia_bob': 20.0,
          'direccion_diferencia': 'FAVOR_EMPRESA',
          'vence_espera_en': '2026-11-11T10:00:00Z',
          'creado_en': '2026-11-04T10:00:00Z',
        }
      ]);
    } else if (ruta == '/reembolsos/mios') {
      return convertir([
        {
          'id': 'r-1',
          'origen_tipo': 'DEVOLUCION_STOCK',
          'estado': 'EJECUTADO',
          'monto_bob': 150.0,
          'creada_en': '2026-11-04T10:00:00Z',
        }
      ]);
    }
    throw UnimplementedError('Ruta GET no mockeada: $ruta');
  }
}

void main() {
  testWidgets('PosventaScreen renderiza pestañas y muestra saldo disponible',
      (tester) async {
    final srv = PosventaService(api: FakeApiClientWidget());

    await tester.pumpWidget(
      MaterialApp(
        home: PosventaScreen(service: srv),
      ),
    );

    // Esperar carga asíncrona
    await tester.pumpAndSettle();

    // Verificar pestañas accesibles
    expect(find.text('Mi Saldo'), findsOneWidget);
    expect(find.text('Devoluciones'), findsOneWidget);
    expect(find.text('Cambios'), findsOneWidget);
    expect(find.text('Reembolsos'), findsOneWidget);

    // Verificar saldo disponible formateado
    expect(find.text('Bs 250.00'), findsOneWidget);
    expect(find.text('Saldo disponible para compras'), findsOneWidget);
    expect(find.text('Abono de cortesía comercial'), findsOneWidget);

    // Cambiar a pestaña Devoluciones
    await tester.tap(find.byKey(const Key('tab_devoluciones')));
    await tester.pumpAndSettle();
    expect(find.text('Devolución: EN_CUSTODIA'), findsOneWidget);

    // Cambiar a pestaña Cambios
    await tester.tap(find.byKey(const Key('tab_cambios')));
    await tester.pumpAndSettle();
    expect(find.text('Cambio: REGISTRADO'), findsOneWidget);
    expect(find.text('Diferencia: Bs 20.00 (FAVOR_EMPRESA)'), findsOneWidget);

    // Cambiar a pestaña Reembolsos
    await tester.tap(find.byKey(const Key('tab_reembolsos')));
    await tester.pumpAndSettle();
    expect(find.text('Reembolso: EJECUTADO'), findsOneWidget);
    expect(find.text('Bs 150.00'), findsOneWidget);
  });

  testWidgets(
      'CuentaScreen permite acceso directo a PosventaScreen sin quedar huerfana',
      (tester) async {
    SharedPreferences.setMockInitialValues({});
    final usuario = ClientePerfilModel.fromJson({
      'id': 'usr-1',
      'usuario_id': 'usr-1',
      'nombres': 'Ana',
      'apellidos': 'Gómez',
      'nombre_completo': 'Ana Gómez',
      'correo_electronico': 'cliente@fashionstore.local',
      'rol': 'CLIENTE',
      'estado': 'ACTIVO',
      'empresa_id': 'emp-1',
      'creado_en': DateTime.now().toUtc().toIso8601String(),
    });
    await SessionManager().guardar(token: 'tok-123', usuario: usuario);

    await tester.pumpWidget(
      MaterialApp(
        home: CuentaScreen(onSesionCerrada: () {}),
      ),
    );
    await tester.pumpAndSettle();

    // El cliente autenticado ve la tarjeta de Posventa y Garantías
    expect(find.text('Posventa y Garantías'), findsOneWidget);
    expect(find.byKey(const Key('btn_posventa_garantias')), findsOneWidget);

    // Al tocarla navega a PosventaScreen
    await tester.tap(find.byKey(const Key('btn_posventa_garantias')));
    await tester.pumpAndSettle();

    expect(find.byType(PosventaScreen), findsOneWidget);
    expect(find.text('Mi Cuenta y Posventa'), findsOneWidget);
  });

  testWidgets('CuentaScreen en modo invitado expone Posventa y Devoluciones',
      (tester) async {
    SharedPreferences.setMockInitialValues({});

    await tester.pumpWidget(
      MaterialApp(
        home: CuentaScreen(onSesionCerrada: () {}),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Posventa y Devoluciones'), findsOneWidget);
  });
}
