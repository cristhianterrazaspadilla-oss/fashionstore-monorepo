import 'package:fashionstore_movil/features/identidad_empresas/models/usuario_model.dart';
import 'package:fashionstore_movil/core/network/api_exception.dart';
import 'package:fashionstore_movil/core/session/session_manager.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

ClientePerfilModel _usuarioPrueba() => ClientePerfilModel(
      id: 'cliente-1',
      usuarioId: 'usuario-1',
      nombres: 'Ana',
      apellidos: 'Pérez',
      nombreCompleto: 'Ana Pérez',
      correoElectronico: 'ana@test.com',
      rol: 'CLIENTE',
      estado: 'ACTIVO',
      preferencias: const {},
      creadoEn: DateTime.utc(2026, 1, 1),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Sesión persiste y expira a las 24 h', () async {
    SharedPreferences.setMockInitialValues({});
    final mgr = SessionManager();
    final base = DateTime(2026, 9, 15, 10, 0, 0);
    await mgr.guardar(token: 'tok-123', usuario: _usuarioPrueba(), ahora: base);

    final valida =
        await mgr.leerValida(ahora: base.add(const Duration(hours: 23)));
    expect(valida, isNotNull);
    expect(valida!.token, 'tok-123');

    final vencida =
        await mgr.leerValida(ahora: base.add(const Duration(hours: 25)));
    expect(vencida, isNull);

    // Después de expirar se limpió.
    final otra = await mgr.leerValida(ahora: base);
    expect(otra, isNull);
  });

  test('Traducción de errores por código', () {
    expect(ApiException.traducir(400), contains('datos'));
    expect(ApiException.traducir(401), contains('sesión'));
    expect(ApiException.traducir(403), contains('permiso'));
    expect(ApiException.traducir(404), contains('No encontramos'));
    expect(ApiException.traducir(422), contains('válidos'));
    expect(
      ApiException.traducir(409, 'Stock insuficiente en sucursal'),
      contains('disponibilidad'),
    );
    expect(
      ApiException.desdeRespuesta(409, {'detail': 'x'}).statusCode,
      409,
    );
  });
}
