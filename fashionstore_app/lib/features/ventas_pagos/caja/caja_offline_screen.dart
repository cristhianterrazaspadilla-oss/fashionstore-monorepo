import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../../core/session/dispositivo_helper.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/colores.dart';
import '../../../core/ui/formato.dart';
import '../../catalogo/services/catalogo_service.dart';
import '../../organizacion/models/organizacion_model.dart';
import '../../organizacion/services/sucursal_service.dart';
import '../models/caja_model.dart';
import '../services/caja_service.dart';

/// Pantalla de Caja Móvil para personal autorizado (Cajero / Admin).
///
/// Permite:
/// 1. Habilitar turno online con cupos autorizados de prendas y sucursal asignada.
/// 2. Registrar cobro de venta física en efectivo sin red con comprobante inmediato.
/// 3. Visualizar y sincronizar operaciones guardadas en el equipo con el servidor.
/// 4. Cierre de turno y arqueo de efectivo con devolución de cupos.
class CajaOfflineScreen extends StatefulWidget {
  final CajaService? servicioCaja;
  final SucursalService? servicioSucursal;
  final CatalogoService? servicioCatalogo;

  const CajaOfflineScreen({
    super.key,
    this.servicioCaja,
    this.servicioSucursal,
    this.servicioCatalogo,
  });

  @override
  State<CajaOfflineScreen> createState() => _CajaOfflineScreenState();
}

class _CajaOfflineScreenState extends State<CajaOfflineScreen> {
  late final CajaService _cajaSrv;
  late final SucursalService _sucursalSrv;
  late final CatalogoService _catalogoSrv;

  bool _cargando = true;
  bool _cargandoVariantes = false;
  bool _sincronizando = false;
  bool _esSupervisor = false;
  String? _operacionLocalId;
  DateTime? _fechaLocalOperacion;
  int _legadoPendiente = 0;
  String? _error;
  String? _errorEstadisticas;

  TurnoHabilitacionModel? _turno;
  List<VentaOfflineCrearModel> _pendientes = [];
  List<ComprobanteLocalModel> _comprobantes = [];
  List<SucursalModel> _sucursales = [];
  List<VarianteCajaDisponibleModel> _variantesDisponibles = [];

  // Formulario Habilitación
  String? _sucursalSel;
  final _codigoCajaCtrl = TextEditingController(text: 'CAJA-MOVIL-01');
  final Map<String, int> _cuposSolicitados = {};
  VarianteCajaDisponibleModel? _varianteSelParaCupo;
  int _cantidadCupo = 1;

  // Formulario Venta Offline
  String? _cupoSeleccionadoId;
  CupoRespuestaModel? get _cupoSeleccionado {
    final turno = _turno;
    if (turno == null) return null;
    for (final cupo in turno.cupos) {
      if (cupo.varianteId == _cupoSeleccionadoId) return cupo;
    }
    return null;
  }

  set _cupoSeleccionado(CupoRespuestaModel? cupo) {
    _cupoSeleccionadoId = cupo?.varianteId;
  }

  int _stockRestanteParaCupo(VarianteCajaDisponibleModel? variante) {
    if (variante == null) return 0;
    return (variante.stockDisponible -
            (_cuposSolicitados[variante.varianteId] ?? 0))
        .clamp(0, variante.stockDisponible);
  }

  int _cantidadVenta = 1;
  final _efectivoRecibidoCtrl = TextEditingController();
  final _clienteIdCtrl = TextEditingController();

  // Formulario Cierre
  final _arqueoCtrl = TextEditingController();
  final _motivoSupervisionCtrl = TextEditingController();
  final _referenciaActaCtrl = TextEditingController();
  final Map<String, TextEditingController> _conteosFisicosCtrl = {};
  final Map<String, String?> _resolucionFaltante = {};
  final Map<String, TextEditingController> _motivosFaltanteCtrl = {};

  @override
  void initState() {
    super.initState();
    _cajaSrv = widget.servicioCaja ?? CajaService();
    _sucursalSrv = widget.servicioSucursal ?? SucursalService();
    _catalogoSrv = widget.servicioCatalogo ?? CatalogoService();
    _inicializar();
  }

  @override
  void dispose() {
    _codigoCajaCtrl.dispose();
    _efectivoRecibidoCtrl.dispose();
    _clienteIdCtrl.dispose();
    _arqueoCtrl.dispose();
    _motivoSupervisionCtrl.dispose();
    _referenciaActaCtrl.dispose();
    for (final controller in _conteosFisicosCtrl.values) {
      controller.dispose();
    }
    for (final controller in _motivosFaltanteCtrl.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _inicializar() async {
    setState(() {
      _cargando = true;
      _error = null;
    });

    try {
      // 1. Restaurar primero de almacenamiento local por si la app fue reiniciada
      await _cajaSrv.restaurarDesdeStorage();
      final sesion = await _cajaSrv.sesiones.leerValida();
      final rol = sesion?.usuario.rol.toUpperCase() ?? '';
      final esSupervisor = const {
        'ADMINISTRADOR',
        'PROPIETARIO',
        'ENCARGADO',
      }.contains(rol);

      // 2. Intentar consultar estado activo online/local
      final turno = await _cajaSrv.consultarTurnoActivo();

      // 3. Cargar sucursales activas
      List<SucursalModel> sucs = [];
      try {
        sucs = await _sucursalSrv.listar();
      } catch (_) {}

      final sucursalesActivas = sucs.where((s) => s.activa).toList();
      final sucursalInicial = _sucursalSel ??
          (sucursalesActivas.isNotEmpty ? sucursalesActivas.first.id : null);

      // 4. Cargar variantes disponibles para la sucursal seleccionada
      List<VarianteCajaDisponibleModel> vars = [];
      try {
        vars = await _catalogoSrv.listarVariantesParaCaja(
            sucursalId: sucursalInicial);
      } catch (_) {}

      _legadoPendiente = await _cajaSrv.diagnosticosRecuperacion();
      // 5. Cargar comprobantes locales si hay turno
      List<ComprobanteLocalModel> comps = [];
      String? errorEstadisticas;
      if (turno != null) {
        try {
          comps = await _cajaSrv.listarComprobantesLocales(turno.turnoId);
        } catch (_) {}

        // Verificar que las estadísticas de ventas locales sean legibles sin error
        try {
          await _cajaSrv.obtenerEstadisticasVentasTurno(turno.turnoId);
        } catch (e) {
          errorEstadisticas =
              'Error al leer operaciones locales de caja: $e. Cierre de turno bloqueado por seguridad.';
        }
      }

      _prepararControladoresConteo(turno);

      if (!mounted) return;
      setState(() {
        _esSupervisor = esSupervisor;
        _turno = turno;
        _sucursales = sucursalesActivas;
        _sucursalSel = sucursalInicial;
        _variantesDisponibles = vars;
        if (vars.isNotEmpty && _varianteSelParaCupo == null) {
          _varianteSelParaCupo = vars.first;
        }
        _operacionLocalId = null; _fechaLocalOperacion = null;
        _pendientes = _cajaSrv.ventasOfflinePendientes;
        _comprobantes = comps;
        _errorEstadisticas = errorEstadisticas;
        _cargando = false;
        if (turno != null && turno.cupos.isNotEmpty) {
          _cupoSeleccionado = turno.cupos.firstWhere(
            (c) => c.disponible > 0,
            orElse: () => turno.cupos.first,
          );
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _cargando = false;
      });
    }
  }

  void _prepararControladoresConteo(TurnoHabilitacionModel? turno,
      {bool reiniciar = true}) {
    final ids = turno?.cupos.map((c) => c.varianteId).toSet() ?? <String>{};
    for (final id in _conteosFisicosCtrl.keys.toList()) {
      if (!ids.contains(id)) {
        _conteosFisicosCtrl.remove(id)?.dispose();
        _motivosFaltanteCtrl.remove(id)?.dispose();
        _resolucionFaltante.remove(id);
      }
    }
    for (final cupo in turno?.cupos ?? const <CupoRespuestaModel>[]) {
      final conteo = _conteosFisicosCtrl.putIfAbsent(
        cupo.varianteId,
        () => TextEditingController(),
      );
      if (reiniciar || conteo.text.isEmpty) {
        conteo.text = cupo.disponible.toString();
      }
      _motivosFaltanteCtrl.putIfAbsent(
        cupo.varianteId,
        () => TextEditingController(),
      );
    }
  }

  int? _conteoFisico(CupoRespuestaModel cupo) =>
      int.tryParse(_conteosFisicosCtrl[cupo.varianteId]?.text.trim() ?? '');

  List<String> _erroresResolucionSupervisada(TurnoHabilitacionModel turno) {
    final errores = <String>[];
    if (!_esSupervisor) {
      errores.add('Solo una persona supervisora puede cerrar la conciliación.');
    }
    if (turno.estado != 'CONCILIACION' && turno.estado != 'RECUPERACION') {
      errores.add('El turno aún no requiere una resolución supervisada.');
    }
    if (_pendientes.isNotEmpty) {
      errores.add('Sincroniza las ventas pendientes antes del conteo final.');
    }
    if (_referenciaActaCtrl.text.trim().isEmpty) {
      errores
          .add('Ingresa la referencia del acta o registro de conteo físico.');
    }
    if (_motivoSupervisionCtrl.text.trim().length < 3) {
      errores.add('Describe el motivo del cierre supervisado.');
    }
    final arqueo =
        double.tryParse(_arqueoCtrl.text.trim().replaceAll(',', '.'));
    if (arqueo == null || arqueo < 0) {
      errores.add(
          'Ingresa un arqueo de efectivo válido, incluido Bs 0 si corresponde.');
    }

    for (final cupo in turno.cupos) {
      final cantidad = _conteoFisico(cupo);
      if (cantidad == null || cantidad < 0) {
        errores.add(
            'Registra un conteo válido para ${cupo.sku ?? cupo.varianteId}.');
        continue;
      }
      if (cantidad > cupo.disponible) {
        errores.add(
            'El conteo de ${cupo.sku ?? cupo.varianteId} supera las unidades pendientes del cupo.');
        continue;
      }
      final faltante = cupo.disponible - cantidad;
      if (faltante > 0) {
        final resolucion = _resolucionFaltante[cupo.varianteId];
        final motivo = _motivosFaltanteCtrl[cupo.varianteId]?.text.trim() ?? '';
        if (resolucion == null) {
          errores.add(
              'Indica cómo resolver el faltante de ${cupo.sku ?? cupo.varianteId}.');
        } else if (motivo.length < (resolucion == 'MERMA' ? 10 : 3)) {
          errores.add(resolucion == 'MERMA'
              ? 'La causa de merma requiere al menos 10 caracteres.'
              : 'Describe por qué el faltante queda pendiente de sincronización.');
        }
      }
    }
    return errores;
  }

  Future<void> _resolverCierreSupervisado() async {
    final turno = _turno;
    if (turno == null || !_esSupervisor) return;
    final errores = _erroresResolucionSupervisada(turno);
    if (errores.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(errores.first), backgroundColor: ColoresFS.danger),
      );
      return;
    }

    final conteos = turno.cupos
        .map((cupo) => {
              'variante_id': cupo.varianteId,
              'cantidad_encontrada': _conteoFisico(cupo)!,
            })
        .toList();
    final resoluciones = <Map<String, dynamic>>[];
    for (final cupo in turno.cupos) {
      final cantidad = _conteoFisico(cupo)!;
      if (cantidad < cupo.disponible) {
        resoluciones.add({
          'variante_id': cupo.varianteId,
          'resolucion': _resolucionFaltante[cupo.varianteId],
          'motivo': _motivosFaltanteCtrl[cupo.varianteId]!.text.trim(),
        });
      }
    }

    final arqueo = double.parse(_arqueoCtrl.text.trim().replaceAll(',', '.'));
    setState(() => _cargando = true);
    try {
      final stats =
          await _cajaSrv.obtenerEstadisticasVentasTurno(turno.turnoId);
      final resultado = await _cajaSrv.cerrarTurno(
        turno.turnoId,
        TurnoCerrarModel(
          revision: turno.revision,
          ultimaSecuenciaLocal: stats['ultima_secuencia'],
          totalOperacionesLocales: stats['total_operaciones'],
          operacionesPendientes: const [],
          arqueoEfectivoBob: arqueo,
          arqueoDeclaradoBob: arqueo,
          supervisionForzada: true,
          motivoSupervision: _motivoSupervisionCtrl.text.trim(),
          evidenciaCierre: {
            'referencia_acta': _referenciaActaCtrl.text.trim(),
            'conteo_fisico_por_variante': conteos,
          },
          ajustesInventario: {
            'resoluciones_por_variante': resoluciones,
          },
        ),
      );

      if (!mounted) return;
      if (resultado.estado == 'CERRADO') {
        setState(() {
          _turno = null;
          _pendientes = [];
          _comprobantes = [];
          _cargando = false;
          _errorEstadisticas = null;
        });
        await _recargarVariantesCaja(turno.sucursalId);
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
              content: Text(
                  'Conciliación finalizada. El inventario fue actualizado según el conteo.')),
        );
        return;
      }

      // El backend devuelve CONCILIACION si quedan unidades pendientes de
      // sincronización. Recargar balances centrales evita cobrar sobre cupos
      // que fueron liberados o convertidos en merma durante esta revisión.
      final actualizado = await _cajaSrv.consultarTurno(turno.turnoId);
      _prepararControladoresConteo(actualizado);
      if (!mounted) return;
      setState(() {
        _turno = actualizado;
        _cargando = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text(
                'La conciliación sigue abierta. Sincroniza las ventas tardías y vuelve a revisar los cupos retenidos.')),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _cargando = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('No se pudo completar la conciliación: $e'),
            backgroundColor: ColoresFS.danger),
      );
    }
  }

  Future<void> _onSucursalCambiada(String? nuevaSucursal) async {
    if (nuevaSucursal == null) return;
    setState(() {
      _sucursalSel = nuevaSucursal;
      _cuposSolicitados.clear();
      _cargandoVariantes = true;
    });
    try {
      final vars =
          await _catalogoSrv.listarVariantesParaCaja(sucursalId: nuevaSucursal);
      if (mounted) {
        setState(() {
          _variantesDisponibles = vars;
          _varianteSelParaCupo = vars.isNotEmpty ? vars.first : null;
          _cargandoVariantes = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _cargandoVariantes = false);
      }
    }
  }

  Future<void> _recargarVariantesCaja(String sucursalId) async {
    if (sucursalId.isEmpty) return;
    if (mounted) setState(() => _cargandoVariantes = true);
    try {
      final variantes = await _catalogoSrv.listarVariantesParaCaja(
        sucursalId: sucursalId,
      );
      if (!mounted) return;
      setState(() {
        _variantesDisponibles = variantes;
        if (!variantes.any(
          (variante) => variante.varianteId == _varianteSelParaCupo?.varianteId,
        )) {
          _varianteSelParaCupo = variantes.firstOrNull;
        }
        _cantidadCupo = 1;
        _cargandoVariantes = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _variantesDisponibles = [];
        _varianteSelParaCupo = null;
        _cargandoVariantes = false;
      });
    }
  }

  // --- Habilitar Turno Online ---
  Future<void> _habilitarTurno() async {
    if (_sucursalSel == null || _sucursalSel!.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Por favor, selecciona una sucursal.')),
      );
      return;
    }

    final cuposList = <CupoItemModel>[];
    _cuposSolicitados.forEach((varId, cant) {
      if (cant > 0) {
        cuposList.add(CupoItemModel(varianteId: varId, cantidad: cant));
      }
    });

    if (cuposList.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
              'Debes agregar al menos una prenda con cupo para habilitar el turno.'),
        ),
      );
      return;
    }

    String dispId = 'caja-movil-01';
    try {
      dispId = await DispositivoHelper.obtenerDispositivoId();
    } catch (_) {}

    setState(() => _cargando = true);
    try {
      final dto = TurnoCrearModel(
        cajaId: _codigoCajaCtrl.text.trim().isEmpty
            ? 'CAJA-MOVIL-01'
            : _codigoCajaCtrl.text.trim(),
        dispositivoId: dispId,
        sucursalId: _sucursalSel!,
        cupos: cuposList,
      );

      final nuevoTurno = await _cajaSrv.habilitarTurno(dto);
      if (!mounted) return;
      setState(() {
        _turno = nuevoTurno;
        _cargando = false;
        _cuposSolicitados.clear();
        _errorEstadisticas = null;
        if (nuevoTurno.cupos.isNotEmpty) {
          _cupoSeleccionado = nuevoTurno.cupos.first;
        }
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(
                'Turno habilitado exitosamente: ${nuevoTurno.cajaCodigo}')),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _cargando = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error al habilitar turno: $e')),
      );
    }
  }

  // --- Cobrar Venta Física en Efectivo ---
  Future<void> _cobrarVentaFisica() async {
    final cupo = _cupoSeleccionado;
    if (cupo == null || cupo.disponible <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('No hay cupo disponible de la prenda elegida.')),
      );
      return;
    }

    if (_cantidadVenta <= 0 || _cantidadVenta > cupo.disponible) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content:
                Text('La cantidad debe ser entre 1 y ${cupo.disponible}.')),
      );
      return;
    }

    final total = cupo.precioAutorizadoBob * _cantidadVenta;
    final recibido = double.tryParse(
            _efectivoRecibidoCtrl.text.trim().replaceAll(',', '.')) ??
        total;
    if (recibido < total) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(
                'El efectivo recibido (Bs $recibido) no cubre el total (Bs $total).')),
      );
      return;
    }
    final cambio = recibido - total;

    setState(() => _cargando = true);
    try {
      _operacionLocalId ??= const Uuid().v4();
      _fechaLocalOperacion ??= DateTime.now();
      final comprobante = await _cajaSrv.registrarVentaFisicaOffline(
        operacionId: _operacionLocalId,
        fechaLocal: _fechaLocalOperacion,
        lineas: [
          VentaOfflineLineaModel(
            varianteId: cupo.varianteId,
            cantidad: _cantidadVenta,
            precioAutorizadoBob: cupo.precioAutorizadoBob,
          )
        ],
        totalBob: total,
        efectivoRecibidoBob: recibido,
        cambioEntregadoBob: cambio,
        clienteId: _clienteIdCtrl.text.trim().isNotEmpty
            ? _clienteIdCtrl.text.trim()
            : null,
      );

      final comps = await _cajaSrv.listarComprobantesLocales(_turno!.turnoId).catchError((_) => <ComprobanteLocalModel>[comprobante]);

      if (!mounted) return;
      setState(() {
        _turno = _cajaSrv.turnoActivoLocal;
        _cupoSeleccionado = _turno?.cupos.where((c) => c.varianteId == cupo.varianteId).firstOrNull;
        _operacionLocalId = null; _fechaLocalOperacion = null;
        _pendientes = _cajaSrv.ventasOfflinePendientes;
        _comprobantes = comps;
        _cargando = false;
        _efectivoRecibidoCtrl.clear();
        _cantidadVenta = 1;
      });

      _mostrarDialogoComprobante(comprobante);
    } catch (e) {
      if (!mounted) return;
      setState(() => _cargando = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error al cobrar venta offline: $e')),
      );
    }
  }

  void _mostrarDialogoComprobante(ComprobanteLocalModel comp) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.receipt_long, color: ColoresFS.success),
            SizedBox(width: 8),
            Text('Comprobante Emitido'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.grey.shade100,
                borderRadius: BorderRadius.circular(6),
              ),
              child: SelectableText(
                comp.numeroComprobante,
                style:
                    const TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
              ),
            ),
            const SizedBox(height: 12),
            Text('Turno: ${_turno?.cajaCodigo ?? "Caja Local"}'),
            Text(
                'Fecha: ${comp.emitidoEn.substring(0, 19).replaceAll("T", " ")}'),
            const Divider(),
            Text('Total Pagado: Bs ${comp.totalBob.toStringAsFixed(2)}',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            Text(
                'Efectivo Recibido: Bs ${comp.efectivoRecibidoBob.toStringAsFixed(2)}'),
            Text('Cambio Entregado: Bs ${comp.cambioBob.toStringAsFixed(2)}',
                style: const TextStyle(
                    color: ColoresFS.brassStrong, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: Colors.green.shade200),
              ),
              child: const Text(
                'Venta registrada localmente en este dispositivo. Lista para sincronizar al conectarse al servidor.',
                style: TextStyle(fontSize: 12, color: Colors.green),
              ),
            ),
          ],
        ),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Aceptar'),
          ),
        ],
      ),
    );
  }

  // --- Sincronizar Operaciones con el Servidor ---
  Future<void> _sincronizar() async {
    final t = _turno;
    setState(() => _sincronizando = true);

    try {
      final sincronizadas =
          await _cajaSrv.sincronizarVentasPendientes(null);
      final comps = t == null ? <ComprobanteLocalModel>[] : await _cajaSrv.listarComprobantesLocales(t.turnoId);
      TurnoHabilitacionModel? turnoActualizado = _cajaSrv.turnoActivoLocal;
      try {
        turnoActualizado = await _cajaSrv.consultarTurnoActivo();
      } catch (_) {}
      _prepararControladoresConteo(turnoActualizado);

      if (!mounted) return;
      setState(() {
        _turno = turnoActualizado;
        _pendientes = _cajaSrv.ventasOfflinePendientes;
        _comprobantes = comps;
        _sincronizando = false;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            sincronizadas > 0
                ? '$sincronizadas venta(s) sincronizada(s) con éxito en el servidor.'
                : '${_pendientes.length} operaciones pendientes o en conciliacion; se conservan para reintento.',
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _sincronizando = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error de sincronización: $e')),
      );
    }
  }

  // --- Cerrar Turno y Arqueo ---
  Future<void> _cerrarTurno() async {
    final t = _turno;
    if (t == null) return;

    // Verificar estadísticas de operaciones locales antes de proceder
    final Map<String, int> stats;
    try {
      stats = await _cajaSrv.obtenerEstadisticasVentasTurno(t.turnoId);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorEstadisticas =
            'Error de lectura en base de datos local: $e. Cierre deshabilitado por seguridad.';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              'Error al leer operaciones locales de caja: $e. Cierre cancelado por seguridad.'),
          backgroundColor: ColoresFS.danger,
        ),
      );
      return; // Nunca enviar 0,0 al servidor ante error de SQLite
    }

    if (!mounted) return;

    final arqueoVal =
        double.tryParse(_arqueoCtrl.text.trim().replaceAll(',', '.'));

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cierre de Turno y Arqueo'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('¿Deseas cerrar el turno ${t.cajaCodigo}?'),
            const SizedBox(height: 8),
            if (_pendientes.isNotEmpty)
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.amber.shade50,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: Colors.amber.shade300),
                ),
                child: Text(
                  'Atención: Quedan ${_pendientes.length} venta(s) pendientes de sincronizar.',
                  style: TextStyle(fontSize: 12, color: Colors.amber.shade900),
                ),
              ),
            const SizedBox(height: 8),
            const Text(
                'Se devolverán los cupos no consumidos al inventario central.'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Confirmar Cierre'),
          ),
        ],
      ),
    );

    if (ok != true) return;

    setState(() => _cargando = true);
    try {
      final ultimaSec = stats['ultima_secuencia'] ?? 0;
      final totalOps = stats['total_operaciones'] ?? 0;

      final dto = TurnoCerrarModel(
        revision: t.revision,
        ultimaSecuenciaLocal: ultimaSec,
        totalOperacionesLocales: totalOps,
        operacionesPendientes: _pendientes.map((p) => p.operacionId).toList(),
        arqueoEfectivoBob: arqueoVal,
      );

      final cerrado = await _cajaSrv.cerrarTurno(t.turnoId, dto);
      if (!mounted) return;
      setState(() {
        if (cerrado.estado == 'CERRADO') {
          _turno = null;
          _pendientes = [];
          _comprobantes = [];
          _errorEstadisticas = null;
        } else if (cerrado.estado == 'CONCILIACION' && _turno != null) {
          _turno!.estado = 'CONCILIACION';
          _turno!.revision = cerrado.revision;
        }
        _cargando = false;
        _arqueoCtrl.clear();
      });

      if (cerrado.estado == 'CERRADO') {
        await _recargarVariantesCaja(t.sucursalId);
        if (!mounted) return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            cerrado.estado == 'CERRADO'
                ? 'Turno cerrado exitosamente. Cupos devueltos: ${cerrado.cuposDevueltos.length}.'
                : 'Turno en estado de conciliación. Cupos devueltos: ${cerrado.cuposDevueltos.length}.',
          ),
        ),
      );
      if (cerrado.estado == 'CONCILIACION') {
        try {
          final actualizado = await _cajaSrv.consultarTurno(t.turnoId);
          _prepararControladoresConteo(actualizado);
          if (mounted) setState(() => _turno = actualizado);
        } catch (_) {
          // El turno ya queda persistido con la revisión devuelta por el servidor.
          // La recarga manual volverá a consultar balances si falla esta lectura.
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _cargando = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error al cerrar turno: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Caja Móvil'),
        actions: [
          if (_pendientes.isNotEmpty) IconButton(icon: const Icon(Icons.sync), tooltip: 'Sincronizar turnos originales (${_pendientes.length})', onPressed: _sincronizando ? null : _sincronizar),
          if (_esSupervisor) IconButton(icon: const Icon(Icons.restore), tooltip: 'Recuperacion supervisada online', onPressed: _recuperarSupervisado),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _inicializar,
            tooltip: 'Recargar estado',
          ),
        ],
      ),
      body: _cargando
          ? const VistaCarga(mensaje: 'Cargando estado de caja local…')
          : _error != null
              ? VistaError(mensaje: _error!, onReintentar: _inicializar)
              : _turno == null
                  ? _vistaSinTurno()
                  : _vistaTurnoActivo(),
    );
  }

  Future<void> _recuperarSupervisado() async {
    String id = '';
    final aceptar = await showDialog<bool>(context: context, builder: (ctx) => AlertDialog(
      title: const Text('Recuperar pendientes del turno original'),
      content: TextField(decoration: const InputDecoration(labelText: 'ID del turno'), onChanged: (v) => id = v.trim()),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Validar online y recuperar'))]));
    if (aceptar != true || id.isEmpty) return;
    try {
      final n = await _cajaSrv.recuperarPendientesSupervisados(id);
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$n operaciones registradas; las restantes siguen conservadas para conciliacion.')));
    } catch (e) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Recuperacion pendiente: $e'))); }
  }

  // --- Vista 1: Formulario para Habilitar Turno Online ---
  Widget _vistaSinTurno() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_legadoPendiente > 0) Text('$_legadoPendiente registros antiguos conservados requieren revalidar su turno online o conciliacion supervisada.'),
          Card(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.point_of_sale,
                          color: ColoresFS.brassStrong, size: 28),
                      SizedBox(width: 8),
                      Text(
                        'Habilitar Turno de Caja',
                        style: TextStyle(
                            fontSize: 18, fontWeight: FontWeight.w800),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Para operar ventas en efectivo sin conexión, habilita un turno online solicitando cupos de prendas para este dispositivo.',
                    style: TextStyle(color: Colors.grey),
                  ),
                  const Divider(height: 24),
                  TextField(
                    controller: _codigoCajaCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Código de Caja / Dispositivo',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.tablet_android),
                    ),
                  ),
                  const SizedBox(height: 14),
                  if (_sucursales.isNotEmpty) ...[
                    DropdownButtonFormField<String>(
                      initialValue: _sucursalSel,
                      decoration: const InputDecoration(
                        labelText: 'Sucursal de Operación',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.store),
                      ),
                      items: [
                        for (final s in _sucursales)
                          DropdownMenuItem(value: s.id, child: Text(s.nombre)),
                      ],
                      onChanged: (v) => _onSucursalCambiada(v),
                    ),
                    const SizedBox(height: 14),
                  ],
                  const Text(
                    'Prendas y cupos solicitados para el turno:',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  if (_cargandoVariantes)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Center(child: CircularProgressIndicator()),
                    )
                  else if (_variantesDisponibles.isEmpty)
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.grey.shade50,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.grey.shade300),
                      ),
                      child: const Text(
                        'No hay prendas con disponibilidad confirmada en esta sucursal. Con?ctate y vuelve a cargar.',
                        style: TextStyle(color: Colors.grey),
                      ),
                    )
                  else ...[
                    DropdownButtonFormField<VarianteCajaDisponibleModel>(
                      key: const Key('dropdown_variante_cupo'),
                      initialValue: _varianteSelParaCupo,
                      decoration: const InputDecoration(
                        labelText: 'Seleccionar Prenda',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.checkroom),
                      ),
                      isExpanded: true,
                      items: [
                        for (final v in _variantesDisponibles)
                          DropdownMenuItem(
                            value: v,
                            child: Text(
                              '${v.productoNombre} · ${v.sku} (Bs ${v.precioBob.toStringAsFixed(2)})',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      onChanged: (v) => setState(() {
                        _varianteSelParaCupo = v;
                        _cantidadCupo = 1;
                      }),
                    ),
                    const SizedBox(height: 10),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (_varianteSelParaCupo != null)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 4),
                            child: Text(
                              'Disponible en esta sucursal: ${_varianteSelParaCupo!.stockDisponible} un. '
                              '(${_stockRestanteParaCupo(_varianteSelParaCupo)} sin asignar)',
                              style: const TextStyle(fontSize: 13),
                            ),
                          ),
                        Row(
                          children: [
                            const Text('Cantidad: ',
                                style: TextStyle(fontWeight: FontWeight.w600)),
                            IconButton.outlined(
                              icon: const Icon(Icons.remove),
                              onPressed: _cantidadCupo > 1
                                  ? () => setState(() => _cantidadCupo--)
                                  : null,
                            ),
                            Padding(
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 10),
                              child: Text('$_cantidadCupo',
                                  style: const TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.bold)),
                            ),
                            IconButton.outlined(
                              icon: const Icon(Icons.add),
                              onPressed: _cantidadCupo <
                                      _stockRestanteParaCupo(
                                          _varianteSelParaCupo)
                                  ? () => setState(() => _cantidadCupo++)
                                  : null,
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        ElevatedButton.icon(
                          onPressed: _varianteSelParaCupo == null ||
                                  _cantidadCupo >
                                      _stockRestanteParaCupo(
                                          _varianteSelParaCupo)
                              ? null
                              : () {
                                  setState(() {
                                    final varId =
                                        _varianteSelParaCupo!.varianteId;
                                    _cuposSolicitados[varId] =
                                        (_cuposSolicitados[varId] ?? 0) +
                                            _cantidadCupo;
                                    _cantidadCupo = 1;
                                  });
                                },
                          icon: const Icon(Icons.add),
                          label: const Text('Agregar prenda'),
                        ),
                      ],
                    ),
                  ],
                  const SizedBox(height: 12),
                  if (_cuposSolicitados.isEmpty)
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.amber.shade50,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.amber.shade300),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.info_outline,
                              color: Colors.amber.shade900, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Debes agregar al menos una prenda con cupo para habilitar el turno.',
                              style: TextStyle(
                                  fontSize: 12, color: Colors.amber.shade900),
                            ),
                          ),
                        ],
                      ),
                    )
                  else ...[
                    const Text('Prendas agregadas al turno:',
                        style: TextStyle(
                            fontWeight: FontWeight.w700, fontSize: 13)),
                    const SizedBox(height: 6),
                    for (final entry in _cuposSolicitados.entries) ...[
                      Builder(builder: (context) {
                        final vMatch = _variantesDisponibles
                            .where((x) => x.varianteId == entry.key)
                            .firstOrNull;
                        final nombre = vMatch?.productoNombre ?? 'Prenda';
                        final sku = vMatch?.sku ?? entry.key;
                        return Card(
                          margin: const EdgeInsets.symmetric(vertical: 4),
                          color: Colors.grey.shade50,
                          child: ListTile(
                            dense: true,
                            leading: const Icon(Icons.check_circle_outline,
                                color: ColoresFS.brassStrong),
                            title: Text('$nombre ($sku)',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700)),
                            subtitle:
                                Text('Cantidad asignada: ${entry.value} un.'),
                            trailing: IconButton(
                              icon: const Icon(Icons.delete_outline,
                                  color: Colors.red),
                              onPressed: () => setState(
                                  () => _cuposSolicitados.remove(entry.key)),
                            ),
                          ),
                        );
                      }),
                    ],
                  ],
                  const SizedBox(height: 20),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                      onPressed:
                          _cuposSolicitados.isNotEmpty ? _habilitarTurno : null,
                      icon: const Icon(Icons.lock_open),
                      label: const Text('Habilitar Turno Online'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  // --- Vista 2: Turno Activo (Cobro, Pendientes y Cierre) ---
  Widget _vistaTurnoActivo() {
    final t = _turno!;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 1. Tarjeta informativa del Turno
          Card(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          const Icon(Icons.point_of_sale,
                              color: ColoresFS.brassStrong),
                          const SizedBox(width: 8),
                          Text(
                            t.cajaCodigo,
                            style: const TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 18),
                          ),
                        ],
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: t.estaVigente
                              ? Colors.green.shade50
                              : Colors.red.shade50,
                          borderRadius: BorderRadius.circular(999),
                          border: Border.all(
                            color: t.estaVigente
                                ? Colors.green.shade300
                                : Colors.red.shade300,
                          ),
                        ),
                        child: Text(
                          t.estado,
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            color: t.estaVigente
                                ? Colors.green.shade800
                                : Colors.red.shade800,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text('Vence: ${textoVigencia(DateTime.tryParse(t.venceEn))}'),
                  Text(
                      'Versión de precios: ${t.versionPrecios} · Revisión: v${t.revision}'),
                  const Divider(height: 20),
                  const Text('Cupos asignados en dispositivo:',
                      style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  for (final c in t.cupos)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Text(
                              c.productoNombre ??
                                  c.sku ??
                                  'Variante ${c.varianteId.substring(0, 8)}',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          Text(
                            'Disp: ${c.disponible} / ${c.otorgado} (Bs ${c.precioAutorizadoBob.toStringAsFixed(2)})',
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),

          // 2. Banner de Sincronización
          if (_pendientes.isNotEmpty)
            Card(
              color: Colors.amber.shade50,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
                side: BorderSide(color: Colors.amber.shade300),
              ),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Row(
                  children: [
                    Icon(Icons.cloud_upload_outlined,
                        color: Colors.amber.shade900),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${_pendientes.length} venta(s) pendientes de sincronizar',
                            style: TextStyle(
                              fontWeight: FontWeight.w800,
                              color: Colors.amber.shade900,
                            ),
                          ),
                          const Text(
                            'Guardadas localmente en este dispositivo.',
                            style: TextStyle(fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                    ElevatedButton(
                      onPressed: _sincronizando ? null : _sincronizar,
                      child: _sincronizando
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Sincronizar'),
                    ),
                  ],
                ),
              ),
            ),
          const SizedBox(height: 12),

          // 3. Formulario de Cobro Físico en Efectivo (Offline)
          Card(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.payments_outlined, color: ColoresFS.success),
                      SizedBox(width: 8),
                      Text('Cobrar Venta en Efectivo (Offline)',
                          style: TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 16)),
                    ],
                  ),
                  const SizedBox(height: 12),
                  if (t.cupos.isNotEmpty) ...[
                    DropdownButtonFormField<String>(
                      isExpanded: true,
                      key: ValueKey(
                        'cupo_venta_${t.turnoId}_${t.cupos.map((c) => c.varianteId).join("_")}',
                      ),
                      initialValue: _cupoSeleccionado?.varianteId,
                      decoration: const InputDecoration(
                        labelText: 'Prenda a Cobrar',
                        border: OutlineInputBorder(),
                      ),
                      items: [
                        for (final c in t.cupos)
                          DropdownMenuItem(
                            value: c.varianteId,
                            child: Text(
                              '${c.productoNombre ?? c.sku ?? "Prenda"} (${c.disponible} disp. - Bs ${c.precioAutorizadoBob.toStringAsFixed(2)})',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      onChanged: (id) =>
                          setState(() => _cupoSeleccionadoId = id),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: Row(
                            children: [
                              IconButton.outlined(
                                icon: const Icon(Icons.remove),
                                onPressed: _cantidadVenta > 1
                                    ? () => setState(() => _cantidadVenta--)
                                    : null,
                              ),
                              Padding(
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 12),
                                child: Text('$_cantidadVenta',
                                    style: const TextStyle(
                                        fontSize: 18,
                                        fontWeight: FontWeight.bold)),
                              ),
                              IconButton.outlined(
                                icon: const Icon(Icons.add),
                                onPressed: (_cupoSeleccionado != null &&
                                        _cantidadVenta <
                                            _cupoSeleccionado!.disponible)
                                    ? () => setState(() => _cantidadVenta++)
                                    : null,
                              ),
                            ],
                          ),
                        ),
                        Text(
                          'Total: Bs ${((_cupoSeleccionado?.precioAutorizadoBob ?? 0.0) * _cantidadVenta).toStringAsFixed(2)}',
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.w900),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _efectivoRecibidoCtrl,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(
                        labelText: 'Efectivo Recibido (Bs)',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.money),
                      ),
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          backgroundColor: ColoresFS.ink,
                          foregroundColor: Colors.white,
                        ),
                        onPressed: t.estaVigente && (_cupoSeleccionado?.disponible ?? 0) > 0
                            ? _cobrarVentaFisica
                            : null,
                        icon: const Icon(Icons.check_circle_outline),
                        label: const Text(
                            'Cobrar en Efectivo y Emitir Comprobante'),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),

          // 4. Historial de Comprobantes Locales Emitidos
          if (_comprobantes.isNotEmpty) ...[
            const Text('Comprobantes Locales Emitidos',
                style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            const SizedBox(height: 6),
            for (final comp in _comprobantes)
              Card(
                child: ListTile(
                  leading: const Icon(Icons.receipt_outlined,
                      color: ColoresFS.brassStrong),
                  title: Text(comp.numeroComprobante,
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: Text(
                      'Total: Bs ${comp.totalBob.toStringAsFixed(2)} · Cambio: Bs ${comp.cambioBob.toStringAsFixed(2)}'),
                  trailing: Text(
                    comp.emitidoEn.length >= 16
                        ? comp.emitidoEn.substring(11, 16)
                        : '',
                    style: const TextStyle(color: Colors.grey),
                  ),
                ),
              ),
            const SizedBox(height: 12),
          ],

          // 5. Cierre de Turno y Arqueo
          if (t.estado == 'ABIERTO')
            Card(
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.lock_clock_outlined,
                            color: ColoresFS.danger),
                        SizedBox(width: 8),
                        Text('Cierre de Turno y Arqueo',
                            style: TextStyle(
                                fontWeight: FontWeight.w800, fontSize: 16)),
                      ],
                    ),
                    if (_errorEstadisticas != null) ...[
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: Colors.red.shade50,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.red.shade300),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.warning_amber_rounded,
                                color: ColoresFS.danger),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                _errorEstadisticas!,
                                style: const TextStyle(
                                  color: ColoresFS.danger,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                    const SizedBox(height: 10),
                    TextField(
                      controller: _arqueoCtrl,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      decoration: const InputDecoration(
                        labelText: 'Arqueo de Efectivo Final en Caja (Bs)',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.account_balance_wallet_outlined),
                      ),
                    ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        style: OutlinedButton.styleFrom(
                          foregroundColor: ColoresFS.danger,
                          side: const BorderSide(color: ColoresFS.danger),
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                        onPressed: (_cargando || _errorEstadisticas != null)
                            ? null
                            : _cerrarTurno,
                        icon: const Icon(Icons.close),
                        label: const Text('Cerrar Turno y Devolver Cupos'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          if (_esSupervisor &&
              (t.estado == 'CONCILIACION' || t.estado == 'RECUPERACION')) ...[
            const SizedBox(height: 12),
            _tarjetaResolucionSupervisada(t),
          ],
        ],
      ),
    );
  }

  Widget _tarjetaResolucionSupervisada(TurnoHabilitacionModel turno) {
    return Card(
      key: const Key('tarjeta_resolucion_supervisada'),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.fact_check_outlined, color: ColoresFS.brassStrong),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Revisión física supervisada',
                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            const Text(
              'Cuenta las unidades disponibles de cada prenda. Las ventas pendientes deben sincronizarse antes de resolver el inventario.',
            ),
            if (_pendientes.isNotEmpty) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.amber.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.amber.shade300),
                ),
                child: const Text(
                  'Sincroniza las ventas pendientes antes de completar el conteo final.',
                  key: Key('mensaje_sync_prev_condiliacion'),
                ),
              ),
            ],
            const SizedBox(height: 12),
            for (final cupo in turno.cupos) ...[
              Text(
                '${cupo.productoNombre ?? cupo.sku ?? 'Prenda'} · ${cupo.disponible} unidades por conciliar',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              TextField(
                key: Key('conteo_fisico_${cupo.varianteId}'),
                controller: _conteosFisicosCtrl[cupo.varianteId],
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Unidades encontradas físicamente',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.inventory_2_outlined),
                ),
                onChanged: (_) => setState(() {}),
              ),
              if ((_conteoFisico(cupo) ?? cupo.disponible) <
                  cupo.disponible) ...[
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  key: Key('resolucion_${cupo.varianteId}'),
                  initialValue: _resolucionFaltante[cupo.varianteId],
                  decoration: const InputDecoration(
                    labelText: 'Resolución de unidades faltantes',
                    border: OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(
                      value: 'PENDIENTE_SINCRONIZACION',
                      child: Text('Mantener retenidas mientras se investiga'),
                    ),
                    DropdownMenuItem(
                      value: 'MERMA',
                      child: Text('Registrar merma física'),
                    ),
                  ],
                  onChanged: (value) => setState(() {
                    _resolucionFaltante[cupo.varianteId] = value;
                  }),
                ),
                const SizedBox(height: 8),
                TextField(
                  key: Key('motivo_faltante_${cupo.varianteId}'),
                  controller: _motivosFaltanteCtrl[cupo.varianteId],
                  minLines: 1,
                  maxLines: 3,
                  decoration: InputDecoration(
                    labelText: _resolucionFaltante[cupo.varianteId] == 'MERMA'
                        ? 'Causa de merma (mínimo 10 caracteres)'
                        : 'Motivo para mantener el faltante retenido',
                    border: const OutlineInputBorder(),
                  ),
                  onChanged: (_) => setState(() {}),
                ),
              ],
              const SizedBox(height: 12),
            ],
            TextField(
              controller: _referenciaActaCtrl,
              decoration: const InputDecoration(
                labelText: 'Referencia del acta o registro físico',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.description_outlined),
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _motivoSupervisionCtrl,
              minLines: 2,
              maxLines: 4,
              decoration: const InputDecoration(
                labelText: 'Motivo de la revisión supervisada',
                border: OutlineInputBorder(),
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _arqueoCtrl,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                labelText: 'Efectivo contado físicamente (Bs)',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.account_balance_wallet_outlined),
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                key: const Key('resolver_cierre_supervisado'),
                onPressed: _cargando ||
                        _errorEstadisticas != null ||
                        _erroresResolucionSupervisada(turno).isNotEmpty
                    ? null
                    : _resolverCierreSupervisado,
                icon: const Icon(Icons.verified_outlined),
                label: const Text('Confirmar conteo y resolver'),
                style: ElevatedButton.styleFrom(
                  minimumSize: const Size.fromHeight(48),
                ),
              ),
            ),
            if (_erroresResolucionSupervisada(turno).isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                _erroresResolucionSupervisada(turno).first,
                key: const Key('validacion_resolucion_supervisada'),
                style: const TextStyle(color: ColoresFS.danger),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
