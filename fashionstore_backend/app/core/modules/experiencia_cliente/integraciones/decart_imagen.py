"""Validación segura de imágenes del probador Decart (CU17).

Garantiza: URL HTTPS, host en allowlist (`DECART_ORIGENES_PERMITIDOS`),
prohibición de localhost/loopback/IP privada/link-local/destinos internos,
resolución DNS con validación de todas las IP resueltas (IPv4/IPv6), sin
redirecciones hacia hosts no permitidos, JPEG/PNG/WebP real (Content-Type
obligatorio + bytes + dimensiones), descarga por streaming con corte
inmediato al superar el tamaño máximo, dimensiones mínimas 512×512, timeout
de red, sin almacenar bytes y sin registrar URL firmada, contenido ni Base64.

Adaptadores inyectables para que las pruebas no descarguen imágenes reales
ni dependan de DNS real: validador, resolvedor DNS y fábrica de cliente HTTP.
"""
import asyncio
import ipaddress
import logging
import socket
from io import BytesIO
from typing import Awaitable, Callable, Optional
from urllib.parse import urljoin, urlparse

from fastapi import HTTPException, status

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

EXTENSIONES_PERMITIDAS = (".jpg", ".jpeg", ".png", ".webp")
MIME_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}
FORMATOS_PILLOW = {"JPEG", "PNG", "WEBP"}
DIMENSION_MINIMA = 512
MAX_REDIRECCIONES = 3
TAMANO_BLOQUE_STREAM = 65536


def origenes_permitidos() -> list:
    crudo = (
        getattr(settings, "DECART_ORIGENES_PERMITIDOS", "")
        or __import__("os").getenv("DECART_ORIGENES_PERMITIDOS", "")
        or ""
    )
    return [h.strip().lower() for h in str(crudo).split(",") if h.strip()]


def _es_host_prohibido(host: str) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return True
    if h in ("localhost", "localhost.localdomain"):
        return True
    for sufijo in (".localhost", ".local", ".internal", ".invalid", ".test.internal"):
        if h.endswith(sufijo):
            return True
    # Literales IP: prohibir loopback, privada, link-local, reservada, etc.
    try:
        ip = ipaddress.ip_address(h)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
            or not ip.is_global
        ):
            return True
        return False
    except ValueError:
        pass
    # Nombres con patrones internos evidentes.
    if h.startswith(("10.", "192.168.", "169.254.")):
        return True
    return False


# ---------------------------------------------------------------------------
# Resolución DNS inyectable (las pruebas fijan un doble sin red real).
# ---------------------------------------------------------------------------
ResolvedorDNS = Callable[[str], Awaitable[list]]
_resolvedor_dns_actual: Optional[ResolvedorDNS] = None


def fijar_resolvedor_dns(fn: Optional[ResolvedorDNS]) -> None:
    """Fija el resolvedor DNS para pruebas (None restaura el del sistema)."""
    global _resolvedor_dns_actual
    _resolvedor_dns_actual = fn


async def _resolver_dns_sistema(hostname: str) -> list:
    """Resuelve el hostname sin bloquear el event loop (hilo dedicado)."""

    def _lookup() -> list:
        infos = socket.getaddrinfo(
            hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
        )
        vistas: list = []
        for _fam, _tipo, _proto, _canon, sockaddr in infos:
            vistas.append(sockaddr[0])
        return list(dict.fromkeys(vistas))

    return await asyncio.to_thread(_lookup)


def obtener_resolvedor_dns() -> ResolvedorDNS:
    if _resolvedor_dns_actual is not None:
        return _resolvedor_dns_actual
    return _resolver_dns_sistema


async def _validar_dns_host(host: str) -> None:
    """Exige que TODAS las IP resueltas del host sean globales/públicas.

    Rechaza loopback, red privada, link-local, multicast, reservada,
    unspecified o cualquier destino interno/no global. Nunca confía solo en
    el texto del hostname: siempre resuelve DNS (inyectable en pruebas).
    """
    try:
        ips = await obtener_resolvedor_dns()(host)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No se pudo resolver el origen de la imagen",
        )
    if not ips:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Origen de imagen sin resolución DNS",
        )
    for ip_txt in ips:
        try:
            ip = ipaddress.ip_address(str(ip_txt).strip())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Origen de imagen no permitido (destino interno)",
            )
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or not ip.is_global
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Origen de imagen no permitido (destino interno)",
            )


async def validar_host_seguro(host: str, permitidos: set) -> None:
    """Validación SSRF completa de un host: texto + allowlist exacta + DNS.

    Se exige antes de la descarga inicial y después de cada redirección.
    """
    h = (host or "").lower()
    if _es_host_prohibido(h):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Origen de imagen no permitido (destino interno)",
        )
    if h not in permitidos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Origen de imagen no permitido",
        )
    await _validar_dns_host(h)


# ---------------------------------------------------------------------------
# Fábrica de cliente HTTP inyectable (pruebas con transporte simulado).
# ---------------------------------------------------------------------------
FabricaClienteHTTP = Callable[..., object]
_fabrica_cliente_actual: Optional[FabricaClienteHTTP] = None


def fijar_fabrica_cliente_http(fn: Optional[FabricaClienteHTTP]) -> None:
    """Fija la fábrica de AsyncClient para pruebas (None restaura httpx)."""
    global _fabrica_cliente_actual
    _fabrica_cliente_actual = fn


def _crear_cliente_http(timeout: int):
    import httpx

    if _fabrica_cliente_actual is not None:
        return _fabrica_cliente_actual(timeout=timeout, follow_redirects=False)
    return httpx.AsyncClient(timeout=timeout, follow_redirects=False)


def validar_sintaxis(url: str) -> str:
    """Valida esquema, host, allowlist y extensión. Retorna hostname.

    422 si la URL no es HTTPS válida o el formato no es permitido; 503 si la
    integración está habilitada pero no hay allowlist configurada (falla
    controlada sin afectar otros módulos).
    """
    try:
        partes = urlparse(url or "")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="URL de prenda inválida",
        )
    if partes.scheme != "https" or not partes.hostname:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La imagen de la prenda debe ser HTTPS",
        )
    host = partes.hostname.lower()
    if _es_host_prohibido(host):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Origen de imagen no permitido (destino interno)",
        )
    if not (partes.path or "").lower().endswith(EXTENSIONES_PERMITIDAS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Formato de imagen no permitido (solo JPEG, PNG o WebP)",
        )
    permitidos = origenes_permitidos()
    if not permitidos:
        # Sin allowlist no se acepta silenciosamente cualquier host cuando la
        # integración está habilitada: falla controlada solo del probador.
        if bool(settings.DECART_ENABLED):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "codigo": "DECART_ORIGENES_NO_CONFIGURADOS",
                    "mensaje": "Orígenes de imagen no configurados. "
                    "Configure DECART_ORIGENES_PERMITIDOS en backend/.env",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Origen de imagen no permitido",
        )
    if host not in permitidos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Origen de imagen no permitido",
        )
    return host


class ValidadorImagenDecart:
    """Validador real: sintaxis + contenido (sin persistir bytes)."""

    async def validar(self, url: str) -> None:
        host = validar_sintaxis(url)
        permitidos = set(origenes_permitidos())
        max_mb = int(getattr(settings, "DECART_IMAGEN_MAX_MB", 5) or 5)
        timeout = int(getattr(settings, "DECART_IMAGEN_TIMEOUT_SEGUNDOS", 8) or 8)
        max_bytes = max_mb * 1024 * 1024
        await self._validar_contenido(url, host, permitidos, max_bytes, timeout)

    async def _validar_contenido(
        self, url: str, host: str, permitidos: set, max_bytes: int, timeout: int
    ) -> None:
        import httpx

        # Protección SSRF previa a la descarga inicial (texto + DNS real).
        await validar_host_seguro(host, permitidos)
        actual = url
        # Un solo cliente para toda la cadena de redirecciones; se cierra
        # siempre al salir, incluso ante errores. Cada respuesta se cierra
        # con su propio contexto antes de seguir al siguiente salto.
        async with _crear_cliente_http(timeout) as cli:
            for _ in range(MAX_REDIRECCIONES + 1):
                partes_actual = urlparse(actual)
                host_actual = (partes_actual.hostname or "").lower()
                if partes_actual.scheme != "https" or not host_actual:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Redirección de imagen insegura",
                    )
                if _es_host_prohibido(host_actual) or host_actual not in permitidos:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Redirección hacia host no permitido",
                    )
                # DNS después de cada redirección: el texto ya no basta.
                await _validar_dns_host(host_actual)
                try:
                    async with cli.stream("GET", actual) as r:
                        if r.status_code in (301, 302, 303, 307, 308):
                            destino = r.headers.get("location", "")
                            try:
                                partes = urlparse(destino or "")
                            except Exception:
                                raise HTTPException(
                                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail="Redirección de imagen inválida",
                                )
                            # Relativa: resolver contra la actual; absoluta exige HTTPS.
                            if not partes.hostname:
                                destino = urljoin(actual, destino)
                                partes = urlparse(destino)
                            if partes.scheme != "https" or not partes.hostname:
                                raise HTTPException(
                                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail="Redirección de imagen insegura",
                                )
                            dest_host = partes.hostname.lower()
                            if _es_host_prohibido(dest_host) or dest_host not in permitidos:
                                raise HTTPException(
                                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    detail="Redirección hacia host no permitido",
                                )
                            actual = destino
                            continue
                        if r.status_code >= 400:
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Imagen de la prenda no disponible",
                            )
                        # Content-Type obligatorio: ausente o distinto de los
                        # MIME permitidos se rechaza sin descargar de más.
                        ctype = (
                            (r.headers.get("content-type", "") or "")
                            .split(";")[0]
                            .strip()
                            .lower()
                        )
                        if not ctype:
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="MIME de imagen ausente (solo JPEG, PNG o WebP)",
                            )
                        if ctype not in MIME_PERMITIDOS:
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="MIME de imagen no permitido (solo JPEG, PNG o WebP)",
                            )
                        # Rechazo anticipado por Content-Length, sin confiar
                        # solo en él: el corte real ocurre durante el stream.
                        try:
                            largo = int(r.headers.get("content-length", "0") or 0)
                        except ValueError:
                            largo = 0
                        if largo and largo > max_bytes:
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Imagen excede el tamaño máximo",
                            )
                        # Streaming real: leer por bloques e interrumpir en
                        # cuanto se supere el límite, sin descargar el resto.
                        datos = bytearray()
                        async for trozo in r.aiter_bytes(chunk_size=TAMANO_BLOQUE_STREAM):
                            if trozo:
                                datos.extend(trozo)
                                if len(datos) > max_bytes:
                                    raise HTTPException(
                                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                        detail="Imagen excede el tamaño máximo",
                                    )
                        if not datos:
                            raise HTTPException(
                                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                                detail="Imagen vacía",
                            )
                        self._validar_bytes(bytes(datos))
                        # No se almacenan los bytes: se descartan al salir.
                        return
                except HTTPException:
                    raise
                except (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Timeout al validar la imagen de la prenda",
                    )
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail={
                            "codigo": "DECART_IMAGEN_NO_DISPONIBLE",
                            "mensaje": "No se pudo validar la imagen de la prenda",
                        },
                    )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Demasiadas redirecciones de imagen",
        )

    def _validar_bytes(self, datos: bytes) -> None:
        from PIL import Image, UnidentifiedImageError
        from PIL.Image import DecompressionBombError

        try:
            with Image.open(BytesIO(datos)) as img:
                formato = (img.format or "").upper()
                if formato not in FORMATOS_PILLOW:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Formato real no permitido (solo JPEG, PNG o WebP)",
                    )
                ancho, alto = img.size
                if ancho < DIMENSION_MINIMA or alto < DIMENSION_MINIMA:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Imagen menor de 512×512",
                    )
                # Forzar decodificación para detectar contenido corrupto y
                # bombas de descompresión de forma controlada.
                try:
                    img.load()
                except (UnidentifiedImageError, DecompressionBombError, OSError, ValueError):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Contenido de imagen inválido",
                    )
        except HTTPException:
            raise
        except (UnidentifiedImageError, DecompressionBombError, OSError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Contenido de imagen inválido",
            )


# Gancho inyectable: las pruebas fijan un doble sin red.
_validador_actual: Optional[ValidadorImagenDecart] = None


def fijar_validador(validador: Optional[ValidadorImagenDecart]) -> None:
    global _validador_actual
    _validador_actual = validador


def obtener_validador() -> ValidadorImagenDecart:
    if _validador_actual is not None:
        return _validador_actual
    return ValidadorImagenDecart()


class ValidadorFalso(ValidadorImagenDecart):
    """Doble de pruebas: valida sintaxis + reglas inyectadas, sin red."""

    def __init__(self, modo: str = "ok"):
        self.modo = modo

    async def validar(self, url: str) -> None:
        # Sintaxis real (HTTPS, host, allowlist, extensión) sin descargar.
        validar_sintaxis(url)
        if self.modo == "ok":
            return
        if self.modo == "mime":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="MIME de imagen no permitido (solo JPEG, PNG o WebP)",
            )
        if self.modo == "pequena":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Imagen menor de 512×512",
            )
        if self.modo == "grande":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Imagen excede el tamaño máximo",
            )
        if self.modo == "redireccion":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Redirección hacia host no permitido",
            )
        if self.modo == "timeout":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Timeout al validar la imagen de la prenda",
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Contenido de imagen inválido",
        )
