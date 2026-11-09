import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../models/checkout_model.dart';
import '../services/checkout_service.dart';
import '../services/pago_service.dart';
import 'stripe_adapter.dart';
import 'stripe_port.dart';

/// Pago de un PedidoCompra CU21 mediante una orden Stripe CU22.
///
/// La app conserva la identidad del recurso PEDIDO de principio a fin. La
/// confirmación final siempre la consulta y aplica el backend contra Stripe.
class PagoPedidoScreen extends StatefulWidget {
  final String pedidoId;
  final CheckoutService? servicioCheckout;
  final PagoService? servicioPago;
  final PuertoStripe? puertoStripe;

  const PagoPedidoScreen({
    super.key,
    required this.pedidoId,
    this.servicioCheckout,
    this.servicioPago,
    this.puertoStripe,
  });

  @override
  State<PagoPedidoScreen> createState() => _PagoPedidoScreenState();
}

class _PagoPedidoScreenState extends State<PagoPedidoScreen> {
  late final CheckoutService _checkout;
  late final PagoService _pagos;
  late final PuertoStripe _stripe;

  CheckoutRespuesta? _pedido;
  String? _error;
  String? _ordenId;
  String? _estadoOrden;
  double? _montoOrdenBob;
  bool _cargando = true;
  bool _pagando = false;
  int _intento = 0;

  @override
  void initState() {
    super.initState();
    _checkout = widget.servicioCheckout ?? CheckoutService();
    _pagos = widget.servicioPago ?? PagoService();
    _stripe = widget.puertoStripe ?? AdaptadorStripe();
    _cargarPedido();
  }

  bool get _pagoAprobado {
    final estado = (_pedido?.estadoPago ?? '').toUpperCase();
    return const {'PAGADO', 'PAGADA', 'APROBADO', 'CAPTURADO'}.contains(estado) ||
        _estadoOrden?.toUpperCase() == 'CAPTURADO';
  }

  bool get _pagoFallido => _estadoOrden?.toUpperCase() == 'FALLIDO';

  Future<void> _cargarPedido() async {
    if (_pedido == null) setState(() => _cargando = true);
    try {
      final pedido = await _checkout.obtenerPedido(widget.pedidoId);
      if (!mounted) return;
      setState(() {
        _pedido = pedido;
        _cargando = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _cargando = false;
      });
    }
  }

  String _clavePago(int intento) => const Uuid().v5(
        Namespace.url.value,
        'fashionstore/pedido/${widget.pedidoId}/oferta/${_pedido?.ofertaRevision ?? 1}/pago/$intento',
      );

  Future<Map<String, dynamic>> _crearORecuperarOrden() async {
    if (_ordenId != null && _estadoOrden?.toUpperCase() == 'FALLIDO') {
      _intento++;
      _ordenId = null;
    }
    if (_ordenId != null) {
      return _pagos.reanudarOrdenPago(_ordenId!);
    }

    // Si la app se reinició tras una respuesta incierta, la misma clave
    // devuelve la misma orden. Solo se crea otra orden tras un rechazo
    // terminal que el backend ya haya confirmado como FALLIDO.
    for (var intentosFallidos = 0; intentosFallidos < 3; intentosFallidos++) {
      final orden = await _pagos.crearOrdenPago(
        contexto: 'PEDIDO',
        pedidoCompraId: widget.pedidoId,
        ofertaRevision: _pedido?.ofertaRevision ?? 1,
        consentimientoCobroPosterior: false,
        claveIdempotencia: _clavePago(_intento),
      );
      final id = (orden['orden_pago_id'] ?? orden['id'])?.toString();
      if (id == null || id.isEmpty) {
        throw StateError('El backend no devolvió el identificador de la orden de pago.');
      }
      _ordenId = id;
      _estadoOrden = orden['estado']?.toString();
      _montoOrdenBob = _aBob(orden['monto_bob']);

      if (_estadoOrden?.toUpperCase() != 'FALLIDO') return orden;
      _intento++;
      _ordenId = null;
    }
    throw StateError('Stripe rechazó varios intentos. Revisa la tarjeta de prueba e inténtalo más tarde.');
  }

  double? _aBob(dynamic valor) {
    if (valor is num) return valor.toDouble();
    return double.tryParse(valor?.toString() ?? '');
  }

  Future<void> _pagar() async {
    final pedido = _pedido;
    if (_pagando || pedido == null || _pagoAprobado) return;

    setState(() {
      _pagando = true;
      _error = null;
    });

    try {
      var orden = await _crearORecuperarOrden();
      var ordenId = _ordenId!;
      var estado = (orden['estado'] ?? _estadoOrden ?? '').toString().toUpperCase();

      if (estado == 'CAPTURADO') {
        await _refrescarEstadoPago(ordenId);
        return;
      }

      var clientSecret = orden['client_secret']?.toString();
      if (clientSecret == null || clientSecret.isEmpty) {
        orden = await _pagos.reanudarOrdenPago(ordenId);
        estado = (orden['estado'] ?? estado).toString().toUpperCase();
        clientSecret = orden['client_secret']?.toString();
        _estadoOrden = estado;
        _montoOrdenBob = _aBob(orden['monto_bob']) ?? _montoOrdenBob;
      }

      if (estado == 'CAPTURADO') {
        await _refrescarEstadoPago(ordenId);
        return;
      }
      if (clientSecret == null || clientSecret.isEmpty) {
        throw StateError(
          'El backend no habilitó el cobro interactivo. Estado de la orden: ${estado.isEmpty ? "desconocido" : estado}.',
        );
      }

      await _stripe.inicializarHoja(clientSecret: clientSecret);
      final resultado = await _stripe.presentarHoja();
      if (!mounted) return;
      if (resultado == ResultadoHojaPago.cancelado) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Cerraste el pago. Puedes retomarlo desde esta pantalla.')),
        );
        return;
      }

      await _refrescarEstadoPago(ordenId);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _pagando = false);
    }
  }

  Future<void> _refrescarEstadoPago(String ordenId) async {
    Map<String, dynamic> resultado;
    try {
      resultado = await _pagos.confirmarOrdenPago(ordenId);
    } catch (_) {
      // La consulta autenticada a Stripe puede fallar temporalmente; consultar
      // la orden guardada no declara el pago confirmado por sí sola.
      resultado = await _pagos.consultarOrdenPago(ordenId);
    }
    if (!mounted) return;
    setState(() {
      _estadoOrden = resultado['estado']?.toString();
      _montoOrdenBob = _aBob(resultado['monto_bob']) ?? _montoOrdenBob;
    });
    await _cargarPedido();
  }

  Future<void> _actualizarPago() async {
    if (_pagando) return;
    final id = _ordenId;
    if (id == null) {
      await _cargarPedido();
      return;
    }
    setState(() {
      _pagando = true;
      _error = null;
    });
    try {
      await _refrescarEstadoPago(id);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _pagando = false);
    }
  }

  String get _estadoVisible {
    final pago = _pedido?.estadoPago ?? '';
    if (_pagoAprobado) return 'Pago aprobado';
    if (_pagoFallido) return 'Pago rechazado';
    if (_estadoOrden == 'REQUIERE_ACCION_CLIENTE') return 'Requiere confirmación';
    if (_estadoOrden == 'PENDIENTE' || pago == 'PENDIENTE') {
      return 'Pendiente de confirmación';
    }
    return 'Pendiente de pago';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Pagar compra')),
      body: _cargando
          ? const VistaCarga(mensaje: 'Consultando tu pedido…')
          : _pedido == null
              ? VistaError(mensaje: _error ?? 'No se pudo consultar el pedido.', onReintentar: _cargarPedido)
              : _contenido(_pedido!),
    );
  }

  Widget _contenido(CheckoutRespuesta pedido) {
    final monto = _montoOrdenBob ?? pedido.total;
    final estadoColor = _pagoAprobado
        ? ColoresFS.success
        : _pagoFallido
            ? ColoresFS.danger
            : ColoresFS.inkSoft;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('Compra digital', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                const SizedBox(height: 6),
                Text('Pedido ${pedido.pedidoId}'),
                const SizedBox(height: 10),
                Text('Total: Bs ${monto.toStringAsFixed(2)}', style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                Text(_estadoVisible, style: TextStyle(color: estadoColor, fontWeight: FontWeight.w700)),
              ],
            ),
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: 8),
          Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(_error!, style: const TextStyle(color: ColoresFS.danger)))),
        ],
        const SizedBox(height: 12),
        if (_pagoAprobado)
          const Text('El backend confirmó el pago y está procesando la asignación de tu pedido.', style: TextStyle(color: ColoresFS.success))
        else ...[
          const Text('Pago protegido con Stripe en modo de prueba. El pedido solo se confirma cuando el servidor verifica el resultado con Stripe.'),
          const SizedBox(height: 12),
          ElevatedButton.icon(
            key: const Key('btn_pagar_pedido_stripe'),
            onPressed: _pagando ? null : _pagar,
            icon: _pagando
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.lock_outline),
            label: Text(_pagando ? 'Procesando…' : (_pagoFallido ? 'Reintentar pago' : 'Pagar con Stripe Test')),
          ),
        ],
        const SizedBox(height: 8),
        OutlinedButton.icon(
          key: const Key('btn_actualizar_pago_pedido'),
          onPressed: _pagando ? null : _actualizarPago,
          icon: const Icon(Icons.refresh),
          label: const Text('Actualizar estado'),
        ),
      ],
    );
  }
}
