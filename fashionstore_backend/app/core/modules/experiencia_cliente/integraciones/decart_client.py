"""Cliente Decart Lucy 2.5 — solo autorización segura y auditoría (CU17).

El backend no implementa cámara ni video. Emite tokens cliente de 60 s con
allowedModels=["lucy-2.5"] y constraints.realtime.maxSessionDuration=120 vía
SDK oficial (`DecartClient(api_key=...)` + `client.tokens.create()`).
Nunca expone la API key permanente ni registra token, Base64, video, frames,
rostro, SDP o contenido audiovisual: solo metadatos sanitizados.
"""
import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

MODELO_EXCLUSIVO = "lucy-2.5"
TTL_SEGUNDOS = 60
SESION_MAX_SEGUNDOS = 120


class DecartDeshabilitado(Exception):
    pass


class DecartError(Exception):
    pass


@dataclass
class TokenClienteDecart:
    client_token: str
    expires_at: datetime
    modelo: str = MODELO_EXCLUSIVO
    max_session_duration_seconds: int = SESION_MAX_SEGUNDOS
    permissions: Optional[dict] = field(default=None)
    constraints: Optional[dict] = field(default=None)


def _habilitado() -> bool:
    return bool(settings.DECART_ENABLED and settings.DECART_API_KEY)


def parametros_token(correlation_id: str) -> dict:
    """Parámetros contractuales del SDK (`client.tokens.create`, snake_case).

    Expuestos para verificación en pruebas sin consumir créditos:
    expires_in=60, allowed_models=["lucy-2.5"],
    constraints.realtime.maxSessionDuration=120. Sin allowedOrigins (Android).
    """
    return {
        "expires_in": TTL_SEGUNDOS,
        "allowed_models": [MODELO_EXCLUSIVO],
        "constraints": {"realtime": {"maxSessionDuration": SESION_MAX_SEGUNDOS}},
        "metadata": {"correlation_id": correlation_id},
    }


def parametros_rest(correlation_id: str) -> dict:
    """Cuerpo camelCase del fallback `POST /v1/client/tokens` (sin allowedOrigins)."""
    return {
        "expiresIn": TTL_SEGUNDOS,
        "allowedModels": [MODELO_EXCLUSIVO],
        "constraints": {"realtime": {"maxSessionDuration": SESION_MAX_SEGUNDOS}},
        "metadata": {"correlation_id": correlation_id},
    }


def _parsear_expires_at(valor: Any) -> Optional[datetime]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        exp = valor
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        # SDK devuelve ISO ("...Z" o con offset).
        iso = texto.replace("Z", "+00:00")
        exp = datetime.fromisoformat(iso)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp
    except Exception:
        return None


def _extraer_token_sdk(respuesta: Any) -> tuple[str, Optional[datetime], Any, Any]:
    """Lee el contrato real del SDK: token.api_key, .expires_at, etc.

    Acepta el objeto `CreateTokenResponse` (snake_case) y, por tolerancia,
    dicts camelCase del REST. Nunca depende únicamente de `apiKey`.
    """
    if isinstance(respuesta, dict):
        token = (
            respuesta.get("api_key")
            or respuesta.get("apiKey")
            or respuesta.get("client_token")
            or respuesta.get("token")
        )
        expira = _parsear_expires_at(
            respuesta.get("expires_at") or respuesta.get("expiresAt")
        )
        return (
            str(token) if token else "",
            expira,
            respuesta.get("permissions"),
            respuesta.get("constraints"),
        )
    token = getattr(respuesta, "api_key", None)
    # Tolerancia legacy: algunos dobles antiguos exponían apiKey.
    if not token:
        token = getattr(respuesta, "apiKey", None)
    expira = _parsear_expires_at(getattr(respuesta, "expires_at", None))
    if expira is None:
        expira = _parsear_expires_at(getattr(respuesta, "expiresAt", None))
    return (
        str(token) if token else "",
        expira,
        getattr(respuesta, "permissions", None),
        getattr(respuesta, "constraints", None),
    )


async def _crear_con_sdk(correlation_id: str) -> TokenClienteDecart:
    """Camino principal: SDK oficial con cierre correcto del cliente."""
    from decart import DecartClient

    base = (settings.DECART_API_BASE_URL or "https://api.decart.ai").rstrip("/")
    # Context manager o cierre explícito: evita fugas de sesión HTTP.
    cliente = DecartClient(api_key=settings.DECART_API_KEY, base_url=base)
    try:
        res = await cliente.tokens.create(**parametros_token(correlation_id))
        token, expira, permisos, constraints = _extraer_token_sdk(res)
        if not token:
            raise DecartError("Respuesta del SDK sin token")
        if expira is None:
            expira = datetime.now(timezone.utc) + timedelta(seconds=TTL_SEGUNDOS)
        logger.info("Token Decart emitido cid=%s modelo=%s", correlation_id, MODELO_EXCLUSIVO)
        return TokenClienteDecart(
            client_token=token,
            expires_at=expira,
            permissions=dict(permisos) if isinstance(permisos, dict) else permisos,
            constraints=dict(constraints) if isinstance(constraints, dict) else constraints,
        )
    finally:
        try:
            await cliente.close()
        except Exception:
            pass


async def _crear_con_https(correlation_id: str) -> TokenClienteDecart:
    """Fallback HTTPS directo, solo si el SDK no está disponible.

    Contrato REST oficial verificado: JSON camelCase (expiresIn,
    allowedModels, constraints.realtime.maxSessionDuration), header
    `X-API-KEY`, lectura de `apiKey` y `expiresAt`. Sin `allowedOrigins`
    para Android.
    """
    import httpx

    base = (settings.DECART_API_BASE_URL or "https://api.decart.ai").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            r = await cli.post(
                f"{base}/v1/client/tokens",
                headers={"X-API-KEY": settings.DECART_API_KEY},
                json=parametros_rest(correlation_id),
            )
    except (asyncio.TimeoutError, TimeoutError) as exc_timeout:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"codigo": "DECART_NO_DISPONIBLE", "mensaje": "Proveedor no disponible (timeout)"},
        ) from exc_timeout
    except Exception as exc_red:
        nombre = type(exc_red).__name__
        texto = str(exc_red)
        if "timeout" in texto.lower() or "timeout" in nombre.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "DECART_NO_DISPONIBLE", "mensaje": "Proveedor no disponible (timeout)"},
            ) from exc_red
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"codigo": "DECART_NO_DISPONIBLE", "mensaje": "Proveedor no disponible"},
        ) from exc_red
    if r.status_code >= 400:
        raise DecartError(f"Decart rechazó la emisión ({r.status_code})")
    try:
        data = r.json()
    except Exception:
        raise DecartError("Respuesta Decart no JSON")
    token = data.get("apiKey") or data.get("api_key") or data.get("token")
    if not token:
        raise DecartError("Respuesta Decart sin token")
    expira = _parsear_expires_at(data.get("expiresAt") or data.get("expires_at"))
    if expira is None:
        expira = datetime.now(timezone.utc) + timedelta(seconds=TTL_SEGUNDOS)
    logger.info("Token Decart emitido cid=%s modelo=%s", correlation_id, MODELO_EXCLUSIVO)
    return TokenClienteDecart(
        client_token=str(token),
        expires_at=expira,
        permissions=data.get("permissions"),
        constraints=data.get("constraints"),
    )


async def crear_token_cliente(correlation_id: str) -> TokenClienteDecart:
    """Crea el token corto. 503 si deshabilitado/sin clave; 502 si Decart falla.

    SDK oficial como camino principal; el fallback HTTPS solo se usa si el
    SDK no está instalado (ImportError). Los errores del SDK (rechazo,
    timeout) nunca se convierten silenciosamente en una solicitud incorrecta:
    rechazo -> DecartError (502), timeout/indisponible -> 503. Nunca registra
    la API key permanente ni el token corto.
    """
    if not _habilitado():
        raise DecartDeshabilitado("Integración Decart deshabilitada o sin clave")
    modelo = (settings.DECART_MODEL or MODELO_EXCLUSIVO).strip() or MODELO_EXCLUSIVO
    if modelo != MODELO_EXCLUSIVO:
        raise DecartError("Modelo no autorizado para CU17")
    ttl = int(settings.DECART_TOKEN_TTL_SECONDS or TTL_SEGUNDOS)
    sesion = int(settings.DECART_SESSION_MAX_SECONDS or SESION_MAX_SEGUNDOS)
    if ttl != TTL_SEGUNDOS or sesion != SESION_MAX_SEGUNDOS:
        logger.warning("Config Decart distinta del contrato (ttl=%s sesion=%s)", ttl, sesion)
        ttl, sesion = TTL_SEGUNDOS, SESION_MAX_SEGUNDOS
    # 1. SDK oficial (principal).
    try:
        return await _crear_con_sdk(correlation_id)
    except DecartError:
        raise
    except HTTPException:
        raise
    except ImportError:
        logger.info("SDK Decart no instalado; intento HTTPS")
    except Exception as exc:
        # No convertir errores del proveedor en fallback incorrecto: si el
        # SDK está presente pero falló (rechazo/timeout/red), propagar con
        # el código correcto en lugar de reintentar por HTTPS.
        nombre = type(exc).__name__
        texto = str(exc)
        try:
            from decart.errors import TokenCreateError

            if isinstance(exc, TokenCreateError):
                raise DecartError(f"Decart rechazó la emisión: {texto}")
        except DecartError:
            raise
        except ImportError:
            pass
        if "timeout" in texto.lower() or "Timeout" in nombre:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "DECART_NO_DISPONIBLE", "mensaje": "Proveedor no disponible (timeout)"},
            )
        # Error genérico del SDK con red disponible: indisponible (503).
        # No se reintenta por HTTPS para no enmascarar el rechazo.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"codigo": "DECART_NO_DISPONIBLE", "mensaje": "Proveedor no disponible"},
        )
    # 2. Fallback HTTPS solo sin SDK.
    try:
        return await _crear_con_https(correlation_id)
    except DecartError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"codigo": "DECART_RECHAZO", "mensaje": "El proveedor rechazó la autorización"},
        )
    except HTTPException:
        raise


def autorizacion_no_disponible() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "codigo": "DECART_DESHABILITADO",
            "mensaje": "Probador virtual no configurado. Catálogo, carrito y reservas siguen operativos.",
        },
    )


# Gancho conmutable para pruebas (doble fiel al SDK, sin créditos).
_creador_falso = None


def fijar_creador_falso(fn) -> None:
    global _creador_falso
    _creador_falso = fn


async def emitir_token(correlation_id: str) -> TokenClienteDecart:
    if _creador_falso is not None:
        try:
            res = await _creador_falso(correlation_id)
        except (asyncio.TimeoutError, TimeoutError) as exc_timeout:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "DECART_NO_DISPONIBLE", "mensaje": "Proveedor no disponible (timeout)"},
            ) from exc_timeout
        except HTTPException:
            raise
        except DecartError:
            # Rechazo válido del proveedor: se propaga para mapeo 502 real.
            raise
        except Exception as exc:
            # El fake fiel imita el SDK: timeout o indisponibilidad de red
            # (p. ej. httpx.TimeoutException, ConnectionError) es 503; el
            # resto se propaga para su mapeo real (DecartError->502).
            nombre = type(exc).__name__
            texto = str(exc)
            minus = f"{nombre} {texto}".lower()
            if (
                "timeout" in minus
                or "timed out" in minus
                or "connect" in minus
                or "network" in minus
                or "unreachable" in minus
                or "unavailable" in minus
                or "dns" in minus
                or "refused" in minus
            ):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={"codigo": "DECART_NO_DISPONIBLE", "mensaje": "Proveedor no disponible (timeout)"},
                ) from exc
            raise
        # El fake fiel imita el SDK: objeto con api_key/expires_at.
        if isinstance(res, tuple) and len(res) == 2:
            token, expira = res
            return TokenClienteDecart(client_token=str(token), expires_at=expira)
        token, expira, permisos, constraints = _extraer_token_sdk(res)
        if not token:
            raise DecartError("Respuesta del SDK sin token")
        if expira is None:
            expira = datetime.now(timezone.utc) + timedelta(seconds=TTL_SEGUNDOS)
        return TokenClienteDecart(
            client_token=str(token), expires_at=expira,
            permissions=permisos, constraints=constraints,
        )
    return await crear_token_cliente(correlation_id)


def referencia_segura() -> str:
    return secrets.token_hex(8)
