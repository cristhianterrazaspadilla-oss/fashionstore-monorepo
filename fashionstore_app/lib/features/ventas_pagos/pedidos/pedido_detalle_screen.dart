// Detalle y seguimiento del pedido (CU16, solo lectura).
//
// Recojo: Solicitado -> Preparado -> Listo para recojo -> Recogido.
// Delivery: Solicitado -> Preparado -> En reparto -> Entregado.
// Muestra venta (número, fecha, importe, productos), pago, sucursal,
// dirección/costo o código. El cliente no avanza estados operativos.
import 'package:flutter/material.dart';

import '../models/checkout_model.dart';
import '../models/entrega_model.dart';
import '../../organizacion/models/organizacion_model.dart';
import '../services/checkout_service.dart';
import '../services/entrega_service.dart';
import '../services/pago_service.dart';
import '../../organizacion/services/sucursal_service.dart';
import '../models/pago_model.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/componentes_ciclo3.dart';
import '../../../core/ui/formato.dart';

class PedidoDetalleScreen extends StatefulWidget {
  final String pedidoId;
  final EntregaService? servicioEntrega;
  final CheckoutService? servicioCheckout;
  final PagoService? servicioPago;
  final SucursalService? servicioSucursal;
  const PedidoDetalleScreen({
    super.key,
    required this.pedidoId,
    this.servicioEntrega,
    this.servicioCheckout,
    this.servicioPago,
    this.servicioSucursal,
  });

  @override
  State<PedidoDetalleScreen> createState() => _PedidoDetalleScreenState();
}

class _PedidoDetalleScreenState extends State<PedidoDetalleScreen> {
  late final EntregaService _entregas;
  late final CheckoutService _checkout;
  late final PagoService _pagos;
  late final SucursalService _sucursales;

  bool _cargando = true;
  String? _error;
  Pedido? _pedido;
  VentaDigital? _venta;
  EstadoPagoVenta? _pago;
  SucursalModel? _sucursal;
  bool _cancelando = false;

  @override
  void initState() {
    super.initState();
    _entregas = widget.servicioEntrega ?? EntregaService();
    _checkout = widget.servicioCheckout ?? CheckoutService();
    _pagos = widget.servicioPago ?? PagoService();
    _sucursales = widget.servicioSucursal ?? SucursalService();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      final pedido = await _entregas.obtenerPedido(widget.pedidoId);
      VentaDigital? venta;
      EstadoPagoVenta? pago;
      SucursalModel? suc;
      try {
        venta = await _checkout.obtenerVenta(pedido.ventaId);
      } catch (_) {}
      try {
        pago = await _pagos.consultarEstado(pedido.ventaId);
      } catch (_) {}
      try {
        final todas = await _sucursales.listar();
        suc = todas.where((s) => s.id == pedido.sucursalId).firstOrNull;
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _pedido = pedido;
        _venta = venta;
        _pago = pago;
        _sucursal = suc;
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

  Future<void> _cancelar() async {
    final p = _pedido;
    if (p == null || _cancelando) return;
    final confirma = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancelar pedido'),
        content: const Text(
          'Solo puedes cancelar mientras esté solicitado y pendiente de pago. El stock se libera automáticamente.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Volver'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sí, cancelar'),
          ),
        ],
      ),
    );
    if (confirma != true || !mounted) return;
    setState(() => _cancelando = true);
    try {
      final actualizado = await _entregas.cancelarPedido(p.id);
      if (!mounted) return;
      setState(() => _pedido = actualizado);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Cancelamos tu pedido.')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString())),
      );
    } finally {
      if (mounted) setState(() => _cancelando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Detalle del pedido')),
      body: _cargando
          ? const VistaCarga(mensaje: 'Cargando tu pedido…')
          : _error != null
              ? VistaError(mensaje: _error!, onReintentar: _cargar)
              : _contenido(),
    );
  }

  Widget _contenido() {
    final p = _pedido!;
    final v = _venta;
    return RefreshIndicator(
      onRefresh: _cargar,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    v != null
                        ? 'Pedido ${v.numero}'
                        : 'Pedido en ${p.esDelivery ? 'delivery' : 'recojo'}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 17),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${formatoFecha(p.creadaEn)} · ${p.esDelivery ? 'Delivery' : 'Recojo en sucursal'}',
                    style: const TextStyle(color: ColoresFS.textMuted),
                  ),
                  const SizedBox(height: 8),
                  if (v != null)
                    FilaTotal(
                        etiqueta: 'Importe del pedido',
                        valor: v.total,
                        destacado: true),
                  if (_pago != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        _pago!.pagoAprobado
                            ? 'Pago aprobado.'
                            : _pago!.pagoRechazado
                                ? 'Pago rechazado o pendiente.'
                                : 'Pago ${_pago!.estadoPago.toLowerCase()}.',
                        style: TextStyle(
                          color: _pago!.pagoAprobado
                              ? ColoresFS.success
                              : ColoresFS.warning,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  if (_sucursal != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        'Sucursal: ${_sucursal!.nombre} · ${_sucursal!.direccion}',
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  if (p.esDelivery && (p.direccion ?? '').isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        'Entrega en: ${p.direccion} (anillo ${p.anilloDestino ?? '—'})',
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  if (p.esDelivery)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: FilaTotal(
                          etiqueta: 'Costo de entrega', valor: p.costoEntrega),
                    ),
                  if (p.esRecojo)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: SelectableText(
                        'Código de recojo: ${p.codigoRecojo ?? 'disponible al pagar'}',
                      ),
                    ),
                ],
              ),
            ),
          ),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('Seguimiento',
                      style:
                          TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                  const SizedBox(height: 8),
                  _seguimiento(p),
                ],
              ),
            ),
          ),
          if (v != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('Prendas incluidas',
                        style: TextStyle(
                            fontWeight: FontWeight.w800, fontSize: 15)),
                    const SizedBox(height: 8),
                    for (final d in v.detalles)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                '${d.cantidad} × prenda (línea de venta)',
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            Importe(d.precioUnitario * d.cantidad, tamano: 14),
                          ],
                        ),
                      ),
                    const Divider(),
                    FilaTotal(etiqueta: 'Subtotal', valor: v.subtotal),
                    FilaTotal(etiqueta: 'Descuento', valor: v.descuento),
                    if (v.costoEntrega > 0)
                      FilaTotal(
                          etiqueta: 'Costo de entrega', valor: v.costoEntrega),
                    FilaTotal(
                        etiqueta: 'Total', valor: v.total, destacado: true),
                  ],
                ),
              ),
            ),
          if (p.puedeCancelar)
            ElevatedButton.icon(
              onPressed: _cancelando ? null : _cancelar,
              icon: const Icon(Icons.cancel_outlined),
              label: Text(_cancelando ? 'Cancelando…' : 'Cancelar pedido'),
            ),
        ],
      ),
    );
  }

  Widget _seguimiento(Pedido p) {
    final pasos = p.pasosSeguimiento;
    final actual = p.indicePaso;
    final nombres = p.esRecojo
        ? const ['Solicitado', 'Preparado', 'Listo para recojo', 'Recogido']
        : const ['Solicitado', 'Preparado', 'En reparto', 'Entregado'];
    return Column(
      children: [
        for (var i = 0; i < pasos.length; i++)
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Column(
                children: [
                  Container(
                    width: 28,
                    height: 28,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: i <= actual
                          ? ColoresFS.brassStrong
                          : ColoresFS.border,
                    ),
                    child: Icon(
                      i < actual
                          ? Icons.check
                          : i == actual
                              ? Icons.radio_button_checked
                              : Icons.radio_button_unchecked,
                      color: Colors.white,
                      size: 16,
                    ),
                  ),
                  if (i < pasos.length - 1)
                    Container(
                      width: 2,
                      height: 22,
                      color:
                          i < actual ? ColoresFS.brassStrong : ColoresFS.border,
                    ),
                ],
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(top: 4, bottom: 12),
                  child: Text(
                    nombres[i],
                    style: TextStyle(
                      fontWeight:
                          i == actual ? FontWeight.w800 : FontWeight.w500,
                      color: i <= actual ? ColoresFS.ink : ColoresFS.textMuted,
                    ),
                  ),
                ),
              ),
            ],
          ),
        if (p.estaCancelado)
          const Text(
            'Este pedido fue cancelado.',
            style: TextStyle(color: ColoresFS.textMuted),
          ),
      ],
    );
  }
}

extension<T> on Iterable<T> {
  T? get firstOrNull {
    for (final e in this) {
      return e;
    }
    return null;
  }
}
