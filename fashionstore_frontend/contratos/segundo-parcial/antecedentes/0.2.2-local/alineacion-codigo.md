# Alineación estática con los tres proyectos — primera presentación

**Inspección estática inicial:** 24/10/2026; contraste puntual adicional de reservas, adelantos, JWT y ciudades: 25/10/2026. Se inspeccionaron `fashionstore_backend` (`c4baf15`), `fashionstore_frontend` (`4d3a83b`) y `fashionstore_app` (`a4a42d4`), con los cambios documentales locales preservados. No se ejecutaron pruebas, migraciones, aplicaciones ni servicios externos. Los hallazgos siguientes describen código; las reglas acordadas siguen en [casos-de-uso.md](casos-de-uso.md), [reglas-aprobadas.md](reglas-aprobadas.md) e [interfaz.json](interfaz.json). Una ruta propuesta nunca se presenta como OpenAPI existente. Los códigos actuales se relacionan con los anteriores mediante [equivalencias-cu.md](equivalencias-cu.md).

Rutas de archivos: `B/` = raíz de `fashionstore_backend/`, `W/` = `fashionstore_frontend/`, `M/` = `fashionstore_app/`. Las rutas HTTP mostradas son relativas a `/api/v1`.

## CU01 — Registrar empresa contratante

| Dimensión | Contraste |
|---|---|
| Existente | B: `app/core/modules/identidad_empresas/models.py` define `Usuario`, `Rol`, `Cliente` y `Empleado`; `app/core/modules/organizacion/models.py` define `Sucursal`. W: `src/app/features/identidad_empresas/usuarios/` administra usuarios. M: solo identidad de cliente. |
| Adaptación necesaria | Añadir ámbito empresarial y de plataforma, alta consistente de empresa y administrador inicial, autorización efectiva y aislamiento de referencias. El paquete dueño propuesto es `identidad_empresas`; `organizacion` aporta sucursales. |
| Faltante | No hay `Empresa`, administrador de plataforma distinguido ni `POST /empresas`. Ningún `empresa_id` atraviesa los modelos actuales. El alta y la migración tenant son diseño, no funcionalidad existente. |
| Archivos implicados | B: `app/core/modules/identidad_empresas/{models.py,schemas.py,routers/,services/}`, `app/core/dependencias.py`, `app/db/modelos.py`, `app/api/v1/api.py`, `alembic/versions/`. W: `src/app/features/identidad_empresas/`, `src/app/app.routes.ts`. M: `lib/core/session/` para consumir el ámbito, sin alta administrativa. |

## CU02 — Administrar suscripción de empresa

| Dimensión | Contraste |
|---|---|
| Existente | B: `Sucursal` tiene estado activo y parámetros de tarifa/adelanto; `SucursalService` crea y administra sucursales. W: pantalla `features/organizacion/sucursales/`. M: `SucursalService.listar` consulta sucursales. |
| Adaptación necesaria | Validar capacidad y vigencia del plan en creación/activación de sucursal y nuevas operaciones, con administración de plataforma y consulta del plan propio. Coordinar con CU01/CU15 y operaciones de reservas. |
| Faltante | No hay entidades de plan, suscripción, historial, gracia, límite por empresa ni `POST /empresas/{empresa_id}/suscripciones` o `GET /empresas/mi-plan`. Las cantidades Básico 2/Profesional 10 son regla acordada, no dato de configuración actual. |
| Archivos implicados | B: `app/core/modules/identidad_empresas/`, `app/core/modules/organizacion/services/sucursal_service.py`, `app/core/modules/reservas_traslados/services/reserva_service.py`, `alembic/versions/`. W: `features/identidad_empresas/` y `organizacion/`. M: sesión/cuenta para mostrar capacidades, sin administración. |

## CU03 — Descargar catálogo para consulta offline

| Dimensión | Contraste |
|---|---|
| Existente | B: `GET /productos`, `GET /catalogo/productos`, `GET /catalogo/filtros-opciones` y `GET /variantes/{id}/disponibilidad` ofrecen consulta online; `catalogo` posee productos, variantes y maestros. W: `CatalogoService.consultarCatalogo`. M: `CatalogoService.listarProductos` y detalle/disponibilidad. |
| Adaptación necesaria | Definir descarga versionada y consistente por empresa/ámbito, fecha y disponibilidad pública conocida; persistir copia válida en IndexedDB y SQLite y conservarla ante falla. El enlace `/tienda/{empresa_codigo}` es navegación propuesta para identificar catálogo, no API existente ni autorización. La consulta pública actual de productos no resuelve empresa y `GET /sucursales` exige autenticación. |
| Faltante | No hay `GET /catalogo/descarga`, versión de descarga, almacén IndexedDB de negocio, SQLite ni flujo de descarga/reapertura sin red. W no registra Service Worker ni manifest de la aplicación Angular. `M/web/manifest.json` no es el manifest Angular. |
| Archivos implicados | B: `app/core/modules/catalogo/{routers/catalogo.py,services/catalogo_service.py,schemas.py,models.py}`, `inventario/`, `alembic/versions/`. W: `features/catalogo/`, `src/app/app.config.ts`, `angular.json`, `src/index.html`. M: `lib/features/catalogo/`, `lib/core/`, `pubspec.yaml`. |

## CU04 — Registrar reserva offline

| Dimensión | Contraste |
|---|---|
| Existente | B: `POST /reservas` y `ReservaService.crear` usan `Idempotency-Key`, transacción y bloqueo de inventario para una reserva **online**. W: `ReservaTrasladoService.crearReserva` envía HTTP. M: `ReservaService.crear` envía HTTP; `BolsaStore` guarda líneas solo en memoria. |
| Adaptación necesaria | Conservar ese servicio como dueño de la aceptación central, integrando una operación durable con `operacion_id`, `creada_local_en`, usuario/empresa, validación temporal, respuesta almacenada y plazo desde creación local. `ReservaService.crear` calcula hoy `fecha_visita + 1 día` cuando se envía visita: debe separar visita de vencimiento. Clientes deben guardar solicitud, detalle y resultado antes de declarar éxito local. |
| Faltante | No hay cola durable, `POST /sincronizacion/operaciones` ni `GET /sincronizacion/operaciones/{operacion_id}`, referencia horaria, estados `CONFLICTO`/`TIEMPO_INCOHERENTE` implementados ni persistencia de reservas en IndexedDB/SQLite. La idempotencia actual de HTTP online no sustituye el protocolo offline. |
| Archivos implicados | B: `app/core/modules/reservas_traslados/{services/reserva_service.py,routers/reservas.py,schemas.py,models.py}`, `inventario/repositories/inventario_repository.py`, `app/core/idempotencia*.py`, `app/core/reloj.py`, `alembic/versions/`. W: `features/reservas_traslados/`, `core/`. M: `features/reservas_traslados/reservas/{bolsa_store.dart,bolsa_screen.dart}`, `services/reserva_service.dart`, `core/`. |

## CU13 — Registrarse e iniciar sesión por empresa

| Dimensión | Contraste |
|---|---|
| Existente | B: `POST /clientes` (`registrarCliente`), `POST /sesion` (`iniciarSesion`), JWT y `require_roles`; `app/core/config.py` declara 24 h por defecto para JWT. W: `AuthService` conserva token/perfil en `localStorage`; guarda e interceptor Bearer. M: `AuthService` y `SessionManager` conservan sesión en `SharedPreferences` durante 24 h. |
| Adaptación necesaria | Añadir selección/contexto de empresa al registro/login, unicidad de correo dentro de empresa, rol/ámbito en sesión y autorización backend por recurso. El enlace público propuesto `/tienda/{empresa_codigo}` debe llevar contexto coherente sin reutilizar sesión ajena. Separar almacenamiento local por usuario/empresa y aplicar ventana privada de 8 h desde último login online sin borrar pendientes/resultados; no exige acortar el JWT de 24 h. |
| Faltante | `RegistroClienteDTO`, `LoginDTO`, `ClientePerfilDTO` y los cuerpos enviados por W/M no contienen empresa; `Usuario.correo_electronico` es único global. No hay rol de administrador de plataforma ni 8 h de acceso privado; `localStorage` web no impone expiración equivalente. |
| Archivos implicados | B: `app/core/modules/identidad_empresas/{models.py,schemas.py,routers/clientes.py,routers/sesion.py,services/}`, `app/core/{dependencias.py,permisos.py,seguridad.py}`, migraciones. W: `features/identidad_empresas/`, `core/{guards,interceptors}/`. M: `features/identidad_empresas/`, `core/{network,session}/`. |

## CU15 — Gestionar ciudades, sucursales y tarifas

| Dimensión | Contraste |
|---|---|
| Existente | B: `GET/POST /ciudades`, `GET/POST /sucursales`, configuración de tarifas y adelanto; `SucursalService` y modelos `Ciudad`/`Sucursal`. W: `OrganizacionService` y pantalla de sucursales. M: `SucursalService.listar` para selección, sin administración. |
| Adaptación necesaria | Mantener ciudades como referencia global administrada solo por plataforma; la empresa puede consultarlas/seleccionarlas, mientras sucursales y tarifas son propias. Separar rol de administrador de plataforma y empresarial; validar plan/límite al activar y compromisos al desactivar. |
| Faltante | `Sucursal` no tiene `empresa_id`; `registrarCiudad` en `routers/ciudades.py` usa `require_roles("ADMINISTRADOR")` sin distinguir plataforma de empresa, y `listarCiudades` exige usuario autenticado. No hay permiso de plataforma separado ni validación de plan para sucursales. La propuesta de CU15 no queda cumplida por las rutas actuales. |
| Archivos implicados | B: `app/core/modules/organizacion/{models.py,schemas.py,routers/ciudades.py,routers/sucursales.py,services/sucursal_service.py}`, `app/core/dependencias.py`, migraciones. W: `features/organizacion/`, `app.routes.ts`. M: `features/organizacion/services/sucursal_service.dart`. |

## CU16 — Consultar catálogo de prendas

| Dimensión | Contraste |
|---|---|
| Existente | B: `ProductoService`/`CatalogoService` implementan filtros y detalle, variantes y disponibilidad por sucursal. W: `CatalogoService.consultarCatalogo` y pantalla `catalogo`; M: `CatalogoService` consulta productos, variantes, filtros y disponibilidad online. |
| Adaptación necesaria | Acotar resultados públicos a la empresa identificada por el enlace propuesto, sin filtrar datos privados; para funciones privadas validar identidad/empresa en backend. Leer copia de CU03 sin red, indicando fecha, origen y disponibilidad conocida. Preservar filtros y rutas online, sin renombrarlas por numeración académica. |
| Faltante | Los modelos de producto/variante y consultas actuales carecen de ámbito empresarial; los clientes no tienen copia de catálogo durable ni selector de fuente local. No existe consulta offline verificable. |
| Archivos implicados | B: `app/core/modules/catalogo/{models.py,schemas.py,routers/productos.py,routers/catalogo.py,services/catalogo_service.py}`, `inventario/`, migraciones. W: `features/catalogo/{catalogo/,services/,models/}`. M: `features/catalogo/{catalogo/,services/,models/}` y almacenamiento SQLite previsto. |

## CU18 — Gestionar reservas de prendas

| Dimensión | Contraste |
|---|---|
| Existente | B: `ReservaService.crear`, `listar`, `obtener`, `cancelar`, `expirarVencidas` y rutas `POST/GET /reservas`, `PATCH /reservas/{id}/cancelar`; inventario se bloquea y se registra Kardex. `crear` usa `fecha_visita + 1 día` si se proporciona visita, y `PagoService` extiende desde `reserva.fecha_creacion`. W: `ReservaTrasladoService`; M: `ReservaService` y pantallas de reservas. |
| Adaptación necesaria | Restringir por empresa además de propietario/sucursal; compartir aceptación central con CU04. Vencimiento online: creación central +24 h; offline aceptada: creación local original +24 h; adelanto confirmado online a tiempo: +72 h desde el mismo origen. Revisar creación, adelantos, cancelación, expiración automática y fechas presentadas en clientes. Extender DTO/persistencia sin recalcular datos históricos en esta revisión. |
| Faltante | No hay empresa en `Reserva`, `ReservaCrearDTO` ni respuesta; las reservas online aceptadas desde CU04 aún no existen. La vista móvil de estado local no prueba sincronización. |
| Archivos implicados | B: `app/core/modules/reservas_traslados/{models.py,schemas.py,routers/reservas.py,services/reserva_service.py}`, `inventario/`, `app/core/tareas.py`, migraciones. W: `features/reservas_traslados/reservas/`. M: `features/reservas_traslados/reservas/`, `services/reserva_service.dart`. |

## Dependencias, decisiones y estado de verificación

- **Bloque A precede a la integración B:** sesión/empresa/sucursal, rol de plataforma, ámbito del catálogo público y permisos deben tener una interfaz mínima acordada. B puede preparar pantallas y almacenamiento con dobles identificados mientras tanto.
- **Rutas existentes frente a propuestas:** las actuales están montadas en `B/app/api/v1/api.py`; `interfaz.json` enumera rutas futuras. Los DTO actuales de reserva usan `sucursal_destino_id`/`fecha_visita` y `Idempotency-Key`; el comando offline propuesto usa envoltorio con `empresa_id`, `operacion_id`, `creada_local_en` y datos `sucursal_id`/`visita_en`. Es un adaptador por diseñar, no un simple cambio de nombre de campos.
- **Migración:** `B/alembic/versions/` llega a `0005_ciclo3_correcciones`. `B/app/main.py` ejecuta DDL de restricciones en `lifespan()` al arrancar; una prueba de aplicación también exige base aislada. `plan-migracion-db.md` contiene cifras históricas de 18/10, no conteos verificados en esta revisión.
- **Decisiones cerradas el 25/10/2026:** enlace público empresarial de navegación propuesto `/tienda/{empresa_codigo}`; ciudades globales administradas por plataforma; asignación administrativa de Profesional a la empresa heredada si se confirman tres sucursales activas. El enlace no es una ruta/API constatada ni permiso privado. Permanecen pendientes los **datos operativos**, no estas reglas: medir sucursales reales, registrar cualquier diferencia y capturar explícitamente fechas de inicio/vencimiento antes de aplicar la asignación. Básico sigue en 2 y Profesional en 10; no se desactivan sucursales ni se crea una suscripción ficticia.
- **Vencimiento y privacidad:** se contrastaron además `B/app/core/modules/reservas_traslados/services/reserva_service.py:209–213`, `B/app/core/modules/ventas_pagos/services/pago_service.py:155`, `B/app/core/config.py:23` y `M/lib/core/session/session_manager.dart`. Los dos primeros requieren adaptación conjunta del origen de vencimiento; el JWT declarado de 24 h y la sesión móvil actual de 24 h no cumplen por sí solos la ventana privada offline de 8 h. Esta última es independiente y no autoriza sincronizar con token vencido.
- **Verificación:** todo lo anterior es lectura estática. No hay pruebas ejecutadas ni evidencia de funcionamiento offline, multitenant o de los endpoints nuevos.
