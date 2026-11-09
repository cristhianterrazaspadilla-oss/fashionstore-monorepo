// Servicio Ciclo 3 — Carrito de compra del canal MOVIL (CU14).
//
// El carrito es independiente de la bolsa de reserva: nunca mezcla IDs,
// estados ni almacenamiento con BolsaStore. Los totales provienen del backend.
import 'package:uuid/uuid.dart';

import '../models/carrito_model.dart';
import '../../../core/network/api_client.dart';

class CarritoService {
  static const String canalMovil = 'MOVIL';
  final ApiClient _api;
  CarritoService({ApiClient? api}) : _api = api ?? ApiClient();

  Future<CarritoCompra> obtenerOCrear() {
    return _api.get<CarritoCompra>(
      '/carritos/mio',
      query: const {'canal': canalMovil},
      convertir: (j) =>
          CarritoCompra.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<CarritoCompra> agregar({
    required String varianteId,
    required int cantidad,
    String? claveIdempotencia,
  }) {
    return _api.post<CarritoCompra>(
      '/carritos/mio/lineas',
      query: const {'canal': canalMovil},
      cuerpo: {'variante_id': varianteId, 'cantidad': cantidad},
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) =>
          CarritoCompra.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<CarritoCompra> cambiarCantidad({
    required String varianteId,
    required int cantidad,
    String? claveIdempotencia,
  }) {
    return _api.patch<CarritoCompra>(
      '/carritos/mio/lineas/$varianteId',
      query: const {'canal': canalMovil},
      cuerpo: {'cantidad': cantidad},
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) =>
          CarritoCompra.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<CarritoCompra> eliminarLinea({
    required String varianteId,
    String? claveIdempotencia,
  }) {
    return _api.delete<CarritoCompra>(
      '/carritos/mio/lineas/$varianteId',
      query: const {'canal': canalMovil},
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) =>
          CarritoCompra.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<CarritoCompra> vaciar({String? claveIdempotencia}) {
    return _api.delete<CarritoCompra>(
      '/carritos/mio',
      query: const {'canal': canalMovil},
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) =>
          CarritoCompra.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<CoberturaCarrito> cobertura() {
    return _api.get<CoberturaCarrito>(
      '/carritos/mio/cobertura',
      query: const {'canal': canalMovil},
      convertir: (j) =>
          CoberturaCarrito.fromJson((j as Map).cast<String, dynamic>()),
    );
  }
}
