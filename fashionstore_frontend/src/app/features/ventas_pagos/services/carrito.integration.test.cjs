// Servicio real, HTTP simulado; sin Angular en navegador, BD ni red.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const ts = require('typescript');
const rx = require('rxjs');
const archivo = path.join(__dirname, 'carrito.service.ts');
const js = ts.transpileModule(fs.readFileSync(archivo, 'utf8'), {
  compilerOptions: { experimentalDecorators: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS }
}).outputText;
const durable = () => ({ id: 'carrito', cliente_id: 'cliente', canal: 'WEB', estado: 'ACTIVO',
  total_estimado_bob: '24.68', lineas: [{ id: 'linea', variante_id: 'variante', cantidad: 2,
    precio_unitario_bob: '12.34', subtotal_bob: '24.68' }] });
function entorno() {
  const llamadas = [];
  const http = {};
  for (const metodo of ['get', 'post', 'patch', 'delete']) http[metodo] = (...args) => rx.defer(() => {
    llamadas.push({ metodo, args }); return rx.of(http.responder(metodo));
  });
  http.responder = durable;
  class HttpParams { set() { return this; } }
  class HttpHeaders { constructor(h) { this.h = h; } }
  const stubs = { '@angular/core': { Injectable: () => x => x },
    '@angular/common/http': { HttpParams, HttpHeaders }, rxjs: rx };
  const module = { exports: {} };
  vm.runInNewContext(js, { module, exports: module.exports, crypto: webcrypto,
    require: nombre => {
      if (nombre.includes('/environments/environment')) return { environment: { apiUrl: '/api/v1' } };
      if (nombre in stubs) return stubs[nombre];
      throw new Error('Import no permitido: ' + nombre);
    } }, { filename: archivo });
  return { http, llamadas, servicio: new module.exports.CarritoService(http) };
}

test('CU21 conserva precios y totales del backend; no convierte campos ausentes a cero', async () => {
  const e = entorno();
  const c = await rx.firstValueFrom(e.servicio.obtenerMio());
  assert.equal(c.total, '24.68'); assert.equal(c.subtotal, '24.68');
  assert.equal(c.lineas[0].precio_unitario, '12.34'); assert.equal(c.descuento_total, '0.00');
  assert.equal(e.llamadas[0].args[0], '/api/v1/carritos/mio');
  e.http.responder = () => { const c = durable(); delete c.lineas[0].precio_unitario_bob; return c; };
  await assert.rejects(rx.firstValueFrom(e.servicio.obtenerMio()), /Precio desconocido/);
});

test('CU14 conserva descuentos y nombres de campos históricos', async () => {
  const e = entorno();
  e.http.responder = () => ({ ...durable(), subtotal: '24.68', descuento_total: '2.00', total: '22.68',
    lineas: [{ id: 'linea', variante_id: 'variante', cantidad: 2, precio_unitario: '12.34',
      descuento_unitario: '1.00', subtotal: '22.68' }] });
  const c = await rx.firstValueFrom(e.servicio.obtenerMio());
  assert.equal(c.total, '22.68'); assert.equal(c.descuento_total, '2.00');
  assert.equal(c.lineas[0].descuento_unitario, '1.00');
});

test('mutación incompleta consulta de nuevo sin borrar líneas; si falta precio muestra error', async () => {
  const e = entorno();
  e.http.responder = metodo => metodo === 'get' ? durable() : {};
  const c = await rx.firstValueFrom(e.servicio.modificarLinea('variante', { cantidad: 2 }));
  assert.equal(c.total, '24.68'); assert.equal(c.lineas.length, 1);
  assert.deepEqual(e.llamadas.map(c => c.metodo), ['patch', 'get']);
  assert.equal(e.llamadas[0].args[0], '/api/v1/carritos/mio/lineas/variante');
  e.http.responder = () => ({});
  await assert.rejects(rx.firstValueFrom(e.servicio.agregarLinea({ variante_id: 'variante', cantidad: 1 })));
  assert.ok(e.llamadas.every(c => c.metodo !== 'delete'));
});
