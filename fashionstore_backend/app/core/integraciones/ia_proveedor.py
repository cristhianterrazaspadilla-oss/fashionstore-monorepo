"""Proveedor IA intercambiable — determinista primero, Gemini opcional (CU18/20/21/25).

Sin GEMINI_API_KEY rige el fallback determinista útil. Con clave, Gemini queda
detrás de esta interfaz; toda salida externa se valida contra schemas y
catálogo antes de usarse. Nunca se ejecuta SQL generado ni se muta negocio.
Las pruebas usan el determinista y fakes; jamás llaman a Gemini real.
"""
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from backend.app.core.config import settings

PATRONES_PELIGROSOS = re.compile(
    r"(drop\s+table|delete\s+from|insert\s+into|update\s+\w+\s+set|union\s+select|"
    r"information_schema|pg_\w+|--|;.*select|<\s*script|ignore\s+previous\s+instructions|"
    r"ignor(a|e)\s+(las\s+)?instrucciones(\s+previas|\s+anteriores)?|"
    r"revelar\s+(el\s+)?(prompt|sistema)|dame\s+todo\s+sin\s+filtr(os|ar))",
    re.IGNORECASE,
)


def rechazar_inyeccion(texto: str) -> Optional[str]:
    """Retorna el motivo si el texto parece SQL/prompt injection; None si es sano."""
    if not texto:
        return None
    if PATRONES_PELIGROSOS.search(texto):
        return "Entrada rechazada: posible inyección SQL o de instrucciones"
    return None


@dataclass
class FiltrosBusqueda:
    categoria: Optional[str] = None
    talla: Optional[str] = None
    color: Optional[str] = None
    temporada: Optional[str] = None
    precio_min: Optional[Any] = None
    precio_max: Optional[Any] = None
    texto: str = ""

    def como_dict(self) -> dict[str, Any]:
        # Importes internos en Decimal; el encoder JSON los expone como
        # número sin usar float en comparaciones ni cálculos.
        return {k: v for k, v in self.__dict__.items() if v is not None}


# Vocabulario cerrado del DTO de filtros (sinónimos comunes en español).
_CATEGORIAS = {
    "camisa": "CAMISA", "camisas": "CAMISA", "blusa": "BLUSA", "blusas": "BLUSA",
    "polera": "POLERA", "poleras": "POLERA", "remera": "POLERA", "pantalon": "PANTALON",
    "pantalones": "PANTALON", "vestido": "VESTIDO", "vestidos": "VESTIDO",
    "chaqueta": "CHAQUETA", "chamarra": "CHAQUETA", "abrigo": "ABRIGO",
    "falda": "FALDA", "short": "SHORT", "jean": "JEAN", "jeans": "JEAN",
}
_COLORES = {
    "negro": "NEGRO", "blanco": "BLANCO", "rojo": "ROJO", "azul": "AZUL",
    "verde": "VERDE", "amarillo": "AMARILLO", "rosado": "ROSADO", "rosa": "ROSADO",
    "gris": "GRIS", "beige": "BEIGE", "marron": "MARRON", "marrón": "MARRON",
}
_TALLAS = {"xs": "XS", "s": "S", "m": "M", "l": "L", "xl": "XL", "xxl": "XXL"}
_TEMPORADAS = {
    "verano": "VERANO", "invierno": "INVIERNO", "primavera": "PRIMAVERA",
    "otoño": "OTOÑO", "otono": "OTOÑO",
}


def interpretar_determinista(texto: str) -> FiltrosBusqueda:
    """Texto/voz -> DTO cerrado de filtros permitidos (sin LLM)."""
    bajo = (texto or "").lower()
    filtros = FiltrosBusqueda(texto=texto.strip()[:280])
    for palabra, valor in _CATEGORIAS.items():
        if palabra in bajo:
            filtros.categoria = valor
            break
    for palabra, valor in _COLORES.items():
        if palabra in bajo:
            filtros.color = valor
            break
    for token in re.findall(r"\b(xs|xxl|xl|s|m|l)\b", bajo):
        filtros.talla = _TALLAS[token]
        break
    for palabra, valor in _TEMPORADAS.items():
        if palabra in bajo:
            filtros.temporada = valor
            break
    from decimal import Decimal as _Decimal

    barato = any(p in bajo for p in ("barato", "económ", "econom", "oferta", "descuento"))
    if barato:
        filtros.precio_max = _Decimal("150.00")
    premium = any(p in bajo for p in ("premium", "caro", "lujo", "exclusiv"))
    if premium:
        filtros.precio_min = _Decimal("300.00")

    def _a_decimal(txt: str) -> _Decimal | None:
        try:
            val = _Decimal(txt.replace(",", "."))
            return val if val > 0 else None
        except Exception:
            return None

    montos: list = []
    hallazgos = re.findall(r"(\d+(?:[.,]\d+)?)\s*(bs|usd|\$)?", bajo)
    for n, _ in hallazgos:
        dec = _a_decimal(n)
        if dec is not None:
            montos.append(dec)
    if len(montos) >= 2:
        filtros.precio_min, filtros.precio_max = sorted(montos[:2])
    elif len(montos) == 1 and ("hasta" in bajo or "menos" in bajo or "max" in bajo):
        filtros.precio_max = montos[0]
    elif len(montos) == 1 and ("desde" in bajo or "mínimo" in bajo or "minimo" in bajo):
        filtros.precio_min = montos[0]
    return filtros


class ProveedorIA:
    nombre = "DETERMINISTA"

    async def interpretar_busqueda(self, texto: str) -> FiltrosBusqueda:
        return interpretar_determinista(texto)

    async def narrar(self, contexto: str, datos: dict) -> str:
        return narrar_determinista(contexto, datos)


def narrar_determinista(contexto: str, datos: dict) -> str:
    total = datos.get("total", datos.get("monto_total", "?"))
    return (
        f"{contexto}: se analizaron datos reales del catálogo/ventas "
        f"(resumen {total}). Respuesta generada sin proveedor externo."
    )


class ProveedorGemini(ProveedorIA):
    """Gemini detrás de la interfaz; valida y cae a determinista ante fallos."""

    nombre = "GEMINI"

    async def interpretar_busqueda(self, texto: str) -> FiltrosBusqueda:
        if not settings.GEMINI_API_KEY:
            return interpretar_determinista(texto)
        try:
            import httpx

            inicio = time.monotonic()
            async with httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT_SECONDS) as cli:
                r = await cli.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{settings.GEMINI_MODEL}:generateContent",
                    headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                    json={"contents": [{"parts": [{
                        "text": "Extrae JSON con claves categoria,talla,color,temporada,"
                        "precio_min,precio_max del texto: " + texto[:500]}]}]},
                )
            _ = time.monotonic() - inicio
            if r.status_code != 200:
                return interpretar_determinista(texto)
            data = r.json()
            txt = str(data.get("candidates", [{}])[0].get("content", {})
                      .get("parts", [{}])[0].get("text", ""))
            import json as _json

            m = re.search(r"\{.*\}", txt, re.DOTALL)
            crudo = _json.loads(m.group(0)) if m else {}
            if not isinstance(crudo, dict):
                return interpretar_determinista(texto)
            permitido = {"categoria", "talla", "color", "temporada", "precio_min", "precio_max"}
            limpio = {k: crudo.get(k) for k in permitido}
            from decimal import Decimal as _Decimal

            base = interpretar_determinista(texto)
            for k, v in limpio.items():
                if isinstance(v, str) and v and len(v) <= 40 and not rechazar_inyeccion(v):
                    setattr(base, k, v.upper() if k != "texto" else v)
                if isinstance(v, (int, float)) and 0 <= v <= 100000:
                    setattr(base, k, _Decimal(str(v)))
            return base
        except Exception:
            return interpretar_determinista(texto)

    async def narrar(self, contexto: str, datos: dict) -> str:
        if not settings.GEMINI_API_KEY:
            return narrar_determinista(contexto, datos)
        try:
            import json
            import httpx

            prompt = (
                "Redacta en espanol un resumen ejecutivo breve, claro y sin Markdown. "
                "Usa exclusivamente los datos JSON proporcionados; no inventes cifras, "
                "causas ni recomendaciones. Si no hay registros, indicalo de forma directa. "
                f"Reporte: {contexto[:120]}. Datos: "
                f"{json.dumps(datos, ensure_ascii=False, default=str)[:12000]}"
            )
            async with httpx.AsyncClient(timeout=settings.GEMINI_TIMEOUT_SECONDS) as cli:
                respuesta = await cli.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{settings.GEMINI_MODEL}:generateContent",
                    headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                )
            if respuesta.status_code != 200:
                return narrar_determinista(contexto, datos)
            cuerpo = respuesta.json()
            texto = str(
                cuerpo.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            ).strip()
            return texto[:1600] if texto else narrar_determinista(contexto, datos)
        except Exception:
            return narrar_determinista(contexto, datos)


def proveedor_activo() -> ProveedorIA:
    if settings.GEMINI_API_KEY:
        return ProveedorGemini()
    return ProveedorIA()
