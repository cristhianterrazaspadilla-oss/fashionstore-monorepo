import 'package:flutter/material.dart';
import '../../../services/auth_service.dart';
import '../../../../../core/ui/colores.dart';
import 'registro_screen.dart';

class LoginScreen extends StatefulWidget {
  final VoidCallback? onLoginOk;
  const LoginScreen({super.key, this.onLoginOk});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _authService = AuthService();

  final _correoController = TextEditingController();
  final _contraseniaController = TextEditingController();

  bool _cargando = false;
  String? _mensajeError;

  @override
  void dispose() {
    _correoController.dispose();
    _contraseniaController.dispose();
    super.dispose();
  }

  void _iniciarSesion() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _cargando = true;
      _mensajeError = null;
    });

    try {
      final respuesta = await _authService.iniciarSesion(
        correoElectronico: _correoController.text.trim(),
        contrasenia: _contraseniaController.text,
      );

      if (!mounted) return;
      setState(() => _cargando = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('¡Hola de nuevo, ${respuesta.usuario.nombreCompleto}!'),
          backgroundColor: ColoresFS.success,
        ),
      );
      // Debe ser la última operación: el callback normalmente hace pop y
      // desmonta este State. No volver a usar context ni setState después.
      widget.onLoginOk?.call();
      return;
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _mensajeError = e.toString().replaceAll('Exception: ', '');
        _cargando = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Icon(Icons.shopping_bag_outlined,
                      size: 72, color: ColoresFS.brassStrong),
                  const SizedBox(height: 16),
                  const Text(
                    'FashionStore',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1.2,
                        color: ColoresFS.ink),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Inicia sesión para continuar',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: ColoresFS.textMuted),
                  ),
                  const SizedBox(height: 32),
                  if (_mensajeError != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFF1F2),
                        borderRadius:
                            BorderRadius.circular(ColoresFS.radioControl),
                        border: Border.all(color: ColoresFS.danger),
                      ),
                      child: Text(_mensajeError!,
                          style: const TextStyle(color: ColoresFS.danger)),
                    ),
                  TextFormField(
                    controller: _correoController,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                        labelText: 'Correo Electrónico',
                        border: OutlineInputBorder()),
                    validator: (v) =>
                        v == null || v.isEmpty ? 'Ingrese su correo' : null,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _contraseniaController,
                    obscureText: true,
                    decoration: const InputDecoration(
                        labelText: 'Contraseña', border: OutlineInputBorder()),
                    validator: (v) =>
                        v == null || v.isEmpty ? 'Ingrese su contraseña' : null,
                  ),
                  const SizedBox(height: 24),
                  ElevatedButton(
                    onPressed: _cargando ? null : _iniciarSesion,
                    child: _cargando
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white),
                          )
                        : const Text('Iniciar Sesión',
                            style: TextStyle(
                                fontSize: 16, fontWeight: FontWeight.bold)),
                  ),
                  const SizedBox(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Text('¿No tienes cuenta? '),
                      TextButton(
                        onPressed: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                                builder: (context) => const RegistroScreen()),
                          );
                        },
                        child: const Text('Regístrate aquí',
                            style: TextStyle(fontWeight: FontWeight.bold)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
