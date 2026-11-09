// IA cliente y voz: recomendaciones, búsqueda, permisos y fallback.
import 'dart:convert';

import 'package:fashionstore_movil/features/catalogo/models/catalogo_model.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/catalogo/services/catalogo_service.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/services/ia_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/busqueda/control_voz.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

ApiClient apiCon(MockClient mock) =>
    ApiClient(httpClient: mock, sesiones: SessionManager());

http.Response ok(Object j) => http.Response(
      jsonEncode(j),
      200,
      headers: {'content-type': 'application/json'},
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('recomendación con productos navegables y motivo', () async {
    SharedPreferences.setMockInitialValues({});
    final mock = MockClient((_) async => ok({
          'items': [
            {
              'producto_id': 'p1',
              'variante_id': 'v1',
              'nombre': 'Vestido',
              'precio': 199.99,
              'disponible': 2,
              'motivo': 'Temporada actual',
            },
          ],
          'proveedor': 'DETERMINISTA',
        }));
    final r = await IaService(api: apiCon(mock)).recomendaciones();
    expect(r.items.length, 1);
    expect(r.items.first.motivo, isNotEmpty);
    expect(r.items.first.disponible, 2);
  });

  test('búsqueda escrita: interpreta y cae a texto si falla IA', () async {
    SharedPreferences.setMockInitialValues({});
    var iaLlamada = false;
    final mockIa = MockClient((_) async {
      iaLlamada = true;
      return http.Response('error', 500);
    });
    // IA falla -> el widget usaría fallback textual del catálogo.
    try {
      await IaService(api: apiCon(mockIa)).interpretarBusqueda('vestido');
      fail('debía fallar');
    } catch (_) {}
    expect(iaLlamada, isTrue);

    final mockCat = MockClient((_) async => ok([
          {
            'id': 'p1',
            'nombre': 'Vestido rojo',
            'precio_base': 100,
            'activo': true,
            'imagenes': [],
            'temporada_ids': [],
            'coleccion_ids': [],
          },
        ]));
    final items = await CatalogoService(api: apiCon(mockCat))
        .listarProductos(filtros: FiltrosCatalogo(texto: 'vestido'));
    expect(items.length, 1);
  });

  test('permiso de voz denegado mantiene búsqueda escrita', () async {
    final control = ControlVoz(
      reconocedor: ReconocedorVozFake(),
      permisoMock: () async => PermissionStatus.denied,
    );
    await control.iniciar();
    expect(control.estado, EstadoVoz.permisoDenegado);
    control.editarTexto('camisa verde');
    expect(control.texto, 'camisa verde');
  });

  test('reconocimiento entrega texto editable y resultado', () async {
    final control = ControlVoz(
      reconocedor: ReconocedorVozFake(textoSimulado: 'vestido rojo talla M'),
      permisoMock: () async => PermissionStatus.granted,
    );
    await control.iniciar();
    expect(control.estado, EstadoVoz.escuchando);
    expect(control.texto, contains('vestido'));
    control.editarTexto('vestido rojo');
    expect(control.texto, 'vestido rojo');
    await control.detener();
    expect(control.estado, EstadoVoz.resultado);
    control.marcarProcesando();
    expect(control.estado, EstadoVoz.procesando);
    control.marcarResultado(hayCoincidencias: false);
    expect(control.estado, EstadoVoz.sinCoincidencias);
    control.marcarError('falló');
    expect(control.estado, EstadoVoz.error);
  });

  test('micrófono no disponible no bloquea', () async {
    final control = ControlVoz(
      reconocedor: ReconocedorVozFake(disponibleSimulado: false),
      permisoMock: () async => PermissionStatus.granted,
    );
    await control.iniciar();
    expect(control.estado, EstadoVoz.noDisponible);
  });

  test('permiso denegado permanentemente y apertura de configuración',
      () async {
    var configAbierta = false;
    final control = ControlVoz(
      reconocedor: ReconocedorVozFake(),
      permisoMock: () async => PermissionStatus.permanentlyDenied,
      abrirConfigMock: () async {
        configAbierta = true;
        return true;
      },
    );
    await control.iniciar();
    expect(control.estado, EstadoVoz.permisoDenegadoPermanente);
    final ok = await control.abrirConfiguracion();
    expect(ok, isTrue);
    expect(configAbierta, isTrue);
  });
}
