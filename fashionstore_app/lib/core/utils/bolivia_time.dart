/// Utilidades de tiempo para la zona horaria oficial del negocio: America/La_Paz (UTC -04:00).
/// Todas las pantallas de FashionStore capturan y muestran horarios en esta zona.
class BoliviaTime {
  BoliviaTime._();

  static const Duration offset = Duration(hours: -4);
  static const String offsetString = '-04:00';

  /// Obtiene la hora actual proyectada en zona horaria de Bolivia (-04:00).
  static DateTime now() {
    return DateTime.now().toUtc().add(offset);
  }

  /// Convierte cualquier DateTime a la hora correspondiente en Bolivia.
  static DateTime toBolivia(DateTime dt) {
    return dt.toUtc().add(offset);
  }

  /// Parsea una cadena de fecha o DateTime y la convierte a Bolivia.
  static DateTime? tryParse(dynamic v) {
    if (v == null) return null;
    if (v is DateTime) return toBolivia(v);
    final parsed = DateTime.tryParse(v.toString());
    if (parsed == null) return null;
    return toBolivia(parsed);
  }

  /// Formatea la fecha en formato ISO 8601 estricto con offset -04:00
  /// Ejemplo: "2026-11-01T10:00:00-04:00"
  static String formatIso8601(DateTime dt) {
    final b = toBolivia(dt);
    final y = b.year.toString().padLeft(4, '0');
    final m = b.month.toString().padLeft(2, '0');
    final d = b.day.toString().padLeft(2, '0');
    final h = b.hour.toString().padLeft(2, '0');
    final min = b.minute.toString().padLeft(2, '0');
    final s = b.second.toString().padLeft(2, '0');
    return '$y-$m-${d}T$h:$min:$s$offsetString';
  }

  /// Atajo para fecha actual en ISO 8601 con offset Bolivia.
  static String ahoraIso() => formatIso8601(DateTime.now());

  /// Formatea un DateTime en ISO 8601 con offset Bolivia.
  static String aIso8601Bolivia(DateTime dt) => formatIso8601(dt);

  /// Verifica si una fecha ISO o DateTime emitidaEn está dentro de la ventana de 8 horas.
  static bool estaDentroVentana8Horas(dynamic emitidaEn, {DateTime? ahora}) {
    if (emitidaEn == null) return false;
    final dt = emitidaEn is DateTime ? emitidaEn : DateTime.tryParse(emitidaEn.toString());
    if (dt == null) return false;
    return dentroDeVentana8Horas(dt, ahora: ahora);
  }

  /// Formato legible completo para el usuario: "dd/MM/yyyy HH:mm"
  static String formatVisible(DateTime? dt) {
    if (dt == null) return '—';
    final b = toBolivia(dt);
    final d = b.day.toString().padLeft(2, '0');
    final m = b.month.toString().padLeft(2, '0');
    final y = b.year.toString().padLeft(4, '0');
    final h = b.hour.toString().padLeft(2, '0');
    final min = b.minute.toString().padLeft(2, '0');
    return '$d/$m/$y $h:$min';
  }

  /// Formato corto de fecha: "dd/MM/yyyy"
  static String formatShort(DateTime? dt) {
    if (dt == null) return '—';
    final b = toBolivia(dt);
    final d = b.day.toString().padLeft(2, '0');
    final m = b.month.toString().padLeft(2, '0');
    final y = b.year.toString().padLeft(4, '0');
    return '$d/$m/$y';
  }

  /// Verifica si una fecha de inicio de sesión se encuentra dentro de las 8 horas privadas.
  static bool dentroDeVentana8Horas(DateTime loginTime, {DateTime? ahora}) {
    final ref = ahora ?? DateTime.now();
    final diff = ref.toUtc().difference(loginTime.toUtc());
    return !diff.isNegative && diff.inHours < 8;
  }
}
