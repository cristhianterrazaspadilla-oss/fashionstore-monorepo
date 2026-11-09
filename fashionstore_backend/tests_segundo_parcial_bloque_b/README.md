# Suite aislada — Bloque B (CU03, CU04, CU16, CU18)

Pruebas ejecutables de extremo a extremo (servicios + rutas HTTP) para la
corrección del Bloque B. **No usa `tests/conftest.py`** porque ese archivo
trunca tablas y recarga la semilla sobre la base efectiva.

## Requisitos de seguridad

- La URL se lee de `FASHIONSTORE_TEST_DATABASE_URL`.
- El nombre de la base debe terminar en `_test`; de lo contrario la suite
  aborta antes de importar la aplicación.
- No hay URL, usuario, contraseña ni nombre de base codificados en el
  repositorio.
- Los datos se crean con un sufijo único y se confirman; no se ejecutan
  `DELETE`, `TRUNCATE` ni limpieza manual sobre bases compartidas.
- La base debe estar migrada a `0007_reservas_offline`.

## Comando

Desde `backend/`:

```powershell
$env:FASHIONSTORE_TEST_DATABASE_URL="postgresql+asyncpg://USUARIO:CLAVE@127.0.0.1:5432/NOMBRE_test"
python -m pytest tests_segundo_parcial_bloque_b -q
```

## Cobertura

| Archivo | Verifica |
| --- | --- |
| `test_catalogo_publico.py` | Aislamiento por empresa, DTO público sin costos/proveedor, contexto obligatorio, instantánea `REPEATABLE READ` con escritura concurrente invisible, ruta administrativa acotada a la sesión. |
| `test_catalogo_compatibilidad.py` | Compatibilidad de llamadas públicas y legacy (/productos, /variantes, disponibilidad), VariantePublicaDTO sin costos internos, aislamiento a sucursales de la empresa y llamadas simuladas de Angular y Flutter. |
| `test_reservas_online.py` | Origen 24 h, visita inválida sin reserva/Kardex, líneas duplicadas, idempotencia y 409, aislamiento, adelanto oportuno a origen + 72 h y tardío rechazado, última unidad, rollback multilínea y Kardex. |
| `test_sincronizacion_offline.py` | C34 (8 h + 5 min), 24 h desde creación local, validación de visita posterior a la recepción del servidor (T0, visita T0+1h, sync T0+2h rechazada sin tocar inventario; visita futura aceptada), líneas duplicadas, reintento idempotente, 409 `OPERACION_MODIFICADA`, consulta por UUID ajena, concurrencia del mismo `operacion_id`, dos operaciones por la última unidad y DTO estricto. |
| `test_politica_plan.py` | Política de capacidad del plan (vigente, en gracia 3 días, vencida fuera de gracia, sin suscripción), bloqueo online con HTTP 403 PLAN_NO_HABILITADO y offline con resultado durable RECHAZADA/PLAN_NO_HABILITADO sin reserva ni Kardex. |
| `test_http_rutas.py` | Aceptación/rechazo/reintento por HTTP, sesión sin empresa, referencia y operación offline, consulta ajena, descarga de catálogo. |
| `test_openapi_segundo_parcial.py` | Exportación vigente sin desfase y compatibilidad del contrato histórico del Ciclo 3. |
