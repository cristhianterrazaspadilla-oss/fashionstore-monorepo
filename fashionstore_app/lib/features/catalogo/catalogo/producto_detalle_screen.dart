import 'package:flutter/material.dart';

import '../models/catalogo_model.dart';
import '../../experiencia_cliente/models/probador_model.dart';
import '../services/catalogo_service.dart';
import '../../experiencia_cliente/services/probador_service.dart';
import '../../../core/session/puerta_auth.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/formato.dart';
import '../../ventas_pagos/carrito/carrito_store.dart';
import '../../experiencia_cliente/probador/probador_screen.dart';
import '../../reservas_traslados/reservas/bolsa_store.dart';
import 'galeria_prenda_screen.dart';

/// Detalle de prenda: variantes por talla/color + disponibilidad por sucursal.
class ProductoDetalleScreen extends StatefulWidget {
  final Producto producto;
  final CatalogoService? servicio;
  final ProbadorService? servicioProbador;

  const ProductoDetalleScreen({
    super.key,
    required this.producto,
    this.servicio,
    this.servicioProbador,
  });

  @override
  State<ProductoDetalleScreen> createState() => _ProductoDetalleScreenState();
}

class _ProductoDetalleScreenState extends State<ProductoDetalleScreen> {
  late final CatalogoService _servicio;
  late final ProbadorService _servicioProbador;
  List<Variante> _variantes = [];
  bool _cargando = true;
  String? _error;
  String? _varianteSel;
  List<DisponibilidadSucursal> _disponibilidad = [];
  bool _cargandoDisp = false;
  String? _errorDisp;
  int _cantidad = 1;

  Future<void> _abrirGaleria(int indiceInicial) {
    final imagenes = List<ImagenProducto>.from(widget.producto.imagenes)
      ..sort((a, b) {
        if (a.esPrincipal != b.esPrincipal) return a.esPrincipal ? -1 : 1;
        return a.orden.compareTo(b.orden);
      });
    if (imagenes.isEmpty) return Future<void>.value();
    return Navigator.push<void>(
      context,
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => GaleriaPrendaScreen(
          nombre: widget.producto.nombre,
          imagenes: imagenes,
          indiceInicial: indiceInicial.clamp(0, imagenes.length - 1),
        ),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _servicio = widget.servicio ?? CatalogoService();
    _servicioProbador = widget.servicioProbador ?? ProbadorService();
    _cargarVariantes();
  }

  Future<void> _cargarVariantes() async {
    setState(() {
      _cargando = true;
      _error = null;
    });
    try {
      final vs = await _servicio.variantesPorProducto(widget.producto.id);
      if (!mounted) return;
      setState(() {
        _variantes = vs.where((e) => e.activa).toList();
        _cargando = false;
        if (_variantes.isNotEmpty) {
          _varianteSel = _variantes.first.id;
          _cargarDisponibilidad(_variantes.first.id);
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _cargando = false;
      });
    }
  }

  Future<void> _cargarDisponibilidad(String varianteId) async {
    setState(() {
      _cargandoDisp = true;
      _errorDisp = null;
      _disponibilidad = [];
    });
    try {
      final d = await _servicio.disponibilidad(varianteId);
      if (!mounted) return;
      setState(() {
        _disponibilidad = d;
        _cargandoDisp = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorDisp = e.toString();
        _cargandoDisp = false;
      });
    }
  }

  Variante? get _sel {
    if (_varianteSel == null) return null;
    try {
      return _variantes.firstWhere((e) => e.id == _varianteSel);
    } catch (_) {
      return null;
    }
  }

  void _agregarABolsa() {
    final v = _sel;
    if (v == null) return;
    // Acción protegida: exigir login sin bloquear la vista del catálogo.
    PuertaAuth.exigir(
      context,
      motivo: 'Inicia sesión para reservar y probar en tienda.',
    ).then((ok) {
      if (!ok || !mounted) return;
      BolsaStore.instancia.agregar(
        varianteId: v.id,
        nombrePrenda: widget.producto.nombre,
        sku: v.sku,
        precio: v.precio,
        cantidad: _cantidad,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content:
              Text('Reservamos $_cantidad prenda(s) para probar en tienda.'),
          action: SnackBarAction(
            label: 'Ver reservas',
            onPressed: () => Navigator.pop(context),
          ),
        ),
      );
    });
  }

  Future<void> _agregarAlCarrito() async {
    final v = _sel;
    if (v == null) return;
    // Acción protegida: el carrito exige sesión (backend 401 sin token).
    final autorizado = await PuertaAuth.exigir(
      context,
      motivo: 'Inicia sesión para agregar prendas a tu carrito.',
    );
    if (!autorizado || !mounted) return;
    final ok = await CarritoStore.instancia.agregar(
      varianteId: v.id,
      cantidad: _cantidad,
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(ok
            ? 'Agregamos $_cantidad prenda(s) a tu carrito de compra.'
            : 'No pudimos agregarla al carrito. Intenta de nuevo.'),
      ),
    );
  }

  bool _validandoProbador = false;

  Future<void> _abrirProbador() async {
    final v = _sel;
    final imagen = widget.producto.primeraImagenOrdenada;
    if (v == null || imagen == null || imagen.isEmpty || _validandoProbador) {
      return;
    }
    // Acción protegida: el probador requiere token autenticado
    // (POST /api/v1/probador/autorizaciones con Bearer + consentimiento).
    final autorizado = await PuertaAuth.exigir(
      context,
      motivo: 'Inicia sesión para usar el probador virtual.',
    );
    if (!autorizado || !mounted) return;
    setState(() => _validandoProbador = true);
    try {
      final rec = await _servicioProbador.obtenerRecurso(v.id);
      if (!mounted) return;
      if (!rec.compatible) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content:
                Text('Esta prenda no es compatible con el probador virtual.'),
          ),
        );
        return;
      }
      final prenda = PrendaProbador(
        productoId: widget.producto.id,
        varianteId: v.id,
        nombre: widget.producto.nombre,
        sku: v.sku,
        precio: v.precio,
        primeraImagenUrl: imagen,
        descripcion: widget.producto.descripcion,
      );
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ProbadorScreen(
            prendas: [prenda],
            varianteId: v.id,
          ),
        ),
      );
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
                'El servicio del probador virtual no está disponible en este momento.'),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _validandoProbador = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.producto;
    return Scaffold(
      appBar: AppBar(title: Text(p.nombre, maxLines: 1)),
      body: _cargando
          ? const VistaCarga(mensaje: 'Cargando tallas y colores…')
          : _error != null
              ? VistaError(mensaje: _error!, onReintentar: _cargarVariantes)
              : SingleChildScrollView(
                  padding: EdgeInsets.fromLTRB(
                    16,
                    12,
                    16,
                    230 + MediaQuery.paddingOf(context).bottom,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (p.imagenPrincipal.isNotEmpty) ...[
                        Semantics(
                          button: true,
                          label: 'Ver fotografía completa de ${p.nombre}',
                          child: InkWell(
                            borderRadius: BorderRadius.circular(16),
                            onTap: () => _abrirGaleria(0),
                            child: Stack(
                              children: [
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(16),
                                  child: Image.network(
                                    p.imagenPrincipal,
                                    width: double.infinity,
                                    height: 260,
                                    fit: BoxFit.contain,
                                    errorBuilder: (_, __, ___) => Container(
                                      height: 160,
                                      color: Colors.grey.shade100,
                                      child:
                                          const Icon(Icons.checkroom, size: 56),
                                    ),
                                  ),
                                ),
                                const Positioned(
                                  right: 10,
                                  bottom: 10,
                                  child: CircleAvatar(
                                    backgroundColor: Colors.black54,
                                    foregroundColor: Colors.white,
                                    child: Icon(Icons.zoom_out_map),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          'Toca la foto para verla completa',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: ColoresFS.textMuted,
                            fontSize: 12,
                          ),
                        ),
                      ],
                      const SizedBox(height: 12),
                      Text(p.nombre,
                          style: const TextStyle(
                              fontSize: 22, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      if ((p.marca ?? '').isNotEmpty ||
                          (p.genero ?? '').isNotEmpty)
                        Text(
                          [p.marca, p.genero]
                              .where(
                                  (e) => e != null && e.toString().isNotEmpty)
                              .join(' · '),
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                      const SizedBox(height: 6),
                      Text(formatoPrecio(p.precioBase),
                          style: const TextStyle(
                              fontSize: 20, fontWeight: FontWeight.w800)),
                      if ((p.descripcion ?? '').isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Text(p.descripcion!),
                      ],
                      const SizedBox(height: 16),
                      const Text('Talla y color',
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      const Text(
                        'Elige la variante que quieres comprar o reservar.',
                        style: TextStyle(color: Colors.grey),
                      ),
                      const SizedBox(height: 8),
                      if (_variantes.isEmpty)
                        const Card(
                          child: Padding(
                            padding: EdgeInsets.all(16),
                            child: Text(
                                'Esta prenda no tiene variantes disponibles por el momento.'),
                          ),
                        )
                      else
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            for (final v in _variantes)
                              ChoiceChip(
                                label: Text(v.sku),
                                selected: _varianteSel == v.id,
                                onSelected: (_) {
                                  setState(() {
                                    _varianteSel = v.id;
                                    _cantidad = 1;
                                  });
                                  _cargarDisponibilidad(v.id);
                                },
                              ),
                          ],
                        ),
                      const SizedBox(height: 16),
                      const Text('Disponibilidad por sucursal',
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      const Text(
                        'Te mostramos dónde hay unidades listas para apartar.',
                        style: TextStyle(color: Colors.grey),
                      ),
                      const SizedBox(height: 8),
                      if (_cargandoDisp)
                        const VistaCarga(mensaje: 'Consultando disponibilidad…')
                      else if (_errorDisp != null)
                        VistaError(
                          mensaje: _errorDisp!,
                          onReintentar: () =>
                              _cargarDisponibilidad(_varianteSel ?? ''),
                        )
                      else if (_disponibilidad.isEmpty)
                        const Card(
                          child: Padding(
                            padding: EdgeInsets.all(16),
                            child: Text(
                              'Sin unidades disponibles en este momento. Puedes elegir otra variante o pedir traslado al confirmar tu bolsa.',
                            ),
                          ),
                        )
                      else
                        for (final d in _disponibilidad)
                          Card(
                            child: ListTile(
                              leading: const Icon(Icons.store_outlined),
                              title: Text(d.sucursalNombre,
                                  maxLines: 1, overflow: TextOverflow.ellipsis),
                              subtitle: Text(
                                '${d.ciudadNombre} · ${d.disponible} disponible(s)',
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                              trailing: Text(
                                '${d.disponible}',
                                style: const TextStyle(
                                    fontSize: 20, fontWeight: FontWeight.w800),
                              ),
                            ),
                          ),
                    ],
                  ),
                ),
      bottomSheet: _cargando || _error != null || _variantes.isEmpty
          ? null
          : SafeArea(
              child: Container(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                decoration: BoxDecoration(
                  color: Theme.of(context).scaffoldBackgroundColor,
                  border: Border(top: BorderSide(color: Colors.grey.shade200)),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Row(
                          children: [
                            IconButton(
                              tooltip: 'Quitar una',
                              onPressed: _cantidad > 1
                                  ? () => setState(() => _cantidad--)
                                  : null,
                              icon: const Icon(Icons.remove_circle_outline),
                            ),
                            Text('$_cantidad',
                                style: const TextStyle(
                                    fontSize: 17, fontWeight: FontWeight.w800)),
                            IconButton(
                              tooltip: 'Agregar una',
                              onPressed: () => setState(() => _cantidad++),
                              icon: const Icon(Icons.add_circle_outline),
                            ),
                          ],
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: ElevatedButton.icon(
                            onPressed: _agregarAlCarrito,
                            icon: const Icon(Icons.shopping_cart_outlined),
                            label: const Text('Agregar al carrito'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: _agregarABolsa,
                      icon: const Icon(Icons.shopping_bag_outlined),
                      label: const Text('Reservar para probar'),
                    ),
                    const SizedBox(height: 8),
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: ColoresFS.brassStrong,
                        foregroundColor: Colors.white,
                        minimumSize: const Size.fromHeight(48),
                      ),
                      onPressed:
                          (widget.producto.primeraImagenOrdenada == null ||
                                  _validandoProbador)
                              ? null
                              : _abrirProbador,
                      icon: _validandoProbador
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Icon(Icons.view_in_ar_outlined),
                      label: Text(_validandoProbador
                          ? 'Validando probador…'
                          : 'Probar con realidad aumentada'),
                    ),
                    if (widget.producto.primeraImagenOrdenada == null)
                      const Padding(
                        padding: EdgeInsets.only(top: 4),
                        child: Text(
                          'Esta prenda todavía no tiene una imagen compatible con el probador.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              color: ColoresFS.textMuted, fontSize: 12),
                        ),
                      ),
                  ],
                ),
              ),
            ),
    );
  }
}
