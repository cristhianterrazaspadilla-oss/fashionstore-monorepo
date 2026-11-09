# FashionStore Web — Frontend

Aplicación Web Single Page Application (SPA) desarrollada en **Angular** con arquitectura de componentes Standalone y diseño responsive premium para la plataforma FashionStore.

---

## Características Principales

- **Arquitectura Angular Standalone**: Enrutamiento modular sin NgModules redundantes, componentes ligeros y lazy-loading optimizado.
- **Control de Acceso por Roles (RBAC)**:
  - **Administrador**: Gestión global de sucursales, usuarios, catálogo maestro y dashboard gerencial.
  - **Encargado de Sucursal**: Gestión de stock local, recepción de traslados y supervisión de pedidos.
  - **Cajero / Vendedor**: Venta presencial, registro de pagos, canje de reservas y emisión de comprobantes.
  - **Almacenero**: Preparación de pedidos, picking y control de mermas/devoluciones.
  - **Cliente**: Exploración de catálogo, carrito de compras, reservas y seguimiento de pedidos.
- **E-Commerce y Pasarela de Pago**:
  - Catálogo interactivo con filtros avanzados (categorías, precio, disponibilidad).
  - Carrito de compras y checkout integrado con **Stripe Elements** (Test Mode).
  - Selección de método de entrega (Recojo en sucursal o Delivery).
- **Módulo de Inteligencia Artificial**:
  - Asistente de compras y consultas por lenguaje natural / texto asistido.
- **Dashboard Analítico**: Visualizaciones de datos nativas (gráficos de barras segmentadas y horizontales sin dependencias externas).

---

## Requisitos Previos

- **Node.js**: 18.x o 20.x LTS.
- **npm**: 9.x o superior.
- **Angular CLI** (opcional para comandos globales): `npm install -g @angular/cli`.

---

## Instalación y Ejecución Local

### 1. Instalar dependencias

```bash
cd frontend-web
npm install
```

### 2. Configuración de Entornos

Los archivos de configuración se encuentran en `src/environments/`:
- `environment.ts`: Entorno de desarrollo local (`http://127.0.0.1:8000/api/v1`).
- `environment.production.ts`: Entorno de producción (URL del backend desplegado en Render).

```typescript
export const environment = {
  production: false,
  apiUrl: 'http://127.0.0.1:8000/api/v1',
  stripePublicKey: 'pk_test_...'
};
```

### 3. Iniciar el Servidor de Desarrollo

```bash
npm start
# O con Angular CLI:
# ng serve
```

Navega a `http://localhost:4200/`. La aplicación se recargará automáticamente ante cualquier cambio de código.

---

## Compilación para Producción

Generar el paquete optimizado para producción:

```bash
npm run build
```

Los artefactos compilados se generarán en el directorio `dist/fashionstore-web/`.

---

## PWA instalable y Render

El build de producción publica los archivos de `dist/fashionstore-web/browser/`,
incluidos `manifest.webmanifest`, los iconos, `custom-sw.js`, `ngsw-worker.js`
y `ngsw.json`. `custom-sw.js` es el único worker registrado: conserva Web Push
e importa el worker de Angular para cachear solo archivos estáticos de la app.
El API y los pagos quedan fuera del caché del service worker.

En Render Static Site usa `npm ci && npm run build`, publica
`dist/fashionstore-web/browser` y configura una reescritura `/*` a
`/index.html` para las rutas Angular. Comprueba que el manifest, los iconos
y ambos scripts del worker responden como archivos reales. La instalación
requiere HTTPS. No hay variables Firebase en este frontend: Web Push obtiene
la clave pública VAPID del backend.

Para consultar prendas sin conexión, un cliente debe iniciar sesión y usar
«Descargar catálogo local» mientras tiene internet. Esa descarga prepara además
la referencia horaria necesaria para guardar solicitudes offline durante su
vigencia. Desde el catálogo guardado puede crear una solicitud de pedido para
recojo; se guarda en IndexedDB con UUID estable y se envía al reconectar.
El pedido no queda confirmado ni pagado hasta que el servidor valide stock,
precio y condiciones. Las imágenes externas pueden requerir conexión.

## Despliegue en Vercel

El proyecto incluye el archivo de configuración `vercel.json` listo para despliegues continuos en Vercel:

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

---

## Estructura del Proyecto

```
frontend-web/
├── src/
│   ├── app/
│   │   ├── core/           # Guards, interceptores HTTP, servicios base y autenticación
│   │   ├── features/       # Módulos funcionales (catálogo, reservas, checkout, dashboard, etc.)
│   │   ├── shared/         # Componentes reutilizables, visualizaciones de datos y layout
│   │   ├── app.component.ts
│   │   ├── app.routes.ts
│   │   └── app.config.ts
│   ├── environments/       # Configuraciones por entorno
│   └── styles.css          # Estilos globales y tokens de diseño
├── angular.json            # Configuración de Angular Workspace
├── package.json            # Dependencias y scripts npm
└── vercel.json             # Configuración de despliegue SPA
```
