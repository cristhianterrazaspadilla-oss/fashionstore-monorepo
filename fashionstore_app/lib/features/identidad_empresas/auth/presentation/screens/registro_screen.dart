import 'package:flutter/material.dart';
import '../../../services/auth_service.dart';
import '../../../../../core/ui/colores.dart';

class RegistroScreen extends StatefulWidget {
  const RegistroScreen({super.key});

  @override
  State<RegistroScreen> createState() => _RegistroScreenState();
}

class _RegistroScreenState extends State<RegistroScreen> {
  final _formKey = GlobalKey<FormState>();
  final _authService = AuthService();

  final _nombresController = TextEditingController();
  final _apellidosController = TextEditingController();
  final _correoController = TextEditingController();
  final _contraseniaController = TextEditingController();
  final _telefonoController = TextEditingController();
  final _direccionController = TextEditingController();

  bool _cargando = false;
  String? _mensajeError;

  @override
  void dispose() {
    _nombresController.dispose();
    _apellidosController.dispose();
    _correoController.dispose();
    _contraseniaController.dispose();
    _telefonoController.dispose();
    _direccionController.dispose();
    super.dispose();
  }

  void _registrarCliente() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _cargando = true;
      _mensajeError = null;
    });

    try {
      final cliente = await _authService.registrarCliente(
        nombres: _nombresController.text.trim(),
        apellidos: _apellidosController.text.trim(),
        correoElectronico: _correoController.text.trim(),
        contrasenia: _contraseniaController.text,
        telefono: _telefonoController.text.trim(),
        direccionReferencia: _direccionController.text.trim(),
      );

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              '¡Bienvenido ${cliente.nombreCompleto}! Cuenta creada exitosamente.'),
          backgroundColor: ColoresFS.success,
        ),
      );
      Navigator.pop(context);
    } catch (e) {
      setState(() {
        _mensajeError = e.toString().replaceAll('Exception: ', '');
      });
    } finally {
      if (mounted) {
        setState(() {
          _cargando = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Crear Cuenta'),
        elevation: 0,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Únete a FashionStore',
                  style: TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      color: ColoresFS.ink),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Crea tu cuenta para reservar prendas y recogerlas en tienda.',
                  style: TextStyle(color: ColoresFS.textMuted),
                ),
                const SizedBox(height: 24),
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
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _nombresController,
                        decoration: const InputDecoration(
                            labelText: 'Nombres *',
                            border: OutlineInputBorder()),
                        validator: (v) =>
                            v == null || v.isEmpty ? 'Requerido' : null,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextFormField(
                        controller: _apellidosController,
                        decoration: const InputDecoration(
                            labelText: 'Apellidos *',
                            border: OutlineInputBorder()),
                        validator: (v) =>
                            v == null || v.isEmpty ? 'Requerido' : null,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _correoController,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(
                      labelText: 'Correo Electrónico *',
                      border: OutlineInputBorder()),
                  validator: (v) =>
                      v == null || !v.contains('@') ? 'Correo no válido' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _contraseniaController,
                  obscureText: true,
                  decoration: const InputDecoration(
                      labelText: 'Contraseña * (mínimo 6 caracteres)',
                      border: OutlineInputBorder()),
                  validator: (v) =>
                      v == null || v.length < 6 ? 'Mínimo 6 caracteres' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _telefonoController,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(
                      labelText: 'Teléfono / Celular',
                      border: OutlineInputBorder()),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _direccionController,
                  decoration: const InputDecoration(
                      labelText: 'Dirección de Referencia',
                      border: OutlineInputBorder()),
                ),
                const SizedBox(height: 24),
                ElevatedButton(
                  onPressed: _cargando ? null : _registrarCliente,
                  child: _cargando
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white),
                        )
                      : const Text('Registrarse',
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
