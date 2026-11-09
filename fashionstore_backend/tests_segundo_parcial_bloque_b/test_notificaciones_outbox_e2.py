"""Pruebas del sistema de Notificaciones, Dispositivos y Outbox (E2 Avisos Push).

Verifica:
- Registro y revocación de dispositivos móviles y PWA.
- Emisión de notificaciones y evento outbox en la misma transacción sin revertir si el envío push falla.
- Consulta de bandeja de notificaciones propia del usuario y marcado de lectura.
- Despachador de notificaciones push real con adaptadores FCM y Web Push.
- Validación honesta: sin dispositivos registrados el estado es SIN_DESTINOS (nunca ENVIADO fraudulento).
- Revocación automática de tokens inválidos reportados por el proveedor push.
- Manejo de reintentos con SKIP LOCKED ante fallos temporales (TIMEOUT).
- Ejecución recurrente mediante worker independiente.
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select

from backend.app.core.modules.identidad_empresas.models_notificaciones import (
    DispositivoAutorizado,
    EventoOutbox,
    Notificacion,
)
from backend.app.core.modules.identidad_empresas.services.notificacion_service import (
    BasePushAdapter,
    MockPushAdapter,
    NotificacionService,
    PushResult,
    RegistroDispositivoDTO,
    ejecutar_ciclo_worker_outbox,
)


@pytest.mark.asyncio
async def test_notificaciones_registro_y_revocacion_dispositivo(http, escenario, fabrica_sesiones):
    """Verifica registro de token de dispositivo PWA y Flutter, y su revocación."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    # 1. Registrar dispositivo
    resp = await http.cliente.post(
        "/api/v1/notificaciones/dispositivos",
        json={
            "dispositivo_id": str(disp_id),
            "canal": "FLUTTER",
            "push_token": "fcm_test_token_123456",
            "sucursal_id": str(escenario.sucursal_a_id),
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dispositivo_id"] == str(disp_id)
    assert data["canal"] == "FLUTTER"
    assert data["estado"] == "ACTIVO"

    # Verificar en base de datos
    async with fabrica_sesiones() as db:
        stmt = select(DispositivoAutorizado).where(
            DispositivoAutorizado.empresa_id == escenario.empresa_a_id,
            DispositivoAutorizado.dispositivo_id == disp_id,
        )
        disp_bd = (await db.execute(stmt)).scalars().first()
        assert disp_bd is not None
        assert disp_bd.estado == "ACTIVO"
        assert disp_bd.push_destino_hash is not None

    # 2. Revocar dispositivo
    resp_del = await http.cliente.delete(f"/api/v1/notificaciones/dispositivos/{disp_id}")
    assert resp_del.status_code == 204, resp_del.text

    async with fabrica_sesiones() as db:
        disp_bd2 = (await db.execute(stmt)).scalars().first()
        assert disp_bd2.estado == "REVOCADO"
        assert disp_bd2.revocado_en is not None


@pytest.mark.asyncio
async def test_notificaciones_emision_outbox_y_bandeja_lectura(http, escenario, fabrica_sesiones):
    """Verifica emisión de evento outbox, persistencia en bandeja y marcado de lectura."""
    http.usar(escenario.usuario_a)

    rec_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        srv = NotificacionService(db)
        notif = await srv.emitir_notificacion(
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            tipo="COMPRA_CONFIRMADA",
            titulo="¡Compra confirmada!",
            cuerpo="Tu pedido ha sido procesado y el stock está comprometido.",
            recurso_tipo="PEDIDO",
            recurso_id=rec_id,
            payload={"pedido_id": str(rec_id), "total_bob": "100.00"},
        )
        notif_id = notif.id
        await db.commit()

    # Verificar evento outbox
    async with fabrica_sesiones() as db:
        stmt_out = select(EventoOutbox).where(EventoOutbox.recurso_id == rec_id)
        ev = (await db.execute(stmt_out)).scalars().first()
        assert ev is not None
        assert ev.transicion == "COMPRA_CONFIRMADA"
        assert ev.estado == "PENDIENTE"

    # 2. Consultar bandeja vía API
    resp = await http.cliente.get("/api/v1/notificaciones/bandeja")
    assert resp.status_code == 200, resp.text
    bandeja = resp.json()
    assert len(bandeja) >= 1
    item = next(b for b in bandeja if b["id"] == str(notif_id))
    assert item["titulo"] == "¡Compra confirmada!"
    assert item["tipo"] == "COMPRA_CONFIRMADA"
    assert item["leida_en"] is None

    # 3. Marcar como leída
    resp_leer = await http.cliente.patch(f"/api/v1/notificaciones/bandeja/{notif_id}/leer")
    assert resp_leer.status_code == 200, resp_leer.text
    assert resp_leer.json()["leida_en"] is not None


@pytest.mark.asyncio
async def test_notificaciones_sin_dispositivos_es_honesto(http, escenario, fabrica_sesiones):
    """P0 Auditoría 23: Sin dispositivos/tokens registrados, el evento queda SIN_DESTINOS y nunca ENVIADO."""
    http.usar(escenario.usuario_a)

    rec_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        # Asegurar que no hay dispositivos activos para usuario_a en este test
        from sqlalchemy import delete
        await db.execute(
            delete(DispositivoAutorizado).where(
                DispositivoAutorizado.empresa_id == escenario.empresa_a_id,
                DispositivoAutorizado.usuario_id == escenario.usuario_a.id,
            )
        )
        srv = NotificacionService(db)
        await srv.emitir_notificacion(
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            tipo="AVISO_PRUEBA",
            titulo="Aviso",
            cuerpo="Prueba sin destinatario push",
            recurso_tipo="TEST",
            recurso_id=rec_id,
        )
        await db.commit()

    # Procesar outbox
    async with fabrica_sesiones() as db:
        srv = NotificacionService(db)
        res = await srv.procesar_outbox(empresa_id=escenario.empresa_a_id, limite=10)
        await db.commit()
        assert res["sin_destinos"] >= 1
        assert res["enviados"] == 0

    # Verificar que el evento NO fue marcado fraudulentamente como ENVIADO
    async with fabrica_sesiones() as db:
        stmt_out = select(EventoOutbox).where(EventoOutbox.recurso_id == rec_id)
        ev = (await db.execute(stmt_out)).scalars().first()
        assert ev.estado == "SIN_DESTINOS"
        assert ev.entregado_en is None


@pytest.mark.asyncio
async def test_notificaciones_despacho_real_con_adaptador_y_worker(http, escenario, fabrica_sesiones):
    """P0 Auditoría 23: Despacho a dispositivo activo con proveedor simulado y worker recurrente."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    # 1. Registrar dispositivo con token
    resp = await http.cliente.post(
        "/api/v1/notificaciones/dispositivos",
        json={
            "dispositivo_id": str(disp_id),
            "canal": "FLUTTER",
            "push_token": "fcm_token_valido_e2",
            "sucursal_id": str(escenario.sucursal_a_id),
        },
    )
    assert resp.status_code == 200, resp.text

    rec_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        srv = NotificacionService(db)
        await srv.emitir_notificacion(
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            tipo="COMPRA_EXITOSA",
            titulo="Compra exitosa",
            cuerpo="Tus prendas fueron reservadas.",
            recurso_tipo="PEDIDO",
            recurso_id=rec_id,
            dispositivo_id=disp_id,
        )
        await db.commit()

    # 2. Ejecutar pasada del worker outbox con adaptador que acepta
    mock_fcm = MockPushAdapter("ACEPTADO")
    res = await ejecutar_ciclo_worker_outbox(
        fabrica_sesiones,
        empresa_id=escenario.empresa_a_id,
        limite=50,
        adapter_fcm=mock_fcm,
    )
    assert res["enviados"] >= 1

    # Verificar que el evento ahora sí está ENVIADO con entrega comprobada
    async with fabrica_sesiones() as db:
        stmt_out = select(EventoOutbox).where(EventoOutbox.recurso_id == rec_id)
        ev = (await db.execute(stmt_out)).scalars().first()
        assert ev.estado == "ENVIADO"
        assert ev.entregado_en is not None


@pytest.mark.asyncio
async def test_notificaciones_token_invalido_revoca_dispositivo(http, escenario, fabrica_sesiones):
    """P0 Auditoría 23: Si el proveedor responde TOKEN_INVALIDO, el dispositivo se revoca automáticamente."""
    http.usar(escenario.usuario_a)

    disp_id = uuid.uuid4()
    resp = await http.cliente.post(
        "/api/v1/notificaciones/dispositivos",
        json={
            "dispositivo_id": str(disp_id),
            "canal": "FLUTTER",
            "push_token": "fcm_token_expirado",
        },
    )
    assert resp.status_code == 200

    rec_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        srv = NotificacionService(db)
        await srv.emitir_notificacion(
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            tipo="AVISO",
            titulo="Aviso",
            cuerpo="Prueba token expirado",
            recurso_tipo="TEST",
            recurso_id=rec_id,
            dispositivo_id=disp_id,
        )
        await db.commit()

    # Procesar con adaptador que simula TOKEN_INVALIDO
    async with fabrica_sesiones() as db:
        srv = NotificacionService(db, adapter_fcm=MockPushAdapter("TOKEN_INVALIDO"))
        res = await srv.procesar_outbox(empresa_id=escenario.empresa_a_id, limite=10)
        await db.commit()
        assert res["fallidos"] >= 1

    # Verificar que el dispositivo quedó REVOCADO
    async with fabrica_sesiones() as db:
        stmt = select(DispositivoAutorizado).where(
            DispositivoAutorizado.empresa_id == escenario.empresa_a_id,
            DispositivoAutorizado.dispositivo_id == disp_id,
        )
        disp_bd = (await db.execute(stmt)).scalars().first()
        assert disp_bd.estado == "REVOCADO"
        assert disp_bd.revocado_en is not None


@pytest.mark.asyncio
async def test_fcm_push_adapter_envio_http_real_y_respuestas(monkeypatch):
    """P0 D3: FCMPushAdapter realiza peticiones HTTP reales (verificadas con MockTransport)
    obteniendo token OAuth2 Bearer con cuenta de servicio Google y validando endpoints FCM v1."""
    import json
    import httpx
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    from backend.app.core.modules.identidad_empresas.services.notificacion_service import FCMPushAdapter

    # 1. Sin credenciales -> NO_CONFIGURADO
    # Entorno vacio explicito prevalece sobre credenciales de backend/.env local.
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    monkeypatch.setenv("FCM_SERVICE_ACCOUNT_JSON", "")
    adapter_sin_cred = FCMPushAdapter()
    res_sin_cred = await adapter_sin_cred.enviar(
        token="token_test",
        canal="FLUTTER",
        titulo="Título",
        cuerpo="Cuerpo",
        payload={"k": "v"},
    )
    assert not res_sin_cred.exito
    assert res_sin_cred.codigo == "NO_CONFIGURADO"

    # 2. Generar clave privada RSA para cuenta de servicio Google simulada
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_pem = rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    sa_info = {
        "client_email": "fashionstore-fcm@test-project.iam.gserviceaccount.com",
        "private_key": rsa_pem,
        "project_id": "test-project",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    monkeypatch.setenv("FCM_SERVICE_ACCOUNT_JSON", json.dumps(sa_info))
    monkeypatch.setenv("FCM_PROJECT_ID", "test-project")

    llamadas = []

    def handler_fcm(request: httpx.Request):
        url_str = str(request.url)
        llamadas.append({
            "url": url_str,
            "auth": request.headers.get("Authorization"),
            "content_type": request.headers.get("Content-Type"),
            "body": request.read().decode("utf-8", errors="ignore"),
        })
        if "oauth2.googleapis.com/token" in url_str:
            # Token OAuth2 generado mediante JWT assertion
            return httpx.Response(200, json={"access_token": "ya29.test_token_fcm_v1_xyz", "expires_in": 3600})
        elif "messages:send" in url_str:
            return httpx.Response(200, json={"name": "projects/test-project/messages/msg_fcm_001"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler_fcm)
    async with httpx.AsyncClient(transport=transport) as client_ok:
        adapter = FCMPushAdapter(http_client=client_ok)
        res_ok = await adapter.enviar(
            token="token_fcm_valido_999",
            canal="FLUTTER",
            titulo="Aviso Pedido",
            cuerpo="Tu pedido está en camino",
            payload={"pedido_id": "ped_123"},
        )
        assert res_ok.exito
        assert res_ok.codigo == "ACEPTADO"
        assert res_ok.mensaje_id == "projects/test-project/messages/msg_fcm_001"
        assert len(llamadas) == 2
        # Primera llamada al endpoint OAuth2 de Google con assertion
        assert "oauth2.googleapis.com/token" in llamadas[0]["url"]
        assert "grant_type" in llamadas[0]["body"]
        # Segunda llamada a FCM v1 con Bearer token obtenido
        assert "messages:send" in llamadas[1]["url"]
        assert llamadas[1]["auth"] == "Bearer ya29.test_token_fcm_v1_xyz"
        assert "token_fcm_valido_999" in llamadas[1]["body"]
        assert "Aviso Pedido" in llamadas[1]["body"]

    # 3. Respuesta 404/410 Token inválido
    def handler_invalid(request: httpx.Request):
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "ya29.token", "expires_in": 3600})
        return httpx.Response(404, json={"error": {"code": 404, "message": "Requested entity was not found."}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_invalid)) as client_inv:
        adapter_inv = FCMPushAdapter(http_client=client_inv)
        res_inv = await adapter_inv.enviar(
            token="token_expirado",
            canal="FLUTTER",
            titulo="Aviso",
            cuerpo="Cuerpo",
            payload={},
        )
        assert not res_inv.exito
        assert res_inv.codigo == "TOKEN_INVALIDO"
        assert res_inv.token_invalido

    # 4. Timeout HTTP
    def handler_timeout(request: httpx.Request):
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "ya29.token", "expires_in": 3600})
        raise httpx.ReadTimeout("Simulated read timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_timeout)) as client_to:
        adapter_to = FCMPushAdapter(http_client=client_to)
        res_to = await adapter_to.enviar(
            token="token_timeout",
            canal="FLUTTER",
            titulo="Aviso",
            cuerpo="Cuerpo",
            payload={},
        )
        assert not res_to.exito
        assert res_to.codigo == "TIMEOUT"


@pytest.mark.asyncio
async def test_webpush_adapter_envio_http_real_y_respuestas(monkeypatch):
    """P0 D3: WebPushAdapter realiza peticiones HTTP reales con firma VAPID ES256
    y cifrado RFC 8291 (aes128gcm), rechazando destinos locales por SSRF."""
    import base64
    import json
    import httpx
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from backend.app.core.modules.identidad_empresas.services.notificacion_service import WebPushAdapter

    # 1. Sin VAPID_PRIVATE_KEY -> NO_CONFIGURADO
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "")
    adapter_sin_vapid = WebPushAdapter()
    res_sin = await adapter_sin_vapid.enviar(
        token="https://push.example.com/sub/123",
        canal="PWA",
        titulo="Título",
        cuerpo="Cuerpo",
        payload={},
    )
    assert not res_sin.exito
    assert res_sin.codigo == "NO_CONFIGURADO"

    # 2. Configurar claves VAPID para el test
    vapid_key = ec.generate_private_key(ec.SECP256R1())
    vapid_priv_pem = vapid_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    vapid_pub_bytes = vapid_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    vapid_pub_b64 = base64.urlsafe_b64encode(vapid_pub_bytes).decode("utf-8").rstrip("=")

    monkeypatch.setenv("VAPID_PRIVATE_KEY", vapid_priv_pem)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", vapid_pub_b64)

    # 2a. Prueba de protección SSRF contra loopback y metadatos
    adapter_ssrf = WebPushAdapter()
    res_ssrf_local = await adapter_ssrf.enviar(
        token="https://127.0.0.1:8080/push",
        canal="PWA",
        titulo="Test",
        cuerpo="Test",
        payload={},
    )
    assert not res_ssrf_local.exito
    assert res_ssrf_local.codigo == "DESTINO_INVALIDO"

    res_ssrf_meta = await adapter_ssrf.enviar(
        token="https://169.254.169.254/latest/meta-data",
        canal="PWA",
        titulo="Test",
        cuerpo="Test",
        payload={},
    )
    assert not res_ssrf_meta.exito
    assert res_ssrf_meta.codigo == "DESTINO_INVALIDO"

    # 2b. Envío conforme a protocolo con suscripción cliente completa (p256dh + auth)
    client_key = ec.generate_private_key(ec.SECP256R1())
    client_pub_bytes = client_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    client_pub_b64 = base64.urlsafe_b64encode(client_pub_bytes).decode("utf-8").rstrip("=")
    client_auth_b64 = base64.urlsafe_b64encode(b"0123456789abcdef").decode("utf-8").rstrip("=")

    endpoint_url = "https://updates.push.services.mozilla.com/wpush/v2/gAAAAAB"
    sub_token = json.dumps({
        "endpoint": endpoint_url,
        "keys": {
            "p256dh": client_pub_b64,
            "auth": client_auth_b64,
        },
    })

    llamadas_wp = []

    def handler_wp(request: httpx.Request):
        raw_body = request.read()
        llamadas_wp.append({
            "url": str(request.url),
            "auth": request.headers.get("Authorization"),
            "content_encoding": request.headers.get("Content-Encoding"),
            "content_type": request.headers.get("Content-Type"),
            "ttl": request.headers.get("TTL"),
            "body_len": len(raw_body),
        })
        return httpx.Response(201)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_wp)) as client_wp:
        adapter = WebPushAdapter(http_client=client_wp)
        res = await adapter.enviar(
            token=sub_token,
            canal="PWA",
            titulo="Notificación Web",
            cuerpo="Tienes un nuevo aviso",
            payload={"tipo": "WEB_AVISO"},
        )
        assert res.exito
        assert res.codigo == "ACEPTADO"
        assert len(llamadas_wp) == 1
        assert llamadas_wp[0]["url"] == endpoint_url
        assert llamadas_wp[0]["auth"].startswith("vapid t=")
        assert f"k={vapid_pub_b64}" in llamadas_wp[0]["auth"]
        assert llamadas_wp[0]["content_encoding"] == "aes128gcm"
        assert llamadas_wp[0]["content_type"] == "application/octet-stream"
        assert llamadas_wp[0]["ttl"] == "60"
        # El cuerpo no es JSON plano, es un payload binario cifrado RFC 8291
        assert llamadas_wp[0]["body_len"] > 86

    # 3. Respuesta 410 Gone (Token WebPush expirado)
    def handler_gone(request: httpx.Request):
        return httpx.Response(410, text="Subscription expired")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_gone)) as client_gone:
        adapter_gone = WebPushAdapter(http_client=client_gone)
        res_gone = await adapter_gone.enviar(
            token=sub_token,
            canal="PWA",
            titulo="Aviso",
            cuerpo="Cuerpo",
            payload={},
        )
        assert not res_gone.exito
        assert res_gone.codigo == "TOKEN_INVALIDO"
        assert res_gone.token_invalido


@pytest.mark.asyncio
async def test_notificaciones_multiples_destinos_aislamiento_reintento(http, escenario, fabrica_sesiones):
    """P0 D3: Múltiples destinos registran resultado individual en payload;
    si uno tiene éxito y el otro falla con TIMEOUT, el segundo intento solo envía al pendiente."""
    http.usar(escenario.usuario_a)

    disp1 = uuid.uuid4()
    disp2 = uuid.uuid4()

    # Registrar dos dispositivos para el usuario
    for disp_id, tok in [(disp1, "tok_disp_1"), (disp2, "tok_disp_2")]:
        await http.cliente.post(
            "/api/v1/notificaciones/dispositivos",
            json={
                "dispositivo_id": str(disp_id),
                "canal": "FLUTTER",
                "push_token": tok,
            },
        )

    # Emitir notificación para usuario_a (sin dispositivo_id fijado para que busque todos sus dispositivos)
    rec_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        srv = NotificacionService(db)
        await srv.emitir_notificacion(
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            tipo="MULTI_DISP_TEST",
            titulo="Aviso",
            cuerpo="Prueba multi destino",
            recurso_tipo="TEST",
            recurso_id=rec_id,
        )
        await db.commit()

    # Primer ciclo: disp1 responde ACEPTADO, disp2 responde TIMEOUT
    envios_disp1 = 0
    envios_disp2 = 0

    class MultiAdapter(BasePushAdapter):
        async def enviar(self, token, canal, titulo, cuerpo, payload):
            nonlocal envios_disp1, envios_disp2
            if "tok_disp_1" in token:
                envios_disp1 += 1
                return PushResult(exito=True, codigo="ACEPTADO", mensaje_id="m1")
            else:
                envios_disp2 += 1
                return PushResult(exito=False, codigo="TIMEOUT", detalle="Timeout en disp2")

    adapter_multi = MultiAdapter()
    async with fabrica_sesiones() as db:
        srv = NotificacionService(db, adapter_fcm=adapter_multi)
        res1 = await srv.procesar_outbox(empresa_id=escenario.empresa_a_id, limite=10)
        await db.commit()

    assert envios_disp1 == 1
    assert envios_disp2 == 1
    # Debe haber quedado en REINTENTO porque disp2 no fue completado
    assert res1["reintentos"] >= 1

    # Segundo ciclo: disp1 ya fue ACEPTADO previamente, solo disp2 debe recibir envío
    class MultiAdapter2(BasePushAdapter):
        async def enviar(self, token, canal, titulo, cuerpo, payload):
            nonlocal envios_disp1, envios_disp2
            if "tok_disp_1" in token:
                envios_disp1 += 1
                return PushResult(exito=True, codigo="ACEPTADO", mensaje_id="m1_duplicado")
            else:
                envios_disp2 += 1
                return PushResult(exito=True, codigo="ACEPTADO", mensaje_id="m2_recuperado")

    async with fabrica_sesiones() as db:
        srv2 = NotificacionService(db, adapter_fcm=MultiAdapter2())
        res2 = await srv2.procesar_outbox(empresa_id=escenario.empresa_a_id, limite=10)
        await db.commit()

    # Verificación estricta de NO duplicación: envios_disp1 sigue en 1
    assert envios_disp1 == 1, "disp1 NO debió recibir segundo envío duplicado"
    assert envios_disp2 == 2, "disp2 debió ser reintentado en el segundo ciclo"
    assert res2["enviados"] >= 1


@pytest.mark.asyncio
async def test_notificaciones_agotamiento_reintentos_marca_fallido_parcial_no_enviado(http, escenario, fabrica_sesiones):
    """P0 Auditoría 28: Si destino A acepta y destino B agota 3 reintentos con fallo,
    el evento global NO debe pasar a ENVIADO; debe marcarse como FALLIDO_PARCIAL
    identificando a B como fallido."""
    http.usar(escenario.usuario_a)

    disp_ok = uuid.uuid4()
    disp_fail = uuid.uuid4()

    # Registrar dos dispositivos
    for disp_id, tok in [(disp_ok, "tok_ok_p28"), (disp_fail, "tok_fail_p28")]:
        await http.cliente.post(
            "/api/v1/notificaciones/dispositivos",
            json={
                "dispositivo_id": str(disp_id),
                "canal": "FLUTTER",
                "push_token": tok,
            },
        )

    rec_id = uuid.uuid4()
    async with fabrica_sesiones() as db:
        srv = NotificacionService(db)
        notif = await srv.emitir_notificacion(
            empresa_id=escenario.empresa_a_id,
            usuario_id=escenario.usuario_a.id,
            tipo="PARCIAL_FAIL_TEST",
            titulo="Aviso Parcial",
            cuerpo="Prueba fallo parcial",
            recurso_tipo="TEST_P28",
            recurso_id=rec_id,
        )
        outbox_id = notif.outbox_id
        await db.commit()

    class PersistentFailAdapter(BasePushAdapter):
        async def enviar(self, token, canal, titulo, cuerpo, payload):
            if "tok_ok" in token:
                return PushResult(exito=True, codigo="ACEPTADO", mensaje_id="m_ok")
            return PushResult(exito=False, codigo="TIMEOUT", detalle="Fallo permanente en disp_fail")

    adapter_p = PersistentFailAdapter()

    # Ejecutar 3 ciclos para agotar los reintentos
    for _ in range(3):
        async with fabrica_sesiones() as db:
            srv = NotificacionService(db, adapter_fcm=adapter_p)
            await srv.procesar_outbox(empresa_id=escenario.empresa_a_id, limite=10)
            await db.commit()

    # Verificar estado final del evento outbox
    async with fabrica_sesiones() as db:
        ev = (await db.execute(select(EventoOutbox).where(EventoOutbox.id == outbox_id))).scalars().first()
        assert ev is not None
        assert ev.intentos >= 3
        # PROHIBIDO marcar ENVIADO si un destino falló
        assert ev.estado != "ENVIADO", f"El outbox no debe ser ENVIADO cuando un destino falló; estado={ev.estado}"
        assert ev.estado == "FALLIDO_PARCIAL"
        assert ev.payload.get("_entrega_parcial") is True
        assert str(disp_fail) in ev.payload.get("_destinos_fallidos", [])
        res_dict = ev.payload.get("_destinos_resultado", {})
        assert "ACEPTADO" in res_dict.values()
        assert "TIMEOUT" in res_dict.values()


@pytest.mark.asyncio
async def test_scheduler_inicia_con_job_outbox_programado():
    """P0 D3: Iniciar scheduler programa los dos jobs requeridos: expiración CU24 y worker outbox."""
    from backend.app.core.tareas import iniciar_scheduler, detener_scheduler

    detener_scheduler()
    sched = iniciar_scheduler(intervalo_minutos=5)
    assert sched is not None
    job_ids = [j.id for j in sched.get_jobs()]
    assert "cu24_expirar_vencidas" in job_ids
    assert "worker_outbox_notificaciones" in job_ids
    detener_scheduler()
