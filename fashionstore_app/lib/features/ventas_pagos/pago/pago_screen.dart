// Pantalla Ciclo 3 — Pago con Stripe Test y confirmación por backend (CU15).
//
// Flujo: crear intención (una vez) -> PaymentSheet -> polling acotado al
// estado backend -> pendiente/aprobado/rechazado/vencido. Reintento solo
// cuando backend lo autoriza. Sin selector de método de pago.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../models/pago_model.dart';
import '../services/entrega_service.dart';
import '../services/pago_service.dart';
import '../../../core/session/dispositivo_helper.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/componentes_ciclo3.dart';
import '../pedidos/pedido_detalle_screen.dart';
import 'stripe_adapter.dart';
import 'stripe_port.dart';

class PagoScreen extends StatefulWidget {
  final String ventaId;
  final PagoService? servicioPago;
  final EntregaService? servicioEntrega;
  final PuertoStripe? puertoStripe;
  const PagoScreen({
    super.key,
    required this.ventaId,
    this.servicioPago,
    this.servicioEntrega,
    this.puertoStripe,
  });

  @override
  State<PagoScreen> createState() => _PagoScreenState();
}

class _PagoScreenState extends State<PagoScreen> with WidgetsBindingObserver {
  late final PagoService _pagos;
  late final EntregaService _entregas;
  late final PuertoStripe _hoja;

  bool _cargando = true;
  String? _error;
  EstadoPagoVenta? _estado;
  IntencionStripe? _intencion;
  bool _pagando = false;
  bool _consultando = false;
  Timer? _polling;
  int _intentos = 0;
  static const int _maxIntentos = 40;
  static const Duration _intervalo = Duration(seconds: 3);
  bool _intencionEnCurso = false;
  bool _finalizado = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _pagos = widget.servicioPago ?? PagoService();
    _entregas = widget.servicioEntrega ?? EntregaService();
    _hoja = widget.puertoStripe ?? AdaptadorStripe();
    _cargarEstado(inicial: true);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _detenerPolling();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Pausa el polling en background y lo retoma al volver, sin duplicar
    // intenciones ni continuar indefinidamente.
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive) {
      _detenerPolling();
    } else if (state == AppLifecycleState.resumed &&
        !_finalizado &&
        _estado != null &&
        !_estado!.pagoAprobado &&
        !_estado!.ventaVencida) {
      _iniciarPolling();
    }
  }

  Future<void> _cargarEstado({bool inicial = false}) async {
    if (inicial) setState(() => _cargando = true);
    try {
      final e = await _pagos.consultarEstado(widget.ventaId);
      if (!mounted) return;
      setState(() {
        _estado = e;
        _cargando = false;
        _error = null;
      });
      _evaluarFinal(e);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _cargando = false;
      });
    }
  }

  void _evaluarFinal(EstadoPagoVenta e) {
    if (e.pagoAprobado || e.ventaVencida) {
      _detenerPolling();
      _finalizado = e.pagoAprobado || e.ventaVencida;
    }
  }

  void _detenerPolling() {
    _polling?.cancel();
    _polling = null;
  }

  void _iniciarPolling() {
    if (_polling != null || _finalizado) return;
    _intentos = 0;
    _polling = Timer.periodic(_intervalo, (_) async {
      if (!mounted || _finalizado) {
        _detenerPolling();
        return;
      }
      if (_intentos >= _maxIntentos) {
        _detenerPolling();
        return;
      }
      _intentos++;
      try {
        final e = await _pagos.consultarEstado(widget.ventaId);
        if (!mounted) return;
        setState(() => _estado = e);
        _evaluarFinal(e);
      } catch (_) {}
    });
  }

  Future<void> _pagar({bool esReintento = false}) async {
    if (_pagando || _intencionEnCurso) return;
    setState(() {
      _pagando = true;
      _error = null;
    });
    try {
      // No crear intenciones duplicadas: una por intento de pago.
      _intencionEnCurso = true;
      final clave = const Uuid().v4();
      final inten = esReintento
          ? await _pagos.reintentar(
              ventaId: widget.ventaId, claveIdempotencia: clave)
          : await _pagos.crearIntencion(
              ventaId: widget.ventaId, claveIdempotencia: clave);
      _intencionEnCurso = false;
      if (!mounted) return;
      setState(() => _intencion = inten);
      final secreto = inten.clientSecret ?? '';
      if (secreto.isEmpty) {
        throw Exception('El backend no devolvió el secreto de pago.');
      }
      await _hoja.inicializarHoja(clientSecret: secreto);
      final res = await _hoja.presentarHoja();
      if (!mounted) return;
      if (res == ResultadoHojaPago.cancelado) {
        setState(() => _pagando = false);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Cerraste el pago. Puedes intentarlo de nuevo.'),
          ),
        );
        return;
      }
      // El resultado visual no confirma la venta: consultar backend.
      setState(() => _consultando = true);
      _iniciarPolling();
      await _cargarEstado();
      if (mounted) setState(() => _consultando = false);
    } catch (e) {
      _intencionEnCurso = false;
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _pagando = false);
    }
  }

  Future<void> _pagarConOrdenCU22() async {
    if (_pagando || _intencionEnCurso) return;
    setState(() {
      _pagando = true;
      _error = null;
    });
    try {
      _intencionEnCurso = true;
      final orden = await _pagos.crearOrdenPago(
        contexto: 'VENTA',
        recursoId: widget.ventaId,
        consentimientoCobroPosterior: true,
      );
      _intencionEnCurso = false;
      if (!mounted) return;

      final secreto = orden['client_secret'] as String?;
      final ordenId = (orden['orden_pago_id'] ?? orden['id'])?.toString();

      if (secreto != null && secreto.isNotEmpty) {
        await _hoja.inicializarHoja(clientSecret: secreto);
        final res = await _hoja.presentarHoja();
        if (!mounted) return;
        if (res == ResultadoHojaPago.cancelado) {
          setState(() => _pagando = false);
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Operación cancelada. Puedes intentar de nuevo.'),
            ),
          );
          return;
        }
        if (ordenId != null && ordenId.isNotEmpty) {
          try {
            await _pagos.continuarAccionOrden(ordenId: ordenId);
          } catch (_) {}
        }
      }

      if (ordenId != null && ordenId.isNotEmpty) {
        await _pagos.consultarOrdenPago(ordenId);
      }

      setState(() => _consultando = true);
      _iniciarPolling();
      await _cargarEstado();
      if (mounted) setState(() => _consultando = false);
    } catch (e) {
      _intencionEnCurso = false;
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _pagando = false);
    }
  }

  Future<void> _prepararMetodoPago() async {
    if (_pagando) return;
    setState(() {
      _pagando = true;
      _error = null;
    });
    try {
      final dispId = await DispositivoHelper.obtenerDispositivoId();
      final prep = await _pagos.prepararMetodoSetupIntent(huellaDispositivo: dispId);
      final secreto = prep['client_secret'] as String?;
      final prepId = (prep['preparacion_pago_id'] ?? prep['id'])?.toString();

      if (secreto != null && secreto.isNotEmpty) {
        await _hoja.inicializarHoja(clientSecret: secreto);
        final res = await _hoja.presentarHoja();
        if (!mounted) return;
        if (res == ResultadoHojaPago.completado && prepId != null) {
          await _pagos.confirmarMetodoPreparado(metodoId: prepId);
          final info = await _pagos.consultarMetodoPreparado(prepId);
          final estado = info['estado']?.toString();
          if (estado == 'LISTO') {
            await _pagos.guardarMetodoPreparado(metodoId: prepId, estado: 'LISTO');
            if (!mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Método de pago vinculado con éxito (SetupIntent CU22).'),
              ),
            );
          } else {
            if (!mounted) return;
            final mensaje = 'El método de pago no quedó listo en el servidor (estado: ${estado ?? "DESCONOCIDO"}).';
            setState(() => _error = mensaje);
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(mensaje),
                backgroundColor: ColoresFS.warning,
              ),
            );
          }
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error al preparar método de pago: $e'),
          backgroundColor: ColoresFS.danger,
        ),
      );
    } finally {
      if (mounted) setState(() => _pagando = false);
    }
  }

  Future<void> _verPedido() async {
    try {
      final lista = await _entregas.misPedidos(limit: 50, offset: 0);
      final match = lista.items.where((p) => p.ventaId == widget.ventaId);
      if (!mounted) return;
      if (match.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
              content: Text('Tu pago fue aprobado. Revisa Pedidos.')),
        );
        Navigator.pop(context);
        return;
      }
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => PedidoDetalleScreen(pedidoId: match.first.id),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString())),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Pagar compra')),
      body: _cargando
          ? const VistaCarga(mensaje: 'Consultando tu pago…')
          : _error != null && _estado == null
              ? VistaError(
                  mensaje: _error!, onReintentar: () => _cargarEstado())
              : _contenido(),
    );
  }

  Widget _contenido() {
    final e = _estado!;
    final resultado = resultadoDesdeEstado(e);
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Pago seguro con Stripe (modo prueba)',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                ),
                const SizedBox(height: 4),
                const Text(
                  'La confirmación definitiva la envía el banco a FashionStore. No cierres la app mientras confirmamos.',
                  style: TextStyle(color: ColoresFS.textMuted),
                ),
                const SizedBox(height: 12),
                FilaTotal(
                    etiqueta: 'Monto a pagar', valor: e.monto, destacado: true),
                const SizedBox(height: 8),
                _chipResultado(resultado),
              ],
            ),
          ),
        ),
        if (_error != null)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(_error!,
                  style: const TextStyle(color: ColoresFS.danger)),
            ),
          ),
        const SizedBox(height: 12),
        if (resultado == ResultadoPago.aprobado) ...[
          const Text(
            'Tu pago fue aprobado y tu pedido entró a preparación. Gracias por tu compra.',
            style: TextStyle(color: ColoresFS.success),
          ),
          const SizedBox(height: 12),
          ElevatedButton.icon(
            onPressed: _verPedido,
            icon: const Icon(Icons.receipt_long_outlined),
            label: const Text('Ver mi pedido'),
          ),
        ] else if (resultado == ResultadoPago.vencido) ...[
          const Text(
            'Esta compra venció y el stock fue liberado. Vuelve al carrito o al catálogo para intentarlo de nuevo.',
            style: TextStyle(color: ColoresFS.danger),
          ),
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Volver al carrito'),
          ),
        ] else ...[
          if (resultado == ResultadoPago.rechazado)
            const Padding(
              padding: EdgeInsets.only(bottom: 8),
              child: Text(
                'Tu pago fue rechazado y la venta sigue pendiente. Puedes intentarlo de nuevo dentro del tiempo permitido.',
                style: TextStyle(color: ColoresFS.warning),
              ),
            )
          else
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(
                _consultando || _polling != null
                    ? 'Esperando la confirmación del banco…'
                    : 'Toca pagar para abrir la hoja segura de Stripe.',
                style: const TextStyle(color: ColoresFS.textMuted),
              ),
            ),
          ElevatedButton.icon(
            key: const Key('btn_pagar_stripe'),
            onPressed:
                _pagando ? null : () => _pagar(esReintento: _intencion != null),
            icon: _pagando
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.lock_outline),
            label: Text(_pagando
                ? 'Procesando…'
                : (_intencion != null ? 'Reintentar pago' : 'Pagar ahora')),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            key: const Key('btn_pagar_orden_cu22'),
            onPressed: _pagando ? null : _pagarConOrdenCU22,
            icon: const Icon(Icons.credit_score_outlined),
            label: const Text('Pagar con Orden Conectada (CU22)'),
          ),
          const SizedBox(height: 6),
          TextButton.icon(
            key: const Key('btn_preparar_metodo_cu22'),
            onPressed: _pagando ? null : _prepararMetodoPago,
            icon: const Icon(Icons.add_card_outlined),
            label: const Text('Vincular tarjeta para compras futuras (SetupIntent)'),
          ),
          TextButton(
            onPressed: _pagando ? null : () => _cargarEstado(),
            child: const Text('Actualizar estado'),
          ),
        ],
      ],
    );
  }

  Widget _chipResultado(ResultadoPago r) {
    switch (r) {
      case ResultadoPago.aprobado:
        return const Text('Estado: aprobado',
            style: TextStyle(
                color: ColoresFS.success, fontWeight: FontWeight.w800));
      case ResultadoPago.rechazado:
        return const Text('Estado: rechazado, puedes reintentar',
            style: TextStyle(
                color: ColoresFS.warning, fontWeight: FontWeight.w800));
      case ResultadoPago.vencido:
        return const Text('Estado: vencido',
            style: TextStyle(
                color: ColoresFS.danger, fontWeight: FontWeight.w800));
      case ResultadoPago.pendiente:
        return const Text('Estado: pendiente de confirmación',
            style: TextStyle(
                color: ColoresFS.inkSoft, fontWeight: FontWeight.w800));
    }
  }
}
