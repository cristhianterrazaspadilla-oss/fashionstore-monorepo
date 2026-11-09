import { ComponentFixture, TestBed, fakeAsync, tick, discardPeriodicTasks } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';
import { of, throwError } from 'rxjs';
import { PagoComponent } from './pago.component';
import { StripeService } from '../services/stripe.service';
import { EstadoPagoDTO, IntencionDTO } from '../models/venta-digital.models';

describe('PagoComponent (Ciclo de Vida del Pago Stripe, Polling y Estados)', () => {
  let component: PagoComponent;
  let fixture: ComponentFixture<PagoComponent>;

  let stripeServiceSpy: jasmine.SpyObj<StripeService>;
  let activatedRouteMock: any;

  const mockEstadoSinIntencion: EstadoPagoDTO = {
    venta_id: 'vta-501',
    estado_venta: 'PENDIENTE_PAGO',
    estado_pago: 'SIN_INTENCION',
    payment_intent_id: null,
    monto: 250,
    expira_en: '2026-09-20T23:59:59Z'
  };

  const mockEstadoPendiente: EstadoPagoDTO = {
    venta_id: 'vta-501',
    estado_venta: 'PENDIENTE_PAGO',
    estado_pago: 'PENDIENTE',
    payment_intent_id: 'pi_test_123',
    monto: 250,
    expira_en: '2026-09-20T23:59:59Z'
  };

  const mockEstadoAprobado: EstadoPagoDTO = {
    venta_id: 'vta-501',
    estado_venta: 'PAGADA',
    estado_pago: 'APROBADO',
    payment_intent_id: 'pi_test_123',
    monto: 250,
    expira_en: '2026-09-20T23:59:59Z'
  };

  const mockEstadoRechazado: EstadoPagoDTO = {
    venta_id: 'vta-501',
    estado_venta: 'PENDIENTE_PAGO',
    estado_pago: 'RECHAZADO',
    payment_intent_id: 'pi_test_123',
    monto: 250,
    expira_en: '2026-09-20T23:59:59Z'
  };

  const mockEstadoAnulado: EstadoPagoDTO = {
    venta_id: 'vta-501',
    estado_venta: 'CANCELADA',
    estado_pago: 'ANULADO',
    payment_intent_id: 'pi_test_123',
    monto: 250,
    expira_en: '2026-09-20T10:00:00Z'
  };

  const mockIntencion: IntencionDTO = {
    payment_intent_id: 'pi_test_123',
    venta_id: 'vta-501',
    client_secret: 'pi_test_123_secret_xyz',
    estado: 'PENDIENTE',
    monto: 250,
    moneda: 'BOB'
  };

  beforeEach(async () => {
    stripeServiceSpy = jasmine.createSpyObj<StripeService>('StripeService', [
      'consultarEstado',
      'crearIntencion',
      'reintentar',
      'cargarStripeJs'
    ]);

    activatedRouteMock = {
      snapshot: {
        paramMap: {
          get: (key: string) => (key === 'ventaId' ? 'vta-501' : null)
        }
      }
    };

    stripeServiceSpy.consultarEstado.and.returnValue(of(mockEstadoSinIntencion));
    stripeServiceSpy.crearIntencion.and.returnValue(of(mockIntencion));
    stripeServiceSpy.cargarStripeJs.and.returnValue(Promise.reject('Test env - no DOM Stripe.js'));

    await TestBed.configureTestingModule({
      imports: [PagoComponent],
      providers: [
        { provide: StripeService, useValue: stripeServiceSpy },
        { provide: ActivatedRoute, useValue: activatedRouteMock }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(PagoComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    component.ngOnDestroy();
  });

  it('inicializa y consulta estado inicial para la venta indicada en la ruta', () => {
    fixture.detectChanges();
    expect(component.ventaId).toBe('vta-501');
    expect(stripeServiceSpy.consultarEstado).toHaveBeenCalledWith('vta-501');
  });

  describe('Estado SIN_INTENCION y PENDIENTE', () => {
    it('inicia o reutiliza la intención de pago cuando el estado es SIN_INTENCION', () => {
      stripeServiceSpy.consultarEstado.and.returnValue(of(mockEstadoSinIntencion));
      fixture.detectChanges();

      expect(stripeServiceSpy.crearIntencion).toHaveBeenCalledWith('vta-501', jasmine.any(String));
      expect(component.intencion).toEqual(mockIntencion);
      expect(component.esPendiente).toBeTrue();
    });

    it('permite continuar y reutiliza la intención cuando el estado es PENDIENTE', () => {
      stripeServiceSpy.consultarEstado.and.returnValue(of(mockEstadoPendiente));
      fixture.detectChanges();

      expect(stripeServiceSpy.crearIntencion).toHaveBeenCalledWith('vta-501', jasmine.any(String));
      expect(component.esPendiente).toBeTrue();
    });
  });

  describe('Estados definitivos APROBADO, RECHAZADO y ANULADO', () => {
    it('reconoce el estado APROBADO y no solicita crear intención', () => {
      stripeServiceSpy.consultarEstado.and.returnValue(of(mockEstadoAprobado));
      fixture.detectChanges();

      expect(component.esAprobado).toBeTrue();
      expect(component.exito).toContain('Pago aprobado correctamente');
      expect(stripeServiceSpy.crearIntencion).not.toHaveBeenCalled();
    });

    it('reconoce el estado RECHAZADO permitiendo reintento', () => {
      stripeServiceSpy.consultarEstado.and.returnValue(of(mockEstadoRechazado));
      fixture.detectChanges();

      expect(component.esRechazado).toBeTrue();
      expect(component.esAprobado).toBeFalse();

      // Al reintentar, genera nuevo intento lógico y llama a reintentar
      stripeServiceSpy.reintentar.and.returnValue(of(mockIntencion));
      component.reintentar();

      expect(stripeServiceSpy.reintentar).toHaveBeenCalledWith('vta-501', jasmine.any(String));
    });

    it('reconoce el estado ANULADO / CANCELADA', () => {
      stripeServiceSpy.consultarEstado.and.returnValue(of(mockEstadoAnulado));
      fixture.detectChanges();

      expect(component.esCanceladoOAnulado).toBeTrue();
    });
  });

  describe('Polling y Confirmación Definitiva en Backend', () => {
    it('no declara pagada la venta solo con Stripe.js; inicia polling y espera confirmación backend', fakeAsync(() => {
      fixture.detectChanges();

      // Simular confirmación en Stripe.js
      const fakeStripe = {
        confirmCardPayment: jasmine.createSpy().and.resolveTo({})
      };
      (component as any).stripe = fakeStripe;
      (component as any).cardElement = {};
      component.intencion = mockIntencion;

      // El polling inicial aún consulta estado PENDIENTE, luego APROBADO
      stripeServiceSpy.consultarEstado.and.returnValues(
        of(mockEstadoPendiente),
        of(mockEstadoAprobado)
      );

      component.confirmarPago();
      tick(); // resuelve confirmCardPayment

      // No está aprobado inmediatamente por el retorno del SDK
      expect(component.exito).toBeNull();

      // Avanza el timer de polling (3000ms)
      tick(3000);
      expect(stripeServiceSpy.consultarEstado).toHaveBeenCalled();

      // Segundo intervalo de polling: backend confirma APROBADO
      tick(3000);
      expect(component.esAprobado).toBeTrue();
      expect(component.exito).toBe('Pago aprobado correctamente.');

      discardPeriodicTasks();
    }));

    it('detiene el polling inmediatamente al destruir el componente', fakeAsync(() => {
      fixture.detectChanges();
      (component as any).iniciarPolling();

      expect((component as any).pollingTimer).not.toBeNull();
      component.ngOnDestroy();
      expect((component as any).pollingTimer).toBeNull();

      discardPeriodicTasks();
    }));

    it('detiene polling por timeout tras MAX_POLLS y activa aviso recuperable', fakeAsync(() => {
      fixture.detectChanges();
      stripeServiceSpy.consultarEstado.and.returnValue(of(mockEstadoPendiente));

      (component as any).iniciarPolling();

      // Avanzar los 30 intervalos de 3000ms
      for (let i = 0; i < 31; i++) {
        tick(3000);
      }

      expect(component.avisoTimeout).toBeTrue();
      expect((component as any).pollingTimer).toBeNull();

      discardPeriodicTasks();
    }));

    it('maneja el flujo de autenticación 3D-Secure cuando se requiere acción bancaria', fakeAsync(() => {
      fixture.detectChanges();
      const mockStripe = {
        confirmCardPayment: jasmine.createSpy('confirmCardPayment').and.returnValue(
          Promise.resolve({ error: { code: 'authentication_required', message: 'Autenticación requerida' } })
        ),
        handleCardAction: jasmine.createSpy('handleCardAction').and.returnValue(
          Promise.resolve({ paymentIntent: { status: 'succeeded' } })
        )
      };
      (component as any).stripe = mockStripe;
      (component as any).cardElement = {};
      component.intencion = mockIntencion;

      component.confirmarPago();
      tick();

      expect(component.requiereAccion3DS).toBeTrue();
      expect(component.error).toContain('3D-Secure');

      component.continuarAccion3DS();
      tick();

      expect(mockStripe.handleCardAction).toHaveBeenCalledWith(mockIntencion.client_secret);
      expect(component.requiereAccion3DS).toBeFalse();

      discardPeriodicTasks();
    }));
  });
});
