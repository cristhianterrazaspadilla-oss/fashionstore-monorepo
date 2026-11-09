import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

/// Helper para obtener un UUID de dispositivo estable y persistente en SharedPreferences (CU04).
class DispositivoHelper {
  static const _kDispositivoId = 'fs_dispositivo_id';
  static String? _cacheDispositivoId;

  static Future<String> obtenerDispositivoId() async {
    if (_cacheDispositivoId != null && _cacheDispositivoId!.isNotEmpty) {
      return _cacheDispositivoId!;
    }
    final prefs = await SharedPreferences.getInstance();
    var id = prefs.getString(_kDispositivoId);
    if (id == null || id.isEmpty) {
      id = const Uuid().v4();
      await prefs.setString(_kDispositivoId, id);
    }
    _cacheDispositivoId = id;
    return id;
  }
}
