# CU17 — Arquitectura del probador Decart

## Decisión de configuración multitenant

FashionStore utiliza **una sola cuenta y una sola API key de Decart por despliegue del backend**, compartida por todas las empresas (tenants). `DECART_API_KEY` y `DECART_ENABLED` son configuración global del servicio FastAPI; no son ajustes de cada empresa. La clave no se almacena en tablas de empresa, no se entrega a Flutter y no se configura desde los dashboards de tenant.

Por tanto, las sesiones de todas las empresas consumen el saldo/créditos de la misma cuenta Decart. El sistema aplica el límite operativo que tenga configurado el backend; no existe presupuesto ni facturación independiente por tenant en Decart. Cualquier futura cuota comercial por empresa tendría que implementarse en FashionStore antes de emitir el token, sin crear cuentas Decart por tenant.

La clave permanente se configura como secreto de entorno del backend local o de Render. La aplicación móvil recibe únicamente un token de cliente temporal, limitado a `lucy-2.5`, con 60 segundos de vigencia y una sesión máxima de 120 segundos.

## Separación de datos entre empresas

Compartir la cuenta del proveedor no comparte el catálogo ni autoriza acceso cruzado. Cada solicitud CU17 debe:

1. Autenticar un usuario con rol `CLIENTE` y una empresa asignada.
2. Resolver la variante dentro de `usuario.empresa_id`; no aceptar una variante de otra empresa aunque el ID sea conocido.
3. Tomar la imagen de referencia y el prompt del catálogo de esa misma empresa; Flutter no elige un host ni envía un prompt libre.
4. Emitir el token de Decart desde la configuración global únicamente después de validar variante, imagen y consentimiento.

El control del alcance de empresa pertenece a FashionStore y al backend. Decart recibe el token limitado y los datos audiovisuales necesarios para esa sesión; no decide la membresía o permisos de los usuarios de FashionStore.

## Flujo de video

1. El cliente autenticado abre una prenda compatible desde el catálogo móvil.
2. FastAPI valida que la variante y el producto estén activos y sean de la empresa del usuario. La prenda debe tener una imagen HTTPS compatible.
3. FashionStore informa que el video se transmite a Decart. El usuario acepta antes de pedir permiso de cámara.
4. Flutter llama `POST /api/v1/probador/autorizaciones` con el consentimiento vigente y una clave de idempotencia. FastAPI emite un token corto usando la API key global.
5. El puente Kotlin usa el SDK Android oficial `com.github.DecartAI:decart-android:0.7.10`, el modelo `lucy-2.5`, cámara frontal y `MirrorMode.AUTO`. El SDK publica el video de cámara por WebRTC y entrega el track remoto transformado al renderer Android.
6. La imagen de la prenda se carga en memoria y se entrega como referencia al SDK. Al cambiar de prenda, la app solicita una nueva transformación en la sesión actual.
7. Flutter solo considera visible la transformación después de recibir un frame remoto posterior al evento de generación. Al salir, pausar, bloquear pantalla o fallar la sesión, desconecta y libera el SDK y detiene la cámara.

No se transmite audio en el probador. No se usa WebRTC implementado manualmente, procesamiento local de imagen, pose, segmentación ni overlay.

## Configuración global

Variables del backend:

| Variable | Alcance | Uso |
|---|---|---|
| `DECART_ENABLED` | Global | Habilita CU17 en el despliegue. |
| `DECART_API_KEY` | Global, secreta | API key permanente; solo la usa FastAPI. |
| `DECART_API_BASE_URL` | Global | Endpoint oficial de Decart. |
| `DECART_ORIGENES_PERMITIDOS` | Global | Hosts HTTPS permitidos para imágenes de prendas. |
| `DECART_RATE_LIMIT_POR_MINUTO` | Global | Límite operativo aplicado por backend al usuario autenticado. |

El modelo, la vigencia del token y la duración máxima de sesión se fijan en el contrato backend de CU17. No crear claves, credenciales, columnas o pantallas de configuración Decart por tenant. La lista de hosts permitidos se configura en el backend y es común a todas las empresas.

## Datos y privacidad

- Video, frames, audio, SDP, token de cliente y bytes de la imagen no se persisten en PostgreSQL ni en logs.
- FastAPI registra únicamente metadatos mínimos de auditoría, como usuario, variante, consentimiento y modelo.
- La referencia de prenda proviene del catálogo empresarial validado; las imágenes existentes del catálogo pueden seguir guardadas en su almacenamiento normal.
- El probador es orientativo: no garantiza talla, color, textura, caída ni ajuste físico.

## Comprobación de extremo a extremo

Las pruebas unitarias del backend, la compilación de Flutter y los eventos simulados del puente no demuestran que Decart recibió cámara ni que devolvió video. La verificación completa requiere teléfono Android físico, conexión a Internet, cliente de una empresa de prueba, prenda superior activa con imagen HTTPS de al menos 512×512 en un host permitido, Decart habilitado y créditos disponibles.

Registrar como verificado solo si se comprueba en el teléfono: cámara local, sesión conectada, stream remoto, frame transformado visible, cambio de prenda y cierre de sesión sin cámara/conexión residual. Una sesión fallida debe registrar la etapa y el código del error, nunca el token, video o imagen.
