import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { provideRouter } from '@angular/router';
import { ReembolsosComponent } from './reembolsos.component';
import { ReembolsoService } from '../services/reembolso.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { ReembolsoDetalleDTO } from '../models/reembolso.models';

describe('Reembolsos: contrato real y ambitos de consulta', () => {
  let component: ReembolsosComponent;
  let fixture: ComponentFixture<ReembolsosComponent>;
  let servicio: jasmine.SpyObj<ReembolsoService>;
  let auth: jasmine.SpyObj<AuthService>;
  const id = '10000000-0000-4000-8000-000000000001';
  const respuesta: ReembolsoDetalleDTO = {
    id, empresa_id: '10000000-0000-4000-8000-000000000002',
    cliente_id: '10000000-0000-4000-8000-000000000003',
    origen_tipo: 'VENTA', origen_id: '10000000-0000-4000-8000-000000000004',
    estado: 'PENDIENTE_AUTORIZACION', monto_bob: '180.00', revision: 1,
    motivo_codigo: 'DEFECTO_FABRICA', creada_en: '2026-11-04T13:00:00Z',
    componentes: [
      { id, medio: 'STRIPE', monto_bob: '100.00', estado: 'PENDIENTE' },
      { id: '10000000-0000-4000-8000-000000000005', medio: 'SALDO', monto_bob: '80.00', estado: 'PENDIENTE' }
    ]
  };

  beforeEach(async () => {
    servicio = jasmine.createSpyObj('ReembolsoService', ['listarMios', 'consultar', 'solicitar', 'autorizar', 'ejecutar']);
    auth = jasmine.createSpyObj('AuthService', ['obtenerUsuarioActual']);
    auth.obtenerUsuarioActual.and.returnValue({ rol: 'CLIENTE' } as any);
    servicio.listarMios.and.returnValue(of([respuesta]));
    servicio.consultar.and.returnValue(of(respuesta));
    await TestBed.configureTestingModule({
      imports: [ReembolsosComponent],
      providers: [provideRouter([]),
        { provide: ReembolsoService, useValue: servicio }, { provide: AuthService, useValue: auth }]
    }).compileComponents();
    fixture = TestBed.createComponent(ReembolsosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('renderiza id/fecha y todos los medios reales; filtra por cualquiera de ellos', () => {
    expect(servicio.listarMios).toHaveBeenCalled();
    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain(component.bs('100.00'));
    expect(texto).toContain(component.bs('80.00'));
    component.filtroMedio = 'SALDO';
    expect(component.reembolsosFiltrados[0].id).toBe(id);
    component.filtroEstado = 'PENDIENTE_AUTORIZACION';
    expect(component.reembolsosFiltrados.length).toBe(1);
  });

  it('consulta administrativa individual separada del listado personal', () => {
    auth.obtenerUsuarioActual.and.returnValue({ rol: 'ADMINISTRADOR' } as any);
    component.idConsulta = id;
    component.consultarAdministrativo();
    expect(servicio.consultar).toHaveBeenCalledWith(id);
    expect(component.consultaAdministrativa).toBeTrue();
    component.verMisReembolsos();
    expect(component.consultaAdministrativa).toBeFalse();
  });

  it('no habilita acciones comerciales de plataforma ni consulta administrativa para cliente', () => {
    component.idConsulta = id;
    component.consultarAdministrativo();
    expect(servicio.consultar).not.toHaveBeenCalled();
    auth.obtenerUsuarioActual.and.returnValue({ rol: 'SUPERADMIN' } as any);
    component.iniciarAutorizacion(respuesta);
    expect(component.esPersonal).toBeFalse();
    expect(component.dialogoConfirmarVisible).toBeFalse();
  });

  it('rechaza numeros de pedido sin UUID y acepta un numero de VENTA para resolverlo en el servicio', () => {
    component.abrirModalSolicitud('PED-0001', 'PEDIDO');
    component.enviarSolicitud();
    expect(servicio.solicitar).not.toHaveBeenCalled();
    servicio.solicitar.and.returnValue(of(respuesta));
    component.abrirModalSolicitud('VNT-0001', 'VENTA');
    component.enviarSolicitud();
    expect(servicio.solicitar).toHaveBeenCalledWith(jasmine.objectContaining({ origen_id: 'VNT-0001', origen_tipo: 'VENTA' }));
  });

  it('utiliza id real para autorizar y no comunica completado si la ejecucion sigue EN_PROCESO', () => {
    auth.obtenerUsuarioActual.and.returnValue({ rol: 'ENCARGADO' } as any);
    servicio.autorizar.and.returnValue(of({ ...respuesta, estado: 'AUTORIZADO' }));
    component.iniciarAutorizacion(respuesta);
    component.confirmarAccion();
    expect(servicio.autorizar).toHaveBeenCalledWith(id, jasmine.any(Object));
    servicio.ejecutar.and.returnValue(of({ ...respuesta, estado: 'EN_PROCESO' }));
    component.iniciarEjecucion({ ...respuesta, estado: 'AUTORIZADO' });
    component.confirmarAccion();
    expect(servicio.ejecutar).toHaveBeenCalledWith(id);
    expect(component.exito).toContain('Consulta el estado');
  });
});
