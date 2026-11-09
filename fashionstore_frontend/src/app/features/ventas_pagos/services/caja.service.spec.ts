import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { CajaService, TurnoHabilitacion, VentaOfflineCrear, CLAVE_DISPOSITIVO } from './caja.service';
import { HttpClient } from '@angular/common/http';
import { of } from 'rxjs';
import { AuthService } from '../../identidad_empresas/services/auth.service';

// Integracion del servicio Angular con IndexedDB nativo. HTTP aislado por TestBed.
describe('CajaService: origen durable y privacidad', () => {
  let servicio: CajaService;
  let http: HttpTestingController;
  let usuario: any;
  let privada: boolean;
  const dispositivo = '99999999-8888-4777-8666-555555555555';
  const eliminarDbDePrueba = () => new Promise<void>((resolve, reject) => {
    const r = indexedDB.deleteDatabase('FashionStoreCajaDB');
    r.onsuccess = () => resolve(); r.onerror = () => reject(r.error);
  });
  function turno(): TurnoHabilitacion {
    const ahora = Date.now();
    return { empresa_id: 'empresa-A', turno_id: 'turno-A', habilitacion_id: 'turno-A', cajero_id: 'usuario-A',
      dispositivo_id: dispositivo, sucursal_id: 'sucursal-A', caja_codigo: 'CAJA', estado: 'ABIERTO', revision: 1,
      inicio_en: new Date(ahora - 1000).toISOString(), vence_en: new Date(ahora + 8 * 3600000).toISOString(),
      hora_central_en: new Date(ahora).toISOString(), version_precios: 'v1',
      cupos: [{variante_id: 'v1', otorgado: 1, consumido: 0, liberado: 0, precio_autorizado_bob: 10}] };
  }
  function venta(id = 'operacion-A'): VentaOfflineCrear {
    const fecha = new Date().toISOString();
    return { operacion_id: id, secuencia_local: 0, vendida_local_en: fecha, entregada_local_en: fecha,
      version_precios: 'v1', lineas: [{variante_id: 'v1', cantidad: 1, precio_autorizado_bob: 10}],
      total_bob: 10, efectivo_recibido_bob: 10, cambio_entregado_bob: 0 };
  }
  beforeEach(async () => {
    await eliminarDbDePrueba();
    for (const k of ['fs_turno_caja_activo', 'fs_ventas_offline_pendientes', 'fs_comprobantes_caja_locales']) localStorage.removeItem(k);
    localStorage.setItem(CLAVE_DISPOSITIVO, dispositivo);
    usuario = {empresa_id: 'empresa-A', usuario_id: 'usuario-A', rol: 'CAJERO'}; privada = true;
    TestBed.configureTestingModule({imports: [HttpClientTestingModule], providers: [CajaService,
      {provide: HttpClient, useValue: {get: (url: string) => { const id = url.split('/').pop()!; return of({...turno(), turno_id: id, habilitacion_id: id}); }}},
      {provide: AuthService, useValue: {obtenerUsuarioActual: () => usuario, esVentanaPrivacidadValida: () => privada}}]});
    servicio = TestBed.inject(CajaService); http = TestBed.inject(HttpTestingController);
  });
  afterEach(async () => { http.verify(); await servicio.cerrarBd(); await eliminarDbDePrueba(); });
  it('conserva empresa, usuario, dispositivo, turno y comprobante tras reiniciar', async () => {
    const t = turno(), v = venta(); await servicio.guardarTurnoLocal(t);
    await servicio.registrarVentaOfflineTransaccional(t, v, {operacion_id: v.operacion_id});
    await servicio.cerrarBd();
    expect((await servicio.obtenerVentasOfflinePendientes())[0]['turno_id']).toBe(t.turno_id);
    expect((await servicio.obtenerComprobantesLocales()).length).toBe(1);
    usuario = {...usuario, usuario_id: 'otro'};
    expect((await servicio.obtenerVentasOfflinePendientes()).length).toBe(0);
    expect(await servicio.obtenerTurnoLocal()).toBeNull();
  });
  it('la presencia de sesion sin privacidad no habilita caja', async () => {
    privada = false;
    await expectAsync(servicio.obtenerTurnoLocal()).toBeRejected();
  });
  it('la misma operacion no consume dos veces y el contenido distinto conflictua', async () => {
    const t = turno(), v = venta(); await servicio.guardarTurnoLocal(t);
    await servicio.registrarVentaOfflineTransaccional(t, v, {});
    await servicio.registrarVentaOfflineTransaccional(t, v, {});
    expect((await servicio.obtenerTurnoLocal())!.cupos[0].consumido).toBe(1);
    await expectAsync(servicio.registrarVentaOfflineTransaccional(t, {...v, cliente_id: 'otro'}, {})).toBeRejected();
  });
  it('cupo insuficiente no deja venta parcial', async () => {
    const t = turno(); await servicio.guardarTurnoLocal(t);
    const v = venta(); v.lineas[0].cantidad = 2; v.total_bob = 20; v.efectivo_recibido_bob = 20;
    await expectAsync(servicio.registrarVentaOfflineTransaccional(t, v, {})).toBeRejected();
    expect((await servicio.obtenerVentasOfflinePendientes()).length).toBe(0);
    expect((await servicio.obtenerTurnoLocal())!.cupos[0].consumido).toBe(0);
  });
  it('conserva pendientes del turno anterior al guardar uno nuevo', async () => {
    const t = turno(); await servicio.guardarTurnoLocal(t);
    await servicio.registrarVentaOfflineTransaccional(t, venta(), {});
    await servicio.guardarTurnoLocal({...turno(), turno_id: 'nuevo', habilitacion_id: 'nuevo'});
    expect((await servicio.obtenerVentasOfflinePendientes())[0]['turno_id']).toBe('turno-A');
  });
});
