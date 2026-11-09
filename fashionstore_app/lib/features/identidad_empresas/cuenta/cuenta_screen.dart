import 'package:flutter/material.dart';

import '../../../core/config/api_config.dart';
import '../../../core/network/api_client.dart';
import '../../../core/session/session_manager.dart';
import '../../../core/ui/colores.dart';
import '../../ventas_pagos/caja/caja_offline_screen.dart';
import '../../ventas_pagos/services/caja_service.dart';
import '../../posventa/posventa_screen.dart';
import '../models/suscripcion_model.dart';
import '../models/usuario_model.dart';
import '../services/auth_service.dart';
import '../services/suscripcion_service.dart';
import '../auth/presentation/screens/login_screen.dart';

/// Perfil + Suscripción y Capacidades + Acceso a Caja Móvil + Cierre de sesión.
/// En modo invitado muestra acceso a login/registro sin bloquear el catálogo.
class CuentaScreen extends StatefulWidget {
  final VoidCallback onSesionCerrada;
  final VoidCallback? onSesionIniciada;
  final SuscripcionService? servicioSuscripcion;

  const CuentaScreen({
    super.key,
    required this.onSesionCerrada,
    this.onSesionIniciada,
    this.servicioSuscripcion,
  });

  @override
  State<CuentaScreen> createState() => _CuentaScreenState();
}

class _CuentaScreenState extends State<CuentaScreen> {
  final _auth = AuthService();
  late final SuscripcionService _suscripcionSrv;
  ClientePerfilModel? _usuario;
  SuscripcionEmpresaModel? _suscripcion;
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    _suscripcionSrv = widget.servicioSuscripcion ?? SuscripcionService();
    _cargar();
  }

  Future<void> _cargar() async {
    final s = await _auth.sesionActual();
    SuscripcionEmpresaModel? plan;
    if (s?.usuario != null) {
      try {
        plan = await _suscripcionSrv.consultarMiPlan(empresaId: s?.usuario.empresaId);
      } catch (_) {
        // En caso de usuario sin empresa o sin red, se mantiene defensivo
      }
    }

    if (mounted) {
      setState(() {
        _usuario = s?.usuario;
        _suscripcion = plan;
        _cargando = false;
      });
    }
  }

  Future<void> _salir() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cerrar sesión'),
        content: const Text('¿Deseas salir de tu cuenta en este equipo?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Volver'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Cerrar sesión'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await _auth.cerrarSesion();
    widget.onSesionCerrada();
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_usuario == null) {
      // Modo invitado: catálogo público + puerta de login solo aquí.
      return SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 90),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Explora sin cuenta',
                        style: TextStyle(fontWeight: FontWeight.w800)),
                    SizedBox(height: 6),
                    Text(
                      'El catálogo es público. Inicia sesión solo cuando quieras comprar, reservar o probar prendas.',
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 10),
            ElevatedButton.icon(
              onPressed: () async {
                final ok = await Navigator.push<bool>(
                  context,
                  MaterialPageRoute(
                    builder: (loginContext) => Scaffold(
                      appBar: AppBar(title: const Text('Inicia sesión')),
                      body: LoginScreen(
                        onLoginOk: () => Navigator.pop(loginContext, true),
                      ),
                    ),
                  ),
                );
                if (ok == true && context.mounted) {
                  await _cargar();
                  widget.onSesionIniciada?.call();
                } else {
                  await _cargar();
                }
              },
              icon: const Icon(Icons.login_outlined),
              label: const Text('Iniciar sesión'),
            ),
            const SizedBox(height: 10),
            Card(
              child: ListTile(
                leading: const Icon(Icons.assignment_return_outlined, color: ColoresFS.ink),
                title: const Text('Posventa y Devoluciones',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                subtitle: const Text('Inicia sesión para consultar tus devoluciones, cambios y saldo a favor.'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () async {
                  final ok = await Navigator.push<bool>(
                    context,
                    MaterialPageRoute(
                      builder: (loginContext) => Scaffold(
                        appBar: AppBar(title: const Text('Inicia sesión')),
                        body: LoginScreen(
                          onLoginOk: () => Navigator.pop(loginContext, true),
                        ),
                      ),
                    ),
                  );
                  if (ok == true && context.mounted) {
                    await _cargar();
                    widget.onSesionIniciada?.call();
                  }
                },
              ),
            ),
            const SizedBox(height: 10),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Conexión',
                        style: TextStyle(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 6),
                    SelectableText(
                      ApiConfig.baseUrl,
                      style: TextStyle(color: Colors.grey.shade800),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      );
    }

    final rol = _usuario?.rol.toUpperCase() ?? 'CLIENTE';
    final esPersonal = rol == 'CAJERO' ||
        rol == 'ADMIN' ||
        rol == 'ADMINISTRADOR' ||
        rol == 'ENCARGADO' ||
        rol == 'GERENTE';

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 90),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Perfil de Usuario
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 26,
                    child: Text(
                      (_usuario?.nombreCompleto.isNotEmpty ?? false)
                          ? _usuario!.nombreCompleto[0].toUpperCase()
                          : '?',
                      style: const TextStyle(
                          fontSize: 24, fontWeight: FontWeight.w800),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _usuario?.nombreCompleto ?? 'Cliente',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 17),
                        ),
                        Text(
                          _usuario?.correoElectronico ?? '',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                        const SizedBox(height: 4),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: esPersonal ? Colors.deepPurple.shade50 : Colors.blue.shade50,
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(
                              color: esPersonal ? Colors.deepPurple.shade200 : Colors.blue.shade200,
                            ),
                          ),
                          child: Text(
                            'Rol: $rol',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: esPersonal ? Colors.deepPurple.shade900 : Colors.blue.shade900,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),

          // Capacidades y Plan de la Empresa
          if (_suscripcion != null) ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.workspace_premium, color: ColoresFS.brassStrong),
                        const SizedBox(width: 8),
                        Text(
                          _suscripcion!.planNombre,
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                        ),
                        const Spacer(),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.green.shade50,
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: Colors.green.shade300),
                          ),
                          child: Text(
                            _suscripcion!.estadoEfectivo,
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              color: Colors.green.shade900,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Límite: ${_suscripcion!.sucursalesActivas} / ${_suscripcion!.limiteSucursales} sucursal(es) activas',
                      style: TextStyle(color: Colors.grey.shade700, fontSize: 13),
                    ),
                    const SizedBox(height: 8),
                    const Text('Capacidades habilitadas:',
                        style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      children: [
                        for (final cap in _suscripcion!.capacidades)
                          Chip(
                            label: Text(cap, style: const TextStyle(fontSize: 10)),
                            padding: EdgeInsets.zero,
                            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 10),
          ],

          // Acceso a Posventa y Garantías (CU08, CU09, CU20, CU27)
          Card(
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
              side: BorderSide(color: ColoresFS.ink.withValues(alpha: 0.2)),
            ),
            child: ListTile(
              key: const Key('btn_posventa_garantias'),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              leading: CircleAvatar(
                backgroundColor: ColoresFS.ink.withValues(alpha: 0.08),
                child: const Icon(Icons.assignment_return_outlined, color: ColoresFS.ink),
              ),
              title: const Text(
                'Posventa y Garantías',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
              ),
              subtitle: const Text(
                'Mis devoluciones, cambios, saldo a favor y reembolsos (CU08, CU09, CU20, CU27).',
                style: TextStyle(fontSize: 13),
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => const PosventaScreen(),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 10),

          // Módulo de Caja Móvil para Personal Autorizado
          if (esPersonal) ...[
            Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
                side: BorderSide(color: Colors.deepPurple.shade200),
              ),
              color: Colors.deepPurple.shade50.withValues(alpha: 0.5),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.point_of_sale, color: Colors.deepPurple),
                        SizedBox(width: 8),
                        Text(
                          'Caja Móvil',
                          style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'Habilita turnos con cupos, registra ventas en efectivo sin red con comprobante inmediato y sincroniza transacciones.',
                      style: TextStyle(fontSize: 13),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.deepPurple,
                          foregroundColor: Colors.white,
                        ),
                        onPressed: () {
                          final sessionMgr = SessionManager();
                          final api = ApiClient(sesiones: sessionMgr);
                          final cajaSrv = CajaService(api: api, sesiones: sessionMgr);
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => CajaOfflineScreen(servicioCaja: cajaSrv),
                            ),
                          );
                        },
                        icon: const Icon(Icons.store),
                        label: const Text('Abrir Módulo de Caja'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 10),
          ],

          // Tarjeta de Conexión
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Conexión',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 6),
                  SelectableText(
                    ApiConfig.baseUrl,
                    style: TextStyle(color: Colors.grey.shade800),
                  ),
                  Text(
                    'Dirección ${ApiConfig.origenDescripcion}. Si cambias de red (emulador, navegador o teléfono), abre la app con su dirección correspondiente.',
                    style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _salir,
              icon: const Icon(Icons.logout),
              label: const Text('Cerrar sesión'),
            ),
          ),
        ],
      ),
    );
  }
}
