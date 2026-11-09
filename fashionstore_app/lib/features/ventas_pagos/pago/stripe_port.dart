// Puerto Stripe Test (CU15).
//
// Abstrae PaymentSheet para probar polling, reintento y vencimiento sin
// depender del SDK nativo. La implementación real usa flutter_stripe; los
// tests usan FakePuertoStripe. El resultado visual nunca sustituye la
// confirmación del backend.
enum ResultadoHojaPago { completado, cancelado, fallido }

abstract class PuertoStripe {
  Future<void> inicializarHoja({required String clientSecret});
  Future<ResultadoHojaPago> presentarHoja();
}

/// Doble para pruebas: respuestas programadas sin Decart/Stripe reales.
class FakePuertoStripe implements PuertoStripe {
  final List<ResultadoHojaPago> respuestas;
  String? ultimoClientSecret;
  int inicializaciones = 0;
  int presentaciones = 0;

  FakePuertoStripe({required this.respuestas});

  @override
  Future<void> inicializarHoja({required String clientSecret}) async {
    inicializaciones++;
    ultimoClientSecret = clientSecret;
  }

  @override
  Future<ResultadoHojaPago> presentarHoja() async {
    presentaciones++;
    if (respuestas.isEmpty) return ResultadoHojaPago.cancelado;
    return respuestas.removeAt(0);
  }
}
