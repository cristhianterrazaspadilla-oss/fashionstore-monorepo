import 'package:flutter/material.dart';

import '../models/reserva_model.dart';
import '../models/sincronizacion_model.dart';
import '../services/reserva_service.dart';
import '../services/sincronizacion_offline_service.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/estado_chip.dart';
import '../../../core/ui/formato.dart';
import 'bolsa_screen.dart';
import 'bolsa_store.dart';
import 'reserva_detalle_screen.dart';

/// Listado paginado de reservas propias (CU18) e integración con reservas offline (CU04).
class ReservasScreen extends StatefulWidget {
  final ReservaService? servicio;
  final SincronizacionOfflineService? servicioOffline;
  const ReservasScreen({super.key, this.servicio, this.servicioOffline});

  @override
  State<ReservasScreen> createState() => _ReservasScreenState();
}

class _ReservasScreenState extends State<ReservasScreen> {
  late final ReservaService _srv;
  late final SincronizacionOfflineService _offlineSrv;

  List<Reserva> _items = [];
  List<OperacionSincronizacionLocal> _pendientesOffline = [];
  bool _cargando = true;
  bool _sincronizando = false;
  String? _error;
  int _offset = 0;
  static const _limite = 20;
  bool _hayMas = true;

  @override
  void initState() {
    super.initState();
    _srv = widget.servicio ?? ReservaService();
    _offlineSrv = widget.servicioOffline ?? SincronizacionOfflineService();
    _offlineSrv.iniciarMonitoreoRed();
    _cargar(inicial: true);
  }

  @override
  void dispose() {
    _offlineSrv.detenerMonitoreoRed();
    super.dispose();
  }

  Future<void> _cargar({bool inicial = false}) async {
    if (inicial) {
      setState(() {
        _cargando = true;
        _error = null;
      });
    }

    // Cargar cola local offline defensivamente
    try {
      final ops = await _offlineSrv.listarOperaciones();
      if (mounted) {
        setState(() {
          _pendientesOffline = ops
              .where((o) =>
                  o.estadoEnvio == 'PENDIENTE_ENVIO' ||
                  o.estadoEnvio == 'ENVIANDO' ||
                  o.estadoEnvio == 'CONFLICTO')
              .toList();
        });
      }
    } catch (_) {}

    try {
      final lista = await _srv.listarMias(
        limit: _limite,
        offset: inicial ? 0 : _offset,
      );
      if (!mounted) return;
      setState(() {
        if (inicial) {
          _items = lista.items;
          _offset = lista.items.length;
        } else {
          _items.addAll(lista.items);
          _offset += lista.items.length;
        }
        _hayMas = _offset < lista.total && lista.items.length >= _limite;
        _cargando = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        if (inicial) {
          _error = e.toString();
          _cargando = false;
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(e.toString())),
          );
        }
      });
    }
  }

  Future<void> _sincronizarAhora() async {
    if (_sincronizando) return;
    setState(() => _sincronizando = true);
    try {
      final resultados = await _offlineSrv.sincronizarPendientes();
      if (!mounted) return;
      setState(() => _sincronizando = false);
      if (resultados.isNotEmpty) {
        final aceptadas = resultados.where((r) => r.estado == 'ACEPTADA').length;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              aceptadas > 0
                  ? '$aceptadas reserva(s) sincronizada(s) y aceptadas centralmente.'
                  : 'Sincronización finalizada.',
            ),
          ),
        );
      }
      _cargar(inicial: true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _sincronizando = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error al sincronizar: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
          child: AnimatedBuilder(
            animation: BolsaStore.instancia,
            builder: (_, __) {
              final n = BolsaStore.instancia.totalPrendas;
              return Card(
                child: ListTile(
                  leading: const Icon(Icons.shopping_bag_outlined,
                      color: ColoresFS.brassStrong),
                  title: const Text('Mis prendas reservadas',
                      style: TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: Text(
                    n == 0
                        ? 'Tu bolsa para apartar y probar en tienda.'
                        : '$n prenda(s) listas para confirmar.',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  trailing: n > 0
                      ? Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: ColoresFS.brassSoft,
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text('$n',
                              style: const TextStyle(
                                  fontWeight: FontWeight.w800,
                                  color: ColoresFS.brassStrong)),
                        )
                      : const Icon(Icons.chevron_right),
                  onTap: () async {
                    await Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => BolsaScreen(
                          onReservaCreada: () => _cargar(inicial: true),
                        ),
                      ),
                    );
                    if (mounted) _cargar(inicial: true);
                  },
                ),
              );
            },
          ),
        ),
        if (_pendientesOffline.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
            child: Card(
              color: Colors.amber.shade50,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
                side: BorderSide(color: Colors.amber.shade300),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                child: Row(
                  children: [
                    Icon(Icons.cloud_upload_outlined, color: Colors.amber.shade900),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${_pendientesOffline.length} solicitud(es) offline pendiente(s)',
                            style: TextStyle(
                              fontWeight: FontWeight.w800,
                              color: Colors.amber.shade900,
                            ),
                          ),
                          Text(
                            'Se sincronizarán al estar conectado.',
                            style: TextStyle(fontSize: 12, color: Colors.amber.shade800),
                          ),
                        ],
                      ),
                    ),
                    ElevatedButton(
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      ),
                      onPressed: _sincronizando ? null : _sincronizarAhora,
                      child: _sincronizando
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Sincronizar', style: TextStyle(fontSize: 12)),
                    ),
                  ],
                ),
              ),
            ),
          ),
        Expanded(child: _lista()),
      ],
    );
  }

  Widget _lista() {
    if (_cargando) return const VistaCarga(mensaje: 'Buscando tus reservas…');
    if (_error != null) {
      return VistaError(
        mensaje: _error!,
        onReintentar: () => _cargar(inicial: true),
      );
    }
    if (_items.isEmpty) {
      return VistaVacia(
        icono: Icons.receipt_long_outlined,
        titulo: 'Aún no tienes reservas',
        detalle:
            'Cuando apartes prendas desde el catálogo, aquí verás su código, vigencia y estado.',
        accionTexto: 'Actualizar',
        onAccion: () => _cargar(inicial: true),
      );
    }
    return RefreshIndicator(
      onRefresh: () => _cargar(inicial: true),
      child: ListView.builder(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 90),
        itemCount: _items.length + (_hayMas ? 1 : 0),
        itemBuilder: (ctx, i) {
          if (i >= _items.length) {
            _cargar();
            return const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()),
            );
          }
          final r = _items[i];
          return Card(
            child: ListTile(
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              title: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Reserva ${r.codigo}',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                  ),
                  if (r.esOrigenOffline) ...[
                    Container(
                      margin: const EdgeInsets.only(right: 6),
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: Colors.blue.shade50,
                        border: Border.all(color: Colors.blue.shade200),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        'Offline CU04',
                        style: TextStyle(fontSize: 10, color: Colors.blue.shade900),
                      ),
                    ),
                  ],
                  EstadoChip.reserva(r.estadoLegible, r.estado),
                ],
              ),
              subtitle: Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '${r.totalPrendas} prenda(s) · ${textoVigencia(r.venceEn)}',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: () async {
                await Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => ReservaDetalleScreen(reservaId: r.id),
                  ),
                );
                if (mounted) _cargar(inicial: true);
              },
            ),
          );
        },
      ),
    );
  }
}
