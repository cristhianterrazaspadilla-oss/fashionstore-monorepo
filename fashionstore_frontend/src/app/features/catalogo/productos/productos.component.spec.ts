import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ProductosComponent } from './productos.component';
import { MaestroService } from '../services/maestro.service';
import { ProductoService } from '../services/producto.service';
import { RecepcionService } from '../../inventario/services/recepcion.service';
import { ProductoDTO, VarianteDTO } from '../models/catalogo.models';

describe('ProductosComponent (Administración de Catálogo, Precios, Galería y Modales)', () => {
  let component: ProductosComponent;
  let fixture: ComponentFixture<ProductosComponent>;

  let maestroServiceSpy: jasmine.SpyObj<MaestroService>;
  let productoServiceSpy: jasmine.SpyObj<ProductoService>;
  let recepcionServiceSpy: jasmine.SpyObj<RecepcionService>;

  const mockProducto: ProductoDTO = {
    id: 'prod-1',
    nombre: 'Vestido Lino Ébano',
    descripcion: 'Vestido fresco de verano',
    categoria_id: 'cat-1',
    proveedor_principal_id: 'prov-1',
    genero: 'MUJER',
    marca: 'FashionStore',
    precio_base: 280.00,
    activo: true,
    creado_en: '2026-01-01',
    actualizado_en: '2026-01-01',
    imagenes: [
      { id: 'img-1', producto_id: 'prod-1', enlace_imagen: 'https://cdn.fs.com/img1.jpg', texto_alternativo: 'Frente', orden: 0, es_principal: true },
      { id: 'img-2', producto_id: 'prod-1', enlace_imagen: 'https://cdn.fs.com/img2.jpg', texto_alternativo: 'Espalda', orden: 1, es_principal: false }
    ],
    temporada_ids: ['temp-1'],
    coleccion_ids: ['col-1']
  };

  const mockVariante: VarianteDTO = {
    id: 'var-1',
    producto_id: 'prod-1',
    talla_id: 'tal-1',
    color_id: 'col-1',
    sku: 'VES-LIN-M',
    codigo_barras: '777000111',
    precio: 295.00, // Precio vendible específico de variante
    peso_gramos: 320,
    costo_promedio: 150,
    costo_ultimo: 150,
    recurso_prueba_virtual: 'modelo3d.glb',
    activa: true
  };

  beforeEach(async () => {
    maestroServiceSpy = jasmine.createSpyObj<MaestroService>('MaestroService', [
      'gestionarTallas', 'gestionarColores', 'gestionarCategorias',
      'gestionarTemporadas', 'gestionarColecciones'
    ]);
    productoServiceSpy = jasmine.createSpyObj<ProductoService>('ProductoService', [
      'gestionarProductos', 'gestionarVariantes', 'actualizarProducto', 'actualizarVariante',
      'toggleProducto', 'toggleVariante'
    ]);
    recepcionServiceSpy = jasmine.createSpyObj<RecepcionService>('RecepcionService', ['gestionarProveedores']);

    maestroServiceSpy.gestionarTallas.and.returnValue(of([]));
    maestroServiceSpy.gestionarColores.and.returnValue(of([]));
    maestroServiceSpy.gestionarCategorias.and.returnValue(of([{ id: 'cat-1', nombre: 'Vestidos', activo: true }]));
    maestroServiceSpy.gestionarTemporadas.and.returnValue(of([{ id: 'temp-1', nombre: 'Verano 2026', activa: true }]));
    maestroServiceSpy.gestionarColecciones.and.returnValue(of([{ id: 'col-1', nombre: 'Urbana', activa: true }]));
    recepcionServiceSpy.gestionarProveedores.and.returnValue(of([{ id: 'prov-1', razon_social: 'Textilera Real', nit: '123' } as any]));

    productoServiceSpy.gestionarProductos.and.returnValue(of([mockProducto]));
    productoServiceSpy.gestionarVariantes.and.returnValue(of([mockVariante]));

    await TestBed.configureTestingModule({
      imports: [ProductosComponent],
      providers: [
        { provide: MaestroService, useValue: maestroServiceSpy },
        { provide: ProductoService, useValue: productoServiceSpy },
        { provide: RecepcionService, useValue: recepcionServiceSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ProductosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    component.ngOnDestroy();
  });

  it('carga listados y distingue precio base (referencia) de precio vendible de variante', () => {
    expect(component.productos.length).toBe(1);
    expect(component.variantes.length).toBe(1);
    expect(Number(component.productos[0].precio_base)).toBe(280.00);
    expect(Number(component.variantes[0].precio)).toBe(295.00);
  });

  describe('Modal Accesible y Galería de Imágenes de Producto', () => {
    it('abre el modal bloqueando el scroll de body y pobla los formularios', () => {
      component.abrirEditarProducto(mockProducto);

      expect(component.editandoProducto).toEqual(mockProducto);
      expect(document.body.classList.contains('modal-open')).toBeTrue();
      expect(component.productoEditForm.controls.nombre.value).toBe('Vestido Lino Ébano');
      expect(component.imagenesGaleria.length).toBe(2);
    });

    it('garantiza exactamente una sola imagen principal en la galería', () => {
      component.abrirEditarProducto(mockProducto);

      // Marcar la segunda como principal
      component.marcarPrincipal(1);
      expect(component.imagenesGaleria[1].es_principal).toBeTrue();
      expect(component.imagenesGaleria[0].es_principal).toBeFalse();

      // Al volver a marcar la primera, la segunda deja de ser principal
      component.marcarPrincipal(0);
      expect(component.imagenesGaleria[0].es_principal).toBeTrue();
      expect(component.imagenesGaleria[1].es_principal).toBeFalse();
    });

    it('permite reordenar imágenes en la galería (mover arriba y abajo)', () => {
      component.abrirEditarProducto(mockProducto);

      expect(component.imagenesGaleria[0].enlace_imagen).toBe('https://cdn.fs.com/img1.jpg');
      component.moverImagen(0, 'abajo');
      expect(component.imagenesGaleria[0].enlace_imagen).toBe('https://cdn.fs.com/img2.jpg');
      expect(component.imagenesGaleria[1].enlace_imagen).toBe('https://cdn.fs.com/img1.jpg');

      component.moverImagen(1, 'arriba');
      expect(component.imagenesGaleria[0].enlace_imagen).toBe('https://cdn.fs.com/img1.jpg');
    });

    it('valida que la URL de una nueva imagen sea https seguro', () => {
      component.abrirEditarProducto(mockProducto);

      component.nuevaImagenUrl = 'http://inseguro.com/foto.jpg';
      component.agregarImagen();
      expect(component.errorGaleria).toContain('https://');

      component.nuevaImagenUrl = 'not-a-url';
      component.agregarImagen();
      expect(component.errorGaleria).toContain('no es válida');

      component.nuevaImagenUrl = 'https://cdn.fs.com/nueva.jpg';
      component.nuevaImagenAlt = 'Detalle costura';
      component.agregarImagen();
      expect(component.errorGaleria).toBeNull();
      expect(component.imagenesGaleria.length).toBe(3);
    });

    it('permite editar la URL de una imagen existente y valida https antes de guardar', () => {
      component.abrirEditarProducto(mockProducto);
      component.actualizarUrlImagen(0, 'http://cdn.fs.com/no-segura.jpg');

      component.guardarEdicionProducto();

      expect(productoServiceSpy.actualizarProducto).not.toHaveBeenCalled();
      expect(component.errorGaleria).toContain('imagen 1');

      productoServiceSpy.actualizarProducto.and.returnValue(of(mockProducto));
      component.actualizarUrlImagen(0, 'https://cdn.fs.com/frente-editado.jpg');
      component.guardarEdicionProducto();

      const dto = productoServiceSpy.actualizarProducto.calls.mostRecent().args[1];
      expect(dto.imagenes?.[0].enlace_imagen).toBe('https://cdn.fs.com/frente-editado.jpg');
    });

    it('envía null explícito al limpiar descripción, categoría o proveedor', () => {
      component.abrirEditarProducto(mockProducto);
      component.productoEditForm.controls.descripcion.setValue('   ');
      component.productoEditForm.controls.categoria_id.setValue('');
      component.productoEditForm.controls.proveedor_principal_id.setValue('');
      component.productoEditForm.controls.genero.setValue('');
      component.productoEditForm.controls.marca.setValue('');

      productoServiceSpy.actualizarProducto.and.returnValue(of(mockProducto));
      component.guardarEdicionProducto();

      expect(productoServiceSpy.actualizarProducto).toHaveBeenCalled();
      const dto = productoServiceSpy.actualizarProducto.calls.mostRecent().args[1];
      expect(dto.descripcion).toBeNull();
      expect(dto.categoria_id).toBeNull();
      expect(dto.proveedor_principal_id).toBeNull();
      expect(dto.genero).toBeNull();
      expect(dto.marca).toBeNull();
      expect(document.body.classList.contains('modal-open')).toBeFalse();
    });

    it('cierra el modal con tecla Escape si no se está guardando', () => {
      component.abrirEditarProducto(mockProducto);
      expect(component.editandoProducto).not.toBeNull();

      const event = new KeyboardEvent('keydown', { key: 'Escape' });
      component.alPresionarTecla(event);

      expect(component.editandoProducto).toBeNull();
      expect(document.body.classList.contains('modal-open')).toBeFalse();
    });

    it('protege el modal de producto durante guardado (botón × deshabilitado, métodos, Escape y backdrop inertes)', () => {
      component.abrirEditarProducto(mockProducto);
      fixture.detectChanges();

      component.guardandoEdicionProd = true;
      fixture.detectChanges();

      // Botón × deshabilitado
      const closeBtn = fixture.nativeElement.querySelector('.modal-header .btn-close-modal');
      expect(closeBtn).not.toBeNull();
      expect(closeBtn.disabled).toBeTrue();
      expect(closeBtn.getAttribute('aria-disabled')).toBe('true');

      // Invocación a cerrarEditarProducto ignorada
      component.cerrarEditarProducto();
      expect(component.editandoProducto).not.toBeNull();

      // Escape ignorado
      const event = new KeyboardEvent('keydown', { key: 'Escape' });
      component.alPresionarTecla(event);
      expect(component.editandoProducto).not.toBeNull();

      // Backdrop click ignorado
      const backdrop = fixture.nativeElement.querySelector('.modal-backdrop');
      backdrop.click();
      expect(component.editandoProducto).not.toBeNull();
      expect(document.body.classList.contains('modal-open')).toBeTrue();
    });
  });

  describe('Edición de Variante y Limpieza de Opcionales', () => {
    it('abre el modal de variante y envía null al limpiar código de barras y recurso 3D', () => {
      component.abrirEditarVariante(mockVariante);
      expect(component.editandoVariante).toEqual(mockVariante);

      component.varianteEditForm.controls.codigo_barras.setValue('');
      component.varianteEditForm.controls.peso_gramos.setValue(null);
      component.varianteEditForm.controls.recurso_prueba_virtual.setValue('');

      productoServiceSpy.actualizarVariante.and.returnValue(of(mockVariante));
      component.guardarEdicionVariante();

      expect(productoServiceSpy.actualizarVariante).toHaveBeenCalled();
      const dto = productoServiceSpy.actualizarVariante.calls.mostRecent().args[1];
      expect(dto.codigo_barras).toBeNull();
      expect(dto.peso_gramos).toBeNull();
      expect(dto.recurso_prueba_virtual).toBeNull();
    });

    it('protege el modal de variante durante guardado (botón × deshabilitado, métodos, Escape y backdrop inertes)', () => {
      component.abrirEditarVariante(mockVariante);
      fixture.detectChanges();

      component.guardandoEdicionVar = true;
      fixture.detectChanges();

      // Botón × deshabilitado
      const closeBtn = fixture.nativeElement.querySelector('.modal-header .btn-close-modal');
      expect(closeBtn).not.toBeNull();
      expect(closeBtn.disabled).toBeTrue();
      expect(closeBtn.getAttribute('aria-disabled')).toBe('true');

      // Invocación directa a cerrarEditarVariante ignorada
      component.cerrarEditarVariante();
      expect(component.editandoVariante).not.toBeNull();

      // Escape ignorado
      const event = new KeyboardEvent('keydown', { key: 'Escape' });
      component.alPresionarTecla(event);
      expect(component.editandoVariante).not.toBeNull();

      // Backdrop click ignorado
      const backdrop = fixture.nativeElement.querySelector('.modal-backdrop');
      backdrop.click();
      expect(component.editandoVariante).not.toBeNull();
      expect(document.body.classList.contains('modal-open')).toBeTrue();
    });
  });

  describe('Desactivación y Reactivación Protegida', () => {
    it('solicita confirmación accesible al desactivar un producto activo', () => {
      component.solicitarToggleProducto(mockProducto);

      expect(component.dialogConfirmDesactivarAbierto).toBeTrue();
      expect(component.productoADesactivar).toEqual(mockProducto);
      fixture.detectChanges();
      expect(document.body.classList.contains('modal-open')).toBeTrue();

      productoServiceSpy.toggleProducto.and.returnValue(of({ ...mockProducto, activo: false }));
      component.confirmarDesactivacion();

      expect(productoServiceSpy.toggleProducto).toHaveBeenCalledWith('prod-1', false);
      expect(component.dialogConfirmDesactivarAbierto).toBeFalse();
      fixture.detectChanges();
      expect(document.body.classList.contains('modal-open')).toBeFalse();
    });

    it('reactiva directamente sin diálogo destructivo si el producto estaba inactivo', () => {
      const prodInactivo = { ...mockProducto, activo: false };
      productoServiceSpy.toggleProducto.and.returnValue(of({ ...mockProducto, activo: true }));

      component.solicitarToggleProducto(prodInactivo);

      expect(component.dialogConfirmDesactivarAbierto).toBeFalse();
      expect(productoServiceSpy.toggleProducto).toHaveBeenCalledWith('prod-1', true);
    });
  });
});
