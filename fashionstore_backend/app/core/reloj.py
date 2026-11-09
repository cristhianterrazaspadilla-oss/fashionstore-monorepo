"""Política temporal de FashionStore.

La zona civil del negocio es America/La_Paz. Persistencia y comparaciones usan
instantes UTC conscientes de zona; presentación e inputs locales usan Bolivia.
Nunca se depende de la zona configurada en el sistema operativo del servidor.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


ZONA_NEGOCIO = ZoneInfo("America/La_Paz")


class RelojSistema:
    """Reloj productivo: siempre UTC con tzinfo."""

    def ahora(self) -> datetime:
        return datetime.now(timezone.utc)


class RelojFijo:
    """Reloj determinista para pruebas: no avanza salvo avance() explicito."""

    def __init__(self, instante: datetime):
        if instante.tzinfo is None:
            instante = instante.replace(tzinfo=timezone.utc)
        self._instante = instante

    def ahora(self) -> datetime:
        return self._instante

    def avanzar(self, delta: timedelta) -> datetime:
        self._instante = self._instante + delta
        return self._instante


def utcnow() -> datetime:
    """Atajo productivo equivalente a RelojSistema().ahora()."""
    return datetime.now(timezone.utc)


def ahora_bolivia() -> datetime:
    """Hora civil actual del negocio, siempre con offset -04:00."""
    return datetime.now(ZONA_NEGOCIO)


def a_hora_bolivia(instante: datetime) -> datetime:
    """Convierte un instante a America/La_Paz para respuesta/presentación."""
    return asegurar_utc(instante).astimezone(ZONA_NEGOCIO)


def entrada_local_a_utc(instante: datetime) -> datetime:
    """Normaliza fechas recibidas del usuario.

    Si el cliente omite offset, se interpreta expresamente como hora boliviana,
    nunca como hora local del servidor. Con offset, se respeta el instante.
    """
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=ZONA_NEGOCIO)
    return instante.astimezone(timezone.utc)


def asegurar_utc(instante: datetime) -> datetime:
    """Normaliza un datetime naive a UTC (asume UTC si no tiene tzinfo)."""
    if instante.tzinfo is None:
        return instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone.utc)


# Vigencias RN-03: sin pago 24 h; con adelanto/pago confirmado 72 h.
# Base temporal: creada_en (el pago no mueve la base ni acumula extensiones).
VIGENCIA_SIN_PAGO = timedelta(hours=24)
VIGENCIA_CON_PAGO = timedelta(hours=72)


def calcular_vencimiento(creada_en: datetime, con_pago_confirmado: bool) -> datetime:
    """vence_en = creada_en + 24 h (sin pago) o + 72 h (con pago/adelanto)."""
    base = asegurar_utc(creada_en)
    return base + (VIGENCIA_CON_PAGO if con_pago_confirmado else VIGENCIA_SIN_PAGO)


def vencida(vence_en: datetime, ahora: datetime) -> bool:
    """True si el instante actual alcanzo o supero el vencimiento (UTC)."""
    return asegurar_utc(ahora) >= asegurar_utc(vence_en)
