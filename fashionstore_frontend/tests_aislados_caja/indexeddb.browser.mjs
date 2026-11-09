// Integración con IndexedDB nativo, sin Angular, mocks de IDB ni API remota.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const ts = require(process.env.TYPESCRIPT_LIB || 'C:/Users/hp/Desktop/si2G3-5/Telemmedicina-SDD/frontend_Telemedicina/node_modules/typescript/lib/typescript.js');
const archivo = new URL('../src/app/features/ventas_pagos/services/caja-local.store.ts', import.meta.url);
const codigo = ts.transpileModule(fs.readFileSync(archivo, 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
const servicioCodigo = ts.transpileModule(fs.readFileSync(new URL('../src/app/features/ventas_pagos/services/caja.service.ts', import.meta.url), 'utf8'),
  { compilerOptions: { experimentalDecorators: true, target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
const pagina = '<!doctype html><title>Caja aislada</title>';
const servidor = http.createServer((req, res) => { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(pagina); });
await new Promise(r => servidor.listen(0, '127.0.0.1', r));
const url = `http://127.0.0.1:${servidor.address().port}/`;
const perfil = fs.mkdtempSync(path.join(os.tmpdir(), 'fashionstore-caja-pruebas-'));
const chrome = process.env.CHROME_BIN || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const proceso = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--no-sandbox', '--single-process', '--disable-features=RendererCodeIntegrity',
  '--disable-extensions', '--disable-background-networking', '--disable-component-update', '--disable-sync',
  '--proxy-server=http://127.0.0.1:9', '--proxy-bypass-list=127.0.0.1;localhost',
  '--remote-debugging-port=0', `--user-data-dir=${perfil}`, 'about:blank'], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
let ws;
let cerrarNavegador;
try {
  const direccion = await new Promise((resolve, reject) => {
    let s = ''; const timer = setTimeout(() => reject(new Error('Chrome no inició CDP')), 15000);
    proceso.stderr.on('data', d => { s += d; const m = s.match(/DevTools listening on (ws:\/\/[^\s]+)/); if (m) { clearTimeout(timer); resolve(m[1]); } });
    proceso.on('error', reject);
  });
  ws = new WebSocket(direccion); await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  console.log('Chrome aislado conectado');
  let id = 0; const pendientes = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id) { const p = pendientes.get(m.id); pendientes.delete(m.id); m.error ? p.reject(m.error) : p.resolve(m.result); } };
  const cdp = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const n = ++id;
    const timer = setTimeout(() => { pendientes.delete(n); reject(new Error('Tiempo agotado: ' + method)); }, 30000);
    pendientes.set(n, { resolve: v => { clearTimeout(timer); resolve(v); }, reject: e => { clearTimeout(timer); reject(e); } });
    ws.send(JSON.stringify({ id: n, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  cerrarNavegador = () => cdp('Browser.close');
  async function tab() {
    const t = await cdp('Target.createTarget', { url });
    const { sessionId } = await cdp('Target.attachToTarget', { targetId: t.targetId, flatten: true });
    await cdp('Runtime.enable', {}, sessionId);
    await cdp('Network.enable', {}, sessionId);
    for (let n = 0; n < 100; n++) {
      if (await evaluar(sessionId, 'location.origin') === url.slice(0, -1)) break;
      await new Promise(r => setTimeout(r, 50));
    }
    await cdp('Network.setBlockedURLs', { urls: ['https://*'] }, sessionId);
    await evaluar(sessionId, 'globalThis.exports = {}; ' + codigo);
    return sessionId;
  }
  async function evaluar(s, expression) {
    const r = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, s);
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  }
  const s = await tab();
  console.log('Ejecutando almacenamiento nativo');
  const resultados = await evaluar(s, `(${async function () {
    const { CajaLocalStore, canonicoCaja } = exports;
    const resultados = [];
    const assert = (condicion, msg = 'Aserción fallida') => { if (!condicion) throw new Error(msg); };
    const rechaza = async (f, texto) => { let error; try { await f(); } catch (e) { error = e; } assert(error && (!texto || error.message.includes(texto)), 'Se esperaba rechazo: ' + texto); };
    const ctx = { empresa_id: 'A', usuario_id: 'uA', dispositivo_id: 'dA', rol: 'CAJERO' };
    let reloj = Date.parse('2026-11-08T12:00:00Z');
    const turno = id => ({ turno_id: id, habilitacion_id: id, empresa_id: 'A', cajero_id: 'uA', dispositivo_id: 'dA',
      estado: 'ABIERTO', inicio_en: '2026-11-08T12:00:00Z', vence_en: '2026-11-08T20:00:00Z', hora_central_en: '2026-11-08T12:00:00Z',
      version_precios: 'v1', revision: 1, cupos: [{ variante_id: 'v', otorgado: 1, consumido: 0, liberado: 0, mermado: 0, precio_autorizado_bob: 10 }] });
    const venta = id => ({ operacion_id: id, secuencia_local: 0, vendida_local_en: '2026-11-08T12:00:00Z', entregada_local_en: '2026-11-08T12:00:00Z',
      version_precios: 'v1', lineas: [{ variante_id: 'v', cantidad: 1, precio_autorizado_bob: 10 }], total_bob: 10, efectivo_recibido_bob: 20, cambio_entregado_bob: 10 });
    const nueva = async nombre => { reloj = Date.parse('2026-11-08T12:00:00Z'); const c = new CajaLocalStore('prueba-' + nombre, () => reloj); await c.guardarTurno(ctx, turno('t1')); return c; };
    async function prueba(nombre, fn) { await fn(); resultados.push('OK ' + nombre); }
    await prueba('aislamiento empresa, usuario y dispositivo', async () => {
      const c = await nueva('ambito'); await c.registrar(ctx, 't1', venta('o1'), { numero: 'local' });
      for (const cambio of [{ empresa_id: 'B' }, { usuario_id: 'uB' }, { dispositivo_id: 'dB' }]) {
        assert((await c.pendientes({ ...ctx, ...cambio })).length === 0);
        assert((await c.turnos({ ...ctx, ...cambio })).length === 0);
        assert((await c.comprobantes({ ...ctx, ...cambio })).length === 0);
      }
      c.cerrar(); const reinicio = new CajaLocalStore('prueba-ambito', () => reloj);
      assert((await reinicio.pendientes(ctx)).length === 1); assert((await reinicio.comprobantes(ctx)).length === 1);
      await reinicio.guardarTurno(ctx, turno('t2'));
      assert((await reinicio.pendientes(ctx))[0].turno_id === 't1'); assert((await reinicio.turnos(ctx)).length === 2); reinicio.cerrar();
    });
    await prueba('UUID idéntico no consume y contenido diferente conflictúa', async () => {
      const c = await nueva('idempotencia'), v = venta('o1');
      const a = await c.registrar(ctx, 't1', v, {}); await c.registrar(ctx, 't1', v, {}); await c.registrar(ctx, 't1', a.venta, {});
      assert((await c.turnos(ctx))[0].cupos[0].consumido === 1); assert((await c.comprobantes(ctx)).length === 1);
      await rechaza(() => c.registrar(ctx, 't1', { ...v, cliente_id: 'otro' }, {}), 'CONFLICTO');
      await rechaza(() => c.registrar(ctx, 't2', v, {}), 'CONFLICTO'); c.cerrar();
    });
    await prueba('vencimiento y conciliación bloquean solo nuevas ventas', async () => {
      const c = await nueva('vigencia'); await c.registrar(ctx, 't1', venta('previa'), {});
      reloj += 8 * 3600000; await rechaza(() => c.registrar(ctx, 't1', venta('tardia'), {}), 'vencido');
      assert((await c.pendientes(ctx)).length === 1); assert((await c.turnos(ctx))[0].cupos[0].liberado === 0);
      reloj -= 8 * 3600000; await c.estado(ctx, 't1', 'CONCILIACION');
      await rechaza(() => c.registrar(ctx, 't1', venta('otra'), {}), 'vencido'); c.cerrar();
    });
    await prueba('dos conexiones concurrentes para última unidad', async () => {
      const c = await nueva('concurrente'), d = new CajaLocalStore('prueba-concurrente', () => reloj);
      const r = await Promise.allSettled([c.registrar(ctx, 't1', venta('uno'), {}), d.registrar(ctx, 't1', venta('dos'), {})]);
      assert(r.filter(x => x.status === 'fulfilled').length === 1); assert((await c.pendientes(ctx)).length === 1);
      assert((await c.turnos(ctx))[0].cupos[0].consumido === 1); c.cerrar(); d.cerrar();
    });
    await prueba('fallo intermedio revierte cupo, venta y comprobante', async () => {
      const c = await nueva('rollback'); await rechaza(() => c.registrar(ctx, 't1', venta('o1'), {}, true), 'simulado');
      assert((await c.pendientes(ctx)).length === 0); assert((await c.comprobantes(ctx)).length === 0);
      assert((await c.turnos(ctx))[0].cupos[0].consumido === 0);
      await c.registrar(ctx, 't1', venta('o1'), {}); c.cerrar();
    });
    await prueba('cupo insuficiente no deja consumo ni documentos', async () => {
      const c = await nueva('insuficiente'), v = venta('o1');
      v.lineas[0].cantidad = 2; v.total_bob = 20; v.efectivo_recibido_bob = 20; v.cambio_entregado_bob = 0;
      await rechaza(() => c.registrar(ctx, 't1', v, {}), 'Cupo');
      assert((await c.pendientes(ctx)).length === 0 && (await c.comprobantes(ctx)).length === 0);
      assert((await c.turnos(ctx))[0].cupos[0].consumido === 0); c.cerrar();
    });
    await prueba('refresco conserva consumo durable, mermas y liberaciones previas', async () => {
      const c = await nueva('saldo-refresco'); await c.registrar(ctx, 't1', venta('o1'), {});
      const db = await c.abrir();
      await new Promise((resolve, reject) => {
        const tx = db.transaction('turnos', 'readwrite'), st = tx.objectStore('turnos'), req = st.get('t1');
        req.onsuccess = () => { const t = req.result; t.cupos[0].consumido = 0; t.cupos[0].mermado = 1; t.cupos[0].liberado = 1; st.put(t); };
        tx.oncomplete = resolve; tx.onabort = () => reject(tx.error);
      });
      await c.guardarTurno(ctx, turno('t1'));
      const saldo = (await c.turnos(ctx))[0].cupos[0];
      assert(saldo.consumido === 1 && saldo.mermado === 1 && saldo.liberado === 1);
      await rechaza(() => c.registrar(ctx, 't1', venta('o2'), {}), 'Cupo'); c.cerrar();
    });
    await prueba('respuesta perdida: cuerpo estable, reintento y resultado durable', async () => {
      const c = await nueva('respuesta'); const v = await c.registrar(ctx, 't1', venta('o1'), {});
      const recibido = new Map(); let cobros = 0;
      async function servidorSimulado(cuerpo, perder) {
        if (!recibido.has(cuerpo.operacion_id)) { cobros++; recibido.set(cuerpo.operacion_id, canonicoCaja(cuerpo)); }
        assert(recibido.get(cuerpo.operacion_id) === canonicoCaja(cuerpo));
        if (perder) throw new Error('respuesta perdida');
        return { resultado: 'REGISTRADA_CENTRAL', operacion_id: cuerpo.operacion_id, venta_id: 'central' };
      }
      await rechaza(() => servidorSimulado(v.venta, true)); assert((await c.pendientes(ctx)).length === 1);
      await c.guardarTurno(ctx, turno('t1')); assert((await c.turnos(ctx))[0].cupos[0].consumido === 1);
      const p = (await c.pendientes(ctx))[0]; await c.resultado(ctx, p.operacion_id, await servidorSimulado(p.cuerpo, false));
      assert(cobros === 1 && (await c.pendientes(ctx)).length === 0); assert((await c.comprobantes(ctx)).length === 1); c.cerrar();
    });
    await prueba('resultado incierto o conciliación no eliminan operación', async () => {
      const c = await nueva('conciliacion'); await c.registrar(ctx, 't1', venta('o1'), {});
      await rechaza(() => c.resultado(ctx, 'o1', { resultado: 'error', operacion_id: 'o1' }));
      await c.resultado(ctx, 'o1', { resultado: 'CONCILIACION_REQUERIDA', operacion_id: 'o1' });
      assert((await c.pendientes(ctx)).length === 1); assert(await c.pendientesCierre(ctx, 't1')); c.cerrar();
    });
    await prueba('retroceso de reloj observado bloqueado y snapshot repetido no extiende turno', async () => {
      const c = await nueva('reloj'); reloj += 1000; await c.registrar(ctx, 't1', venta('o1'), {});
      reloj -= 500; await rechaza(() => c.registrar(ctx, 't1', venta('o2'), {}), 'reloj');
      reloj += 8 * 3600000; await c.guardarTurno(ctx, turno('t1'));
      await rechaza(() => c.registrar(ctx, 't1', venta('o3'), {}), 'vencido'); c.cerrar();
    });
    await prueba('migración v1 conserva legado sin atribución a sesión actual', async () => {
      await new Promise((resolve, reject) => {
        const r = indexedDB.open('prueba-legado', 1);
        r.onupgradeneeded = () => { r.result.createObjectStore('turnos', { keyPath: 'turno_id' }); r.result.createObjectStore('ventas_offline', { keyPath: 'operacion_id' }); r.result.createObjectStore('comprobantes', { keyPath: 'operacion_id' }); };
        r.onerror = () => reject(r.error); r.onsuccess = () => { const d = r.result, tx = d.transaction('ventas_offline', 'readwrite'); tx.objectStore('ventas_offline').put(venta('legado')); tx.oncomplete = () => { d.close(); resolve(); }; };
      });
      const c = new CajaLocalStore('prueba-legado'); assert((await c.pendientes(ctx)).length === 0);
      assert((await c.diagnosticos(ctx)).length === 1);
      await c.importarLegado({ bruto: '{json dañado sin eliminar}' });
      await c.importarLegado({ bruto: 'no sobrescribir respaldo original' });
      const db = await c.abrir();
      const respaldo = await new Promise(resolve => {
        const q = db.transaction('recuperacion').objectStore('recuperacion').get('bruto'); q.onsuccess = () => resolve(q.result.valor);
      });
      assert(respaldo === '{json dañado sin eliminar}');
      const viejo = await new Promise(resolve => { const r = db.transaction('ventas_offline').objectStore('ventas_offline').get('legado'); r.onsuccess = () => resolve(r.result); });
      assert(viejo.total_bob === 10 && !viejo.origen && viejo.estado_local === 'RECUPERACION_REQUERIDA'); c.cerrar();
    });
    await prueba('recuperación supervisada exige autorización y mantiene origen', async () => {
      const c = await nueva('supervision'); await c.registrar(ctx, 't1', venta('o1'), {});
      const supervisor = { ...ctx, usuario_id: 'admin', rol: 'ADMINISTRADOR' };
      await rechaza(() => c.supervisados(supervisor, { ...turno('t1'), empresa_id: 'B' }));
      const r = await c.supervisados(supervisor, turno('t1')); assert(r.length === 1 && r[0].origen.usuario_id === 'uA');
      assert((await c.pendientes(supervisor)).length === 0); c.cerrar();
    });
    return resultados;
  }} )()`);
  resultados.forEach(x => console.log(x));
  const s2 = await tab();
  const ctx = { empresa_id: 'A', usuario_id: 'uA', dispositivo_id: 'dA', rol: 'CAJERO' };
  const ahora = Date.now();
  const turno = { turno_id: 'turno-pestanas', habilitacion_id: 'turno-pestanas', empresa_id: 'A', cajero_id: 'uA', dispositivo_id: 'dA', estado: 'ABIERTO',
    inicio_en: new Date(ahora - 1000).toISOString(), vence_en: new Date(ahora + 8 * 3600000).toISOString(), hora_central_en: new Date(ahora).toISOString(),
    version_precios: 'v1', revision: 1, cupos: [{ variante_id: 'v', otorgado: 1, consumido: 0, liberado: 0, precio_autorizado_bob: 10 }] };
  const venta = { operacion_id: 'izquierda', secuencia_local: 0, vendida_local_en: new Date(ahora).toISOString(), entregada_local_en: new Date(ahora).toISOString(),
    version_precios: 'v1', lineas: [{ variante_id: 'v', cantidad: 1, precio_autorizado_bob: 10 }], total_bob: 10, efectivo_recibido_bob: 10, cambio_entregado_bob: 0 };
  for (const sid of [s, s2]) await evaluar(sid, `globalThis.ctx = ${JSON.stringify(ctx)}; globalThis.cajaPestana = new exports.CajaLocalStore('prueba-dos-pestanas');`);
  await evaluar(s, `cajaPestana.guardarTurno(ctx, ${JSON.stringify(turno)})`);
  const competir = v => `(async()=>{try { await cajaPestana.registrar(ctx, 'turno-pestanas', ${JSON.stringify(v)}, {}); return true; } catch { return false; }})()`;
  const competencia = await Promise.all([evaluar(s, competir(venta)), evaluar(s2, competir({ ...venta, operacion_id: 'derecha' }))]);
  if (competencia.filter(Boolean).length !== 1) throw new Error('Concurrencia entre pestañas incorrecta');
  if (await evaluar(s, '(async()=> (await cajaPestana.turnos(ctx))[0].cupos[0].consumido)()') !== 1) throw new Error('Consumo entre pestañas incorrecto');
  console.log('OK dos pestañas compiten por la última unidad');

  // Unidad de integración del adaptador: DI/RxJS se sustituyen, IndexedDB es real.
  await evaluar(s, `globalThis.cajaServicioExports = {}; ((require, exports) => { ${servicioCodigo} })((nombre) => {
    if (nombre === '@angular/core') return { Injectable: () => target => target };
    if (nombre === 'rxjs') return { from: p => p, firstValueFrom: p => Promise.resolve(p) };
    if (nombre.includes('environment')) return { environment: { apiUrl: '/api/v1' } };
    if (nombre.includes('solicitud-http')) return { cabeceraIdempotencia: () => ({}) };
    if (nombre.includes('caja-local.store')) return globalThis.exports;
    throw new Error('Dependencia de prueba no prevista: ' + nombre);
  }, cajaServicioExports);`);
  const adapter = await evaluar(s, `(${async function () {
    const assert = (x, m) => { if (!x) throw new Error(m); };
    let usuario = { empresa_id: 'A', usuario_id: 'uA', rol: 'CAJERO' }, privada = true, perder = true;
    const llamadas = [], aceptadas = new Map();
    const auth = { obtenerUsuarioActual: () => usuario, esVentanaPrivacidadValida: () => privada };
    const http = { get: async url => ({ ...t(url.split('/').pop()), hora_central_en: new Date().toISOString() }), post: async (url, cuerpo) => {
      llamadas.push({ url, cuerpo: JSON.stringify(cuerpo) });
      if (!aceptadas.has(cuerpo.operacion_id)) aceptadas.set(cuerpo.operacion_id, JSON.stringify(cuerpo));
      if (perder) { perder = false; throw new Error('respuesta perdida'); }
      return { resultado: 'REGISTRADA_CENTRAL', operacion_id: cuerpo.operacion_id, venta_id: 'central' };
    }};
    const servicio = new cajaServicioExports.CajaService(http, auth), dispositivo = servicio.obtenerDispositivoId();
    const ahora = Date.now();
    const t = id => ({ turno_id: id, habilitacion_id: id, empresa_id: 'A', cajero_id: 'uA', dispositivo_id: dispositivo, estado: 'ABIERTO',
      inicio_en: new Date(ahora - 1000).toISOString(), vence_en: new Date(ahora + 8 * 3600000).toISOString(), hora_central_en: new Date(ahora).toISOString(),
      version_precios: 'v1', revision: 1, cupos: [{ variante_id: 'v', otorgado: 2, consumido: 0, liberado: 0, precio_autorizado_bob: 10 }] });
    await servicio.guardarTurnoLocal(t('original'));
    const v = { operacion_id: 'operacion-original', secuencia_local: 0, vendida_local_en: new Date(ahora).toISOString(), entregada_local_en: new Date(ahora).toISOString(),
      version_precios: 'v1', lineas: [{ variante_id: 'v', cantidad: 1, precio_autorizado_bob: 10 }], total_bob: 10, efectivo_recibido_bob: 10, cambio_entregado_bob: 0 };
    const registrado = await servicio.registrarVentaOfflineTransaccional(t('original'), v, {});
    try { await servicio.registrarVentaOffline('original', registrado.venta); } catch {}
    assert((await servicio.obtenerVentasOfflinePendientes()).length === 1, 'Se perdió el pendiente al fallar la respuesta');
    usuario = { empresa_id: 'B', usuario_id: 'uB', rol: 'CAJERO' };
    assert((await servicio.obtenerVentasOfflinePendientes()).length === 0, 'Lectura cruzada');
    assert((await servicio.sincronizarPendientes()).completadas === 0 && llamadas.length === 1, 'Se envió bajo otra identidad');
    usuario = { empresa_id: 'A', usuario_id: 'uA', rol: 'CAJERO' }; privada = false;
    let bloqueada = false; try { await servicio.obtenerVentasOfflinePendientes(); } catch { bloqueada = true; }
    assert(bloqueada, 'Token sin privacidad autoriza caja'); privada = true;
    await servicio.guardarTurnoLocal(t('nuevo'));
    const res = await servicio.sincronizarPendientes();
    assert(res.completadas === 1 && llamadas.length === 2, 'No recuperó la operación');
    assert(llamadas.every(l => l.url.endsWith('/cajas/turnos/original/ventas')), 'Se reasignó al nuevo turno');
    assert(llamadas[0].cuerpo === llamadas[1].cuerpo && aceptadas.size === 1, 'Se modificó el cuerpo en reintento');
    const confirmado = await servicio.registrarVentaOffline('original', registrado.venta);
    assert(confirmado.resultado === 'REGISTRADA_CENTRAL' && llamadas.length === 2, 'Se perdio el resultado durable');
    assert((await servicio.obtenerComprobantesLocales())[0].esOffline === false, 'Comprobante confirmado sigue marcado pendiente');
    await servicio.cerrarBd();
    localStorage.setItem('fs_ventas_offline_pendientes', '[{"operacion_id":"legado-sin-origen"}]');
    const cierre = new cajaServicioExports.CajaService(http, auth);
    let cierreBloqueado = false;
    try { await cierre.cerrarTurno('original', { revision: 1 }); } catch { cierreBloqueado = true; }
    assert(cierreBloqueado && llamadas.length === 2, 'Cierre sin importar antes el legado pendiente');
    await cierre.cerrarBd();
    localStorage.removeItem('fs_ventas_offline_pendientes');
    return 'OK adaptador HTTP: identidad, privacidad, turno original y reintento inmutable';
  }})()`);
  console.log(adapter);
  console.log(`${resultados.length + 2} pruebas de almacenamiento/adaptador aprobadas`);
} catch (error) {
  console.error(error);
  process.exitCode = 1;
} finally {
  if (cerrarNavegador) await Promise.race([cerrarNavegador().catch(() => {}), new Promise(r => setTimeout(r, 1000))]);
  ws?.close(); proceso.kill(); proceso.stderr.destroy(); proceso.unref(); servidor.closeAllConnections(); servidor.close();
  // Chrome/crashpad puede heredar handles de stderr en Windows. El resultado ya
  // está decidido; no dejar un ejecutor de pruebas esperando esos handles.
  setTimeout(() => process.exit(process.exitCode || 0), 100);
}
