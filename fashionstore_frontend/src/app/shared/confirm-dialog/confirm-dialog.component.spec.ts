import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { ConfirmDialogComponent } from './confirm-dialog.component';

describe('ConfirmDialogComponent (Accesibilidad, Focus Trap y Scroll Lock)', () => {
  let component: ConfirmDialogComponent;
  let fixture: ComponentFixture<ConfirmDialogComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmDialogComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(ConfirmDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    component.ngOnDestroy();
    document.body.classList.remove('modal-open');
  });

  // 1. No renderiza el diálogo cuando abierto=false
  it('1. no renderiza el diálogo cuando abierto=false', () => {
    component.abierto = false;
    fixture.detectChanges();

    const backdrop = fixture.nativeElement.querySelector('.dialog-backdrop');
    expect(backdrop).toBeNull();
  });

  // 2. Renderiza role="alertdialog" y aria-modal="true" al abrir
  it('2. renderiza role="alertdialog" y aria-modal="true" al abrir', () => {
    component.abierto = true;
    fixture.detectChanges();

    const dialog = fixture.nativeElement.querySelector('[role="alertdialog"]');
    expect(dialog).not.toBeNull();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
  });

  // 3. La transición false -> true coloca el foco dentro del diálogo
  it('3. la transición false -> true coloca el foco dentro del diálogo', fakeAsync(() => {
    component.abierto = false;
    fixture.detectChanges();

    component.abierto = true;
    fixture.detectChanges();
    tick(60);

    expect(component.cancelButton?.nativeElement).toBeDefined();
    expect(document.activeElement).toBe(component.cancelButton!.nativeElement);
  }));

  // 4. Tab desde el último control vuelve al primero
  it('4. Tab desde el último control vuelve al primero', () => {
    component.abierto = true;
    fixture.detectChanges();

    const cancelBtn = component.cancelButton!.nativeElement;
    const confirmBtn = component.confirmButton!.nativeElement;

    confirmBtn.focus();
    expect(document.activeElement).toBe(confirmBtn);

    const tabEvent = new KeyboardEvent('keydown', {
      key: 'Tab',
      shiftKey: false,
      bubbles: true,
      cancelable: true
    });
    component.manejarTeclado(tabEvent);

    expect(tabEvent.defaultPrevented).toBeTrue();
    expect(document.activeElement).toBe(cancelBtn);
  });

  // 5. Shift+Tab desde el primero vuelve al último
  it('5. Shift+Tab desde el primero vuelve al último', () => {
    component.abierto = true;
    fixture.detectChanges();

    const cancelBtn = component.cancelButton!.nativeElement;
    const confirmBtn = component.confirmButton!.nativeElement;

    cancelBtn.focus();
    expect(document.activeElement).toBe(cancelBtn);

    const shiftTabEvent = new KeyboardEvent('keydown', {
      key: 'Tab',
      shiftKey: true,
      bubbles: true,
      cancelable: true
    });
    component.manejarTeclado(shiftTabEvent);

    expect(shiftTabEvent.defaultPrevented).toBeTrue();
    expect(document.activeElement).toBe(confirmBtn);
  });

  // 6. Escape emite cancelar
  it('6. Escape emite cancelar cuando no está procesando', () => {
    component.abierto = true;
    component.procesando = false;
    fixture.detectChanges();

    spyOn(component.cancelar, 'emit');

    const escapeEvent = new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true
    });
    component.manejarTeclado(escapeEvent);

    expect(escapeEvent.defaultPrevented).toBeTrue();
    expect(component.cancelar.emit).toHaveBeenCalled();
  });

  // 7. Backdrop emite cancelar
  it('7. Backdrop emite cancelar cuando no está procesando', () => {
    component.abierto = true;
    component.procesando = false;
    fixture.detectChanges();

    spyOn(component.cancelar, 'emit');

    const backdropEl: HTMLElement = fixture.nativeElement.querySelector('.dialog-backdrop');
    expect(backdropEl).not.toBeNull();

    const mockEvent = {
      target: backdropEl,
      stopPropagation: () => {}
    } as unknown as MouseEvent;

    component.onBackdropClick(mockEvent);

    expect(component.cancelar.emit).toHaveBeenCalled();
  });

  // 8. No permite Escape, backdrop, cancelar ni confirmar durante procesando=true
  it('8. no permite Escape, backdrop, cancelar ni confirmar durante procesando=true', () => {
    component.abierto = true;
    component.procesando = true;
    fixture.detectChanges();

    spyOn(component.cancelar, 'emit');
    spyOn(component.confirmar, 'emit');

    // Escape ignorado
    const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    component.manejarTeclado(escapeEvent);
    expect(component.cancelar.emit).not.toHaveBeenCalled();

    // Backdrop click ignorado
    const backdropEl: HTMLElement = fixture.nativeElement.querySelector('.dialog-backdrop');
    const mockBackdropEvent = { target: backdropEl } as unknown as MouseEvent;
    component.onBackdropClick(mockBackdropEvent);
    expect(component.cancelar.emit).not.toHaveBeenCalled();

    // Invocaciones directas bloqueadas
    component.onCancelar();
    expect(component.cancelar.emit).not.toHaveBeenCalled();

    component.onConfirmar();
    expect(component.confirmar.emit).not.toHaveBeenCalled();

    // Botones deshabilitados en template
    expect(component.cancelButton!.nativeElement.disabled).toBeTrue();
    expect(component.confirmButton!.nativeElement.disabled).toBeTrue();
  });

  // 9. Restaura el foco al disparador al cerrar
  it('9. restaura el foco al disparador al cerrar', fakeAsync(() => {
    const triggerBtn = document.createElement('button');
    triggerBtn.id = 'test-trigger-btn';
    document.body.appendChild(triggerBtn);
    triggerBtn.focus();
    expect(document.activeElement).toBe(triggerBtn);

    component.abierto = true;
    fixture.detectChanges();
    tick(60);
    expect(document.activeElement).toBe(component.cancelButton!.nativeElement);

    component.abierto = false;
    fixture.detectChanges();
    tick(60);

    expect(document.activeElement).toBe(triggerBtn);
    document.body.removeChild(triggerBtn);
  }));

  // 10. Bloquea el scroll al abrir
  it('10. bloquea el scroll de body al abrir', () => {
    component.abierto = true;
    fixture.detectChanges();

    expect(document.body.classList.contains('modal-open')).toBeTrue();
  });

  // 11. Desbloquea el scroll al cerrar o destruir
  it('11. desbloquea el scroll al cerrar o destruir', () => {
    component.abierto = true;
    fixture.detectChanges();
    expect(document.body.classList.contains('modal-open')).toBeTrue();

    component.abierto = false;
    fixture.detectChanges();
    expect(document.body.classList.contains('modal-open')).toBeFalse();

    // Abrir nuevamente y destruir
    component.abierto = true;
    fixture.detectChanges();
    expect(document.body.classList.contains('modal-open')).toBeTrue();

    component.ngOnDestroy();
    expect(document.body.classList.contains('modal-open')).toBeFalse();
  });

  // 12. Abrir y cerrar varias veces no desbalancea el contador de overlays
  it('12. abrir y cerrar varias veces no desbalancea el contador de overlays', () => {
    for (let i = 0; i < 3; i++) {
      component.abierto = true;
      fixture.detectChanges();
      expect(document.body.classList.contains('modal-open')).toBeTrue();

      component.abierto = false;
      fixture.detectChanges();
      expect(document.body.classList.contains('modal-open')).toBeFalse();
    }

    // Una apertura adicional debe bloquearlo y un cierre final debe limpiarlo
    component.abierto = true;
    fixture.detectChanges();
    expect(document.body.classList.contains('modal-open')).toBeTrue();

    component.abierto = false;
    fixture.detectChanges();
    expect(document.body.classList.contains('modal-open')).toBeFalse();
  });
});
