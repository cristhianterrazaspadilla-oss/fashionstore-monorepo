// node --test src/app/features/posventa/reembolsos/reembolsos.integration.test.cjs
// Servicio/controlador/store reales y RxJS instalado. HTTP y Angular simulados.
// Sin renderizado, .env, red, BD ni proveedores; no emite archivos compilados.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const ts = require(process.env.TYPESCRIPT_LIB || 'C:/Users/hp/Desktop/si2G3-5/Telemmedicina-SDD/frontend_Telemedicina/node_modules/typescript/lib/typescript.js');
const rx = require(process.env.RXJS_LIB || 'C:/Users/hp/Desktop/si2G3-5/Telemmedicina-SDD/frontend_Telemedicina/node_modules/rxjs/dist/cjs/index.js');
const root = path.resolve(__dirname, '..');
const ids = Array.from({ length: 8 }, (_, i) => '10000000-0000-4000-8000-' + String(i + 1).padStart(12, '0'));
const [id, empresa, cliente, venta, otro, empresaB, clienteB] = ids;
const detalle = (extra = {}) => ({ id, empresa_id: empresa, cliente_id: cliente,
  origen_tipo: 'VENTA', origen_id: venta, motivo_codigo: 'DEFECTO_FABRICA',
  estado: 'PENDIENTE_AUTORIZACION', monto_bob: '180.00', revision: 1,
  creada_en: '2026-11-04T13:00:00Z', componentes: [
    { id: otro, medio: 'STRIPE', monto_bob: '100.00', estado: 'PENDIENTE' },
    { id: venta, medio: 'SALDO', monto_bob: '80.00', estado: 'PENDIENTE' }
  ], ...extra });
const solicitud = (extra = {}) => ({ origen_tipo: 'VENTA', origen_id: venta, motivo_codigo: 'DEFECTO_FABRICA', ...extra });
class StorageMemoria {
  datos = new Map();
  getItem(k) { return this.datos.get(k) ?? null; }
  setItem(k, v) { this.datos.set(k, v); }
  removeItem(k) { this.datos.delete(k); }
}

function entorno(storage = new StorageMemoria()) {
  const auth = { usuario: { empresa_id: empresa, usuario_id: cliente, id: cliente, rol: 'CLIENTE' },
    obtenerUsuarioActual() { return this.usuario; } };
  const llamadas = [];
  const http = {
    responder: c => rx.of(c.metodo === 'GET' && c.url.endsWith('/mios') ? [detalle()] : detalle()),
    get(url) { return rx.defer(() => { const c = { metodo: 'GET', url }; llamadas.push(c); return http.responder(c); }); },
    post(url, cuerpo, opciones) { return rx.defer(() => {
      const c = { metodo: 'POST', url, cuerpo: structuredClone(cuerpo), clave: opciones.headers.get('Idempotency-Key') };
      llamadas.push(c); return http.responder(c);
    }); }
  };
  const cache = new Map();
  const stubs = {
    '@angular/core': { Injectable: () => x => x, Component: () => x => x, inject: () => ({}) },
    '@angular/common': {}, '@angular/forms': {}, '@angular/router': {},
    '@angular/core/rxjs-interop': { takeUntilDestroyed: () => x => x },
    '@angular/common/http': { HttpHeaders: class { constructor(h) { this.h = h; } get(k) { return this.h[k]; } } }, rxjs: rx
  };
  function cargar(archivo) {
    const nombre = path.resolve(archivo);
    if (cache.has(nombre)) return cache.get(nombre);
    const module = { exports: {} }; cache.set(nombre, module.exports);
    const js = ts.transpileModule(fs.readFileSync(nombre, 'utf8'), {
      compilerOptions: { experimentalDecorators: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }
    }).outputText;
    const resolver = requerido => {
      if (requerido in stubs) return stubs[requerido];
      if (requerido.includes('/environments/environment')) return { environment: { apiUrl: '/api/v1' } };
      if (requerido.endsWith('/auth.service')) return { AuthService: class {} };
      if (requerido.endsWith('/moneda.util')) return { formatearBs: String, formatearFechaHora: String };
      if (requerido.endsWith('/error-handler.util')) return { formatearErrorApi: (_e, mensaje) => mensaje };
      if (requerido.endsWith('/confirm-dialog.component')) return { ConfirmDialogComponent: class {} };
      if (requerido.startsWith('.')) return cargar(path.resolve(path.dirname(nombre), requerido + '.ts'));
      throw new Error('Import no permitido: ' + requerido);
    };
    vm.runInNewContext(js, { module, exports: module.exports, require: resolver, crypto: webcrypto,
      TextEncoder, Uint8Array, structuredClone, localStorage: storage }, { filename: nombre });
    return module.exports;
  }
  const { ReembolsoService } = cargar(path.join(root, 'services/reembolso.service.ts'));
  const { ReembolsosComponent } = cargar(path.join(root, 'reembolsos/reembolsos.component.ts'));
  const nuevoServicio = () => new ReembolsoService(http, auth);
  return { auth, llamadas, http, storage, nuevoServicio, servicio: nuevoServicio(), componente: s => new ReembolsosComponent(s, auth) };
}
const recibir = rx.firstValueFrom;
const perdida = () => rx.throwError(() => new Error('Respuesta perdida simulada'));
const posts = e => e.llamadas.filter(c => c.metodo === 'POST');

test('listado GET /mios y consulta individual usan campos reales y multiples componentes', async () => {
  const e = entorno(); const r = await recibir(e.servicio.listarMios());
  assert.equal(e.llamadas[0].url, '/api/v1/reembolsos/mios');
  assert.equal(r[0].id, id); assert.equal(r[0].creada_en, detalle().creada_en); assert.equal(r[0].componentes.length, 2);
  await recibir(e.servicio.consultar(id)); assert.equal(e.llamadas[1].url, '/api/v1/reembolsos/' + id);
  await assert.rejects(recibir(e.servicio.consultar('REM-1'))); assert.equal(e.llamadas.length, 2);
});

test('numero de venta se resuelve con GET autorizado antes de POST con UUID', async () => {
  const e = entorno(); e.http.responder = c => rx.of(c.metodo === 'GET' ? { id: venta } : detalle());
  await recibir(e.servicio.solicitar(solicitud({ origen_id: ' VNT-0001 ' })));
  assert.equal(e.llamadas[0].url, '/api/v1/ventas/VNT-0001');
  assert.equal(posts(e)[0].url, '/api/v1/reembolsos'); assert.equal(posts(e)[0].cuerpo.origen_id, venta);
});

test('venta rechazada/sin UUID y numeros de otros tipos nunca producen POST', async () => {
  const e = entorno(); e.http.responder = perdida;
  await assert.rejects(recibir(e.servicio.solicitar(solicitud({ origen_id: 'VNT-1' }))));
  e.http.responder = () => rx.of({ numero: 'VNT-1' });
  await assert.rejects(recibir(e.servicio.solicitar(solicitud({ origen_id: 'VNT-1' }))));
  for (const tipo of ['PEDIDO', 'CAMBIO', 'DEVOLUCION'])
    await assert.rejects(recibir(e.servicio.solicitar(solicitud({ origen_tipo: tipo, origen_id: 'COD-1' }))));
  assert.equal(posts(e).length, 0);
});

test('UUID directo evita GET y congela el cuerpo antes de suscribirse', async () => {
  const e = entorno(); const dto = solicitud(); const obs = e.servicio.solicitar(dto);
  dto.motivo_codigo = 'CAMBIADO'; await recibir(obs);
  assert.equal(e.llamadas.length, 1); assert.equal(posts(e)[0].cuerpo.motivo_codigo, 'DEFECTO_FABRICA');
});

test('solicitud perdida conserva clave tras recarga; otro contenido usa otra y no se guarda el motivo', async () => {
  const e = entorno(); e.http.responder = perdida;
  await assert.rejects(recibir(e.servicio.solicitar(solicitud())));
  await assert.rejects(recibir(e.nuevoServicio().solicitar(solicitud())));
  await assert.rejects(recibir(e.servicio.solicitar(solicitud({ motivo_codigo: 'OTRO' }))));
  assert.equal(posts(e)[0].clave, posts(e)[1].clave); assert.notEqual(posts(e)[0].clave, posts(e)[2].clave);
  assert.ok(!JSON.stringify([...e.storage.datos]).includes('DEFECTO_FABRICA'));
});

test('ejecucion perdida y recarga reutilizan ambos UUID sin repetir efecto simulado', async () => {
  const storage = new StorageMemoria(); let efectos = 0; const aceptados = new Set(); const e = entorno(storage);
  e.http.responder = c => {
    assert.match(c.cuerpo.clave_ejecucion, /^[0-9a-f-]{36}$/);
    if (!aceptados.has(c.cuerpo.clave_ejecucion)) { aceptados.add(c.cuerpo.clave_ejecucion); efectos++; }
    return perdida();
  };
  await assert.rejects(recibir(e.servicio.ejecutar(id)));
  const recarga = entorno(storage); recarga.http.responder = c => {
    if (!aceptados.has(c.cuerpo.clave_ejecucion)) efectos++;
    return rx.of(detalle({ estado: 'COMPLETADO' }));
  };
  await recibir(recarga.servicio.ejecutar(id)); assert.equal(efectos, 1);
  assert.equal(posts(e)[0].clave, posts(recarga)[0].clave);
  assert.equal(posts(e)[0].cuerpo.clave_ejecucion, posts(recarga)[0].cuerpo.clave_ejecucion);
});

test('acciones, recursos, empresa y usuario distintos nunca comparten claves', async () => {
  const e = entorno(); e.http.responder = perdida;
  await assert.rejects(recibir(e.servicio.ejecutar(id)));
  await assert.rejects(recibir(e.servicio.ejecutar(otro)));
  await assert.rejects(recibir(e.servicio.autorizar(id)));
  e.auth.usuario = { ...e.auth.usuario, usuario_id: clienteB }; await assert.rejects(recibir(e.servicio.ejecutar(id)));
  e.auth.usuario = { ...e.auth.usuario, empresa_id: empresaB }; await assert.rejects(recibir(e.servicio.ejecutar(id)));
  assert.equal(new Set(posts(e).map(c => c.clave)).size, 5);
});

test('confirmacion cierra intento; otra solicitud no reutiliza su clave', async () => {
  const e = entorno(); await recibir(e.servicio.solicitar(solicitud())); await recibir(e.servicio.solicitar(solicitud()));
  assert.notEqual(posts(e)[0].clave, posts(e)[1].clave);
});

test('EN_PROCESO conserva ambos UUID; respuesta de otro recurso/tenant no confirma', async () => {
  const e = entorno(); e.http.responder = () => rx.of(detalle({ estado: 'EN_PROCESO' }));
  await recibir(e.servicio.ejecutar(id)); await recibir(e.nuevoServicio().ejecutar(id));
  e.http.responder = () => rx.of(detalle({ id: otro, estado: 'COMPLETADO' }));
  await assert.rejects(recibir(e.servicio.ejecutar(id)));
  e.http.responder = () => rx.of(detalle({ empresa_id: empresaB, estado: 'COMPLETADO' }));
  await assert.rejects(recibir(e.servicio.ejecutar(id)));
  assert.equal(new Set(posts(e).map(c => c.clave)).size, 1);
  assert.equal(new Set(posts(e).map(c => c.cuerpo.clave_ejecucion)).size, 1);
});

test('sin persistencia durable o con intento corrupto no se inventa otro POST', async () => {
  const storage = new StorageMemoria(); storage.setItem = () => { throw new Error('cuota'); };
  const sinStorage = entorno(storage); await assert.rejects(recibir(sinStorage.servicio.ejecutar(id)));
  assert.equal(posts(sinStorage).length, 0);
  const e = entorno(); e.http.responder = perdida; await assert.rejects(recibir(e.servicio.ejecutar(id)));
  for (const k of e.storage.datos.keys()) e.storage.setItem(k, '{}');
  await assert.rejects(recibir(e.nuevoServicio().ejecutar(id))); assert.equal(posts(e).length, 1);
});

test('cambio de identidad durante resolucion impide POST', async () => {
  const e = entorno(); e.http.responder = () => {
    e.auth.usuario = { ...e.auth.usuario, empresa_id: empresaB }; return rx.of({ id: venta });
  };
  await assert.rejects(recibir(e.servicio.solicitar(solicitud({ origen_id: 'VNT-1' })))); assert.equal(posts(e).length, 0);
});

test('controlador filtra por cualquier componente y separa consulta administrativa de /mios', () => {
  const e = entorno(); const c = e.componente(e.servicio); c.ngOnInit();
  c.filtroMedio = 'SALDO'; c.filtroEstado = 'PENDIENTE_AUTORIZACION'; assert.equal(c.reembolsosFiltrados[0].id, id);
  e.llamadas.length = 0; c.idConsulta = id; c.consultarAdministrativo(); assert.equal(e.llamadas.length, 0);
  e.auth.usuario.rol = 'ADMINISTRADOR'; c.consultarAdministrativo();
  assert.equal(e.llamadas[0].url, '/api/v1/reembolsos/' + id); assert.equal(c.consultaAdministrativa, true);
  c.verMisReembolsos(); assert.equal(e.llamadas[1].url, '/api/v1/reembolsos/mios');
  e.auth.usuario.rol = 'SUPERADMIN'; c.iniciarAutorizacion(detalle()); assert.equal(c.esPersonal, false);
  assert.equal(c.dialogoConfirmarVisible, false);
});

test('controlador valida origen, estado y usa id real sin anunciar completado ante EN_PROCESO', () => {
  const e = entorno(); const usados = []; const c = e.componente({
    ejecutar: x => { usados.push(x); return rx.of(detalle({ estado: 'EN_PROCESO' })); }, listarMios: () => rx.of([detalle()]) });
  c.abrirModalSolicitud('PED-1', 'PEDIDO'); c.enviarSolicitud(); assert.ok(c.errorSolicitud);
  e.auth.usuario.rol = 'ENCARGADO'; c.iniciarEjecucion(detalle({ estado: 'FALLIDO' })); assert.equal(c.dialogoConfirmarVisible, false);
  c.iniciarEjecucion(detalle({ estado: 'AUTORIZADO' })); c.confirmarAccion();
  assert.equal(usados[0], id); assert.match(c.exito, /Consulta el estado/);
});
