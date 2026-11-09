import 'package:flutter/material.dart';

import 'colores.dart';

/// Estados uniformes de consulta: carga, vacío, error con reintento.
class VistaCarga extends StatelessWidget {
  final String mensaje;
  const VistaCarga({super.key, this.mensaje = 'Cargando…'});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 12),
            Text(mensaje, style: Theme.of(context).textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}

class VistaVacia extends StatelessWidget {
  final IconData icono;
  final String titulo;
  final String detalle;
  final String? accionTexto;
  final VoidCallback? onAccion;

  const VistaVacia({
    super.key,
    required this.icono,
    required this.titulo,
    required this.detalle,
    this.accionTexto,
    this.onAccion,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icono, size: 56, color: ColoresFS.textMuted),
            const SizedBox(height: 12),
            Text(
              titulo,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: ColoresFS.ink),
            ),
            const SizedBox(height: 6),
            Text(
              detalle,
              textAlign: TextAlign.center,
              style: const TextStyle(color: ColoresFS.textMuted),
            ),
            if (accionTexto != null && onAccion != null) ...[
              const SizedBox(height: 16),
              ElevatedButton(onPressed: onAccion, child: Text(accionTexto!)),
            ],
          ],
        ),
      ),
    );
  }
}

class VistaError extends StatelessWidget {
  final String mensaje;
  final VoidCallback onReintentar;

  const VistaError({
    super.key,
    required this.mensaje,
    required this.onReintentar,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined,
                size: 56, color: ColoresFS.danger),
            const SizedBox(height: 12),
            const Text(
              'No pudimos completar la consulta',
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: ColoresFS.ink),
            ),
            const SizedBox(height: 6),
            Text(
              mensaje,
              textAlign: TextAlign.center,
              style: const TextStyle(color: ColoresFS.textBody),
            ),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: onReintentar,
              icon: const Icon(Icons.refresh),
              label: const Text('Reintentar'),
            ),
          ],
        ),
      ),
    );
  }
}
