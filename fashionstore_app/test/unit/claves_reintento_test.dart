import 'package:fashionstore_movil/core/network/api_exception.dart';
import 'package:fashionstore_movil/features/reservas_traslados/reservas/claves_reintento.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('reintento con mismo origen reutiliza la misma clave', () {
    var contador = 0;
    final claves = ClavesReintento(generar: () => 'clave-${++contador}');

    final primera = claves.clavePara(lineaId: 'd-1', origenId: 'suc-a');
    final segunda = claves.clavePara(lineaId: 'd-1', origenId: 'suc-a');

    expect(primera, 'clave-1');
    expect(segunda, 'clave-1');
    expect(contador, 1);
  });

  test('cambiar el origen genera una clave nueva', () {
    var contador = 0;
    final claves = ClavesReintento(generar: () => 'clave-${++contador}');

    final original = claves.clavePara(lineaId: 'd-1', origenId: 'suc-a');
    final nueva = claves.clavePara(lineaId: 'd-1', origenId: 'suc-b');

    expect(original, isNot(equals(nueva)));
    expect(nueva, 'clave-2');
  });

  test('conflicto de payload invalida la clave para regenerarla', () {
    var contador = 0;
    final claves = ClavesReintento(generar: () => 'clave-${++contador}');

    expect(claves.clavePara(lineaId: 'd-1', origenId: 'suc-a'), 'clave-1');
    claves.invalidarPorConflicto('d-1');
    expect(claves.claveActual('d-1'), isNull);
    expect(claves.clavePara(lineaId: 'd-1', origenId: 'suc-a'), 'clave-2');
  });

  test('detecta 409 por idempotencia con payload distinto', () {
    expect(
      esConflictoIdempotencia(const ApiException(
        statusCode: 409,
        mensaje: 'Esta solicitud ya fue enviada con otros datos.',
        detalleTecnico: 'Idempotency-Key reutilizada con otro payload',
      )),
      isTrue,
    );
    expect(
      esConflictoIdempotencia(const ApiException(
        statusCode: 409,
        mensaje: 'No hay suficiente disponibilidad en esa sucursal.',
        detalleTecnico: 'Stock insuficiente en sucursal',
      )),
      isFalse,
    );
    expect(
      esConflictoIdempotencia(const ApiException(
        statusCode: 500,
        mensaje: 'Error interno',
      )),
      isFalse,
    );
  });
}
