import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { PromocionesComponent } from './promociones.component';
import { PromocionService } from '../services/promocion.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { EnriquecimientoService } from '../services/enriquecimiento.service';
import { PromocionDTO } from '../models/gestion-catalogo.models';

describe('PromocionesComponent (CRUD, Asociación de Variantes y Accesibilidad)', () => {
  let component: PromocionesComponent;
  let fixture: ComponentFixture<PromocionesComponent>;

  let promoServiceSpy: jasmine.SpyObj<PromocionService>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let enriquecimientoServiceSpy: jasmine.SpyObj<EnriquecimientoService>;

  const mockPromo: PromocionDTO = {
    id: 'promo-1',
    codigo: 'VERANO2026',
    nombre: 'Descuento Temporada Verano',
    descripcion: '20% off en prendas seleccionadas',
    tipo: 'PORCENTAJE',
    valor: 20,
    activa: true,
    vigencia_inicio: '2026-12-01T00:00:00Z',
    vigencia_fin: '2026-12-31T23:59:59Z',
    creada_en: '2026-09-01T00:00:00Z',
    variante_ids: ['var-1']
  };

  beforeEach(async () => {
    promoServiceSpy = jasmine.createSpyObj<PromocionService>('PromocionService', [
      'listar', 'obtener', 'crear', 'actualizar', 'eliminar', 'asociarVariantes', 'desasociarVariante'
    ]);
    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', ['obtenerUsuarioActual']);
    enriquecimientoServiceSpy = jasmine.createSpyObj<EnriquecimientoService>('EnriquecimientoService', [
      'obtenerVariante', 'listarVariantesBuscables'
    ]);

    promoServiceSpy.listar.and.returnValue(of({ total: 1, limit: 50, offset: 0, items: [mockPromo] }));
    authServiceSpy.obtenerUsuarioActual.and.returnValue({
      id: 'adm-1',
      usuario_id: 'adm-1',
      nombres: 'Admin',
      apellidos: 'Principal',
      nombre_completo: 'Admin Principal',
      correo_electronico: 'admin@fs.com',
      rol: 'ADMINISTRADOR',
      estado: 'ACTIVO',
      preferencias: {},
      creado_en: '2026-01-01'
    });
    enriquecimientoServiceSpy.obtenerVariante.and.returnValue(of({
      variante_id: 'var-1',
      sku: 'SKU-01',
      precio: 100,
      producto_id: 'p-1',
      nombre_producto: 'Prenda Test',
      talla_nombre: 'M',
      color_nombre: 'Azul',
      imagen_url: ''
    }));
    enriquecimientoServiceSpy.listarVariantesBuscables.and.returnValue(of([
      {
        variante_id: 'var-2',
        sku: 'SKU-02',
        precio: 150,
        producto_id: 'p-2',
        nombre_producto: 'Blusa Seda',
        talla_nombre: 'S',
        color_nombre: 'Negro',
        imagen_url: ''
      }
    ]));

    await TestBed.configureTestingModule({
      imports: [PromocionesComponent],
      providers: [
        { provide: PromocionService, useValue: promoServiceSpy },
        { provide: AuthService, useValue: authServiceSpy },
        { provide: EnriquecimientoService, useValue: enriquecimientoServiceSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(PromocionesComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    component.ngOnDestroy();
  });

  it('carga la lista de promociones y detecta rol Administrador', () => {
    expect(component.promociones.length).toBe(1);
    expect(component.esAdmin).toBeTrue();
    expect(component.cargando).toBeFalse();
  });

  describe('Creación y Edición de Promociones', () => {
    it('abre modal de creación con campos limpios y bloquea scroll de body', () => {
      component.abrirCrear();

      expect(component.dialogAbierto).toBeTrue();
      expect(component.editando).toBeNull();
      expect(document.body.classList.contains('modal-open')).toBeTrue();
      expect(component.promoForm.controls.codigo.enabled).toBeTrue();
    });

    it('abre modal de edición con código deshabilitado y valores poblados', () => {
      component.abrirEditar(mockPromo);

      expect(component.dialogAbierto).toBeTrue();
      expect(component.editando).toEqual(mockPromo);
      expect(component.promoForm.controls.codigo.disabled).toBeTrue();
      expect(component.promoForm.controls.nombre.value).toBe('Descuento Temporada Verano');
    });

    it('valida que el porcentaje no supere el 100%', () => {
      component.abrirCrear();
      component.promoForm.controls.tipo.setValue('PORCENTAJE');
      component.promoForm.controls.valor.setValue(150);

      expect(component.validarFechasVigencia()).toBeFalse();
      expect(component.errorVigencia).toContain('no puede superar el 100%');
    });

    it('valida que la fecha de inicio no sea posterior a la fecha de fin', () => {
      component.abrirCrear();
      component.promoForm.controls.vigencia_inicio.setValue('2026-12-31T00:00');
      component.promoForm.controls.vigencia_fin.setValue('2026-12-01T00:00');

      expect(component.validarFechasVigencia()).toBeFalse();
      expect(component.errorVigencia).toContain('no puede ser posterior');
    });

    it('envía null al limpiar descripción o vigencia_fin al actualizar', () => {
      component.abrirEditar(mockPromo);
      component.promoForm.controls.nombre.setValue('Promo Verano Editada');
      component.promoForm.controls.descripcion.setValue('   ');
      component.promoForm.controls.vigencia_fin.setValue('');

      promoServiceSpy.actualizar.and.returnValue(of(mockPromo));
      component.guardar();

      expect(promoServiceSpy.actualizar).toHaveBeenCalled();
      const dto = promoServiceSpy.actualizar.calls.mostRecent().args[1];
      expect(dto.nombre).toBe('Promo Verano Editada');
      expect(dto.descripcion).toBeNull();
      expect(dto.vigencia_fin).toBeNull();
      expect(document.body.classList.contains('modal-open')).toBeFalse();
    });

    it('cierra el diálogo al pulsar tecla Escape si no se está guardando', () => {
      component.abrirCrear();
      expect(component.dialogAbierto).toBeTrue();

      const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape' });
      component.alPresionarTecla(escapeEvent);

      expect(component.dialogAbierto).toBeFalse();
      expect(document.body.classList.contains('modal-open')).toBeFalse();
    });

    it('protege el diálogo de promoción durante guardado (botón × deshabilitado, métodos, Escape y backdrop inertes)', () => {
      component.abrirCrear();
      fixture.detectChanges();

      component.guardando = true;
      fixture.detectChanges();

      // Botón × deshabilitado con aria-disabled
      const closeBtn = fixture.nativeElement.querySelector('.promo-form-dialog .btn-close-modal');
      expect(closeBtn).not.toBeNull();
      expect(closeBtn.disabled).toBeTrue();
      expect(closeBtn.getAttribute('aria-disabled')).toBe('true');

      // Invocación directa a cerrarDialog ignorada
      component.cerrarDialog();
      expect(component.dialogAbierto).toBeTrue();

      // Escape ignorado
      const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape' });
      component.alPresionarTecla(escapeEvent);
      expect(component.dialogAbierto).toBeTrue();

      // Backdrop click ignorado
      const backdrop = fixture.nativeElement.querySelector('.dialog-backdrop');
      backdrop.click();
      expect(component.dialogAbierto).toBeTrue();
      expect(document.body.classList.contains('modal-open')).toBeTrue();
    });
  });

  describe('Asociación de Variantes', () => {
    it('abre modal asociar y carga prendas disponibles con selector', () => {
      component.abrirAsociar(mockPromo);

      expect(component.asociarDialogAbierto).toBeTrue();
      expect(component.asociarPromocion).toEqual(mockPromo);
      expect(document.body.classList.contains('modal-open')).toBeTrue();
      expect(enriquecimientoServiceSpy.listarVariantesBuscables).toHaveBeenCalled();
      expect(component.variantesDisponibles.length).toBe(1);
    });

    it('protege el diálogo de asociar mientras se procesa la asociación (botón ×, métodos, Escape y backdrop)', () => {
      component.abrirAsociar(mockPromo);
      fixture.detectChanges();

      component.asociando = true;
      fixture.detectChanges();

      // Botón × deshabilitado
      const closeBtn = fixture.nativeElement.querySelector('.asociar-dialog .btn-close-modal');
      expect(closeBtn).not.toBeNull();
      expect(closeBtn.disabled).toBeTrue();
      expect(closeBtn.getAttribute('aria-disabled')).toBe('true');

      // Invocación a cerrarAsociar ignorada
      component.cerrarAsociar();
      expect(component.asociarDialogAbierto).toBeTrue();

      // Escape ignorado
      const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape' });
      component.alPresionarTecla(escapeEvent);
      expect(component.asociarDialogAbierto).toBeTrue();

      // Backdrop click ignorado
      const backdrop = fixture.nativeElement.querySelector('.dialog-backdrop');
      backdrop.click();
      expect(component.asociarDialogAbierto).toBeTrue();
      expect(document.body.classList.contains('modal-open')).toBeTrue();
    });

    it('asocia una prenda y actualiza la lista', () => {
      component.abrirAsociar(mockPromo);
      component.varianteSeleccionadaId = 'var-2';

      promoServiceSpy.asociarVariantes.and.returnValue(of(mockPromo));
      component.asociar();

      expect(promoServiceSpy.asociarVariantes).toHaveBeenCalledWith('promo-1', { variante_ids: ['var-2'] });
      expect(component.exito).toContain('asociada');
    });

    it('desasocia una prenda y llama al servicio de desasociación', () => {
      component.abrirAsociar(mockPromo);

      promoServiceSpy.desasociarVariante.and.returnValue(of(mockPromo));
      component.desasociar('var-1');

      expect(promoServiceSpy.desasociarVariante).toHaveBeenCalledWith('promo-1', 'var-1');
    });
  });

  describe('Eliminación con Diálogo Accesible', () => {
    it('solicita confirmación accesible antes de eliminar', () => {
      component.solicitarEliminar(mockPromo);

      expect(component.dialogEliminarAbierto).toBeTrue();
      expect(component.promocionAEliminar).toEqual(mockPromo);
      fixture.detectChanges();
      expect(document.body.classList.contains('modal-open')).toBeTrue();

      promoServiceSpy.eliminar.and.returnValue(of(undefined));
      component.confirmarEliminar();

      expect(promoServiceSpy.eliminar).toHaveBeenCalledWith('promo-1');
      expect(component.dialogEliminarAbierto).toBeFalse();
      fixture.detectChanges();
      expect(document.body.classList.contains('modal-open')).toBeFalse();
    });

    it('cancela la eliminación restaurando estado y foco', () => {
      component.solicitarEliminar(mockPromo);
      expect(component.dialogEliminarAbierto).toBeTrue();
      fixture.detectChanges();

      component.cancelarEliminar();
      expect(component.dialogEliminarAbierto).toBeFalse();
      fixture.detectChanges();
      expect(document.body.classList.contains('modal-open')).toBeFalse();
    });
  });
});
