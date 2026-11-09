import 'dart:async';
import 'dart:convert';
import 'package:uuid/uuid.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/session/dispositivo_helper.dart';
import '../../../core/session/session_manager.dart';
import '../../../core/storage/local_database_service.dart';
import '../../../core/utils/bolivia_time.dart';
import '../models/reserva_model.dart';
import '../models/sincronizacion_model.dart';

/// Servicio para registrar y sincronizar reservas offline según CU04 (revisión 0.3.2).
///
/// - Emisión y almacenamiento de referencias horarias en SQLite.
/// - Registro de reservas offline en transacción SQLite con estado PENDIENTE_ENVIO.
/// - Sincronización automática o manual al recuperar red con la app ejecutándose.
/// - Control de reentradas durante la sincronización activa.
/// - Consulta por UUID original antes de reintentar operaciones que quedaron en ENVIANDO.
/// - Persistencia durable de resultados (ACEPTADA, RECHAZADA, CONFLICTO) en SQLite.
/// - Respeto estricto de la ventana privada de 8 horas desde login online y aislamiento por cuenta.
class SincronizacionOfflineService {
  final ApiClient _api;
  final LocalDatabaseService _storage;
  final SessionManager _sesiones;
  bool _sincronizando = false;
  Timer? _timerMonitoreo;

  SincronizacionOfflineService({
    ApiClient? api,
    LocalDatabaseService? storage,
    SessionManager? sesiones,
  })  : _api = api ?? ApiClient(),
        _storage = storage ?? LocalDatabaseService(),
        _sesiones = sesiones ?? SessionManager();

  /// Emite y guarda una referencia horaria del servidor central cuando hay conexión.
  Future<ReferenciaHorariaModel> emitirYGuardarReferencia({
    String? empresaId,
    String? usuarioId,
    String? dispositivoId,
  }) async {
    final sesion = await _sesiones.leerValida();
    final empId = (sesion?.usuario.empresaId != null && sesion!.usuario.empresaId!.isNotEmpty)
        ? sesion.usuario.empresaId!
        : (empresaId ?? '');
    final usrId = usuarioId ?? sesion?.usuario.usuarioId ?? '';
    final dispId = dispositivoId ?? await DispositivoHelper.obtenerDispositivoId();

    final clave = const Uuid().v4();
    final horaBolivia = BoliviaTime.formatIso8601(BoliviaTime.now());

    // Intentar POST canónico /sincronizacion/referencias-horarias
    try {
      final ref = await _api.post<ReferenciaHorariaModel>(
        '/sincronizacion/referencias-horarias',
        idempotencyKey: clave,
        cuerpo: {
          'dispositivo_id': dispId,
          'hora_local_en': horaBolivia,
        },
        convertir: (j) => ReferenciaHorariaModel.fromJson(
          (j as Map).cast<String, dynamic>(),
          fallbackEmpresaId: empId,
          fallbackUsuarioId: usrId,
          fallbackDispositivoId: dispId,
        ),
      );
      await _storage.guardarReferenciaHoraria(ref);
      return ref;
    } on ApiException catch (e) {
      if (e.statusCode == 404 || e.statusCode == 405) {
        // Adaptador de compatibilidad: GET /sincronizacion/referencia-horaria
        final refLegacy = await _api.get<ReferenciaHorariaModel>(
          '/sincronizacion/referencia-horaria',
          query: {'dispositivo_id': dispId},
          convertir: (j) => ReferenciaHorariaModel.fromJson(
            (j as Map).cast<String, dynamic>(),
            fallbackEmpresaId: empId,
            fallbackUsuarioId: usrId,
            fallbackDispositivoId: dispId,
          ),
        );
        await _storage.guardarReferenciaHoraria(refLegacy);
        return refLegacy;
      }
      rethrow;
    }
  }

  /// Alias de conveniencia para emisión/almacenamiento de referencia horaria.
  Future<ReferenciaHorariaModel> obtenerOGenerarReferencia({
    String? empresaId,
    String? usuarioId,
    String? dispositivoId,
  }) =>
      emitirYGuardarReferencia(
        empresaId: empresaId,
        usuarioId: usuarioId,
        dispositivoId: dispositivoId,
      );

  /// Crea una reserva offline atómicamente en SQLite antes de mostrar PENDIENTE_ENVIO.
  /// Exige una referencia horaria válida en SQLite (CU04 0.3.2).
  Future<OperacionSincronizacionLocal> registrarReservaOffline({
    required String empresaId,
    String? usuarioId,
    String? dispositivoId,
    required String sucursalId,
    dynamic visitaEn,
    dynamic fechaVisitaEstimada,
    required dynamic items,
    String? notas,
  }) async {
    String usrId = usuarioId ?? '';
    String dispId = dispositivoId ?? '';
    String empId = empresaId;

    final sesion = await _sesiones.leerValida();
    if (sesion != null) {
      if (!BoliviaTime.dentroDeVentana8Horas(sesion.guardadaEn)) {
        throw const ApiException(
          statusCode: 401,
          mensaje:
              'La ventana de 8 horas de tu sesión expiró. Inicia sesión conectado.',
        );
      }
      if (usrId.isEmpty) {
        usrId = sesion.usuario.usuarioId;
      }
      if (sesion.usuario.empresaId != null &&
          sesion.usuario.empresaId!.isNotEmpty &&
          (empId.isEmpty || empId == 'fashionstore')) {
        empId = sesion.usuario.empresaId!;
      }
    } else if (usrId.isEmpty) {
      throw const ApiException(
        statusCode: 401,
        mensaje: 'Inicia sesión para registrar una reserva.',
      );
    }

    if (dispId.isEmpty) {
      dispId = await DispositivoHelper.obtenerDispositivoId();
    }

    DateTime visitaDateTime;
    final v = visitaEn ?? fechaVisitaEstimada;
    if (v is DateTime) {
      visitaDateTime = v;
    } else if (v is String) {
      visitaDateTime =
          DateTime.tryParse(v) ?? DateTime.now().add(const Duration(days: 1));
    } else {
      visitaDateTime = DateTime.now().add(const Duration(days: 1));
    }

    List<Map<String, dynamic>> lineas;
    if (items is List<ItemBolsa>) {
      lineas = items
          .map((e) => {
                'variante_id': e.varianteId,
                'cantidad': e.cantidad,
              })
          .toList();
    } else if (items is List) {
      lineas = items.map((e) {
        if (e is ItemBolsa) {
          return {'variante_id': e.varianteId, 'cantidad': e.cantidad};
        }
        final m = (e as Map).cast<String, dynamic>();
        return {
          'variante_id': '${m['variante_id'] ?? ''}',
          'cantidad': (m['cantidad'] as num?)?.toInt() ?? 1,
        };
      }).toList();
    } else {
      lineas = [];
    }

    // Obtener referencia horaria activa en SQLite
    final ref = await _storage.obtenerReferenciaHorariaValida(
      empresaId: empId,
      usuarioId: usrId,
    );

    if (ref == null || ref.id.isEmpty) {
      throw const ApiException(
        statusCode: 428,
        mensaje:
            'No cuentas con una referencia horaria válida emitida por el servidor. Conéctate a internet para sincronizar la hora civil antes de registrar nuevas reservas.',
      );
    }

    final secuencia = await _storage.obtenerSiguienteSecuencia(
      dispositivoId: dispId,
      usuarioId: usrId,
    );

    final operacionId = const Uuid().v4();
    final creadaLocalEn = BoliviaTime.formatIso8601(BoliviaTime.now());

    // Contrato estricto 0.3.2: datos solo admite sucursal_id, visita_en y lineas
    final datosJson = jsonEncode({
      'sucursal_id': sucursalId,
      'visita_en': BoliviaTime.formatIso8601(visitaDateTime),
      'lineas': lineas,
    });

    final op = OperacionSincronizacionLocal(
      operacionId: operacionId,
      empresaId: empId,
      usuarioId: usrId,
      dispositivoId: dispId,
      secuenciaLocal: secuencia,
      referenciaHorariaId: ref.id,
      creadaLocalEn: creadaLocalEn,
      datosJson: datosJson,
      estadoEnvio: 'PENDIENTE_ENVIO',
      actualizadoEn: DateTime.now().toUtc().toIso8601String(),
    );

    await _storage.encolarOperacion(op);
    return op;
  }

  /// Encola una operación de compra offline (CU05 v3) en SQLite con consentimiento exacto y autorización de cobro.
  Future<OperacionSincronizacionLocal> encolarCompraOffline({
    required String sucursalId,
    required List<Map<String, dynamic>> lineas,
    String modalidad = 'RECOJO',
    String? direccion,
    int? anilloDestino,
    Map<String, dynamic>? autorizacionCobro,
    String? empresaId,
    String? usuarioId,
    String? dispositivoId,
  }) async {
    final sesion = await _sesiones.leerValida();
    final empId = (sesion?.usuario.empresaId != null && sesion!.usuario.empresaId!.isNotEmpty)
        ? sesion.usuario.empresaId!
        : (empresaId ?? '');
    final usrId = usuarioId ?? sesion?.usuario.usuarioId ?? '';
    final dispId = dispositivoId ?? await DispositivoHelper.obtenerDispositivoId();

    if (empId.isEmpty || usrId.isEmpty) {
      throw StateError('No hay sesión válida para encolar compra offline');
    }

    final ref = await _storage.obtenerReferenciaHorariaValida(
      empresaId: empId,
      usuarioId: usrId,
    );
    if (ref == null) {
      throw StateError('No hay referencia horaria válida (8h) para operar offline');
    }

    final secuencia = await _storage.obtenerSiguienteSecuencia(
      dispositivoId: dispId,
      usuarioId: usrId,
    );

    final operacionId = const Uuid().v4();
    final creadaLocalEn = BoliviaTime.formatIso8601(BoliviaTime.now());

    final datosJson = jsonEncode({
      '_tipo_operacion': 'SOLICITAR_COMPRA',
      'sucursal_id': sucursalId,
      'modalidad': modalidad,
      if (direccion != null) 'direccion': direccion,
      if (anilloDestino != null) 'anillo_destino': anilloDestino,
      'lineas': lineas,
      if (autorizacionCobro != null) 'autorizacion_cobro': autorizacionCobro,
    });

    final op = OperacionSincronizacionLocal(
      operacionId: operacionId,
      empresaId: empId,
      usuarioId: usrId,
      dispositivoId: dispId,
      secuenciaLocal: secuencia,
      referenciaHorariaId: ref.id,
      creadaLocalEn: creadaLocalEn,
      datosJson: datosJson,
      estadoEnvio: 'PENDIENTE_ENVIO',
      actualizadoEn: DateTime.now().toUtc().toIso8601String(),
    );

    await _storage.encolarOperacion(op);
    return op;
  }

  /// Sincroniza todas las operaciones pendientes de la empresa y usuario activo.
  /// Se ejecuta con la app abierta al detectar red, con control de reentradas.
  Future<List<ResultadoOperacionDTO>> sincronizarPendientes({
    String? empresaId,
    String? usuarioId,
  }) async {
    if (_sincronizando) return const [];
    _sincronizando = true;

    try {
      final sesion = await _sesiones.leerValida();
      String empId = empresaId ?? '';
      String usrId = usuarioId ?? '';

      if (sesion != null) {
        if (!BoliviaTime.dentroDeVentana8Horas(sesion.guardadaEn)) {
          return const [];
        }
        usrId = sesion.usuario.usuarioId;
        if (sesion.usuario.empresaId != null &&
            sesion.usuario.empresaId!.isNotEmpty) {
          empId = sesion.usuario.empresaId!;
        }
      } else if (usrId.isEmpty) {
        return const [];
      }

      if (empId.isEmpty || usrId.isEmpty) {
        return const [];
      }

      final pendientes = await _storage.listarOperacionesCola(
        empresaId: empId,
        usuarioId: usrId,
        estados: ['PENDIENTE_ENVIO', 'ENVIANDO'],
      );

      final resultados = <ResultadoOperacionDTO>[];

      for (final op in pendientes) {
        if (op.estadoEnvio == 'ENVIANDO') {
          // Consultar primero por UUID original antes de reenviar
          try {
            final res = await _api.get<ResultadoOperacionDTO>(
              '/sincronizacion/operaciones/${op.operacionId}',
              convertir: (j) => ResultadoOperacionDTO.fromJson(
                  (j as Map).cast<String, dynamic>()),
            );
            await _storage.actualizarEstadoOperacion(
              op.operacionId,
              res.estado,
              resultadoJson: res.toJson(),
            );
            resultados.add(res);
            continue;
          } on ApiException catch (e) {
            if (e.statusCode != 404) {
              // Error de transporte o sesión: dejar en ENVIANDO y continuar luego
              continue;
            }
            // 404: el servidor aún no la recibió, procedemos a enviarla abajo
          } catch (_) {
            continue;
          }
        }

        // Marcar como ENVIANDO en SQLite antes de la llamada de red
        await _storage.actualizarEstadoOperacion(op.operacionId, 'ENVIANDO');

        try {
          final res = await _api.post<ResultadoOperacionDTO>(
            '/sincronizacion/operaciones',
            cuerpo: op.toApiPayload(),
            convertir: (j) => ResultadoOperacionDTO.fromJson(
                (j as Map).cast<String, dynamic>()),
          );

          await _storage.actualizarEstadoOperacion(
            op.operacionId,
            res.estado,
            resultadoJson: res.toJson(),
          );
          resultados.add(res);
        } on ApiException catch (e) {
          if (e.statusCode == 409) {
            // Conflicto durable (operación modificada u otro)
            final conf = ResultadoOperacionDTO(
              operacionId: op.operacionId,
              estado: 'CONFLICTO',
              codigo: 'OPERACION_MODIFICADA',
              recibidaEn: BoliviaTime.formatIso8601(BoliviaTime.now()),
              detalle: e.mensaje,
            );
            await _storage.actualizarEstadoOperacion(
              op.operacionId,
              'CONFLICTO',
              resultadoJson: conf.toJson(),
            );
            resultados.add(conf);
          } else if (e.statusCode == 422 || e.statusCode == 400) {
            final rech = ResultadoOperacionDTO(
              operacionId: op.operacionId,
              estado: 'RECHAZADA',
              codigo: 'DATOS_INVALIDOS',
              recibidaEn: BoliviaTime.formatIso8601(BoliviaTime.now()),
              detalle: e.mensaje,
            );
            await _storage.actualizarEstadoOperacion(
              op.operacionId,
              'RECHAZADA',
              resultadoJson: rech.toJson(),
            );
            resultados.add(rech);
          }
          // En otros errores de transporte o 503/timeout se mantiene en ENVIANDO para consulta futura por UUID
        } catch (_) {
          // Fallo de red: permanece en ENVIANDO sin borrar
        }
      }

      return resultados;
    } finally {
      _sincronizando = false;
    }
  }

  /// Alias de conveniencia para sincronización de cola.
  Future<List<ResultadoOperacionDTO>> sincronizarCola({
    String? empresaId,
    String? usuarioId,
  }) =>
      sincronizarPendientes(empresaId: empresaId, usuarioId: usuarioId);

  /// Lista las operaciones en la cola local para el usuario y empresa autenticada.
  /// Aplica la ventana de privacidad de 8 horas.
  Future<List<OperacionSincronizacionLocal>> listarOperaciones({
    String? empresaId,
    String? usuarioId,
  }) async {
    final sesion = await _sesiones.leerValida();
    String empId = empresaId ?? '';
    String usrId = usuarioId ?? '';

    if (sesion != null) {
      if (!BoliviaTime.dentroDeVentana8Horas(sesion.guardadaEn)) {
        return const [];
      }
      usrId = sesion.usuario.usuarioId;
      if (sesion.usuario.empresaId != null &&
          sesion.usuario.empresaId!.isNotEmpty) {
        empId = sesion.usuario.empresaId!;
      }
    } else if (usrId.isEmpty) {
      return const [];
    }

    if (empId.isEmpty || usrId.isEmpty) {
      return const [];
    }

    return _storage.listarOperacionesCola(
      empresaId: empId,
      usuarioId: usrId,
    );
  }

  /// Monitoreo de red mientras la aplicación está en ejecución.
  void iniciarMonitoreoRed({Duration intervalo = const Duration(seconds: 30)}) {
    _timerMonitoreo?.cancel();
    _timerMonitoreo = Timer.periodic(intervalo, (_) async {
      final sesion = await _sesiones.leerValida();
      if (sesion != null && BoliviaTime.dentroDeVentana8Horas(sesion.guardadaEn)) {
        await sincronizarPendientes(
          empresaId: sesion.usuario.empresaId,
          usuarioId: sesion.usuario.usuarioId,
        );
      }
    });
  }

  /// Detiene el monitoreo al cerrar pantallas o app.
  void detenerMonitoreoRed() {
    _timerMonitoreo?.cancel();
    _timerMonitoreo = null;
  }
}
