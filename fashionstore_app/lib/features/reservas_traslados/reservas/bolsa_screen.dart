import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../../catalogo/models/catalogo_model.dart';
import '../../organizacion/models/organizacion_model.dart';
import '../models/reserva_model.dart';
import '../../catalogo/services/catalogo_service.dart';
import '../services/reserva_service.dart';
import '../services/sincronizacion_offline_service.dart';
import '../../organizacion/services/sucursal_service.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/session/session_manager.dart';
import '../../../core/ui/async_view.dart';
import '../../../core/ui/formato.dart';
import 'bolsa_store.dart';
import 'origen_helper.dart';

/// Estado explícito de disponibilidad por variante.
///
/// - [noConsultada]: aún no comenzó ninguna consulta.
/// - [cargando]: existe una consulta vigente.
/// - [disponible]: la última consulta terminó correctamente y los datos
///   almacenados en `_disponibilidad` son confiables.
/// - [error]: la última consulta falló; no hay datos confiables y no se
///   reintenta automáticamente.
enum EstadoDisponibilidad {
  noConsultada,
  cargando,
  disponible,
  error,
}

/// Bolsa multiítem: destino único + fecha de visita + origen explícito
/// cuando la línea necesita traslado.
///
/// Reglas (corrección Ciclo 2):
/// - Si el destino no cubre la cantidad, el traslado es obligatorio y se
///   activa automáticamente; no es desactivable mientras siga necesario.
/// - Se muestra la indicación no editable "Requiere traslado" y el selector
///   de origen con solo orígenes válidos (distintos al destino y con stock
///   suficiente, vía [origenesValidosParaLinea]). Nunca se elige origen
///   automáticamente ni se envía origen vacío/nulo/incoherente.
/// - Con stock suficiente en destino se usa reserva local y se limpian
///   `solicitaTraslado` y el origen.
/// - No se confirma si una línea que requiere traslado no tiene origen
///   válido: se bloquea localmente sin esperar el 409 del backend.
/// - No se confirma sin disponibilidad verificada: cada variante debe estar
///   en [EstadoDisponibilidad.disponible]. Los estados `noConsultada`,
///   `cargando` o `error` bloquean el botón y también bloquean `_confirmar`
///   defensivamente, sin invocar red ni crear clave de idempotencia.
/// - Un error permanece estable hasta reintento manual o cambio legítimo de
///   cantidad/destino. Nunca hay reintentos automáticos desde `build` ni
///   desde `_confirmar`.
/// - Aumentar/disminuir cantidad invalida la evidencia anterior (estado a
///   `cargando`, sin usar lo cacheado) y recarga. Cambio de destino invalida
///   todas las líneas y recarga una vez por variante.
/// - Respuestas fuera de orden se descartan por versión (_seqDisp).
class BolsaScreen extends StatefulWidget {
  final VoidCallback? onReservaCreada;
  final SucursalService? servicioSucursales;
  final ReservaService? servicioReservas;
  final CatalogoService? servicioCatalogo;
  final SincronizacionOfflineService? servicioOffline;

  const BolsaScreen({
    super.key,
    this.onReservaCreada,
    this.servicioSucursales,
    this.servicioReservas,
    this.servicioCatalogo,
    this.servicioOffline,
  });

  @override
  State<BolsaScreen> createState() => _BolsaScreenState();
}

class _BolsaScreenState extends State<BolsaScreen> {
  late final SucursalService _sucursalesSrv;
  late final ReservaService _reservasSrv;
  late final CatalogoService _catalogoSrv;
  late final SincronizacionOfflineService _offlineSrv;

  List<SucursalModel> _sucursales = [];
  bool _cargandoSuc = true;
  String? _errorSuc;
  String? _destinoId;
  DateTime? _fechaVisita;
  final _obs = TextEditingController();
  bool _enviando = false;
  String? _errorEnvio;
  String? _claveActual;

  // Disponibilidad verificada por variante. Solo es confiable cuando
  // [_estadoDisponibilidad] es [EstadoDisponibilidad.disponible].
  final Map<String, List<DisponibilidadSucursal>> _disponibilidad = {};

  // Estado explícito que controla interfaz y confirmación.
  final Map<String, EstadoDisponibilidad> _estadoDisponibilidad = {};

  // Versión por variante para descartar respuestas asíncronas fuera de orden:
  // solo la respuesta con la versión más reciente puede mutar el estado.
  final Map<String, int> _seqDisp = {};

  @override
  void initState() {
    super.initState();
    _sucursalesSrv = widget.servicioSucursales ?? SucursalService();
    _reservasSrv = widget.servicioReservas ?? ReservaService();
    _catalogoSrv = widget.servicioCatalogo ?? CatalogoService();
    _offlineSrv = widget.servicioOffline ?? SincronizacionOfflineService();
    _cargarSucursales();
  }

  @override
  void dispose() {
    _obs.dispose();
    super.dispose();
  }

  EstadoDisponibilidad _estadoDe(String varianteId) {
    return _estadoDisponibilidad[varianteId] ??
        EstadoDisponibilidad.noConsultada;
  }

  bool get _hayCargaDisponibilidad {
    for (final item in BolsaStore.instancia.items) {
      if (_estadoDe(item.varianteId) == EstadoDisponibilidad.cargando) {
        return true;
      }
    }
    return false;
  }

  bool get _hayErrorDisponibilidad {
    for (final item in BolsaStore.instancia.items) {
      if (_estadoDe(item.varianteId) == EstadoDisponibilidad.error) {
        return true;
      }
    }
    return false;
  }

  bool get _hayNoConsultada {
    for (final item in BolsaStore.instancia.items) {
      if (_estadoDe(item.varianteId) == EstadoDisponibilidad.noConsultada) {
        return true;
      }
    }
    return false;
  }

  /// Verdadero solo si todas las líneas están verificadas.
  bool get _puedeConfirmarDisponibilidad {
    final items = BolsaStore.instancia.items;
    if (items.isEmpty) return false;
    for (final item in items) {
      if (_estadoDe(item.varianteId) != EstadoDisponibilidad.disponible) {
        return false;
      }
      if (!_disponibilidad.containsKey(item.varianteId)) return false;
    }
    return true;
  }

  bool _trasladoBloquea(ItemBolsa item) {
    final disp = _disponibilidad[item.varianteId];
    if (disp == null) return true;
    final necesita = necesitaOrigenParaLinea(
      disponibleDestino: disponibleEnDestino(disp, _destinoId),
      cantidadSolicitada: item.cantidad,
    );
    if (!necesita) return false;
    if (!item.tieneOrigenValido) return true;
    final opciones = origenesValidosParaLinea(
      disponibilidad: disp,
      sucursales: _sucursales,
      destinoId: _destinoId,
      cantidadNecesaria: item.cantidad,
    );
    return !opciones.any((o) => o.sucursal.id == item.origenId);
  }

  bool get _confirmarHabilitado {
    if (BolsaStore.instancia.vacia) return false;
    if (_cargandoSuc) return false;
    if (_destinoId == null) return false;
    if (_enviando) return false;
    if (!_puedeConfirmarDisponibilidad) return false;
    for (final item in BolsaStore.instancia.items) {
      if (_trasladoBloquea(item)) return false;
    }
    return true;
  }

  String get _etiquetaConfirmar {
    if (_enviando) return 'Confirmando…';
    if (_hayCargaDisponibilidad || _hayNoConsultada) {
      return 'Verificando disponibilidad…';
    }
    if (_hayErrorDisponibilidad) return 'Revisa la disponibilidad';
    return 'Confirmar reserva';
  }

  Future<void> _cargarSucursales() async {
    setState(() {
      _cargandoSuc = true;
      _errorSuc = null;
    });
    try {
      final s = await _sucursalesSrv.listar();
      final activas = s.where((e) => e.activa).toList();
      if (!mounted) return;
      setState(() {
        _sucursales = activas;
        _cargandoSuc = false;
        if (_destinoId == null && activas.isNotEmpty) {
          _destinoId = activas.first.id;
        }
      });
      // Carga inicial: una sola vez por variante en estado noConsultada.
      for (final item in BolsaStore.instancia.items) {
        if (_estadoDe(item.varianteId) == EstadoDisponibilidad.noConsultada) {
          _cargarDisponibilidad(item.varianteId);
        }
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorSuc = e.toString();
        _cargandoSuc = false;
      });
    }
  }

  SucursalModel? _destino() {
    if (_destinoId == null) return null;
    try {
      return _sucursales.firstWhere((e) => e.id == _destinoId);
    } catch (_) {
      return null;
    }
  }

  Future<void> _elegirFecha() async {
    final ahora = DateTime.now();
    final f = await showDatePicker(
      context: context,
      initialDate: _fechaVisita ?? ahora.add(const Duration(days: 1)),
      firstDate: ahora,
      lastDate: ahora.add(const Duration(days: 7)),
      helpText: 'Fecha aproximada de visita',
    );
    if (f != null && mounted) setState(() => _fechaVisita = f);
  }

  void _alCambiarDestino(String? nuevo) {
    if (nuevo == null) return;
    if (!mounted) return;
    if (nuevo == _destinoId) return;
    setState(() => _destinoId = nuevo);
    // Descartar orígenes que ahora coinciden con el destino.
    BolsaStore.instancia.alCambiarDestino(nuevo);
    final items = List<ItemBolsa>.from(BolsaStore.instancia.items);
    if (items.isEmpty) return;
    // Invalida la disponibilidad de todas las líneas: sin evidencia anterior.
    setState(() {
      for (final item in items) {
        _estadoDisponibilidad[item.varianteId] = EstadoDisponibilidad.cargando;
        _disponibilidad.remove(item.varianteId);
      }
    });
    // Una sola consulta nueva por variante para el nuevo destino.
    for (final item in items) {
      _cargarDisponibilidad(item.varianteId);
    }
  }

  /// Carga disponibilidad para una variante y concilia el traslado.
  ///
  /// Cada llamada incrementa la versión de la variante; solo la respuesta
  /// más reciente muta el estado. En error se marca `error` y se elimina lo
  /// anterior sin reintentar automáticamente. Nunca hace `setState` si el
  /// widget fue desmontado.
  Future<void> _cargarDisponibilidad(String varianteId) async {
    final seq = (_seqDisp[varianteId] ?? 0) + 1;
    _seqDisp[varianteId] = seq;
    if (!mounted) {
      _estadoDisponibilidad[varianteId] = EstadoDisponibilidad.cargando;
      return;
    }
    setState(() {
      _estadoDisponibilidad[varianteId] = EstadoDisponibilidad.cargando;
    });
    late final List<DisponibilidadSucursal> disp;
    try {
      disp = await _catalogoSrv.disponibilidad(varianteId);
    } catch (_) {
      if (!mounted) return;
      if (_seqDisp[varianteId] != seq) return;
      setState(() {
        _estadoDisponibilidad[varianteId] = EstadoDisponibilidad.error;
        _disponibilidad.remove(varianteId);
      });
      return;
    }
    if (!mounted) return;
    // Respuesta obsoleta: otra carga más reciente tomó el relevo.
    if (_seqDisp[varianteId] != seq) return;
    setState(() {
      _disponibilidad[varianteId] = disp;
      _estadoDisponibilidad[varianteId] = EstadoDisponibilidad.disponible;
    });
    _conciliarTrasladoLocal(varianteId, disp);
  }

  /// Reintento manual desde la tarjeta: una sola consulta para esa variante.
  void _reintentarDisponibilidad(String varianteId) {
    if (_estadoDe(varianteId) == EstadoDisponibilidad.cargando) return;
    _cargarDisponibilidad(varianteId);
  }

  /// Concilia el traslado de una línea con la disponibilidad real.
  ///
  /// Regla única (reutiliza `origenesValidosParaLinea` +
  /// `necesitaOrigenParaLinea`, sin duplicarla):
  /// - Si el destino cubre la cantidad → reserva local: se limpian
  ///   `solicitaTraslado` y `sucursalOrigenId`.
  /// - Si el destino NO cubre → traslado obligatorio: se activa
  ///   `solicitaTraslado` automáticamente (el usuario no puede desactivarlo
  ///   mientras siga siendo necesario) y solo se conserva el origen si sigue
  ///   figurando entre los orígenes válidos; si no, se limpia para exigir
  ///   una elección válida. Nunca se elige origen automáticamente.
  void _conciliarTrasladoLocal(
    String varianteId,
    List<DisponibilidadSucursal> disp,
  ) {
    final bolsa = BolsaStore.instancia;
    ItemBolsa? item;
    try {
      item = bolsa.items.firstWhere((e) => e.varianteId == varianteId);
    } catch (_) {
      return;
    }
    final dispDestino = disponibleEnDestino(disp, _destinoId);
    final necesita = necesitaOrigenParaLinea(
      disponibleDestino: dispDestino,
      cantidadSolicitada: item.cantidad,
    );
    if (!necesita) {
      // Destino cubre: volver a local limpiando todo rastro de traslado.
      if (item.solicitaTraslado || item.tieneOrigenValido) {
        bolsa.solicitarTraslado(varianteId, false);
      }
      return;
    }
    // Necesita traslado: activación obligatoria.
    if (!item.solicitaTraslado) {
      bolsa.solicitarTraslado(varianteId, true);
    }
    // Conservar el origen solo si sigue siendo válido; si no, limpiarlo
    // (se mantiene solicitaTraslado=true para bloquear la confirmación).
    if (item.tieneOrigenValido) {
      final opciones = origenesValidosParaLinea(
        disponibilidad: disp,
        sucursales: _sucursales,
        destinoId: _destinoId,
        cantidadNecesaria: item.cantidad,
      );
      final sigueValido = opciones.any((o) => o.sucursal.id == item!.origenId);
      if (!sigueValido) {
        bolsa.definirOrigen(varianteId, null, null);
      }
    }
  }

  /// Cambio centralizado de cantidad (aumentar y disminuir comparten vía).
  ///
  /// - Impide cantidades < 1 (usar Quitar para eliminar).
  /// - Invalida la evidencia anterior (estado a `cargando`, sin usar lo
  ///   cacheado para confirmar) y recarga con datos frescos.
  /// - La conciliación posterior limpia `solicitaTraslado`/origen si el
  ///   destino vuelve a cubrir, o limpia el origen si dejó de ser válido.
  /// - Descarta respuestas fuera de orden por versión y nunca hace
  ///   `setState` tras dispose.
  Future<void> _cambiarCantidad(ItemBolsa item, int nuevaCantidad) async {
    if (nuevaCantidad < 1) return;
    if (item.cantidad == nuevaCantidad) return;
    final varianteId = item.varianteId;
    if (mounted) {
      setState(() {
        _estadoDisponibilidad[varianteId] = EstadoDisponibilidad.cargando;
        _disponibilidad.remove(varianteId);
      });
    } else {
      _estadoDisponibilidad[varianteId] = EstadoDisponibilidad.cargando;
      _disponibilidad.remove(varianteId);
    }
    BolsaStore.instancia.cambiarCantidad(varianteId, nuevaCantidad);
    await _cargarDisponibilidad(varianteId);
  }

  List<OpcionOrigen> _origenesPara(ItemBolsa item) {
    if (_estadoDe(item.varianteId) != EstadoDisponibilidad.disponible) {
      return const [];
    }
    final disp = _disponibilidad[item.varianteId];
    if (disp == null) return const [];
    return origenesValidosParaLinea(
      disponibilidad: disp,
      sucursales: _sucursales,
      destinoId: _destinoId,
      cantidadNecesaria: item.cantidad,
    );
  }

  Future<void> _confirmar() async {
    final bolsa = BolsaStore.instancia;
    if (bolsa.vacia) return;
    if (_destinoId == null) {
      if (!mounted) return;
      setState(
        () => _errorEnvio =
            'Elige la sucursal donde quieres recoger tus prendas.',
      );
      return;
    }
    if (_enviando) return;
    // Validación defensiva con estado explícito: nunca se envía sin
    // disponibilidad verificada ni se invoca red ni se crea clave.
    for (final item in bolsa.items) {
      final estado = _estadoDe(item.varianteId);
      if (estado != EstadoDisponibilidad.disponible ||
          !_disponibilidad.containsKey(item.varianteId)) {
        if (!mounted) return;
        final hayCarga = estado == EstadoDisponibilidad.cargando ||
            estado == EstadoDisponibilidad.noConsultada;
        setState(() {
          _errorEnvio = hayCarga
              ? 'Verificando disponibilidad… Espera un momento e inténtalo de nuevo.'
              : 'No pudimos verificar la disponibilidad. Reintenta antes de confirmar.';
        });
        return;
      }
    }
    // Validación local de traslado con la disponibilidad verificada.
    for (final item in bolsa.items) {
      final disp = _disponibilidad[item.varianteId]!;
      final dispDestino = disponibleEnDestino(disp, _destinoId);
      final necesita = necesitaOrigenParaLinea(
        disponibleDestino: dispDestino,
        cantidadSolicitada: item.cantidad,
      );
      if (!necesita) {
        // Destino volvió a cubrir: limpiar rastro obsoleto antes de enviar.
        if (item.solicitaTraslado || item.tieneOrigenValido) {
          bolsa.solicitarTraslado(item.varianteId, false);
        }
        continue;
      }
      // Requiere traslado: activación obligatoria aunque el flag aún no se
      // haya conciliado (p. ej. disponibilidad recién llegada).
      if (!item.solicitaTraslado) {
        bolsa.solicitarTraslado(item.varianteId, true);
      }
      if (!item.tieneOrigenValido) {
        if (!mounted) return;
        setState(() {
          _errorEnvio = bolsa.items.length == 1
              ? 'Esta prenda requiere traslado: elige la sucursal de origen para confirmar.'
              : 'Hay prendas que requieren traslado: elige la sucursal de origen para confirmar.';
        });
        return;
      }
      final opciones = origenesValidosParaLinea(
        disponibilidad: disp,
        sucursales: _sucursales,
        destinoId: _destinoId,
        cantidadNecesaria: item.cantidad,
      );
      final valido = opciones.any((o) => o.sucursal.id == item.origenId);
      if (!valido) {
        // Origen incoherente (vacío distinto al destino o sin stock): se
        // limpia para exigir una elección válida y se bloquea localmente.
        bolsa.definirOrigen(item.varianteId, null, null);
        if (!mounted) return;
        setState(() {
          _errorEnvio =
              'El origen elegido ya no tiene disponibilidad suficiente: elige otra sucursal de origen.';
        });
        return;
      }
    }
    final sinOrigen = bolsa.lineasSinOrigen;
    if (sinOrigen.isNotEmpty) {
      if (!mounted) return;
      setState(() {
        _errorEnvio = sinOrigen.length == 1
            ? 'Esta prenda requiere traslado: elige la sucursal de origen para confirmar.'
            : 'Elige la sucursal de origen para las ${sinOrigen.length} prendas que piden traslado.';
      });
      return;
    }
    // Clave de idempotencia solo inmediatamente antes del primer POST válido.
    if (!mounted) return;
    setState(() {
      _enviando = true;
      _errorEnvio = null;
      _claveActual ??= const Uuid().v4();
    });
    try {
      final reserva = await _reservasSrv.crear(
        sucursalDestinoId: _destinoId!,
        items: bolsa.items,
        fechaVisita: _fechaVisita,
        observacion: _obs.text,
        claveIdempotencia: _claveActual,
      );
      bolsa.limpiar();
      if (!mounted) return;
      setState(() {
        _enviando = false;
        _claveActual = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Reserva ${reserva.codigo} creada. ¡Te esperamos!'),
          backgroundColor: Colors.green.shade700,
        ),
      );
      widget.onReservaCreada?.call();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        // Mantener _claveActual para que el reintento use la misma.
        _errorEnvio = e.toString();
        _enviando = false;
      });
    }
  }

  Future<void> _guardarOffline() async {
    final bolsa = BolsaStore.instancia;
    if (bolsa.vacia || _destinoId == null) return;
    setState(() => _enviando = true);
    try {
      final sesion = await SessionManager().leerValida();
      if (sesion == null ||
          sesion.usuario.empresaId == null ||
          sesion.usuario.empresaId!.isEmpty) {
        throw const ApiException(
          statusCode: 401,
          mensaje:
              'Inicia sesión con una cuenta activa antes de guardar reservas offline.',
        );
      }
      final op = await _offlineSrv.registrarReservaOffline(
        empresaId: sesion.usuario.empresaId!,
        sucursalId: _destinoId!,
        visitaEn: _fechaVisita ?? DateTime.now().add(const Duration(days: 1)),
        items: bolsa.items,
      );
      bolsa.limpiar();
      if (!mounted) return;
      setState(() {
        _enviando = false;
        _errorEnvio = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Solicitud offline ${op.operacionId.substring(0, 8)} guardada (PENDIENTE_ENVIO). Se sincronizará automáticamente.',
          ),
          backgroundColor: Colors.blue.shade800,
        ),
      );
      widget.onReservaCreada?.call();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _enviando = false;
        _errorEnvio = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(title: const Text('Bolsa de reserva')),
      body: AnimatedBuilder(
        animation: BolsaStore.instancia,
        builder: (ctx, _) {
          final bolsa = BolsaStore.instancia;
          if (bolsa.vacia) {
            return const VistaVacia(
              icono: Icons.shopping_bag_outlined,
              titulo: 'Tu bolsa está vacía',
              detalle:
                  'Explora el catálogo y agrega las prendas que quieras probarte en tienda.',
            );
          }
          if (_cargandoSuc) {
            return const VistaCarga(mensaje: 'Cargando sucursales…');
          }
          if (_errorSuc != null) {
            return VistaError(
              mensaje: _errorSuc!,
              onReintentar: _cargarSucursales,
            );
          }
          // Carga inicial controlada: solo variantes nunca consultadas inician
          // una única consulta. Un estado `error` permanece hasta reintento
          // manual o cambio legítimo de cantidad/destino.
          for (final item in bolsa.items) {
            if (_estadoDe(item.varianteId) ==
                EstadoDisponibilidad.noConsultada) {
              final id = item.varianteId;
              Future.microtask(() {
                if (!mounted) return;
                if (_estadoDe(id) != EstadoDisponibilidad.noConsultada) return;
                _cargarDisponibilidad(id);
              });
            }
          }
          final habilitado = _confirmarHabilitado;
          final etiqueta = _etiquetaConfirmar;
          // "Reintentar con la misma solicitud" solo tras un POST real con clave.
          final mostrarReintentoMismoPost =
              _errorEnvio != null && _claveActual != null && !_enviando;
          return SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 100),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          'Dónde quieres recoger',
                          style: TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 16,
                          ),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          'Todas las prendas llegan a la misma sucursal.',
                          style: TextStyle(color: Colors.grey),
                        ),
                        const SizedBox(height: 8),
                        DropdownButtonFormField<String>(
                          key: const ValueKey('bolsa-destino'),
                          initialValue: _destinoId,
                          isExpanded: true,
                          decoration: const InputDecoration(
                            labelText: 'Sucursal de destino',
                            border: OutlineInputBorder(),
                          ),
                          items: [
                            for (final s in _sucursales)
                              DropdownMenuItem(
                                value: s.id,
                                child: Text(
                                  '${s.nombre} · ${s.ciudadNombre ?? ''}',
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                          ],
                          onChanged: _alCambiarDestino,
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: _elegirFecha,
                                icon: const Icon(Icons.calendar_month_outlined),
                                label: Text(
                                  _fechaVisita == null
                                      ? 'Fecha de visita (opcional)'
                                      : formatoFechaCorta(_fechaVisita),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        TextField(
                          controller: _obs,
                          maxLines: 2,
                          decoration: const InputDecoration(
                            labelText: 'Comentario (opcional)',
                            hintText: 'Ej.: pasaré por la tarde',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                for (final item in bolsa.items)
                  _TarjetaLinea(
                    item: item,
                    destinoId: _destinoId,
                    estadoDisponibilidad: _estadoDe(item.varianteId),
                    disponibilidad: _disponibilidad[item.varianteId],
                    origenes: _origenesPara(item),
                    sucursales: _sucursales,
                    onRecargarDisponibilidad: () =>
                        _reintentarDisponibilidad(item.varianteId),
                    onCambiarCantidad: (nueva) => _cambiarCantidad(item, nueva),
                  ),
                const SizedBox(height: 10),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text('Total estimado'),
                            Text(
                              formatoPrecio(bolsa.totalEstimado),
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ],
                        ),
                        Text(
                          '${bolsa.totalPrendas} prenda(s) · se paga en tienda',
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                        if (_errorEnvio != null) ...[
                          const SizedBox(height: 8),
                          Text(
                            _errorEnvio!,
                            style: const TextStyle(color: Colors.red),
                          ),
                        ],
                        const SizedBox(height: 10),
                        SizedBox(
                          width: double.infinity,
                          child: ElevatedButton.icon(
                            key: const ValueKey('bolsa-confirmar'),
                            onPressed: habilitado ? _confirmar : null,
                            icon: _enviando
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      color: Colors.white,
                                    ),
                                  )
                                : const Icon(Icons.check_circle_outline),
                            label: Text(etiqueta),
                          ),
                        ),
                        if (mostrarReintentoMismoPost)
                          TextButton.icon(
                            onPressed: _confirmar,
                            icon: const Icon(Icons.refresh),
                            label: const Text(
                              'Reintentar con la misma solicitud',
                            ),
                          ),
                        if (_errorEnvio != null && !_enviando)
                          TextButton.icon(
                            onPressed: _guardarOffline,
                            icon: const Icon(Icons.cloud_off_outlined),
                            label: const Text(
                              'Guardar solicitud offline (CU04)',
                            ),
                          ),
                        Text(
                          'Destino: ${_destino()?.nombre ?? '—'}',
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// Tarjeta de una línea de la bolsa con traslado obligatorio cuando el
/// destino no cubre la cantidad.
///
/// - Si [estadoDisponibilidad] es `cargando`/`noConsultada` muestra
///   "Verificando disponibilidad…".
/// - Si es `error` muestra el mensaje de error y el botón "Reintentar" que
///   inicia una sola consulta manual.
/// - Si es `disponible` y no requiere traslado, muestra reserva local.
/// - Si requiere traslado, el traslado se activa automáticamente y
///   no es desactivable: se muestra "Requiere traslado" y selector válido.
/// - Nunca se elige origen automáticamente ni se envía origen vacío/nulo.
/// - El cambio de cantidad pasa por [onCambiarCantidad] para invalidar y
///   recargar.
class _TarjetaLinea extends StatelessWidget {
  final ItemBolsa item;
  final String? destinoId;
  final EstadoDisponibilidad estadoDisponibilidad;
  final List<DisponibilidadSucursal>? disponibilidad;
  final List<OpcionOrigen> origenes;
  final List<SucursalModel> sucursales;
  final VoidCallback onRecargarDisponibilidad;
  final Future<void> Function(int nuevaCantidad) onCambiarCantidad;

  const _TarjetaLinea({
    required this.item,
    required this.destinoId,
    required this.estadoDisponibilidad,
    required this.disponibilidad,
    required this.origenes,
    required this.sucursales,
    required this.onRecargarDisponibilidad,
    required this.onCambiarCantidad,
  });

  @override
  Widget build(BuildContext context) {
    final bolsa = BolsaStore.instancia;
    final estaCargando =
        estadoDisponibilidad == EstadoDisponibilidad.cargando ||
            estadoDisponibilidad == EstadoDisponibilidad.noConsultada;
    final hayError = estadoDisponibilidad == EstadoDisponibilidad.error;
    final tieneDisp = estadoDisponibilidad == EstadoDisponibilidad.disponible &&
        disponibilidad != null;
    final dispDestino =
        tieneDisp ? disponibleEnDestino(disponibilidad!, destinoId) : null;
    final requiereTraslado = tieneDisp &&
        necesitaOrigenParaLinea(
          disponibleDestino: dispDestino!,
          cantidadSolicitada: item.cantidad,
        );

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.nombrePrenda,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      Text(
                        item.sku,
                        style: TextStyle(
                          color: Colors.grey.shade600,
                          fontSize: 12,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        formatoPrecio(item.precio),
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Quitar de la bolsa',
                  onPressed: () => bolsa.quitar(item.varianteId),
                  icon: const Icon(Icons.delete_outline),
                ),
              ],
            ),
            Row(
              children: [
                IconButton(
                  key: ValueKey('cantidad-menos-${item.varianteId}'),
                  tooltip: 'Quitar una',
                  onPressed: item.cantidad > 1
                      ? () => onCambiarCantidad(item.cantidad - 1)
                      : null,
                  icon: const Icon(Icons.remove_circle_outline),
                ),
                Text(
                  '${item.cantidad}',
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
                IconButton(
                  key: ValueKey('cantidad-mas-${item.varianteId}'),
                  tooltip: 'Agregar una',
                  onPressed: () => onCambiarCantidad(item.cantidad + 1),
                  icon: const Icon(Icons.add_circle_outline),
                ),
                const Spacer(),
                Text(
                  formatoPrecio(item.precio * item.cantidad),
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ],
            ),
            const Divider(),
            if (estaCargando)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  children: [
                    SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Verificando disponibilidad…',
                        style: TextStyle(fontSize: 13),
                      ),
                    ),
                  ],
                ),
              )
            else if (hayError)
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      'No pudimos verificar la disponibilidad. Reintenta antes de confirmar.',
                      style: TextStyle(fontSize: 13),
                    ),
                  ),
                  TextButton(
                    onPressed: onRecargarDisponibilidad,
                    child: const Text('Reintentar'),
                  ),
                ],
              )
            else if (!requiereTraslado)
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.green.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.green.shade200),
                ),
                child: Text(
                  'Hay $dispDestino disponible(s) en tu destino: se apartará localmente, sin traslado.',
                  style: TextStyle(
                    color: Colors.green.shade900,
                    fontSize: 13,
                  ),
                ),
              )
            else ...[
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.orange.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.orange.shade200),
                ),
                child: Text(
                  'En tu destino hay $dispDestino y necesitas ${item.cantidad}: esta prenda requiere traslado desde otra sucursal.',
                  style: TextStyle(
                    color: Colors.orange.shade900,
                    fontSize: 13,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              // Indicación no editable: el traslado es obligatorio mientras
              // el destino no cubra la cantidad (no desactivable).
              Container(
                key: ValueKey('traslado-requerido-${item.varianteId}'),
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: Colors.orange.shade100,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.orange.shade300),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.local_shipping_outlined,
                      size: 18,
                      color: Colors.orange.shade900,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Requiere traslado',
                        style: TextStyle(
                          color: Colors.orange.shade900,
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              if (origenes.isEmpty)
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.red.shade50,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.red.shade200),
                  ),
                  child: const Text(
                    'Ninguna otra sucursal tiene suficientes unidades por ahora. Prueba con otra cantidad o destino.',
                    style: TextStyle(fontSize: 13, color: Colors.red),
                  ),
                )
              else
                Builder(
                  builder: (context) {
                    // Solo se preselecciona si figura entre las opciones
                    // válidas (origenesValidosParaLinea). Nunca se elige
                    // automáticamente: sin elección no hay preselección.
                    final preseleccion = origenes.any(
                      (o) => o.sucursal.id == item.origenId,
                    )
                        ? item.origenId
                        : null;
                    return DropdownButtonFormField<String>(
                      key: ValueKey('traslado-origen-${item.varianteId}'),
                      initialValue: preseleccion,
                      decoration: const InputDecoration(
                        labelText: 'Sucursal de origen',
                        border: OutlineInputBorder(),
                      ),
                      items: [
                        for (final o in origenes)
                          DropdownMenuItem(
                            value: o.sucursal.id,
                            child: Text(
                              '${o.sucursal.nombre} · ${o.sucursal.ciudadNombre ?? ''} (${o.disponible})',
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                      ],
                      onChanged: (v) {
                        SucursalModel? s;
                        try {
                          s = sucursales.firstWhere((e) => e.id == v);
                        } catch (_) {
                          s = null;
                        }
                        bolsa.definirOrigen(item.varianteId, v, s?.nombre);
                      },
                    );
                  },
                ),
              if (item.bloqueaConfirmacion)
                const Padding(
                  padding: EdgeInsets.only(top: 6),
                  child: Text(
                    'Esta prenda requiere traslado: elige la sucursal de origen para confirmar.',
                    style: TextStyle(color: Colors.red, fontSize: 12),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
