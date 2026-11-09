"""Servicio de Notificaciones, Bandeja y Dispositivos Autorizados (E2).

Implementa:
- Registro y revocación de dispositivos móviles y PWA (seguridad.dispositivos_autorizados).
- Emisión transaccional de eventos de negocio en outbox (comercial.eventos_outbox).
- Bandeja de notificaciones del cliente/usuario (comercial.notificaciones).
- Marcado de lectura y consulta durable.
- Despachador de notificaciones push real con adaptadores FCM y Web Push.
- Manejo de reintentos con SKIP LOCKED y revocación de tokens inválidos.
- Caída de push o simulación sin revertir transacciones de negocio.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Literal, Optional
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException, status
from jose import jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.modules.identidad_empresas.models import Usuario
from backend.app.core.modules.identidad_empresas.models_notificaciones import (
    DispositivoAutorizado,
    EventoOutbox,
    Notificacion,
)

logger = logging.getLogger("notificaciones")


def _push_setting(name: str) -> str:
    """Prioriza el entorno de Render y admite el .env local de Pydantic."""
    return os.environ.get(name, getattr(settings, name))


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class RegistroDispositivoDTO(BaseModel):
    dispositivo_id: uuid.UUID
    canal: Literal["PWA", "FLUTTER"]
    push_token: Optional[str] = None
    sucursal_id: Optional[uuid.UUID] = None


class DispositivoDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    dispositivo_id: uuid.UUID
    canal: str
    estado: str
    creado_en: datetime


class NotificacionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tipo: str
    titulo: str
    cuerpo: str
    recurso_tipo: Optional[str] = None
    recurso_id: Optional[uuid.UUID] = None
    creada_en: datetime
    leida_en: Optional[datetime] = None


# ============================================================================
# Adaptadores Push (FCM Android / Web Push PWA / Mock verificable)
# ============================================================================

class PushResult(BaseModel):
    exito: bool
    codigo: str  # "ACEPTADO", "TOKEN_INVALIDO", "TIMEOUT", "ERROR_PROVEEDOR", "NO_CONFIGURADO"
    token_invalido: bool = False
    mensaje_id: Optional[str] = None
    detalle: Optional[str] = None


class BasePushAdapter:
    async def enviar(
        self,
        token: str,
        canal: str,
        titulo: str,
        cuerpo: str,
        payload: Dict[str, Any],
    ) -> PushResult:
        raise NotImplementedError


def _es_url_segura_webpush(url_str: str) -> bool:
    """Verifica HTTPS y previene SSRF a loopback, metadatos e IPs privadas."""
    try:
        parsed = urlsplit(url_str)
        if parsed.scheme.lower() != "https":
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "169.254.169.254"):
            return False
        if hostname.startswith("10.") or hostname.startswith("192.168."):
            return False
        if hostname.startswith("172."):
            parts = hostname.split(".")
            if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
                return False
        return True
    except Exception:
        return False


def _b64decode_padding(s: str) -> bytes:
    pad = len(s) % 4
    if pad:
        s += "=" * (4 - pad)
    return base64.urlsafe_b64decode(s)


def cifrar_payload_webpush(payload_bytes: bytes, p256dh_b64: str, auth_b64: str) -> tuple[bytes, Dict[str, str]]:
    """Cifra el payload conforme a RFC 8291 (aes128gcm) para Web Push."""
    client_pub_bytes = _b64decode_padding(p256dh_b64)
    client_auth = _b64decode_padding(auth_b64)

    client_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), client_pub_bytes)
    local_key = ec.generate_private_key(ec.SECP256R1())
    local_pub_bytes = local_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    shared_secret = local_key.exchange(ec.ECDH(), client_key)

    auth_info = b"WebPush: info\x00" + client_pub_bytes + local_pub_bytes
    ikm = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=client_auth,
        info=auth_info,
    ).derive(shared_secret)

    salt = os.urandom(16)
    cek = HKDF(
        algorithm=hashes.SHA256(),
        length=16,
        salt=salt,
        info=b"Content-Encoding: aes128gcm\x00",
    ).derive(ikm)

    nonce = HKDF(
        algorithm=hashes.SHA256(),
        length=12,
        salt=salt,
        info=b"Content-Encoding: nonce\x00",
    ).derive(ikm)

    padded = payload_bytes + b"\x02"
    aesgcm = AESGCM(cek)
    ciphertext = aesgcm.encrypt(nonce, padded, None)

    rs = 4096
    header = salt + rs.to_bytes(4, "big") + len(local_pub_bytes).to_bytes(1, "big") + local_pub_bytes
    body = header + ciphertext

    headers = {
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
    }
    return body, headers


def generar_cabecera_vapid(
    endpoint: str,
    private_key_pem: str,
    public_key_b64: str,
    subject: str = "mailto:admin@fashionstore.local",
) -> str:
    """Genera cabecera Authorization VAPID conforme a RFC 8292 con firma ES256."""
    parsed = urlsplit(endpoint)
    aud = f"{parsed.scheme}://{parsed.netloc}"
    now_int = int(time.time())
    claims = {
        "aud": aud,
        "exp": now_int + 86400,
        "sub": subject,
    }
    vapid_jwt = jwt.encode(claims, private_key_pem, algorithm="ES256")
    return f"vapid t={vapid_jwt}, k={public_key_b64}"


class FCMPushAdapter(BasePushAdapter):
    """Adaptador Firebase Cloud Messaging (FCM v1) conforme a protocolo Google OAuth2."""

    def __init__(self, http_client: Optional[Any] = None):
        self.http_client = http_client
        self._token_cache: Optional[Dict[str, Any]] = None

    async def _obtener_oauth2_token(self, client: Any) -> Optional[tuple[str, str]]:
        ahora = time.time()
        if self._token_cache and self._token_cache.get("expira_en", 0) > ahora + 60:
            return self._token_cache["access_token"], self._token_cache["project_id"]

        cred_path = _push_setting("GOOGLE_APPLICATION_CREDENTIALS")
        cred_json_str = _push_setting("FCM_SERVICE_ACCOUNT_JSON")
        sa_data = None

        if cred_json_str:
            try:
                sa_data = json.loads(cred_json_str)
            except Exception:
                pass
        elif cred_path:
            if os.path.exists(cred_path):
                try:
                    with open(cred_path, "r", encoding="utf-8") as f:
                        sa_data = json.load(f)
                except Exception as e:
                    logger.warning(f"No se pudo leer GOOGLE_APPLICATION_CREDENTIALS: {e}")
            elif cred_path.strip().startswith("{"):
                try:
                    sa_data = json.loads(cred_path)
                except Exception:
                    pass

        if not sa_data or not isinstance(sa_data, dict):
            return None

        client_email = sa_data.get("client_email")
        private_key_pem = sa_data.get("private_key")
        project_id = sa_data.get("project_id") or _push_setting("FCM_PROJECT_ID")
        if not project_id:
            return None
        token_uri = sa_data.get("token_uri", "https://oauth2.googleapis.com/token")

        if not client_email or not private_key_pem:
            return None

        now_int = int(ahora)
        claims = {
            "iss": client_email,
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": token_uri,
            "exp": now_int + 3600,
            "iat": now_int,
        }
        try:
            assertion = jwt.encode(claims, private_key_pem, algorithm="RS256")
        except Exception as e:
            logger.error(f"Error firmando JWT assertion RS256 para Google: {e}")
            return None

        try:
            resp = await client.post(
                token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code == 200:
                data = resp.json()
                access_token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                self._token_cache = {
                    "access_token": access_token,
                    "project_id": project_id,
                    "expira_en": ahora + expires_in,
                }
                return access_token, project_id
            logger.error(f"Fallo token OAuth2 Google HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Error al conectar con token_uri de Google: {e}")
        return None

    async def enviar(
        self,
        token: str,
        canal: str,
        titulo: str,
        cuerpo: str,
        payload: Dict[str, Any],
    ) -> PushResult:
        import httpx

        client = self.http_client or httpx.AsyncClient(timeout=8.0)
        close_after = self.http_client is None
        try:
            token_info = await self._obtener_oauth2_token(client)
            if not token_info:
                return PushResult(
                    exito=False,
                    codigo="NO_CONFIGURADO",
                    detalle="FCM no configurado: falta archivo o JSON de cuenta de servicio Google con permisos FCM v1",
                )
            access_token, project_id = token_info
            url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; UTF-8",
            }
            body = {
                "message": {
                    "token": token,
                    "notification": {
                        "title": titulo,
                        "body": cuerpo,
                    },
                    "data": {str(k): str(v) for k, v in payload.items() if not str(k).startswith("_")},
                }
            }
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code in (200, 201):
                data = resp.json() if resp.content else {}
                msg_id = data.get("name") or f"fcm_{uuid.uuid4().hex[:12]}"
                return PushResult(
                    exito=True,
                    codigo="ACEPTADO",
                    mensaje_id=msg_id,
                    detalle="Aceptado por pasarela FCM v1",
                )
            elif resp.status_code in (404, 410):
                return PushResult(
                    exito=False,
                    codigo="TOKEN_INVALIDO",
                    token_invalido=True,
                    detalle=f"Token FCM no registrado o revocado (HTTP {resp.status_code})",
                )
            elif resp.status_code == 429:
                return PushResult(
                    exito=False,
                    codigo="RATE_LIMITED",
                    detalle="Límite de tasa excedido en FCM",
                )
            elif resp.status_code in (401, 403):
                return PushResult(
                    exito=False,
                    codigo="ERROR_AUTORIZACION",
                    detalle=f"Credenciales de FCM no autorizadas (HTTP {resp.status_code})",
                )
            else:
                return PushResult(
                    exito=False,
                    codigo="ERROR_PROVEEDOR",
                    detalle=f"Fallo del proveedor FCM HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as e:
            if isinstance(e, (httpx.TimeoutException, TimeoutError)):
                return PushResult(
                    exito=False,
                    codigo="TIMEOUT",
                    detalle=f"Timeout al invocar FCM: {str(e)}",
                )
            return PushResult(
                exito=False,
                codigo="ERROR_PROVEEDOR",
                detalle=f"Fallo al invocar FCM: {str(e)}",
            )
        finally:
            if close_after:
                await client.aclose()


class WebPushAdapter(BasePushAdapter):
    """Adaptador Web Push (RFC 8291 cifrado / RFC 8292 VAPID) para PWA."""

    def __init__(self, http_client: Optional[Any] = None):
        self.http_client = http_client

    async def enviar(
        self,
        token: str,
        canal: str,
        titulo: str,
        cuerpo: str,
        payload: Dict[str, Any],
    ) -> PushResult:
        import httpx

        vapid_private = _push_setting("VAPID_PRIVATE_KEY")
        vapid_public = _push_setting("VAPID_PUBLIC_KEY") or NotificacionService.obtener_clave_publica_vapid()
        if not vapid_private:
            return PushResult(
                exito=False,
                codigo="NO_CONFIGURADO",
                detalle="Web Push no configurado: falta VAPID_PRIVATE_KEY en entorno",
            )

        endpoint = token
        p256dh = None
        auth_key = None
        if token.strip().startswith("{"):
            try:
                sub_data = json.loads(token)
                endpoint = sub_data.get("endpoint", endpoint)
                keys = sub_data.get("keys", {})
                p256dh = keys.get("p256dh")
                auth_key = keys.get("auth")
            except Exception:
                pass

        if not _es_url_segura_webpush(endpoint):
            return PushResult(
                exito=False,
                codigo="DESTINO_INVALIDO",
                detalle=f"Endpoint Web Push no seguro o rechazado por SSRF: {endpoint}",
            )

        payload_data = {
            "title": titulo,
            "body": cuerpo,
            "data": {str(k): str(v) for k, v in payload.items() if not str(k).startswith("_")},
        }
        payload_bytes = json.dumps(payload_data, ensure_ascii=False).encode("utf-8")

        subject = _push_setting("VAPID_SUBJECT")
        try:
            auth_header = generar_cabecera_vapid(endpoint, vapid_private, vapid_public, subject)
        except Exception as e:
            return PushResult(
                exito=False,
                codigo="ERROR_VAPID",
                detalle=f"Fallo al generar firma VAPID ES256: {e}",
            )

        headers = {
            "TTL": "60",
            "Authorization": auth_header,
        }

        body: bytes
        if p256dh and auth_key:
            try:
                body_encrypted, enc_headers = cifrar_payload_webpush(payload_bytes, p256dh, auth_key)
                headers.update(enc_headers)
                body = body_encrypted
            except Exception as e:
                return PushResult(
                    exito=False,
                    codigo="ERROR_CIFRADO",
                    detalle=f"Fallo al cifrar payload Web Push (RFC 8291): {e}",
                )
        else:
            headers["Content-Length"] = "0"
            body = b""

        client = self.http_client or httpx.AsyncClient(timeout=8.0, follow_redirects=False)
        close_after = self.http_client is None
        try:
            resp = await client.post(endpoint, headers=headers, content=body)
            if resp.status_code in (200, 201, 202):
                return PushResult(
                    exito=True,
                    codigo="ACEPTADO",
                    mensaje_id=f"wp_{uuid.uuid4().hex[:12]}",
                    detalle="Aceptado por endpoint WebPush conforme a protocolo",
                )
            elif resp.status_code in (404, 410):
                return PushResult(
                    exito=False,
                    codigo="TOKEN_INVALIDO",
                    token_invalido=True,
                    detalle=f"Suscripción Web Push no válida o expirada (HTTP {resp.status_code})",
                )
            elif resp.status_code == 429:
                return PushResult(
                    exito=False,
                    codigo="RATE_LIMITED",
                    detalle="Límite de tasa excedido en Web Push",
                )
            else:
                return PushResult(
                    exito=False,
                    codigo="ERROR_PROVEEDOR",
                    detalle=f"Fallo del endpoint Web Push HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as e:
            if isinstance(e, (httpx.TimeoutException, TimeoutError)):
                return PushResult(
                    exito=False,
                    codigo="TIMEOUT",
                    detalle=f"Timeout al invocar Web Push: {str(e)}",
                )
            return PushResult(
                exito=False,
                codigo="ERROR_PROVEEDOR",
                detalle=f"Fallo al invocar Web Push: {str(e)}",
            )
        finally:
            if close_after:
                await client.aclose()


class MockPushAdapter(BasePushAdapter):
    """Adaptador determinista para pruebas de estados honestos de entrega y fallo."""

    def __init__(self, respuesta: str = "ACEPTADO"):
        self.respuesta = respuesta

    async def enviar(
        self,
        token: str,
        canal: str,
        titulo: str,
        cuerpo: str,
        payload: Dict[str, Any],
    ) -> PushResult:
        if self.respuesta == "ACEPTADO":
            return PushResult(
                exito=True,
                codigo="ACEPTADO",
                mensaje_id=f"mock_{canal}_{uuid.uuid4().hex[:8]}",
                detalle="Entrega aceptada por el proveedor simulado",
            )
        elif self.respuesta == "TOKEN_INVALIDO":
            return PushResult(
                exito=False,
                codigo="TOKEN_INVALIDO",
                token_invalido=True,
                detalle="Token no registrado o revocado por el proveedor",
            )
        elif self.respuesta == "TIMEOUT":
            return PushResult(
                exito=False,
                codigo="TIMEOUT",
                detalle="Tiempo de espera agotado al conectar con el servicio push",
            )
        elif self.respuesta == "ERROR_PROVEEDOR":
            return PushResult(
                exito=False,
                codigo="ERROR_PROVEEDOR",
                detalle="Error interno del proveedor de notificaciones (500)",
            )
        elif self.respuesta == "NO_CONFIGURADO":
            return PushResult(
                exito=False,
                codigo="NO_CONFIGURADO",
                detalle="Proveedor push no configurado en entorno",
            )
        return PushResult(
            exito=False,
            codigo="DESCONOCIDO",
            detalle=f"Respuesta simulada desconocida: {self.respuesta}",
        )


# ============================================================================
# Servicio de Negocio
# ============================================================================

class NotificacionService:
    @staticmethod
    def obtener_clave_publica_vapid() -> str:
        """Retorna la clave pública VAPID en base64url no comprimido (P-256)."""
        vapid_pub = _push_setting("VAPID_PUBLIC_KEY")
        if vapid_pub:
            return vapid_pub
        vapid_priv = _push_setting("VAPID_PRIVATE_KEY")
        if vapid_priv:
            try:
                from cryptography.hazmat.primitives.serialization import load_pem_private_key
                key = load_pem_private_key(vapid_priv.encode("utf-8"), password=None)
                pub_bytes = key.public_key().public_bytes(
                    serialization.Encoding.X962,
                    serialization.PublicFormat.UncompressedPoint,
                )
                return base64.urlsafe_b64encode(pub_bytes).decode("utf-8").rstrip("=")
            except Exception:
                pass
        # Clave pública VAPID canónica para desarrollo y pruebas
        return "BLhc4i0LB2yTy_IinZKPUTrkgcZBecC3ovCLPHEx0Ij_krxrHwl5Qa1LfN8ruHenn89t6vi9WTnhNCuB38XUZ0s"

    def __init__(
        self,
        db: AsyncSession,
        adapter_fcm: Optional[BasePushAdapter] = None,
        adapter_webpush: Optional[BasePushAdapter] = None,
    ):
        self.db = db
        self.adapter_fcm = adapter_fcm or FCMPushAdapter()
        self.adapter_webpush = adapter_webpush or WebPushAdapter()

    async def registrar_dispositivo(
        self, usuario: Usuario, dto: RegistroDispositivoDTO
    ) -> DispositivoDTO:
        if not usuario.empresa_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Usuario sin empresa asignada",
            )

        token_bytes = dto.push_token.encode("utf-8") if dto.push_token else None
        token_hash = hashlib.sha256(token_bytes).hexdigest() if token_bytes else None

        stmt = select(DispositivoAutorizado).where(
            DispositivoAutorizado.empresa_id == usuario.empresa_id,
            DispositivoAutorizado.usuario_id == usuario.id,
            DispositivoAutorizado.canal == dto.canal,
            DispositivoAutorizado.dispositivo_id == dto.dispositivo_id,
        )
        disp = (await self.db.execute(stmt)).scalars().first()

        ahora = _ahora_utc()
        if disp is not None:
            disp.estado = "ACTIVO"
            disp.push_destino_cifrado = token_bytes
            disp.push_destino_hash = token_hash
            disp.sucursal_id = dto.sucursal_id
            disp.revision += 1
            disp.revocado_en = None
        else:
            disp = DispositivoAutorizado(
                id=uuid.uuid4(),
                empresa_id=usuario.empresa_id,
                usuario_id=usuario.id,
                sucursal_id=dto.sucursal_id,
                canal=dto.canal,
                dispositivo_id=dto.dispositivo_id,
                push_destino_cifrado=token_bytes,
                push_destino_hash=token_hash,
                estado="ACTIVO",
                revision=1,
                creado_en=ahora,
            )
            self.db.add(disp)

        await self.db.flush()
        return DispositivoDTO.model_validate(disp)

    async def revocar_dispositivo(
        self, usuario: Usuario, dispositivo_id: uuid.UUID
    ) -> None:
        if not usuario.empresa_id:
            return

        stmt = select(DispositivoAutorizado).where(
            DispositivoAutorizado.empresa_id == usuario.empresa_id,
            DispositivoAutorizado.usuario_id == usuario.id,
            DispositivoAutorizado.dispositivo_id == dispositivo_id,
            DispositivoAutorizado.estado == "ACTIVO",
        )
        disp = (await self.db.execute(stmt)).scalars().first()
        if disp is not None:
            disp.estado = "REVOCADO"
            disp.revocado_en = _ahora_utc()
            disp.revision += 1
            await self.db.flush()

    async def emitir_notificacion(
        self,
        empresa_id: uuid.UUID,
        usuario_id: uuid.UUID,
        tipo: str,
        titulo: str,
        cuerpo: str,
        recurso_tipo: Optional[str] = None,
        recurso_id: Optional[uuid.UUID] = None,
        payload: Optional[Dict[str, Any]] = None,
        dispositivo_id: Optional[uuid.UUID] = None,
    ) -> Notificacion:
        ahora = _ahora_utc()
        outbox_id = uuid.uuid4()
        evento = EventoOutbox(
            id=outbox_id,
            empresa_id=empresa_id,
            recurso_tipo=recurso_tipo or "NOTIFICACION",
            recurso_id=recurso_id or outbox_id,
            transicion=tipo,
            revision=1,
            dispositivo_id=dispositivo_id,
            payload=payload or {"titulo": titulo, "cuerpo": cuerpo},
            estado="PENDIENTE",
            intentos=0,
            creado_en=ahora,
        )
        self.db.add(evento)

        notif = Notificacion(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            outbox_id=outbox_id,
            tipo=tipo,
            titulo=titulo,
            cuerpo=cuerpo,
            recurso_tipo=recurso_tipo,
            recurso_id=recurso_id,
            creada_en=ahora,
        )
        self.db.add(notif)
        await self.db.flush()
        return notif

    async def listar_bandeja(
        self, usuario: Usuario, limite: int = 50
    ) -> List[NotificacionDTO]:
        if not usuario.empresa_id:
            return []

        stmt = (
            select(Notificacion)
            .where(
                Notificacion.empresa_id == usuario.empresa_id,
                Notificacion.usuario_id == usuario.id,
            )
            .order_by(desc(Notificacion.creada_en))
            .limit(limite)
        )
        filas = (await self.db.execute(stmt)).scalars().all()
        return [NotificacionDTO.model_validate(f) for f in filas]

    async def marcar_leida(
        self, usuario: Usuario, notificacion_id: uuid.UUID
    ) -> NotificacionDTO:
        if not usuario.empresa_id:
            raise HTTPException(status_code=400, detail="Sin empresa asignada")

        stmt = select(Notificacion).where(
            Notificacion.id == notificacion_id,
            Notificacion.empresa_id == usuario.empresa_id,
            Notificacion.usuario_id == usuario.id,
        )
        notif = (await self.db.execute(stmt)).scalars().first()
        if notif is None:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")

        if notif.leida_en is None:
            notif.leida_en = _ahora_utc()
            await self.db.flush()

        return NotificacionDTO.model_validate(notif)

    async def procesar_outbox(
        self,
        empresa_id: Optional[uuid.UUID] = None,
        limite: int = 20,
        simular_fallo_push: bool = False,
        mock_modo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Procesa eventos pendientes de comercial.eventos_outbox con SKIP LOCKED.

        Solo marca ENVIADO cuando el proveedor push confirma aceptación verificable.
        Fallo de envío push jamas revierte datos o pagos de negocio.
        """
        ahora = _ahora_utc()
        condiciones = [EventoOutbox.estado.in_(["PENDIENTE", "REINTENTO"])]
        if empresa_id:
            condiciones.append(EventoOutbox.empresa_id == empresa_id)

        stmt = (
            select(EventoOutbox)
            .where(*condiciones)
            .order_by(EventoOutbox.creado_en.asc())
            .limit(limite)
            .with_for_update(skip_locked=True)
        )
        eventos = (await self.db.execute(stmt)).scalars().all()

        procesados = 0
        enviados = 0
        reintentos = 0
        fallidos = 0
        sin_destinos = 0

        for ev in eventos:
            procesados += 1
            ev.intentos += 1

            if ev.intentos > 3:
                ev.estado = "FALLIDO"
                fallidos += 1
                continue

            # Buscar destinatarios y dispositivos autorizados
            disps: List[DispositivoAutorizado] = []
            if ev.dispositivo_id:
                stmt_disp = select(DispositivoAutorizado).where(
                    DispositivoAutorizado.empresa_id == ev.empresa_id,
                    DispositivoAutorizado.dispositivo_id == ev.dispositivo_id,
                    DispositivoAutorizado.estado == "ACTIVO",
                )
                disps = list((await self.db.execute(stmt_disp)).scalars().all())
            else:
                # Buscar usuario destinatario a través de la Notificación vinculada
                stmt_notif = select(Notificacion).where(Notificacion.outbox_id == ev.id)
                notif = (await self.db.execute(stmt_notif)).scalars().first()
                if notif:
                    stmt_disp = select(DispositivoAutorizado).where(
                        DispositivoAutorizado.empresa_id == ev.empresa_id,
                        DispositivoAutorizado.usuario_id == notif.usuario_id,
                        DispositivoAutorizado.estado == "ACTIVO",
                    )
                    disps = list((await self.db.execute(stmt_disp)).scalars().all())

            disps_con_token = [d for d in disps if d.push_destino_cifrado]

            if not disps_con_token:
                # No hay tokens activos para entrega push
                ev.estado = "SIN_DESTINOS"
                sin_destinos += 1
                continue

            # Despachar a cada dispositivo autorizado registrando resultado por destino
            payload_dict = dict(ev.payload) if isinstance(ev.payload, dict) else {}
            destinos_res = payload_dict.setdefault("_destinos_resultado", {})
            algun_exito = False
            algun_reintento = False

            titulo = payload_dict.get("titulo", "Notificación FashionStore")
            cuerpo = payload_dict.get("cuerpo", "")

            for disp in disps_con_token:
                disp_key = str(disp.id)
                # Si el dispositivo ya fue aceptado en un intento previo, no duplicar envío
                if destinos_res.get(disp_key) == "ACEPTADO":
                    algun_exito = True
                    continue

                token_str = disp.push_destino_cifrado.decode("utf-8", errors="ignore")

                # Seleccionar adaptador correspondiente o simulado
                if mock_modo:
                    adapter = MockPushAdapter(mock_modo)
                elif simular_fallo_push:
                    adapter = MockPushAdapter("TIMEOUT")
                elif disp.canal == "PWA":
                    adapter = self.adapter_webpush
                else:
                    adapter = self.adapter_fcm

                res = await adapter.enviar(
                    token=token_str,
                    canal=disp.canal,
                    titulo=titulo,
                    cuerpo=cuerpo,
                    payload=payload_dict,
                )

                destinos_res[disp_key] = res.codigo

                if res.token_invalido:
                    disp.estado = "REVOCADO"
                    disp.revocado_en = ahora
                    disp.revision += 1

                if res.exito:
                    algun_exito = True
                elif res.codigo in ("TIMEOUT", "ERROR_PROVEEDOR"):
                    algun_reintento = True

            ev.payload = payload_dict

            # Evaluar si todos los destinos vigentes fueron aceptados
            todos_aceptados = all(
                destinos_res.get(str(d.id)) == "ACEPTADO"
                for d in disps_con_token
            )

            if todos_aceptados:
                ev.estado = "ENVIADO"
                ev.entregado_en = ahora
                enviados += 1
            elif algun_reintento and ev.intentos < 3:
                ev.estado = "REINTENTO"
                reintentos += 1
            else:
                # Agotó reintentos o fallo no reintentable: señalar destinos fallidos
                destinos_fallidos = [
                    str(d.dispositivo_id) for d in disps_con_token if destinos_res.get(str(d.id)) != "ACEPTADO"
                ]
                payload_dict["_destinos_fallidos"] = destinos_fallidos
                if algun_exito:
                    # Entrega parcial: al menos un destino aceptado pero otro falló definitivamente
                    ev.estado = "FALLIDO_PARCIAL"
                    payload_dict["_entrega_parcial"] = True
                else:
                    ev.estado = "FALLIDO"
                ev.payload = payload_dict
                fallidos += 1

        await self.db.flush()
        return {
            "procesados": procesados,
            "enviados": enviados,
            "reintentos": reintentos,
            "fallidos": fallidos,
            "sin_destinos": sin_destinos,
        }


# ============================================================================
# Background Worker Outbox (Procesamiento recurrente no dependiente de llamadas manuales)
# ============================================================================

async def ejecutar_ciclo_worker_outbox(
    fabrica_sesiones: Callable[[], AsyncSession],
    empresa_id: Optional[uuid.UUID] = None,
    limite: int = 50,
    adapter_fcm: Optional[BasePushAdapter] = None,
    adapter_webpush: Optional[BasePushAdapter] = None,
) -> Dict[str, Any]:
    """Ejecuta una pasada del consumidor outbox con bloqueo y commit independiente."""
    async with fabrica_sesiones() as session:
        srv = NotificacionService(
            session,
            adapter_fcm=adapter_fcm,
            adapter_webpush=adapter_webpush,
        )
        res = await srv.procesar_outbox(empresa_id=empresa_id, limite=limite)
        await session.commit()
        return res
