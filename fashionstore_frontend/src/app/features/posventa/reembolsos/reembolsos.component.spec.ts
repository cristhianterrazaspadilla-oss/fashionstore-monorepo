import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { provideRouter } from '@angular/router';
import { ReembolsosComponent } from './reembolsos.component';
import { ReembolsoService } from '../services/reembolso.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { ReembolsoDetalleDTO } from '../models/reembolso.models';

describe('ReembolsosComponent (Solicitud y Seguimiento de Reembolsos por Medio Original)', () => {
  let component: ReembolsosComponent;
  let fixture: ComponentFixture<ReembolsosComponent>;
  let reembolsoServiceSpy: jasmine.SpyObj<ReembolsoService>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;

  const mockReembolsos: ReembolsoDetalleDTO[] = [
    {
      reembolso_id: 'rem-1',
      estado: 'SOLICITADO',
      monto_bob: '180.00',
      medio_original: 'STRIPE',
      motivo_codigo: 'DEFECTO_FABRICA',
      motivo_descripcion: 'Costura descosida en manga',
      creado_en: '2026-11-04T09:00:00-04:00'
    },
    {
      reembolso_id: 'rem-2',
      estado: 'AUTORIZADO',
      monto_bob: '120.00',
      medio_original: 'SALDO',
      motivo_codigo: 'DIFERENCIA_CAMBIO',
      motivo_descripcion: 'Diferencia a favor por cambio de prenda',
      creado_en: '2026-11-04T10:00:00-04:00'
    },
    {
      reembolso_id: 'rem-3',
      estado: 'COMPLETADO',
      monto_bob: '90.00',
      medio_original: 'EFECTIVO',
      motivo_codigo: 'DISCONFORMIDAD_TALLA',
      motivo_descripcion: 'Devolución física en caja',
      creado_en: '2026-11-04T11:00:00-04:00'
    }
  ];

  beforeEach(async () => {
    reembolsoServiceSpy = jasmine.createSpyObj<ReembolsoService>('ReembolsoService', [
      'listar',
      'solicitar',
      'autorizar',
      'ejecutar',
      'conciliar'
    ]);
    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', ['obtenerUsuarioActual']);

    await TestBed.configureTestingModule({
      imports: [ReembolsosComponent],
      providers: [
        provideRouter([]),
        { provide: ReembolsoService, useValue: reembolsoServiceSpy },
        { provide: AuthService, useValue: authServiceSpy }
      ]
    }).compileComponents();
  });

  it('debe listar reembolsos y mostrar la tarjeta con el medio original', () => {
    authServiceSpy.obtenerUsuarioActual.and.returnValue({ rol: 'CLIENTE' } as any);
    reembolsoServiceSpy.listar.and.returnValue(of(mockReembolsos));

    fixture = TestBed.createComponent(ReembolsosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    expect(component).toBeTruthy();
    expect(component.cargando).toBeFalse();
    expect(component.reembolsosFiltrados.length).toBe(3);
    expect(component.reembolsosFiltrados[0].medio_original).toBe('STRIPE');
  });

  it('debe filtrar por estado y medio original', () => {
    authServiceSpy.obtenerUsuarioActual.and.returnValue({ rol: 'CLIENTE' } as any);
    reembolsoServiceSpy.listar.and.returnValue(of(mockReembolsos));

    fixture = TestBed.createComponent(ReembolsosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    component.filtroEstado = 'SOLICITADO';
    expect(component.reembolsosFiltrados.length).toBe(1);
    expect(component.reembolsosFiltrados[0].reembolso_id).toBe('rem-1');

    component.filtroEstado = 'TODOS';
    component.filtroMedio = 'SALDO';
    expect(component.reembolsosFiltrados.length).toBe(1);
    expect(component.reembolsosFiltrados[0].reembolso_id).toBe('rem-2');
  });

  it('debe permitir solicitar un nuevo reembolso con validación', () => {
    authServiceSpy.obtenerUsuarioActual.and.returnValue({ rol: 'CLIENTE' } as any);
    reembolsoServiceSpy.listar.and.returnValue(of(mockReembolsos));
    reembolsoServiceSpy.solicitar.and.returnValue(of(mockReembolsos[0]));

    fixture = TestBed.createComponent(ReembolsosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    component.abrirModalSolicitud('VNT-0001');
    expect(component.modalSolicitudAbierto).toBeTrue();
    expect(component.solicitud.origen_id).toBe('VNT-0001');

    component.enviarSolicitud();
    expect(reembolsoServiceSpy.solicitar).toHaveBeenCalled();
    expect(component.modalSolicitudAbierto).toBeFalse();
    expect(component.exito).toBeTruthy();
  });

  it('debe permitir a personal administrativo autorizar y ejecutar un reembolso', () => {
    authServiceSpy.obtenerUsuarioActual.and.returnValue({ rol: 'ADMINISTRADOR' } as any);
    reembolsoServiceSpy.listar.and.returnValue(of(mockReembolsos));
    reembolsoServiceSpy.autorizar.and.returnValue(of({ ...mockReembolsos[0], estado: 'AUTORIZADO' }));

    fixture = TestBed.createComponent(ReembolsosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    expect(component.esPersonal).toBeTrue();

    // Iniciar autorización
    component.iniciarAutorizacion(mockReembolsos[0]);
    expect(component.dialogoConfirmarVisible).toBeTrue();
    expect(component.accionPendiente).toBe('AUTORIZAR');

    component.confirmarAccion();
    expect(reembolsoServiceSpy.autorizar).toHaveBeenCalledWith('rem-1', jasmine.any(Object));
  });
});
