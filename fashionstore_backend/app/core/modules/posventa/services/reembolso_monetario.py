"""Aritmetica exacta sobre el cargo original; nunca vuelve a cotizar."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, InvalidOperation
from fastapi import HTTPException


def conciliar(motivo):
    raise HTTPException(409, detail="CONCILIACION_REQUERIDA: " + motivo)


def dinero(valor):
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        conciliar("importe monetario ausente o invalido")
    if not d.is_finite() or d < 0 or d != d.quantize(Decimal('.01')):
        conciliar("importe monetario invalido")
    return d


def centavos_acumulados(bob, centavos, utilizado, centavos_utilizados, importe):
    """Redondeo acumulado HALF_UP: el ultimo parcial devuelve el resto exacto."""
    bob, utilizado, importe = map(dinero, (bob, utilizado, importe))
    if type(centavos) is not int or type(centavos_utilizados) is not int:
        conciliar("las unidades minimas deben ser enteros exactos")
    if bob <= 0 or centavos <= 0 or importe <= 0 or utilizado + importe > bob:
        conciliar("el importe supera el cargo original disponible")
    previo = int((Decimal(centavos) * utilizado / bob).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if previo != centavos_utilizados:
        conciliar("los parciales anteriores no corresponden al cargo original")
    nuevo = int((Decimal(centavos) * (utilizado + importe) / bob).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) - previo
    if nuevo <= 0 or nuevo + centavos_utilizados > centavos:
        conciliar("parcial no representable en unidades minimas; requiere agrupar o conciliar")
    return nuevo


def distribuir(importe, disponibles):
    """Proporcion por medio, restos mayores y desempate por orden estable."""
    importe = dinero(importe)
    pesos = [int(dinero(d) * 100) for d in disponibles]
    total = sum(pesos)
    unidades = int(importe * 100)
    if unidades <= 0 or unidades > total:
        conciliar("no hay saldo capturado suficiente para el reintegro")
    exactos = [Decimal(unidades) * p / total for p in pesos]
    partes = [int(x.to_integral_value(rounding=ROUND_FLOOR)) for x in exactos]
    for i in sorted(range(len(partes)), key=lambda i: (-(exactos[i] - partes[i]), i))[:unidades - sum(partes)]:
        partes[i] += 1
    return [Decimal(p) / 100 for p in partes]
