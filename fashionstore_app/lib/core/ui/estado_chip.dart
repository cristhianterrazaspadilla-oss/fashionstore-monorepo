import 'package:flutter/material.dart';

import 'colores.dart';

/// Etiqueta de estado con contraste accesible y texto comprensible.
class EstadoChip extends StatelessWidget {
  final String texto;
  final Color color;
  const EstadoChip({super.key, required this.texto, required this.color});

  factory EstadoChip.reserva(String estadoLegible, String estadoCrudo) {
    return EstadoChip(texto: estadoLegible, color: _colorReserva(estadoCrudo));
  }

  factory EstadoChip.traslado(String texto, String estadoCrudo) {
    return EstadoChip(texto: texto, color: _colorTraslado(estadoCrudo));
  }

  static Color _colorReserva(String e) {
    switch (e) {
      case 'PENDIENTE_TRASLADO':
        return ColoresFS.warning;
      case 'PENDIENTE':
        return ColoresFS.inkSoft;
      case 'PREPARADA':
        return ColoresFS.success;
      case 'ATENDIDA':
        return ColoresFS.brassStrong;
      case 'COMPLETADA':
        return ColoresFS.success;
      case 'CANCELADA':
      case 'VENCIDA':
        return ColoresFS.textMuted;
      default:
        return ColoresFS.inkSoft;
    }
  }

  static Color _colorTraslado(String e) {
    switch (e) {
      case 'RECIBIDO':
        return ColoresFS.success;
      case 'RECHAZADO':
        return ColoresFS.danger;
      case 'DESPACHADO':
      case 'APROBADO':
        return ColoresFS.inkSoft;
      default:
        return ColoresFS.warning;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Text(
        texto,
        style: TextStyle(
          color: color,
          fontWeight: FontWeight.w700,
          fontSize: 12.5,
        ),
      ),
    );
  }
}
