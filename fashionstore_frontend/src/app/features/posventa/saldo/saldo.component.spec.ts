import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { provideRouter } from '@angular/router';
import { SaldoComponent } from './saldo.component';
import { SaldoService } from '../services/saldo.service';
import { SaldoResumenDTO } from '../models/saldo.models';

describe('SaldoComponent (Consulta de Saldo Propio y Movimientos)', () => {
  let component: SaldoComponent;
  let fixture: ComponentFixture<SaldoComponent>;
  let saldoServiceSpy: jasmine.SpyObj<SaldoService>;

  const mockResumen: SaldoResumenDTO = {
    saldo_disponible_bob: '150.00',
    saldo_retenido_bob: '20.00',
    saldo_total_bob: '170.00',
    movimientos: [
      {
        id: 'mov-1',
        tipo: 'CREDITO',
        monto_bob: '150.00',
        saldo_resultante_bob: '150.00',
        motivo: 'Devolución de prenda por cambio de talla',
        creado_en: '2026-11-04T10:00:00-04:00'
      },
      {
        id: 'mov-2',
        tipo: 'RETENCION',
        monto_bob: '20.00',
        saldo_resultante_bob: '130.00',
        motivo: 'Retención para reserva en tienda',
        creado_en: '2026-11-04T11:00:00-04:00'
      },
      {
        id: 'mov-3',
        tipo: 'DEBITO',
        monto_bob: '50.00',
        saldo_resultante_bob: '80.00',
        motivo: 'Pago aplicado a compra online',
        creado_en: '2026-11-04T12:00:00-04:00'
      }
    ]
  };

  beforeEach(async () => {
    saldoServiceSpy = jasmine.createSpyObj<SaldoService>('SaldoService', ['obtenerMiSaldo']);

    await TestBed.configureTestingModule({
      imports: [SaldoComponent],
      providers: [
        provideRouter([]),
        { provide: SaldoService, useValue: saldoServiceSpy }
      ]
    }).compileComponents();
  });

  it('debe crearse y cargar el resumen de saldo exitosamente', () => {
    saldoServiceSpy.obtenerMiSaldo.and.returnValue(of(mockResumen));
    fixture = TestBed.createComponent(SaldoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    expect(component).toBeTruthy();
    expect(component.cargando).toBeFalse();
    expect(component.resumen).toEqual(mockResumen);
    expect(component.movimientosFiltrados.length).toBe(3);
  });

  it('debe filtrar movimientos por tipo', () => {
    saldoServiceSpy.obtenerMiSaldo.and.returnValue(of(mockResumen));
    fixture = TestBed.createComponent(SaldoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    component.filtroTipo = 'CREDITO';
    expect(component.movimientosFiltrados.length).toBe(1);
    expect(component.movimientosFiltrados[0].id).toBe('mov-1');

    component.filtroTipo = 'DEBITO';
    expect(component.movimientosFiltrados.length).toBe(1);
    expect(component.movimientosFiltrados[0].id).toBe('mov-3');
  });

  it('debe filtrar movimientos por término de búsqueda en motivo', () => {
    saldoServiceSpy.obtenerMiSaldo.and.returnValue(of(mockResumen));
    fixture = TestBed.createComponent(SaldoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    component.terminoBusqueda = 'reserva';
    expect(component.movimientosFiltrados.length).toBe(1);
    expect(component.movimientosFiltrados[0].tipo).toBe('RETENCION');
  });

  it('debe manejar error al consultar saldo y permitir reintento', () => {
    saldoServiceSpy.obtenerMiSaldo.and.returnValue(throwError(() => new Error('Error de red')));
    fixture = TestBed.createComponent(SaldoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();

    expect(component.cargando).toBeFalse();
    expect(component.error).toBeTruthy();

    saldoServiceSpy.obtenerMiSaldo.and.returnValue(of(mockResumen));
    component.cargarSaldo();
    expect(component.cargando).toBeFalse();
    expect(component.error).toBeNull();
    expect(component.resumen).toEqual(mockResumen);
  });
});
