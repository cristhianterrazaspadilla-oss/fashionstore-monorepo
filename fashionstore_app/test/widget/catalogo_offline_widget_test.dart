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
import 'package:fashionstore_movil/features/catalogo/catalogo/catalogo_screen.dart';
import 'package:fashionstore_movil/features/catalogo/models/catalogo_snapshot_model.dart';
import 'package:fashionstore_movil/features/catalogo/services/catalogo_service.dart';

Widget _crearApp(Widget child) => MaterialApp(
      home: Scaffold(body: child),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfiNoIsolate;
  });

  group('CU16 & CU03: Catálogo Offline en SQLite', () {
    late LocalDatabaseService storage;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      storage = LocalDatabaseService(dbName: inMemoryDatabasePath);
    });

    tearDown(() async {
      await storage.close();
    });

    testWidgets('CU16: sin red y sin snapshot muestra pantalla de aviso con botón de descarga', (tester) async {
      // Mock HTTP que simula fallo de conexión
      final mock = MockClient((_) async => throw Exception('Connection refused'));
      final api = ApiClient(httpClient: mock, sesiones: SessionManager());
      final servicio = CatalogoService(api: api, storage: storage);

      await tester.pumpWidget(_crearApp(CatalogoScreen(servicio: servicio)));
      await tester.pumpAndSettle();

      expect(find.text('Catálogo no descargado'), findsOneWidget);
      expect(
        find.textContaining('No se encontró una copia local en este dispositivo'),
        findsOneWidget,
      );
      expect(find.text('Descargar catálogo al conectar'), findsOneWidget);
      expect(find.text('Reintentar conexión'), findsOneWidget);
    });

    testWidgets('CU16: sin red pero con snapshot muestra badge de copia local, versión y stock conocido', (tester) async {
      // Guardar snapshot previo en SQLite
      final snapshot = CatalogoSnapshotModel(
        empresaId: 'empresa-fs',
        empresaCodigo: 'fashionstore',
        catalogoVersion: 3,
        generadoEn: '2026-11-01T10:00:00-04:00',
        guardadoLocalEn: '2026-11-01T11:00:00-04:00',
        ambitoSucursales: ['sucursal-central'],
        productos: [
          CatalogoProductoLocal(
            id: 'prod-vestido-1',
            empresaId: 'empresa-fs',
            nombre: 'Vestido de Gala Primavera',
            descripcion: 'Vestido elegante con corte sirena',
            precioBaseBob: '249.99',
            imagenesJson: '[]',
            variantes: [
              CatalogoVarianteLocal(
                id: 'var-1',
                productoId: 'prod-vestido-1',
                sku: 'VES-PRIM-M',
                tallaId: 'talla-m',
                talla: 'M',
                colorId: 'color-rojo',
                color: 'Rojo Carmesí',
                precioBob: '249.99',
                disponibilidad: 8,
                disponibilidadPorSucursalJson: jsonEncode([
                  {'sucursal_id': 'sucursal-central', 'nombre': 'Central', 'stock': 8}
                ]),
              ),
            ],
          ),
        ],
        colores: [
          CatalogoColorLocal(
            id: 'color-rojo',
            empresaId: 'empresa-fs',
            nombre: 'Rojo Carmesí',
            componentesJson: '[]',
          ),
        ],
        promociones: [
          CatalogoPromocionLocal(
            id: 'promo-1',
            empresaId: 'empresa-fs',
            tipo: 'DESCUENTO_PORCENTAJE',
            valor: '15.00',
            cantidadMinima: 3,
            vigenteDesde: '2026-11-01T00:00:00-04:00',
            vigenteHasta: '2026-11-30T23:59:59-04:00',
            varianteIdsJson: jsonEncode(['var-1']),
          ),
        ],
      );

      await storage.guardarSnapshot(snapshot: snapshot);

      // Simular que no hay conexión de red
      final mock = MockClient((_) async => throw Exception('Red no disponible'));
      final api = ApiClient(httpClient: mock, sesiones: SessionManager());
      final servicio = CatalogoService(api: api, storage: storage);

      await tester.pumpWidget(_crearApp(CatalogoScreen(servicio: servicio)));
      await tester.pumpAndSettle();

      // 1. Debe mostrar el badge de copia local con fecha y versión
      expect(find.textContaining('Copia local'), findsOneWidget);
      expect(find.textContaining('Versión 3'), findsOneWidget);

      // 2. Debe mostrar la prenda encontrada en la base local SQLite
      expect(find.text('Vestido de Gala Primavera'), findsOneWidget);
      expect(find.textContaining('249'), findsWidgets);

      // 3. Debe indicar "Disponibilidad conocida" (no stock absoluto)
      expect(find.text('Disponibilidad conocida'), findsOneWidget);
    });

    testWidgets('CU03: botón de descarga offline obtiene catálogo del backend y persiste en SQLite', (tester) async {
      final mock = MockClient((request) async {
        if (request.url.path.contains('/catalogo/descarga')) {
          return http.Response(
            jsonEncode({
              'empresa_id': 'emp-sync',
              'empresa_codigo': 'fashionstore',
              'catalogo_version': 5,
              'generado_en': '2026-11-01T12:00:00-04:00',
              'ambito_sucursales': ['suc-1'],
              'productos': [
                {
                  'id': 'p-descargado',
                  'empresa_id': 'emp-sync',
                  'nombre': 'Blusa Seda Descargada',
                  'descripcion': 'Blusa fresca',
                  'precio_base_bob': '120.00',
                  'imagenes': [],
                  'variantes': [
                    {
                      'id': 'v-desc',
                      'producto_id': 'p-descargado',
                      'sku': 'BLU-SED',
                      'talla_id': 't-s',
                      'talla': 'S',
                      'color_id': 'c-blanco',
                      'color': 'Blanco',
                      'precio_bob': '120.00',
                      'disponibilidad': 10,
                      'disponibilidad_por_sucursal': [],
                    }
                  ],
                }
              ],
              'colores': [],
              'promociones': [],
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.contains('/catalogo/filtros-opciones')) {
          return http.Response(
            jsonEncode({'categorias': [], 'generos': [], 'tallas': [], 'colores': []}),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        if (request.url.path.contains('/productos')) {
          return http.Response(
            jsonEncode([
              {
                'id': 'p-online',
                'nombre': 'Blusa Online',
                'precio_base': 120.0,
                'imagenes': [],
              }
            ]),
            200,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('Not found', 404);
      });

      final api = ApiClient(httpClient: mock, sesiones: SessionManager());
      final servicio = CatalogoService(api: api, storage: storage);

      await tester.pumpWidget(_crearApp(CatalogoScreen(servicio: servicio)));
      await tester.pumpAndSettle();

      // Debe mostrar botón de descarga offline
      final btnDescarga = find.text('Descargar catálogo offline');
      expect(btnDescarga, findsOneWidget);

      await tester.tap(btnDescarga);
      await tester.pumpAndSettle();

      // Verificar que el snapshot quedó activo en SQLite
      final activo = await storage.obtenerSnapshotActivo('fashionstore');
      expect(activo, isNotNull);
      expect(activo!.catalogoVersion, 5);
      expect(activo.empresaCodigo, 'fashionstore');
    });
  });
}
