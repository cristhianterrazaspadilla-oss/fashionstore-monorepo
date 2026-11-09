import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/probador_model.dart';
import '../../../core/ui/colores.dart';
import 'control_probador.dart';
import 'puente_decart.dart';

/// Superficie dedicada de Decart. El AndroidView se crea antes de conectar,
/// de modo que el bridge nativo ya dispone del renderer al recibir el stream.
class ProbadorEnVivoScreen extends StatefulWidget {
  final ControlProbador control;
  final List<PrendaProbador> prendas;
  final int indiceInicial;

  const ProbadorEnVivoScreen({
    super.key,
    required this.control,
    required this.prendas,
    required this.indiceInicial,
  });

  @override
  State<ProbadorEnVivoScreen> createState() => _ProbadorEnVivoScreenState();
}

class _ProbadorEnVivoScreenState extends State<ProbadorEnVivoScreen>
    with WidgetsBindingObserver {
  late int _indice;
  bool _inicioSolicitado = false;
  bool _inicioFinalizado = false;
  bool _saliendo = false;

  ControlProbador get _control => widget.control;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _indice = widget.indiceInicial;
    _control.addListener(_actualizar);
  }

  void _actualizar() {
    if (mounted) setState(() {});
  }

  Future<void> _rendererCreado(int _) async {
    if (_inicioSolicitado || !mounted) return;
    _inicioSolicitado = true;
    await _control.iniciar();
    _inicioFinalizado = true;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // El diálogo nativo de permiso pausa temporalmente la Activity. Solo se
    // considera abandono cuando la inicialización ya terminó.
    if (!_inicioFinalizado) return;
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      _salir();
    }
  }

  Future<void> _salir() async {
    if (_saliendo) return;
    _saliendo = true;
    await _control.cerrar();
    if (mounted) Navigator.pop(context, _indice);
  }

  Future<void> _cambiar(int nuevo) async {
    if (nuevo < 0 || nuevo >= widget.prendas.length || _control.ocupado) return;
    final prenda = widget.prendas[nuevo];
    setState(() => _indice = nuevo);
    await _control.cambiarPrenda(
      imagenUrl: prenda.primeraImagenUrl,
      prompt:
          'Replace only the current top with the referenced garment ${prenda.nombre}',
    );
  }

  String get _estado {
    switch (_control.estado) {
      case EstadoProbador.requestingPermission:
        return 'Autoriza la cámara para continuar';
      case EstadoProbador.authorizing:
        return 'Solicitando autorización segura…';
      case EstadoProbador.connecting:
        return 'Conectando con Decart…';
      case EstadoProbador.cameraReady:
        return 'Preparando la cámara…';
      case EstadoProbador.remoteStream:
        return 'Recibiendo video remoto…';
      case EstadoProbador.generating:
        return 'Decart está aplicando la prenda…';
      case EstadoProbador.switchingGarment:
        return 'Cambiando de prenda…';
      case EstadoProbador.error:
        return _control.error ?? 'No pudimos iniciar el probador.';
      default:
        return 'Preparando la prueba…';
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _control.removeListener(_actualizar);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final transformacionVisible =
        _control.enVivo && _control.primeraTransformacion;
    final vistaLocalVisible =
        _control.vistaLocalDisponible && _control.estado != EstadoProbador.error;
    final prenda = widget.prendas[_indice];
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _salir();
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: SafeArea(
          child: Stack(
            fit: StackFit.expand,
            children: [
              AndroidView(
                viewType: PuenteDecart.vistaVideo,
                creationParamsCodec: const StandardMessageCodec(),
                onPlatformViewCreated: _rendererCreado,
              ),
              if (!transformacionVisible && !vistaLocalVisible)
                ColoredBox(
                  color: Colors.black.withValues(alpha: 0.82),
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(28),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (_control.estado != EstadoProbador.error)
                            const CircularProgressIndicator(
                                color: Colors.white),
                          const SizedBox(height: 18),
                          Text(
                            _estado,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 17,
                            ),
                          ),
                          const SizedBox(height: 10),
                          Text(
                            _control.etapaDiagnostico,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: Colors.white70,
                              fontSize: 13,
                            ),
                          ),
                          if (_control.vigenciaTokenAlConectarSegundos !=
                              null) ...[
                            const SizedBox(height: 6),
                            Text(
                              'Token recibido con ${_control.vigenciaTokenAlConectarSegundos} s de vigencia',
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                color: Colors.white54,
                                fontSize: 12,
                              ),
                            ),
                          ],
                          if (_control.codigoError != null) ...[
                            const SizedBox(height: 6),
                            SelectableText(
                              'Código: ${_control.codigoError}',
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                color: Colors.amberAccent,
                                fontSize: 12,
                              ),
                            ),
                          ],
                          if (_control.estado == EstadoProbador.error) ...[
                            const SizedBox(height: 16),
                            ElevatedButton(
                              onPressed: _salir,
                              child: const Text('Volver'),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
              if (!transformacionVisible && vistaLocalVisible)
                Positioned(
                  left: 18,
                  right: 18,
                  bottom: widget.prendas.length > 1 ? 82 : 24,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 12),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.72),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Row(
                      children: [
                        const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            _estado,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              Positioned(
                top: 8,
                left: 8,
                right: 8,
                child: Row(
                  children: [
                    IconButton.filled(
                      tooltip: 'Cerrar probador',
                      onPressed: _salir,
                      icon: const Icon(Icons.close),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 10),
                        decoration: BoxDecoration(
                          color: Colors.black54,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          prenda.nombre,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 10),
                      decoration: BoxDecoration(
                        color: ColoresFS.brassStrong,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        '${_control.segundosRestantes} s',
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              if (widget.prendas.length > 1)
                Positioned(
                  left: 12,
                  right: 12,
                  bottom: 18,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                    decoration: BoxDecoration(
                      color: Colors.black54,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Row(
                      children: [
                        IconButton(
                          tooltip: 'Prenda anterior',
                          color: Colors.white,
                          onPressed: _indice > 0 && !_control.ocupado
                              ? () => _cambiar(_indice - 1)
                              : null,
                          icon: const Icon(Icons.arrow_back_ios_new),
                        ),
                        Expanded(
                          child: Text(
                            '${_indice + 1} de ${widget.prendas.length}',
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                        IconButton(
                          tooltip: 'Prenda siguiente',
                          color: Colors.white,
                          onPressed: _indice < widget.prendas.length - 1 &&
                                  !_control.ocupado
                              ? () => _cambiar(_indice + 1)
                              : null,
                          icon: const Icon(Icons.arrow_forward_ios),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
