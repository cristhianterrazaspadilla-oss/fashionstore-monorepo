// Servicio Ciclo 3 — Cotización, pedidos y seguimiento (CU16).
//
// La app solo consulta el estado; no avanza estados operativos. Solo puede
// cancelar cuando el pedido lo permite (SOLICITADO + PENDIENTE_PAGO).
import '../models/entrega_model.dart';
import '../../../core/network/api_client.dart';

class EntregaService {
  final ApiClient _api;
  EntregaService({ApiClient? api}) : _api = api ?? ApiClient();

  Future<CotizacionDelivery> cotizar({
    required String sucursalId,
    required int anilloDestino,
  }) {
    return _api.get<CotizacionDelivery>(
      '/entregas/cotizacion',
      query: {'sucursal_id': sucursalId, 'anillo_destino': '$anilloDestino'},
      convertir: (j) =>
          CotizacionDelivery.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<PedidoLista> misPedidos({int limit = 50, int offset = 0}) {
    return _api.get<PedidoLista>(
      '/entregas/mis-pedidos',
      query: {'limit': '$limit', 'offset': '$offset'},
      convertir: (j) =>
          PedidoLista.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<Pedido> obtenerPedido(String pedidoId) {
    return _api.get<Pedido>(
      '/entregas/$pedidoId',
      convertir: (j) => Pedido.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<Pedido> cancelarPedido(String pedidoId) {
    return _api.post<Pedido>(
      '/entregas/$pedidoId/cancelar',
      convertir: (j) => Pedido.fromJson((j as Map).cast<String, dynamic>()),
    );
  }
}
