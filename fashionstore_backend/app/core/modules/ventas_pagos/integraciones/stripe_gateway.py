"""Puerta Stripe Test Mode — Ciclo 3 y E2 (CU15, CU22, CU27).

Sin claves la app inicia y este módulo responde 503 tipado; ninguna prueba
automática llama a Stripe real (usan FakeStripeGateway vía monkeypatch).
Con claves, el adaptador real usa httpx contra api.stripe.com (PaymentIntents, SetupIntents, Refunds)
y verifica el webhook con HMAC-SHA256 del cuerpo crudo (sin SDK obligatorio).
Nunca se almacena tarjeta/CVC: solo IDs (pi_*, seti_*, re_*) y estados.
"""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException, status

from backend.app.core.config import settings


class StripeDeshabilitado(Exception):
    """Stripe sin configurar o apagado: el endpoint debe responder 503 tipado."""


class FirmaStripeInvalida(Exception):
    """La firma del webhook no verifica contra el cuerpo crudo."""


@dataclass
class IntencionPago:
    id: str
    venta_id: str
    monto_centavos: int
    moneda: str
    estado: str  # REQUIRES_PAYMENT | SUCCEEDED | FAILED | CANCELED | REQUIRES_ACTION
    client_secret: Optional[str] = None
    empresa_id: Optional[str] = None
    cliente_id: Optional[str] = None
    metadata: Optional[dict] = None
    capturado_centavos: Optional[int] = None
    reembolsado_centavos: Optional[int] = None


@dataclass
class SetupIntentInfo:
    id: str
    cliente_id: str
    estado: str  # requires_payment_method | succeeded
    client_secret: Optional[str] = None
    customer: Optional[str] = None
    payment_method: Optional[str] = None
    empresa_id: Optional[str] = None


@dataclass
class ReembolsoInfo:
    id: str
    payment_intent_id: str
    centavos_usd: int
    estado: str  # succeeded | pending | failed | canceled | requires_action
    moneda: Optional[str] = None


class StripeGateway:
    """Contrato del adaptador. Producción y fakes lo implementan."""

    async def crear_o_reutilizar_intencion(
        self, venta_id: str, monto_centavos: int, moneda: str,
        idempotency_key: str, referencia_existente: Optional[str] = None,
        empresa_id: Optional[str] = None, metadata: Optional[dict] = None,
    ) -> IntencionPago:
        raise NotImplementedError

    async def consultar_intencion(self, payment_intent_id: str) -> IntencionPago:
        raise NotImplementedError

    async def cancelar_intencion(self, payment_intent_id: str) -> IntencionPago:
        raise NotImplementedError

    async def crear_setup_intent(
        self, cliente_id: str, idempotency_key: Optional[str] = None, empresa_id: Optional[str] = None,
    ) -> SetupIntentInfo:
        raise NotImplementedError

    async def consultar_setup_intent(self, setup_intent_id: str) -> SetupIntentInfo:
        raise NotImplementedError

    async def confirmar_setup_intent(
        self, setup_intent_id: str, payment_method_id: Optional[str] = None,
    ) -> SetupIntentInfo:
        raise NotImplementedError

    async def crear_pago_conectado(
        self, recurso_id: str, monto_centavos: int, moneda: str,
        idempotency_key: str, metodo_preparado_id: Optional[str] = None,
        off_session: bool = False, simular_requiere_accion: bool = False,
        customer_id: Optional[str] = None, payment_method_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> IntencionPago:
        raise NotImplementedError

    async def confirmar_intencion(self, payment_intent_id: str) -> IntencionPago:
        raise NotImplementedError

    async def crear_reembolso(
        self, payment_intent_id: str, centavos_usd: int, idempotency_key: Optional[str] = None,
    ) -> ReembolsoInfo:
        raise NotImplementedError

    async def consultar_reembolso(self, referencia: str) -> ReembolsoInfo:
        raise NotImplementedError

    async def buscar_reembolso(self, payment_intent_id: str, clave: str) -> Optional[ReembolsoInfo]:
        raise NotImplementedError

    async def consultar_payment_method(self, payment_method_id: str) -> dict:
        raise NotImplementedError


class FakeStripeGateway(StripeGateway):
    """Doble de pruebas: sin red, determinista, conmutado por tests."""

    def __init__(self):
        self.intenciones: dict[str, IntencionPago] = {}
        self.intenciones_creadas: dict[str, IntencionPago] = {}
        self.por_venta: dict[str, str] = {}
        self.setup_intents: dict[str, SetupIntentInfo] = {}
        self.reembolsos: dict[str, ReembolsoInfo] = {}
        self.claves_reembolso: dict[str, str] = {}
        self.payment_methods: dict[str, dict] = {}
        self.simular_requiere_accion: bool = False
        self.simular_sin_customer: bool = False
        self.simular_sin_payment_method: bool = False
        self.simular_customer_ajeno: bool = False
        self.customer_ajeno_personalizado: Optional[str] = None
        self.simular_metodo_no_adjunto: bool = False
        self.simular_metodo_invalido: bool = False
        self.simular_metodo_otro_customer: bool = False
        self.metodo_otro_customer_id: Optional[str] = None
        self.fallos_temporales_restantes: int = 0

    async def crear_o_reutilizar_intencion(
        self, venta_id, monto_centavos, moneda, idempotency_key, referencia_existente=None,
        empresa_id=None, metadata=None,
    ) -> IntencionPago:
        if self.fallos_temporales_restantes > 0:
            self.fallos_temporales_restantes -= 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_FALLO_TEMPORAL", "mensaje": "Fallo temporal simulado en Stripe"},
            )
        # FAILED reutiliza el PI vigente; CANCELED exige uno nuevo porque un
        # PI cancelado ya no puede procesar un pago (contrato Stripe).
        if referencia_existente and referencia_existente in self.intenciones:
            vigente = self.intenciones[referencia_existente]
            if vigente.estado != "CANCELED":
                return vigente
        elif venta_id in self.por_venta:
            pi_id = self.por_venta[venta_id]
            vigente = self.intenciones.get(pi_id)
            if vigente is not None and vigente.estado != "CANCELED":
                return vigente
        pi_id = f"pi_test_{secrets.token_hex(4)}"
        meta = dict(metadata or {})
        if venta_id and "venta_id" not in meta:
            meta["venta_id"] = str(venta_id)
        if empresa_id and "empresa_id" not in meta:
            meta["empresa_id"] = str(empresa_id)
        inten = IntencionPago(
            id=pi_id, venta_id=venta_id, monto_centavos=monto_centavos,
            moneda=moneda, estado="REQUIRES_PAYMENT",
            client_secret=f"{pi_id}_secret_test",
            empresa_id=str(empresa_id) if empresa_id else None,
            metadata=meta,
        )
        self.intenciones[pi_id] = inten
        self.intenciones_creadas[pi_id] = inten
        self.por_venta[venta_id] = pi_id
        return inten

    async def consultar_intencion(self, payment_intent_id: str) -> IntencionPago:
        if self.fallos_temporales_restantes > 0:
            self.fallos_temporales_restantes -= 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_FALLO_TEMPORAL", "mensaje": "Fallo temporal simulado en Stripe"},
            )
        if payment_intent_id not in self.intenciones:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intención no encontrada")
        inten = self.intenciones[payment_intent_id]
        if inten.estado == 'SUCCEEDED':
            inten.capturado_centavos = inten.monto_centavos
            inten.reembolsado_centavos = sum(r.centavos_usd for r in self.reembolsos.values()
                if r.payment_intent_id == payment_intent_id and r.estado == 'succeeded')
        if inten.metadata is None and payment_intent_id in self.intenciones_creadas:
            inten.metadata = dict(self.intenciones_creadas[payment_intent_id].metadata or {})
        return inten

    async def cancelar_intencion(self, payment_intent_id: str) -> IntencionPago:
        if self.fallos_temporales_restantes > 0:
            self.fallos_temporales_restantes -= 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_FALLO_TEMPORAL", "mensaje": "Fallo temporal simulado en Stripe"},
            )
        if payment_intent_id not in self.intenciones:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intención no encontrada")
        inten = self.intenciones[payment_intent_id]
        if inten.estado in ("SUCCEEDED", "CAPTURADO"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"codigo": "STRIPE_ESTADO_INVALIDO", "mensaje": "No se puede cancelar un PaymentIntent ya capturado/succeeded en Stripe"},
            )
        inten.estado = "CANCELED"
        return inten

    async def crear_setup_intent(
        self, cliente_id: str, idempotency_key: Optional[str] = None, empresa_id: Optional[str] = None,
    ) -> SetupIntentInfo:
        if self.fallos_temporales_restantes > 0:
            self.fallos_temporales_restantes -= 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_FALLO_TEMPORAL", "mensaje": "Fallo temporal simulado en Stripe"},
            )
        seti_id = f"seti_test_{secrets.token_hex(4)}"
        if self.simular_sin_customer:
            cus_id = None
        elif self.simular_customer_ajeno:
            cus_id = self.customer_ajeno_personalizado or f"cus_otro_valido_{secrets.token_hex(4)}"
        else:
            cus_id = f"cus_test_{secrets.token_hex(4)}"

        info = SetupIntentInfo(
            id=seti_id,
            cliente_id=cliente_id,
            estado="requires_payment_method",
            client_secret=f"{seti_id}_secret_test",
            customer=cus_id,
            payment_method=None,
            empresa_id=empresa_id,
        )
        self.setup_intents[seti_id] = info
        return info

    async def consultar_setup_intent(self, setup_intent_id: str) -> SetupIntentInfo:
        if self.fallos_temporales_restantes > 0:
            self.fallos_temporales_restantes -= 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_FALLO_TEMPORAL", "mensaje": "Fallo temporal simulado en Stripe"},
            )
        if setup_intent_id not in self.setup_intents:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SetupIntent no encontrado")
        return self.setup_intents[setup_intent_id]

    async def confirmar_setup_intent(
        self, setup_intent_id: str, payment_method_id: Optional[str] = None,
    ) -> SetupIntentInfo:
        if self.fallos_temporales_restantes > 0:
            self.fallos_temporales_restantes -= 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_FALLO_TEMPORAL", "mensaje": "Fallo temporal simulado en Stripe"},
            )
        if setup_intent_id not in self.setup_intents:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SetupIntent no encontrado")
        info = self.setup_intents[setup_intent_id]
        info.estado = "succeeded"

        if self.simular_sin_payment_method:
            info.payment_method = None
        elif self.simular_metodo_no_adjunto:
            info.payment_method = "pm_no_adjunto"
        elif self.simular_metodo_invalido:
            info.payment_method = "metodo_sin_prefijo"
        else:
            info.payment_method = payment_method_id or f"pm_card_test_{secrets.token_hex(4)}"

        if self.simular_sin_customer:
            info.customer = None
        elif self.simular_customer_ajeno:
            info.customer = self.customer_ajeno_personalizado or f"cus_otro_valido_{secrets.token_hex(4)}"
        elif not info.customer:
            info.customer = f"cus_test_{secrets.token_hex(4)}"

        if info.payment_method:
            if self.simular_metodo_no_adjunto or info.payment_method == "pm_no_adjunto":
                pm_cus = None
            elif self.simular_metodo_otro_customer:
                pm_cus = self.metodo_otro_customer_id or f"cus_otro_propietario_{secrets.token_hex(4)}"
            else:
                pm_cus = info.customer
            self.payment_methods[info.payment_method] = {"id": info.payment_method, "customer": pm_cus}
        return info

    async def consultar_payment_method(self, payment_method_id: str) -> dict:
        if self.fallos_temporales_restantes > 0:
            self.fallos_temporales_restantes -= 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_FALLO_TEMPORAL", "mensaje": "Fallo temporal simulado en Stripe"},
            )
        if payment_method_id in self.payment_methods:
            return self.payment_methods[payment_method_id]
        if payment_method_id == "pm_no_adjunto" or self.simular_metodo_no_adjunto:
            return {"id": payment_method_id, "customer": None}
        if self.simular_metodo_otro_customer:
            return {
                "id": payment_method_id,
                "customer": self.metodo_otro_customer_id or f"cus_otro_propietario_{secrets.token_hex(4)}",
            }
        for s in self.setup_intents.values():
            if s.payment_method == payment_method_id:
                return {"id": payment_method_id, "customer": s.customer}
        return {"id": payment_method_id, "customer": "cus_default_owner"}

    async def crear_pago_conectado(
        self, recurso_id: str, monto_centavos: int, moneda: str,
        idempotency_key: str, metodo_preparado_id: Optional[str] = None,
        off_session: bool = False, simular_requiere_accion: bool = False,
        customer_id: Optional[str] = None, payment_method_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> IntencionPago:
        if self.fallos_temporales_restantes > 0:
            self.fallos_temporales_restantes -= 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"codigo": "STRIPE_FALLO_TEMPORAL", "mensaje": "Fallo temporal simulado en Stripe"},
            )
        pi_id = f"pi_test_{secrets.token_hex(4)}"
        requiere = simular_requiere_accion or self.simular_requiere_accion
        if requiere:
            estado = "REQUIRES_ACTION"
        elif off_session:
            estado = "SUCCEEDED"
        else:
            estado = "REQUIRES_PAYMENT"

        meta = {"recurso_id": str(recurso_id), **(metadata or {})}
        inten = IntencionPago(
            id=pi_id,
            venta_id=recurso_id,
            monto_centavos=monto_centavos,
            moneda=moneda,
            estado=estado,
            client_secret=f"{pi_id}_secret_test",
            metadata=meta,
        )
        self.intenciones[pi_id] = inten
        self.por_venta[recurso_id] = pi_id
        return inten

    async def confirmar_intencion(self, payment_intent_id: str) -> IntencionPago:
        if payment_intent_id not in self.intenciones:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intención no encontrada")
        inten = self.intenciones[payment_intent_id]
        if self.simular_requiere_accion:
            inten.estado = "REQUIRES_ACTION"
        else:
            inten.estado = "SUCCEEDED"
        return inten

    async def crear_reembolso(self, payment_intent_id, centavos_usd, idempotency_key=None):
        if not idempotency_key:
            raise ValueError("El reembolso requiere clave durable")
        previo = await self.buscar_reembolso(payment_intent_id, idempotency_key)
        if previo:
            if previo.centavos_usd != centavos_usd:
                raise ValueError("Clave reutilizada con otro importe")
            return previo
        pi = await self.consultar_intencion(payment_intent_id)
        if pi.estado != 'SUCCEEDED' or centavos_usd <= 0 or centavos_usd > pi.capturado_centavos - pi.reembolsado_centavos:
            raise ValueError("Importe no reembolsable")
        re_id = f"re_test_{secrets.token_hex(4)}"
        resultado = ReembolsoInfo(re_id, payment_intent_id, centavos_usd, 'succeeded', pi.moneda)
        self.reembolsos[re_id] = resultado
        self.claves_reembolso[idempotency_key] = re_id
        return resultado

    async def consultar_reembolso(self, referencia):
        return self.reembolsos[referencia]

    async def buscar_reembolso(self, payment_intent_id, clave):
        r = self.reembolsos.get(self.claves_reembolso.get(clave))
        return r if r and r.payment_intent_id == payment_intent_id else None

    # Helpers de prueba: transiciones controladas sin red.
    def marcar(self, pi_id: str, estado: str) -> None:
        if pi_id in self.intenciones:
            self.intenciones[pi_id].estado = estado


def verificar_firma_stripe(cuerpo_crudo: bytes, encabezado_firma: Optional[str], secreto: str) -> dict:
    """Verifica Stripe-Signature (t=...,v1=...) contra el cuerpo crudo.

    Lanza FirmaStripeInvalida si falta, expiró (>5 min) o no coincide.
    Retorna {'timestamp': int} para auditoría (sin datos sensibles).
    """
    if not encabezado_firma or not secreto:
        raise FirmaStripeInvalida("Falta firma o secreto de webhook")
    partes: dict[str, str] = {}
    for trozo in (encabezado_firma or "").split(","):
        if "=" in trozo:
            k, v = trozo.strip().split("=", 1)
            partes[k.strip()] = v.strip()
    t = partes.get("t", "")
    v1 = partes.get("v1", "")
    if not t or not v1:
        raise FirmaStripeInvalida("Formato de firma inválido")
    try:
        ts = int(t)
    except ValueError:
        raise FirmaStripeInvalida("Timestamp de firma inválido")
    if abs(time.time() - ts) > 300:
        raise FirmaStripeInvalida("Firma vencida")
    esperado = hmac.new(
        secreto.encode("utf-8"), f"{t}.".encode("utf-8") + cuerpo_crudo, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(esperado, v1):
        raise FirmaStripeInvalida("Firma del webhook no coincide")
    return {"timestamp": ts}


def firmar_prueba(cuerpo: bytes, secreto: str, ts: Optional[int] = None) -> str:
    """Solo pruebas: genera un encabezado Stripe-Signature válido."""
    marca = ts if ts is not None else int(time.time())
    firma = hmac.new(
        secreto.encode("utf-8"), f"{marca}.".encode("utf-8") + cuerpo, hashlib.sha256
    ).hexdigest()
    return f"t={marca},v1={firma}"


# Instancia conmutable: tests la reemplazan; producción usa el adaptador real.
_gateway_actual: Optional[StripeGateway] = None


def fijar_gateway(gateway: Optional[StripeGateway]) -> None:
    global _gateway_actual
    _gateway_actual = gateway


def es_clave_test_mode(clave: str) -> bool:
    """True solo para claves de Test Mode (sk_test_/rk_test_)."""
    c = (clave or "").strip()
    return c.startswith("sk_test_") or c.startswith("rk_test_")


def es_clave_live(clave: str) -> bool:
    c = (clave or "").strip()
    return c.startswith("sk_live_") or c.startswith("rk_live_")


def exigir_test_mode() -> None:
    """Rechaza claves live o fuera de Test Mode sin exponer la clave.

    Nunca imprime la clave ni su prefijo completo en errores o logs.
    """
    clave = settings.STRIPE_SECRET_KEY or ""
    if es_clave_live(clave):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "codigo": "STRIPE_MODO_NO_PERMITIDO",
                "mensaje": "Pasarela solo en Test Mode; clave live no permitida",
            },
        )
    if not es_clave_test_mode(clave):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "codigo": "STRIPE_MODO_NO_PERMITIDO",
                "mensaje": "Pasarela solo en Test Mode; configure una clave de prueba",
            },
        )


def obtener_gateway() -> StripeGateway:
    """503 tipado si Stripe está deshabilitado o sin claves (módulos sanos)."""
    if _gateway_actual is not None:
        return _gateway_actual
    if not settings.STRIPE_ENABLED or not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "codigo": "STRIPE_DESHABILITADO",
                "mensaje": "Pasarela en modo prueba no configurada. "
                "Configure STRIPE_SECRET_KEY y STRIPE_ENABLED=true en backend/.env",
            },
        )
    exigir_test_mode()
    return RealStripeGateway()


class RealStripeGateway(StripeGateway):
    """Adaptador productivo mínimo vía httpx (solo con claves del usuario)."""

    async def _obtener_o_crear_customer(
        self, cli, cliente_id: str, empresa_id: Optional[str] = None
    ) -> str:
        """Crea o recupera de forma idempotente un Stripe Customer para (cliente_id, empresa_id)."""
        filtro = f"metadata['cliente_id']:'{cliente_id}'"
        if empresa_id:
            filtro += f" AND metadata['empresa_id']:'{empresa_id}'"
        try:
            r_search = await cli.get(
                "https://api.stripe.com/v1/customers/search",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                params={"query": filtro, "limit": 1},
            )
            if r_search.status_code == 200:
                data_search = r_search.json()
                if data_search.get("data") and len(data_search["data"]) > 0:
                    return data_search["data"][0]["id"]
        except Exception:
            pass

        # Idempotencia determinista para creación de cliente
        idem_key = hashlib.sha256(f"{empresa_id or 'default'}_{cliente_id}".encode("utf-8")).hexdigest()[:32]
        post_data = {"metadata[cliente_id]": cliente_id}
        if empresa_id:
            post_data["metadata[empresa_id]"] = empresa_id

        r_create = await cli.post(
            "https://api.stripe.com/v1/customers",
            auth=(settings.STRIPE_SECRET_KEY, ""),
            headers={"Idempotency-Key": f"cus_idem_{idem_key}"},
            data=post_data,
        )
        if r_create.status_code < 400:
            return r_create.json()["id"]
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"codigo": "STRIPE_CUSTOMER_FALLIDO", "mensaje": "No se pudo crear o recuperar Customer en Stripe"},
        )

    async def crear_o_reutilizar_intencion(
        self, venta_id, monto_centavos, moneda, idempotency_key, referencia_existente=None,
        empresa_id=None, metadata=None,
    ) -> IntencionPago:
        import httpx

        if referencia_existente:
            return await self.consultar_intencion(referencia_existente)
        post_data = {
            "amount": str(monto_centavos),
            "currency": moneda,
            "metadata[venta_id]": venta_id,
        }
        if empresa_id:
            post_data["metadata[empresa_id]"] = str(empresa_id)
        if metadata:
            for k, v in metadata.items():
                post_data[f"metadata[{k}]"] = str(v)
        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.post(
                "https://api.stripe.com/v1/payment_intents",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                headers={"Idempotency-Key": idempotency_key or secrets.token_hex(16)},
                data=post_data,
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"codigo": "STRIPE_RECHAZO", "mensaje": "La pasarela rechazó la intención"},
            )
        data: Any = r.json()
        meta = data.get("metadata", {})
        return IntencionPago(
            id=data["id"], venta_id=venta_id, monto_centavos=int(data["amount"]),
            moneda=data.get("currency", moneda), estado="REQUIRES_PAYMENT",
            client_secret=data.get("client_secret"),
            empresa_id=str(meta.get("empresa_id", "")) if meta.get("empresa_id") else (str(empresa_id) if empresa_id else None),
            metadata=meta,
        )

    async def consultar_intencion(self, payment_intent_id: str) -> IntencionPago:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.get(
                f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                params={"expand[]": "latest_charge"},
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"codigo": "STRIPE_CONSULTA_FALLIDA", "mensaje": "No se pudo consultar la intención"},
            )
        data: Any = r.json()
        mapa = {
            "requires_payment_method": "REQUIRES_PAYMENT",
            "requires_action": "REQUIRES_ACTION",
            "succeeded": "SUCCEEDED",
            "canceled": "CANCELED",
        }
        estado = mapa.get(str(data.get("status", "")), "REQUIRES_PAYMENT")
        meta = data.get("metadata", {})
        return IntencionPago(
            id=data["id"], venta_id=str(meta.get("venta_id", "") or meta.get("recurso_id", "")),
            monto_centavos=int(data.get("amount", 0)), moneda=str(data.get("currency", "usd")),
            estado=estado, client_secret=data.get("client_secret"),
            capturado_centavos=data.get("amount_received"),
            reembolsado_centavos=(data["latest_charge"].get("amount_refunded")
                if isinstance(data.get("latest_charge"), dict) else None),
            empresa_id=str(meta.get("empresa_id", "")) if meta.get("empresa_id") else None,
            cliente_id=str(meta.get("cliente_id", "")) if meta.get("cliente_id") else None,
            metadata=meta,
        )

    async def cancelar_intencion(self, payment_intent_id: str) -> IntencionPago:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.post(
                f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}/cancel",
                auth=(settings.STRIPE_SECRET_KEY, ""),
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"codigo": "STRIPE_CANCELACION_FALLIDA", "mensaje": "No se pudo cancelar la intención en Stripe"},
            )
        data: Any = r.json()
        meta = data.get("metadata", {})
        return IntencionPago(
            id=data["id"],
            venta_id=str(meta.get("venta_id", "") or meta.get("recurso_id", "")),
            monto_centavos=int(data.get("amount", 0)),
            moneda=str(data.get("currency", "usd")),
            estado="CANCELED",
            client_secret=data.get("client_secret"),
            empresa_id=str(meta.get("empresa_id", "")) if meta.get("empresa_id") else None,
            cliente_id=str(meta.get("cliente_id", "")) if meta.get("cliente_id") else None,
            metadata=meta,
        )

    async def crear_setup_intent(
        self, cliente_id: str, idempotency_key: Optional[str] = None, empresa_id: Optional[str] = None,
    ) -> SetupIntentInfo:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as cli:
            customer_id = await self._obtener_o_crear_customer(cli, cliente_id, empresa_id)
            post_data = {
                "usage": "off_session",
                "customer": customer_id,
                "metadata[cliente_id]": cliente_id,
            }
            if empresa_id:
                post_data["metadata[empresa_id]"] = empresa_id
            r = await cli.post(
                "https://api.stripe.com/v1/setup_intents",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                headers={"Idempotency-Key": idempotency_key or secrets.token_hex(16)},
                data=post_data,
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"codigo": "STRIPE_RECHAZO", "mensaje": "La pasarela rechazó el setup intent"},
            )
        data = r.json()
        return SetupIntentInfo(
            id=data["id"],
            cliente_id=cliente_id,
            estado=data.get("status", "requires_payment_method"),
            client_secret=data.get("client_secret"),
            customer=data.get("customer") or customer_id,
            payment_method=data.get("payment_method"),
            empresa_id=empresa_id,
        )

    async def consultar_setup_intent(self, setup_intent_id: str) -> SetupIntentInfo:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.get(
                f"https://api.stripe.com/v1/setup_intents/{setup_intent_id}",
                auth=(settings.STRIPE_SECRET_KEY, ""),
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"codigo": "STRIPE_CONSULTA_FALLIDA", "mensaje": "No se pudo consultar el setup intent"},
            )
        data = r.json()
        meta = data.get("metadata", {})
        return SetupIntentInfo(
            id=data["id"],
            cliente_id=str(meta.get("cliente_id", "")),
            estado=data.get("status", "requires_payment_method"),
            client_secret=data.get("client_secret"),
            customer=data.get("customer"),
            payment_method=data.get("payment_method"),
            empresa_id=str(meta.get("empresa_id", "")) if meta.get("empresa_id") else None,
        )

    async def confirmar_setup_intent(
        self, setup_intent_id: str, payment_method_id: Optional[str] = None,
    ) -> SetupIntentInfo:
        import httpx

        post_data = {}
        if payment_method_id:
            post_data["payment_method"] = payment_method_id
        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.post(
                f"https://api.stripe.com/v1/setup_intents/{setup_intent_id}/confirm",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                data=post_data,
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"codigo": "STRIPE_CONFIRMACION_FALLIDA", "mensaje": "No se pudo confirmar el setup intent"},
            )
        data = r.json()
        meta = data.get("metadata", {})
        return SetupIntentInfo(
            id=data["id"],
            cliente_id=str(meta.get("cliente_id", "")),
            estado=data.get("status", "requires_payment_method"),
            client_secret=data.get("client_secret"),
            customer=data.get("customer"),
            payment_method=data.get("payment_method"),
            empresa_id=str(meta.get("empresa_id", "")) if meta.get("empresa_id") else None,
        )

    async def crear_pago_conectado(
        self, recurso_id: str, monto_centavos: int, moneda: str,
        idempotency_key: str, metodo_preparado_id: Optional[str] = None,
        off_session: bool = False, simular_requiere_accion: bool = False,
        customer_id: Optional[str] = None, payment_method_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> IntencionPago:
        import httpx

        meta = {"recurso_id": str(recurso_id), **(metadata or {})}
        post_data = {
            "amount": str(monto_centavos),
            "currency": moneda,
        }
        post_data.update({f"metadata[{k}]": str(v) for k, v in meta.items() if v is not None})
        if off_session:
            post_data["off_session"] = "true"
            post_data["confirm"] = "true"
            if customer_id:
                post_data["customer"] = customer_id
            if payment_method_id:
                post_data["payment_method"] = payment_method_id
        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.post(
                "https://api.stripe.com/v1/payment_intents",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                headers={"Idempotency-Key": idempotency_key or secrets.token_hex(16)},
                data=post_data,
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"codigo": "STRIPE_RECHAZO", "mensaje": "La pasarela rechazó el pago conectado"},
            )
        data = r.json()
        st = data.get("status", "")
        estado = "SUCCEEDED" if st == "succeeded" else ("REQUIRES_ACTION" if st == "requires_action" else "REQUIRES_PAYMENT")
        meta_resp = data.get("metadata") or {}
        return IntencionPago(
            id=data["id"], venta_id=recurso_id, monto_centavos=int(data["amount"]),
            moneda=data.get("currency", moneda), estado=estado, client_secret=data.get("client_secret"),
            empresa_id=str(meta_resp.get("empresa_id")) if meta_resp.get("empresa_id") else None,
            metadata=meta_resp,
        )

    async def confirmar_intencion(self, payment_intent_id: str) -> IntencionPago:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.post(
                f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}/confirm",
                auth=(settings.STRIPE_SECRET_KEY, ""),
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"codigo": "STRIPE_CONFIRMACION_FALLIDA", "mensaje": "No se pudo confirmar la intención"},
            )
        data = r.json()
        st = str(data.get("status", "")).lower()
        if st == "succeeded":
            estado = "SUCCEEDED"
        elif st == "requires_action":
            estado = "REQUIRES_ACTION"
        elif st == "requires_payment_method":
            estado = "REQUIRES_PAYMENT"
        elif st == "canceled":
            estado = "CANCELED"
        else:
            estado = st.upper()
        return IntencionPago(
            id=data["id"], venta_id=str(data.get("metadata", {}).get("recurso_id", "")),
            monto_centavos=int(data.get("amount", 0)), moneda=str(data.get("currency", "usd")),
            estado=estado, client_secret=data.get("client_secret"),
        )

    @staticmethod
    def _reembolso(data):
        # Campos ausentes nunca se sustituyen por valores de la solicitud.
        return ReembolsoInfo(
            id=data.get("id", ""), payment_intent_id=data.get("payment_intent", ""),
            centavos_usd=data.get("amount"), estado=data.get("status", "unknown"),
            moneda=data.get("currency"),
        )

    async def crear_reembolso(self, payment_intent_id, centavos_usd, idempotency_key=None):
        import httpx
        if not idempotency_key or not isinstance(centavos_usd, int) or centavos_usd <= 0:
            raise ValueError("El reembolso requiere importe entero positivo y clave durable")
        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.post("https://api.stripe.com/v1/refunds",
                auth=(settings.STRIPE_SECRET_KEY, ""),
                headers={"Idempotency-Key": idempotency_key},
                data={"payment_intent": payment_intent_id, "amount": str(centavos_usd),
                      "metadata[ejecucion_id]": idempotency_key})
        if r.status_code >= 400:
            raise HTTPException(502, detail={"codigo": "STRIPE_REEMBOLSO_FALLIDO",
                                           "mensaje": "Resultado no confirmado; consulte o concilie la operacion"})
        return self._reembolso(r.json())

    async def consultar_reembolso(self, referencia):
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.get(f"https://api.stripe.com/v1/refunds/{referencia}",
                              auth=(settings.STRIPE_SECRET_KEY, ""))
        if r.status_code != 200:
            raise HTTPException(502, detail="No se pudo verificar el reembolso")
        return self._reembolso(r.json())

    async def buscar_reembolso(self, payment_intent_id, clave):
        import httpx
        encontrados = []
        params = {"payment_intent": payment_intent_id, "limit": 100}
        async with httpx.AsyncClient(timeout=15.0) as cli:
            while True:
                r = await cli.get("https://api.stripe.com/v1/refunds",
                                  auth=(settings.STRIPE_SECRET_KEY, ""), params=params)
                if r.status_code != 200:
                    raise HTTPException(502, detail="No se pudo verificar el historial de reembolsos")
                datos = r.json()
                for registro in datos.get("data", []):
                    if (registro.get("metadata") or {}).get("ejecucion_id") == clave:
                        encontrados.append(self._reembolso(registro))
                if not datos.get("has_more"):
                    break
                if not datos.get("data"):
                    raise HTTPException(502, detail="Historial de reembolsos incompleto")
                params["starting_after"] = datos["data"][-1]["id"]
        if len(encontrados) > 1:
            raise HTTPException(409, detail="CONCILIACION_REQUERIDA: varias referencias para una ejecucion")
        return encontrados[0] if encontrados else None

    async def consultar_payment_method(self, payment_method_id: str) -> dict:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as cli:
            r = await cli.get(
                f"https://api.stripe.com/v1/payment_methods/{payment_method_id}",
                auth=(settings.STRIPE_SECRET_KEY, ""),
            )
        if r.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"codigo": "STRIPE_PM_CONSULTA_FALLIDA", "mensaje": "No se pudo consultar el PaymentMethod en Stripe"},
            )
        return r.json()


_StripeReal = RealStripeGateway
