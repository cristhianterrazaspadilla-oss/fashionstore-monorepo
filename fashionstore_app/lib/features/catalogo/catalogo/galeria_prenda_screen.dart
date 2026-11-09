import 'package:flutter/material.dart';

import '../models/catalogo_model.dart';

/// Galería de producto a pantalla completa con zoom y desplazamiento.
class GaleriaPrendaScreen extends StatefulWidget {
  final String nombre;
  final List<ImagenProducto> imagenes;
  final int indiceInicial;

  const GaleriaPrendaScreen({
    super.key,
    required this.nombre,
    required this.imagenes,
    this.indiceInicial = 0,
  });

  @override
  State<GaleriaPrendaScreen> createState() => _GaleriaPrendaScreenState();
}

class _GaleriaPrendaScreenState extends State<GaleriaPrendaScreen> {
  late final PageController _paginas;
  late int _indice;

  @override
  void initState() {
    super.initState();
    _indice = widget.indiceInicial;
    _paginas = PageController(initialPage: _indice);
  }

  @override
  void dispose() {
    _paginas.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(widget.nombre, maxLines: 1),
        actions: [
          Center(
            child: Padding(
              padding: const EdgeInsets.only(right: 16),
              child: Text('${_indice + 1}/${widget.imagenes.length}'),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: PageView.builder(
          controller: _paginas,
          itemCount: widget.imagenes.length,
          onPageChanged: (i) => setState(() => _indice = i),
          itemBuilder: (_, i) => InteractiveViewer(
            minScale: 1,
            maxScale: 4,
            child: Center(
              child: Image.network(
                widget.imagenes[i].enlace,
                width: double.infinity,
                height: double.infinity,
                fit: BoxFit.contain,
                loadingBuilder: (_, child, progreso) => progreso == null
                    ? child
                    : const Center(child: CircularProgressIndicator()),
                errorBuilder: (_, __, ___) => const Center(
                  child: Text(
                    'No pudimos cargar esta fotografía.',
                    style: TextStyle(color: Colors.white),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
