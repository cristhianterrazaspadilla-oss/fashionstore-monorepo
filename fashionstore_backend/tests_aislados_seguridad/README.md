# Pruebas aisladas H01, H02, H15 y H17

Ejecutar esta suite en un proceso independiente, desde la raíz del backend:

```powershell
$env:FASHIONSTORE_SQLITE_SECURITY_TESTS = '1'
python -B -m pytest tests_aislados_seguridad -q -p no:cacheprovider -o asyncio_default_fixture_loop_scope=function
```

No ejecutar este comando contra una base compartida: la suite **no necesita
ninguna conexión PostgreSQL**. Antes de importar la aplicación sustituye el
módulo de persistencia por una Base SQLAlchemy aislada y una dependencia que
falla si falta su override. No importa `database.py`, no ejecuta el lifespan y
bloquea conexiones de red, salvo el socketpair interno de asyncio en Windows.

Ejecuta rutas HTTP y servicios/repositorios de producción con datos sintéticos
de dos empresas en SQLite exclusivamente en memoria. Captura las consultas y
comprueba resultados y conteos reales; no sustituye las consultas por respuestas
predeterminadas. La sesión síncrona SQLite tiene un adaptador de interfaz async.
Los artefactos ML se escriben únicamente en el directorio temporal de pytest.

La prueba de cancelación sustituye el límite con el job PostgreSQL/proveedor;
comprueba que el servicio le entrega solo empresa, venta y lote autorizados.
La ejecución completa de ese job sigue pendiente en PostgreSQL aislado.

Entorno usado en esta revisión: Python 3.11, FastAPI 0.115.6, Pydantic 2.10.4,
SQLAlchemy 2.0.36, pytest 8.3.4, pytest-asyncio 0.25.0, HTTPX 0.28.1 y NumPy 2.2.0,
con las dependencias de importación del backend disponibles localmente.
No es necesario instalar drivers PostgreSQL para esta suite.

Limitaciones: las tablas de prueba conservan las columnas ORM, pero no reproducen
las restricciones, índices, triggers, bloqueo ni semántica temporal PostgreSQL.
Esta suite no valida migraciones, concurrencia, proveedor de pagos, JWT real,
despliegue o funcionamiento de navegadores/Flutter. La identidad autenticada se
inyecta mediante el mecanismo estándar de dependency overrides de FastAPI.

Política aplicada: CU02 permite consultas convencionales después de la gracia.
La nueva generación de reportes premium y el entrenamiento ML requieren la
capacidad configurada y una suscripción efectiva vigente o dentro de sus 72 h
de gracia. Los GET ML actuales también entrenan/persisten; no son una consulta
de un artefacto previamente guardado. CU10/11/24 reservan estas capacidades al
administrador empresarial; no habilitan acceso comercial global de plataforma.

## Extension H04/H05

Se agregaron tres casos de caja: reintento inmutable con un solo pago/Kardex/consumo,
rechazo de variantes repetidas y del limite temporal exclusivo, y consulta de turno
con empresa/titular/sucursal autorizados (incluido dispositivo de otro cajero).
Resultado de la entrega: **37 pruebas aprobadas**, conservando las 34 anteriores.

El cambio de backend es aditivo en TurnoHabilitacionDTO: empresa_id y hora_central_en.
Los clientes nuevos hacen GET fresco para anclar el reloj; el POST idempotente puede
conservar su respuesta original. Las rutas y el cuerpo de venta no cambiaron.
La venta usa la columna hash_solicitud existente para comprobar UUID + turno + cuerpo;
una venta central antigua sin esa huella devuelve conflicto para conciliacion, sin
inventar igualdad ni duplicar el cobro. Se bloquea turno antes de resolver reintentos
y se usan los bloqueos de inventario existentes antes de descontar comprometido_caja.

No hay cambios DDL/migraciones/semillas. SQLite de esta suite no demuestra bloqueo
FOR UPDATE ni concurrencia PostgreSQL. Esa verificacion debe hacerse posteriormente
con una base desechable, configuracion exclusivamente de pruebas y dos transacciones,
sin respaldo a una conexion real ni llamadas a proveedores.
