// Control de búsqueda por voz (CU20).
//
// La voz es una ayuda del buscador: convierte voz a texto editable y envía
// el texto al backend para interpretar filtros. Nunca persiste audio.
// Estados: permiso denegado, micrófono no disponible, escuchando,
// procesando, resultado, sin coincidencias, error.
import 'package:flutter/foundation.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:speech_to_text/speech_to_text.dart';

enum EstadoVoz {
  inactivo,
  permisoDenegado,
  permisoDenegadoPermanente,
  noDisponible,
  escuchando,
  procesando,
  resultado,
  sinCoincidencias,
  error,
}

/// Puerto mínimo para pruebas sin micrófono real.
abstract class ReconocedorVoz {
  Future<bool> inicializar();
  Future<void> escuchar({required void Function(String texto) alReconocer});
  Future<void> detener();
  bool get disponible;
}

/// Adaptador real con speech_to_text (sin guardar audio).
class ReconocedorVozReal implements ReconocedorVoz {
  final SpeechToText _stt;
  ReconocedorVozReal({SpeechToText? stt}) : _stt = stt ?? SpeechToText();

  @override
  bool get disponible => true;

  @override
  Future<bool> inicializar() async {
    try {
      return await _stt.initialize();
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> escuchar(
      {required void Function(String texto) alReconocer}) async {
    await _stt.listen(
      onResult: (r) => alReconocer(r.recognizedWords),
      listenOptions: SpeechListenOptions(
        partialResults: true,
      ),
    );
  }

  @override
  Future<void> detener() async {
    try {
      await _stt.stop();
    } catch (_) {}
  }
}

/// Doble para pruebas.
class ReconocedorVozFake implements ReconocedorVoz {
  final bool disponibleSimulado;
  final bool inicializaOk;
  final String textoSimulado;
  ReconocedorVozFake({
    this.disponibleSimulado = true,
    this.inicializaOk = true,
    this.textoSimulado = 'vestido rojo talla M',
  });

  @override
  bool get disponible => disponibleSimulado;

  @override
  Future<bool> inicializar() async => inicializaOk;

  @override
  Future<void> escuchar(
      {required void Function(String texto) alReconocer}) async {
    alReconocer(textoSimulado);
  }

  @override
  Future<void> detener() async {}
}

class ControlVoz extends ChangeNotifier {
  final ReconocedorVoz _voz;
  final Future<PermissionStatus> Function()? _permisoMock;
  final Future<bool> Function()? _abrirConfigMock;

  ControlVoz({
    ReconocedorVoz? reconocedor,
    Future<PermissionStatus> Function()? permisoMock,
    Future<bool> Function()? abrirConfigMock,
  })  : _voz = reconocedor ?? ReconocedorVozReal(),
        _permisoMock = permisoMock,
        _abrirConfigMock = abrirConfigMock;

  EstadoVoz estado = EstadoVoz.inactivo;
  String texto = '';
  String? error;

  Future<void> iniciar() async {
    error = null;
    PermissionStatus permiso;
    try {
      final mock = _permisoMock;
      permiso =
          mock != null ? await mock() : await Permission.microphone.request();
    } catch (_) {
      estado = EstadoVoz.noDisponible;
      notifyListeners();
      return;
    }
    if (permiso.isPermanentlyDenied) {
      estado = EstadoVoz.permisoDenegadoPermanente;
      notifyListeners();
      return;
    }
    if (permiso.isDenied || !permiso.isGranted) {
      estado = EstadoVoz.permisoDenegado;
      notifyListeners();
      return;
    }
    if (!_voz.disponible) {
      estado = EstadoVoz.noDisponible;
      notifyListeners();
      return;
    }
    final ok = await _voz.inicializar();
    if (!ok) {
      estado = EstadoVoz.noDisponible;
      notifyListeners();
      return;
    }
    estado = EstadoVoz.escuchando;
    notifyListeners();
    await _voz.escuchar(alReconocer: (t) {
      texto = t;
      notifyListeners();
    });
  }

  Future<bool> abrirConfiguracion() async {
    final mock = _abrirConfigMock;
    if (mock != null) return await mock();
    return await openAppSettings();
  }

  Future<void> detener() async {
    await _voz.detener();
    if (estado == EstadoVoz.escuchando) {
      estado = texto.trim().isEmpty ? EstadoVoz.inactivo : EstadoVoz.resultado;
      notifyListeners();
    }
  }

  void marcarProcesando() {
    estado = EstadoVoz.procesando;
    error = null;
    notifyListeners();
  }

  void marcarResultado({required bool hayCoincidencias}) {
    estado =
        hayCoincidencias ? EstadoVoz.resultado : EstadoVoz.sinCoincidencias;
    notifyListeners();
  }

  void marcarError(String mensaje) {
    estado = EstadoVoz.error;
    error = mensaje;
    notifyListeners();
  }

  void editarTexto(String nuevo) {
    texto = nuevo;
    notifyListeners();
  }
}
