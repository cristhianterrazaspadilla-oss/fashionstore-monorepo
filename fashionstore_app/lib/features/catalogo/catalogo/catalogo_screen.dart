import 'package:flutter/material.dart';

import '../models/catalogo_model.dart';
import '../models/catalogo_snapshot_model.dart';
import '../services/catalogo_service.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/formato.dart';
import '../../experiencia_cliente/busqueda/buscador_voz.dart';
import '../../experiencia_cliente/recomendaciones/recomendaciones_section.dart';
import 'producto_detalle_screen.dart';

/// Catálogo con búsqueda, filtros, paginado, descarga offline (CU03)
/// y consulta local sobre SQLite (CU16).
class CatalogoScreen extends StatefulWidget {
  final CatalogoService? servicio;
  const CatalogoScreen({super.key, this.servicio});

  @override
  State<CatalogoScreen> createState() => _CatalogoScreenState();
}

class _CatalogoScreenState extends State<CatalogoScreen> {
  late final CatalogoService _servicio;
  final _busqueda = TextEditingController();
  final _filtros = FiltrosCatalogo();

  List<Producto> _items = [];
  FiltrosOpciones? _opciones;
  SnapshotMetadata? _snapshotActivo;
  bool _cargando = true;
  bool _cargandoMas = false;
  bool _descargandoSnapshot = false;
  bool _esModoOffline = false;
  bool _sinCopiaLocal = false;
  String? _error;
  String? _errorFiltros;
  int _offset = 0;
  static const _limite = 20;
  bool _hayMas = true;

  @override
  void initState() {
    super.initState();
    _servicio = widget.servicio ?? CatalogoService();
    _cargarTodo();
  }

  @override
  void dispose() {
    _busqueda.dispose();
    super.dispose();
  }

  Future<void> _cargarTodo() async {
    setState(() {
      _cargando = true;
      _error = null;
      _sinCopiaLocal = false;
    });

    // 1. Obtener metadatos de snapshot local activo si existe
    try {
      _snapshotActivo = await _servicio.obtenerSnapshotActivo();
    } catch (_) {}

    // 2. Intentar consulta online
    try {
      final opciones = await _servicio.filtrosOpciones().catchError((_) {
        return FiltrosOpciones.vacio();
      });
      final items = await _servicio.listarProductos(
        filtros: _filtros,
        limit: _limite,
        offset: 0,
      );
      if (!mounted) return;
      setState(() {
        _opciones = opciones;
        _items = items;
        _offset = items.length;
        _hayMas = items.length >= _limite;
        _esModoOffline = false;
        _sinCopiaLocal = false;
        _cargando = false;
      });
    } catch (e) {
      // 3. Fallback a consulta local en SQLite (CU16)
      try {
        final resLocal = await _servicio.consultarCatalogoLocal(
          texto: _filtros.texto,
          categoriaId: _filtros.categoriaId,
          colorId: _filtros.colorId,
          precioMin: _filtros.precioMin,
          precioMax: _filtros.precioMax,
          limit: _limite,
          offset: 0,
        );

        if (!mounted) return;

        if (resLocal.haySnapshot) {
          setState(() {
            _items = resLocal.items;
            _snapshotActivo = resLocal.snapshot;
            _offset = resLocal.items.length;
            _hayMas = resLocal.items.length >= _limite;
            _esModoOffline = true;
            _sinCopiaLocal = false;
            _cargando = false;
            _error = null;
          });
        } else {
          // No hay snapshot descargado ni red: no fingir lista vacía como catálogo actualizado
          setState(() {
            _items = [];
            _sinCopiaLocal = true;
            _esModoOffline = true;
            _cargando = false;
            _error =
                'Catálogo no disponible sin conexión. No se ha descargado una copia local en este dispositivo.';
          });
        }
      } catch (errLocal) {
        if (!mounted) return;
        setState(() {
          _error = e.toString();
          _cargando = false;
        });
      }
    }
  }

  Future<void> _cargarMas() async {
    if (_cargandoMas || !_hayMas) return;
    setState(() => _cargandoMas = true);
    try {
      if (_esModoOffline) {
        final resLocal = await _servicio.consultarCatalogoLocal(
          texto: _filtros.texto,
          categoriaId: _filtros.categoriaId,
          colorId: _filtros.colorId,
          precioMin: _filtros.precioMin,
          precioMax: _filtros.precioMax,
          limit: _limite,
          offset: _offset,
        );
        if (!mounted) return;
        setState(() {
          _items.addAll(resLocal.items);
          _offset += resLocal.items.length;
          _hayMas = resLocal.items.length >= _limite;
          _cargandoMas = false;
        });
      } else {
        final mas = await _servicio.listarProductos(
          filtros: _filtros,
          limit: _limite,
          offset: _offset,
        );
        if (!mounted) return;
        setState(() {
          _items.addAll(mas);
          _offset += mas.length;
          _hayMas = mas.length >= _limite;
          _cargandoMas = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _cargandoMas = false);
    }
  }

  /// Descarga el snapshot completo del catálogo en SQLite para consulta offline (CU03).
  Future<void> _descargarSnapshotOffline() async {
    if (_descargandoSnapshot) return;
    setState(() => _descargandoSnapshot = true);
    try {
      final snap = await _servicio.descargarCatalogo();
      final meta = await _servicio.obtenerSnapshotActivo();
      if (!mounted) return;
      setState(() {
        _snapshotActivo = meta;
        _descargandoSnapshot = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Catálogo descargado (v${snap.catalogoVersion}, ${snap.productos.length} prendas). Disponible sin conexión.',
          ),
          backgroundColor: Colors.green.shade800,
        ),
      );
      _cargarTodo();
    } catch (e) {
      if (!mounted) return;
      setState(() => _descargandoSnapshot = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('No se pudo descargar el catálogo offline: $e'),
          backgroundColor: Colors.red.shade800,
        ),
      );
    }
  }

  void _buscar() {
    _filtros.texto = _busqueda.text;
    _offset = 0;
    _hayMas = true;
    _cargarTodo();
  }

  void _limpiarFiltros() {
    _busqueda.clear();
    _filtros
      ..texto = ''
      ..categoriaId = null
      ..tallaId = null
      ..colorId = null
      ..temporadaId = null
      ..coleccionId = null
      ..marca = null
      ..genero = null
      ..precioMin = null
      ..precioMax = null;
    _cargarTodo();
  }

  Future<void> _abrirFiltros() async {
    final opciones = _opciones ?? FiltrosOpciones.vacio();
    String? categoria = _filtros.categoriaId;
    String? genero = _filtros.genero;
    final marcaCtrl = TextEditingController(text: _filtros.marca ?? '');
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setLocal) {
            return SafeArea(
              child: Padding(
                padding: EdgeInsets.only(
                  left: 20,
                  right: 20,
                  top: 16,
                  bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
                ),
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text(
                        'Filtrar prendas',
                        style: TextStyle(
                            fontSize: 18, fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 12),
                      if (opciones.categorias.isNotEmpty) ...[
                        const Text('Categoría'),
                        const SizedBox(height: 6),
                        Wrap(
                          spacing: 8,
                          children: [
                            ChoiceChip(
                              label: const Text('Todas'),
                              selected: categoria == null,
                              onSelected: (_) =>
                                  setLocal(() => categoria = null),
                            ),
                            for (final c in opciones.categorias)
                              ChoiceChip(
                                label: Text(c.nombre,
                                    overflow: TextOverflow.ellipsis),
                                selected: categoria == c.id,
                                onSelected: (_) =>
                                    setLocal(() => categoria = c.id),
                              ),
                          ],
                        ),
                        const SizedBox(height: 12),
                      ],
                      const Text('Colección por uso'),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 8,
                        children: [
                          for (final g in ['HOMBRE', 'MUJER', 'UNISEX', 'NIÑO'])
                            ChoiceChip(
                              label: Text(g),
                              selected: genero == g,
                              onSelected: (_) => setLocal(
                                  () => genero = genero == g ? null : g),
                            ),
                        ],
                      ),
                      if (opciones.generos.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          children: [
                            for (final g in opciones.generos.where((e) => ![
                                  'HOMBRE',
                                  'MUJER',
                                  'UNISEX',
                                  'NIÑO'
                                ].contains(e)))
                              ChoiceChip(
                                label: Text(g),
                                selected: genero == g,
                                onSelected: (_) => setLocal(
                                    () => genero = genero == g ? null : g),
                              ),
                          ],
                        ),
                      ],
                      const SizedBox(height: 12),
                      TextField(
                        controller: marcaCtrl,
                        decoration: const InputDecoration(
                          labelText: 'Marca (opcional)',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () => Navigator.pop(ctx),
                              child: const Text('Cerrar'),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: ElevatedButton(
                              onPressed: () {
                                _filtros.categoriaId = categoria;
                                _filtros.genero = genero;
                                _filtros.marca = marcaCtrl.text.trim().isEmpty
                                    ? null
                                    : marcaCtrl.text.trim();
                                Navigator.pop(ctx);
                                _cargarTodo();
                              },
                              child: const Text('Aplicar'),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        );
      },
    );
    marcaCtrl.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_cargando) {
      return const VistaCarga(mensaje: 'Buscando prendas…');
    }

    if (_sinCopiaLocal) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.cloud_off_outlined, size: 64, color: Colors.grey.shade600),
                const SizedBox(height: 16),
                const Text(
                  'Catálogo no descargado',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 8),
                Text(
                  'No se encontró una copia local en este dispositivo. Conéctate a internet para descargar el catálogo.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey.shade700),
                ),
                const SizedBox(height: 20),
                ElevatedButton.icon(
                  onPressed: _descargandoSnapshot ? null : _descargarSnapshotOffline,
                  icon: _descargandoSnapshot
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.download_outlined),
                  label: const Text('Descargar catálogo al conectar'),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: _cargarTodo,
                  child: const Text('Reintentar conexión'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    if (_error != null) {
      return VistaError(mensaje: _error!, onReintentar: _cargarTodo);
    }

    final fechaDescarga = _snapshotActivo != null
        ? formatoFecha(DateTime.tryParse(
            _snapshotActivo!.guardadoLocalEn.isNotEmpty
                ? _snapshotActivo!.guardadoLocalEn
                : _snapshotActivo!.generadoEn,
          ))
        : '—';

    return RefreshIndicator(
      onRefresh: _cargarTodo,
      child: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Indicador/Badge de modo offline (CU16) o estado del snapshot (CU03)
                  if (_esModoOffline && _snapshotActivo != null)
                    Container(
                      margin: const EdgeInsets.only(bottom: 10),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.blue.shade50,
                        border: Border.all(color: Colors.blue.shade200),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.offline_pin_outlined,
                              size: 20, color: Colors.blue.shade800),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Copia local — $fechaDescarga — Versión ${_snapshotActivo!.catalogoVersion}',
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w700,
                                color: Colors.blue.shade900,
                              ),
                            ),
                          ),
                        ],
                      ),
                    )
                  else
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        TextButton.icon(
                          onPressed: _descargandoSnapshot
                              ? null
                              : _descargarSnapshotOffline,
                          icon: _descargandoSnapshot
                              ? const SizedBox(
                                  width: 14,
                                  height: 14,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.cloud_download_outlined, size: 18),
                          label: Text(
                            _snapshotActivo != null
                                ? 'Copia local v${_snapshotActivo!.catalogoVersion}'
                                : 'Descargar catálogo offline',
                            style: const TextStyle(fontSize: 12),
                          ),
                        ),
                      ],
                    ),

                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _busqueda,
                          textInputAction: TextInputAction.search,
                          onSubmitted: (_) => _buscar(),
                          decoration: InputDecoration(
                            hintText: 'Buscar por nombre o descripción',
                            prefixIcon: const Icon(Icons.search),
                            suffixIcon: _busqueda.text.isNotEmpty ||
                                    _filtros.tieneFiltros
                                ? IconButton(
                                    tooltip: 'Limpiar',
                                    icon: const Icon(Icons.clear),
                                    onPressed: () {
                                      setState(() => _busqueda.clear());
                                      _limpiarFiltros();
                                    },
                                  )
                                : null,
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      IconButton.filledTonal(
                        tooltip: 'Filtros',
                        onPressed: _abrirFiltros,
                        icon: Badge(
                          isLabelVisible: _filtros.tieneFiltros,
                          child: const Icon(Icons.tune),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  if (_errorFiltros != null)
                    Text(_errorFiltros!,
                        style: const TextStyle(color: Colors.red)),
                  const SizedBox(height: 8),
                  if (!_esModoOffline) ...[
                    const ExpansionTile(
                      leading: Icon(Icons.mic_none_outlined),
                      title: Text('Buscar por voz o texto'),
                      subtitle:
                          Text('Dicta, revisa el texto y encuentra prendas'),
                      children: [
                        Padding(
                          padding: EdgeInsets.fromLTRB(8, 0, 8, 12),
                          child: BuscadorConVoz(conTarjeta: false),
                        ),
                      ],
                    ),
                    const ExpansionTile(
                      leading: Icon(Icons.auto_awesome_outlined),
                      title: Text('Sugerencias para ti'),
                      subtitle: Text('Prendas disponibles según tus visitas'),
                      children: [
                        Padding(
                          padding: EdgeInsets.fromLTRB(8, 0, 8, 12),
                          child: RecomendacionesSection(conTarjeta: false),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),
          if (_items.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: VistaVacia(
                icono: Icons.checkroom_outlined,
                titulo: 'Sin resultados',
                detalle:
                    'No encontramos prendas con esos criterios. Prueba con otra búsqueda o quita los filtros.',
                accionTexto: 'Quitar filtros',
                onAccion: _limpiarFiltros,
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 90),
              sliver: SliverGrid(
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 260,
                  mainAxisSpacing: 10,
                  crossAxisSpacing: 10,
                  childAspectRatio: 0.62,
                ),
                delegate: SliverChildBuilderDelegate(
                  (ctx, i) {
                    if (i >= _items.length) {
                      Future.microtask(_cargarMas);
                      return const Center(
                        child: Padding(
                          padding: EdgeInsets.all(12),
                          child: CircularProgressIndicator(),
                        ),
                      );
                    }
                    final p = _items[i];
                    return _TarjetaProducto(
                      producto: p,
                      esModoOffline: _esModoOffline,
                    );
                  },
                  childCount: _items.length + (_hayMas ? 1 : 0),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _TarjetaProducto extends StatelessWidget {
  final Producto producto;
  final bool esModoOffline;
  const _TarjetaProducto({
    required this.producto,
    this.esModoOffline = false,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => ProductoDetalleScreen(producto: producto),
            ),
          );
        },
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Container(
                    color: Colors.grey.shade100,
                    child: producto.imagenPrincipal.isEmpty
                        ? const Icon(Icons.checkroom, size: 56, color: Colors.grey)
                        : Image.network(
                            producto.imagenPrincipal,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => const Icon(
                                Icons.checkroom,
                                size: 56,
                                color: Colors.grey),
                          ),
                  ),
                  if (esModoOffline)
                    Positioned(
                      top: 6,
                      left: 6,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.blue.shade900.withValues(alpha: 0.85),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text(
                          'Disponibilidad conocida',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    producto.nombre,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 2),
                  if ((producto.marca ?? '').isNotEmpty)
                    Text(
                      producto.marca!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style:
                          TextStyle(color: Colors.grey.shade600, fontSize: 12),
                    ),
                  const SizedBox(height: 6),
                  Text(
                    formatoPrecio(producto.precioBase),
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      fontSize: 15,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
