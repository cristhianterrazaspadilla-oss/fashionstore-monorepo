// Componentes compartidos Ciclo 3: importes y tarjetas de producto.
//
// Reutilizan tema central, tokens de color y formato; sin colores literales,
// sin textos técnicos y con controles táctiles accesibles.
import 'package:flutter/material.dart';

import 'colores.dart';
import 'formato.dart';

/// Importe monetario con formato es_BO y protección contra overflow.
class Importe extends StatelessWidget {
  final double valor;
  final double? tamano;
  final FontWeight? peso;
  final Color? color;
  const Importe(this.valor, {super.key, this.tamano, this.peso, this.color});

  @override
  Widget build(BuildContext context) {
    return Text(
      formatoPrecio(valor),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      semanticsLabel: 'Importe ${formatoPrecio(valor)}',
      style: TextStyle(
        fontSize: tamano ?? 16,
        fontWeight: peso ?? FontWeight.w800,
        color: color ?? ColoresFS.ink,
      ),
    );
  }
}

/// Fila de total con etiqueta comprensible (subtotal, descuento, entrega).
class FilaTotal extends StatelessWidget {
  final String etiqueta;
  final double valor;
  final bool destacado;
  const FilaTotal({
    super.key,
    required this.etiqueta,
    required this.valor,
    this.destacado = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Expanded(
            child: Text(
              etiqueta,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: destacado ? ColoresFS.ink : ColoresFS.textBody,
                fontWeight: destacado ? FontWeight.w800 : FontWeight.w500,
                fontSize: destacado ? 16 : 14,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Importe(
            valor,
            tamano: destacado ? 18 : 15,
            peso: destacado ? FontWeight.w800 : FontWeight.w700,
          ),
        ],
      ),
    );
  }
}

/// Tarjeta compacta de prenda para carrito, recomendaciones y búsqueda.
class TarjetaPrenda extends StatelessWidget {
  final String nombre;
  final String? detalleVariante;
  final double precio;
  final String? imagenUrl;
  final String? pieDisponibilidad;
  final Widget? acciones;
  final VoidCallback? onAbrir;
  const TarjetaPrenda({
    super.key,
    required this.nombre,
    this.detalleVariante,
    required this.precio,
    this.imagenUrl,
    this.pieDisponibilidad,
    this.acciones,
    this.onAbrir,
  });

  @override
  Widget build(BuildContext context) {
    final img = (imagenUrl ?? '').isNotEmpty
        ? Image.network(
            imagenUrl!,
            width: 72,
            height: 72,
            fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => Container(
              width: 72,
              height: 72,
              color: ColoresFS.paper,
              child: const Icon(Icons.checkroom, color: ColoresFS.textMuted),
            ),
          )
        : Container(
            width: 72,
            height: 72,
            color: ColoresFS.paper,
            child: const Icon(Icons.checkroom, color: ColoresFS.textMuted),
          );
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(ColoresFS.radioTarjeta),
        onTap: onAbrir,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: img,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      nombre,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 15,
                        color: ColoresFS.ink,
                      ),
                    ),
                    if ((detalleVariante ?? '').isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        detalleVariante!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: ColoresFS.textMuted,
                          fontSize: 12.5,
                        ),
                      ),
                    ],
                    const SizedBox(height: 4),
                    Importe(precio, tamano: 15),
                    if ((pieDisponibilidad ?? '').isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        pieDisponibilidad!,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: ColoresFS.textMuted,
                          fontSize: 12.5,
                        ),
                      ),
                    ],
                    if (acciones != null) ...[
                      const SizedBox(height: 8),
                      acciones!,
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
