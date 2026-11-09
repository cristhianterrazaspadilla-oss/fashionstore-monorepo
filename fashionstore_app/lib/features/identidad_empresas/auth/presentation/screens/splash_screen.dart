import 'package:flutter/material.dart';

import '../../../services/auth_service.dart';

/// Puerta de sesión persistente: decide Home o Login sin parpadeos.
class SplashScreen extends StatefulWidget {
  final void Function(bool tieneSesion) onDecidido;
  const SplashScreen({super.key, required this.onDecidido});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _decidir();
  }

  Future<void> _decidir() async {
    await Future.delayed(const Duration(milliseconds: 350));
    final ok = await AuthService().estaAutenticado();
    if (mounted) widget.onDecidido(ok);
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.shopping_bag_outlined,
                size: 64, color: Color(0xFF1F1B2D)),
            SizedBox(height: 12),
            Text('FashionStore',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
            SizedBox(height: 8),
            CircularProgressIndicator(),
          ],
        ),
      ),
    );
  }
}
