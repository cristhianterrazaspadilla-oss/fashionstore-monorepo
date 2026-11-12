import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { CajaComponent } from './caja.component';
import { CajaService } from '../services/caja.service';
import { VentaPresencialService } from '../services/venta-presencial.service';
import { StripeService } from '../services/stripe.service';
import { ReservaTrasladoService } from '../../reservas_traslados/services/reserva-traslado.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { UsuarioService } from '../../identidad_empresas/services/usuario.service';
import { ProductoService } from '../../catalogo/services/producto.service';

describe('CU06/CU07 formulario real, HTTP sustituido sin proveedores', () => {
  it('asigna A=3 y B=2 al cajero; al cargar permite cobrar A=2/B=1 y conserva todas las líneas', async () => {
    let usuario: any = {id:'admin', empresa_id:'empresa', rol:'ADMINISTRADOR'};
    let guardado: any = null;
    let enviado: any;
    const turno: any = {empresa_id:'empresa', cajero_id:'cajero', dispositivo_id:'dispositivo', turno_id:'turno',
      habilitacion_id:'turno', sucursal_id:'sucursal', caja_codigo:'C1', estado:'ABIERTO', version_precios:'v1', revision:1,
      inicio_en:new Date().toISOString(), vence_en:new Date(Date.now()+28800000).toISOString(),
      cupos:[{variante_id:'A',producto_nombre:'Polera',talla:'M',color:'Negro',precio_autorizado_bob:10,otorgado:3,consumido:0,liberado:0},
             {variante_id:'B',producto_nombre:'Pantalón',talla:'32',precio_autorizado_bob:20,otorgado:2,consumido:0,liberado:0}]};
    const caja: any = {
      obtenerDispositivoId:()=> 'dispositivo', obtenerTurnoLocal:async()=>guardado,
      guardarTurnoLocal:async(t:any)=>guardado=structuredClone(t), consultarTurnoActivo:()=>of(null),
      limpiarTurnoLocal:async()=>{}, obtenerVentasOfflinePendientes:async()=>[], diagnosticosRecuperacion:async()=>[],
      listarConciliacion:()=>of([]),
      habilitarTurno:(dto:any)=>{ enviado=structuredClone(dto); return of(turno); },
      registrarVentaOfflineTransaccional:async(t:any,v:any,c:any)=>{
        enviado=structuredClone(v); const copia=structuredClone(t);
        for(const l of v.lineas)copia.cupos.find((x:any)=>x.variante_id===l.variante_id).consumido+=l.cantidad;
        return {turno:copia,venta:{...v,secuencia_local:1}};
      },
      registrarVentaOffline:(_t:any,v:any)=>of({resultado:'CONCILIACION_REQUERIDA',operacion_id:v.operacion_id})
    };
    await TestBed.configureTestingModule({imports:[CajaComponent],providers:[
      {provide:AuthService,useValue:{obtenerUsuarioActual:()=>usuario}},
      {provide:UsuarioService,useValue:{gestionarUsuarios:()=>of([{id:'cajero',rol_nombre:'CAJERO',estado:'ACTIVO',sucursal_id:'sucursal',nombre_completo:'Cajero prueba'}])}},
      {provide:CajaService,useValue:caja}, {provide:VentaPresencialService,useValue:{}},
      {provide:StripeService,useValue:{obtenerOrdenActivaCaja:()=>of(null)}},
      {provide:ReservaTrasladoService,useValue:{}},
      {provide:ProductoService,useValue:{gestionarVariantes:()=>of([
        {id:'A',sku:'FS-001-1',precio:10,producto_nombre:'Camisa',talla_nombre:'M',color_nombre:'Negro'},
        {id:'B',sku:'FS-001-2',precio:20,producto_nombre:'Camisa',talla_nombre:'L',color_nombre:'Azul'}])}}
    ]}).compileComponents();
    const fixture=TestBed.createComponent(CajaComponent); const c=fixture.componentInstance;
    fixture.detectChanges(); await fixture.whenStable();
    const opciones=Array.from(fixture.nativeElement.querySelectorAll('select[aria-label="Seleccionar prenda para cupo"] option') as NodeListOf<HTMLOptionElement>).map(o=>o.textContent || '');
    expect(opciones.some(o=>o.includes('Camisa · M · Negro · FS-001-1') && o.includes('10.00'))).toBeTrue();
    expect(opciones.some(o=>o.includes('Camisa · L · Azul · FS-001-2') && o.includes('20.00'))).toBeTrue();
    c.variantes.push({id:'solo-sku',sku:'SKU-SIN-NOMBRES'} as any);
    expect(c.v('solo-sku')).toBe('SKU-SIN-NOMBRES');
    c.cajeroSeleccionado='cajero';c.cajaId='C1';
    for(const [variante,cantidad] of [['A',1],['A',2],['B',2]] as const){
      c.cupoVarianteSeleccionada=variante;c.cupoCantidadSolicitada=cantidad;c.agregarCupoSolicitado();
    }
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.cupos-builder tbody tr').length).toBe(2);
    c.abrirTurno();await fixture.whenStable();
    expect(enviado.cajero_id).toBe('cajero');expect(enviado.cupos.map((x:any)=>x.cantidad)).toEqual([3,2]);
    expect(guardado).toBeNull();expect(c.turnoActivo).toBeNull();
    usuario={id:'cajero',empresa_id:'empresa',rol:'CAJERO',sucursal_id:'sucursal'};
    await c.persistirTurnoLocalmente(turno); fixture.detectChanges();
    for(const variante of ['A','A','B']) {
      c.varianteVentaOffline=variante;c.cantidadVentaOffline=1;c.agregarLineaVentaOffline();
    }
    expect(c.lineasVentaOffline.length).toBe(2);
    // La ruta presencial conserva la misma combinación por variante sin duplicarla.
    for(const variante of ['A','A','B']) { c.variante=variante;c.cantidad=1;c.agregar(); }
    expect(c.items.map(i=>i.cantidad)).toEqual([2,1]);
    c.efectivoRecibido=50;c.cambioEntregado=10;
    await c.cobrarVentaContado();await fixture.whenStable();fixture.detectChanges();
    expect(enviado.lineas.map((l:any)=>l.cantidad)).toEqual([2,1]);expect(enviado.total_bob).toBe(40);
    expect(c.turnoActivo!.cupos.map(x=>x.otorgado-x.consumido)).toEqual([1,1]);
    expect(c.comprobanteOffline!.lineas.length).toBe(2);expect(c.comprobanteOffline!.esOffline).toBeTrue();
    expect(c.comprobanteOffline!.lineas[0].sku).toContain('Camisa · M · Negro · FS-001-1');
    expect(c.comprobanteOffline!.lineas[1].sku).toContain('Camisa · L · Azul · FS-001-2');
    const catalogo=c.variantes;c.variantes=[];
    expect(c.v('A')).toContain('Polera · M · Negro');
    c.variantes=catalogo;
    expect(c.error).toContain('conciliacion');
    // El supervisor localiza y cierra el turno de otro titular desde la lista.
    usuario={id:'admin',empresa_id:'empresa',rol:'ADMINISTRADOR'};
    guardado=null;c.turnoActivo=null;
    turno.estado='CONCILIACION';turno.cupos[0].consumido=2;turno.cupos[1].consumido=1;
    let persistencias=0, cierres=0;
    caja.guardarTurnoLocal=async()=>{persistencias++;throw Error('No puede adoptar una caja ajena');};
    caja.listarConciliacion=()=>of(turno.estado==='CERRADO'?[]:[turno]);
    caja.consultarTurno=()=>of(structuredClone(turno));
    caja.cerrarTurno=(id:string,dto:any)=>{
      expect(id).toBe('turno');expect(dto.supervision_forzada).toBeTrue();
      expect(dto.evidencia_cierre.conteo_fisico_por_variante.map((x:any)=>x.cantidad_encontrada)).toEqual([1,1]);
      expect(dto.ultima_secuencia_local).toBeUndefined();
      cierres++;turno.estado='CERRADO';return of({estado:'CERRADO',cupos_devueltos:[{devuelto:1},{devuelto:1}]});
    };
    c.vistaModo='RESERVA';c.cargarConciliaciones();fixture.detectChanges();
    const boton=Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find(b=>b.textContent?.trim()==='Resolver conciliación')!;
    boton.click();await fixture.whenStable();fixture.detectChanges();
    expect(c.mostrarDialogoCierre).toBeTrue();expect(c.supervisandoTurno).toBeTrue();
    expect(c.vistaModo).toBe('TURNO_OFFLINE');
    expect(fixture.nativeElement.querySelector('.modal-dialog')).toBeTruthy();
    c.referenciaActa='ACTA-PRUEBA';c.motivoSupervision='Conteo físico de práctica aislada';c.arqueoEfectivoBob=40;
    c.conteoFisicoPorVariante={A:1,B:1};fixture.detectChanges();
    const guardar=Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>).find(b=>b.textContent?.trim()==='Guardar conteo y resolver')!;
    expect(guardar.disabled).toBeFalse();guardar.click();await fixture.whenStable();fixture.detectChanges();
    expect(cierres).toBe(1);expect(persistencias).toBe(0);expect(c.supervisandoTurno).toBeFalse();
    expect(c.turnosConciliacion.length).toBe(0);expect(c.mensajeExito).toContain('Turno cerrado');
  });
});
