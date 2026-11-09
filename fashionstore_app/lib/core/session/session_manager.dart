import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../../features/identidad_empresas/models/usuario_model.dart';

/// Sesión persistente del cliente.
///
/// Guarda token + perfil + vencimiento (24 h, igual que el JWT del backend).
/// La expiración se verifica en local antes de cada uso.
class SesionPersistente {
  final String token;
  final ClientePerfilModel usuario;
  final DateTime guardadaEn;
  final DateTime venceEn;

  SesionPersistente({
    required this.token,
    required this.usuario,
    required this.guardadaEn,
    required this.venceEn,
  });

  bool get expirada => DateTime.now().isAfter(venceEn);

  Map<String, dynamic> toJson() => {
        'token': token,
        'usuario': usuario.toJson(),
        'guardada_en': guardadaEn.toIso8601String(),
        'vence_en': venceEn.toIso8601String(),
      };

  factory SesionPersistente.fromJson(Map<String, dynamic> json) {
    return SesionPersistente(
      token: json['token'] as String? ?? '',
      usuario: ClientePerfilModel.fromJson(
        (json['usuario'] as Map?)?.cast<String, dynamic>() ?? {},
      ),
      guardadaEn: DateTime.tryParse(json['guardada_en'] as String? ?? '') ??
          DateTime.now(),
      venceEn: DateTime.tryParse(json['vence_en'] as String? ?? '') ??
          DateTime.now(),
    );
  }
}

class SessionManager {
  static const _kSesion = 'fs_sesion_v2';
  // Claves heredadas del Ciclo 1 para migración transparente.
  static const _kTokenLegacy = 'fs_token';
  static const _kUsuarioLegacy = 'fs_usuario';

  static const Duration vigencia = Duration(hours: 24);

  Future<void> guardar({
    required String token,
    required ClientePerfilModel usuario,
    DateTime? ahora,
  }) async {
    final now = (ahora ?? DateTime.now()).toUtc().toLocal();
    final sesion = SesionPersistente(
      token: token,
      usuario: usuario,
      guardadaEn: now,
      venceEn: now.add(vigencia),
    );
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kSesion, jsonEncode(sesion.toJson()));
    // Limpiar formato anterior para no mantener dos fuentes.
    await prefs.remove(_kTokenLegacy);
    await prefs.remove(_kUsuarioLegacy);
  }

  /// Lee la sesión válida. Retorna null si no hay o si expiró (y la limpia).
  Future<SesionPersistente?> leerValida({DateTime? ahora}) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kSesion);
    if (raw != null) {
      try {
        final sesion =
            SesionPersistente.fromJson(jsonDecode(raw) as Map<String, dynamic>);
        if (sesion.token.isEmpty) {
          await limpiar();
          return null;
        }
        final ref = ahora ?? DateTime.now();
        if (ref.isAfter(sesion.venceEn)) {
          await limpiar();
          return null;
        }
        return sesion;
      } catch (_) {
        await limpiar();
        return null;
      }
    }
    // Migración Ciclo 1: token + usuario sueltos (sin vencimiento guardado).
    final legacyToken = prefs.getString(_kTokenLegacy);
    final legacyUsuario = prefs.getString(_kUsuarioLegacy);
    if (legacyToken != null &&
        legacyToken.isNotEmpty &&
        legacyUsuario != null) {
      try {
        final usuario = ClientePerfilModel.fromJson(
          jsonDecode(legacyUsuario) as Map<String, dynamic>,
        );
        await guardar(token: legacyToken, usuario: usuario, ahora: ahora);
        return leerValida(ahora: ahora);
      } catch (_) {
        await limpiar();
        return null;
      }
    }
    return null;
  }

  Future<void> limpiar() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kSesion);
    await prefs.remove(_kTokenLegacy);
    await prefs.remove(_kUsuarioLegacy);
  }
}
