import '../../catalogo/models/catalogo_model.dart';
import '../../organizacion/models/organizacion_model.dart';

/// Opción de origen con stock verificado para una línea de la bolsa.
class OpcionOrigen {
  final SucursalModel sucursal;
  final int disponible;
  const OpcionOrigen({required this.sucursal, required this.disponible});

  String get etiqueta => '${sucursal.nombre} ($disponible)';
}

/// Disponibilidad de una variante en la sucursal destino.
int disponibleEnDestino(
  List<DisponibilidadSucursal> disponibilidad,
  String? destinoId,
) {
  if (destinoId == null || destinoId.isEmpty) return 0;
  for (final d in disponibilidad) {
    if (d.sucursalId == destinoId) return d.disponible;
  }
  return 0;
}

/// true cuando el destino no cubre la cantidad solicitada y la línea
/// necesita un origen con traslado.
bool necesitaOrigenParaLinea({
  required int disponibleDestino,
  required int cantidadSolicitada,
}) =>
    disponibleDestino < cantidadSolicitada;

/// Filtra orígenes válidos para una línea:
///
/// - distintos del destino;
/// - con [disponible] mayor o igual a [cantidadNecesaria];
/// - excluye [excluirOrigenId] (origen rechazado anteriormente);
/// - ordenados de mayor a menor disponibilidad.
List<OpcionOrigen> origenesValidosParaLinea({
  required List<DisponibilidadSucursal> disponibilidad,
  required List<SucursalModel> sucursales,
  required String? destinoId,
  required int cantidadNecesaria,
  String? excluirOrigenId,
}) {
  final porSucursal = <String, SucursalModel>{
    for (final s in sucursales) s.id: s,
  };
  final salida = <OpcionOrigen>[];
  for (final d in disponibilidad) {
    if (destinoId != null &&
        destinoId.isNotEmpty &&
        d.sucursalId == destinoId) {
      continue;
    }
    if (excluirOrigenId != null &&
        excluirOrigenId.isNotEmpty &&
        d.sucursalId == excluirOrigenId) {
      continue;
    }
    if (d.disponible < cantidadNecesaria) continue;
    final suc = porSucursal[d.sucursalId];
    if (suc == null) continue;
    salida.add(OpcionOrigen(sucursal: suc, disponible: d.disponible));
  }
  salida.sort((a, b) => b.disponible.compareTo(a.disponible));
  return salida;
}

/// Origen rechazado anteriormente para una línea, buscado en el
/// seguimiento de traslados (sin usar dynamic).
String? origenRechazadoParaLinea({
  required List<TrasladoRecibido> traslados,
  required String detalleReservaId,
}) {
  for (final t in traslados) {
    if (t.estado != 'RECHAZADO') continue;
    if (t.detalleIds.contains(detalleReservaId)) return t.origenId;
  }
  return null;
}

/// Vista mínima de traslado para localizar el origen rechazado sin
/// acoplar el helper al modelo completo de traslados.
class TrasladoRecibido {
  final String estado;
  final String origenId;
  final List<String> detalleIds;
  const TrasladoRecibido({
    required this.estado,
    required this.origenId,
    required this.detalleIds,
  });
}
