import 'dart:convert';

import 'package:fashionstore_movil/features/catalogo/models/catalogo_model.dart';
import 'package:fashionstore_movil/core/network/api_client.dart';
import 'package:fashionstore_movil/features/catalogo/services/catalogo_service.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:fashionstore_movil/features/catalogo/catalogo/catalogo_screen.dart';
import 'package:fashionstore_movil/features/catalogo/catalogo/producto_detalle_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> _productoJson(String id, String nombre) => {
      'id': id,
      'categoria_id': null,
      'nombre': nombre,
      'descripcion': 'Prenda de prueba',
      'genero': 'MUJER',
      'marca': 'FashionStore',
      'precio_base': '120.00',
      'activo': true,
      'imagenes': [],
      'temporada_ids': [],
      'coleccion_ids': [],
    };

MockClient _clienteSimulado({required List<Map<String, dynamic>> productos}) {
  return MockClient((req) async {
    final path = req.url.path;
    if (req.method == 'GET' && path.endsWith('/filtros-opciones')) {
      return http.Response(
        jsonEncode({
          'categorias': [],
          'tallas': [],
          'colores': [],
          'temporadas': [],
          'colecciones': [],
          'generos': [],
          'marcas': [],
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (req.method == 'GET' && path.endsWith('/productos')) {
      return http.Response(
        jsonEncode(productos),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    return http.Response('No encontrado', 404);
  });
}

CatalogoScreen _pantalla(MockClient mock) => CatalogoScreen(
      servicio: CatalogoService(
          api: ApiClient(httpClient: mock, sesiones: SessionManager())),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('Catálogo muestra carga inicial', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: CatalogoScreen()));
    expect(find.text('Buscando prendas…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsWidgets);
  });

  testWidgets('Catálogo muestra prendas simuladas', (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: _pantalla(_clienteSimulado(productos: [
      _productoJson('p-1', 'Camisa Clásica'),
      _productoJson('p-2', 'Pantalón Recto'),
    ])))));
    await tester.pumpAndSettle();

    expect(find.text('Camisa Clásica'), findsOneWidget);
    expect(find.text('Pantalón Recto'), findsOneWidget);
  });

  testWidgets('Catálogo vacío ofrece quitar filtros', (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: _pantalla(_clienteSimulado(productos: [])))));
    await tester.pumpAndSettle();

    expect(find.text('Sin resultados'), findsOneWidget);
    expect(find.text('Quitar filtros'), findsOneWidget);
  });

  testWidgets(
      'Detalle muestra botón Probar con realidad aumentada habilitado cuando hay imagen compatible',
      (tester) async {
    final prodJson = _productoJson('p-1', 'Camisa Lino');
    prodJson['imagenes'] = [
      {
        'id': 'img-1',
        'enlace_imagen': 'https://images.example.com/lino.webp',
        'es_principal': true,
        'orden': 1,
      }
    ];
    final producto = Producto.fromJson(prodJson);

    final mock = MockClient((req) async {
      final path = req.url.path;
      if (path.endsWith('/variantes')) {
        return http.Response(
          jsonEncode([
            {
              'id': 'v-1',
              'producto_id': 'p-1',
              'sku': 'LIN-M',
              'talla': 'M',
              'color': 'Blanco',
              'precio': '150.00',
              'activa': true,
            }
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.endsWith('/disponibilidad')) {
        return http.Response('[]', 200,
            headers: {'content-type': 'application/json'});
      }
      return http.Response('Not found', 404);
    });

    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final catServicio = CatalogoService(api: api);

    await tester.pumpWidget(
      MaterialApp(
        home: ProductoDetalleScreen(
          producto: producto,
          servicio: catServicio,
        ),
      ),
    );
    await tester.pumpAndSettle();

    final btn = find.text('Probar con realidad aumentada');
    expect(btn, findsOneWidget);
    final elevatedBtn = tester.widget<ElevatedButton>(
      find.ancestor(of: btn, matching: find.byType(ElevatedButton)),
    );
    expect(elevatedBtn.onPressed, isNotNull);
  });

  testWidgets(
      'Detalle deshabilita botón y explica cuando no hay imagen compatible',
      (tester) async {
    final prodJson = _productoJson('p-2', 'Prenda Sin Foto');
    prodJson['imagenes'] = [];
    final producto = Producto.fromJson(prodJson);

    final mock = MockClient((req) async {
      final path = req.url.path;
      if (path.endsWith('/variantes')) {
        return http.Response(
          jsonEncode([
            {
              'id': 'v-2',
              'producto_id': 'p-2',
              'sku': 'NOFOTO-S',
              'talla': 'S',
              'color': 'Negro',
              'precio': '80.00',
              'activa': true,
            }
          ]),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (path.endsWith('/disponibilidad')) {
        return http.Response('[]', 200,
            headers: {'content-type': 'application/json'});
      }
      return http.Response('Not found', 404);
    });

    final api = ApiClient(httpClient: mock, sesiones: SessionManager());
    final catServicio = CatalogoService(api: api);

    await tester.pumpWidget(
      MaterialApp(
        home: ProductoDetalleScreen(
          producto: producto,
          servicio: catServicio,
        ),
      ),
    );
    await tester.pumpAndSettle();

    final btn = find.text('Probar con realidad aumentada');
    expect(btn, findsOneWidget);
    final elevatedBtn = tester.widget<ElevatedButton>(
      find.ancestor(of: btn, matching: find.byType(ElevatedButton)),
    );
    expect(elevatedBtn.onPressed, isNull);
    expect(
      find.text(
          'Esta prenda todavía no tiene una imagen compatible con el probador.'),
      findsOneWidget,
    );
  });
}
