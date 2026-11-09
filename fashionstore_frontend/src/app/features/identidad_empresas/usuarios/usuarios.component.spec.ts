import { ComponentFixture, TestBed, fakeAsync, tick, flush } from '@angular/core/testing';
import { of } from 'rxjs';
import { UsuariosComponent } from './usuarios.component';
import { UsuarioService } from '../services/usuario.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { UsuarioListadoDTO, RolDTO } from '../models/usuario.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';

describe('UsuariosComponent', () => {
  let fixture: ComponentFixture<UsuariosComponent>;
  let component: UsuariosComponent;
  let usuarioServiceSpy: jasmine.SpyObj<UsuarioService>;
  let organizacionServiceSpy: jasmine.SpyObj<OrganizacionService>;

  const mockRoles: RolDTO[] = [
    { id: 'rol-1', nombre: 'ADMINISTRADOR', activo: true, creado_en: '2026-01-01T00:00:00Z' },
    { id: 'rol-2', nombre: 'ENCARGADO', activo: true, creado_en: '2026-01-01T00:00:00Z' },
    { id: 'rol-3', nombre: 'CAJERO', activo: true, creado_en: '2026-01-01T00:00:00Z' }
  ];

  const mockSucursales: SucursalDTO[] = [
    {
      id: 'suc-1',
      ciudad_id: 'ciu-1',
      ciudad_nombre: 'La Paz',
      nombre: 'Sucursal Central',
      direccion: 'Av. Principal 123',
      tarifa_base_delivery: 15,
      incremento_anillo_delivery: 5,
      anillo_minimo_delivery: 1,
      anillo_maximo_delivery: 4,
      delivery_activo: true,
      activa: true
    }
  ];

  const mockUsuarios: UsuarioListadoDTO[] = [
    {
      id: 'usr-1',
      nombres: 'Carlos',
      apellidos: 'Mendoza',
      nombre_completo: 'Carlos Mendoza',
      correo_electronico: 'carlos@fashionstore.com',
      rol_id: 'rol-2',
      rol_nombre: 'ENCARGADO',
      sucursal_id: 'suc-1',
      sucursal_nombre: 'Sucursal Central',
      cargo: 'Jefe de Tienda',
      estado: 'ACTIVO',
      telefono: '70011223',
      creado_en: '2026-01-01T00:00:00Z',
      actualizado_en: '2026-01-01T00:00:00Z'
    }
  ];

  beforeEach(async () => {
    usuarioServiceSpy = jasmine.createSpyObj<UsuarioService>('UsuarioService', [
      'listarRoles',
      'gestionarUsuarios',
      'crearUsuario',
      'asignarRol',
      'actualizarEstadoUsuario',
      'actualizarUsuario'
    ]);
    organizacionServiceSpy = jasmine.createSpyObj<OrganizacionService>('OrganizacionService', [
      'gestionarSucursales'
    ]);

    usuarioServiceSpy.listarRoles.and.returnValue(of(mockRoles));
    usuarioServiceSpy.gestionarUsuarios.and.returnValue(of(mockUsuarios));
    organizacionServiceSpy.gestionarSucursales.and.returnValue(of(mockSucursales));

    await TestBed.configureTestingModule({
      imports: [UsuariosComponent],
      providers: [
        { provide: UsuarioService, useValue: usuarioServiceSpy },
        { provide: OrganizacionService, useValue: organizacionServiceSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(UsuariosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('inicializa y muestra la lista de usuarios en tarjetas móviles y tabla', () => {
    expect(component.usuarios.length).toBe(1);
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).toContain('Carlos Mendoza');
    expect(compiled.textContent).toContain('carlos@fashionstore.com');
    expect(compiled.textContent).toContain('ENCARGADO');
    expect(compiled.textContent).toContain('Sucursal Central');
    expect(compiled.textContent).toContain('ACTIVO');
  });

  it('abre el diálogo de cambio de rol y confirma la actualización', fakeAsync(() => {
    usuarioServiceSpy.asignarRol.and.returnValue(
      of({ ...mockUsuarios[0], rol_id: 'rol-1', rol_nombre: 'ADMINISTRADOR' })
    );

    component.cambiarRol(mockUsuarios[0]);
    tick(60);
    fixture.detectChanges();

    expect(component.usuarioCambioRol).toEqual(mockUsuarios[0]);
    const dialogTitle = fixture.nativeElement.querySelector('#role-dialog-title');
    expect(dialogTitle?.textContent).toContain('Cambiar rol de Carlos Mendoza');

    component.nuevoRolId = 'rol-1';
    component.confirmarCambioRol();
    tick();
    flush();

    expect(usuarioServiceSpy.asignarRol).toHaveBeenCalledWith('usr-1', 'rol-1');
    expect(component.usuarioCambioRol).toBeNull();
  }));

  it('cierra el diálogo de cambio de rol al pulsar Escape', () => {
    component.cambiarRol(mockUsuarios[0]);
    fixture.detectChanges();
    expect(component.usuarioCambioRol).not.toBeNull();

    component.alPresionarEscape();
    fixture.detectChanges();
    expect(component.usuarioCambioRol).toBeNull();
  });

  it('abre y procesa el diálogo para alternar estado activo/inactivo', fakeAsync(() => {
    usuarioServiceSpy.actualizarEstadoUsuario.and.returnValue(
      of({ ...mockUsuarios[0], estado: 'INACTIVO' })
    );

    component.alternarEstado(mockUsuarios[0]);
    tick(60);
    fixture.detectChanges();

    expect(component.usuarioCambioEstado).toEqual(mockUsuarios[0]);
    const stateTitle = fixture.nativeElement.querySelector('#state-dialog-title');
    expect(stateTitle?.textContent).toContain('Desactivar usuario');

    component.confirmarCambioEstado();
    tick();
    flush();

    expect(usuarioServiceSpy.actualizarEstadoUsuario).toHaveBeenCalledWith('usr-1', 'INACTIVO');
    expect(component.usuarioCambioEstado).toBeNull();
  }));

  it('abre el diálogo de edición completa y guarda los cambios', fakeAsync(() => {
    usuarioServiceSpy.actualizarUsuario.and.returnValue(
      of({ ...mockUsuarios[0], nombres: 'Carlos Alberto', nombre_completo: 'Carlos Alberto Mendoza' })
    );

    component.editarUsuario(mockUsuarios[0]);
    tick(60);
    fixture.detectChanges();

    expect(component.usuarioEditando).toEqual(mockUsuarios[0]);
    expect(component.datosEdicion.nombres).toBe('Carlos');

    component.datosEdicion.nombres = 'Carlos Alberto';
    component.guardarEdicion();
    tick();
    flush();

    expect(usuarioServiceSpy.actualizarUsuario).toHaveBeenCalled();
    expect(component.usuarioEditando).toBeNull();
  }));

  it('no produce scroll horizontal forzado en anchos 360, 390, 440, 768, 1024 y 1440 px', () => {
    const anchos = [360, 390, 440, 768, 1024, 1440];
    const host = fixture.nativeElement as HTMLElement;

    anchos.forEach(ancho => {
      host.style.width = `${ancho}px`;
      fixture.detectChanges();
      const container = host.querySelector('.module-container') as HTMLElement;
      if (container) {
        expect(container.scrollWidth).toBeLessThanOrEqual(ancho + 1);
      }
    });
  });
});
