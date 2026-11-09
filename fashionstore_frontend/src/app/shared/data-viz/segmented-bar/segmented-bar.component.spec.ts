import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SegmentedBarComponent, SegmentoItem } from './segmented-bar.component';

describe('SegmentedBarComponent', () => {
  let component: SegmentedBarComponent;
  let fixture: ComponentFixture<SegmentedBarComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SegmentedBarComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(SegmentedBarComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('calcula la distribución proporcional entre segmentos', () => {
    const segmentos: SegmentoItem[] = [
      { etiqueta: 'Con promoción', valor: 20, colorClase: 'color-brass' },
      { etiqueta: 'Sin promoción', valor: 80, colorClase: 'color-ink' }
    ];
    component.segmentos = segmentos;
    fixture.detectChanges();

    expect(component.total).toBe(100);
    expect(component.porcentajeSegmento(segmentos[0])).toBe(20);
    expect(component.porcentajeSegmento(segmentos[1])).toBe(80);
    expect(component.computedAriaLabel).toContain('Con promoción: 20 (20.0%)');
  });

  it('maneja de forma segura un total de cero sin dividir por cero', () => {
    component.segmentos = [
      { etiqueta: 'Con promoción', valor: 0, colorClase: 'color-brass' },
      { etiqueta: 'Sin promoción', valor: 0, colorClase: 'color-ink' }
    ];
    fixture.detectChanges();

    expect(component.total).toBe(0);
    expect(component.porcentajeSegmento(component.segmentos[0])).toBe(0);

    const empty = fixture.nativeElement.querySelector('.seg-empty');
    expect(empty).toBeTruthy();
    expect(empty.textContent).toContain(component.etiquetaVacio);
  });
});
