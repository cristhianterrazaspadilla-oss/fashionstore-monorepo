"""Plan de consulta acotado. El texto nunca produce SQL ni cambia el tenant."""
import calendar
import re
import unicodedata
from datetime import datetime, timedelta

from fastapi import HTTPException
from backend.app.core.reloj import ZONA_NEGOCIO, entrada_local_a_utc

ADMITIDOS = "ventas por sucursal, ranking de productos, evolución semanal, ingresos por categoría y menor existencia"
MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
NUMEROS = {"un": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
           "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "veinte": 20}


def normalizar(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def aclarar(mensaje):
    raise HTTPException(422, detail="ACLARACION_REQUERIDA: " + mensaje)


def tipo_texto(texto):
    c = normalizar(texto)
    if re.search(r"(menor|baj[ao]|poc[ao]|critic|agot).*?(existencia|stock|inventario)|(?:existencia|stock|inventario).*?(menor|baj[ao]|critic|agot)", c):
        return "MENOR_EXISTENCIA"
    if re.search(r"(mas vendid|menos vendid|ranking|top|mejores prendas)", c):
        return "RANKING_PRODUCTOS"
    if re.search(r"categorias.*(ingres|venta)|ingres.*categorias", c):
        return "INGRESOS_POR_CATEGORIA"
    if re.search(r"seman|evolucion|tendencia", c) and re.search(r"venta|ingres|evolucion|tendencia", c):
        return "EVOLUCION_SEMANAL"
    if re.search(r"venta|ingres", c):
        return "VENTAS_POR_SUCURSAL"
    return None


def interpretar(datos, ahora):
    """Los filtros explícitos y el texto deben coincidir; una ambigüedad se devuelve al usuario."""
    d = datos.model_copy(deep=True)
    c = normalizar(d.consulta)
    tipo = tipo_texto(c)
    if d.tipo_reporte and tipo and d.tipo_reporte != tipo:
        aclarar("El tipo seleccionado contradice el texto. Selecciona el reporte solicitado o cambia la consulta.")
    d.tipo_reporte = d.tipo_reporte or tipo
    if not d.tipo_reporte:
        raise HTTPException(422, detail=f"FUERA_DE_ALCANCE: Se admiten {ADMITIDOS}.")
    if re.search(r"por (?:dia|mes|ano|vendedor|cliente)\b", c) or (re.search(r"agrupad\w* por categor", c) and d.tipo_reporte != "INGRESOS_POR_CATEGORIA"):
        aclarar("Esa agrupación no está disponible. Se admite sucursal, producto, categoría o semana según el reporte.")
    agrupacion = "SUCURSAL" if re.search(r"(?:por|cada) sucursal|agrupad\w* por sucursal", c) else None
    if d.agrupacion and agrupacion and d.agrupacion != agrupacion:
        aclarar("La agrupación del texto contradice el filtro seleccionado.")
    d.agrupacion = d.agrupacion or agrupacion or ("SUCURSAL" if d.tipo_reporte == "VENTAS_POR_SUCURSAL" else "GLOBAL")
    n = re.search(r"(?:los|las|top|primeros|primeras|mostrar|mostra|mostrame|limite)\s+(\d+|diez|cinco|veinte|dos|tres)\s*(?:productos|prendas|mas|menos|$)", c)
    limite = (int(n[1]) if n[1].isdigit() else NUMEROS[n[1]]) if n else None
    if limite and not 1 <= limite <= 100:
        aclarar("El límite admitido es de 1 a 100 resultados por grupo.")
    if d.limite and limite and d.limite != limite:
        aclarar("El límite del texto contradice el filtro seleccionado.")
    d.limite = d.limite or limite or (15 if d.tipo_reporte == "RANKING_PRODUCTOS" else 50)
    orden = "ASC" if re.search(r"ascendente|menor a mayor|menos vendidos", c) else ("DESC" if re.search(r"descendente|mayor a menor", c) else None)
    if d.orden and orden and d.orden != orden:
        aclarar("El orden del texto contradice el filtro seleccionado.")
    d.orden = d.orden or orden or ("ASC" if d.tipo_reporte in ("MENOR_EXISTENCIA", "EVOLUCION_SEMANAL") else "DESC")
    d.presentacion = d.presentacion or ("GRAFICO" if "grafico" in c else "TABLA")
    local = ahora.astimezone(ZONA_NEGOCIO)
    inicio = fin = None
    if "este mes" in c:
        inicio = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        fin = local
    elif m := re.search(r"ultimos?\s+(\d+|un|uno|dos|tres|seis|doce)\s+mes", c):
        meses = int(m[1]) if m[1].isdigit() else {**NUMEROS, "doce": 12}[m[1]]
        if not 1 <= meses <= 120:
            aclarar("Indica un período de 1 a 120 meses.")
        absoluto = local.year * 12 + local.month - 1 - meses
        anio, mes0 = divmod(absoluto, 12)
        inicio = local.replace(year=anio, month=mes0 + 1, day=min(local.day, calendar.monthrange(anio, mes0 + 1)[1]), hour=0, minute=0, second=0, microsecond=0)
        fin = local
    else:
        fechas = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", c)
        if fechas:
            if len(fechas) != 2:
                aclarar("Indica desde y hasta (AAAA-MM-DD), o completa ambos filtros de fecha.")
            try:
                inicio = datetime.fromisoformat(fechas[0]).replace(tzinfo=ZONA_NEGOCIO)
                fin = datetime.fromisoformat(fechas[1]).replace(tzinfo=ZONA_NEGOCIO) + timedelta(days=1, microseconds=-1)
            except ValueError:
                aclarar("Las fechas indicadas no son válidas.")
        else:
            for mes, nombre in enumerate(MESES, 1):
                if re.search(r"\b" + nombre + r"\b", c):
                    anio = re.search(r"\b(20\d{2})\b", c)
                    if not anio:
                        if not (d.desde and d.hasta):
                            aclarar(f"¿De qué año es {nombre}? Indica el año o selecciona desde y hasta.")
                        if entrada_local_a_utc(d.desde).astimezone(ZONA_NEGOCIO).month != mes:
                            aclarar("El mes solicitado no coincide con el filtro desde.")
                        break
                    anio = int(anio[1])
                    inicio = datetime(anio, mes, 1, tzinfo=ZONA_NEGOCIO)
                    fin = inicio.replace(day=calendar.monthrange(anio, mes)[1], hour=23, minute=59, second=59, microsecond=999999)
                    break
    if re.search(r"est[ea] period|ese period", c) and not (d.desde and d.hasta):
        aclarar("¿Qué período? Completa desde y hasta.")
    for campo, inferido in (("desde", inicio), ("hasta", fin)):
        valor = getattr(d, campo)
        if valor and inferido and entrada_local_a_utc(valor).astimezone(ZONA_NEGOCIO).date() != inferido.date():
            aclarar(f"La fecha {campo} seleccionada contradice el período del texto.")
        setattr(d, campo, entrada_local_a_utc(valor or inferido) if (valor or inferido) else None)
    if d.desde and d.hasta and d.desde > d.hasta:
        aclarar("Desde debe ser anterior a hasta.")
    if d.tipo_reporte == "MENOR_EXISTENCIA" and (d.desde or d.hasta):
        aclarar("Menor existencia consulta inventario disponible actual, no histórico. Retira las fechas.")
    return d
