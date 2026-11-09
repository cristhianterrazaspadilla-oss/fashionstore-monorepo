import { ComponentFixture, TestBed, fakeAsync, tick, flush } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { of } from 'rxjs';
import { CatalogoComponent } from './catalogo.component';
import { CatalogoService } from '../services/catalogo.service';
import { MaestroService } from '../services/maestro.service';
import { ProductoService } from '../services/producto.service';
import { CarritoService } from '../../ventas_pagos/services/carrito.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { IAService } from '../../experiencia_cliente/services/ia.service';
import { ProductoDTO } from '../models/catalogo.models';

describe('CatalogoComponent (Roles, Asistente IA y Accesibilidad de Modal)', () => {
  let component: CatalogoComponent;
  let fixture: ComponentFixture<CatalogoComponent>;

  let catalogoServiceSpy: jasmine.SpyObj<CatalogoService>;
  let maestroServiceSpy: jasmine.SpyObj<MaestroService>;
  let productoServiceSpy: jasmine.SpyObj<ProductoService>;
  let carritoServiceSpy: jasmine.SpyObj<CarritoService>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let iaServiceSpy: jasmine.SpyObj<IAService>;

  const mockProductos: ProductoDTO[] = [
    {
      id: 'prod-1',
      nombre: 'Vestido Seda Atelier',
      descripcion: 'Corte fino',
      precio_base: 250,
      activo: true,
      marca: 'Atelier',
      genero: 'MUJER',
      categoria_id: 'cat-1',
      temporada_ids: [],
      coleccion_ids: [],
      imagenes: [],
      creado_en: '2026-09-20T10:00:00Z',
      actualizado_en: '2026-09-20T10:00:00Z'
    }
  ];

  beforeEach(async () => {
    document.body.classList.remove('modal-open');

    catalogoServiceSpy = jasmine.createSpyObj<CatalogoService>('CatalogoService', ['consultarCatalogo', 'consultarDisponibilidad']);
    maestroServiceSpy = jasmine.createSpyObj<MaestroService>('MaestroService', [
      'gestionarTallas', 'gestionarColores', 'gestionarCategorias', 'gestionarTemporadas', 'gestionarColecciones'
    ]);
    productoServiceSpy = jasmine.createSpyObj<ProductoService>('ProductoService', ['gestionarVariantes', 'obtenerProducto']);
    carritoServiceSpy = jasmine.createSpyObj<CarritoService>('CarritoService', ['agregarLinea']);
    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', [
      'obtenerUsuarioActual',
      'estaAutenticado',
      'esVentanaPrivacidadValida',
      'obtenerEmpresaId',
      'obtenerEmpresaCodigo'
    ]);
    authServiceSpy.obtenerEmpresaId.and.returnValue('00000000-0000-4000-8000-000000000001');
    authServiceSpy.esVentanaPrivacidadValida.and.returnValue(true);
    authServiceSpy.obtenerEmpresaCodigo.and.returnValue('fashionstore');
    iaServiceSpy = jasmine.createSpyObj<IAService>('IAService', ['buscar', 'recomendaciones']);

    catalogoServiceSpy.consultarCatalogo.and.returnValue(of(mockProductos));
    catalogoServiceSpy.consultarDisponibilidad.and.returnValue(of([]));
    maestroServiceSpy.gestionarTallas.and.returnValue(of([]));
    maestroServiceSpy.gestionarColores.and.returnValue(of([]));
    maestroServiceSpy.gestionarCategorias.and.returnValue(of([]));
    maestroServiceSpy.gestionarTemporadas.and.returnValue(of([]));
    maestroServiceSpy.gestionarColecciones.and.returnValue(of([]));
    productoServiceSpy.gestionarVariantes.and.returnValue(of([]));
    iaServiceSpy.recomendaciones.and.returnValue(of({ items: [], total: 0, proveedor: 'gemini' }));

    await TestBed.configureTestingModule({
      imports: [CatalogoComponent, HttpClientTestingModule],
      providers: [
        provideRouter([]),
        { provide: CatalogoService, useValue: catalogoServiceSpy },
        { provide: MaestroService, useValue: maestroServiceSpy },
        { provide: ProductoService, useValue: productoServiceSpy },
        { provide: CarritoService, useValue: carritoServiceSpy },
        { provide: AuthService, useValue: authServiceSpy },
        { provide: IAService, useValue: iaServiceSpy }
      ]
    }).compileComponents();
  });

  afterEach(() => {
    document.body.classList.remove('modal-open');
  });

  it('guarda un pedido local para recojo sin autorizar cobro ni confirmarlo', async () => {
    authServiceSpy.obtenerUsuarioActual.and.returnValue({ id: 'u-1', rol: 'CLIENTE' } as any);
    fixture = TestBed.createComponent(CatalogoComponent);
    component = fixture.componentInstance;
    component.esModoCopiaLocal = true;
    component.varianteSeleccionada = { id: 'v-1' } as any;
    component.cantidadAgregar = 2;
    component.snapshotLocal = {
      empresa_id: 'empresa-1', valido: true,
      sucursales: [{ id: 's-1', nombre: 'Centro' }],
      productos: [{ variantes: [{ id: 'v-1', precio_bob: '80.00', disponibilidad: 3, disponibilidad_por_sucursal: [{ sucursal_id: 's-1', disponible_conocido: 3 }] }] }]
    } as any;
    const registrar = spyOn(component.syncOfflineService, 'registrarCompraOffline').and.resolveTo({} as any);
    spyOn(component.syncOfflineService, 'listarComprasLocales').and.resolveTo([]);

    await component.guardarCompraFueraDeLinea();

    expect(registrar).toHaveBeenCalledWith({
      sucursal_id: 's-1', modalidad: 'RECOJO',
      lineas: [{ variante_id: 'v-1', cantidad: 2, precio_visto_bob: '80.00' }]
    });
    expect(component.mensajeCompraOffline).toContain('pendientes de confirmación');
    expect(component.guardandoCompraOffline).toBeFalse();
  });

  describe('Permisos y visualización por rol', () => {
    it('para visitante no autenticado: no muestra botón del asistente IA, muestra enlace a login y bloquea búsqueda IA', () => {
      authServiceSpy.estaAutenticado.and.returnValue(false);
      authServiceSpy.obtenerUsuarioActual.and.returnValue(null);

      fixture = TestBed.createComponent(CatalogoComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();

      expect(component.esVisitante()).toBeTrue();
      expect(component.esCliente()).toBeFalse();
      expect(component.esPersonalInterno()).toBeFalse();

      const element: HTMLElement = fixture.nativeElement;
      expect(element.textContent).toContain('Inicia sesión para asistente de estilo');

      // Intento de búsqueda IA bloqueado
      component.textoConsultaIA = 'Prenda de fiesta';
      component.buscarConIA();
      expect(iaServiceSpy.buscar).not.toHaveBeenCalled();
    });

    it('para CLIENTE: muestra botón del asistente IA y permite consulta asistida', () => {
      authServiceSpy.estaAutenticado.and.returnValue(true);
      authServiceSpy.obtenerUsuarioActual.and.returnValue({
        id: 'u-1',
        correo_electronico: 'cliente@test.com',
        rol: 'CLIENTE',
        nombre_completo: 'Cliente Test',
        sucursal_id: null
      } as any);
      iaServiceSpy.buscar.and.returnValue(of({ items: [], total: 0, filtros: {}, proveedor: 'gemini' }));

      fixture = TestBed.createComponent(CatalogoComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();

      expect(component.esCliente()).toBeTrue();
      expect(iaServiceSpy.recomendaciones).toHaveBeenCalled();

      component.textoConsultaIA = 'Vestido elegante';
      component.buscarConIA();
      expect(iaServiceSpy.buscar).toHaveBeenCalledWith('Vestido elegante');
    });

    it('para personal interno (ADMINISTRADOR / ENCARGADO / CAJERO): oculta asistente IA y recomendaciones', () => {
      authServiceSpy.estaAutenticado.and.returnValue(true);
      authServiceSpy.obtenerUsuarioActual.and.returnValue({
        id: 'u-2',
        correo_electronico: 'admin@test.com',
        rol: 'ADMINISTRADOR',
        nombre_completo: 'Admin Test',
        sucursal_id: null
      } as any);

      fixture = TestBed.createComponent(CatalogoComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();

      expect(component.esPersonalInterno()).toBeTrue();
      expect(component.esCliente()).toBeFalse();
      expect(component.esVisitante()).toBeFalse();

      const element: HTMLElement = fixture.nativeElement;
      expect(element.textContent).not.toContain('Asistente de estilo IA');
      expect(element.textContent).not.toContain('Inicia sesión para asistente de estilo');
      expect(iaServiceSpy.recomendaciones).not.toHaveBeenCalled();
    });

    it('para ADMINISTRADOR muestra el catálogo como consulta y nunca ofrece iniciar sesión o comprar', () => {
      authServiceSpy.estaAutenticado.and.returnValue(true);
      authServiceSpy.obtenerUsuarioActual.and.returnValue({
        id: 'u-admin', correo_electronico: 'admin@test.com', rol: 'ADMINISTRADOR',
        nombre_completo: 'Admin Test', sucursal_id: null
      } as any);

      fixture = TestBed.createComponent(CatalogoComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
      component.productoSeleccionado = mockProductos[0];
      component.varianteSeleccionada = {
        id: 'var-1',
        producto_id: mockProductos[0].id,
        talla_id: 'talla-m',
        color_id: 'color-negro',
        sku: 'CAM-NEG-M',
        precio: 250,
        costo_promedio: 0,
        costo_ultimo: 0,
        activa: true
      };
      spyOnProperty(component, 'stockDisponibleTotal', 'get').and.returnValue(5);
      fixture.detectChanges();

      const texto = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(texto).toContain('Vista de consulta operativa');
      expect(texto).not.toContain('Inicia sesión para agregar al carrito');
      expect(texto).not.toContain('Agregar al carrito');

      component.agregarAlCarrito();
      expect(carritoServiceSpy.agregarLinea).not.toHaveBeenCalled();
    });
  });

  describe('Accesibilidad del modal de detalle de producto', () => {
    beforeEach(() => {
      authServiceSpy.estaAutenticado.and.returnValue(true);
      authServiceSpy.obtenerUsuarioActual.and.returnValue({
        id: 'u-1',
        correo_electronico: 'cliente@test.com',
        rol: 'CLIENTE',
        nombre_completo: 'Cliente Test',
        sucursal_id: null
      } as any);

      fixture = TestBed.createComponent(CatalogoComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
    });

    it('abre modal con role="dialog", aria-modal="true", aria-labelledby y bloquea scroll', fakeAsync(() => {
      component.abrirDetalle(mockProductos[0]);
      fixture.detectChanges();
      tick(50);

      const overlay = fixture.nativeElement.querySelector('.modal-overlay');
      expect(overlay).toBeTruthy();
      expect(overlay.getAttribute('role')).toBe('dialog');
      expect(overlay.getAttribute('aria-modal')).toBe('true');
      expect(overlay.getAttribute('aria-labelledby')).toBe('modal-prod-nombre');
      expect(document.body.classList.contains('modal-open')).toBeTrue();

      component.cerrarModal();
      fixture.detectChanges();
      tick(50);
      flush();

      expect(document.body.classList.contains('modal-open')).toBeFalse();
    }));

    it('cierra el modal y restaura el scroll con la tecla Escape', fakeAsync(() => {
      component.abrirDetalle(mockProductos[0]);
      fixture.detectChanges();
      tick(50);
      expect(document.body.classList.contains('modal-open')).toBeTrue();

      const event = new KeyboardEvent('keydown', { key: 'Escape' });
      window.dispatchEvent(event);
      component.alPresionarEscape();
      tick(50);
      flush();

      expect(component.productoSeleccionado).toBeNull();
      expect(document.body.classList.contains('modal-open')).toBeFalse();
    }));
  });
});
