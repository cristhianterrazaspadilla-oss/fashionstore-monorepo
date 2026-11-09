// Pantalla Ciclo 3 — Checkout digital por pasos (CU14/CU16).
//
// 1. Revisar productos. 2. Elegir sucursal que cubre. 3. Elegir modalidad
// (Recojo/Delivery). 4. Datos de entrega. 5. Revisar totales. 6. Confirmar
// y pagar con Stripe Test. Totales y tarifa provienen del backend; la app no
// calcula totales definitivos.
import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';
import '../../../core/utils/bolivia_time.dart';
import '../../../core/session/session_manager.dart';

import '../models/carrito_model.dart';
import '../models/checkout_model.dart';
import '../models/entrega_model.dart';
import '../../organizacion/models/organizacion_model.dart';
import '../../organizacion/models/tasa_cambio_model.dart';
import '../../organizacion/services/sucursal_service.dart';
import '../../organizacion/services/tasa_cambio_service.dart';
import '../services/carrito_service.dart';
import '../services/checkout_service.dart';
import '../services/entrega_service.dart';
import '../services/stripe_service.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/componentes_ciclo3.dart';
import '../../reservas_traslados/services/sincronizacion_offline_service.dart';
import '../carrito/carrito_store.dart';
import '../pago/pago_screen.dart';
import '../pago/pago_pedido_screen.dart';

class CheckoutScreen extends StatefulWidget {
  final CarritoService? servicioCarrito;
  final CheckoutService? servicioCheckout;
  final SucursalService? servicioSucursal;
  final EntregaService? servicioEntrega;
  final TasaCambioService? servicioTasa;
  final SincronizacionOfflineService? servicioSincronizacion;
  final PagoService? servicioPago;
  final String? metodoPreparadoId;
  final String? empresaId;
  final String? usuarioId;

  const CheckoutScreen({
    super.key,
    this.servicioCarrito,
    this.servicioCheckout,
    this.servicioSucursal,
    this.servicioEntrega,
    this.servicioTasa,
    this.servicioSincronizacion,
    this.servicioPago,
    this.metodoPreparadoId,
    this.empresaId,
    this.usuarioId,
  });

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  late final CarritoService _carritoSrv;
  late final CheckoutService _checkoutSrv;
  late final SucursalService _sucursalSrv;
  late final EntregaService _entregaSrv;
  late final TasaCambioService _tasaSrv;
  late final SincronizacionOfflineService _sincronizacionSrv;
  late final PagoService _pagoSrv;

  bool _cargando = true;
  String? _error;
  CarritoCompra? _carrito;
  TasaCambioModel? _tasaVigente;
  List<SucursalModel> _sucursales = [];
  Set<String> _cubren = {};
  String? _sucursalSel;
  String _modalidad = ModalidadEntrega.recojo;
  final _direccion = TextEditingController();
  int _anillo = 1;
  CotizacionDelivery? _cotizacion;
  bool _cotizando = false;
  String? _errorCotizacion;
  bool _confirmando = false;
  String? _errorConfirmacion;
  final String _claveConfirmacion = const Uuid().v4();

  // CU05 / CU22: Método preparado y sesión
  String? _metodoPreparadoId;
  bool _metodoPreparadoListo = false;
  String? _empresaId;
  String? _usuarioId;

  @override
  void initState() {
    super.initState();
    _carritoSrv = widget.servicioCarrito ?? CarritoService();
    _checkoutSrv = widget.servicioCheckout ?? CheckoutService();
    _sucursalSrv = widget.servicioSucursal ?? SucursalService();
    _entregaSrv = widget.servicioEntrega ?? EntregaService();
    _tasaSrv = widget.servicioTasa ?? TasaCambioService();
    _sincronizacionSrv = widget.servicioSincronizacion ?? SincronizacionOfflineService();
    _pagoSrv = widget.servicioPago ?? PagoService();
    _cargar();
  }

  @override
  void dispose() {
    _direccion.dispose();
    super.dispose();
  }

  Future<void> _cargar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      final carrito = await _carritoSrv.obtenerOCrear();
      final sucursales = await _sucursalSrv.listar();
      TasaCambioModel? tasa;
      try {
        tasa = await _tasaSrv.obtenerTasaVigente();
      } catch (_) {}
      Set<String> cubren = {};
      try {
        final cob = await _carritoSrv.cobertura();
        cubren = cob.queCubren.map((e) => e.sucursalId).toSet();
      } catch (_) {}

      // CU05: Consultar si existe un método preparado previamente confirmado (LISTO)
      String? metodoId = widget.metodoPreparadoId ?? await _pagoSrv.obtenerMetodoPreparadoIdLocal();
      bool listo = false;
      if (metodoId != null && metodoId.isNotEmpty) {
        try {
          final info = await _pagoSrv.consultarMetodoPreparado(metodoId);
          if (info['estado'] == 'LISTO') {
            listo = true;
            await _pagoSrv.guardarMetodoPreparado(metodoId: metodoId, estado: 'LISTO');
          }
        } catch (_) {
          final estadoLocal = await _pagoSrv.obtenerMetodoPreparadoEstadoLocal();
          if (estadoLocal == 'LISTO') {
            listo = true;
          }
        }
      }

      String? empId = widget.empresaId;
      String? usrId = widget.usuarioId;
      if (empId == null || usrId == null) {
        try {
          final sesion = await SessionManager().leerValida();
          if (sesion != null) {
            empId ??= sesion.usuario.empresaId;
            usrId ??= sesion.usuario.usuarioId;
          }
        } catch (_) {}
      }

      if (!mounted) return;
      setState(() {
        _carrito = carrito;
        _sucursales = sucursales.where((s) => s.activa).toList();
        _cubren = cubren;
        _tasaVigente = tasa;
        _metodoPreparadoId = metodoId;
        _metodoPreparadoListo = listo;
        _empresaId = empId;
        _usuarioId = usrId;
        _cargando = false;
        if (_sucursalSel == null) {
          final primera = _sucursales.where((s) => cubren.contains(s.id));
          if (primera.isNotEmpty) _sucursalSel = primera.first.id;
        }
      });
      await _recotizar();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _cargando = false;
      });
    }
  }

  SucursalModel? get _sucursalElegida {
    if (_sucursalSel == null) return null;
    try {
      return _sucursales.firstWhere((e) => e.id == _sucursalSel);
    } catch (_) {
      return null;
    }
  }

  Future<void> _recotizar() async {
    if (_modalidad != ModalidadEntrega.delivery || _sucursalSel == null) {
      if (mounted) setState(() => _cotizacion = null);
      return;
    }
    setState(() {
      _cotizando = true;
      _errorCotizacion = null;
    });
    try {
      final c = await _entregaSrv.cotizar(
        sucursalId: _sucursalSel!,
        anilloDestino: _anillo,
      );
      if (!mounted) return;
      setState(() {
        _cotizacion = c;
        _cotizando = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorCotizacion = e.toString();
        _cotizando = false;
      });
    }
  }

  String? _validar() {
    if (_sucursalSel == null) {
      return 'Elige la sucursal que preparará tu pedido.';
    }
    if (_modalidad == ModalidadEntrega.delivery) {
      if (_direccion.text.trim().isEmpty) {
        return 'Escribe tu dirección de referencia para el delivery.';
      }
      if (_anillo < 1 || _anillo > 12) {
        return 'El anillo de destino debe estar entre 1 y 12.';
      }
    }
    return null;
  }

  Future<void> _confirmar() async {
    if (_confirmando) return;
    final msg = _validar();
    if (msg != null) {
      setState(() => _errorConfirmacion = msg);
      return;
    }
    setState(() {
      _confirmando = true;
      _errorConfirmacion = null;
    });
    try {
      final resp = await _checkoutSrv.confirmar(
        datos: CheckoutCrear(
          sucursalId: _sucursalSel!,
          canal: 'MOVIL',
          modalidad: _modalidad,
          direccion: _modalidad == ModalidadEntrega.delivery
              ? _direccion.text.trim()
              : null,
          anilloDestino:
              _modalidad == ModalidadEntrega.delivery ? _anillo : null,
        ),
        claveIdempotencia: _claveConfirmacion,
      );
      await CarritoStore.instancia.limpiarReferenciaLocal();
      if (!mounted) return;
      if (resp.esPedidoDurable) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) => PagoPedidoScreen(pedidoId: resp.pedidoId),
          ),
        );
        return;
      }
      if (resp.ventaId.isEmpty) {
        throw StateError('El checkout no devolvió pedido_id ni venta_id.');
      }
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => PagoScreen(ventaId: resp.ventaId)),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        // Se conserva lo ingresado; se genera nueva clave solo tras éxito.
        _errorConfirmacion = e.toString();
        _confirmando = false;
      });
      // Recargar carrito por posible cambio de precio/stock.
      try {
        final c = await _carritoSrv.obtenerOCrear();
        if (mounted) setState(() => _carrito = c);
      } catch (_) {}
    }
  }

  Widget _estadoCobroOffline() {
    final tieneMetodo = _metodoPreparadoListo && _metodoPreparadoId != null && _metodoPreparadoId!.isNotEmpty;
    final tieneTasa = _tasaVigente != null && _tasaVigente!.id.isNotEmpty && _tasaVigente!.tasaBobPorUsd > 0;
    final cobroListo = tieneMetodo && tieneTasa;

    return Container(
      margin: const EdgeInsets.only(top: 8, bottom: 4),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cobroListo ? const Color(0xFFE8F5E9) : const Color(0xFFFFF8E1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: cobroListo ? const Color(0xFFA5D6A7) : const Color(0xFFFFD54F),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            cobroListo ? Icons.check_circle_outline : Icons.info_outline,
            color: cobroListo ? ColoresFS.success : const Color(0xFFF57F17),
            size: 20,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  cobroListo
                      ? 'Cobro automático offline habilitado'
                      : 'Cobro automático offline desactivado',
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  cobroListo
                      ? 'Método preparado verificado y tasa oficial vigente. Se cobrará automáticamente al reconectar.'
                      : (!tieneMetodo && !tieneTasa)
                          ? 'Sin método de pago preparado (LISTO) ni tasa oficial. La solicitud se encolará sin cobro automático (requerirá intervención).'
                          : !tieneMetodo
                              ? 'Sin método preparado confirmado (LISTO). Requiere pago manual al reconectar.'
                              : 'Sin tasa oficial vigente. Requiere confirmación al reconectar.',
                  style: const TextStyle(fontSize: 12),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _encolarCompraOffline() async {
    if (_confirmando) return;
    final msg = _validar();
    if (msg != null) {
      setState(() => _errorConfirmacion = msg);
      return;
    }
    if (_carrito == null || _carrito!.lineas.isEmpty) return;

    setState(() {
      _confirmando = true;
      _errorConfirmacion = null;
    });

    try {
      final lineas = _carrito!.lineas
          .map((l) => {
                'variante_id': l.varianteId,
                'cantidad': l.cantidad,
                'precio_unitario_bob': l.precioUnitario,
              })
          .toList();

      final subtotal = _carrito!.subtotal;
      final descuento = _carrito!.descuentoTotal;
      final costoEntrega = (_modalidad == ModalidadEntrega.delivery && _cotizacion != null)
          ? _cotizacion!.costoEntrega
          : 0.0;
      final totalBob = subtotal - descuento + costoEntrega;

      // CU05: Verificar si existe método preparado LISTO real y tasa vigente real
      final tieneMetodoListo = _metodoPreparadoListo && _metodoPreparadoId != null && _metodoPreparadoId!.isNotEmpty;
      final tieneTasaReal = _tasaVigente != null && _tasaVigente!.id.isNotEmpty && _tasaVigente!.tasaBobPorUsd > 0;

      final Map<String, dynamic>? autorizacionCobro;

      if (tieneMetodoListo && tieneTasaReal) {
        // Flujo verificado: tasa real y método LISTO confirmados
        final tasaVal = _tasaVigente!.tasaBobPorUsd;
        final tasaId = _tasaVigente!.id;
        final metodoId = _metodoPreparadoId!;
        final importeUsd = (totalBob / tasaVal).toStringAsFixed(2);
        final consentimientoId = const Uuid().v4();
        final aceptadoLocalEn = BoliviaTime.formatIso8601(BoliviaTime.now());
        final expiraDateTime = DateTime.now().add(const Duration(hours: 24)).toUtc();
        final expiraEn = '${expiraDateTime.year.toString().padLeft(4, '0')}-${expiraDateTime.month.toString().padLeft(2, '0')}-${expiraDateTime.day.toString().padLeft(2, '0')}T${expiraDateTime.hour.toString().padLeft(2, '0')}:${expiraDateTime.minute.toString().padLeft(2, '0')}:${expiraDateTime.second.toString().padLeft(2, '0')}Z';

        final empId = _empresaId ?? '11111111-1111-1111-1111-111111111111';
        final usrId = _usuarioId ?? '55555555-5555-5555-5555-555555555555';

        // Huella canónica estricta v3
        final huellaSha = calcularHuellaCompraCanonica(
          empresaId: empId,
          usuarioId: usrId,
          sucursalId: _sucursalSel!,
          modalidad: _modalidad,
          direccion: _modalidad == ModalidadEntrega.delivery ? _direccion.text.trim() : null,
          lineas: lineas,
          baseBob: subtotal,
          descuentoBob: descuento,
          envioBob: costoEntrega,
          totalBob: totalBob,
          monedaCobro: 'USD',
          importeCobro: double.parse(importeUsd),
          tasaId: tasaId,
          tasaBobPorUsd: tasaVal,
          condicionesVersion: 'v3',
          vigenteHasta: expiraEn,
        );

        autorizacionCobro = {
          'consentimiento_id': consentimientoId,
          'aceptado_local_en': aceptadoLocalEn,
          'huella_compra': huellaSha,
          'base_bob': subtotal.toStringAsFixed(2),
          'descuento_bob': descuento.toStringAsFixed(2),
          'envio_bob': costoEntrega.toStringAsFixed(2),
          'total_bob': totalBob.toStringAsFixed(2),
          'moneda_cobro': 'USD',
          'importe_cobro': importeUsd,
          'tasa_id': tasaId,
          'tasa_bob_por_usd': tasaVal.toStringAsFixed(2),
          'condiciones_version': 'v3',
          'vigente_hasta': expiraEn,
          'preparacion_pago_id': metodoId,
          'permite_cobro_al_reconectar': true,
        };
      } else {
        // Sin método LISTO o sin tasa real: NO construir Map parcial con permite_cobro_al_reconectar: false.
        // Se omite completamente (autorizacionCobro = null) para encolar la operación sin cobro automático.
        autorizacionCobro = null;
      }

      final op = await _sincronizacionSrv.encolarCompraOffline(
        sucursalId: _sucursalSel!,
        modalidad: _modalidad,
        direccion: _modalidad == ModalidadEntrega.delivery
            ? _direccion.text.trim()
            : null,
        anilloDestino:
            _modalidad == ModalidadEntrega.delivery ? _anillo : null,
        lineas: lineas,
        autorizacionCobro: autorizacionCobro,
        empresaId: _empresaId,
        usuarioId: _usuarioId,
      );

      await CarritoStore.instancia.limpiarReferenciaLocal();
      if (!mounted) return;

      setState(() => _confirmando = false);

      final cobroAutorizado = autorizacionCobro != null && autorizacionCobro['permite_cobro_al_reconectar'] == true;
      final motivoSinCobro = !tieneMetodoListo && !tieneTasaReal
          ? 'No hay método de pago preparado (LISTO) ni tasa oficial vigente.'
          : !tieneMetodoListo
              ? 'No hay método de pago preparado previamente confirmado (LISTO).'
              : 'No se cuenta con una tasa de cambio oficial vigente del servidor.';

      await showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Compra guardada offline (CU05 v3)'),
          content: Text(
            cobroAutorizado
                ? 'Tu solicitud de compra (${op.operacionId.substring(0, 8)}…) fue encolada de forma duradera con cobro automático autorizado mediante tu método preparado.\n\nSe sincronizará automáticamente con el servidor cuando se detecte conexión activa.'
                : 'Tu solicitud de compra (${op.operacionId.substring(0, 8)}…) fue encolada de forma duradera.\n\nEstado previsto: PENDIENTE_INTERVENCION.\nMotivo: $motivoSinCobro\nCobro automático: Desactivado (permite_cobro_al_reconectar = false).\n\nAl reconectar deberás completar el pago manualmente.',
          ),
          actions: [
            ElevatedButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Entendido'),
            ),
          ],
        ),
      );

      if (mounted) {
        Navigator.pop(context);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorConfirmacion = 'Error al encolar compra offline: $e';
        _confirmando = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Confirmar compra')),
      body: _cargando
          ? const VistaCarga(mensaje: 'Preparando tu compra…')
          : _error != null
              ? VistaError(mensaje: _error!, onReintentar: _cargar)
              : _carrito == null || _carrito!.estaVacio
                  ? const VistaVacia(
                      icono: Icons.shopping_cart_outlined,
                      titulo: 'Tu carrito está vacío',
                      detalle:
                          'Agrega prendas desde el catálogo para continuar.',
                    )
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 150),
                      children: [
                        _paso('1 · Revisa tus prendas', _resumen()),
                        _paso('2 · Elige la sucursal', _selectorSucursal()),
                        _paso('3 · Recojo o delivery', _selectorModalidad()),
                        if (_modalidad == ModalidadEntrega.delivery)
                          _paso('4 · Datos de entrega', _datosDelivery()),
                        _paso('5 · Revisa los totales', _totales()),
                        const SizedBox(height: 8),
                        _estadoCobroOffline(),
                        const SizedBox(height: 8),
                        OutlinedButton.icon(
                          key: const Key('btn_compra_offline_cu05'),
                          onPressed: _confirmando ? null : _encolarCompraOffline,
                          icon: const Icon(Icons.cloud_off_outlined),
                          label: const Text('Guardar compra offline (CU05 v3)'),
                        ),
                        if (_errorConfirmacion != null)
                          Card(
                            child: Padding(
                              padding: const EdgeInsets.all(12),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  Text(
                                    _errorConfirmacion!,
                                    style: const TextStyle(color: ColoresFS.danger),
                                  ),
                                  const SizedBox(height: 8),
                                  TextButton.icon(
                                    onPressed: _encolarCompraOffline,
                                    icon: const Icon(Icons.cloud_off),
                                    label: const Text('Intentar guardar offline ahora'),
                                  ),
                                ],
                              ),
                            ),
                          ),
                      ],
                    ),
      bottomSheet: _cargando || _error != null
          ? null
          : SafeArea(
              child: Container(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                decoration: BoxDecoration(
                  color: Theme.of(context).scaffoldBackgroundColor,
                  border: Border(top: BorderSide(color: Colors.grey.shade200)),
                ),
                child: SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _confirmando ? null : _confirmar,
                    icon: _confirmando
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.lock_outline),
                    label: Text(_confirmando
                        ? 'Confirmando…'
                        : 'Confirmar y pagar con Stripe'),
                  ),
                ),
              ),
            ),
    );
  }

  Widget _paso(String titulo, Widget hijo) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(titulo,
                style:
                    const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            const SizedBox(height: 8),
            hijo,
          ],
        ),
      ),
    );
  }

  Widget _resumen() {
    final c = _carrito!;
    return Column(
      children: [
        for (final l in c.lineas)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '${l.cantidad} × prenda seleccionada',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                Importe(l.subtotal, tamano: 14),
              ],
            ),
          ),
      ],
    );
  }

  Widget _selectorSucursal() {
    if (_sucursales.isEmpty) {
      return const Text('No hay sucursales disponibles por el momento.');
    }
    final cubren = _sucursales.where((s) => _cubren.contains(s.id)).toList();
    final otras = _sucursales.where((s) => !_cubren.contains(s.id)).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (cubren.isEmpty)
          const Text(
            'Ninguna sucursal cubre todo tu carrito. Ajusta cantidades en el carrito.',
            style: TextStyle(color: ColoresFS.warning),
          )
        else
          DropdownButtonFormField<String>(
            initialValue: _sucursalSel,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Sucursal que prepara tu pedido',
            ),
            selectedItemBuilder: (ctx) => [
              for (final s in cubren)
                Text(
                  s.nombre,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
            ],
            items: [
              for (final s in cubren)
                DropdownMenuItem(
                  value: s.id,
                  child: Text(
                    '${s.nombre} · ${s.direccion}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
            onChanged: (v) {
              setState(() => _sucursalSel = v);
              _recotizar();
            },
          ),
        if (otras.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            '${otras.length} sucursal(es) no cubren todo tu carrito y no se ofrecen.',
            style: const TextStyle(color: ColoresFS.textMuted, fontSize: 12.5),
          ),
        ],
        if (_sucursalElegida != null) ...[
          const SizedBox(height: 6),
          Text(
            'Recogerás o despacharemos desde ${_sucursalElegida!.nombre}.',
            style: const TextStyle(color: ColoresFS.textMuted),
          ),
        ],
      ],
    );
  }

  Widget _selectorModalidad() {
    return RadioGroup<String>(
      groupValue: _modalidad,
      onChanged: (v) {
        if (v == null) return;
        setState(() => _modalidad = v);
        if (v == ModalidadEntrega.delivery) _recotizar();
      },
      child: const Column(
        children: [
          RadioListTile<String>(
            value: ModalidadEntrega.recojo,
            title: Text('Recojo en sucursal'),
            subtitle:
                Text('Te avisaremos con un código para recoger tu pedido.'),
          ),
          RadioListTile<String>(
            value: ModalidadEntrega.delivery,
            title: Text('Delivery en Santa Cruz'),
            subtitle: Text('Llevamos tu pedido a tu dirección de referencia.'),
          ),
        ],
      ),
    );
  }

  Widget _datosDelivery() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _direccion,
          minLines: 1,
          maxLines: 3,
          textInputAction: TextInputAction.done,
          decoration: const InputDecoration(
            labelText: 'Dirección de referencia',
            hintText: 'Calle, zona y referencia cercana',
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            const Expanded(
              child: Text('Anillo de destino (1 a 12)'),
            ),
            IconButton(
              tooltip: 'Disminuir anillo',
              constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
              onPressed: _anillo > 1
                  ? () {
                      setState(() => _anillo--);
                      _recotizar();
                    }
                  : null,
              icon: const Icon(Icons.remove_circle_outline),
            ),
            Text('$_anillo',
                style:
                    const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            IconButton(
              tooltip: 'Aumentar anillo',
              constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
              onPressed: _anillo < 12
                  ? () {
                      setState(() => _anillo++);
                      _recotizar();
                    }
                  : null,
              icon: const Icon(Icons.add_circle_outline),
            ),
          ],
        ),
        const SizedBox(height: 8),
        if (_cotizando)
          const VistaCarga(mensaje: 'Calculando tarifa de entrega…')
        else if (_errorCotizacion != null)
          Text(_errorCotizacion!,
              style: const TextStyle(color: ColoresFS.danger))
        else if (_cotizacion != null)
          FilaTotal(
              etiqueta: 'Tarifa de entrega', valor: _cotizacion!.costoEntrega),
      ],
    );
  }

  Widget _totales() {
    final c = _carrito!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FilaTotal(etiqueta: 'Subtotal', valor: c.subtotal),
        FilaTotal(
            etiqueta: 'Descuento de promociones', valor: c.descuentoTotal),
        if (_modalidad == ModalidadEntrega.delivery && _cotizacion != null)
          FilaTotal(
              etiqueta: 'Costo de entrega', valor: _cotizacion!.costoEntrega),
        const Divider(),
        FilaTotal(etiqueta: 'Total a pagar', valor: c.total, destacado: true),
        if (_tasaVigente != null && c.total > 0)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Row(
              children: [
                const Icon(Icons.currency_exchange,
                    size: 14, color: ColoresFS.brassStrong),
                const SizedBox(width: 4),
                Text(
                  '≈ USD ${(c.total / _tasaVigente!.tasaBobPorUsd).toStringAsFixed(2)} (Tasa oficial: ${_tasaVigente!.tasaBobPorUsd.toStringAsFixed(2)} BOB/USD)',
                  style: const TextStyle(
                    color: ColoresFS.brassStrong,
                    fontWeight: FontWeight.w700,
                    fontSize: 11.5,
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 4),
        const Text(
          'El total final lo confirma el backend al pagar. Solo se usa Stripe en modo prueba.',
          style: TextStyle(color: ColoresFS.textMuted, fontSize: 12.5),
        ),
      ],
    );
  }
}
