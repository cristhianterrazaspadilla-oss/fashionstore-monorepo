import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HorizontalBarsComponent, HorizontalBarItem } from './horizontal-bars.component';

describe('HorizontalBarsComponent', () => {
  let component: HorizontalBarsComponent;
  let fixture: ComponentFixture<HorizontalBarsComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HorizontalBarsComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(HorizontalBarsComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('calcula la escala relativa al valor máximo de la lista', () => {
    const items: HorizontalBarItem[] = [
      { etiqueta: 'Producto A', valor: 50 },
      { etiqueta: 'Producto B', valor: 100 }
    ];
    component.items = items;
    fixture.detectChanges();

    expect(component.maximo).toBe(100);
    expect(component.calcularPorcentaje(50)).toBe(50);
    expect(component.calcularPorcentaje(100)).toBe(100);
  });

  it('maneja de forma segura listas vacías o valores máximos iguales a cero', () => {
    component.items = [];
    fixture.detectChanges();
    expect(component.maximo).toBe(0);
    expect(component.calcularPorcentaje(10)).toBe(0);

    const emptyText = fixture.nativeElement.querySelector('.h-bars-empty');
    expect(emptyText).toBeTruthy();
    expect(emptyText.textContent).toContain(component.etiquetaVacio);
  });

  it('respeta un máximo manual si se define', () => {
    component.items = [{ etiqueta: 'Item 1', valor: 20 }];
    component.maximoManual = 80;
    fixture.detectChanges();

    expect(component.maximo).toBe(80);
    expect(component.calcularPorcentaje(20)).toBe(25);
  });

  it('renderiza etiquetas largas y valores formateados sin truncamiento destructivo', () => {
    component.items = [
      {
        etiqueta: 'Vestido Largo de Seda Noir Edición Limitada',
        valor: 12000.5,
        valorFormateado: 'Bs 12.000,50',
        subtitulo: '15 transacciones'
      }
    ];
    component.mostrarPosicion = true;
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Vestido Largo de Seda');
    expect(compiled.textContent).toContain('Bs 12.000,50');
    expect(compiled.textContent).toContain('15 transacciones');
    expect(compiled.querySelector('.h-bar-pos')?.textContent).toContain('1');
  });
});
