# FashionStore Móvil — Flutter App

Aplicación móvil desarrollada en **Flutter** para la plataforma FashionStore (Ciclos 1, 2 y 3), diseñada con una experiencia de usuario moderna, probador virtual en tiempo real y flujo de compra integral.

---

## Características Principales

- **Catálogo y Exploración de Productos**:
  - Visualización de categorías, productos, variantes de color y tallas.
  - Galería detallada de fotos y disponibilidad de stock por sucursal.
- **Carrito de Compras y Reservas**:
  - Carrito persistente con validación de inventario en tiempo real.
  - Gestión de reservas presenciales y solicitud de traslados inter-sucursales cuando no hay stock local.
- **Checkout y Pagos con Stripe (CU15)**:
  - Flujo de checkout con selección de entrega (Recojo en Tienda o Delivery).
  - Integración segura con **Stripe Test Mode** mediante clave publicable (`pk_test_...`) inyectable por entorno.
- **Probador Virtual IA en Tiempo Real (CU17 — Decart)**:
  - Transformación de video en tiempo real utilizando el modelo `lucy-2.5` de Decart AI.
  - **Puente nativo en Android (`DecartTryOnBridge` / `DecartVideoView`)**: Integración directa con el SDK de Decart en Kotlin, garantizando máximo rendimiento de streaming y renderizado de video.
  - **Arquitectura de Seguridad**: La app móvil nunca almacena la API Key maestra de Decart; solicita tokens temporales seguros al backend FastAPI.
- **Búsqueda por Voz y Asistente de Estilo (CU18 / CU20)**:
  - Reconocimiento de voz para búsqueda rápida de prendas.
  - Recomendaciones inteligentes basadas en contexto.
- **Seguimiento de Pedidos y Perfil (CU16)**:
  - Historial y estado de pedidos en tiempo real (activo, completado, cancelado).
  - Puerta de autenticación contextual (`PuertaAuth`): navegación pública del catálogo con solicitud de login únicamente al realizar acciones protegidas.

---

## Requisitos Previos

- **Flutter SDK**: 3.24 o superior (Dart 3.5+).
- **Android Studio / SDK**: Android SDK con `minSdkVersion 24` (Android 7.0+) y `targetSdkVersion 34`.
- **Dispositivo Físico Android**: Recomendado para pruebas de cámara y streaming en vivo del probador virtual Decart.

---

## Configuración y Ejecución

### 1. Obtener dependencias

```bash
cd app-movil
flutter pub get
```

### 2. Ejecutar en Emulador o Dispositivo

Por defecto, la app apunta al backend de producción en Render.

```bash
flutter run
```

#### Parámetros de Entorno (`--dart-define`)

Puedes personalizar los endpoints o credenciales sin modificar el código fuente:

```bash
# Apuntando al backend local en emulador Android (10.0.2.2)
flutter run \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 \
  --dart-define=STRIPE_PUBLISHABLE_KEY=pk_test_tu_clave_publicable

# Apuntando a dispositivo físico en la misma red Wi-Fi
flutter run \
  --dart-define=API_BASE_URL=http://192.168.1.50:8000/api/v1
```

---

## Pruebas Automatizadas

El proyecto cuenta con una cobertura completa de pruebas unitarias y de widgets (más de 150 pruebas):

```bash
# Análisis estático de código
flutter analyze

# Ejecutar suite de pruebas
flutter test
```

---

## Estructura del Proyecto

```
app-movil/
├── android/
│   └── app/src/main/kotlin/.../
│       ├── MainActivity.kt        # Registro de canales de plataforma
│       ├── DecartTryOnBridge.kt   # Puente nativo Kotlin para Decart AI
│       └── DecartVideoView.kt     # Vista nativa de video streaming
├── lib/
│   ├── core/
│   │   ├── config/                # ApiConfig y StripeConfig (inyección segura)
│   │   ├── models/                # Modelos de datos (catálogo, carrito, checkout, pagos, etc.)
│   │   ├── network/               # Cliente HTTP centralizado y manejo de errores
│   │   ├── services/              # Servicios de negocio (carrito, pedidos, IA, etc.)
│   │   └── session/               # Manejo de tokens y PuertaAuth
│   ├── features/
│   │   ├── auth/                  # Inicio de sesión y registro
│   │   ├── catalogo/              # Pantallas de catálogo y detalle
│   │   ├── carrito/               # Gestión de cesta de compras
│   │   ├── checkout/              # Proceso de compra y entrega
│   │   ├── probador/              # Probador virtual con cámara y video en vivo
│   │   ├── pedidos/               # Historial y seguimiento de pedidos
│   │   └── busqueda/              # Búsqueda tradicional y por voz
│   └── main.dart
├── test/
│   ├── unit/                      # Pruebas unitarias de servicios y modelos
│   └── widget/                    # Pruebas de widgets y flujos de usuario
└── pubspec.yaml                   # Dependencias de Flutter
```
