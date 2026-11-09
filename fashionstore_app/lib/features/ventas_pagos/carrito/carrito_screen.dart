// Pantalla Ciclo 3 — Carrito de compra (canal MOVIL).
//
// Separado de la bolsa de reserva. Totales y promociones provienen del
// backend; la app no calcula totales definitivos ni usa el almacenamiento
// local como fuente de verdad.
import 'package:flutter/material.dart';

import '../models/carrito_model.dart';
import '../../catalogo/models/catalogo_model.dart';
import '../../experiencia_cliente/models/probador_model.dart';
import '../../organizacion/models/tasa_cambio_model.dart';
import '../../organizacion/services/tasa_cambio_service.dart';
import '../services/carrito_service.dart';
import '../../catalogo/services/catalogo_service.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/componentes_ciclo3.dart';
import '../../../core/ui/formato.dart';
import '../checkout/checkout_screen.dart';
import '../../experiencia_cliente/probador/probador_screen.dart';
import 'carrito_store.dart';

class CarritoScreen extends StatefulWidget {
  final CarritoStore? store;
  final CarritoService? servicio;
  final CatalogoService? servicioCatalogo;
  final TasaCambioService? servicioTasa;
  const CarritoScreen({
    super.key,
    this.store,
    this.servicio,
    this.servicioCatalogo,
    this.servicioTasa,
  });

  @override
  State<CarritoScreen> createState() => _CarritoScreenState();
}

class _DetalleLinea {
  final String productoId;
  final String nombre;
  final String sku;
  final String tallaColor;
  final String imagenUrl;
  final double precio;

  _DetalleLinea({
    this.productoId = '',
    required this.nombre,
    required this.sku,
    required this.tallaColor,
    this.imagenUrl = '',
    this.precio = 0,
  });
}

class _CarritoScreenState extends State<CarritoScreen> {
  late final CarritoStore _store;
  late final CatalogoService _catalogo;
  late final TasaCambioService _tasaSrv;
  TasaCambioModel? _tasaVigente;
  final Map<String, _DetalleLinea> _detalles = {};
  bool _resolviendoNombres = false;

  @override
  void initState() {
    super.initState();
    _store = widget.store ?? CarritoStore.instancia;
    if (widget.servicio != null) {
      _store.configurarParaPruebas(servicio: widget.servicio);
    }
    _catalogo = widget.servicioCatalogo ?? CatalogoService();
    _tasaSrv = widget.servicioTasa ?? TasaCambioService();
    _store.addListener(_alCambiarStore);
    _store.cargar().then((_) => _resolverNombres());
    _cargarTasa();
  }

  Future<void> _cargarTasa() async {
    try {
      final t = await _tasaSrv.obtenerTasaVigente();
      if (mounted) setState(() => _tasaVigente = t);
    } catch (_) {}
  }

  @override
  void dispose() {
    _store.removeListener(_alCambiarStore);
    super.dispose();
  }

  void _alCambiarStore() {
    if (mounted) setState(() {});
    if (!_store.cargando && _store.error == null) _resolverNombres();
  }

  Future<void> _resolverNombres() async {
    final lineas = _store.carrito.lineas;
    if (lineas.isEmpty || _resolviendoNombres) return;
    final pendientes =
        lineas.where((l) => !_detalles.containsKey(l.varianteId)).toList();
    if (pendientes.isEmpty) return;
    _resolviendoNombres = true;
    try {
      FiltrosOpciones? opciones;
      try {
        opciones = await _catalogo.filtrosOpciones();
      } catch (_) {
        opciones = null;
      }
      String nombreTalla(String id) {
        if (opciones == null) return '';
        try {
          return opciones.tallas.firstWhere((e) => e.id == id).nombre;
        } catch (_) {
          return '';
        }
      }

      String nombreColor(String id) {
        if (opciones == null) return '';
        try {
          return opciones.colores.firstWhere((e) => e.id == id).nombre;
        } catch (_) {
          return '';
        }
      }

      final nuevos = <String, _DetalleLinea>{};
      for (final l in pendientes) {
        try {
          final v = await _catalogo.obtenerVariante(l.varianteId);
          Producto? p;
          try {
            p = await _catalogo.obtenerProducto(v.productoId);
          } catch (_) {
            p = null;
          }
          final tc = [
            nombreTalla(v.tallaId),
            nombreColor(v.colorId),
          ].where((e) => e.isNotEmpty).join(' · ');
          final img = p?.primeraImagenOrdenada ?? p?.imagenPrincipal ?? '';
          nuevos[l.varianteId] = _DetalleLinea(
            productoId: p?.id ?? '',
            nombre: p?.nombre ?? 'Prenda seleccionada',
            sku: v.sku.isNotEmpty ? v.sku : 'Variante',
            tallaColor: tc,
            imagenUrl: img,
            precio: l.precioUnitario > 0 ? l.precioUnitario : v.precio,
          );
        } catch (_) {
          nuevos[l.varianteId] = _DetalleLinea(
            nombre: 'Prenda seleccionada',
            sku: 'Variante',
            tallaColor: '',
            precio: l.precioUnitario,
          );
        }
      }
      if (!mounted) return;
      setState(() => _detalles.addAll(nuevos));
    } finally {
      _resolviendoNombres = false;
    }
  }

  void _probarPrendasSeleccionadas() {
    final lineas = _store.carrito.lineas;
    final variantesUnicas = <String>{};
    final compatibles = <PrendaProbador>[];

    for (final l in lineas) {
      if (variantesUnicas.add(l.varianteId)) {
        final d = _detalles[l.varianteId];
        if (d != null &&
            d.imagenUrl.toLowerCase().startsWith('https://') &&
            d.sku.isNotEmpty &&
            d.precio > 0) {
          compatibles.add(PrendaProbador(
            productoId: d.productoId.isNotEmpty ? d.productoId : null,
            varianteId: l.varianteId,
            nombre: d.nombre,
            sku: d.sku,
            precio: d.precio,
            primeraImagenUrl: d.imagenUrl,
            atributos: d.tallaColor.isNotEmpty ? d.tallaColor : null,
          ));
        }
      }
    }

    if (compatibles.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
              'No hay prendas en el carrito con imagen compatible para el probador.'),
        ),
      );
      return;
    }

    // Inicialmente hasta 3 prendas seleccionadas (máximo 5)
    final seleccionadas = compatibles.take(3).toList();

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setLocal) {
            return SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Probar prendas seleccionadas',
                      style:
                          TextStyle(fontWeight: FontWeight.w800, fontSize: 17),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      compatibles.length > 5
                          ? 'Selecciona hasta 5 prendas para probar en tu sesión.'
                          : 'Elige las prendas que deseas probar en una sola sesión.',
                      style: const TextStyle(color: ColoresFS.textMuted),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Chip(
                          label: Text(
                            '${seleccionadas.length} seleccionada(s) (máx. 5)',
                            style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 12,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Flexible(
                      child: ListView.separated(
                        shrinkWrap: true,
                        itemCount: compatibles.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (_, i) {
                          final item = compatibles[i];
                          final estaSeleccionada = seleccionadas
                              .any((e) => e.varianteId == item.varianteId);

                          return CheckboxListTile(
                            value: estaSeleccionada,
                            contentPadding: EdgeInsets.zero,
                            secondary: ClipRRect(
                              borderRadius: BorderRadius.circular(6),
                              child: Image.network(
                                item.primeraImagenUrl,
                                width: 44,
                                height: 44,
                                fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => Container(
                                  width: 44,
                                  height: 44,
                                  color: Colors.grey.shade200,
                                  child: const Icon(Icons.checkroom, size: 24),
                                ),
                              ),
                            ),
                            title: Text(
                              item.nombre,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w700),
                            ),
                            subtitle: Text(
                              [
                                'Modelo ${item.sku}',
                                if (item.atributos != null) item.atributos!,
                                formatoPrecio(item.precio),
                              ].join(' · '),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            onChanged: (bool? checked) {
                              if (checked == true) {
                                if (seleccionadas.length >= 5) {
                                  ScaffoldMessenger.of(ctx).showSnackBar(
                                    const SnackBar(
                                      duration: Duration(seconds: 2),
                                      content: Text(
                                          'Solo puedes seleccionar hasta 5 prendas.'),
                                    ),
                                  );
                                  return;
                                }
                                setLocal(() => seleccionadas.add(item));
                              } else {
                                setLocal(() => seleccionadas.removeWhere(
                                    (e) => e.varianteId == item.varianteId));
                              }
                            },
                          );
                        },
                      ),
                    ),
                    const SizedBox(height: 12),
                    ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: ColoresFS.brassStrong,
                        foregroundColor: Colors.white,
                        minimumSize: const Size.fromHeight(48),
                      ),
                      onPressed: seleccionadas.isEmpty
                          ? null
                          : () {
                              Navigator.pop(ctx);
                              Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (_) =>
                                      ProbadorScreen(prendas: seleccionadas),
                                ),
                              );
                            },
                      icon: const Icon(Icons.view_in_ar_outlined),
                      label: Text(
                        seleccionadas.isEmpty
                            ? 'Selecciona al menos 1 prenda'
                            : 'Probar ${seleccionadas.length} prenda(s)',
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _verCobertura() async {
    final servicio = widget.servicio ?? CarritoService();
    List<CoberturaSucursal> sucursales = [];
    String? error;
    try {
      final c = await servicio.cobertura();
      sucursales = c.sucursales;
    } catch (e) {
      error = e.toString();
    }
    if (!mounted) return;
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) {
        if (error != null) {
          return Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'Sucursales que cubren tu carrito',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                ),
                const SizedBox(height: 8),
                Text(error, textAlign: TextAlign.center),
                const SizedBox(height: 12),
                ElevatedButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('Cerrar'),
                ),
              ],
            ),
          );
        }
        final cubren = sucursales.where((e) => e.cubreTodo).toList();
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Sucursales que cubren tu carrito',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Elige una de estas sucursales al confirmar tu compra.',
                  style: TextStyle(color: ColoresFS.textMuted),
                ),
                const SizedBox(height: 12),
                Flexible(
                  child: ListView(
                    shrinkWrap: true,
                    children: [
                      if (cubren.isEmpty)
                        const Text(
                          'Ninguna sucursal cubre todo tu carrito por ahora. Prueba quitar una prenda o cambiar cantidades.',
                        )
                      else
                        for (final s in cubren)
                          ListTile(
                            leading: const Icon(Icons.store_outlined),
                            title: Text(s.sucursalNombre,
                                maxLines: 1, overflow: TextOverflow.ellipsis),
                            trailing: const Icon(
                              Icons.check_circle,
                              color: ColoresFS.success,
                            ),
                          ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _irACheckout() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const CheckoutScreen()),
    ).then((_) => _store.cargar());
  }

  @override
  Widget build(BuildContext context) {
    final c = _store.carrito;
    if (_store.cargando && c.estaVacio) {
      return const VistaCarga(mensaje: 'Cargando tu carrito…');
    }
    if (_store.error != null && c.estaVacio) {
      return VistaError(
        mensaje: _store.error!,
        onReintentar: () => _store.cargar(),
      );
    }
    if (c.estaVacio) {
      return VistaVacia(
        icono: Icons.shopping_cart_outlined,
        titulo: 'Tu carrito está vacío',
        detalle:
            'Explora el catálogo y agrega prendas para comprarlas desde la app. Reservar para probar es un flujo aparte.',
        accionTexto: 'Ver catálogo',
        onAccion: () => _store.cargar(),
      );
    }
    final conPromo = c.lineas.where((e) => e.promocionId != null).length;
    return RefreshIndicator(
      onRefresh: () => _store.cargar(),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 140),
        children: [
          if (_store.error != null)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  _store.error!,
                  style: const TextStyle(color: ColoresFS.danger),
                ),
              ),
            ),
          for (final l in c.lineas) _filaLinea(l),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FilaTotal(etiqueta: 'Subtotal', valor: c.subtotal),
                  FilaTotal(
                      etiqueta: 'Descuento de promociones',
                      valor: c.descuentoTotal),
                  const Divider(),
                  FilaTotal(
                      etiqueta: 'Total a pagar',
                      valor: c.total,
                      destacado: true),
                  if (_tasaVigente != null && c.total > 0)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Row(
                        children: [
                          const Icon(Icons.currency_exchange,
                              size: 14, color: ColoresFS.brassStrong),
                          const SizedBox(width: 4),
                          Text(
                            '≈ USD ${(c.total / _tasaVigente!.tasaBobPorUsd).toStringAsFixed(2)} (Tasa oficial: ${_tasaVigente!.tasaBobPorUsd.toStringAsFixed(2)} BOB/USD · CU12)',
                            style: const TextStyle(
                              color: ColoresFS.brassStrong,
                              fontWeight: FontWeight.w700,
                              fontSize: 11.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (conPromo > 0)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        'Incluye promociones aplicadas en $conPromo prenda(s).',
                        style: const TextStyle(color: ColoresFS.textMuted),
                      ),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _store.operando ? null : _verCobertura,
            icon: const Icon(Icons.store_outlined),
            label: const Text('Ver sucursales que cubren el carrito'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
              minimumSize: const Size.fromHeight(48),
            ),
            onPressed: _store.operando ? null : _probarPrendasSeleccionadas,
            icon: const Icon(Icons.view_in_ar_outlined),
            label: const Text('Probar prendas seleccionadas'),
          ),
          const SizedBox(height: 8),
          ElevatedButton.icon(
            onPressed: _store.operando ? null : _irACheckout,
            icon: const Icon(Icons.lock_outline),
            label: const Text('Continuar con la compra'),
          ),
          TextButton(
            onPressed: _store.operando
                ? null
                : () async {
                    final messenger = ScaffoldMessenger.of(context);
                    final ok = await _store.vaciar();
                    if (!mounted || !ok) return;
                    messenger.showSnackBar(
                      const SnackBar(content: Text('Vaciamos tu carrito.')),
                    );
                  },
            child: const Text('Vaciar carrito'),
          ),
        ],
      ),
    );
  }

  Widget _filaLinea(LineaCarrito l) {
    final d = _detalles[l.varianteId];
    return TarjetaPrenda(
      nombre: d?.nombre ?? 'Prenda seleccionada',
      detalleVariante: [
        if ((d?.sku ?? '').isNotEmpty) 'Modelo ${d!.sku}',
        if ((d?.tallaColor ?? '').isNotEmpty) d!.tallaColor,
        if (l.promocionId != null) 'Con promoción aplicada',
      ].join(' · '),
      precio: l.precioUnitario,
      pieDisponibilidad: l.descuentoUnitario > 0
          ? 'Con descuento aplicado al confirmar la compra.'
          : null,
      acciones: Row(
        children: [
          IconButton(
            tooltip: 'Quitar una',
            constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
            onPressed: _store.operando
                ? null
                : () => _store.cambiarCantidad(
                      varianteId: l.varianteId,
                      cantidad: l.cantidad - 1,
                    ),
            icon: const Icon(Icons.remove_circle_outline),
          ),
          Text('${l.cantidad}',
              style:
                  const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
          IconButton(
            tooltip: 'Agregar una',
            constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
            onPressed: _store.operando
                ? null
                : () => _store.cambiarCantidad(
                      varianteId: l.varianteId,
                      cantidad: l.cantidad + 1,
                    ),
            icon: const Icon(Icons.add_circle_outline),
          ),
          const Spacer(),
          TextButton(
            onPressed:
                _store.operando ? null : () => _store.eliminar(l.varianteId),
            child: const Text('Quitar'),
          ),
        ],
      ),
    );
  }
}
