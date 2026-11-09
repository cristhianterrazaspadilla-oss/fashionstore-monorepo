// Buscador con ayuda de voz (CU20), integrado al catálogo.
//
// Mantiene siempre la entrada escrita disponible. Flujo: permiso ->
// Escuchando -> texto editable -> interpretar en backend -> resultados del
// catálogo; si no se interpreta, búsqueda textual simple.
import 'package:flutter/material.dart';

import '../../catalogo/models/catalogo_model.dart';
import '../models/ia_model.dart';
import '../../catalogo/services/catalogo_service.dart';
import '../services/ia_service.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/componentes_ciclo3.dart';
import '../../ventas_pagos/carrito/carrito_store.dart';
import '../../catalogo/catalogo/producto_detalle_screen.dart';
import '../../reservas_traslados/reservas/bolsa_store.dart';
import 'control_voz.dart';

class BuscadorConVoz extends StatefulWidget {
  final IaService? servicioIa;
  final CatalogoService? servicioCatalogo;
  final ControlVoz? control;
  final bool conTarjeta;
  const BuscadorConVoz(
      {super.key,
      this.servicioIa,
      this.servicioCatalogo,
      this.control,
      this.conTarjeta = true});

  @override
  State<BuscadorConVoz> createState() => _BuscadorConVozState();
}

class _BuscadorConVozState extends State<BuscadorConVoz> {
  late final IaService _ia;
  late final CatalogoService _catalogo;
  late final ControlVoz _voz;
  final _texto = TextEditingController();
  InterpretacionBusqueda? _resultado;
  List<Producto> _fallback = [];
  bool _buscando = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _ia = widget.servicioIa ?? IaService();
    _catalogo = widget.servicioCatalogo ?? CatalogoService();
    _voz = widget.control ?? ControlVoz();
    _voz.addListener(_alCambiarVoz);
  }

  @override
  void dispose() {
    _voz.removeListener(_alCambiarVoz);
    _texto.dispose();
    super.dispose();
  }

  void _alCambiarVoz() {
    if (!mounted) return;
    setState(() {
      if (_voz.texto.isNotEmpty && _texto.text != _voz.texto) {
        _texto.text = _voz.texto;
      }
    });
  }

  Future<void> _buscar() async {
    final q = _texto.text.trim();
    if (q.length < 2 || _buscando) return;
    setState(() {
      _buscando = true;
      _error = null;
      _resultado = null;
      _fallback = [];
    });
    _voz.marcarProcesando();
    try {
      final r = await _ia.interpretarBusqueda(q);
      if (!mounted) return;
      setState(() {
        _resultado = r;
        _buscando = false;
      });
      _voz.marcarResultado(hayCoincidencias: r.items.isNotEmpty);
    } catch (_) {
      // Fallback textual simple sin bloquear el catálogo.
      try {
        final f = FiltrosCatalogo(texto: q);
        final items =
            await _catalogo.listarProductos(filtros: f, limit: 20, offset: 0);
        if (!mounted) return;
        setState(() {
          _fallback = items;
          _buscando = false;
        });
        _voz.marcarResultado(hayCoincidencias: items.isNotEmpty);
      } catch (e) {
        if (!mounted) return;
        setState(() {
          _error = e.toString();
          _buscando = false;
        });
        _voz.marcarError(e.toString());
      }
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
              'Buscar por voz o texto',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
            ),
            const SizedBox(height: 4),
            const Text(
              'Dicta lo que buscas, revisa el texto y toca buscar. Siempre puedes escribir.',
              style: TextStyle(color: ColoresFS.textMuted),
            ),
            const SizedBox(height: 10),
          ],
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _texto,
                  textInputAction: TextInputAction.search,
                  onSubmitted: (_) => _buscar(),
                  onChanged: _voz.editarTexto,
                  decoration: const InputDecoration(
                    labelText: 'Qué buscas hoy',
                    hintText: 'Ej. vestido rojo para fiesta',
                  ),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: 'Buscar por voz',
                constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
                style: IconButton.styleFrom(
                  backgroundColor: ColoresFS.brassSoft,
                ),
                onPressed: _voz.estado == EstadoVoz.escuchando
                    ? () => _voz.detener()
                    : () => _voz.iniciar(),
                icon: Icon(
                  _voz.estado == EstadoVoz.escuchando
                      ? Icons.mic
                      : Icons.mic_none_outlined,
                  color: ColoresFS.brassStrong,
                ),
              ),
            ],
          ),
          AnimatedBuilder(
            animation: _voz,
            builder: (_, __) => _estadoVoz(),
          ),
          const SizedBox(height: 8),
          ElevatedButton.icon(
            onPressed: _buscando ? null : _buscar,
            icon: _buscando
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.search),
            label: Text(_buscando ? 'Buscando…' : 'Buscar'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: ColoresFS.danger)),
          ],
          if (_resultado != null) _listaIa(),
          if (_fallback.isNotEmpty) _listaFallback(),
        ],
      ),
    );
    if (widget.conTarjeta) {
      return Card(child: contenido);
    }
    return contenido;
  }

  Widget _estadoVoz() {
    switch (_voz.estado) {
      case EstadoVoz.escuchando:
        return const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text(
              'Escuchando… habla ahora. Toca el micrófono para terminar.',
              style: TextStyle(
                  color: ColoresFS.brassStrong, fontWeight: FontWeight.w700)),
        );
      case EstadoVoz.permisoDenegado:
        return const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text(
              'Permiso de micrófono denegado. Puedes escribir tu búsqueda.',
              style: TextStyle(color: ColoresFS.warning)),
        );
      case EstadoVoz.permisoDenegadoPermanente:
        return Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Permiso de micrófono denegado permanentemente. Puedes escribir tu búsqueda o activarlo en configuración.',
                style: TextStyle(color: ColoresFS.warning),
              ),
              const SizedBox(height: 4),
              TextButton.icon(
                onPressed: () => _voz.abrirConfiguracion(),
                icon: const Icon(Icons.settings_outlined, size: 18),
                label: const Text('Abrir configuración'),
              ),
            ],
          ),
        );
      case EstadoVoz.noDisponible:
        return const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text(
              'Micrófono no disponible en este equipo. Usa la búsqueda escrita.',
              style: TextStyle(color: ColoresFS.textMuted)),
        );
      case EstadoVoz.procesando:
        return const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text('Interpretando tu búsqueda…',
              style: TextStyle(color: ColoresFS.textMuted)),
        );
      case EstadoVoz.sinCoincidencias:
        return const Padding(
          padding: EdgeInsets.only(top: 8),
          child: Text('Sin coincidencias. Prueba con otras palabras.',
              style: TextStyle(color: ColoresFS.textMuted)),
        );
      case EstadoVoz.error:
        return Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(_voz.error ?? 'No pudimos completar la búsqueda.',
              style: const TextStyle(color: ColoresFS.danger)),
        );
      case EstadoVoz.resultado:
      case EstadoVoz.inactivo:
        return const SizedBox.shrink();
    }
  }

  Widget _listaIa() {
    final r = _resultado!;
    if (r.sinCoincidencias) {
      return const Padding(
        padding: EdgeInsets.only(top: 8),
        child: Text('Sin coincidencias. Prueba con otras palabras.'),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 8),
        Text('Encontramos ${r.total} coincidencia(s).',
            style: const TextStyle(fontWeight: FontWeight.w700)),
        for (final item in r.items)
          TarjetaPrenda(
            nombre: item.nombre,
            precio: item.precio,
            pieDisponibilidad:
                '${item.disponible} disponible(s). ${item.motivo}',
            onAbrir: () async {
              try {
                final p = await _catalogo.obtenerProducto(item.productoId);
                if (!mounted) return;
                Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (_) => ProductoDetalleScreen(producto: p)),
                );
              } catch (e) {
                if (mounted) {
                  ScaffoldMessenger.of(context)
                      .showSnackBar(SnackBar(content: Text(e.toString())));
                }
              }
            },
            acciones: Wrap(
              spacing: 4,
              children: [
                TextButton(
                  onPressed: () => CarritoStore.instancia
                      .agregar(varianteId: item.varianteId, cantidad: 1),
                  child: const Text('Al carrito'),
                ),
                TextButton(
                  onPressed: () => BolsaStore.instancia.agregar(
                    varianteId: item.varianteId,
                    nombrePrenda: item.nombre,
                    sku: 'Búsqueda',
                    precio: item.precio,
                  ),
                  child: const Text('Reservar'),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _listaFallback() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 8),
        const Text('Resultados de búsqueda textual:',
            style: TextStyle(fontWeight: FontWeight.w700)),
        for (final p in _fallback)
          ListTile(
            leading: const Icon(Icons.checkroom_outlined),
            title: Text(p.nombre, maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text(p.marca ?? '',
                maxLines: 1, overflow: TextOverflow.ellipsis),
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(
                  builder: (_) => ProductoDetalleScreen(producto: p)),
            ),
          ),
      ],
    );
  }
}
