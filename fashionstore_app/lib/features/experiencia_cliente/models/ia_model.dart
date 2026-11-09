// Modelos Ciclo 3 — IA para cliente: recomendaciones y búsqueda (CU18/CU20).
//
// - POST /ia/recomendaciones {limite, categoria?, talla?}
// - POST /ia/busqueda {texto} (texto ya transcripto; sin audio)
// - POST /ia/navegacion {evento, variante_id?, producto_id?}
// La IA es de solo lectura: no crea carrito, reserva, venta ni inventario.

double _aDouble(dynamic v, [double fb = 0]) {
  if (v == null) return fb;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? fb;
}

class RecomendacionItem {
  final String productoId;
  final String varianteId;
  final String nombre;
  final double precio;
  final int disponible;
  final String motivo;

  RecomendacionItem({
    required this.productoId,
    required this.varianteId,
    required this.nombre,
    required this.precio,
    required this.disponible,
    required this.motivo,
  });

  factory RecomendacionItem.fromJson(Map<String, dynamic> j) =>
      RecomendacionItem(
        productoId: '${j['producto_id'] ?? ''}',
        varianteId: '${j['variante_id'] ?? ''}',
        nombre: '${j['nombre'] ?? 'Prenda sugerida'}',
        precio: _aDouble(j['precio']),
        disponible: (j['disponible'] as num?)?.toInt() ?? 0,
        motivo: '${j['motivo'] ?? ''}',
      );
}

class RecomendacionRespuesta {
  final List<RecomendacionItem> items;
  final String proveedor;

  RecomendacionRespuesta({required this.items, required this.proveedor});

  factory RecomendacionRespuesta.fromJson(Map<String, dynamic> j) =>
      RecomendacionRespuesta(
        items: ((j['items'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => RecomendacionItem.fromJson(e.cast<String, dynamic>()))
            .toList(),
        proveedor: '${j['proveedor'] ?? 'DETERMINISTA'}',
      );

  bool get estaVacia => items.isEmpty;
}

/// Interpretación de búsqueda por voz/texto (BusquedaRespuestaDTO).
class InterpretacionBusqueda {
  final Map<String, dynamic> filtros;
  final int total;
  final List<RecomendacionItem> items;
  final String proveedor;

  InterpretacionBusqueda({
    required this.filtros,
    required this.total,
    required this.items,
    required this.proveedor,
  });

  factory InterpretacionBusqueda.fromJson(Map<String, dynamic> j) =>
      InterpretacionBusqueda(
        filtros: ((j['filtros'] as Map?) ?? {}).cast<String, dynamic>(),
        total: (j['total'] as num?)?.toInt() ?? 0,
        items: ((j['items'] as List?) ?? [])
            .whereType<Map>()
            .map((e) => RecomendacionItem.fromJson(e.cast<String, dynamic>()))
            .toList(),
        proveedor: '${j['proveedor'] ?? 'DETERMINISTA'}',
      );

  bool get sinCoincidencias => items.isEmpty;
}
