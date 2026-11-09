import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { PedidosComponent } from './pedidos.component';
import { EntregaService } from '../services/entrega.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { PedidoDTO, PedidoListaDTO } from '../models/venta-digital.models';

describe('PedidosComponent (Cola operativa, Capacidades y Paginación)', () => {
  let component: PedidosComponent;
  let fixture: ComponentFixture<PedidosComponent>;

  let entregaServiceSpy: jasmine.SpyObj<EntregaService>;
  let orgServiceSpy: jasmine.SpyObj<OrganizacionService>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;

  const mockPedidoTransicionable: PedidoDTO = {
    id: 'ped-10',
    venta_id: 'vta-10',
    modalidad: 'RECOJO',
    estado: 'SOLICITADO',
    sucursal_id: 'suc-1',
    anillo_sucursal: null,
    anillo_destino: null,
    direccion: null,
    tarifa_base: 0,
    incremento_anillo: 0,
    costo_entrega: 0,
    codigo_recojo: 'REC-5678',
    creada_en: '2026-09-20T10:00:00Z',
    puede_cancelar: false,
    puede_transicionar: true,
    siguiente_estado: 'PREPARADO'
  };

  const mockPedidoBloqueado: PedidoDTO = {
    id: 'ped-11',
    venta_id: 'vta-11',
    modalidad: 'DELIVERY',
    estado: 'SOLICITADO',
    sucursal_id: 'suc-2',
    anillo_sucursal: 2,
    anillo_destino: 3,
    direccion: 'Calle Los Cedros #12',
    tarifa_base: 15,
    incremento_anillo: 5,
    costo_entrega: 20,
    codigo_recojo: null,
    creada_en: '2026-09-20T10:00:00Z',
    puede_cancelar: false,
    puede_transicionar: false, // Por ejemplo, venta no pagada aún
    siguiente_estado: null
  };

  const mockLista: PedidoListaDTO = {
    items: [mockPedidoTransicionable, mockPedidoBloqueado],
    total: 30,
    limit: 10,
    offset: 0
  };

  beforeEach(async () => {
    entregaServiceSpy = jasmine.createSpyObj<EntregaService>('EntregaService', ['cola', 'transicionar']);
    orgServiceSpy = jasmine.createSpyObj<OrganizacionService>('OrganizacionService', ['gestionarSucursales']);
    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', ['obtenerUsuarioActual']);

    entregaServiceSpy.cola.and.returnValue(of(mockLista));
    orgServiceSpy.gestionarSucursales.and.returnValue(of([{ id: 'suc-1', nombre: 'Central' } as any]));
    authServiceSpy.obtenerUsuarioActual.and.returnValue({
      id: 'emp-1',
      correo_electronico: 'admin@test.com',
      rol: 'ADMINISTRADOR',
      nombre_completo: 'Admin Test',
      sucursal_id: null
    } as any);

    await TestBed.configureTestingModule({
      imports: [PedidosComponent],
      providers: [
        { provide: EntregaService, useValue: entregaServiceSpy },
        { provide: OrganizacionService, useValue: orgServiceSpy },
        { provide: AuthService, useValue: authServiceSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(PedidosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('determina siguienteEstado y puedeAvanzar desde las capacidades backend', () => {
    expect(component.siguienteEstado(mockPedidoTransicionable)).toBe('PREPARADO');
    expect(component.puedeAvanzar(mockPedidoTransicionable)).toBeTrue();

    expect(component.siguienteEstado(mockPedidoBloqueado)).toBeNull();
    expect(component.puedeAvanzar(mockPedidoBloqueado)).toBeFalse();
  });

  it('avanza el pedido únicamente cuando puede_transicionar es verdadero', () => {
    entregaServiceSpy.transicionar.and.returnValue(of({ ...mockPedidoTransicionable, estado: 'PREPARADO' }));

    component.avanzar(mockPedidoTransicionable);
    expect(entregaServiceSpy.transicionar).toHaveBeenCalledWith('ped-10', 'PREPARADO');

    entregaServiceSpy.transicionar.calls.reset();
    component.avanzar(mockPedidoBloqueado);
    expect(entregaServiceSpy.transicionar).not.toHaveBeenCalled();
  });

  it('gestiona la paginación preservando filtros aplicados', () => {
    component.sucursalFiltro = 'suc-1';
    component.estadoFiltro = 'SOLICITADO';

    component.paginaSiguiente();
    expect(component.offset).toBe(10);
    expect(entregaServiceSpy.cola).toHaveBeenCalledWith({
      sucursal_id: 'suc-1',
      estado: 'SOLICITADO',
      limit: 10,
      offset: 10
    });
  });

  it('devuelve nombre amigable sin exponer UUIDs cuando la sucursal no está en la lista', () => {
    expect(component.sucursalNombre('suc-1')).toBe('Central');
    expect(component.sucursalNombre('99999999-0000-0000-0000-000000000000')).toBe('No disponible');
  });
});
