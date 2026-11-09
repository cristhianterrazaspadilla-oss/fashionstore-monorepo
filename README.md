# FashionStore monorepo

Instantánea del código local de los tres proyectos, incluidos cambios sin commit
y archivos nuevos. Historial Git nuevo; los historiales y stashes originales no
se importan. No hay submódulos.

## Estructura

- `fashionstore_backend/`: API FastAPI, modelos, migraciones y pruebas Python.
- `fashionstore_frontend/`: aplicación web Angular.
- `fashionstore_app/`: aplicación Flutter y sus pruebas.

## Arranque local

Los siguientes comandos son instrucciones para preparar un entorno propio;
no se instalaron dependencias ni se ejecutaron servidores durante esta importación.

Backend (Python 3.11+, desde una terminal en la raíz):

```powershell
cd fashionstore_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Completar .env con valores propios antes de iniciar el servidor.
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

El backend requiere una base PostgreSQL preparada por separado. No se ejecutan
migraciones automáticamente. El `docker-compose.yml` heredado referencia un SQL
externo que no forma parte de estos tres proyectos: revisar ese montaje antes
de usar Docker Compose.

Frontend (Node.js compatible con Angular 18, terminal independiente):

```powershell
cd fashionstore_frontend
npm ci
npm start
```

Móvil (Flutter compatible con `pubspec.yaml`, terminal independiente):

```powershell
cd fashionstore_app
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

La URL anterior corresponde al emulador Android. Para otro dispositivo, usar
la dirección del backend local accesible desde ese dispositivo. Las claves
publicables de Stripe del cliente son configuración pública; las claves privadas
se suministran únicamente al backend. Android requiere aportar su configuración
Firebase propia para el plugin Google Services y generar la configuración local
del SDK; no se incluyen credenciales ni archivos de firma.

## Validación pendiente

Los conflictos de las pruebas móviles están resueltos en el contenido copiado.
**Las pruebas Flutter siguen pendientes; no se declara que pasen.**

```powershell
cd fashionstore_app
flutter test --no-pub --reporter expanded test/widget/caja_flujo_productivo_completo_test.dart test/widget/caja_offline_screen_test.dart
```

## Exclusiones

Se omiten `.git` internos, entornos virtuales, `node_modules`, cachés, compilados,
entornos `.env` reales, claves privadas, credenciales y bases o respaldos locales.
Se conservan las plantillas de entorno revisadas, manifiestos de dependencias y
lockfiles, esquemas y migraciones SQL.

También se excluyeron la semilla `sql/neon/02_reset_semilla_oficial_ciclo2.sql`
del backend (contenía hashes de contraseñas y datos de contacto) y la guía móvil
`GUIA_FCM_ANDROID_AUDITORIA.md` (contenía una cadena con formato de clave de
proveedor). Ambos archivos permanecen intactos en los proyectos originales.
La semilla de ciclo 3 conserva datos de demostración y depende de una base
preparada; no se ejecutó ningún SQL ni se conectó a Neon durante la importación.
