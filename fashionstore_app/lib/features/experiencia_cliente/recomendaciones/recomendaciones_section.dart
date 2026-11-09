// Sección Ciclo 3 — Recomendaciones para cliente (CU18).
//
// Vive dentro del catálogo. Consulta de solo lectura: muestra productos
// reales con disponibilidad y explicación del backend, sin inventar
// atributos. Permite abrir detalle, agregar al carrito, reservar para
// probar o abrir el probador cuando la variante es compatible.
import 'package:flutter/material.dart';

import '../models/ia_model.dart';
import '../models/probador_model.dart';
import '../../catalogo/services/catalogo_service.dart';
import '../services/ia_service.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/componentes_ciclo3.dart';
import '../../ventas_pagos/carrito/carrito_store.dart';
import '../../catalogo/catalogo/producto_detalle_screen.dart';
import '../probador/probador_screen.dart';
import '../../reservas_traslados/reservas/bolsa_store.dart';

class RecomendacionesSection extends StatefulWidget {
  final IaService? servicioIa;
  final CatalogoService? servicioCatalogo;
  final bool conTarjeta;
  const RecomendacionesSection(
      {super.key,
      this.servicioIa,
      this.servicioCatalogo,
      this.conTarjeta = true});

  @override
  State<RecomendacionesSection> createState() => _RecomendacionesSectionState();
}

class _RecomendacionesSectionState extends State<RecomendacionesSection> {
  late final IaService _ia;
  late final CatalogoService _catalogo;
  final _categoria = TextEditingController();
  final _talla = TextEditingController();
  bool _analizando = false;
  String? _error;
  RecomendacionRespuesta? _respuesta;
  bool _consultado = false;

  @override
  void initState() {
    super.initState();
    _ia = widget.servicioIa ?? IaService();
    _catalogo = widget.servicioCatalogo ?? CatalogoService();
  }

  @override
  void dispose() {
    _categoria.dispose();
    _talla.dispose();
    super.dispose();
  }

  Future<void> _pedir() async {
    if (_analizando) return;
    setState(() {
      _analizando = true;
      _error = null;
    });
    try {
      final r = await _ia.recomendaciones(
        limite: 3,
        categoria:
            _categoria.text.trim().isEmpty ? null : _categoria.text.trim(),
        talla: _talla.text.trim().isEmpty ? null : _talla.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        _respuesta = r;
        _consultado = true;
        _analizando = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _analizando = false;
      });
    }
  }

  Future<void> _abrirDetalle(RecomendacionItem item) async {
    try {
      final p = await _catalogo.obtenerProducto(item.productoId);
      if (!mounted) return;
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => ProductoDetalleScreen(producto: p)),
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
    final contenido = Padding(
      padding: EdgeInsets.all(widget.conTarjeta ? 14 : 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.conTarjeta) ...[
            const Text(
              'Sugerencias para ti',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
            ),
            const SizedBox(height: 4),
            const Text(
              'Te sugerimos prendas disponibles según temporada y tus visitas. Toca pedir y explora.',
              style: TextStyle(color: ColoresFS.textMuted),
            ),
            const SizedBox(height: 10),
          ],
          TextField(
            controller: _categoria,
            textInputAction: TextInputAction.next,
            decoration: const InputDecoration(
              labelText: 'Categoría (opcional)',
              hintText: 'Ej. vestidos, camisas',
            ),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _talla,
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _pedir(),
            decoration: const InputDecoration(
              labelText: 'Talla (opcional)',
              hintText: 'Ej. M, 38',
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              ActionChip(
                label: const Text('Vestidos'),
                onPressed: _analizando
                    ? null
                    : () {
                        _categoria.text = 'vestidos';
                        _pedir();
                      },
              ),
              ActionChip(
                label: const Text('Novedades'),
                onPressed: _analizando ? null : () => _pedir(),
              ),
            ],
          ),
          const SizedBox(height: 10),
          ElevatedButton.icon(
            onPressed: _analizando ? null : _pedir,
            icon: _analizando
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.auto_awesome_outlined),
            label: Text(_analizando ? 'Analizando…' : 'Pedir sugerencias'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: ColoresFS.danger)),
            TextButton(
              onPressed: _pedir,
              child: const Text('Reintentar'),
            ),
          ],
          if (_consultado && _respuesta != null) ...[
            const SizedBox(height: 10),
            if (_respuesta!.estaVacia)
              const Text(
                'No encontramos sugerencias con esos datos. Prueba sin filtros o con otra categoría.',
              )
            else
              for (final item in _respuesta!.items)
                TarjetaPrenda(
                  nombre: item.nombre,
                  precio: item.precio,
                  pieDisponibilidad:
                      '${item.disponible} disponible(s). ${item.motivo}',
                  onAbrir: () => _abrirDetalle(item),
                  acciones: Wrap(
                    spacing: 4,
                    runSpacing: 4,
                    children: [
                      TextButton(
                        onPressed: () async {
                          final messenger = ScaffoldMessenger.of(context);
                          final ok = await CarritoStore.instancia.agregar(
                            varianteId: item.varianteId,
                            cantidad: 1,
                          );
                          if (!mounted) return;
                          messenger.showSnackBar(
                            SnackBar(
                              content: Text(ok
                                  ? 'Agregamos la prenda a tu carrito.'
                                  : 'No pudimos agregarla. Intenta de nuevo.'),
                            ),
                          );
                        },
                        child: const Text('Al carrito'),
                      ),
                      TextButton(
                        onPressed: () async {
                          final messenger = ScaffoldMessenger.of(context);
                          var sku = 'Sugerencia';
                          try {
                            final v = await _catalogo
                                .obtenerVariante(item.varianteId);
                            sku = v.sku;
                          } catch (_) {}
                          if (!mounted) return;
                          BolsaStore.instancia.agregar(
                            varianteId: item.varianteId,
                            nombrePrenda: item.nombre,
                            sku: sku,
                            precio: item.precio,
                          );
                          messenger.showSnackBar(
                            const SnackBar(
                              content: Text(
                                  'La sumamos a tus prendas reservadas. Revísala en Reservas.'),
                            ),
                          );
                        },
                        child: const Text('Reservar'),
                      ),
                      TextButton(
                        onPressed: () async {
                          final navigator = Navigator.of(context);
                          try {
                            final v = await _catalogo
                                .obtenerVariante(item.varianteId);
                            final p =
                                await _catalogo.obtenerProducto(v.productoId);
                            final img =
                                p.primeraImagenOrdenada ?? p.imagenPrincipal;
                            if (!mounted) return;
                            navigator.push(
                              MaterialPageRoute(
                                builder: (_) => ProbadorScreen(
                                  prendas: [
                                    PrendaProbador(
                                      productoId: p.id,
                                      varianteId: v.id,
                                      nombre: p.nombre,
                                      sku: v.sku,
                                      precio:
                                          v.precio > 0 ? v.precio : item.precio,
                                      primeraImagenUrl: img,
                                    ),
                                  ],
                                  varianteId: item.varianteId,
                                ),
                              ),
                            );
                          } catch (_) {
                            if (mounted) {
                              navigator.push(
                                MaterialPageRoute(
                                  builder: (_) => ProbadorScreen(
                                      varianteId: item.varianteId),
                                ),
                              );
                            }
                          }
                        },
                        child: const Text('Probar'),
                      ),
                    ],
                  ),
                ),
          ],
        ],
      ),
    );
    if (widget.conTarjeta) {
      return Card(child: contenido);
    }
    return contenido;
  }
}
