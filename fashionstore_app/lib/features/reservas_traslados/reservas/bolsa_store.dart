import 'package:flutter/foundation.dart';

import '../models/reserva_model.dart';

/// Bolsa multiítem de reserva (estado local, sin backend hasta confirmar).
class BolsaStore extends ChangeNotifier {
  static final BolsaStore instancia = BolsaStore._();
  BolsaStore._();

  /// Solo para pruebas unitarias (evita compartir el singleton).
  factory BolsaStore.paraPruebas() => BolsaStore._();

  final List<ItemBolsa> _items = [];

  List<ItemBolsa> get items => List.unmodifiable(_items);
  bool get vacia => _items.isEmpty;
  int get totalPrendas => _items.fold(0, (a, e) => a + e.cantidad);
  double get totalEstimado =>
      _items.fold(0, (a, e) => a + e.precio * e.cantidad);

  void agregar({
    required String varianteId,
    required String nombrePrenda,
    required String sku,
    required double precio,
    int cantidad = 1,
  }) {
    final idx = _items.indexWhere((e) => e.varianteId == varianteId);
    if (idx >= 0) {
      _items[idx].cantidad += cantidad;
    } else {
      _items.add(ItemBolsa(
        varianteId: varianteId,
        nombrePrenda: nombrePrenda,
        sku: sku,
        precio: precio,
        cantidad: cantidad,
      ));
    }
    notifyListeners();
  }

  void cambiarCantidad(String varianteId, int cantidad) {
    final idx = _items.indexWhere((e) => e.varianteId == varianteId);
    if (idx < 0) return;
    if (cantidad <= 0) {
      _items.removeAt(idx);
    } else {
      _items[idx].cantidad = cantidad;
    }
    notifyListeners();
  }

  void quitar(String varianteId) {
    _items.removeWhere((e) => e.varianteId == varianteId);
    notifyListeners();
  }

  void definirOrigen(
      String varianteId, String? origenId, String? origenNombre) {
    final idx = _items.indexWhere((e) => e.varianteId == varianteId);
    if (idx < 0) return;
    final item = _items[idx];
    final limpio =
        origenId == null || origenId.trim().isEmpty ? null : origenId.trim();
    item.origenId = limpio;
    item.origenNombre = limpio == null ? null : origenNombre;
    // Si hay origen real, el traslado queda solicitado; si se limpia el
    // origen sin desmarcar, se conserva solicitaTraslado para que la UI
    // siga mostrando el selector (corrección auditoría: no ocultar).
    if (limpio != null) item.solicitaTraslado = true;
    notifyListeners();
  }

  /// Marca o desmarca el traslado de una línea. Al desmarcar limpia el
  /// origen; al marcar conserva el origen previo si existe.
  void solicitarTraslado(String varianteId, bool solicita) {
    final idx = _items.indexWhere((e) => e.varianteId == varianteId);
    if (idx < 0) return;
    _items[idx].fijarSolicitudTraslado(solicita);
    notifyListeners();
  }

  /// Al cambiar la sucursal destino se descartan los orígenes que ahora
  /// coinciden con el destino (origen debe ser distinto al destino).
  void alCambiarDestino(String? nuevoDestinoId) {
    if (nuevoDestinoId == null || nuevoDestinoId.isEmpty) return;
    var cambio = false;
    for (final item in _items) {
      if (item.origenId != null && item.origenId == nuevoDestinoId) {
        item.origenId = null;
        item.origenNombre = null;
        cambio = true;
      }
    }
    if (cambio) notifyListeners();
  }

  /// Líneas que piden traslado pero aún no tienen origen válido.
  List<ItemBolsa> get lineasSinOrigen =>
      _items.where((e) => e.bloqueaConfirmacion).toList();

  /// La bolsa puede confirmarse si no está vacía y ninguna línea que
  /// solicita traslado quedó sin origen.
  bool get puedeConfirmar => _items.isNotEmpty && lineasSinOrigen.isEmpty;

  void limpiar() {
    _items.clear();
    notifyListeners();
  }
}
