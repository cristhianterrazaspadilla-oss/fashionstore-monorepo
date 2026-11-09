# Manual local de uso y pruebas: FashionStore multitenant y PWA

**Actualizado:** 07/11/2026 (America/La_Paz)  
**Estado:** guía para pruebas locales; no es acta de aceptación.  
**Punto de partida técnico:** [ejecución del plan 46](47-ejecucion-plan-46.md).

## 1. Dictamen antes de probar

La base local aislada `fashionstore_manual_test` ya contiene empresas y cuentas de demostración. **Puedes probar el aislamiento multitenant desde la interfaz.** La instalación PWA completa, Stripe Test y Web Push conservan sus propias verificaciones pendientes.

| Área | Situación observada | Consecuencia para las pruebas |
|---|---|---|
| Backend y Angular | El checkpoint 47 registra 290 pruebas del Bloque B aprobadas, Angular 303/303 y build de producción aprobado. La suite heredada amplia tuvo 92 fallos y 97 aprobaciones; falta clasificar esos fallos y repetirla. | Se puede hacer una prueba exploratoria sobre el código local, sin declarar cierre funcional. |
| Flutter | `analyze` pasó; la suite Flutter no entregó resultado antes del timeout registrado en el checkpoint 47. | Los recorridos móviles y Decart requieren la prueba física pendiente y su propio resultado automatizado. |
| Cuentas de demostración | Hay una cuenta SUPERADMIN, tres administradores de empresas activas, un administrador pendiente, dos cajeros y cuatro cuentas cliente, todas en `fashionstore_manual_test`. | Se pueden recorrer permisos, aislamiento A/B y cambio de empresa desde la web. |
| Suscripciones de demostración | `fashionstore` y `demo-andes` tienen plan PROFESIONAL; `demo-oriente`, BASICO. `demo-pendiente` no tiene plan. Estas vigencias son **datos ficticios de prueba**, sin pago Stripe. | Permiten contrastar capacidades y bloqueo por falta de plan; no acreditan cobro SaaS. |
| Aislamiento RLS de PostgreSQL | No encontré `CREATE POLICY` ni `ENABLE ROW LEVEL SECURITY` en las migraciones y código del backend revisados. | Las pruebas de API/servicios no demuestran aislamiento RLS de la base de datos. No presentes este manual como auditoría de RLS. |
| Instalación PWA y apertura offline | Angular no declara `serviceWorker` en `angular.json`; `src/index.html` no enlaza un manifiesto; `public/custom-sw.js` implementa eventos de Web Push, no caché del shell de la aplicación. | No considerar aprobada la instalación como PWA ni la apertura en frío sin internet. La aplicación debe permanecer abierta para probar las colas locales actuales. |
| Integraciones | Stripe Test y Web Push dependen de claves y webhook configurados en el entorno local. | Sin esa configuración, probar solo los estados de interfaz; no registrar pago o push real como verificado. |

El sembrado nuevo se verificó con inicios de sesión HTTP reales, productos A/B separados y rechazo `403` al consultar una empresa ajena. La suite de Bloque B usa otros fixtures con hashes `no-usar`; sus usuarios no son las credenciales de esta guía.

## 2. Credenciales disponibles

Estas credenciales existen **solo** en `fashionstore_manual_test`; el sembrador de demostración las crea con hashes bcrypt:

| Rol | Empresa (código de acceso) | Correo | Contraseña |
|---|---|---|---|
| SUPERADMIN | Sin empresa | `superadmin.demo@example.com` | `SuperDemo2026!` |
| ADMINISTRADOR | `fashionstore` | `admin@fashionstore.com` | `Fashion123!` |
| ADMINISTRADOR | `demo-andes` | `admin.andes@example.com` | `AndesDemo2026!` |
| ADMINISTRADOR | `demo-oriente` | `admin.oriente@example.com` | `OrienteDemo2026!` |
| ADMINISTRADOR pendiente | `demo-pendiente` | `admin.pendiente@example.com` | `Pendiente2026!` |
| CAJERO | `demo-andes` | `cajero.andes@example.com` | `CajaAndes2026!` |
| CAJERO | `demo-oriente` | `cajero.oriente@example.com` | `CajaOriente2026!` |
| CLIENTE | `demo-andes` | `cliente.andes@example.com` | `ClienteAndes2026!` |
| CLIENTE | `demo-oriente` | `cliente.oriente@example.com` | `ClienteOriente2026!` |
| CLIENTE compartido | `demo-andes` | `cliente.compartido@example.com` | `ClienteDemo2026!` |
| CLIENTE compartido | `demo-oriente` | `cliente.compartido@example.com` | `ClienteDemo2026!` |

Para el correo compartido, escribe siempre el **código de empresa** en el login. Sin él, el backend responde `300` para solicitar la elección del tenant. El SUPERADMIN inicia sesión sin código. Las contraseñas son públicas de demostración y nunca deben emplearse en otra base. El sembrador conserva usuarios existentes y falla si su contraseña o rol no coincide; no restablece contraseñas silenciosamente.

## 3. Preparar un entorno aislado

La base creada se llama **`fashionstore_manual_test`** en el PostgreSQL local configurado en `backend/.env`. El `POSTGRES_DB` de ese archivo apunta ahora a la base demo para las pruebas web. La base oficial `fashionstore_db` no fue migrada ni poblada por este procedimiento. En pgAdmin busca `fashionstore_manual_test` en el mismo servidor local, normalmente `127.0.0.1:5432`.

Desde la raíz del repositorio, con PostgreSQL en marcha, puedes repetir el sembrado sin duplicar empresas, usuarios ni recepciones:

```powershell
& .\backend\venv\Scripts\python.exe .\backend\scripts\preparar_demo_tenants.py
```

El script toma la conexión local de `backend/.env` o de variables de entorno; exige host de loopback y opera únicamente sobre `fashionstore_manual_test`. Solo invoca el preparador de esquema cuando esa base no existe. Si la base ya existe, conserva sus filas y exige que Alembic esté en `0014_pago_ref_externa_unique`. No uses directamente `tests/preparar_base_pruebas.py` para repetir una base poblada: el SQL base de ese preparador restablece la revisión Alembic en ejecuciones posteriores.

### Iniciar backend

En una terminal nueva ejecuta desde la raíz:

```powershell
& .\backend\venv\Scripts\python.exe .\backend\scripts\iniciar_api_demo.py
```

Swagger queda en `http://127.0.0.1:8000/api/v1/docs`. Confirma allí que la API responde antes de abrir la web.

### Iniciar Angular

En otra terminal:

```powershell
Set-Location frontend-web
npm.cmd start -- --host 127.0.0.1 --port 4200
```

Abre `http://localhost:4200/`. El entorno Angular local apunta al backend `http://127.0.0.1:8000/api/v1`.

Si tenías la API abierta antes de cambiar `backend/.env`, reiníciala. Cierra la sesión web anterior y vuelve a entrar con una cuenta demo: el perfil de la sesión antigua conserva la empresa y sucursal previas. Los administradores y cajeros demo de empresas activas tienen una sucursal asignada; se verificó que el login devuelve `sucursal_id`.

## 4. Recorrido básico de uso

1. Entra a `/auth/login`.
2. Inicia sesión como `admin.andes@example.com`, código `demo-andes`, con la contraseña de la tabla. Comprueba que el perfil indica `ADMINISTRADOR` y la empresa correcta.
3. Abre catálogo y sucursales. Deben aparecer `Camiseta Andes Demo` (Bs 135 para la variante M) y `Centro Andes`/`Norte Andes`. El stock se cargó mediante recepciones con Kardex.
4. Cierra sesión y entra como `admin.oriente@example.com`, código `demo-oriente`. Debes ver `Camiseta Oriente Demo` (Bs 150 para la variante M) y solo `Centro Oriente`.
5. Usa las cuentas `CLIENTE` de cada empresa para recorrer catálogo y reservas. Usa las cuentas `CAJERO` para probar las pantallas de caja; una compra real o simulada debe tener su propia comprobación financiera.
6. Inicia sesión con `admin.pendiente@example.com`, código `demo-pendiente`. La cuenta existe, pero las operaciones que exigen plan deben rechazarse porque esta empresa no tiene suscripción. No cambies la base diaria para saltar esa regla.
7. Para probar la empresa heredada, entra como `admin@fashionstore.com`, código `fashionstore`. También tiene un producto y stock de demostración en esta base aislada.

## 5. Cómo funciona hoy el modo offline web

En el estado actual, “offline” significa **datos y operaciones locales de ciertos flujos**, no una aplicación web completa disponible después de cerrar el navegador:

- El catálogo puede guardar una instantánea por empresa en IndexedDB. La pantalla muestra conexión y permite usar **Descargar catálogo local** o **Actualizar copia local** mientras hay internet.
- La reserva offline necesita sesión iniciada, una copia local de catálogo y una referencia horaria obtenida del servidor antes de desconectarse. El horario de reserva se registra en Bolivia (`America/La_Paz`, UTC−04:00).
- **Limitación verificada del frontend:** la referencia horaria se solicita al intentar registrar una operación mientras aún hay conexión, pero las pantallas de reserva sólo llaman al registro offline después de desconectarse. Desde una sesión nueva no hay un paso de interfaz que precargue esa referencia. Si aparece «No cuentas con una referencia horaria válida», registra la reserva offline como bloqueada; no lo interpretes como fallo de IndexedDB ni como solicitud enviada.
- La acción **Guardar reserva fuera de línea** registra una solicitud local en cola. Es una solicitud pendiente; no confirma por sí sola una reserva ni aparta existencias en el servidor.
- Al volver internet, el servicio escucha el evento `online` e intenta sincronizar la cola. Revisa el resultado del servidor en la aplicación y en el detalle de la operación; una solicitud rechazada/conflictiva debe mostrarse como tal.
- Una compra guardada sin conexión no equivale a un pago. La compra queda pendiente hasta la conciliación del backend y la confirmación de Stripe que corresponda. No registres el mensaje local de “en cola” como venta pagada.
- La sesión privada tiene una ventana de 8 horas desde el último acceso online. Al vencer, la interfaz debe ocultar datos privados; las operaciones locales no se vuelven válidas por permanecer en IndexedDB.
- La persistencia de catálogo/cola depende del almacenamiento del sitio en el navegador. Cambiar de perfil del navegador crea otro almacenamiento; limpiar datos del sitio puede borrar datos locales pendientes.

### Prueba exploratoria de catálogo y reserva offline

Esta prueba requiere que el plan habilite la operación offline y que exista catálogo:

1. Inicia sesión con internet.
2. Abre **Catálogo** y descarga la copia local. Espera el indicador de éxito y revisa productos y disponibilidad.
3. En DevTools del navegador abre **Network** y selecciona **Offline** sin cerrar ni recargar la pestaña.
4. Confirma que la pantalla indica modo fuera de línea y muestra datos de la empresa de la sesión actual.
5. Con una cuenta CLIENTE, intenta registrar una reserva offline. Si la referencia horaria ya existe y sigue vigente, debe quedar **pendiente**. Si falta, registra el bloqueo indicado arriba; la interfaz requiere una corrección para precargarla mientras hay red.
6. Vuelve a **Online**. Espera la sincronización y confirma el resultado final que comunica el backend. Registra el ID/estado; no guardes JWT ni claves en capturas.
7. Si el navegador devuelve 403 por plan o no existe referencia horaria válida, registra el resultado y la precondición faltante; no lo cuentes como una reserva aprobada.

No cierres ni recargues la pestaña con la red deshabilitada como criterio de PWA: el shell no está configurado para caché offline en frío. Esa prueba debe quedar como pendiente/bloqueo de instalación offline.

## 6. Prueba manual multitenant: datos y pasos

### Recorrido A/B con datos ya creados

1. Inicia sesión como `superadmin.demo@example.com` sin código de empresa. Comprueba que puedes consultar las cuatro empresas de demostración y sus estados. La ruta de alta `POST /api/v1/empresas` requiere SUPERADMIN e `Idempotency-Key` UUID; una empresa recién creada queda `PENDIENTE_PLAN`.
   Desde Angular, el SUPERADMIN entra al **Panel de plataforma** (`/plataforma`). Allí ve tiendas, sucursales y planes, crea una tienda con su administrador inicial y asigna o renueva el plan. El [recorrido completo](50-panel-plataforma-superadmin.md) incluye el siguiente login como administrador de la tienda nueva.
2. Inicia sesión como admin de `demo-andes` y luego como admin de `demo-oriente`, siempre con el código explícito. Ambos catálogos usan el SKU `DEMO-CAMISETA-M-NEGRO`, pero sus productos, precios y existencias son propios: Andes Bs 135 y 11 unidades M; Oriente Bs 150 y 5 unidades M al sembrar.
3. Comprueba las sucursales: Andes tiene dos y Oriente una. En cada sesión revisa que catálogo, clientes, reservas, inventario e informes solo muestren datos de su empresa. Algunas pantallas estarán vacías hasta que generes operaciones manuales.
4. Como admin de Andes, toma el identificador de `demo-oriente` desde la cuenta SUPERADMIN e intenta consultar `GET /api/v1/empresas/{id}`. Se verificó que la API responde `403`. Repite con identificadores de operaciones que crees durante la prueba; el resultado esperado es `403`/`404` sin efectos sobre el otro tenant.
5. Inicia sesión con `cliente.compartido@example.com` y `ClienteDemo2026!` indicando `demo-andes`; repite con `demo-oriente`. Sin código, el backend responde `300` para elegir empresa. Comprueba que las sesiones y los datos privados no se mezclan.
6. Descarga la copia local del catálogo en A, cierra sesión y entra en B. La vista offline debe mostrar solo el snapshot de B; una cola local creada en A no debe enviarse como B.
7. Contrasta `demo-andes` (PROFESIONAL), `demo-oriente` (BASICO) y `demo-pendiente` (sin plan). Las suscripciones activas son fixtures locales, no pagos Stripe. Anota el resultado de la API, además de lo que muestra la interfaz.

No reutilices manualmente el token A ni alteres el `empresa_id` del JWT. Un intento de cambiar el contexto del token es una prueba negativa; nunca debe ser una forma de iniciar sesión como otro tenant.

## 7. Web Push, Stripe Test y PWA instalable

### Notificaciones Web Push

Tras login, Angular intenta suscribir el navegador al Web Push. Para que el recorrido externo funcione se necesita un contexto seguro (`localhost` o HTTPS), permiso de notificación, `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` configuradas en el backend, un service worker activo y un evento de notificación procesable. El código `public/custom-sw.js` muestra notificaciones push; no guarda el HTML/JS de Angular para apertura offline. Si el permiso se bloqueó, restablécelo en los ajustes del sitio y vuelve a probar.

Confirma en DevTools → **Application → Service Workers** que está registrado `/custom-sw.js`. Si no hay VAPID o el backend no puede enviar, marca Push como no configurado/no verificado; un mock automatizado no es prueba de entrega real.

### Stripe Test

No pegues claves secretas en este documento, capturas ni código frontend. El backend necesita `STRIPE_ENABLED=true`, una clave `sk_test_…` y un secreto de webhook de pruebas `whsec_…`; el frontend usa una clave publicable de pruebas. Para webhooks desde localhost se necesita un forwarder de Stripe CLI u otro endpoint de prueba autorizado. Si falta cualquiera de estos elementos, no se puede dar por probado el pago end-to-end. Nunca habilites claves live para esta guía.

### Instalación y apertura sin red

La instalación como PWA y la recarga offline no están verificadas y la configuración inspeccionada no contiene el manifiesto ni el service worker de caché del shell. Puedes usar la aplicación en navegador y probar las funciones IndexedDB de la sección 5, con la pestaña abierta. Para aceptar instalación/offline en frío primero hay que completar esa configuración y repetir en un build servido desde HTTPS/local seguro.

## 8. Registro de resultados

Por cada prueba anota:

| Campo | Qué registrar |
|---|---|
| ID | `MAN-01`, `MAN-02`, etc. |
| Código | Commit/HEAD de `backend`, `frontend-web` y, si aplica, `app-movil`; indicar si había cambios locales sin commit. |
| Entorno | Base `*_test`, navegador/versión, URL local, Online/Offline, Stripe Test o sin proveedor. Nunca guardar la URL completa de PostgreSQL. |
| Actor/tenant | Rol y código de empresa; no adjuntar contraseña ni JWT. |
| Pasos | Acción reproducible y datos ficticios utilizados. |
| Resultado | Esperado, observado, estado `PASA` / `FALLA` / `BLOQUEADO` y error HTTP cuando corresponda. |
| Evidencia | Captura sanitizada; no incluir datos personales reales, claves, tarjetas reales, cookies o encabezados de autorización. |

## 9. Criterio de preparación

**Sí puedes empezar** con login, permisos y aislamiento entre varios tenants en `fashionstore_manual_test`. La base ya tiene cuatro empresas, cuentas por rol, sucursales, catálogo y stock con Kardex.  
**Aún no se puede afirmar** que el proyecto pasó toda la prueba manual: falta comprobar el flujo completo desde el navegador, la aplicación no ofrece caché de shell para instalación/apertura offline, Stripe/Web Push dependen de configuración externa y siguen pendientes las puertas automáticas/manuales anotadas en el checkpoint 47.

Fuentes inspeccionadas: `backend/scripts/preparar_demo_tenants.py`, `backend/scripts/iniciar_api_demo.py`, `backend/tests/BASE_DE_PRUEBAS.md`, `backend/tests/preparar_base_pruebas.py`, `backend/tests_segundo_parcial_bloque_b/conftest.py`, `backend/app/core/modules/identidad_empresas/routers/empresas.py`, `backend/app/core/modules/identidad_empresas/services/autenticacion_service.py`, `frontend-web/angular.json`, `frontend-web/src/index.html`, `frontend-web/public/custom-sw.js` y `frontend-web/src/app/core/services/offline-store.service.ts`.
