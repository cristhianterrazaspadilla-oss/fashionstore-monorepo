import { ComponentFixture, TestBed, fakeAsync, tick, flush } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { BehaviorSubject, Subject, of, throwError } from 'rxjs';
import { MisPedidosComponent } from './mis-pedidos.component';
import { EntregaService } from '../services/entrega.service';
import { PedidoDTO, PedidoListaDTO } from '../models/venta-digital.models';

describe('MisPedidosComponent (Capacidades, Detalle directo, Navegación y Accesibilidad)', () => {
  let component: MisPedidosComponent;
  let fixture: ComponentFixture<MisPedidosComponent>;
  let entregaServiceSpy: jasmine.SpyObj<EntregaService>;
  let routerSpy: jasmine.SpyObj<Router>;
  let paramMapSubject: BehaviorSubject<ReturnType<typeof convertToParamMap>>;

  const mockPedido1: PedidoDTO = {
    id: 'ped-1',
    venta_id: 'vta-1',
    modalidad: 'RECOJO',
    estado: 'SOLICITADO',
    sucursal_id: 'suc-1',
    anillo_sucursal: null,
    anillo_destino: null,
    direccion: null,
    tarifa_base: 0,
    incremento_anillo: 0,
    costo_entrega: 0,
    codigo_recojo: 'REC-1234',
    creada_en: '2026-09-20T10:00:00Z',
    puede_cancelar: true,
    puede_transicionar: false,
    siguiente_estado: null
  };

  const mockPedido2: PedidoDTO = {
    id: 'ped-2',
    venta_id: 'vta-2',
    modalidad: 'DELIVERY',
    estado: 'SOLICITADO',
    sucursal_id: 'suc-1',
    anillo_sucursal: 1,
    anillo_destino: 2,
    direccion: 'Av. Las Palmas #45',
    tarifa_base: 10,
    incremento_anillo: 5,
    costo_entrega: 15,
    codigo_recojo: null,
    creada_en: '2026-09-20T10:00:00Z',
    puede_cancelar: false, // Venta ya pagada
    puede_transicionar: false,
    siguiente_estado: null
  };

  const mockLista: PedidoListaDTO = {
    items: [mockPedido1, mockPedido2],
    total: 25,
    limit: 10,
    offset: 0
  };

  beforeEach(async () => {
    document.body.classList.remove('modal-open');
    paramMapSubject = new BehaviorSubject(convertToParamMap({}));
    entregaServiceSpy = jasmine.createSpyObj<EntregaService>('EntregaService', ['misPedidos', 'obtener', 'cancelar']);
    entregaServiceSpy.misPedidos.and.returnValue(of(mockLista));
    entregaServiceSpy.obtener.and.returnValue(of(mockPedido1));
    routerSpy = jasmine.createSpyObj<Router>('Router', ['navigate']);

    await TestBed.configureTestingModule({
      imports: [MisPedidosComponent],
      providers: [
        { provide: EntregaService, useValue: entregaServiceSpy },
        { provide: Router, useValue: routerSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: paramMapSubject.asObservable(),
            snapshot: {
              paramMap: convertToParamMap({})
            }
          }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(MisPedidosComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    document.body.classList.remove('modal-open');
  });

  it('evalúa puedeCancelar exclusivamente desde la capacidad backend puede_cancelar', () => {
    expect(component.puedeCancelar(mockPedido1)).toBeTrue();
    expect(component.puedeCancelar(mockPedido2)).toBeFalse();
  });

  it('permite paginación preservando límites y rangos', () => {
    expect(component.paginaActual).toBe(1);
    expect(component.totalPaginas).toBe(3);
    expect(component.rangoInicio).toBe(1);
    expect(component.rangoFin).toBe(10);

    component.paginaSiguiente();
    expect(component.offset).toBe(10);
    expect(entregaServiceSpy.misPedidos).toHaveBeenCalledWith(10, 10);

    component.paginaAnterior();
    expect(component.offset).toBe(0);
    expect(entregaServiceSpy.misPedidos).toHaveBeenCalledWith(10, 0);
  });

  it('al seleccionar un pedido desde la lista, navega a /mis-pedidos/:id', () => {
    component.verDetalle(mockPedido1);
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/mis-pedidos', 'ped-1']);
  });

  it('al abrir directamente una URL con :id, consulta GET /entregas/:id y muestra el detalle', fakeAsync(() => {
    paramMapSubject.next(convertToParamMap({ id: 'ped-1' }));
    fixture.detectChanges();
    tick(60);

    expect(entregaServiceSpy.obtener).toHaveBeenCalledWith('ped-1');
    expect(component.detalle).toEqual(mockPedido1);
    expect(component.cargandoDetalle).toBeFalse();
    expect(component.errorDetalle).toBeNull();
    expect(document.body.classList.contains('modal-open')).toBeTrue();
    flush();
  }));

  it('reacciona a cambios entre diferentes IDs sin recrear el componente', fakeAsync(() => {
    entregaServiceSpy.obtener.and.returnValue(of(mockPedido2));
    paramMapSubject.next(convertToParamMap({ id: 'ped-2' }));
    fixture.detectChanges();
    tick(60);

    expect(entregaServiceSpy.obtener).toHaveBeenCalledWith('ped-2');
    expect(component.detalle).toEqual(mockPedido2);
    flush();
  }));

  it('al cerrar el detalle, navega de vuelta a /mis-pedidos y limpia el modal', fakeAsync(() => {
    paramMapSubject.next(convertToParamMap({ id: 'ped-1' }));
    fixture.detectChanges();
    tick(60);
    expect(component.detalle).toEqual(mockPedido1);

    component.cerrarDetalle();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/mis-pedidos']);

    // Al cambiar la ruta a /mis-pedidos sin id, se cierra el detalle local
    paramMapSubject.next(convertToParamMap({}));
    fixture.detectChanges();
    tick(60);

    expect(component.detalle).toBeNull();
    expect(document.body.classList.contains('modal-open')).toBeFalse();
    flush();
  }));

  it('muestra error útil y no lo silencia cuando la carga directa devuelve 403', fakeAsync(() => {
    entregaServiceSpy.obtener.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 403,
      error: { detail: 'No tienes permiso para ver este pedido' }
    })));

    paramMapSubject.next(convertToParamMap({ id: 'ped-prohibido' }));
    fixture.detectChanges();
    tick(60);

    expect(component.errorDetalle).toContain('No tienes permiso');
    expect(component.cargandoDetalle).toBeFalse();
    expect(component.detalle).toBeNull();

    const dialogError = fixture.nativeElement.querySelector('.cycle-alert.danger');
    expect(dialogError).toBeTruthy();
    flush();
  }));

  it('muestra error útil y no lo silencia cuando la carga directa devuelve 404', fakeAsync(() => {
    entregaServiceSpy.obtener.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 404,
      error: { detail: 'El pedido solicitado no fue encontrado.' }
    })));

    paramMapSubject.next(convertToParamMap({ id: 'ped-inexistente' }));
    fixture.detectChanges();
    tick(60);

    expect(component.errorDetalle).toContain('no fue encontrado');
    expect(component.cargandoDetalle).toBeFalse();
    flush();
  }));

  it('muestra error de red útil ante fallo de conexión en carga directa', fakeAsync(() => {
    entregaServiceSpy.obtener.and.returnValue(throwError(() => new HttpErrorResponse({
      status: 0,
      statusText: 'Unknown Error'
    })));

    paramMapSubject.next(convertToParamMap({ id: 'ped-red' }));
    fixture.detectChanges();
    tick(60);

    expect(component.errorDetalle).toContain('conexión');
    expect(component.cargandoDetalle).toBeFalse();
    flush();
  }));

  it('conserva el diálogo abierto y no permite cerrar si la cancelación está procesándose', () => {
    component.detalle = mockPedido1;
    component.cancelando = true;

    component.cerrarDetalle();
    expect(routerSpy.navigate).not.toHaveBeenCalled();

    component.alPresionarEscape();
    expect(routerSpy.navigate).not.toHaveBeenCalled();
  });

  it('cierra el diálogo de confirmación con Escape sin cerrar el modal de detalle', () => {
    component.detalle = mockPedido1;
    component.mostrarConfirmacionCancelar = true;

    component.alPresionarEscape();
    expect(component.mostrarConfirmacionCancelar).toBeFalse();
    expect(component.detalle).toEqual(mockPedido1);
    expect(routerSpy.navigate).not.toHaveBeenCalled();
  });

  it('cancela la petición obsoleta y solo muestra el detalle del ID vigente (carrera ped-1 → ped-2)', fakeAsync(() => {
    const pedido1$ = new Subject<PedidoDTO>();
    const pedido2$ = new Subject<PedidoDTO>();
    entregaServiceSpy.obtener.and.callFake((id: string) => {
      if (id === 'ped-1') return pedido1$.asObservable();
      if (id === 'ped-2') return pedido2$.asObservable();
      return of(mockPedido1);
    });

    paramMapSubject.next(convertToParamMap({ id: 'ped-1' }));
    fixture.detectChanges();
    expect(component.cargandoDetalle).toBeTrue();

    // Cambio inmediato a ped-2 antes de que responda ped-1
    paramMapSubject.next(convertToParamMap({ id: 'ped-2' }));
    fixture.detectChanges();
    expect(component.cargandoDetalle).toBeTrue();
    expect(entregaServiceSpy.obtener).toHaveBeenCalledWith('ped-1');
    expect(entregaServiceSpy.obtener).toHaveBeenCalledWith('ped-2');

    // Responde tarde ped-1: debe ser ignorada por switchMap
    pedido1$.next(mockPedido1);
    fixture.detectChanges();
    tick(60);
    expect(component.detalle).toBeNull();

    // Responde ped-2: solo este detalle puede modificar la vista
    pedido2$.next(mockPedido2);
    fixture.detectChanges();
    tick(60);

    expect(component.detalle?.id).toBe('ped-2');
    expect(component.detalle).toEqual(mockPedido2);
    expect(component.cargandoDetalle).toBeFalse();
    flush();
  }));

  it('al hacer clic en el backdrop navega a /mis-pedidos', fakeAsync(() => {
    paramMapSubject.next(convertToParamMap({ id: 'ped-1' }));
    fixture.detectChanges();
    tick(60);
    expect(component.detalle).toEqual(mockPedido1);

    const overlay: HTMLElement | null = fixture.nativeElement.querySelector('.cycle-overlay');
    expect(overlay).toBeTruthy();
    overlay?.click();
    fixture.detectChanges();

    expect(routerSpy.navigate).toHaveBeenCalledWith(['/mis-pedidos']);
    flush();
  }));

  it('quitar el ID cierra y limpia el modal', fakeAsync(() => {
    paramMapSubject.next(convertToParamMap({ id: 'ped-1' }));
    fixture.detectChanges();
    tick(60);
    expect(component.detalle).toEqual(mockPedido1);

    paramMapSubject.next(convertToParamMap({}));
    fixture.detectChanges();
    tick(60);

    expect(component.detalle).toBeNull();
    expect(component.cargandoDetalle).toBeFalse();
    expect(component.errorDetalle).toBeNull();
    flush();
  }));
});
