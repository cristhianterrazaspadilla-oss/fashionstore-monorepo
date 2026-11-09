# Base de pruebas del backend (Ciclo 2)

Las pruebas crean usuarios, sucursales, productos, reservas y ventas:
son **destructivas** y nunca deben ejecutarse contra `fashionstore_db`.
La suite se niega a correr si la base EFECTIVA no termina en `_test`
(protección en `tests/conftest.py`, función `nombre_base_efectiva`).

## Mecanismo real implementado (`conftest.py`)

1. Al importarse `tests/conftest.py`, ANTES de importar cualquier módulo que
   inicialice configuración, engine, sesiones o la app FastAPI, se copian los
   alias de pruebas a las variables que la aplicación realmente consume:
   - `TEST_DATABASE_URL` → `DATABASE_URL`
   - `TEST_POSTGRES_DB` → `POSTGRES_DB`
   - `TEST_POSTGRES_SERVER` → `POSTGRES_SERVER`
   - `TEST_POSTGRES_PORT` → `POSTGRES_PORT`
   - `TEST_POSTGRES_USER` → `POSTGRES_USER`
   - `TEST_POSTGRES_PASSWORD` → `POSTGRES_PASSWORD`
2. Recién después se importa `backend.app.core.config.settings`,
   `backend.app.core.database` (engine/SQLAlchemy) y `backend.app.main:app`.
   No existen dos fuentes de verdad: todo lee la configuración efectiva.
3. `nombre_base_efectiva()` inspecciona `settings.async_database_url` (la
   misma URL que usa el engine), extrae el path sin query string ni
   credenciales con `urllib.parse.urlsplit` y devuelve solo el nombre de la
   base. Funciona tanto con `DATABASE_URL` como con la composición
   `POSTGRES_*`, porque `Settings` ya resolvió esa prioridad.
4. `es_base_de_pruebas()` exige que el nombre termine en `_test`
   (p. ej. `fashionstore_test`). Si no, el fixture de sesión
   `_proteger_base_productiva` (autouse) hace `pytest.fail` antes de crear,
   eliminar o modificar ningún dato.
5. No se usa el valor de una variable auxiliar como evidencia: solo cuenta la
   URL efectiva de SQLAlchemy. Un conflicto como
   `DATABASE_URL=.../fashionstore_db` + `TEST_POSTGRES_DB=fashionstore_test`
   falla cerrado (gana `DATABASE_URL`, la efectiva es productiva y la suite
   aborta).

## 1. Crear y preparar la base (una vez)

```powershell
cd backend
$env:POSTGRES_DB = "fashionstore_test"
$env:TEST_ADMIN_EMAIL = "admin@fashionstore.com"
$env:TEST_ADMIN_PASSWORD = "Fashion123!"
venv\Scripts\python.exe tests/preparar_base_pruebas.py
```

El script (con protección `_test`) hace, en orden:

1. `CREATE DATABASE` si falta (sin tocar otras bases).
2. `CREATE SCHEMA IF NOT EXISTS` de los seis esquemas.
3. Esquema Ciclo 1 desde los modelos (las migraciones lo asumen).
4. Retiro del índice plano `uq_movimientos_efecto_logico` si no es el de
   la migración (el modelo lo declara sin `COALESCE`).
5. `alembic upgrade head` (tipos ENUM y tablas del Ciclo 2; idempotente).
6. Verificación del índice `uq_movimientos_efecto_logico` con el DDL exacto
   de la migración (repara re-ejecuciones donde alembic ya está en head).
7. Resto del esquema desde los modelos (`checkfirst`).
8. Semilla del tenant heredado `fashionstore`: roles empresariales,
   `SUPERADMIN` de plataforma, ciudad, sucursal, admin de pruebas, maestros de
   catalogo (talla, color, categoria, proveedor), plan `TEST` y suscripcion
   vigente creada por el superadmin. Si no hay tasa vigente, anade una tasa
   BOB/USD de prueba. La suite crea y limpia el resto de sus datos.

El script es idempotente: puede repetirse sin duplicar la semilla.

## 2. Ejecutar la suite contra la base de pruebas

```powershell
cd backend
$env:POSTGRES_DB = "fashionstore_test"
$env:TEST_ADMIN_EMAIL = "admin@fashionstore.com"
$env:TEST_ADMIN_PASSWORD = "Fashion123!"
venv\Scripts\python.exe -m pytest tests/ -q
```

Equivalencias aceptadas (se copian a las reales antes del import, ver
mecanismo arriba):
`TEST_DATABASE_URL=.../fashionstore_test` → `DATABASE_URL`, o
`TEST_POSTGRES_DB=fashionstore_test` → `POSTGRES_DB`.

Para demostrar qué base efectiva usa la aplicación (sin imprimir secretos):

```powershell
cd backend
$env:POSTGRES_DB = "fashionstore_test"
venv\Scripts\python.exe -c "import sys; sys.path.insert(0, '.'); sys.path.insert(0, '..'); import app; from backend.app.core.config import settings; from urllib.parse import urlsplit; u=settings.async_database_url; print(urlsplit(u.split('?')[0]).path.rsplit('/',1)[-1])"
# Debe imprimir: fashionstore_test
```

## 3. Credenciales de pruebas

- Auto-login del fixture `cliente_http`: `TEST_ADMIN_EMAIL` (por defecto
  `admin@fashionstore.com`) y `TEST_ADMIN_PASSWORD` (por defecto
  `Fashion123!`). No se usa `admin123456` en ningún test.
- La semilla de suscripcion usa `TEST_SUPERADMIN_EMAIL` y
  `TEST_SUPERADMIN_PASSWORD` (por defecto `superadmin@fashionstore.com` /
  `Fashion123!`). El usuario se crea solo en la base aislada `*_test`; lo
  requiere el trigger de plataforma que valida `creada_por` al asignar planes.
- La prueba de rollback de adelanto (`test_sucursal_adelanto_coherente`)
  compara contra el estado original de la sucursal, sin asumir
  `adelanto_activo=false`.

## 4. Verificación de no contaminación

```powershell
# fashionstore_db conserva sus conteos; solo fashionstore_test crece:
# (ver entrega: 7 usuarios, 5 roles, 3 sucursales, 0 reservas, 0 ventas,
#  48 movimientos en fashionstore_db antes y después).
```

Si pytest muestra el mensaje de protección (`... base EFECTIVA es '...'`), 
revise que `POSTGRES_DB`/`DATABASE_URL` apunten a `fashionstore_test`
en esa terminal antes de reintentar. Nunca se truncó ni se limpió
`fashionstore_db` desde pytest.

## 5. Proveedor IA durante las pruebas

El fixture automático de `conftest.py` deja `settings.GEMINI_API_KEY` vacío para
cada prueba. Así se usa el proveedor determinista aunque `backend/.env` tenga
una clave Gemini, y la suite no depende de llamadas externas. La aplicación
fuera de pytest conserva su configuración normal.
