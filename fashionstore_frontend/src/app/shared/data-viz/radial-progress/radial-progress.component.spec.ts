import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RadialProgressComponent } from './radial-progress.component';

describe('RadialProgressComponent', () => {
  let component: RadialProgressComponent;
  let fixture: ComponentFixture<RadialProgressComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RadialProgressComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(RadialProgressComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('calcula porcentaje y dashoffset seguro para valores normales', () => {
    component.valor = 50;
    component.numerador = 25;
    component.denominador = 50;
    fixture.detectChanges();

    expect(component.porcentajeClamped).toBe(50);
    // Para 50%, offset debe ser exactamente la mitad de la circunferencia
    expect(component.strokeDashoffset).toBeCloseTo(component.circunferencia * 0.5, 2);
    expect(component.textoPrincipal).toBe('50.0%');
    expect(component.textoSubtitulo).toBe('25 de 50 completadas');
  });

  it('maneja de forma segura valores extremos (negativos, cero, mayores a 100)', () => {
    component.valor = -10;
    expect(component.porcentajeClamped).toBe(0);
    expect(component.strokeDashoffset).toBeCloseTo(component.circunferencia, 2);

    component.valor = 150;
    expect(component.porcentajeClamped).toBe(100);
    expect(component.strokeDashoffset).toBeCloseTo(0, 2);
  });

  it('proporciona fallback seguro y accesible cuando el total es cero', () => {
    component.valor = 0;
    component.numerador = 0;
    component.denominador = 0;
    fixture.detectChanges();

    expect(component.textoSubtitulo).toBe('Sin registros en el periodo');
    expect(component.computedAriaLabel).toContain('Sin registros');

    const svg = fixture.nativeElement.querySelector('svg');
    expect(svg.getAttribute('role')).toBe('img');
    expect(svg.getAttribute('aria-label')).toContain('Sin registros');
  });
});
