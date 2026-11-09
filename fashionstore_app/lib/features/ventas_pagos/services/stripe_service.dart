import 'dart:collection';
import 'dart:convert';
import 'package:crypto/crypto.dart';

import 'pago_service.dart';
export 'pago_service.dart';

/// Calcula el SHA-256 canónico de la compra v3 (CU05) conforme al contrato unificado.
///
/// Reglas canónicas:
/// 1. Claves ordenadas alfabéticamente.
/// 2. Sin espacios entre `:` y `,` (separators=(',', ':')).
/// 3. Importes con 2 decimales string (`toStringAsFixed(2)`).
/// 4. Líneas ordenadas por `variante_id` ascendente.
/// 5. Fechas en UTC con formato estricto `YYYY-MM-DDTHH:MM:SSZ` (sin microsegundos ni milisegundos).
/// 6. Dirección colapsada únicamente cuando la modalidad es `DELIVERY`.
String calcularHuellaCompraCanonica({
  required String empresaId,
  required String usuarioId,
  required String sucursalId,
  required String modalidad,
  String? direccion,
  required List<Map<String, dynamic>> lineas,
  required double baseBob,
  required double descuentoBob,
  required double envioBob,
  required double totalBob,
  required String monedaCobro,
  required double importeCobro,
  required String tasaId,
  required double tasaBobPorUsd,
  required String condicionesVersion,
  required String vigenteHasta,
}) {
  // 1. Ordenar líneas por variante_id asc
  final lineasOrdenadas = List<Map<String, dynamic>>.from(lineas)
    ..sort((a, b) => (a['variante_id'] ?? '').toString().compareTo((b['variante_id'] ?? '').toString()));

  final lineasFormateadas = lineasOrdenadas.map((l) {
    final cant = (l['cantidad'] as num).toInt();
    final pUnit = (l['precio_unitario_bob'] is num)
        ? (l['precio_unitario_bob'] as num).toDouble().toStringAsFixed(2)
        : (double.tryParse(l['precio_unitario_bob']?.toString() ?? '0')?.toStringAsFixed(2) ?? '0.00');
    final varId = (l['variante_id'] ?? '').toString();

    final m = SplayTreeMap<String, dynamic>();
    m['cantidad'] = cant;
    m['precio_unitario_bob'] = pUnit;
    m['variante_id'] = varId;
    return m;
  }).toList();

  // 2. SplayTreeMap para ordenar claves raíz alfabéticamente
  final payload = SplayTreeMap<String, dynamic>();
  payload['base_bob'] = baseBob.toStringAsFixed(2);
  payload['condiciones_version'] = condicionesVersion.trim();
  payload['descuento_bob'] = descuentoBob.toStringAsFixed(2);

  final modUpper = modalidad.toUpperCase().trim();
  if (direccion != null && modUpper == 'DELIVERY') {
    final dirColapsada = direccion.trim().split(RegExp(r'\s+')).where((s) => s.isNotEmpty).join(' ');
    if (dirColapsada.isNotEmpty) {
      payload['direccion'] = dirColapsada;
    }
  }

  payload['empresa_id'] = empresaId;
  payload['envio_bob'] = envioBob.toStringAsFixed(2);
  payload['importe_cobro'] = importeCobro.toStringAsFixed(2);
  payload['lineas'] = lineasFormateadas;
  payload['modalidad'] = modUpper;
  payload['moneda_cobro'] = monedaCobro.toUpperCase().trim();
  payload['sucursal_id'] = sucursalId;
  payload['tasa_bob_por_usd'] = tasaBobPorUsd.toStringAsFixed(2);
  payload['tasa_id'] = tasaId;
  payload['total_bob'] = totalBob.toStringAsFixed(2);
  payload['usuario_id'] = usuarioId;

  // 3. Normalizar fecha a UTC YYYY-MM-DDTHH:MM:SSZ
  String fechaUtc = vigenteHasta;
  final dt = DateTime.tryParse(vigenteHasta);
  if (dt != null) {
    final u = dt.toUtc();
    final y = u.year.toString().padLeft(4, '0');
    final m = u.month.toString().padLeft(2, '0');
    final d = u.day.toString().padLeft(2, '0');
    final h = u.hour.toString().padLeft(2, '0');
    final min = u.minute.toString().padLeft(2, '0');
    final s = u.second.toString().padLeft(2, '0');
    fechaUtc = '$y-$m-${d}T$h:$min:${s}Z';
  }
  payload['vigente_hasta'] = fechaUtc;

  final jsonStr = jsonEncode(payload);
  return sha256.convert(utf8.encode(jsonStr)).toString();
}

/// Servicio especializado de Stripe para app móvil FashionStore.
class StripeService extends PagoService {
  StripeService({super.api});
}
