import 'package:flutter/material.dart';
import 'package:flutter_stripe/flutter_stripe.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'core/config/stripe_config.dart';
import 'core/network/api_client.dart';
import 'features/identidad_empresas/services/auth_service.dart';
import 'core/session/sesion_expirada.dart';
import 'core/ui/tema.dart';
import 'features/identidad_empresas/auth/presentation/screens/splash_screen.dart';
import 'features/experiencia_cliente/home/home_screen.dart';
import 'features/posventa/posventa_screen.dart';

/// Clave global del ScaffoldMessenger: permite mostrar el aviso de sesión
/// vencida sin depender de un BuildContext que pueda estar desmontado.
final GlobalKey<ScaffoldMessengerState> fsScaffoldMessengerKey =
    GlobalKey<ScaffoldMessengerState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('es');
  // Stripe Test como único pago: clave publicable por entorno. Sin clave, la
  // app funciona salvo el pago, que explica cómo configurarla.
  if (StripeConfig.estaConfigurada) {
    Stripe.publishableKey = StripeConfig.publishableKey;
    await Stripe.instance.applySettings();
  }
  runApp(const FashionStoreApp());
}

class FashionStoreApp extends StatefulWidget {
  const FashionStoreApp({super.key});

  @override
  State<FashionStoreApp> createState() => _FashionStoreAppState();
}

class _FashionStoreAppState extends State<FashionStoreApp> {
  bool? _tieneSesion;
  int _generacion = 0;
  final ManejadorSesionExpirada _manejador401 = ManejadorSesionExpirada();

  @override
  void initState() {
    super.initState();
    // Cierre de sesión controlado ante 401 del servidor.
    ApiClient.onNoAutorizadoGlobal = _alRecibir401Global;
  }

  @override
  void dispose() {
    if (identical(ApiClient.onNoAutorizadoGlobal, _alRecibir401Global)) {
      ApiClient.onNoAutorizadoGlobal = null;
    }
    super.dispose();
  }

  /// Gancho síncrono del ApiClient: delega al manejador con protección
  /// contra ráfagas (un aviso, una limpieza, navegación segura).
  /// En modo invitado (catálogo público) el 401 solo limpia la sesión y
  /// avisa; la puerta de auth (`PuertaAuth`) pide login únicamente al
  /// intentar la acción protegida que lo provocó.
  void _alRecibir401Global() {
    _manejador401.manejar(
      limpiarSesion: AuthService().cerrarSesion,
      mostrarAviso: () {
        fsScaffoldMessengerKey.currentState?.showSnackBar(
          const SnackBar(
            content: Text('Tu sesión venció. Vuelve a iniciar sesión.'),
          ),
        );
      },
      irALogin: () {
        if (!mounted) return;
        setState(() {
          _tieneSesion = false;
          _generacion++;
        });
      },
    );
  }

  void _irA(bool ok) => setState(() {
        _tieneSesion = ok;
        _generacion++;
      });

  void _sesionIniciada() => setState(() => _tieneSesion = true);

  @override
  Widget build(BuildContext context) {
    // Corrección final: catálogo público sin iniciar sesión. Tanto con
    // sesión como en modo invitado se entra a Home; la autenticación se
    // exige solo en acciones protegidas vía PuertaAuth. El 401 global ya
    // no expulsa al login: solo limpia y avisa.
    return MaterialApp(
      title: 'FashionStore',
      debugShowCheckedModeBanner: false,
      theme: temaFashionStore(),
      scaffoldMessengerKey: fsScaffoldMessengerKey,
      home: _tieneSesion == null
          ? SplashScreen(onDecidido: _irA)
          : HomeScreen(
              key: ValueKey('home-$_generacion'),
              onSesionCerrada: () => _irA(false),
              onSesionIniciada: _sesionIniciada,
            ),
      routes: {
        '/posventa': (_) => const PosventaScreen(),
      },
    );
  }
}
