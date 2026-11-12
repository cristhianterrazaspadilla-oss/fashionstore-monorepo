// Lógica real con dobles Angular/HTTP/micrófono. Sin navegador, .env ni red.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'); const path=require('node:path'); const vm=require('node:vm');
const {webcrypto}=require('node:crypto'); const ts=require('typescript'); const rx=require('rxjs');
const raiz=path.resolve(__dirname,'../..');
const ids=Array.from({length:6},(_,i)=>'10000000-0000-4000-8000-'+String(i+1).padStart(12,'0'));
function entorno() {
 const auth={usuario:{id:ids[0],empresa_id:ids[1],rol:'CLIENTE'},usuario$:new rx.BehaviorSubject(null),obtenerUsuarioActual(){return this.usuario;}};
 const memoria=new Map(); const storage={getItem:k=>memoria.get(k)??null,setItem:(k,v)=>memoria.set(k,v),removeItem:k=>memoria.delete(k)};
 const cache=new Map(), descargas=[]; const exportsStub={};
 function cargar(archivo) {
  archivo=path.resolve(archivo); if(cache.has(archivo))return cache.get(archivo);
  const module={exports:{}};cache.set(archivo,module.exports);
  const resolver=nombre=>{
   if(nombre==='rxjs')return rx;
   if(nombre==='exceljs'||nombre==='jspdf')return require(nombre);
   if(nombre==='@angular/core')return {Component:()=>x=>x,Injectable:()=>x=>x,DestroyRef:class DestroyRef{},
    inject:token=>token.name==='AuthService'?auth:token.name==='OrganizacionService'?{gestionarSucursales:()=>rx.of([])}:{}};
   if(nombre==='@angular/common'||nombre==='@angular/forms')return {};
   if(nombre==='@angular/core/rxjs-interop')return {takeUntilDestroyed:()=>x=>x};
   if(nombre==='@angular/common/http')return {HttpHeaders:class{constructor(h){this.h=h;} get(k){return this.h[k];}},HttpParams:class{set(){return this;}}};
   if(nombre.endsWith('/auth.service'))return {AuthService:class AuthService{}};
   if(nombre.endsWith('/organizacion.service'))return {OrganizacionService:class OrganizacionService{}};
   if(nombre.endsWith('/moneda.util'))return {entradaLocalIso:x=>x||undefined,formatearBs:String,formatearFechaHora:String};
   if(nombre.endsWith('/estado-mapper.util'))return {etiquetaEstado:String,claseEstado:String};
   if(nombre.endsWith('/error-handler.util'))return {formatearErrorApi:(_e,m)=>m||'Error controlado'};
   if(nombre.includes('/environments/environment'))return {environment:{apiUrl:'/api/v1'}};
   if(nombre.includes('/shared/data-viz/'))return {RadialProgressComponent:class{},HorizontalBarsComponent:class{},SegmentedBarComponent:class{}};
   if(nombre==='./exportar-reporte'&&exportsStub.archivoReporte)return exportsStub;
   if(nombre.startsWith('.'))return cargar(path.resolve(path.dirname(archivo),nombre+'.ts'));
   throw Error('Import no permitido: '+nombre);
  };
  const js=ts.transpileModule(fs.readFileSync(archivo,'utf8'),{compilerOptions:{experimentalDecorators:true,target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
  // Exportador y librerías comparten realm, como en el navegador real: ExcelJS
  // usa instanceof Array para addRows y rechaza arrays de otro VM.
  const ejecutar=vm.runInThisContext('(function(module,exports,require,crypto,localStorage){'+js+'\n})',{filename:archivo});
  ejecutar(module,module.exports,resolver,webcrypto,storage);
  return module.exports;
 }
 return {auth,cargar,memoria,exportsStub,descargas};
}
const resultado=(tipo='VENTAS_POR_SUCURSAL')=>({consulta_id:ids[4],tipo_reporte:tipo,
 filtros_efectivos:{sucursal_id:ids[2],desde:'2026-01-01',hasta:'2026-12-31',narrativa_origen:'DETERMINISTA'},
 columnas:['nombre','importe_bob','unidades'],filas:[{nombre:'Niñez <script>alert(1)</script>',importe_bob:'12.34',unidades:2},
 {nombre:'=HYPERLINK("malicioso")',importe_bob:'-1.20',unidades:1}],totales:{importe_bob:'11.14',unidades:3},
 narrativa:'Cálculo real, explicación determinista',generado_en:'2026-11-10T12:00:00Z',origen:'REAL',proveedor:'DETERMINISTA'});

test('dictado en español, detener/destruir, permiso y exclusión de sesiones; no consulta implícita',()=>{
 const e=entorno(),{DictadoReporte}=e.cargar(path.join(__dirname,'dictado-reporte.ts'));
 const instancias=[]; class Reconocedor{start(){this.iniciado=true;}stop(){this.onend?.();}abort(){this.abortado=true;}constructor(){instancias.push(this);}}
 let texto='',estado=false,error=''; const a=new DictadoReporte(t=>texto=t,(s,x)=>{estado=s;error=x;},{SpeechRecognition:Reconocedor});
 assert.equal(instancias.length,0);a.iniciar('Ventas');assert.equal(instancias[0].lang,'es-ES'); assert.equal(estado,true);
 instancias[0].onresult({results:[[{transcript:'por sucursal'}]]});assert.equal(texto,'Ventas por sucursal');a.detener();assert.equal(estado,false);
 a.iniciar('');const b=new DictadoReporte(()=>{},()=>{},{SpeechRecognition:Reconocedor});b.iniciar('');assert.equal(instancias[1].abortado,true);
 b.destruir();assert.equal(instancias[2].abortado,true);a.iniciar('');instancias[3].onerror({error:'not-allowed'});assert.match(error,/denegado/);
 const no=new DictadoReporte(()=>{},(_s,x)=>error=x,{});no.iniciar('');assert.match(error,/no disponible/);
});

for(const tipo of ['VENTAS_POR_SUCURSAL','RANKING_PRODUCTOS','EVOLUCION_SEMANAL','INGRESOS_POR_CATEGORIA'])
 test('CSV/HTML/XLSX/PDF reales, acentos, números y fórmulas seguras: '+tipo,async()=>{
 const {cargar}=entorno(),{archivoReporte}=cargar(path.join(__dirname,'exportar-reporte.ts')),r=resultado(tipo);
 const csv=await(await archivoReporte(r,'Niñez y ventas','csv')).text();assert.match(csv,/12.34/);assert.match(csv,/Niñez/);assert.match(csv,/'=HYPERLINK/);assert.match(csv,/Totales/);
 const html=await(await archivoReporte(r,'Niñez <img onerror=x>','html')).text();assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);assert.match(html,/narrativa_origen/);
 const bytes=await(await archivoReporte(r,'Niñez y ventas','xlsx')).arrayBuffer();assert.equal(Buffer.from(bytes).subarray(0,2).toString(),'PK');
 const {Workbook}=require('exceljs'),libro=new Workbook();await libro.xlsx.load(bytes);
 assert.equal(libro.getWorksheet('Contexto').getCell('A1').value,'Título');
 assert.equal(libro.getWorksheet('Contexto').getCell('B1').value,'Niñez y ventas');
 assert.equal(libro.getWorksheet('Datos').getCell('B2').value,12.34);assert.equal(libro.getWorksheet('Datos').getCell('B3').value,-1.2);
 assert.equal(libro.getWorksheet('Datos').getCell('A3').type,require('exceljs').ValueType.String);
 assert.match(libro.getWorksheet('Datos').getCell('A3').value,/^'=HYPERLINK/);
 assert.match(libro.getWorksheet('Datos').getCell('A2').value,/Niñez/);assert.equal(libro.getWorksheet('Totales').getCell('B2').value,11.14);
 const pdf=Buffer.from(await(await archivoReporte(r,'Niñez y ventas','pdf')).arrayBuffer()).toString('latin1');assert.ok(pdf.startsWith('%PDF-'));assert.match(pdf,/Niñez/);assert.match(pdf,/12.34/);assert.match(pdf,/11.14/);
});

test('PDF pagina todas las filas; columnas variables; resultado inválido se rechaza',async()=>{
 const {cargar}=entorno(),{archivoReporte}=cargar(path.join(__dirname,'exportar-reporte.ts')),r=resultado();
 r.columnas=['semana','ventas'];r.filas=Array.from({length:400},(_,i)=>({semana:'fila'+i,ventas:i}));
 const pdf=Buffer.from(await(await archivoReporte(r,'Evolución','pdf')).arrayBuffer()).toString('latin1');
 assert.ok((pdf.match(/\/Type \/Page\b/g)||[]).length>1);assert.match(pdf,/fila0/);assert.match(pdf,/fila399/);
 await assert.rejects(archivoReporte({...r,filas:[{}]},'Inválido','xlsx'));
});

test('exporta snapshot obtenido; fallo, consulta nueva o cambio de sesión invalidan descarga',async()=>{
 const e=entorno();let resolver;let peticiones=0;
 e.exportsStub.archivoReporte=()=>new Promise(r=>resolver=r);e.exportsStub.descargarReporte=()=>e.descargas.push(1);
 const {InteligenciaComponent}=e.cargar(path.join(__dirname,'inteligencia.component.ts'));
 const respuestas=new rx.Subject();const c=new InteligenciaComponent({solicitarReporteInterpretado:()=>{peticiones++;return respuestas;}});c.ngOnInit();
 c.consulta='ventas';c.ejecutarReporteTipado();respuestas.next(resultado());assert.equal(c.exportacionDisponible,true);
 const promesa=c.exportar('pdf');assert.equal(peticiones,1);e.auth.usuario={...e.auth.usuario,empresa_id:ids[5]};e.auth.usuario$.next(null);
 resolver(new Blob(['pdf']));await promesa;assert.equal(e.descargas.length,0);assert.equal(c.reporteTipado,null);
 c.ejecutarReporteTipado();respuestas.error(new Error('fallo'));assert.equal(c.exportacionDisponible,false);assert.equal(c.reporteTipado,null);c.ngOnDestroy();
});

test('devolución física conserva clave/cuerpo tras respuesta perdida; ámbito y UUID correctos',async()=>{
 const e=entorno(),llamadas=[];let falla=true;
 const respuesta={id:ids[3],venta_id:ids[2],cliente_id:ids[0],estado:'SOLICITADA'};
 const http={post:(ruta,cuerpo,opciones)=>{llamadas.push({ruta,cuerpo:structuredClone(cuerpo),clave:opciones.headers.get('Idempotency-Key')});return falla?rx.throwError(()=>Error('perdida')):rx.of(respuesta);}};
 const {PosventaService}=e.cargar(path.join(raiz,'posventa/services/posventa.service.ts'));
 const dto={venta_id:ids[2],lineas:[{detalle_venta_id:ids[4],cantidad:1}],motivo_codigo:'TALLA'};
 await assert.rejects(rx.firstValueFrom(new PosventaService(http,e.auth).solicitarDevolucion(dto)));
 falla=false;await rx.firstValueFrom(new PosventaService(http,e.auth).solicitarDevolucion(dto));
 assert.equal(llamadas[0].clave,llamadas[1].clave);assert.deepEqual(llamadas[0].cuerpo,llamadas[1].cuerpo);assert.equal(llamadas[1].cuerpo.venta_id,ids[2]);
 assert.equal(llamadas[1].cuerpo.lineas[0].detalle_venta_id,ids[4]);assert.equal(llamadas[1].cuerpo.lineas[0].variante_id,undefined);
 assert.throws(()=>new PosventaService(http,e.auth).solicitarDevolucion({...dto,venta_id:'CG-123'}),/UUID/);
 falla=true;await assert.rejects(rx.firstValueFrom(new PosventaService(http,e.auth).solicitarDevolucion(dto)));
 e.auth.usuario={...e.auth.usuario,empresa_id:ids[5]};await assert.rejects(rx.firstValueFrom(new PosventaService(http,e.auth).solicitarDevolucion(dto)));
 assert.notEqual(llamadas[2].clave,llamadas[3].clave);
});

test('operaciones usa UUID de venta/línea y reintenta inspección sin repetir solicitud ni fallback',()=>{
 const e=entorno(),{OperacionesComponent}=e.cargar(path.join(raiz,'posventa/operaciones/operaciones.component.ts'));
 let solicitudes=0,inspecciones=0,legacy=0,consulta;
 const venta={id:ids[2],numero:'CODIGO-SIN-INFERIR',detalles:[{id:ids[4],variante_id:ids[5],cantidad:2}]};
 const dev={id:ids[3],venta_id:ids[2],estado:'SOLICITADA'};
 const posventa={solicitarDevolucion:dto=>{solicitudes++;assert.equal(dto.lineas[0].detalle_venta_id,ids[4]);return rx.of(dev);},
 registrarInspeccion:()=>{inspecciones++;return inspecciones===1?rx.throwError(()=>Error('perdida')):rx.of({...dev,estado:'APROBADA_REPOSICION'});},
 devolver:()=>{legacy++;return rx.of({});}};
 const c=new OperacionesComponent({comprobante:id=>{consulta=id;return rx.of(venta);}},posventa,{},e.auth,{},{});
 c.irADevolucionDesdeVenta(venta);assert.equal(consulta,ids[2]);c.realizarInspeccion=true;c.devolver();
 assert.equal(c.devolucionRegistrada.id,ids[3]);assert.equal(c.procesando,false);
 c.devolver();assert.equal(solicitudes,1);assert.equal(inspecciones,2);assert.equal(legacy,0);
 const d=new OperacionesComponent({}, {...posventa,solicitarDevolucion:()=>rx.throwError(()=>Error('403'))},{},e.auth,{},{});
 d.comprobanteDev=venta;d.detalleSeleccionado=venta.detalles[0];d.detalleVenta=ids[4];d.devolver();assert.equal(legacy,0);assert.ok(d.error);
});

test('Caja 502/504 es solo aviso: conserva variantes, turno y errores de sincronización',()=>{
 const archivo=path.join(raiz,'ventas_pagos/caja/caja.component.ts');
 const actual=fs.readFileSync(archivo,'utf8');
 const metodos=codigo=>{const fuente=ts.createSourceFile('caja.ts',codigo,ts.ScriptTarget.Latest,true);const clase=fuente.statements.find(ts.isClassDeclaration);return new Map(clase.members.filter(ts.isMethodDeclaration).map(m=>[m.name.getText(fuente),m.getText(fuente).replaceAll('\r\n','\n')]));};
 const nuevos=metodos(actual);
 const js=ts.transpileModule('class Prueba{'+nuevos.get('cargarVariantes')+'};module.exports=Prueba',{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
 const module={exports:{}};vm.runInNewContext(js,{module,console:{warn(){}}});
 for(const status of [502,504]){const c=new module.exports();const variantes=[{id:'local'}];c.variantes=variantes;c.error='Sincronización pendiente';c.turnoActivo={id:'turno-original'};
 c.productos={gestionarVariantes:()=>rx.throwError(()=>({status,url:'https://tecnico.invalid',message:'Gateway Timeout'}))};c.cargarVariantes();
 assert.equal(c.variantes,variantes);assert.equal(c.error,'Sincronización pendiente');assert.equal(c.turnoActivo.id,'turno-original');
 assert.match(c.avisoCatalogo,/datos locales pueden estar desactualizados/);assert.ok(!c.avisoCatalogo.includes('https://'));
 }
});
test('CU24 texto y dictado usan el mismo DTO; ranking por sucursal y menor existencia admiten gráfico/exportación',()=>{
 const e=entorno(); let enviado; const {InteligenciaComponent}=e.cargar(path.join(__dirname,'inteligencia.component.ts'));
 const r={...resultado('RANKING_PRODUCTOS'),filtros_efectivos:{metrica:'unidades_vendidas',agrupacion:'SUCURSAL',presentacion:'GRAFICO'},
 filas:[{sucursal_nombre:'Norte',producto_nombre:'Polera',unidades_vendidas:12},{sucursal_nombre:'Sur',producto_nombre:'Pantalón',unidades_vendidas:8}]};
 const c=new InteligenciaComponent({solicitarReporteInterpretado:d=>{enviado=d;return rx.of(r);}});
 c.consulta='Mostrá los 10 productos más vendidos durante los últimos tres meses, agrupados por sucursal';
 c.generarReporte(); assert.equal(enviado.consulta,c.consulta);assert.equal(enviado.tipo_reporte,undefined);
 assert.equal(c.barrasReporteTipado.length,2);assert.equal(c.barrasReporteTipado[0].valor,12);
 assert.match(c.barrasReporteTipado[1].etiqueta,/Sur.*Pantalón/);assert.equal(c.exportacionDisponible,true);
 c.consulta='Mostrame los productos con menor existencia';c.generarReporte();assert.equal(enviado.consulta,c.consulta);
 c.ngOnDestroy();
});
test('CU06 envía todas las líneas y el cajero seleccionado; no habilita offline al supervisor',async()=>{
 const fuente=ts.createSourceFile('caja.ts',fs.readFileSync(path.join(raiz,'ventas_pagos/caja/caja.component.ts'),'utf8'),ts.ScriptTarget.Latest,true);
 const clase=fuente.statements.find(ts.isClassDeclaration);
 const codigo=clase.members.filter(m=>(ts.isMethodDeclaration(m)||ts.isGetAccessorDeclaration(m))&&['abrirTurno','puedeAsignarCajero'].includes(m.name.getText(fuente))).map(m=>m.getText(fuente)).join('\n');
 const module={exports:{}};vm.runInNewContext(ts.transpileModule('class Prueba{'+codigo+'};module.exports=Prueba',{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,{module,navigator:{onLine:true}});
 const c=new module.exports();c.auth={obtenerUsuarioActual:()=>({id:'admin',rol:'ADMINISTRADOR'})};c.cajeros=[{id:'cajero',sucursal_id:'s1'}];
 c.cajeroSeleccionado='cajero';c.cajaId='C1';c.dispositivoId='D1';c.cuposSolicitados=[{variante_id:'A',cantidad:3},{variante_id:'B',cantidad:2}];
 let enviado, guardados=0;c.persistirTurnoLocalmente=async()=>guardados++;c.cajaService={habilitarTurno:d=>{enviado=d;return rx.of({cajero_id:'cajero',caja_codigo:'C1',dispositivo_id:'D1',sucursal_id:'s1'});}};
 c.abrirTurno();assert.equal(enviado.cajero_id,'cajero');assert.deepEqual(JSON.parse(JSON.stringify(enviado.cupos)),[{variante_id:'A',cantidad:3},{variante_id:'B',cantidad:2}]);
 assert.equal(guardados,0);assert.match(c.mensajeExito,/cajero debe iniciar sesión/);
});
// Las regresiones anteriores no comparan todo el componente con HEAD: se comprueba su comportamiento.
