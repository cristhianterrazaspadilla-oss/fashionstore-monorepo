import 'package:flutter/material.dart';

import '../../features/identidad_empresas/services/auth_service.dart';
import '../../features/identidad_empresas/auth/presentation/screens/login_screen.dart';

/// Puerta de autenticación para acciones protegidas (corrección final Ciclo 3).
///
/// El catálogo es público (backend sin auth en GET /productos, /variantes y
/// disponibilidad). La autenticación se exige únicamente al intentar acciones
/// protegidas: carrito, checkout, reservas, pedidos, probador (token Decart),
/// recomendaciones personalizadas o cualquier POST autenticado.
///
/// Uso: `if (!await PuertaAuth.exigir(context)) return;`
/// Si no hay sesión, abre Login y devuelve true solo cuando el login
/// completa. Nunca fuerza login para navegar o ver el catálogo.
class PuertaAuth {
  static Future<bool> haySesion() => AuthService().estaAutenticado();

  static Future<bool> exigir(
    BuildContext context, {
    String? motivo,
    Future<bool> Function()? comprobarSesion,
    Future<bool?> Function(BuildContext context, String? motivo)? abrirLogin,
  }) async {
    final ok = await (comprobarSesion?.call() ?? haySesion());
    if (ok || !context.mounted) return ok;
    if (abrirLogin != null) {
      return await abrirLogin(context, motivo) == true;
    }
    final entro = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => _LoginPuerta(motivo: motivo),
      ),
    );
    return entro == true;
  }
}

/// Envoltorio del Login que devuelve true al completar y muestra el motivo.
class _LoginPuerta extends StatelessWidget {
  final String? motivo;
  const _LoginPuerta({this.motivo});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Inicia sesión')),
      body: Column(
        children: [
          if (motivo != null && motivo!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    children: [
                      const Icon(Icons.lock_outline),
                      const SizedBox(width: 10),
                      Expanded(child: Text(motivo!)),
                    ],
                  ),
                ),
              ),
            ),
          Expanded(
            child: LoginScreen(
              onLoginOk: () {
                Navigator.pop(context, true);
              },
            ),
          ),
        ],
      ),
    );
  }
}
