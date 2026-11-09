import 'package:fashionstore_movil/core/config/api_config.dart';
import 'package:fashionstore_movil/core/session/puerta_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('la app generada usa Render como backend predeterminado', () {
    expect(
      ApiConfig.baseUrl,
      'https://fashionstore-backend-natk.onrender.com/api/v1',
    );
  });

  testWidgets('una acción autenticada continúa sin abrir login',
      (tester) async {
    var aperturasLogin = 0;
    var ejecuciones = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              final permitido = await PuertaAuth.exigir(
                context,
                comprobarSesion: () async => true,
                abrirLogin: (_, __) async {
                  aperturasLogin++;
                  return true;
                },
              );
              if (permitido) ejecuciones++;
            },
            child: const Text('Acción protegida'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Acción protegida'));
    await tester.pump();
    expect(aperturasLogin, 0);
    expect(ejecuciones, 1);
  });

  testWidgets('cancelar login no ejecuta la acción protegida', (tester) async {
    var ejecuciones = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              final permitido = await PuertaAuth.exigir(
                context,
                comprobarSesion: () async => false,
                abrirLogin: (_, __) async => false,
              );
              if (permitido) ejecuciones++;
            },
            child: const Text('Acción protegida'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Acción protegida'));
    await tester.pump();
    expect(ejecuciones, 0);
  });

  testWidgets('login correcto retoma la acción exactamente una vez',
      (tester) async {
    var aperturasLogin = 0;
    var ejecuciones = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              final permitido = await PuertaAuth.exigir(
                context,
                motivo: 'Inicia sesión para continuar.',
                comprobarSesion: () async => false,
                abrirLogin: (_, motivo) async {
                  aperturasLogin++;
                  expect(motivo, 'Inicia sesión para continuar.');
                  return true;
                },
              );
              if (permitido) ejecuciones++;
            },
            child: const Text('Acción protegida'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Acción protegida'));
    await tester.pump();
    expect(aperturasLogin, 1);
    expect(ejecuciones, 1);
  });
}
