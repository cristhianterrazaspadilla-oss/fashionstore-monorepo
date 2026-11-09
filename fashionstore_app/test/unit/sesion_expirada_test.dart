import 'package:fashionstore_movil/core/session/sesion_expirada.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('varios 401 concurrentes generan un solo aviso y una limpieza',
      () async {
    final manejador = ManejadorSesionExpirada(
      ventanaAviso: const Duration(milliseconds: 50),
    );
    var limpiezas = 0;
    var avisos = 0;
    var logins = 0;

    Future<void> limpiar() async {
      limpiezas++;
      await Future.delayed(const Duration(milliseconds: 10));
    }

    for (var i = 0; i < 5; i++) {
      manejador.manejar(
        limpiarSesion: limpiar,
        mostrarAviso: () => avisos++,
        irALogin: () => logins++,
      );
    }

    await Future.delayed(const Duration(milliseconds: 100));
    expect(limpiezas, 1);
    expect(avisos, 1);
    expect(logins, 1);
  });

  test('tras la ventana se permite un nuevo aviso', () async {
    final manejador = ManejadorSesionExpirada(
      ventanaAviso: const Duration(milliseconds: 30),
    );
    var avisos = 0;
    void manejar() => manejador.manejar(
          limpiarSesion: () async {},
          mostrarAviso: () => avisos++,
          irALogin: () {},
        );

    manejar();
    await Future.delayed(const Duration(milliseconds: 80));
    manejar();
    await Future.delayed(const Duration(milliseconds: 80));

    expect(avisos, 2);
  });

  test('fallos en callbacks no lanzan excepciones', () async {
    final manejador = ManejadorSesionExpirada(
      ventanaAviso: const Duration(milliseconds: 20),
    );
    manejador.manejar(
      limpiarSesion: () => throw Exception('sin almacenamiento'),
      mostrarAviso: () => throw Exception('sin scaffold'),
      irALogin: () => throw Exception('desmontado'),
    );
    await Future.delayed(const Duration(milliseconds: 60));
    // Si llegamos aquí, ninguna excepción escapó del manejador.
    expect(manejador.gestionando, isFalse);
  });
}
