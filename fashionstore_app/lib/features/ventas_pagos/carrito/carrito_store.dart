// Estado del carrito de compra (Ciclo 3, canal MOVIL).
//
// Independiente de BolsaStore (reserva): no comparte IDs, estados,
// almacenamiento, contadores, modelos ni acciones. El backend es la fuente
// de verdad para precio, promoción, disponibilidad y total; aquí solo se
// guarda metadata mínima local para recuperar el flujo.
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import '../models/carrito_model.dart';
import '../services/carrito_service.dart';

/// Clave local con metadata mínima (nunca precios ni totales como verdad).
const String claveMetaCarrito = 'fs_carrito_meta_v1';

class CarritoStore extends ChangeNotifier {
  static final CarritoStore instancia = CarritoStore._();
  CarritoStore._() : _servicio = CarritoService();

  /// Solo para pruebas (evita compartir el singleton).
  factory CarritoStore.paraPruebas({
    CarritoService? servicio,
    SharedPreferences? prefs,
  }) =>
      CarritoStore._con(servicio: servicio, prefs: prefs);

  CarritoStore._con({CarritoService? servicio, SharedPreferences? prefs})
      : _servicio = servicio ?? CarritoService(),
        _prefs = prefs;

  CarritoService _servicio;
  SharedPreferences? _prefs;

  CarritoCompra _carrito = CarritoCompra.vacio();
  bool _cargando = false;
  String? _error;
  bool _operando = false;
  String? _ultimaClave;

  CarritoCompra get carrito => _carrito;
  bool get cargando => _cargando;
  String? get error => _error;
  bool get operando => _operando;
  bool get vacio => _carrito.estaVacio;
  int get totalPrendas => _carrito.totalPrendas;

  /// Permite inyectar dobles en pruebas de widgets.
  void configurarParaPruebas({CarritoService? servicio}) {
    if (servicio != null) _servicio = servicio;
  }

  Future<SharedPreferences> _prefsAsync() async {
    final p = _prefs;
    if (p != null) return p;
    final obtenido = await SharedPreferences.getInstance();
    _prefs = obtenido;
    return obtenido;
  }

  Future<void> _guardarMetaMinima() async {
    try {
      final p = await _prefsAsync();
      await p.setString(
        claveMetaCarrito,
        jsonEncode({
          'canal': 'MOVIL',
          'actualizada_en': DateTime.now().toUtc().toIso8601String(),
          'total_prendas': _carrito.totalPrendas,
        }),
      );
    } catch (_) {}
  }

  Future<void> limpiarReferenciaLocal() async {
    _carrito = CarritoCompra.vacio();
    _error = null;
    try {
      final p = await _prefsAsync();
      await p.remove(claveMetaCarrito);
    } catch (_) {}
    notifyListeners();
  }

  Future<void> cargar() async {
    if (_cargando) return;
    _cargando = true;
    _error = null;
    notifyListeners();
    try {
      _carrito = await _servicio.obtenerOCrear();
      await _guardarMetaMinima();
    } catch (e) {
      _error = e.toString();
    } finally {
      _cargando = false;
      notifyListeners();
    }
  }

  /// Ejecuta una mutación con protección contra doble toque.
  Future<bool> _mutar(
    Future<CarritoCompra> Function(String clave) llamada, {
    String? claveReuso,
  }) async {
    if (_operando) return false;
    _operando = true;
    _error = null;
    notifyListeners();
    final clave = claveReuso ?? const Uuid().v4();
    _ultimaClave = clave;
    try {
      _carrito = await llamada(clave);
      await _guardarMetaMinima();
      return true;
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _operando = false;
      notifyListeners();
    }
  }

  Future<bool> agregar({
    required String varianteId,
    required int cantidad,
  }) =>
      _mutar((clave) => _servicio.agregar(
            varianteId: varianteId,
            cantidad: cantidad,
            claveIdempotencia: clave,
          ));

  Future<bool> cambiarCantidad({
    required String varianteId,
    required int cantidad,
  }) =>
      _mutar((clave) => _servicio.cambiarCantidad(
            varianteId: varianteId,
            cantidad: cantidad,
            claveIdempotencia: clave,
          ));

  Future<bool> eliminar(String varianteId) => _mutar(
        (clave) => _servicio.eliminarLinea(
          varianteId: varianteId,
          claveIdempotencia: clave,
        ),
      );

  Future<bool> vaciar() => _mutar(
        (clave) => _servicio.vaciar(claveIdempotencia: clave),
      );

  /// Reintenta la última mutación fallida con la misma clave de
  /// idempotencia cuando la UI lo solicita (recuperable).
  Future<bool> reintentarUltima(
    Future<CarritoCompra> Function(String clave) llamada,
  ) =>
      _mutar(llamada, claveReuso: _ultimaClave);
}
