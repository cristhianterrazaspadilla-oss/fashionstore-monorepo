import 'package:flutter/material.dart';
import '../../core/ui/colores.dart';
import 'models/posventa_models.dart';
import 'services/posventa_service.dart';

/// Pantalla integral de Posventa del Cliente (CU08, CU09, CU20, CU27).
class PosventaScreen extends StatefulWidget {
  final PosventaService? service;

  const PosventaScreen({super.key, this.service});

  @override
  State<PosventaScreen> createState() => _PosventaScreenState();
}

class _PosventaScreenState extends State<PosventaScreen>
    with SingleTickerProviderStateMixin {
  late final PosventaService _srv;
  late final TabController _tabController;

  bool _cargando = false;
  String? _error;

  SaldoClienteModel? _saldo;
  List<DevolucionModel> _devoluciones = [];
  List<CambioModel> _cambios = [];
  List<ReembolsoModel> _reembolsos = [];

  @override
  void initState() {
    super.initState();
    _srv = widget.service ?? PosventaService();
    _tabController = TabController(length: 4, vsync: this);
    _cargarDatos();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _cargarDatos() async {
    setState(() {
      _cargando = true;
      _error = null;
    });

    try {
      final saldo = await _srv.obtenerMiSaldo();
      final devoluciones = await _srv.obtenerMisDevoluciones();
      final cambios = await _srv.obtenerMisCambios();
      final reembolsos = await _srv.obtenerMisReembolsos();

      if (mounted) {
        setState(() {
          _saldo = saldo;
          _devoluciones = devoluciones;
          _cambios = cambios;
          _reembolsos = reembolsos;
          _cargando = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'No se pudieron cargar los datos de posventa.';
          _cargando = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Mi Cuenta y Posventa'),
        backgroundColor: ColoresFS.paper,
        elevation: 0,
        bottom: TabBar(
          controller: _tabController,
          labelColor: ColoresFS.ink,
          unselectedLabelColor: ColoresFS.textMuted,
          indicatorColor: ColoresFS.ink,
          isScrollable: true,
          tabs: const [
            Tab(key: Key('tab_saldo'), text: 'Mi Saldo'),
            Tab(key: Key('tab_devoluciones'), text: 'Devoluciones'),
            Tab(key: Key('tab_cambios'), text: 'Cambios'),
            Tab(key: Key('tab_reembolsos'), text: 'Reembolsos'),
          ],
        ),
      ),
      body: _cargando
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(_error!, style: const TextStyle(color: ColoresFS.danger)),
                      const SizedBox(height: 12),
                      ElevatedButton(
                        onPressed: _cargarDatos,
                        child: const Text('Reintentar'),
                      ),
                    ],
                  ),
                )
              : TabBarView(
                  controller: _tabController,
                  children: [
                    _buildSaldoTab(),
                    _buildDevolucionesTab(),
                    _buildCambiosTab(),
                    _buildReembolsosTab(),
                  ],
                ),
    );
  }

  Widget _buildSaldoTab() {
    final saldo = _saldo;
    if (saldo == null) {
      return const Center(child: Text('No hay información de saldo.'));
    }

    return RefreshIndicator(
      onRefresh: _cargarDatos,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            elevation: 2,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Saldo disponible para compras',
                    style: TextStyle(color: ColoresFS.textMuted, fontSize: 14),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Bs ${saldo.saldoDisponibleBob.toStringAsFixed(2)}',
                    style: const TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      color: ColoresFS.ink,
                    ),
                  ),
                  if (saldo.saldoRetenidoBob > 0) ...[
                    const SizedBox(height: 6),
                    Text(
                      'Retenido temporalmente: Bs ${saldo.saldoRetenidoBob.toStringAsFixed(2)}',
                      style: const TextStyle(color: ColoresFS.warning, fontSize: 13),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            'Historial de movimientos',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          if (saldo.movimientos.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: Text('Aún no tienes movimientos registrados en tu saldo.'),
              ),
            )
          else
            ...saldo.movimientos.map((m) {
              final esIngreso = m.montoBob > 0;
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: Icon(
                    esIngreso ? Icons.arrow_downward : Icons.arrow_upward,
                    color: esIngreso ? ColoresFS.success : ColoresFS.danger,
                  ),
                  title: Text(m.motivo.isNotEmpty ? m.motivo : m.tipo),
                  subtitle: Text(m.creadaEn.split('T').first),
                  trailing: Text(
                    '${esIngreso ? "+" : ""}Bs ${m.montoBob.toStringAsFixed(2)}',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: esIngreso ? ColoresFS.success : ColoresFS.danger,
                    ),
                  ),
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _buildDevolucionesTab() {
    return RefreshIndicator(
      onRefresh: _cargarDatos,
      child: _devoluciones.isEmpty
          ? const Center(
              child: Text('No tienes solicitudes de devolución activas.'),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _devoluciones.length,
              itemBuilder: (context, index) {
                final d = _devoluciones[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.assignment_return_outlined, color: ColoresFS.ink),
                    title: Text('Devolución: ${d.estado}'),
                    subtitle: Text('Motivo: ${d.motivo} — ${d.creadaEn.split("T").first}'),
                  ),
                );
              },
            ),
    );
  }

  Widget _buildCambiosTab() {
    return RefreshIndicator(
      onRefresh: _cargarDatos,
      child: _cambios.isEmpty
          ? const Center(
              child: Text('No tienes solicitudes de cambio activas.'),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _cambios.length,
              itemBuilder: (context, index) {
                final c = _cambios[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.swap_horiz_outlined, color: ColoresFS.ink),
                    title: Text('Cambio: ${c.estado}'),
                    subtitle: Text(
                      'Diferencia: Bs ${c.diferenciaBob.toStringAsFixed(2)} (${c.direccionDiferencia})',
                    ),
                  ),
                );
              },
            ),
    );
  }

  Widget _buildReembolsosTab() {
    return RefreshIndicator(
      onRefresh: _cargarDatos,
      child: _reembolsos.isEmpty
          ? const Center(
              child: Text('No tienes reembolsos registrados.'),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _reembolsos.length,
              itemBuilder: (context, index) {
                final r = _reembolsos[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ListTile(
                    leading: const Icon(Icons.monetization_on_outlined, color: ColoresFS.success),
                    title: Text('Reembolso: ${r.estado}'),
                    subtitle: Text(
                      'Origen: ${r.origenTipo} — ${r.creadaEn.split("T").first}',
                    ),
                    trailing: Text(
                      'Bs ${r.montoTotalBob.toStringAsFixed(2)}',
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                    ),
                  ),
                );
              },
            ),
    );
  }
}
