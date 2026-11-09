# H04 / H05: caja fisica offline

Alcance: contado en efectivo con habilitacion online previa. No modifica checkout,
Stripe, saldo, instalacion SQL, CU27 ni manifest/cache PWA.

## Cambios

- `caja-local.store.ts` es la fuente durable: origen empresa/usuario/dispositivo/turno,
  cuerpo inmutable, secuencia, cupos, comprobante y estado. La transaccion IndexedDB
  incluye lectura del saldo, validacion, consumo y documentos. Las transacciones
  readwrite sobre los mismos stores serializan tambien otras conexiones/pestanas.
- El mismo UUID/cuerpo devuelve el registro previo. Otro cuerpo/origen es conflicto.
  Una respuesta perdida conserva el pendiente. Solo REGISTRADA_CENTRAL lo confirma;
  el resultado central y el comprobante se conservan, sin eliminar ventas.
- La sincronizacion toma el turno y cuerpo persistidos de cada operacion, incluso
  sin turno activo o con uno nuevo. Otra sesion no puede listarlos ni enviarlos.
- La recuperacion de otro titular es una accion explicita de supervisor: consulta
  autorizada online del turno original y filtro por sus tres campos de origen.
  No permite nuevas ventas usando la autorizacion del titular anterior.
- El cierre local se bloquea mientras existan operaciones sin resolver. La caducidad
  no devuelve cupos ni borra historial. Un refresco no reduce consumo/mermas/liberaciones.

La habilitacion mantiene inicio/vence originales y limita nuevas ventas a ocho horas.
Una consulta GET nueva proporciona `empresa_id` y `hora_central_en`; un POST idempotente
antiguo no se usa para renovar el reloj. Se guarda desfase y ultimo reloj observado,
ademas de respetar la ventana de privacidad ya existente en AuthService.
Esto detecta retrocesos observados, pero no convierte el dispositivo en un reloj
seguro: manipular almacenamiento/reloj o revocar permisos mientras no hay red no
puede resolverse con certeza absoluta. El servidor revalida al sincronizar.

## Migracion v1 -> v2

Se conserva `FashionStoreCajaDB`; se agrega el store `recuperacion`. Los registros v1
sin sobre de origen/cuerpo quedan RECUPERACION_REQUERIDA y no se envian. Las claves
localStorage antiguas se copian como texto, incluso JSON danado, sin borrarlas ni
sobrescribir el primer respaldo. No se atribuyen al usuario actual. Un legado ligado
a un turno impide nuevas ventas de ese turno hasta conciliarlo. Los pendientes de
origen indeterminado bloquean el cierre por precaucion.

El boton de recuperacion supervisada procesa operaciones con origen verificable;
los registros ambiguos requieren revisar evidencia del origen y resultado central.
Este bloque no automatiza su reasignacion ni los descarta. No borrar datos del sitio
ni usar una version antigua del cliente como mecanismo de recuperacion.

## Pruebas ejecutadas

```powershell
# Desde fashionstore_frontend, Node 24 y Chrome local.
# TYPESCRIPT_LIB apunta a typescript.js de una instalacion LOCAL disponible.
$env:TYPESCRIPT_LIB = (Resolve-Path 'node_modules/typescript/lib/typescript.js').Path
$env:CHROME_BIN = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
node tests_aislados_caja/indexeddb.browser.mjs
```

Resultado de esta entrega: **14 casos aprobados**, IndexedDB nativo en Chrome,
incluidas dos pestañas reales. Se usa perfil temporal vacio, servidor loopback,
proxy sin salida y bloqueo HTTPS; no carga la aplicacion ni contacta la API.
El ejecutor transpila en memoria con TypeScript. Si faltan dependencias del repo,
puede indicarse TYPESCRIPT_LIB de otra instalacion local. En esta maquina se uso
la copia local de TypeScript disponible en el proyecto Telemmedicina-SDD.
Los flags sin sandbox/single-process son exclusivos de este perfil sintetico de
pruebas del entorno Windows; no deben trasladarse al navegador de uso habitual.

Doce casos prueban almacenamiento (aislamiento, reinicio, turnos anteriores,
idempotencia/conflicto, vencimiento/conciliacion, concurrencia, rollback,
insuficiencia, refresco, respuesta perdida, reloj, migracion y supervision,
agrupados en doce casos). Otro verifica dos pestañas y otro el CajaService real
con DI/RxJS y transporte HTTP sustituidos. No son pruebas de renderizado Angular
ni de un backend PostgreSQL real. El store tambien paso TypeScript estricto sin emitir.

Se adaptaron `caja.service.spec.ts` y `caja.component.spec.ts`. Su ejecucion Angular/Karma
queda pendiente: `npm ci --offline --ignore-scripts --no-audit --no-fund` fallo por
ENOTCACHED de update-browserslist-db-1.3.2.tgz; no se descargaron paquetes ni se
cambiaron manifiestos/lockfiles. No declarar compilada la aplicacion completa.

## Comprobacion manual posterior

Usar solo una instalacion de pruebas aislada, dos empresas A/B, cajero A, otro
usuario, supervisor autorizado y cupos sinteticos; nunca la base compartida.

1. Abrir la web con red, autenticar cajero A y habilitar turno T1 con una unidad.
   Confirmar la consulta GET del turno y los dos metadatos nuevos del backend.
2. Mantener la pestaña cargada, desconectar y cobrar efectivo. Debe existir un solo
   comprobante, un pendiente y saldo cero. Otra venta debe rechazarse.
3. Con cupo nuevo de una unidad en una fixture aislada, intentar dos cobros desde dos
   pestañas. Solo uno puede consumirla. El UUID ya guardado conserva cuerpo y secuencia.
4. Volver a cargar con red (el arranque en frio sin red depende aun de la PWA).
   Verificar recuperacion. Cambiar a otro usuario/empresa: no debe ver ni enviar T1.
   Volver a A: el pendiente reaparece sin perder su origen.
5. Con una fixture que permita otro turno T2, mantener un pendiente T1 y sincronizar:
   la URL debe seguir siendo `/cajas/turnos/T1/ventas`, con el UUID/cuerpo originales.
   El backend actual puede impedir abrir T2 en el mismo dispositivo mientras T1
   siga incompatible; esto no autoriza a saltar esa regla.
6. Simular perdida de respuesta en el transporte de pruebas despues de aceptar la
   venta. Reintentar: un pago/Kardex en central y resultado durable en el cliente.
7. Probar vencimiento y CONCILIACION con reloj/fixture aislados: bloquear ventas
   nuevas, conservar pendientes y no devolver cupos. Un cierre con pendientes se rechaza.
8. Iniciar supervisor, indicar T1 y recuperar deliberadamente. Debe conservar titular
   y dispositivo originales. Un supervisor B no puede recuperar T1 de A.

Pendientes: renderizado/build Angular, pruebas del backend bajo PostgreSQL aislado
(bloqueos/constraints), dispositivos reales y PWA/arranque offline. No se probaron
pagos electronicos ni se declaran corregidos los demas hallazgos.
