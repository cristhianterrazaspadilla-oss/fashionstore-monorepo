import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { BehaviorSubject } from 'rxjs';
import { ShellComponent } from './shell.component';
import { AuthService } from '../../features/identidad_empresas/services/auth.service';
import { CarritoService } from '../../features/ventas_pagos/services/carrito.service';
import { ClientePerfil } from '../../features/identidad_empresas/models/auth.models';

describe('ShellComponent (Navegación y Acceso por Roles)', () => {
  let component: ShellComponent;
  let fixture: ComponentFixture<ShellComponent>;

  let usuarioSubject: BehaviorSubject<ClientePerfil | null>;
  let conteoSubject: BehaviorSubject<number>;

  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let carritoServiceSpy: jasmine.SpyObj<CarritoService>;

  beforeEach(async () => {
    usuarioSubject = new BehaviorSubject<ClientePerfil | null>(null);
    conteoSubject = new BehaviorSubject<number>(0);

    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', [
      'estaAutenticado',
      'obtenerUsuarioActual',
      'cerrarSesion'
    ], {
      usuario$: usuarioSubject.asObservable()
    });

    carritoServiceSpy = jasmine.createSpyObj<CarritoService>('CarritoService', [
      'refrescarConteo'
    ], {
      conteo$: conteoSubject.asObservable()
    });

    await TestBed.configureTestingModule({
      imports: [ShellComponent, RouterTestingModule],
      providers: [
        { provide: AuthService, useValue: authServiceSpy },
        { provide: CarritoService, useValue: carritoServiceSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(ShellComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    document.body.classList.remove('menu-open');
  });

  it('debe crearse correctamente', () => {
    expect(component).toBeTruthy();
  });

  it('permite abrir el catálogo guardado sin mostrar la navegación privada cuando no hay red', () => {
    component.sinConexion = true;
    component.enCatalogo = false;
    fixture.detectChanges();
    const root: HTMLElement = fixture.nativeElement;
    expect(root.querySelector('.app-header')).toBeNull();
    expect(root.querySelector('.pwa-offline a')?.getAttribute('href')).toBe('/catalogo');

    component.enCatalogo = true;
    fixture.detectChanges();
    expect(root.querySelector('router-outlet')).not.toBeNull();
  });

  describe('Navegación para VISITANTE (No autenticado)', () => {
    beforeEach(() => {
      usuarioSubject.next(null);
      fixture.detectChanges();
    });

    it('identifica correctamente estado no autenticado', () => {
      expect(component.usuarioActual).toBeNull();
      expect(component.esCliente()).toBeFalse();
      expect(component.esCajero()).toBeFalse();
      expect(component.esEncargado()).toBeFalse();
      expect(component.esAdmin()).toBeFalse();
    });

    it('solo permite acceso a vistas públicas y niega vistas operativas/administrativas', () => {
      expect(component.puedeVerCarrito()).toBeFalse();
      expect(component.puedeVerMisPedidos()).toBeFalse();
      expect(component.puedeVerHistorial()).toBeFalse();
      expect(component.puedeVerPedidos()).toBeFalse();
      expect(component.puedeVerPromociones()).toBeFalse();
      expect(component.puedeVerDashboard()).toBeFalse();
      expect(component.puedeVerProductos()).toBeFalse();
      expect(component.puedeVerCaja()).toBeFalse();
      expect(component.puedeVerSucursales()).toBeFalse();
      expect(component.puedeVerSaldo()).toBeFalse();
      expect(component.puedeVerReembolsos()).toBeFalse();
    });
  });

  describe('Navegación para CLIENTE', () => {
    beforeEach(() => {
      const cliente: ClientePerfil = {
        id: 'c-1',
        usuario_id: 'u-c-1',
        nombres: 'María',
        apellidos: 'Cliente',
        nombre_completo: 'María Cliente',
        correo_electronico: 'cliente@fs.com',
        rol: 'CLIENTE',
        estado: 'ACTIVO',
        preferencias: {},
        creado_en: '2026-01-01'
      };
      usuarioSubject.next(cliente);
      fixture.detectChanges();
    });

    it('habilita compras y seguimiento, refrescando conteo de carrito', () => {
      expect(component.esCliente()).toBeTrue();
      expect(carritoServiceSpy.refrescarConteo).toHaveBeenCalled();
      expect(component.puedeVerCarrito()).toBeTrue();
      expect(component.puedeVerMisPedidos()).toBeTrue();
      expect(component.puedeVerHistorial()).toBeTrue();
      expect(component.puedeVerReservas()).toBeTrue();
      expect(component.puedeVerSaldo()).toBeTrue();
      expect(component.puedeVerReembolsos()).toBeTrue();
    });

    it('bloquea vistas de operación y administración', () => {
      expect(component.puedeVerPedidos()).toBeFalse();
      expect(component.puedeVerCaja()).toBeFalse();
      expect(component.puedeVerDashboard()).toBeFalse();
      expect(component.puedeVerProductos()).toBeFalse();
      expect(component.puedeVerSucursales()).toBeFalse();
    });
  });

  describe('Navegación para CAJERO', () => {
    beforeEach(() => {
      const cajero: ClientePerfil = {
        id: 'caj-1',
        usuario_id: 'u-caj-1',
        nombres: 'Carlos',
        apellidos: 'Cajero',
        nombre_completo: 'Carlos Cajero',
        correo_electronico: 'cajero@fs.com',
        rol: 'CAJERO',
        estado: 'ACTIVO',
        preferencias: {},
        creado_en: '2026-01-01'
      };
      usuarioSubject.next(cajero);
      fixture.detectChanges();
    });

    it('habilita caja, cola de pedidos e inventario', () => {
      expect(component.esCajero()).toBeTrue();
      expect(component.puedeVerCaja()).toBeTrue();
      expect(component.puedeVerPedidos()).toBeTrue();
      expect(component.puedeVerInventario()).toBeTrue();
    });

    it('bloquea vistas de cliente y gerencia', () => {
      expect(component.puedeVerCarrito()).toBeFalse();
      expect(component.puedeVerMisPedidos()).toBeFalse();
      expect(component.puedeVerDashboard()).toBeFalse();
      expect(component.puedeVerProductos()).toBeFalse();
      expect(component.puedeVerSucursales()).toBeFalse();
    });
  });

  describe('Navegación para ENCARGADO', () => {
    beforeEach(() => {
      const encargado: ClientePerfil = {
        id: 'enc-1',
        usuario_id: 'u-enc-1',
        nombres: 'Elena',
        apellidos: 'Encargada',
        nombre_completo: 'Elena Encargada',
        correo_electronico: 'encargado@fs.com',
        rol: 'ENCARGADO',
        estado: 'ACTIVO',
        preferencias: {},
        creado_en: '2026-01-01'
      };
      usuarioSubject.next(encargado);
      fixture.detectChanges();
    });

    it('habilita dashboard de sucursal, pedidos, promociones, traslados e inteligencia', () => {
      expect(component.esEncargado()).toBeTrue();
      expect(component.puedeVerDashboard()).toBeTrue();
      expect(component.puedeVerPedidos()).toBeTrue();
      expect(component.puedeVerPromociones()).toBeTrue();
      expect(component.puedeVerInteligencia()).toBeTrue();
      expect(component.puedeVerTraslados()).toBeTrue();
      expect(component.puedeVerOperaciones()).toBeTrue();
    });

    it('no tiene acceso a catálogo administrativo exclusivo de admin ni sucursales', () => {
      expect(component.puedeVerCarrito()).toBeFalse();
      expect(component.puedeVerProductos()).toBeFalse();
      expect(component.puedeVerSucursales()).toBeFalse();
      expect(component.puedeVerRecepciones()).toBeFalse();
    });
  });

  describe('Navegación para ADMINISTRADOR', () => {
    beforeEach(() => {
      const admin: ClientePerfil = {
        id: 'adm-1',
        usuario_id: 'u-adm-1',
        nombres: 'Admin',
        apellidos: 'General',
        nombre_completo: 'Admin General',
        correo_electronico: 'admin@fs.com',
        rol: 'ADMINISTRADOR',
        estado: 'ACTIVO',
        preferencias: {},
        creado_en: '2026-01-01'
      };
      usuarioSubject.next(admin);
      fixture.detectChanges();
    });

    it('habilita control total: dashboard, productos, sucursales, promociones, pedidos y caja', () => {
      expect(component.esAdmin()).toBeTrue();
      expect(component.puedeVerCarrito()).toBeFalse();
      expect(component.puedeVerDashboard()).toBeTrue();
      expect(component.puedeVerProductos()).toBeTrue();
      expect(component.puedeVerSucursales()).toBeTrue();
      expect(component.puedeVerRecepciones()).toBeTrue();
      expect(component.puedeVerPromociones()).toBeTrue();
      expect(component.puedeVerPedidos()).toBeTrue();
      expect(component.puedeVerCaja()).toBeTrue();
      expect(component.puedeVerOperaciones()).toBeTrue();
      expect(component.puedeVerTraslados()).toBeTrue();
    });
  });

  it('muestra al SUPERADMIN el panel de plataforma sin navegación de tienda', () => {
    usuarioSubject.next({
      id: 'super-1', usuario_id: 'super-1', nombres: 'Super', apellidos: 'Admin',
      nombre_completo: 'Super Admin', correo_electronico: 'super@example.com',
      rol: 'SUPERADMIN', estado: 'ACTIVO', preferencias: {}, creado_en: '2026-01-01', empresa_id: null
    });
    fixture.detectChanges();

    expect(component.esPlataforma()).toBeTrue();
    expect(component.esAdmin()).toBeFalse();
    expect(component.puedeVerCaja()).toBeFalse();
    expect(fixture.nativeElement.querySelector('a[href="/plataforma"]')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('a[href="/caja"]')).toBeNull();
  });

  describe('Control de Menú Móvil y Teclado', () => {
    it('alternarMenu abre y cierra correctamente bloqueando y desbloqueando el body', () => {
      expect(component.menuAbierto).toBeFalse();
      component.alternarMenu();
      expect(component.menuAbierto).toBeTrue();
      expect(document.body.classList.contains('menu-open')).toBeTrue();

      component.alternarMenu();
      expect(component.menuAbierto).toBeFalse();
      expect(document.body.classList.contains('menu-open')).toBeFalse();
    });

    it('cierra el menú móvil al presionar la tecla Escape', () => {
      component.abrirMenu();
      expect(component.menuAbierto).toBeTrue();

      const escapeEvent = new KeyboardEvent('keydown', { key: 'Escape' });
      component.alPresionarTecla(escapeEvent);

      expect(component.menuAbierto).toBeFalse();
    });
  });
});
