import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AplicarSaldoDialogComponent } from './aplicar-saldo-dialog.component';

describe('AplicarSaldoDialogComponent (Modal Accesible para Aplicar Saldo)', () => {
  let component: AplicarSaldoDialogComponent;
  let fixture: ComponentFixture<AplicarSaldoDialogComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AplicarSaldoDialogComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(AplicarSaldoDialogComponent);
    component = fixture.componentInstance;
  });

  it('debe crearse correctamente', () => {
    expect(component).toBeTruthy();
    expect(component.visible).toBeFalse();
  });

  it('debe calcular saldo remanente y restante por pagar correctamente', () => {
    component.visible = true;
    component.totalPorPagar = 200;
    component.saldoDisponible = 80;
    component.montoAplicar = 50;
    fixture.detectChanges();

    expect(component.restantePorPagar).toBe(150);
    expect(component.saldoRemanente).toBe(30);
  });

  it('debe validar que el monto no supere el saldo disponible ni el total a pagar', () => {
    component.visible = true;
    component.totalPorPagar = 100;
    component.saldoDisponible = 50;

    component.montoAplicar = 60; // Mayor que saldo
    expect(component.validarMonto()).toBeFalse();
    expect(component.errorValidacion).toContain('saldo disponible');

    component.saldoDisponible = 150;
    component.montoAplicar = 120; // Mayor que total
    expect(component.validarMonto()).toBeFalse();
    expect(component.errorValidacion).toContain('total a pagar');

    component.montoAplicar = 50; // Válido
    expect(component.validarMonto()).toBeTrue();
    expect(component.errorValidacion).toBe('');
  });

  it('debe emitir el monto seleccionado al confirmar', () => {
    spyOn(component.aplicar, 'emit');
    component.visible = true;
    component.totalPorPagar = 100;
    component.saldoDisponible = 100;
    component.montoAplicar = 40;

    component.confirmar();
    expect(component.aplicar.emit).toHaveBeenCalledWith(40);
  });

  it('debe emitir cerrar al pulsar cancelar o presionar Escape', () => {
    spyOn(component.cerrar, 'emit');
    component.visible = true;

    component.cancelar();
    expect(component.cerrar.emit).toHaveBeenCalled();

    const escEvent = new KeyboardEvent('keydown', { key: 'Escape' });
    component.onKeydown(escEvent);
    expect(component.cerrar.emit).toHaveBeenCalledTimes(2);
  });
});
