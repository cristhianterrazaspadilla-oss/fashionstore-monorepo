# FashionStore API — Backend

API REST asíncrona de alto rendimiento desarrollada con **FastAPI**, **SQLAlchemy (AsyncIO)** y **PostgreSQL** para la plataforma FashionStore (Ciclos 1, 2 y 3).

---

## Características Principales

- **Seguridad y Autenticación**: Tokens JWT (`Bearer`), control de acceso basado en roles (RBAC: Administrador, Encargado de Sucursal, Cajero, Almacenero, Cliente).
- **Gestión de Catálogo e Inventario**: Categorías, productos, variantes (talla/color), imágenes y control de stock por sucursal.
- **Kardex Multi-Sucursal**: Registro inmutable de movimientos de inventario con costeo promedio ponderado.
- **Ciclo de Reservas y Traslados**:
  - Reservas locales con ventana de expiración automática.
  - Solicitud, aprobación, despacho y recepción de traslados inter-sucursales.
- **Venta Presencial y Caja**: Venta directa o desde reserva, adelantos, tickets y devoluciones/mermas con reposición o baja en Kardex.
- **E-Commerce y Checkout (Ciclo 3)**:
  - Carrito de compras aislado por usuario/dispositivo.
  - Checkout con reserva de inventario temporal (60 minutos).
  - Pagos seguros con **Stripe Test Mode** y conciliación vía Webhooks.
  - Entregas con opción de recojo en sucursal o delivery a domicilio.
- **Probador Virtual IA (Decart)**:
  - Integración con el modelo `lucy-2.5` de Decart AI.
  - Emisión de tokens cliente efímeros (TTL seguro) sin exponer credenciales maestras.
- **Inteligencia Artificial y Recomendaciones**:
  - Asistente de búsqueda por voz y recomendaciones personalizadas vía Gemini API con fallback determinista.
- **Dashboard & Analítica**: Reportes consolidados de ventas, valorización de inventario y auditoría operativa.

---

## Requisitos Previos

- **Python**: 3.11 o superior.
- **PostgreSQL**: 15 o superior.
- **Docker & Docker Compose** (opcional, para base de datos local).

---

## Instalación y Configuración

### 1. Clonar el repositorio y preparar el entorno virtual

```bash
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# En Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# En Linux/macOS:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

Copiar la plantilla de ejemplo y completar los valores requeridos:

```bash
cp .env.example .env
```

Editar `.env` según tu entorno:
```ini
# Base de datos PostgreSQL
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=fashionstore_db

# Seguridad JWT
SECRET_KEY=tu_clave_secreta_super_segura
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Stripe (Opcional en desarrollo local)
STRIPE_ENABLED=false
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# Decart AI (Lucy 2.5)
DECART_ENABLED=false
DECART_API_KEY=
DECART_MODEL=lucy-2.5

# Gemini AI (Opcional)
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
```

### 3. Migraciones de Base de Datos

Ejecutar las migraciones con Alembic para inicializar las tablas:

```bash
alembic upgrade head
```

### Push Firebase en local y Render

El JSON privado de la cuenta de servicio Firebase se guarda fuera de Git.
Para desarrollo local, definir `GOOGLE_APPLICATION_CREDENTIALS` en `backend/.env`
con la ruta absoluta del archivo. Para Render, subir el JSON en **Environment →
Secret Files** como `firebase-service-account.json` y definir
`GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/firebase-service-account.json`.
También se admite `FCM_SERVICE_ACCOUNT_JSON` con el contenido completo como
variable secreta de Render; no se requieren ambas opciones. `project_id` se
obtiene del propio JSON.

El worker que entrega las notificaciones del outbox se activa con
`EXPIRACION_JOB_ACTIVO=true`. Ejecutarlo en una sola instancia del backend.
Para Web Push, configurar además `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY` y
`VAPID_SUBJECT`. Estas claves VAPID son independientes de Firebase.

Antes del despliegue, aplicar `alembic upgrade head` en Neon y comprobar
`public.alembic_version`. Subir el código a GitHub no ejecuta migraciones.

---

## Ejecución del Servidor

Iniciar el servidor en modo desarrollo con recarga automática:

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

> **Documentación Interactiva:**
> - Swagger UI: `http://localhost:8000/docs`
> - Redoc: `http://localhost:8000/redoc`

---

## Pruebas Automatizadas

El backend cuenta con una suite completa de pruebas unitarias y de integración.

> **Importante:** Por seguridad contra pérdida de datos, las pruebas solo se ejecutan si la base de datos configurada termina en `_test` (ej. `fashionstore_test`).

```bash
# Configurar PYTHONPATH y ejecutar pytest
$env:PYTHONPATH=".;backend"
pytest backend/tests -v
```

---

## Estructura del Proyecto

```
backend/
├── alembic/              # Scripts de migración de base de datos
├── app/
│   ├── api/v1/           # Endpoints agrupados por módulo funcional
│   ├── core/             # Configuración, base de datos y seguridad
│   ├── models/           # Modelos declarativos SQLAlchemy
│   ├── repositories/     # Capa de acceso a datos
│   ├── schemas/          # Esquemas de validación Pydantic
│   └── services/         # Lógica de negocio transaccional
├── backups/              # Respaldos de base de datos
├── sql/                  # Scripts SQL de inicialización
├── tests/                # Suite de pruebas automatizadas
├── .env.example          # Plantilla de variables de entorno
└── requirements.txt      # Dependencias del proyecto
```
