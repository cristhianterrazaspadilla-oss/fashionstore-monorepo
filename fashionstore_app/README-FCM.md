# Notificaciones Push FCM — FashionStore App Móvil

Consulta la documentación técnica completa para auditoría en:
[GUIA_FCM_ANDROID_AUDITORIA.md](GUIA_FCM_ANDROID_AUDITORIA.md)

### Puntos Clave:
1. **Dependencias Oficiales FlutterFire:**
   - `firebase_core: 5.1.0` y `firebase_messaging: 17.0.1` en `pubspec.yaml` (resueltas desde caché local / offline).
2. **Configuración Android:**
   - Requiere `app-movil/android/app/google-services.json` (no commiteado en el repositorio por seguridad de credenciales).
   - El paquete Firebase Android debe coincidir con `applicationId` en `android/app/build.gradle.kts`.
   - `com.google.gms.google-services` está declarado en `android/settings.gradle.kts` y aplicado en `android/app/build.gradle.kts`. No copiar manualmente el Firebase BoM: `firebase_core` y `firebase_messaging` resuelven las dependencias nativas.
   - Tras clonar, colocar de nuevo `google-services.json` antes de compilar el APK.
3. **Permisos Android en `AndroidManifest.xml`:**
   - `POST_NOTIFICATIONS` (Android 13+ / API 33+), `INTERNET` y `WAKE_LOCK` declarados en el manifiesto principal.
   - El servicio de segundo plano es administrado automáticamente por el plugin oficial (`FlutterFirebaseMessagingService` via merge de manifiestos), evitando entradas manuales de clases abstractas.
4. **Ciclo de Vida Reactivo y Defensivo:**
   - `NativePlatformFcmAdapter`: Conecta con `Firebase.initializeApp()`, `FirebaseMessaging.instance`, `requestPermission()`, `getToken()`, `onTokenRefresh`, `FirebaseMessaging.onMessage`, `FirebaseMessaging.onBackgroundMessage` (con handler `@pragma('vm:entry-point')` estático) y `getInitialMessage()`.
   - Fallback limpio y seguro a `EstadoFcm.noConfigurado` en CI, entornos de desarrollo o desktop sin crashear.
   - Inyección en tiempo de ejecución: Permite pasar `FcmAdapter` directamente en el constructor de `NotificacionMovilService({ApiClient? api, FcmAdapter? adapter})`.
   - `SimulatedFcmAdapter` como doble de prueba para ejecución autónoma sin emulador ni hardware.
   - Bandeja local offline (`bandejaOffline`) sincronizada con backend `/api/v1/notificaciones/bandeja`.

### Credenciales del servidor

El JSON de **cuenta de servicio** descargado de Firebase es distinto de
`google-services.json`. Se guarda fuera de Git y solo lo utiliza FastAPI:

- Local: `GOOGLE_APPLICATION_CREDENTIALS` en `backend/.env` apunta a la ruta
  absoluta del JSON. El backend ahora lee esa variable también desde `.env`.
- Render: subir el JSON en **Environment → Secret Files** con el nombre
  `firebase-service-account.json` y definir
  `GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/firebase-service-account.json`.
  Como alternativa, definir `FCM_SERVICE_ACCOUNT_JSON` con el contenido completo.
- Activar `EXPIRACION_JOB_ACTIVO=true` en un solo proceso del backend para
  despachar el outbox de notificaciones cada 30 segundos.

No colocar la cuenta de servicio en Flutter, frontend, ni GitHub. El envío
real se comprueba después de instalar el APK en un Android físico, iniciar
sesión y registrar el token FCM con el backend.
