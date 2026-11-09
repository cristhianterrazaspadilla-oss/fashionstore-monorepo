import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { of, throwError, Subject } from 'rxjs';
import { LandingComponent } from './landing.component';
import { CatalogoService } from '../../catalogo/services/catalogo.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';

describe('LandingComponent (simulador delivery sin errores silenciosos)', () => {
  let component: LandingComponent;
  let fixture: ComponentFixture<LandingComponent>;
  let catalogoSpy: jasmine.SpyObj<CatalogoService>;
  let orgSpy: jasmine.SpyObj<OrganizacionService>;

  const mockSucursales: SucursalDTO[] = [
    {
      id: 'suc-1',
      ciudad_id: 'ciu-1',
      nombre: 'Central',
      direccion: 'Av. Principal #100',
      numero_anillo: 1,
      tarifa_base_delivery: 15,
      incremento_anillo_delivery: 3,
      anillo_minimo_delivery: 1,
      anillo_maximo_delivery: 10,
      delivery_activo: true,
      activa: true
    },
    {
      id: 'suc-2',
      ciudad_id: 'ciu-1',
      nombre: 'Equipetrol',
      direccion: 'Av. Equipetrol #200',
      numero_anillo: 4,
      tarifa_base_delivery: 20,
      incremento_anillo_delivery: 5,
      anillo_minimo_delivery: 1,
      anillo_maximo_delivery: 10,
      delivery_activo: true,
      activa: true
    }
  ];

  beforeEach(async () => {
    catalogoSpy = jasmine.createSpyObj<CatalogoService>('CatalogoService', ['consultarCatalogo']);
    orgSpy = jasmine.createSpyObj<OrganizacionService>('OrganizacionService', ['gestionarSucursales']);
    catalogoSpy.consultarCatalogo.and.returnValue(of([]));
    orgSpy.gestionarSucursales.and.returnValue(of(mockSucursales));

    await TestBed.configureTestingModule({
      imports: [LandingComponent],
      providers: [
        provideRouter([]),
        { provide: CatalogoService, useValue: catalogoSpy },
        { provide: OrganizacionService, useValue: orgSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(LandingComponent);
    component = fixture.componentInstance;
  });

  it('carga exitosa de sucursales y habilita el simulador', () => {
    fixture.detectChanges();

    expect(orgSpy.gestionarSucursales).toHaveBeenCalled();
    expect(component.sucursales.length).toBe(2);
    expect(component.errorSucursales).toBeNull();
    expect(component.cargandoSucursales).toBeFalse();
    expect(component.sucursalDemo?.id).toBe('suc-1');
    expect(component.simuladorDisponible).toBeTrue();
    expect(component.costoDelivery).not.toBeNull();
  });

  it('ante error de red muestra mensaje entendible y no usa valores ficticios', () => {
    orgSpy.gestionarSucursales.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 0, statusText: 'Unknown Error' }))
    );
    fixture.detectChanges();

    expect(component.cargandoSucursales).toBeFalse();
    expect(component.errorSucursales).toContain('simulador');
    expect(component.sucursalDemo).toBeNull();
    expect(component.simuladorDisponible).toBeFalse();
    expect(component.costoDelivery).toBeNull();
  });

  it('presenta el mensaje con role="alert" y botón type="button" para reintentar', () => {
    orgSpy.gestionarSucursales.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 0, statusText: 'Unknown Error' }))
    );
    fixture.detectChanges();

    const alerta: HTMLElement | null = fixture.nativeElement.querySelector('.calc-error[role="alert"]');
    expect(alerta).toBeTruthy();
    expect(alerta?.textContent).toContain('simulador');

    const boton: HTMLButtonElement | null = fixture.nativeElement.querySelector('.calc-error button');
    expect(boton).toBeTruthy();
    expect(boton?.getAttribute('type')).toBe('button');
    expect(boton?.textContent).toContain('Reintentar');

    // Sin sucursal válida no se muestra el costo como si fuera real
    expect(fixture.nativeElement.querySelector('.calc-total')).toBeNull();
  });

  it('permite reintentar y se recupera con éxito después del error', () => {
    orgSpy.gestionarSucursales.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 0, statusText: 'Unknown Error' }))
    );
    fixture.detectChanges();
    expect(component.errorSucursales).not.toBeNull();

    orgSpy.gestionarSucursales.and.returnValue(of(mockSucursales));
    component.cargarSucursales();
    fixture.detectChanges();

    expect(component.errorSucursales).toBeNull();
    expect(component.sucursales.length).toBe(2);
    expect(component.simuladorDisponible).toBeTrue();
    expect(component.costoDelivery).not.toBeNull();
    expect(orgSpy.gestionarSucursales).toHaveBeenCalledTimes(2);
  });

  it('limpia el error anterior al iniciar una nueva carga', () => {
    orgSpy.gestionarSucursales.and.returnValue(
      throwError(() => new HttpErrorResponse({ status: 0, statusText: 'Unknown Error' }))
    );
    fixture.detectChanges();
    expect(component.errorSucursales).not.toBeNull();

    const pendiente = new Subject<SucursalDTO[]>();
    orgSpy.gestionarSucursales.and.returnValue(pendiente.asObservable());
    component.cargarSucursales();

    expect(component.errorSucursales).toBeNull();
    expect(component.cargandoSucursales).toBeTrue();
    pendiente.next(mockSucursales);
    pendiente.complete();
    expect(component.simuladorDisponible).toBeTrue();
  });

  it('previene doble solicitud mientras está cargando', () => {
    const pendiente = new Subject<SucursalDTO[]>();
    // Evita la carga automática del ngOnInit para controlar el escenario
    orgSpy.gestionarSucursales.and.returnValue(pendiente.asObservable());
    // No se ha hecho detectChanges aún en este test, así que el conteo parte en cero
    component.cargarSucursales();
    component.cargarSucursales();
    component.cargarSucursales();

    expect(orgSpy.gestionarSucursales).toHaveBeenCalledTimes(1);

    pendiente.next(mockSucursales);
    pendiente.complete();

    expect(component.cargandoSucursales).toBeFalse();
    expect(component.simuladorDisponible).toBeTrue();

    component.cargarSucursales();
    expect(orgSpy.gestionarSucursales).toHaveBeenCalledTimes(2);
  });
});
