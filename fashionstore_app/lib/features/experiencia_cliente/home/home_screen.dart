// Navegación principal Ciclo 3 — CLIENTE + invitado (máximo 5 destinos).
//
// 1. Catálogo (público, con recomendaciones y voz integradas)
// 2. Carrito de compra (protegido: exige login al intentar usarlo)
// 3. Pedidos (protegido)
// 4. Reservas (protegido)
// 5. Cuenta (muestra login en modo invitado)
// La bolsa deja de ser pestaña; el probador se abre desde el detalle.
import 'package:flutter/material.dart';

import '../../identidad_empresas/services/auth_service.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../identidad_empresas/auth/presentation/screens/login_screen.dart';
import '../../ventas_pagos/carrito/carrito_screen.dart';
import '../../ventas_pagos/carrito/carrito_store.dart';
import '../../catalogo/catalogo/catalogo_screen.dart';
import '../../identidad_empresas/cuenta/cuenta_screen.dart';
import '../../ventas_pagos/pedidos/pedidos_screen.dart';
import '../../reservas_traslados/reservas/bolsa_store.dart';
import '../../reservas_traslados/reservas/reservas_screen.dart';

class HomeScreen extends StatefulWidget {
  final VoidCallback onSesionCerrada;
  final VoidCallback? onSesionIniciada;
  const HomeScreen(
      {super.key, required this.onSesionCerrada, this.onSesionIniciada});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _indice = 0;
  bool? _tieneSesion;

  @override
  void initState() {
    super.initState();
    _verificarSesion();
  }

  Future<void> _verificarSesion() async {
    final ok = await AuthService().estaAutenticado();
    if (!mounted) return;
    setState(() => _tieneSesion = ok);
    if (ok) {
      CarritoStore.instancia.cargar();
      AuthService.asegurarPushActivo();
    }
  }

  void _irALogin() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => Scaffold(
          appBar: AppBar(title: const Text('Inicia sesión')),
          body: LoginScreen(onLoginOk: () {
            Navigator.pop(context);
          }),
        ),
      ),
    );
    await _verificarSesion();
    if (_tieneSesion == true) {
      widget.onSesionIniciada?.call();
    }
  }

  Future<void> _seleccionarDestino(int indice) async {
    // El login también puede ocurrir desde una acción profunda del
    // catálogo (carrito, bolsa o probador). Revalidar antes de cambiar de
    // pestaña evita conservar el estado visual de invitado hasta reiniciar.
    final ok = await AuthService().estaAutenticado();
    if (!mounted) return;
    setState(() {
      _tieneSesion = ok;
      _indice = indice;
    });
    if (ok) {
      CarritoStore.instancia.cargar();
      widget.onSesionIniciada?.call();
    }
  }

  @override
  Widget build(BuildContext context) {
    final esInvitado = _tieneSesion == false;
    final paginas = [
      const CatalogoScreen(),
      esInvitado
          ? _VistaLoginRequerido(
              titulo: 'Tu carrito te espera',
              detalle:
                  'Inicia sesión para agregar prendas, pagar con Stripe y hacer seguimiento de tu compra.',
              onLogin: _irALogin,
            )
          : const CarritoScreen(),
      esInvitado
          ? _VistaLoginRequerido(
              titulo: 'Tus pedidos están protegidos',
              detalle:
                  'Inicia sesión para ver el seguimiento de tu recojo o delivery.',
              onLogin: _irALogin,
            )
          : const PedidosScreen(),
      esInvitado
          ? _VistaLoginRequerido(
              titulo: 'Tus reservas están protegidas',
              detalle: 'Inicia sesión para apartar prendas y probar en tienda.',
              onLogin: _irALogin,
            )
          : const ReservasScreen(),
      CuentaScreen(
        onSesionCerrada: () async {
          await _verificarSesion();
          widget.onSesionCerrada();
        },
        onSesionIniciada: () async {
          await _verificarSesion();
          widget.onSesionIniciada?.call();
        },
      ),
    ];
    const titulos = [
      'Catálogo',
      'Carrito de compra',
      'Mis pedidos',
      'Mis reservas',
      'Mi cuenta',
    ];
    const subtitulos = [
      'Descubre, prueba y elige',
      'Tu compra digital con Stripe',
      'Seguimiento de recojo y delivery',
      'Aparta para probar en tienda',
      'Tus datos y sesión',
    ];
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(titulos[_indice],
                style: const TextStyle(fontWeight: FontWeight.w800)),
            Text(
              'FashionStore · ${subtitulos[_indice]}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12, color: ColoresFS.textMuted),
            ),
          ],
        ),
      ),
      body: IndexedStack(index: _indice, children: paginas),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _indice,
        onDestinationSelected: _seleccionarDestino,
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.checkroom_outlined),
            selectedIcon: Icon(Icons.checkroom),
            label: 'Catálogo',
          ),
          NavigationDestination(
            icon: AnimatedBuilder(
              animation: CarritoStore.instancia,
              builder: (_, __) {
                final n = CarritoStore.instancia.totalPrendas;
                return Badge(
                  isLabelVisible: n > 0,
                  label: Text('$n'),
                  child: const Icon(Icons.shopping_cart_outlined),
                );
              },
            ),
            label: 'Carrito',
          ),
          const NavigationDestination(
            icon: Icon(Icons.receipt_long_outlined),
            selectedIcon: Icon(Icons.receipt_long),
            label: 'Pedidos',
          ),
          NavigationDestination(
            icon: AnimatedBuilder(
              animation: BolsaStore.instancia,
              builder: (_, __) {
                final n = BolsaStore.instancia.totalPrendas;
                return Badge(
                  isLabelVisible: n > 0,
                  label: Text('$n'),
                  child: const Icon(Icons.shopping_bag_outlined),
                );
              },
            ),
            label: 'Reservas',
          ),
          const NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Cuenta',
          ),
        ],
      ),
    );
  }
}

/// Vista protegida para invitados: explica y ofrece iniciar sesión sin
/// bloquear el catálogo público. Mantiene identidad visual y responsive.
class _VistaLoginRequerido extends StatelessWidget {
  final String titulo;
  final String detalle;
  final VoidCallback onLogin;
  const _VistaLoginRequerido({
    required this.titulo,
    required this.detalle,
    required this.onLogin,
  });

  @override
  Widget build(BuildContext context) {
    return VistaVacia(
      icono: Icons.lock_outline,
      titulo: titulo,
      detalle: '$detalle Puedes seguir explorando el catálogo sin cuenta.',
      accionTexto: 'Iniciar sesión',
      onAccion: onLogin,
    );
  }
}
