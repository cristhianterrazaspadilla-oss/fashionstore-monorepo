// Modelos Ciclo 3 — Probador virtual Decart Lucy 2.5 (CU17/RN-07).
//
// - GET /variantes/{id}/prueba-virtual -> PruebaVirtualDTO
// - POST /probador/autorizaciones (Idempotency-Key) -> AutorizacionDTO
// Modelo exacto: lucy-2.5. Token de 60 s solo en memoria, sesión máx 120 s.
// Nunca guardar cámara, video, frames, token, API key, SDP, Base64 ni URLs.

/// Versión de consentimiento exigida por backend.
const String consentimientoDecartVigente = 'decart-v1';

/// Modelo Decart fijado por el proyecto.
const String modeloDecartFijado = 'lucy-2.5';

/// Duración máxima de sesión realtime (segundos).
const int duracionMaximaProbadorSegundos = 120;

/// Aviso permanente orientativo.
const String avisoProbadorPermanente =
    'Visualización orientativa. No garantiza talla, ajuste, caída, color ni reproducción exacta de la prenda.';

/// Recurso de prueba virtual de una variante (PruebaVirtualDTO).
class RecursoPruebaVirtual {
  final String varianteId;
  final bool compatible;
  final String imagenPrendaUrl;
  final String promptPrenda;
  final String proveedor;
  final String modelo;
  final String avisoOrientativo;

  RecursoPruebaVirtual({
    required this.varianteId,
    required this.compatible,
    required this.imagenPrendaUrl,
    required this.promptPrenda,
    required this.proveedor,
    required this.modelo,
    required this.avisoOrientativo,
  });

  factory RecursoPruebaVirtual.fromJson(Map<String, dynamic> j) =>
      RecursoPruebaVirtual(
        varianteId: '${j['variante_id'] ?? ''}',
        compatible: j['compatible'] == true,
        imagenPrendaUrl: '${j['imagen_prenda_url'] ?? ''}',
        promptPrenda: '${j['prompt_prenda'] ?? ''}',
        proveedor: '${j['proveedor'] ?? 'DECART'}',
        modelo: '${j['modelo'] ?? 'lucy-2.5'}',
        avisoOrientativo:
            '${j['aviso_orientativo'] ?? avisoProbadorPermanente}',
      );
}

/// Autorización temporal Decart (AutorizacionDTO). Solo en memoria.
class AutorizacionDecart {
  final String tokenCliente;
  final DateTime? expiraEn;
  final String modelo;
  final int duracionMaximaSegundos;
  final String imagenPrendaUrl;
  final String promptPrenda;

  AutorizacionDecart({
    required this.tokenCliente,
    this.expiraEn,
    required this.modelo,
    required this.duracionMaximaSegundos,
    required this.imagenPrendaUrl,
    required this.promptPrenda,
  });

  factory AutorizacionDecart.fromJson(Map<String, dynamic> j) {
    DateTime? exp;
    final raw = j['expires_at'];
    if (raw is DateTime) {
      exp = raw;
    } else if (raw != null) {
      exp = DateTime.tryParse(raw.toString());
    }
    return AutorizacionDecart(
      tokenCliente: '${j['client_token'] ?? ''}',
      expiraEn: exp,
      modelo: '${j['modelo'] ?? 'lucy-2.5'}',
      duracionMaximaSegundos:
          (j['max_session_duration_seconds'] as num?)?.toInt() ?? 120,
      imagenPrendaUrl: '${j['imagen_prenda_url'] ?? ''}',
      promptPrenda: '${j['prompt_prenda'] ?? ''}',
    );
  }

  bool get tokenVencido {
    final e = expiraEn;
    if (e == null) return false;
    return DateTime.now().toUtc().isAfter(e.toUtc());
  }
}

/// Estados mínimos del probador (puente nativo + UI).
///
/// Diferenciación obligatoria (corrección final Ciclo 3):
/// - `authorizing`: solicitando autorización al backend (token en memoria).
/// - `connecting`: conectando al proveedor (sin asumir video visible).
/// - `cameraReady`: cámara preparada, antes de autorizar.
/// - `remoteStream`: stream remoto disponible, cubierta conservada.
/// - `generating`: Decart procesando (GENERATING), cubierta conservada.
/// - `live`: primera transformación visible o prenda aplicada (único estado
///   que retira la cubierta, siempre con `primeraTransformacion == true`).
/// - `switchingGarment`: cambiando prenda, cubierta de transición.
/// - `closing` / `disconnected` / `error`: cierre y fallo.
/// CONNECTED, streamRemoto o GENERATING nunca implican resultado visible.
enum EstadoProbador {
  idle,
  requestingPermission,
  cameraReady,
  authorizing,
  connecting,
  remoteStream,
  generating,
  live,
  switchingGarment,
  closing,
  disconnected,
  error,
}

/// Prenda real para el probador virtual (CU17).
///
/// Prohibido el uso de datos ficticios (ej. "Prenda probada", SKU "Probador", precio 0).
/// Trabaja exclusivamente con datos autoritativos provenientes del backend.
class PrendaProbador {
  final String? productoId;
  final String varianteId;
  final String nombre;
  final String sku;
  final double precio;
  final String primeraImagenUrl;
  final String? descripcion;
  final String? atributos;

  PrendaProbador({
    this.productoId,
    required this.varianteId,
    required this.nombre,
    required this.sku,
    required this.precio,
    required this.primeraImagenUrl,
    this.descripcion,
    this.atributos,
  });

  /// Verifica si la prenda posee datos reales completos y autoritativos.
  bool get esValida =>
      varianteId.trim().isNotEmpty &&
      nombre.trim().isNotEmpty &&
      nombre.trim().toLowerCase() != 'prenda probada' &&
      sku.trim().isNotEmpty &&
      sku.trim().toLowerCase() != 'probador' &&
      precio > 0 &&
      primeraImagenUrl.trim().toLowerCase().startsWith('https://');

  Map<String, dynamic> toJson() => {
        'producto_id': productoId,
        'variante_id': varianteId,
        'nombre': nombre,
        'sku': sku,
        'precio': precio,
        'primera_imagen_url': primeraImagenUrl,
        'descripcion': descripcion,
        'atributos': atributos,
      };

  factory PrendaProbador.fromJson(Map<String, dynamic> j) => PrendaProbador(
        productoId: j['producto_id']?.toString(),
        varianteId: '${j['variante_id'] ?? ''}',
        nombre: '${j['nombre'] ?? ''}',
        sku: '${j['sku'] ?? ''}',
        precio: (j['precio'] is num)
            ? (j['precio'] as num).toDouble()
            : double.tryParse('${j['precio']}') ?? 0,
        primeraImagenUrl: '${j['primera_imagen_url'] ?? ''}',
        descripcion: j['descripcion'] as String?,
        atributos: j['atributos'] as String?,
      );
}
