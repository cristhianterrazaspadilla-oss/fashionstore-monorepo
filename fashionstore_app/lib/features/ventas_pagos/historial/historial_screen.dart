import 'package:flutter/material.dart';

import '../models/compra_model.dart';
import '../../identidad_empresas/services/auth_service.dart';
import '../services/historial_service.dart';
import '../../posventa/services/posventa_service.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/formato.dart';

/// Historial paginado de compras del cliente.
class HistorialScreen extends StatefulWidget {
  final HistorialService? servicioHistorial;
  final AuthService? servicioAuth;
  final PosventaService? servicioPosventa;
  const HistorialScreen({
    super.key,
    this.servicioHistorial,
    this.servicioAuth,
    this.servicioPosventa,
  });

  @override
  State<HistorialScreen> createState() => _HistorialScreenState();
}

class _HistorialScreenState extends State<HistorialScreen> {
  late final HistorialService _srv;
  late final AuthService _auth;
  late final PosventaService _posventa;
  List<Compra> _items = [];
  bool _cargando = true;
  String? _error;
  int _offset = 0;
  static const _limite = 20;
  bool _hayMas = true;

  @override
  void initState() {
    super.initState();
    _srv = widget.servicioHistorial ?? HistorialService();
    _auth = widget.servicioAuth ?? AuthService();
    _posventa = widget.servicioPosventa ?? PosventaService();
    _cargar(inicial: true);
  }

  Future<void> _solicitarDevolucion(Compra compra, DetalleCompra detalle) async {
    var cantidad = 1;
    var motivoCodigo = 'TALLA';
    final descripcion = TextEditingController();
    final confirmar = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, actualizarDialogo) => AlertDialog(
          title: const Text('Solicitar devolución'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<String>(
                initialValue: motivoCodigo,
                decoration: const InputDecoration(labelText: 'Motivo'),
                items: const [
                  DropdownMenuItem(value: 'TALLA', child: Text('Talla')),
                  DropdownMenuItem(value: 'COLOR', child: Text('Color')),
                  DropdownMenuItem(value: 'DEFECTO_FABRICACION', child: Text('Defecto de fabricación')),
                  DropdownMenuItem(value: 'PRODUCTO_INCORRECTO', child: Text('Producto incorrecto')),
                  DropdownMenuItem(value: 'OTRO', child: Text('Otro')),
                ],
                onChanged: (value) {
                  if (value != null) actualizarDialogo(() => motivoCodigo = value);
                },
              ),
              TextField(
                controller: descripcion,
                decoration: const InputDecoration(labelText: 'Detalle (opcional)'),
                maxLength: 300,
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Unidades a devolver'),
                  Row(
                    children: [
                      IconButton(
                        onPressed: cantidad > 1
                            ? () => actualizarDialogo(() => cantidad--)
                            : null,
                        icon: const Icon(Icons.remove_circle_outline),
                      ),
                      Text('$cantidad / ${detalle.cantidad}'),
                      IconButton(
                        onPressed: cantidad < detalle.cantidad
                            ? () => actualizarDialogo(() => cantidad++)
                            : null,
                        icon: const Icon(Icons.add_circle_outline),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Enviar solicitud')),
          ],
        ),
      ),
    );
    if (confirmar != true || !mounted) {
      descripcion.dispose();
      return;
    }
    try {
      await _posventa.solicitarDevolucion(
        ventaId: compra.id,
        motivoCodigo: motivoCodigo,
        motivo: descripcion.text.trim(),
        lineas: [
          {'detalle_venta_id': detalle.id, 'cantidad': cantidad},
        ],
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Solicitud enviada. Podrás consultar su estado en Posventa.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No se pudo enviar la solicitud: $e')),
        );
      }
    } finally {
      descripcion.dispose();
    }
  }

  Future<void> _cargar({bool inicial = false}) async {
    if (inicial) {
      setState(() {
        _cargando = true;
        _error = null;
      });
    }
    try {
      final sesion = await _auth.sesionActual();
      final cid = sesion?.usuario.id ?? '';
      if (cid.isEmpty) throw Exception('Inicia sesión para ver tu historial.');
      final h = await _srv.historial(
        clienteId: cid,
        limit: _limite,
        offset: inicial ? 0 : _offset,
      );
      if (!mounted) return;
      setState(() {
        if (inicial) {
          _items = h.items;
          _offset = h.items.length;
        } else {
          _items.addAll(h.items);
          _offset += h.items.length;
        }
        _hayMas = _offset < h.total && h.items.length >= _limite;
        _cargando = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        if (inicial) {
          _error = e.toString().replaceAll('Exception: ', '');
          _cargando = false;
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(e.toString())),
          );
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) return const VistaCarga(mensaje: 'Buscando tus compras…');
    if (_error != null) {
      return VistaError(
          mensaje: _error!, onReintentar: () => _cargar(inicial: true));
    }
    if (_items.isEmpty) {
      return VistaVacia(
        icono: Icons.shopping_bag_outlined,
        titulo: 'Aún no tienes compras',
        detalle:
            'Cuando compres en tienda, aquí verás el detalle de tus comprobantes.',
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
          final c = _items[i];
          return Card(
            child: ExpansionTile(
              title: Text(
                'Compra ${c.numero}',
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              subtitle: Text(
                '${formatoFecha(c.creadaEn)} · ${c.totalPrendas} prenda(s)',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              trailing: Text(
                formatoPrecio(c.total),
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              children: [
                for (final d in c.detalles)
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      ListTile(
                        dense: true,
                        title: Text('Cantidad: ${d.cantidad}'),
                        trailing: Text(formatoPrecio(
                            d.precioUnitario * d.cantidad - d.descuento)),
                      ),
                      if (c.estado == 'PAGADA' || c.estado == 'PARCIALMENTE_DEVUELTA')
                        Align(
                          alignment: Alignment.centerRight,
                          child: TextButton.icon(
                            key: Key('devolver-${c.id}-${d.id}'),
                            onPressed: () => _solicitarDevolucion(c, d),
                            icon: const Icon(Icons.assignment_return_outlined),
                            label: const Text('Solicitar devolución'),
                          ),
                        ),
                    ],
                  ),
              ],
            ),
          );
        },
      ),
    );
  }
}
