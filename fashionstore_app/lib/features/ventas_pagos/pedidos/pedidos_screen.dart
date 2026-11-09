// Pantalla Ciclo 3 — Pedidos del cliente (integra Mis compras).
//
// Muestra número, fecha, importe, modalidad, sucursal, estados de pago y
// pedido, dirección/costo en delivery y código en recojo. Separa activos,
// completados, cancelados y pagos pendientes. Solo consulta el estado.
import 'package:flutter/material.dart';

import '../models/entrega_model.dart';
import '../services/entrega_service.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/estado_chip.dart';
import '../../../core/ui/formato.dart';
import 'pedido_detalle_screen.dart';

class PedidosScreen extends StatefulWidget {
  final EntregaService? servicio;
  const PedidosScreen({super.key, this.servicio});

  @override
  State<PedidosScreen> createState() => _PedidosScreenState();
}

String _textoEstadoPedido(String e) {
  switch (e) {
    case 'SOLICITADO':
      return 'Solicitado';
    case 'PREPARADO':
      return 'Preparado';
    case 'LISTO_RECOJO':
      return 'Listo para recojo';
    case 'EN_REPARTO':
      return 'En reparto';
    case 'RECOGIDO':
      return 'Recogido';
    case 'ENTREGADO':
      return 'Entregado';
    case 'CANCELADO':
      return 'Cancelado';
    default:
      return e;
  }
}

Color _colorPedido(Pedido p) {
  if (p.estaCancelado) return ColoresFS.textMuted;
  if (p.estaCompletado) return ColoresFS.success;
  return ColoresFS.inkSoft;
}

class _PedidosScreenState extends State<PedidosScreen> {
  late final EntregaService _srv;
  List<Pedido> _items = [];
  bool _cargando = true;
  String? _error;
  String _filtro = 'ACTIVOS';

  @override
  void initState() {
    super.initState();
    _srv = widget.servicio ?? EntregaService();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      final r = await _srv.misPedidos(limit: 50, offset: 0);
      if (!mounted) return;
      setState(() {
        _items = r.items;
        _cargando = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _cargando = false;
      });
    }
  }

  List<Pedido> get _filtrados {
    switch (_filtro) {
      case 'ACTIVOS':
        return _items.where((p) => p.estaActivo).toList();
      case 'COMPLETADOS':
        return _items.where((p) => p.estaCompletado).toList();
      case 'CANCELADOS':
        return _items.where((p) => p.estaCancelado).toList();
      default:
        return _items;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) return const VistaCarga(mensaje: 'Cargando tus pedidos…');
    if (_error != null) {
      return VistaError(mensaje: _error!, onReintentar: _cargar);
    }
    if (_items.isEmpty) {
      return VistaVacia(
        icono: Icons.receipt_long_outlined,
        titulo: 'Aún no tienes pedidos',
        detalle:
            'Cuando compres desde el carrito, aquí verás el seguimiento de tu recojo o delivery.',
        accionTexto: 'Actualizar',
        onAccion: _cargar,
      );
    }
    final lista = _filtrados;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final f in [
                  'ACTIVOS',
                  'COMPLETADOS',
                  'CANCELADOS',
                  'TODOS'
                ])
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(f == 'TODOS'
                          ? 'Todos'
                          : f.toLowerCase().replaceFirst(
                              f[0].toLowerCase(), f[0].toUpperCase())),
                      selected: _filtro == f,
                      onSelected: (_) => setState(() => _filtro = f),
                    ),
                  ),
              ],
            ),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: _cargar,
            child: lista.isEmpty
                ? ListView(
                    children: const [
                      Padding(
                        padding: EdgeInsets.all(24),
                        child: Text(
                          'No hay pedidos en esta sección.',
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ],
                  )
                : ListView.builder(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
                    itemCount: lista.length,
                    itemBuilder: (_, i) {
                      final p = lista[i];
                      return Card(
                        child: ListTile(
                          leading: Icon(
                            p.esDelivery
                                ? Icons.delivery_dining_outlined
                                : Icons.store_outlined,
                            color: ColoresFS.brassStrong,
                          ),
                          title: Text(
                            p.esDelivery
                                ? 'Delivery · ${_textoEstadoPedido(p.estado)}'
                                : 'Recojo · ${_textoEstadoPedido(p.estado)}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          subtitle: Text(
                            '${formatoFechaCorta(p.creadaEn)} · ${p.esDelivery ? 'Costo entrega ${formatoPrecio(p.costoEntrega)}' : 'Código ${p.codigoRecojo ?? 'pendiente'}'}',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          trailing: EstadoChip(
                            texto: _textoEstadoPedido(p.estado),
                            color: _colorPedido(p),
                          ),
                          onTap: () => Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) =>
                                  PedidoDetalleScreen(pedidoId: p.id),
                            ),
                          ).then((_) => _cargar()),
                        ),
                      );
                    },
                  ),
          ),
        ),
      ],
    );
  }
}
