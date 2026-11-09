// Pantalla Ciclo 3 — Probador virtual Decart Lucy 2.5 (CU17, solo Android).
//
// Informa transmisión a Decart, pide consentimiento versionado y luego
// permiso de cámara, usa token temporal solo en memoria, cubre el video
// hasta la primera transformación, cuenta 120 s, permite detener y cambiar
// de prenda sin conexiones simultáneas (máximo 5 prendas), y ejecuta cleanup
// garantizado e idempotente al salir.
// En iOS/web muestra indisponibilidad (MVP Android).
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../models/probador_model.dart';
import '../../catalogo/services/catalogo_service.dart';
import '../services/ia_service.dart';
import '../services/probador_service.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/formato.dart';
import '../../ventas_pagos/carrito/carrito_store.dart';
import '../../reservas_traslados/reservas/bolsa_store.dart';
import 'control_probador.dart';
import 'probador_en_vivo_screen.dart';
import 'puente_decart.dart';

class ProbadorScreen extends StatefulWidget {
  final String? varianteId;
  final List<PrendaProbador>? prendas;
  final ProbadorService? servicio;
  final IaService? navegacion;
  final PuenteDecart? puente;
  final CatalogoService? catalogo;
  final bool? forzarAndroid;
  final CarritoStore? carritoStore;
  final BolsaStore? bolsaStore;

  const ProbadorScreen({
    super.key,
    this.varianteId,
    this.prendas,
    this.servicio,
    this.navegacion,
    this.puente,
    this.catalogo,
    this.forzarAndroid,
    this.carritoStore,
    this.bolsaStore,
  }) : assert(varianteId != null || (prendas != null && prendas.length > 0),
            'Debe proveer varianteId o prendas');

  @override
  State<ProbadorScreen> createState() => _ProbadorScreenState();
}

class _ProbadorScreenState extends State<ProbadorScreen>
    with WidgetsBindingObserver {
  late final ControlProbador _control;
  late final CatalogoService _catalogo;
  late final List<PrendaProbador> _prendas;
  int _indiceActual = 0;
  bool _cargandoDatosPrenda = false;
  bool _pruebaPantallaActiva = false;

  PrendaProbador get _prendaActual {
    if (_prendas.isEmpty) {
      return PrendaProbador(
        varianteId: widget.varianteId ?? '',
        nombre: 'Cargando prenda…',
        sku: '...',
        precio: 0,
        primeraImagenUrl: '',
      );
    }
    return _prendas[_indiceActual.clamp(0, _prendas.length - 1)];
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _catalogo = widget.catalogo ?? CatalogoService();
    _control = ControlProbador(
      servicio: widget.servicio,
      navegacion: widget.navegacion,
      puente: widget.puente,
    );
    _control.addListener(_alCambiar);

    if (widget.prendas != null && widget.prendas!.isNotEmpty) {
      // Máximo 5 prendas por sesión de probador
      _prendas = widget.prendas!.take(5).toList();
      _control.cargarRecurso(_prendas.first.varianteId);
    } else {
      final vid = widget.varianteId!;
      _prendas = [
        PrendaProbador(
          varianteId: vid,
          nombre: 'Prenda',
          sku: '...',
          precio: 0,
          primeraImagenUrl: '',
        )
      ];
      _control.cargarRecurso(vid);
      _resolverDatosRealesVariante(vid);
    }
  }

  Future<void> _resolverDatosRealesVariante(String varianteId) async {
    setState(() => _cargandoDatosPrenda = true);
    try {
      final v = await _catalogo.obtenerVariante(varianteId);
      final p = await _catalogo.obtenerProducto(v.productoId);
      final primeraImagen = p.primeraImagenOrdenada ?? p.imagenPrincipal;
      if (!mounted) return;
      setState(() {
        _prendas[0] = PrendaProbador(
          productoId: p.id,
          varianteId: v.id,
          nombre: p.nombre,
          sku: v.sku,
          precio: v.precio,
          primeraImagenUrl: primeraImagen,
          descripcion: p.descripcion,
        );
        _cargandoDatosPrenda = false;
      });
    } catch (_) {
      if (mounted) setState(() => _cargandoDatosPrenda = false);
    }
  }

  void _alCambiar() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _control.removeListener(_alCambiar);
    // Cierre asíncrono idempotente (corrección final): `dispose()` no puede
    // esperar tareas asíncronas, por lo que se inicia `cerrar()` (disconnect
    // + release nativos) y se libera el ChangeNotifier solo cuando el cierre
    // termina. Llamar `_control.cerrar(); _control.dispose();` de forma
    // síncrona rompe el cierre: `dispose()` impide los `notifyListeners()`
    // pendientes y deja la sesión nativa sin esperar.
    final control = _control;
    control.cerrar().whenComplete(() {
      try {
        control.dispose();
      } catch (_) {}
    });
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // La pantalla hija administra la sesión mientras solicita el permiso de
    // cámara. Android puede pausar la Activity durante ese diálogo y el
    // padre no debe interpretar esa pausa como abandono del probador.
    if (_pruebaPantallaActiva) return;
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached ||
        state == AppLifecycleState.hidden) {
      // Respaldo de ciclo de vida: cerrar sesión inmediatamente.
      // Fire-and-forget seguro: `cerrar()` es idempotente y tolera
      // llamadas concurrentes/duplicadas y `dispose()` posterior.
      try {
        _control.cerrar();
      } catch (_) {}
    }
  }

  Future<void> _salir() async {
    await _control.cerrar();
    if (mounted) Navigator.pop(context);
  }

  Future<void> _abrirPruebaEnVivo() async {
    setState(() => _pruebaPantallaActiva = true);
    final indice = await Navigator.push<int>(
      context,
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => ProbadorEnVivoScreen(
          control: _control,
          prendas: _prendas,
          indiceInicial: _indiceActual,
        ),
      ),
    );
    if (mounted) {
      setState(() {
        _pruebaPantallaActiva = false;
        if (indice != null) _indiceActual = indice;
      });
    }
  }

  Future<void> _cambiarPrenda(int nuevoIndice) async {
    if (nuevoIndice < 0 || nuevoIndice >= _prendas.length || _control.ocupado) {
      return;
    }
    setState(() {
      _indiceActual = nuevoIndice;
    });
    final prenda = _prendas[nuevoIndice];
    if (_control.enVivo) {
      final imagen = prenda.primeraImagenUrl;
      final prompt =
          'Replace only the current top with the referenced garment ${prenda.nombre}';
      await _control.cambiarPrenda(imagenUrl: imagen, prompt: prompt);
    } else {
      await _control.cargarRecurso(prenda.varianteId);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        await _salir();
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Probador virtual'),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            tooltip: 'Volver',
            onPressed: _salir,
          ),
        ),
        body: _cuerpo(),
      ),
    );
  }

  Widget _cuerpo() {
    final c = _control;
    if (c.recurso == null && c.estado == EstadoProbador.idle) {
      return const VistaCarga(mensaje: 'Consultando compatibilidad…');
    }
    if (c.recurso == null && c.estado == EstadoProbador.error) {
      return VistaError(
        mensaje: c.error ?? 'No pudimos consultar la prenda.',
        onReintentar: () => c.cargarRecurso(_prendaActual.varianteId),
      );
    }
    final r = c.recurso!;
    if (!r.compatible) {
      return VistaVacia(
        icono: Icons.checkroom_outlined,
        titulo: 'Prenda no compatible',
        detalle:
            'Esta variante no tiene recurso de prueba virtual. Vuelve al producto para elegir otra prenda.',
        accionTexto: 'Volver al producto',
        onAccion: _salir,
      );
    }
    final esAndroid = widget.forzarAndroid ?? (!kIsWeb && Platform.isAndroid);
    if (!esAndroid) {
      return const VistaVacia(
        icono: Icons.smartphone_outlined,
        titulo: 'Probador disponible solo en Android',
        detalle:
            'La prueba virtual con video en vivo está habilitada únicamente en la app Android. Puedes agregar la prenda al carrito o reservarla.',
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        _tarjetaPrendaActual(),
        if (_prendas.length > 1) ...[
          const SizedBox(height: 10),
          _selectorPrendasSecuencial(),
        ],
        const SizedBox(height: 12),
        _aviso(),
        const SizedBox(height: 12),
        _consentimiento(),
        const SizedBox(height: 12),
        _video(r),
        const SizedBox(height: 12),
        _acciones(),
      ],
    );
  }

  Widget _tarjetaPrendaActual() {
    final p = _prendaActual;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: p.primeraImagenUrl.isNotEmpty
                  ? Image.network(
                      p.primeraImagenUrl,
                      width: 56,
                      height: 56,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Container(
                        width: 56,
                        height: 56,
                        color: Colors.grey.shade200,
                        child: const Icon(Icons.checkroom, size: 28),
                      ),
                    )
                  : Container(
                      width: 56,
                      height: 56,
                      color: Colors.grey.shade200,
                      child: const Icon(Icons.checkroom, size: 28),
                    ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    p.nombre,
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 15),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'SKU: ${p.sku}${p.atributos != null && p.atributos!.isNotEmpty ? ' · ${p.atributos}' : ''}',
                    style: const TextStyle(
                        color: ColoresFS.textMuted, fontSize: 13),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  if (p.precio > 0)
                    Text(
                      formatoPrecio(p.precio),
                      style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          color: ColoresFS.brassStrong),
                    ),
                ],
              ),
            ),
            if (_cargandoDatosPrenda)
              const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
          ],
        ),
      ),
    );
  }

  Widget _selectorPrendasSecuencial() {
    final c = _control;
    final total = _prendas.length;
    final pos = _indiceActual + 1;
    final puedeAnterior = _indiceActual > 0 && !c.ocupado;
    final puedeSiguiente = _indiceActual < total - 1 && !c.ocupado;

    return Card(
      color: ColoresFS.brassSoft,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: [
            IconButton(
              tooltip: 'Prenda anterior',
              icon: const Icon(Icons.arrow_back_ios_new, size: 18),
              onPressed: puedeAnterior
                  ? () => _cambiarPrenda(_indiceActual - 1)
                  : null,
            ),
            Expanded(
              child: Text(
                'Prenda $pos de $total',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 14,
                  color: ColoresFS.brassStrong,
                ),
              ),
            ),
            IconButton(
              tooltip: 'Prenda siguiente',
              icon: const Icon(Icons.arrow_forward_ios, size: 18),
              onPressed: puedeSiguiente
                  ? () => _cambiarPrenda(_indiceActual + 1)
                  : null,
            ),
          ],
        ),
      ),
    );
  }

  Widget _aviso() {
    return const Card(
      child: Padding(
        padding: EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Antes de encender tu cámara',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            SizedBox(height: 4),
            Text(
              'Tu video en vivo será transmitido y procesado por Decart para mostrarte la prenda. FashionStore no guarda tu video ni tu imagen.',
            ),
            SizedBox(height: 8),
            Text(
              avisoProbadorPermanente,
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }

  Widget _consentimiento() {
    final c = _control;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            CheckboxListTile(
              value: c.consentimiento,
              contentPadding: EdgeInsets.zero,
              title: const Text(
                'Entiendo que mi video se transmite a Decart y acepto la prueba (versión decart-v1).',
              ),
              onChanged:
                  c.ocupado ? null : (v) => c.aceptarConsentimiento(v ?? false),
            ),
            ElevatedButton.icon(
              onPressed: (!c.consentimiento || c.ocupado || c.enVivo)
                  ? null
                  : _abrirPruebaEnVivo,
              icon: const Icon(Icons.videocam_outlined),
              label: Text(c.ocupado ? 'Conectando…' : 'Iniciar prueba'),
            ),
            if (c.estado == EstadoProbador.error && c.error != null) ...[
              const SizedBox(height: 8),
              Text(c.error!, style: const TextStyle(color: ColoresFS.danger)),
              TextButton(
                onPressed: () => c.cargarRecurso(_prendaActual.varianteId),
                child: const Text('Volver a consultar la prenda'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _video(RecursoPruebaVirtual r) {
    return const Card(
      child: Padding(
        padding: EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(Icons.live_tv_outlined, color: ColoresFS.brassStrong),
                SizedBox(width: 8),
                Expanded(
                  child: Text('Vista previa en vivo',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                ),
              ],
            ),
            SizedBox(height: 8),
            Text(
              'Al iniciar se abrirá una pantalla completa. Mantén el teléfono vertical y encuadra la parte superior de tu cuerpo.',
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _acciones() {
    final c = _control;
    final prenda = _prendaActual;
    final tieneDatosReales = prenda.esValida;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (c.enVivo) ...[
              OutlinedButton.icon(
                onPressed: () => c.cerrar(),
                icon: const Icon(Icons.stop_outlined),
                label: const Text('Detener prueba'),
              ),
              const SizedBox(height: 8),
            ],
            ElevatedButton(
              onPressed: _salir,
              child: const Text('Volver al producto'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: !tieneDatosReales
                  ? null
                  : () async {
                      final messenger = ScaffoldMessenger.of(context);
                      final tiendaCarrito =
                          widget.carritoStore ?? CarritoStore.instancia;
                      final ok = await tiendaCarrito.agregar(
                        varianteId: prenda.varianteId,
                        cantidad: 1,
                      );
                      if (!mounted) return;
                      messenger.showSnackBar(
                        SnackBar(
                          content: Text(ok
                              ? 'Agregamos ${prenda.nombre} a tu carrito.'
                              : 'No pudimos agregar la prenda al carrito.'),
                        ),
                      );
                    },
              child: const Text('Agregar al carrito'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: !tieneDatosReales || prenda.precio <= 0
                  ? null
                  : () {
                      final tiendaBolsa =
                          widget.bolsaStore ?? BolsaStore.instancia;
                      tiendaBolsa.agregar(
                        varianteId: prenda.varianteId,
                        nombrePrenda: prenda.nombre,
                        sku: prenda.sku,
                        precio: prenda.precio,
                        cantidad: 1,
                      );
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(
                              'Reservamos ${prenda.nombre} (${prenda.sku}) para probar en tienda.'),
                        ),
                      );
                    },
              child: const Text('Reservar para probar'),
            ),
            if (!tieneDatosReales)
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text(
                  'Datos incompletos de la prenda; las acciones de compra y reserva están deshabilitadas.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: ColoresFS.danger, fontSize: 12),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
