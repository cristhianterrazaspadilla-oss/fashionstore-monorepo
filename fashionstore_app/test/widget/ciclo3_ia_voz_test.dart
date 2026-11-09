// Widgets IA y voz: recomendaciones, buscador, estados y accesibilidad.
import 'dart:convert';

import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/catalogo/services/catalogo_service.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/services/ia_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/busqueda/buscador_voz.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/busqueda/control_voz.dart';
import 'package:fashionstore_movil/features/experiencia_cliente/recomendaciones/recomendaciones_section.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response ok(Object j, [int code = 200]) => http.Response(
      jsonEncode(j),
      code,
      headers: {'content-type': 'application/json'},
    );

MockClient mockIa({bool vacio = false, bool error = false}) =>
    MockClient((req) async {
      if (error) return http.Response('falla', 500);
      if (req.url.path.contains('recomendaciones')) {
        return ok({
          'items': vacio
              ? []
              : [
                  {
                    'producto_id': 'p1',
                    'variante_id': 'v1',
                    'nombre':
                        'Vestido de Verano con Estampado Floral Exclusivo de Temporada',
                    'precio': 249.99,
                    'disponible': 4,
                    'motivo': 'Coincide con tu talla y la temporada actual.',
                  },
                ],
          'proveedor': 'DETERMINISTA',
        });
      }
      if (req.url.path.contains('busqueda')) {
        return ok({
          'filtros': {'categoria': 'vestidos'},
          'total': 1,
          'items': [
            {
              'producto_id': 'p1',
              'variante_id': 'v1',
              'nombre': 'Vestido',
              'precio': 249.99,
              'disponible': 4,
              'motivo': 'Búsqueda por voz.',
            },
          ],
          'proveedor': 'DETERMINISTA',
        });
      }
      return http.Response('no', 404);
    });

void main() {
  setUpAll(() async {
    await initializeDateFormatting('es');
  });
  testWidgets('recomendaciones: pedir, ver motivo y reintentar', (t) async {
    SharedPreferences.setMockInitialValues({});
    final api = ApiClient(httpClient: mockIa(), sesiones: SessionManager());
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: RecomendacionesSection(
            servicioIa: IaService(api: api),
            servicioCatalogo: CatalogoService(api: api),
          ),
        ),
      ),
    ));
    await t.pumpAndSettle();
    await t.tap(find.text('Pedir sugerencias'));
    await t.pumpAndSettle();
    expect(find.textContaining('Coincide con tu talla'), findsOneWidget);
    expect(find.text('Al carrito'), findsOneWidget);
    expect(find.text('Reservar'), findsOneWidget);
  });

  testWidgets('recomendación vacía explica sin inventar', (t) async {
    SharedPreferences.setMockInitialValues({});
    final api =
        ApiClient(httpClient: mockIa(vacio: true), sesiones: SessionManager());
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: RecomendacionesSection(
            servicioIa: IaService(api: api),
            servicioCatalogo: CatalogoService(api: api),
          ),
        ),
      ),
    ));
    await t.pumpAndSettle();
    await t.tap(find.text('Pedir sugerencias'));
    await t.pumpAndSettle();
    expect(find.textContaining('No encontramos sugerencias'), findsOneWidget);
  });

  testWidgets('buscador por voz: permiso, texto y resultados', (t) async {
    SharedPreferences.setMockInitialValues({});
    final api = ApiClient(httpClient: mockIa(), sesiones: SessionManager());
    final control = ControlVoz(
      reconocedor: ReconocedorVozFake(textoSimulado: 'vestido rojo'),
      permisoMock: () async => PermissionStatus.granted,
    );
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: BuscadorConVoz(
            servicioIa: IaService(api: api),
            servicioCatalogo: CatalogoService(api: api),
            control: control,
          ),
        ),
      ),
    ));
    await t.pumpAndSettle();
    // Botón accesible con descripción.
    expect(find.byTooltip('Buscar por voz'), findsOneWidget);
    await t.tap(find.byTooltip('Buscar por voz'));
    await t.pumpAndSettle();
    expect(find.textContaining('Escuchando'), findsOneWidget);
    await t.enterText(find.byType(TextField).first, 'vestido rojo para fiesta');
    await t.tap(find.text('Buscar'));
    await t.pumpAndSettle();
    expect(find.textContaining('coincidencia'), findsOneWidget);
  });

  testWidgets('voz denegada mantiene escritura', (t) async {
    SharedPreferences.setMockInitialValues({});
    final api = ApiClient(httpClient: mockIa(), sesiones: SessionManager());
    final control = ControlVoz(
      reconocedor: ReconocedorVozFake(),
      permisoMock: () async => PermissionStatus.denied,
    );
    await t.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: BuscadorConVoz(
            servicioIa: IaService(api: api),
            servicioCatalogo: CatalogoService(api: api),
            control: control,
          ),
        ),
      ),
    ));
    await t.pumpAndSettle();
    await t.tap(find.byTooltip('Buscar por voz'));
    await t.pumpAndSettle();
    expect(find.textContaining('denegado'), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
  });
}
