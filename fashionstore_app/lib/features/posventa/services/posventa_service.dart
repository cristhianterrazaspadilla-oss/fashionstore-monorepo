import 'package:uuid/uuid.dart';
import '../../../core/network/api_client.dart';
import '../models/posventa_models.dart';

/// Servicio de Posventa para la App Móvil:
/// - CU09: Saldo personal y movimientos
/// - CU08: Cambios de prendas
/// - CU20: Devoluciones en período voluntario
/// - CU27: Consulta y seguimiento de reembolsos
class PosventaService {
  final ApiClient _api;

  PosventaService({ApiClient? api}) : _api = api ?? ApiClient();

  // ---------------- CU09: Saldo ----------------
  Future<SaldoClienteModel> obtenerMiSaldo() {
    return _api.get<SaldoClienteModel>(
      '/saldos/mio',
      convertir: (j) =>
          SaldoClienteModel.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  // ---------------- CU20: Devoluciones ----------------
  Future<List<DevolucionModel>> obtenerMisDevoluciones() {
    return _api.get<List<DevolucionModel>>(
      '/devoluciones/mias',
      convertir: (j) {
        if (j is List) {
          return j
              .map((e) => DevolucionModel.fromJson((e as Map).cast<String, dynamic>()))
              .toList();
        }
        return [];
      },
    );
  }

  Future<DevolucionModel> solicitarDevolucion({
    required String ventaId,
    required String motivo,
    required List<Map<String, dynamic>> lineas,
    String motivoCodigo = 'OTRO',
    List<String> evidenciaRefs = const [],
    String? claveIdempotencia,
  }) {
    return _api.post<DevolucionModel>(
      '/devoluciones/solicitudes',
      cuerpo: {
        'venta_id': ventaId,
        'motivo_codigo': motivoCodigo,
        'motivo_descripcion': motivo,
        'lineas': lineas,
        'evidencia_refs': evidenciaRefs,
      },
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) =>
          DevolucionModel.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  // ---------------- CU08: Cambios ----------------
  Future<List<CambioModel>> obtenerMisCambios() {
    return _api.get<List<CambioModel>>(
      '/cambios/mios',
      convertir: (j) {
        if (j is List) {
          return j
              .map((e) => CambioModel.fromJson((e as Map).cast<String, dynamic>()))
              .toList();
        }
        return [];
      },
    );
  }

  Future<CambioModel> solicitarCambio({
    required String ventaId,
    required String sucursalId,
    required String motivoCodigo,
    String? motivoDescripcion,
    required List<Map<String, dynamic>> lineasOriginales,
    List<Map<String, dynamic>> reemplazos = const [],
    String modalidadReemplazo = 'RECOJO',
    String? direccion,
    String? claveIdempotencia,
  }) {
    return _api.post<CambioModel>(
      '/cambios',
      cuerpo: {
        'venta_id': ventaId,
        'sucursal_id': sucursalId,
        'motivo_codigo': motivoCodigo,
        if (motivoDescripcion != null) 'motivo_descripcion': motivoDescripcion,
        'lineas_originales': lineasOriginales,
        'reemplazos': reemplazos,
        'modalidad_reemplazo': modalidadReemplazo,
        if (direccion != null) 'direccion': direccion,
      },
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) => CambioModel.fromJson((j as Map).cast<String, dynamic>()),
    );
  }

  Future<Map<String, dynamic>> resolverDiferenciaCambio({
    required String cambioId,
    required String destinoDiferencia, // SALDO | REEMBOLSO | PAGO_CLIENTE | SIN_DIFERENCIA
    double? saldoBob,
    double? reembolsoBob,
    String? claveIdempotencia,
  }) {
    return _api.post<Map<String, dynamic>>(
      '/cambios/$cambioId/resolver-diferencia',
      cuerpo: {
        'destino_diferencia': destinoDiferencia,
        if (saldoBob != null) 'saldo_bob': saldoBob,
        if (reembolsoBob != null) 'reembolso_bob': reembolsoBob,
      },
      idempotencyKey: claveIdempotencia ?? const Uuid().v4(),
      convertir: (j) => (j as Map).cast<String, dynamic>(),
    );
  }

  // ---------------- CU27: Reembolsos ----------------
  Future<List<ReembolsoModel>> obtenerMisReembolsos() {
    return _api.get<List<ReembolsoModel>>(
      '/reembolsos/mios',
      convertir: (j) {
        if (j is List) {
          return j
              .map((e) => ReembolsoModel.fromJson((e as Map).cast<String, dynamic>()))
              .toList();
        }
        return [];
      },
    );
  }
}
