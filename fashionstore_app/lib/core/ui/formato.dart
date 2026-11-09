import 'package:intl/intl.dart';
import '../utils/bolivia_time.dart';

final _moneda =
    NumberFormat.currency(locale: 'es_BO', symbol: 'Bs ', decimalDigits: 2);

String formatoPrecio(double v) => _moneda.format(v);

String formatoFecha(DateTime? f) {
  return BoliviaTime.formatVisible(f);
}

String formatoFechaCorta(DateTime? f) {
  return BoliviaTime.formatShort(f);
}

/// Texto de vigencia: "Vence el ..." + si ya venció.
String textoVigencia(DateTime? venceEn, {DateTime? ahora}) {
  if (venceEn == null) return 'Sin fecha de vencimiento registrada.';
  final ref = ahora ?? DateTime.now();
  final venceBolivia = BoliviaTime.toBolivia(venceEn);
  final ahoraBolivia = BoliviaTime.toBolivia(ref);
  if (ahoraBolivia.isAfter(venceBolivia)) {
    return 'Venció el ${formatoFecha(venceEn)}.';
  }
  final diff = venceBolivia.difference(ahoraBolivia);
  if (diff.inHours < 24) {
    return 'Vence el ${formatoFecha(venceEn)} (en ${diff.inHours} h aprox.).';
  }
  return 'Vence el ${formatoFecha(venceEn)} (en ${diff.inDays} día(s) aprox.).';
}
