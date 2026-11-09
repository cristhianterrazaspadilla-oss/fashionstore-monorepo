import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import {
  CheckoutComponent,
  calcularHuellaCanonicaV3,
  HuellaCanonicaParams
} from './checkout.component';
import { CarritoService } from '../services/carrito.service';
import { EntregaService } from '../services/entrega.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { EnriquecimientoService } from '../../catalogo/services/enriquecimiento.service';
import { SincronizacionOfflineService } from '../../../core/services/sincronizacion-offline.service';
import { StripeService } from '../services/stripe.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { CarritoDTO, CoberturaDTO, CotizacionDTO } from '../models/venta-digital.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';

describe('CheckoutComponent (Formulario reactivo, Validaciones e Idempotencia)', () => {
  let component: CheckoutComponent;
  let fixture: ComponentFixture<CheckoutComponent>;

  let carritoServiceSpy: jasmine.SpyObj<CarritoService>;
  let entregaServiceSpy: jasmine.SpyObj<EntregaService>;
  let orgServiceSpy: jasmine.SpyObj<OrganizacionService>;
  let enriquecimientoServiceSpy: jasmine.SpyObj<EnriquecimientoService>;
  let sincronizacionServiceSpy: jasmine.SpyObj<SincronizacionOfflineService>;
  let stripeServiceSpy: jasmine.SpyObj<StripeService>;
  let routerSpy: jasmine.SpyObj<Router>;

  const mockCarrito: CarritoDTO = {
    id: 'cart-1',
    cliente_id: 'cli-1',
    canal: 'WEB',
    estado: 'ACTIVO',
    creada_en: '2026-09-20T10:00:00Z',
    actualizada_en: '2026-09-20T10:00:00Z',
    lineas: [
      { id: 'l-1', variante_id: 'v-1', cantidad: 2, precio_unitario: 100, descuento_unitario: 0, promocion_id: null, subtotal: 200 }
    ],
    subtotal: 200,
    descuento_total: 0,
    total: 200
  };

  const mockCobertura: CoberturaDTO = {
    sucursales: [
      {
        sucursal_id: 'suc-1',
        sucursal_nombre: 'Sucursal Central',
        cubre_todo: true,
        faltantes: []
      }
    ]
  };

  const mockSucursales: SucursalDTO[] = [
    {
      id: 'suc-1',
      ciudad_id: 'ciu-1',
      nombre: 'Sucursal Central',
      direccion: 'Av. Siempre Viva 123',
      telefono: '70000000',
      numero_anillo: 1,
      tarifa_base_delivery: 15,
      incremento_anillo_delivery: 5,
      anillo_minimo_delivery: 1,
      anillo_maximo_delivery: 5,
      delivery_activo: true,
      activa: true
    },
    {
      id: 'suc-2',
      ciudad_id: 'ciu-1',
      nombre: 'Sucursal Peatonal',
      direccion: 'Calle Comercio 456',
      telefono: '70000001',
      numero_anillo: 1,
      tarifa_base_delivery: 0,
      incremento_anillo_delivery: 0,
      anillo_minimo_delivery: 1,
      anillo_maximo_delivery: 1,
      delivery_activo: false,
      activa: true
    }
  ];

  beforeEach(async () => {
    carritoServiceSpy = jasmine.createSpyObj<CarritoService>('CarritoService', [
      'obtenerMio', 'cobertura', 'checkout', 'vaciar'
    ]);
    entregaServiceSpy = jasmine.createSpyObj<EntregaService>('EntregaService', ['cotizar']);
    orgServiceSpy = jasmine.createSpyObj<OrganizacionService>('OrganizacionService', ['gestionarSucursales', 'obtenerTasaVigente']);
    enriquecimientoServiceSpy = jasmine.createSpyObj<EnriquecimientoService>('EnriquecimientoService', ['obtenerVariante']);
    sincronizacionServiceSpy = jasmine.createSpyObj<SincronizacionOfflineService>('SincronizacionOfflineService', [
      'registrarCompraOffline'
    ], {
      estaEnLinea: true
    });
    stripeServiceSpy = jasmine.createSpyObj<StripeService>('StripeService', [
      'prepararMetodo',
      'confirmarMetodo',
      'consultarMetodo',
      'cargarStripeJs'
    ]);
    stripeServiceSpy.cargarStripeJs.and.rejectWith(new Error('Test env - no DOM Stripe.js'));
    const authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', [
      'obtenerUsuarioActual',
      'obtenerEmpresaId'
    ]);
    authServiceSpy.obtenerUsuarioActual.and.returnValue({
      id: '55555555-5555-5555-5555-555555555555',
      usuario_id: '55555555-5555-5555-5555-555555555555',
      nombres: 'Cliente',
      apellidos: 'Test',
      correo: 'cliente@test.com',
      empresa_id: '11111111-1111-1111-1111-111111111111',
      empresa_codigo: 'fashionstore',
      roles: ['CLIENTE'],
      bloqueado_hasta: null
    } as any);
    authServiceSpy.obtenerEmpresaId.and.returnValue('11111111-1111-1111-1111-111111111111');
    routerSpy = jasmine.createSpyObj<Router>('Router', ['navigate']);

    orgServiceSpy.obtenerTasaVigente.and.returnValue(of({
      id: 'tasa-uuid-123',
      tasa_bob_por_usd: 6.96
    }));

    stripeServiceSpy.prepararMetodo.and.returnValue(of({
      preparacion_pago_id: 'prep-mock-123',
      client_secret: 'seti_secret_123',
      estado: 'LISTO'
    }));
    stripeServiceSpy.confirmarMetodo.and.returnValue(of({
      preparacion_pago_id: 'prep-mock-123',
      client_secret: 'seti_secret_123',
      estado: 'LISTO'
    }));
    stripeServiceSpy.consultarMetodo.and.returnValue(of({
      preparacion_pago_id: 'prep-mock-123',
      client_secret: 'seti_secret_123',
      estado: 'LISTO'
    }));

    carritoServiceSpy.obtenerMio.and.returnValue(of(mockCarrito));
    carritoServiceSpy.cobertura.and.returnValue(of(mockCobertura));
    orgServiceSpy.gestionarSucursales.and.returnValue(of(mockSucursales));
    enriquecimientoServiceSpy.obtenerVariante.and.returnValue(of({
      variante_id: 'v-1',
      sku: 'SKU-01',
      precio: 100,
      producto_id: 'prod-1',
      nombre_producto: 'Camisa Lino',
      talla_nombre: 'M',
      color_nombre: 'Blanco',
      imagen_url: ''
    }));

    await TestBed.configureTestingModule({
      imports: [CheckoutComponent],
      providers: [
        { provide: CarritoService, useValue: carritoServiceSpy },
        { provide: EntregaService, useValue: entregaServiceSpy },
        { provide: OrganizacionService, useValue: orgServiceSpy },
        { provide: EnriquecimientoService, useValue: enriquecimientoServiceSpy },
        { provide: SincronizacionOfflineService, useValue: sincronizacionServiceSpy },
        { provide: StripeService, useValue: stripeServiceSpy },
        { provide: AuthService, useValue: authServiceSpy },
        { provide: Router, useValue: routerSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(CheckoutComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('inicializa los datos del carrito, cobertura y sucursales', () => {
    expect(component.carrito).toEqual(mockCarrito);
    expect(component.cobertura).toEqual(mockCobertura);
    expect(component.sucursales.length).toBe(2);
    expect(component.cargando).toBeFalse();
  });

  describe('Validación de modalidad RECOJO', () => {
    it('requiere sucursal pero no exige dirección ni anillo', () => {
      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');

      expect(component.checkoutForm.valid).toBeTrue();
      expect(component.puedeConfirmar).toBeTrue();
    });

    it('es inválido si falta seleccionar la sucursal', () => {
      component.checkoutForm.controls.sucursalId.setValue('');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');

      expect(component.puedeConfirmar).toBeFalse();
    });
  });

  describe('Validación de modalidad DELIVERY', () => {
    beforeEach(() => {
      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('DELIVERY');
    });

    it('exige dirección, anillo (1-12) y cotización calculada para poder confirmar', () => {
      // Sin dirección ni anillo ni cotización
      expect(component.puedeConfirmar).toBeFalse();

      // Con dirección muy corta
      component.checkoutForm.controls.direccion.setValue('Abc');
      component.checkoutForm.controls.anilloDestino.setValue(2);
      expect(component.checkoutForm.controls.direccion.valid).toBeFalse();
      expect(component.puedeConfirmar).toBeFalse();

      // Con dirección válida y anillo pero sin cotización
      component.checkoutForm.controls.direccion.setValue('Calle Los Pinos #456');
      expect(component.checkoutForm.controls.direccion.valid).toBeTrue();
      expect(component.puedeConfirmar).toBeFalse();

      // Al recibir cotización exitosa, puedeConfirmar es verdadero
      const mockCotizacion: CotizacionDTO = {
        sucursal_id: 'suc-1',
        anillo_sucursal: 1,
        anillo_destino: 2,
        costo_entrega: 15,
        tarifa_base: 10,
        incremento_anillo: 5
      };
      component.cotizacion = mockCotizacion;
      expect(component.puedeConfirmar).toBeTrue();
    });

    it('ejecuta cotización mediante EntregaService', () => {
      const mockCotizacion: CotizacionDTO = {
        sucursal_id: 'suc-1',
        anillo_sucursal: 1,
        anillo_destino: 3,
        costo_entrega: 20,
        tarifa_base: 10,
        incremento_anillo: 5
      };
      entregaServiceSpy.cotizar.and.returnValue(of(mockCotizacion));

      component.checkoutForm.controls.anilloDestino.setValue(3);
      component.cotizar();

      expect(entregaServiceSpy.cotizar).toHaveBeenCalledWith('suc-1', 3);
      expect(component.cotizacion).toEqual(mockCotizacion);
    });
  });

  describe('Idempotencia y Prevención de Doble Envío', () => {
    it('mantiene la misma Idempotency-Key ante un reintento técnico idéntico tras error', () => {
      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');

      // Primer intento: simula error de red
      carritoServiceSpy.checkout.and.returnValue(throwError(() => new Error('Error de conexión')));
      component.confirmarCheckout();

      expect(carritoServiceSpy.checkout).toHaveBeenCalledTimes(1);
      const primeraClave = carritoServiceSpy.checkout.calls.mostRecent().args[1];
      expect(primeraClave).toBeTruthy();
      expect(component.procesando).toBeFalse();

      // Reintento técnico con los mismos parámetros: DEBE conservar la misma clave
      carritoServiceSpy.checkout.and.returnValue(of({ venta_id: 'vta-100' } as any));
      component.confirmarCheckout();

      expect(carritoServiceSpy.checkout).toHaveBeenCalledTimes(2);
      const segundaClave = carritoServiceSpy.checkout.calls.mostRecent().args[1];
      expect(segundaClave).toBe(primeraClave);
      expect(routerSpy.navigate).toHaveBeenCalledWith(['/pago', 'vta-100']);
    });

    it('genera una nueva Idempotency-Key cuando cambia el intento lógico (parámetros)', () => {
      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');

      carritoServiceSpy.checkout.and.returnValue(of({ venta_id: 'vta-101' } as any));
      component.confirmarCheckout();

      const primeraClave = carritoServiceSpy.checkout.calls.mostRecent().args[1];

      // El usuario cambia a DELIVERY con dirección y cotización
      component.checkoutForm.controls.modalidad.setValue('DELIVERY');
      component.checkoutForm.controls.direccion.setValue('Av. Ballivian 789');
      component.checkoutForm.controls.anilloDestino.setValue(4);
      component.cotizacion = { sucursal_id: 'suc-1', anillo_sucursal: 1, anillo_destino: 4, costo_entrega: 25, tarifa_base: 10, incremento_anillo: 5 };

      component.confirmarCheckout();

      const segundaClave = carritoServiceSpy.checkout.calls.mostRecent().args[1];
      expect(segundaClave).not.toBe(primeraClave);
    });

    it('bloquea envíos duplicados si ya está procesando', () => {
      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');

      component.procesando = true;
      component.confirmarCheckout();

      expect(carritoServiceSpy.checkout).not.toHaveBeenCalled();
    });

    it('calcula totalVisible sumando importes sin concatenar cadenas cuando total y delivery son strings', () => {
      component.carrito = { ...mockCarrito, total: '100.50' as any };
      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('DELIVERY');
      component.checkoutForm.controls.anilloDestino.setValue(2);
      component.cotizacion = {
        sucursal_id: 'suc-1',
        anillo_sucursal: 1,
        anillo_destino: 2,
        costo_entrega: '15.25' as any,
        tarifa_base: '10.00' as any,
        incremento_anillo: '5.25' as any
      };

      expect(component.totalVisible).toBe(115.75);
      expect(component.bs(component.totalVisible)).toContain('115');
    });

    it('invalida la cotización si cambia la sucursal o el anillo de destino', () => {
      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('DELIVERY');
      component.checkoutForm.controls.direccion.setValue('Av. Principal 123');
      component.checkoutForm.controls.anilloDestino.setValue(2);
      component.cotizacion = {
        sucursal_id: 'suc-1',
        anillo_sucursal: 1,
        anillo_destino: 2,
        costo_entrega: 20,
        tarifa_base: 10,
        incremento_anillo: 10
      };

      expect(component.cotizacionEsVigente).toBeTrue();
      expect(component.puedeConfirmar).toBeTrue();

      // Cambia el anillo
      component.checkoutForm.controls.anilloDestino.setValue(4);
      expect(component.cotizacion).toBeNull();
      expect(component.cotizacionEsVigente).toBeFalse();
      expect(component.requiereRecalcularCotizacion).toBeTrue();
      expect(component.puedeConfirmar).toBeFalse();
    });

    it('si se cambia desde una sucursal con delivery hacia una sucursal sin delivery, cambia de forma segura a RECOJO', () => {
      // Configurar sucursal 1 (con delivery) en modalidad DELIVERY
      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('DELIVERY');
      component.checkoutForm.controls.direccion.setValue('Av. Los Olivos 123');
      component.checkoutForm.controls.anilloDestino.setValue(2);
      expect(component.modalidadSeleccionada).toBe('DELIVERY');

      // Cambiar a sucursal 2 (sin delivery)
      component.checkoutForm.controls.sucursalId.setValue('suc-2');

      // Debe haber cambiado a RECOJO automáticamente y eliminado cotización
      expect(component.modalidadSeleccionada).toBe('RECOJO');
      expect(component.cotizacion).toBeNull();
      expect(component.puedeConfirmar).toBeTrue();
    });

    it('permite guardar la compra en cola offline cuando se encuentra sin conexión', fakeAsync(() => {
      // Simular offline
      spyOnProperty(component, 'estaEnLinea', 'get').and.returnValue(false);
      sincronizacionServiceSpy.registrarCompraOffline.and.returnValue(Promise.resolve({
        operacion_id: 'op-compra-123',
        version_esquema: 1,
        tipo: 'SOLICITAR_COMPRA',
        creada_local_en: '2026-11-04T12:00:00-04:00',
        empresa_id: 'emp-1',
        usuario_id: 'usr-1',
        dispositivo_id: 'disp-1',
        secuencia_local: 1,
        referencia_horaria_id: 'ref-1',
        datos: {} as any,
        estado_envio: 'PENDIENTE_ENVIO',
        actualizado_en: '2026-11-04T12:00:00-04:00'
      }));
      carritoServiceSpy.vaciar.and.returnValue(of({} as any));

      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');

      component.confirmarCheckout();
      tick();

      expect(sincronizacionServiceSpy.registrarCompraOffline).toHaveBeenCalled();
      expect(routerSpy.navigate).toHaveBeenCalledWith(['/mis-pedidos']);
    }));

    it('prepara el método de pago cuando se invoca prepararMetodoPago', () => {
      component.prepararMetodoPago();
      expect(stripeServiceSpy.prepararMetodo).toHaveBeenCalled();
      expect(component.preparacionPagoId).toBe('prep-mock-123');
    });

    it('incluye autorizacion_cobro v3 en la compra offline si el cliente otorga consentimiento', fakeAsync(() => {
      spyOnProperty(component, 'estaEnLinea', 'get').and.returnValue(false);
      sincronizacionServiceSpy.registrarCompraOffline.and.returnValue(Promise.resolve({
        operacion_id: 'op-compra-v3',
        version_esquema: 3,
        tipo: 'SOLICITAR_COMPRA',
        creada_local_en: '2026-11-04T12:00:00-04:00',
        empresa_id: 'emp-1',
        usuario_id: 'usr-1',
        dispositivo_id: 'disp-1',
        secuencia_local: 1,
        referencia_horaria_id: 'ref-1',
        datos: {} as any,
        estado_envio: 'PENDIENTE_ENVIO',
        actualizado_en: '2026-11-04T12:00:00-04:00'
      }));
      carritoServiceSpy.vaciar.and.returnValue(of({} as any));

      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');
      component.consentimientoCobroV3 = true;
      component.preparacionPagoId = 'prep-mock-123';
      component.metodoPreparadoExito = true;

      component.confirmarCheckout();
      tick();

      expect(sincronizacionServiceSpy.registrarCompraOffline).toHaveBeenCalledWith(
        jasmine.objectContaining({
          autorizacion_cobro: jasmine.objectContaining({
            preparacion_pago_id: 'prep-mock-123',
            permite_cobro_al_reconectar: true
          })
        })
      );
    }));
  });

  describe('P0 CU05 PWA Checkout y Método Preparado (CU22 Stripe en PWA)', () => {
    it('ciclo DOM real de Stripe Elements: montaje, renderizado, llamada a confirmCardSetup con el elemento y transición a LISTO (Auditoría 28)', fakeAsync(() => {
      component.paso = 'confirmacion';
      fixture.detectChanges();

      stripeServiceSpy.prepararMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-dom-cycle-1',
        client_secret: 'seti_dom_secret_123',
        estado: 'PENDIENTE'
      }));

      const fakeCardElement = {
        mount: jasmine.createSpy('mount'),
        destroy: jasmine.createSpy('destroy'),
        on: jasmine.createSpy('on')
      };

      const fakeElements = {
        create: jasmine.createSpy('create').and.returnValue(fakeCardElement)
      };

      const fakeStripe = {
        elements: jasmine.createSpy('elements').and.returnValue(fakeElements),
        confirmCardSetup: jasmine.createSpy('confirmCardSetup').and.resolveTo({
          setupIntent: {
            id: 'seti_dom_123',
            status: 'succeeded',
            payment_method: 'pm_card_dom_real_9999'
          }
        })
      };

      component.stripe = fakeStripe;
      component.cardElement = null; // Ciclo real: inicialmente null
      expect(component.mostrandoFormularioTarjeta).toBeFalse();

      // 1. Iniciar preparación: recibe client_secret y activa mostrandoFormularioTarjeta
      component.prepararMetodoPago();
      tick(); // resuelve promesas internas y setTimeout de montaje
      fixture.detectChanges();

      expect(stripeServiceSpy.prepararMetodo).toHaveBeenCalled();
      expect(component.mostrandoFormularioTarjeta).toBeTrue();
      expect(fakeElements.create).toHaveBeenCalledWith('card', jasmine.any(Object));
      expect(fakeCardElement.mount).toHaveBeenCalledWith('#card-element');
      expect(component.cardElementMontado).toBeTrue();
      // Debe iniciar en false hasta que el usuario complete los campos
      expect(component.cardElementValido).toBeFalse();

      // Verificar que el contenedor de tarjeta existe en el DOM
      const cardContainer = fixture.nativeElement.querySelector('#card-element');
      expect(cardContainer).toBeTruthy();

      // El botón de guardar tarjeta debe estar deshabilitado mientras cardElementValido sea false
      const btnConfirmar = fixture.nativeElement.querySelector('.btn-confirmar-tarjeta');
      expect(btnConfirmar.disabled).toBeTrue();

      // Simular ingreso de tarjeta completa por el usuario
      const changeHandler = fakeCardElement.on.calls.allArgs().find(arg => arg[0] === 'change')?.[1];
      expect(changeHandler).toBeDefined();

      // 1a. Tarjeta incompleta: sigue deshabilitado
      changeHandler({ complete: false, error: null });
      fixture.detectChanges();
      expect(component.cardElementValido).toBeFalse();
      expect(btnConfirmar.disabled).toBeTrue();

      // 1b. Error en tarjeta: muestra mensaje de error y sigue deshabilitado
      changeHandler({ complete: false, error: { message: 'El número de tarjeta es inválido.' } });
      fixture.detectChanges();
      expect(component.cardElementValido).toBeFalse();
      expect(component.errorTarjeta).toBe('El número de tarjeta es inválido.');
      expect(btnConfirmar.disabled).toBeTrue();

      // 1c. Tarjeta completa y válida: habilita botón
      changeHandler({ complete: true, error: null });
      fixture.detectChanges();
      expect(component.cardElementValido).toBeTrue();
      expect(btnConfirmar.disabled).toBeFalse();

      // 2. Simular confirmación del usuario con el botón de guardar tarjeta
      stripeServiceSpy.confirmarMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-dom-cycle-1',
        client_secret: 'seti_dom_secret_123',
        estado: 'PENDIENTE'
      }));
      stripeServiceSpy.consultarMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-dom-cycle-1',
        client_secret: '',
        estado: 'LISTO'
      }));

      component.confirmarTarjetaStripe();
      tick(); // resuelve confirmCardSetup y suscripciones
      fixture.detectChanges();

      // 3. Verifica que confirmCardSetup recibió exactamente el cardElement montado
      expect(fakeStripe.confirmCardSetup).toHaveBeenCalledWith('seti_dom_secret_123', {
        payment_method: { card: fakeCardElement }
      });

      // 4. Verifica envío del payment_method_id obtenido al backend
      expect(stripeServiceSpy.confirmarMetodo).toHaveBeenCalledWith('prep-dom-cycle-1', {
        payment_method_id: 'pm_card_dom_real_9999'
      });

      // 5. Verifica transición a LISTO, desmontaje del elemento y ocultamiento del formulario
      expect(stripeServiceSpy.consultarMetodo).toHaveBeenCalledWith('prep-dom-cycle-1');
      expect(component.metodoPreparadoExito).toBeTrue();
      expect(component.mostrandoFormularioTarjeta).toBeFalse();
      expect(fakeCardElement.destroy).toHaveBeenCalled();
      expect(component.clientSecretActual).toBeNull();
    }));

    it('falla cerrado si el SDK de Stripe no está disponible (no crea dummy element)', fakeAsync(() => {
      component.paso = 'confirmacion';
      fixture.detectChanges();

      stripeServiceSpy.prepararMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-no-sdk',
        client_secret: 'seti_secret_no_sdk',
        estado: 'PENDIENTE'
      }));

      component.stripe = null;
      (window as any).Stripe = undefined;
      stripeServiceSpy.cargarStripeJs.and.rejectWith(new Error('Network error loading Stripe.js'));

      component.prepararMetodoPago();
      tick();
      fixture.detectChanges();

      expect(component.cardElementMontado).toBeFalse();
      expect(component.cardElementValido).toBeFalse();
      expect(component.cardElement).toBeNull();
      expect(component.errorTarjeta).toContain('No se pudo cargar la pasarela segura de Stripe');
    }));

    it('[CONTRAEJEMPLO ROJO] rechaza emulador global window.stripeElementsEmulator en producción', async () => {
      component.stripe = null;
      (window as any).stripeElementsEmulator = {
        confirmCardSetup: jasmine.createSpy('confirmCardSetup').and.resolveTo({
          setupIntent: { payment_method: 'pm_emulated_fake' }
        })
      };
      try {
        const res = await component.confirmarSetupIntentConPasarela('seti_secret_test');
        expect(res.paymentMethodId).toBeUndefined();
        expect(res.error).toContain('No se pudo cargar el formulario');
      } finally {
        delete (window as any).stripeElementsEmulator;
      }
    });

    it('falla cerrado si el montaje del elemento en el DOM falla', fakeAsync(() => {
      component.paso = 'confirmacion';
      fixture.detectChanges();

      stripeServiceSpy.prepararMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-mount-fail',
        client_secret: 'seti_secret_mount_fail',
        estado: 'PENDIENTE'
      }));

      const failingCardElement = {
        mount: jasmine.createSpy('mount').and.throwError(new Error('DOM mount failure')),
        destroy: jasmine.createSpy('destroy'),
        on: jasmine.createSpy('on')
      };

      const fakeElements = {
        create: jasmine.createSpy('create').and.returnValue(failingCardElement)
      };

      const fakeStripe = {
        elements: jasmine.createSpy('elements').and.returnValue(fakeElements)
      };

      component.stripe = fakeStripe;

      component.prepararMetodoPago();
      tick();
      fixture.detectChanges();

      expect(component.cardElementMontado).toBeFalse();
      expect(component.cardElementValido).toBeFalse();
      expect(component.errorTarjeta).toContain('Error al montar el campo de tarjeta');
    }));

    it('desmonta elemento y purga clientSecret al cancelar o destruir componente', fakeAsync(() => {
      const mockCardElement = {
        destroy: jasmine.createSpy('destroy')
      };
      component.cardElement = mockCardElement;
      component.clientSecretActual = 'seti_secret_leak_test';
      component.cardElementMontado = true;
      component.cardElementValido = true;

      component.cancelarFormularioTarjeta();

      expect(mockCardElement.destroy).toHaveBeenCalled();
      expect(component.cardElement).toBeNull();
      expect(component.cardElementMontado).toBeFalse();
      expect(component.cardElementValido).toBeFalse();
      expect(component.clientSecretActual).toBeNull();
    }));

    it('confirmación con tarjeta ingresada a través de Stripe Elements y revalidación LISTO en backend', fakeAsync(() => {
      stripeServiceSpy.prepararMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-setup-100',
        client_secret: 'seti_secret_real_100',
        estado: 'PENDIENTE'
      }));
      // Simular ingreso de tarjeta por el usuario y confirmación con el SDK Stripe.js / Elements
      const fakeStripe = {
        confirmCardSetup: jasmine.createSpy('confirmCardSetup').and.resolveTo({
          setupIntent: {
            id: 'seti_100',
            status: 'succeeded',
            payment_method: 'pm_card_ingresada_4242'
          }
        })
      };
      component.stripe = fakeStripe;
      const cardInst = { id: 'card-element-instance' };
      component.cardElement = cardInst;

      stripeServiceSpy.confirmarMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-setup-100',
        client_secret: 'seti_secret_real_100',
        estado: 'PENDIENTE'
      }));
      stripeServiceSpy.consultarMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-setup-100',
        client_secret: '',
        estado: 'LISTO'
      }));
      localStorage.removeItem('fs_metodo_preparado_id');

      component.prepararMetodoPago();
      tick(); // resuelve confirmCardSetup

      expect(stripeServiceSpy.prepararMetodo).toHaveBeenCalled();
      expect(fakeStripe.confirmCardSetup).toHaveBeenCalledWith('seti_secret_real_100', {
        payment_method: { card: cardInst }
      });
      // Verifica que no se usó pm_card_visa estático, sino el ID devuelto por la tarjeta ingresada
      expect(stripeServiceSpy.confirmarMetodo).toHaveBeenCalledWith('prep-setup-100', {
        payment_method_id: 'pm_card_ingresada_4242'
      });
      // Verifica que consulta al backend antes de presentar éxito
      expect(stripeServiceSpy.consultarMetodo).toHaveBeenCalledWith('prep-setup-100');
      expect(component.metodoPreparadoExito).toBeTrue();
      expect(component.preparacionPagoId).toBe('prep-setup-100');
      expect(localStorage.getItem('fs_metodo_preparado_id')).toBe('prep-setup-100');
    }));

    it('fallo en pasarela al validar la tarjeta no marca éxito ni persiste en localStorage', fakeAsync(() => {
      stripeServiceSpy.prepararMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-fail-200',
        client_secret: 'seti_fail_secret',
        estado: 'PENDIENTE'
      }));
      const fakeStripe = {
        confirmCardSetup: jasmine.createSpy('confirmCardSetup').and.resolveTo({
          error: { message: 'Tu tarjeta no dispone de fondos suficientes.' }
        })
      };
      component.stripe = fakeStripe;
      component.cardElement = {};
      localStorage.removeItem('fs_metodo_preparado_id');

      component.prepararMetodoPago();
      tick();

      expect(fakeStripe.confirmCardSetup).toHaveBeenCalled();
      expect(stripeServiceSpy.confirmarMetodo).not.toHaveBeenCalled();
      expect(component.metodoPreparadoExito).toBeFalse();
      expect(component.error).toBe('Tu tarjeta no dispone de fondos suficientes.');
      expect(localStorage.getItem('fs_metodo_preparado_id')).toBeNull();
      expect(component.preparandoMetodo).toBeFalse();
    }));

    it('si el backend responde PENDIENTE tras confirmar, muestra estado visible y no marca éxito prematuro', fakeAsync(() => {
      stripeServiceSpy.prepararMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-pend-300',
        client_secret: 'seti_pend_secret',
        estado: 'PENDIENTE'
      }));
      const fakeStripe = {
        confirmCardSetup: jasmine.createSpy('confirmCardSetup').and.resolveTo({
          setupIntent: { id: 'seti_300', status: 'succeeded', payment_method: 'pm_pend_7777' }
        })
      };
      component.stripe = fakeStripe;
      component.cardElement = {};
      stripeServiceSpy.confirmarMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-pend-300',
        client_secret: '',
        estado: 'PENDIENTE'
      }));
      stripeServiceSpy.consultarMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-pend-300',
        client_secret: '',
        estado: 'PENDIENTE'
      }));
      localStorage.removeItem('fs_metodo_preparado_id');

      component.prepararMetodoPago();
      tick();

      expect(stripeServiceSpy.consultarMetodo).toHaveBeenCalledWith('prep-pend-300');
      expect(component.metodoPreparadoExito).toBeFalse();
      expect(component.error).toContain('PENDIENTE');
      expect(localStorage.getItem('fs_metodo_preparado_id')).toBeNull();
      expect(component.preparandoMetodo).toBeFalse();
    }));

    it('ngOnInit con localStorage consulta al backend antes de marcar éxito', () => {
      localStorage.setItem('fs_metodo_preparado_id', 'prep-guardado-123');
      stripeServiceSpy.consultarMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-guardado-123',
        client_secret: '',
        estado: 'LISTO'
      }));

      component.ngOnInit();

      expect(stripeServiceSpy.consultarMetodo).toHaveBeenCalledWith('prep-guardado-123');
      expect(component.metodoPreparadoExito).toBeTrue();
      expect(component.metodoPreparadoId).toBe('prep-guardado-123');
      expect(localStorage.getItem('fs_metodo_preparado_id')).toBe('prep-guardado-123');
    });

    it('ngOnInit con localStorage purga de almacenamiento si el servidor indica PENDIENTE', () => {
      localStorage.setItem('fs_metodo_preparado_id', 'prep-invalido-456');
      stripeServiceSpy.consultarMetodo.and.returnValue(of({
        preparacion_pago_id: 'prep-invalido-456',
        client_secret: '',
        estado: 'PENDIENTE'
      }));

      component.ngOnInit();

      expect(stripeServiceSpy.consultarMetodo).toHaveBeenCalledWith('prep-invalido-456');
      expect(component.metodoPreparadoExito).toBeFalse();
      expect(component.metodoPreparadoId).toBeNull();
      expect(localStorage.getItem('fs_metodo_preparado_id')).toBeNull();
    });

    it('ngOnInit con localStorage purga de almacenamiento si pertenece a otro usuario o empresa (HTTP 403)', () => {
      localStorage.setItem('fs_metodo_preparado_id', 'prep-ajeno-789');
      stripeServiceSpy.consultarMetodo.and.returnValue(throwError(() => ({
        status: 403,
        error: { detail: 'No autorizado para confirmar método de otra empresa' }
      })));

      component.ngOnInit();

      expect(stripeServiceSpy.consultarMetodo).toHaveBeenCalledWith('prep-ajeno-789');
      expect(component.metodoPreparadoExito).toBeFalse();
      expect(component.metodoPreparadoId).toBeNull();
      expect(localStorage.getItem('fs_metodo_preparado_id')).toBeNull();
    });
  });

  describe('Prevención de método ficticio y tasa inventada (Bloqueo 3)', () => {
    it('si falta tasaId o tasaCambioVigente, OMITE completamente autorizacion_cobro (undefined)', fakeAsync(() => {
      spyOnProperty(component, 'estaEnLinea', 'get').and.returnValue(false);
      sincronizacionServiceSpy.registrarCompraOffline.and.returnValue(Promise.resolve({
        operacion_id: 'op-sin-tasa',
        version_esquema: 1,
        tipo: 'SOLICITAR_COMPRA',
        creada_local_en: '2026-11-04T12:00:00-04:00',
        empresa_id: 'emp-1',
        usuario_id: 'usr-1',
        dispositivo_id: 'disp-1',
        secuencia_local: 1,
        referencia_horaria_id: 'ref-1',
        datos: {} as any,
        estado_envio: 'PENDIENTE_ENVIO',
        actualizado_en: '2026-11-04T12:00:00-04:00'
      }));
      carritoServiceSpy.vaciar.and.returnValue(of({} as any));

      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');
      component.consentimientoCobroV3 = true;
      component.metodoPreparadoId = 'prep-mock-123';
      component.metodoPreparadoExito = true;

      // Desactivar tasa intencionalmente
      component.tasaId = null;

      expect(component.tieneTasaValida).toBeFalse();

      component.confirmarCheckout();
      tick();

      expect(sincronizacionServiceSpy.registrarCompraOffline).toHaveBeenCalled();
      const llamado = sincronizacionServiceSpy.registrarCompraOffline.calls.mostRecent().args[0];
      // Si falta tasa, autorizacion_cobro debe estar completamente ausente (undefined)
      expect(llamado.autorizacion_cobro).toBeUndefined();
    }));

    it('si metodoPreparadoExito es falso, OMITE completamente autorizacion_cobro (undefined)', fakeAsync(() => {
      spyOnProperty(component, 'estaEnLinea', 'get').and.returnValue(false);
      sincronizacionServiceSpy.registrarCompraOffline.and.returnValue(Promise.resolve({
        operacion_id: 'op-sin-metodo',
        version_esquema: 1,
        tipo: 'SOLICITAR_COMPRA',
        creada_local_en: '2026-11-04T12:00:00-04:00',
        empresa_id: 'emp-1',
        usuario_id: 'usr-1',
        dispositivo_id: 'disp-1',
        secuencia_local: 1,
        referencia_horaria_id: 'ref-1',
        datos: {} as any,
        estado_envio: 'PENDIENTE_ENVIO',
        actualizado_en: '2026-11-04T12:00:00-04:00'
      }));
      carritoServiceSpy.vaciar.and.returnValue(of({} as any));

      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');
      component.consentimientoCobroV3 = true;
      component.tasaId = '44444444-4444-4444-4444-444444444444';
      component.metodoPreparadoId = null;
      component.metodoPreparadoExito = false;

      component.confirmarCheckout();
      tick();

      expect(sincronizacionServiceSpy.registrarCompraOffline).toHaveBeenCalled();
      const llamado = sincronizacionServiceSpy.registrarCompraOffline.calls.mostRecent().args[0];
      // Si falta método LISTO, autorizacion_cobro debe estar completamente ausente (undefined)
      expect(llamado.autorizacion_cobro).toBeUndefined();
    }));

    it('si falta consentimiento del usuario, OMITE completamente autorizacion_cobro (undefined)', fakeAsync(() => {
      spyOnProperty(component, 'estaEnLinea', 'get').and.returnValue(false);
      sincronizacionServiceSpy.registrarCompraOffline.and.returnValue(Promise.resolve({
        operacion_id: 'op-sin-consentimiento',
        version_esquema: 1,
        tipo: 'SOLICITAR_COMPRA',
        creada_local_en: '2026-11-04T12:00:00-04:00',
        empresa_id: 'emp-1',
        usuario_id: 'usr-1',
        dispositivo_id: 'disp-1',
        secuencia_local: 1,
        referencia_horaria_id: 'ref-1',
        datos: {} as any,
        estado_envio: 'PENDIENTE_ENVIO',
        actualizado_en: '2026-11-04T12:00:00-04:00'
      }));
      carritoServiceSpy.vaciar.and.returnValue(of({} as any));

      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');
      component.consentimientoCobroV3 = false;
      component.tasaId = '44444444-4444-4444-4444-444444444444';
      component.metodoPreparadoId = 'prep-mock-123';
      component.metodoPreparadoExito = true;

      component.confirmarCheckout();
      tick();

      expect(sincronizacionServiceSpy.registrarCompraOffline).toHaveBeenCalled();
      const llamado = sincronizacionServiceSpy.registrarCompraOffline.calls.mostRecent().args[0];
      expect(llamado.autorizacion_cobro).toBeUndefined();
    }));

    it('con método preparado LISTO, tasa oficial vigente y consentimiento explícito emite el objeto completo con los 15 campos y permite_cobro_al_reconectar: true', fakeAsync(() => {
      spyOnProperty(component, 'estaEnLinea', 'get').and.returnValue(false);
      sincronizacionServiceSpy.registrarCompraOffline.and.returnValue(Promise.resolve({
        operacion_id: 'op-con-todo-valido',
        version_esquema: 3,
        tipo: 'SOLICITAR_COMPRA',
        creada_local_en: '2026-11-04T12:00:00-04:00',
        empresa_id: 'emp-1',
        usuario_id: 'usr-1',
        dispositivo_id: 'disp-1',
        secuencia_local: 1,
        referencia_horaria_id: 'ref-1',
        datos: {} as any,
        estado_envio: 'PENDIENTE_ENVIO',
        actualizado_en: '2026-11-04T12:00:00-04:00'
      }));
      carritoServiceSpy.vaciar.and.returnValue(of({} as any));

      component.checkoutForm.controls.sucursalId.setValue('suc-1');
      component.checkoutForm.controls.modalidad.setValue('RECOJO');
      component.consentimientoCobroV3 = true;
      component.autorizoCobroOffline = true;
      component.tasaId = '44444444-4444-4444-4444-444444444444';
      component.tasaCambioVigente = '6.96';
      component.metodoPreparadoId = 'prep-listo-999';
      component.metodoPreparadoExito = true;

      component.confirmarCheckout();
      tick();

      expect(sincronizacionServiceSpy.registrarCompraOffline).toHaveBeenCalled();
      const llamado = sincronizacionServiceSpy.registrarCompraOffline.calls.mostRecent().args[0];
      const aut = llamado.autorizacion_cobro;
      expect(aut).toBeDefined();
      expect(aut?.permite_cobro_al_reconectar).toBeTrue();
      expect(aut?.consentimiento_id).toBeDefined();
      expect(aut?.aceptado_local_en).toBeDefined();
      expect(aut?.huella_compra).toMatch(/^[a-f0-9]{64}$/);
      expect(aut?.base_bob).toBe('200.00');
      expect(aut?.descuento_bob).toBe('0.00');
      expect(aut?.envio_bob).toBe('0.00');
      expect(aut?.total_bob).toBe('200.00');
      expect(aut?.moneda_cobro).toBe('USD');
      expect(aut?.importe_cobro).toBe((200 / 6.96).toFixed(2));
      expect(aut?.tasa_id).toBe('44444444-4444-4444-4444-444444444444');
      expect(aut?.tasa_bob_por_usd).toBe('6.96');
      expect(aut?.condiciones_version).toBe('v3');
      expect(aut?.vigente_hasta).toBeDefined();
      expect(aut?.preparacion_pago_id).toBe('prep-listo-999');
    }));
  });

  describe('P1 Huella Canónica v3 (Vectores pactados y Sensibilidad)', () => {
    const vector1Params: HuellaCanonicaParams = {
      base_bob: '100.00',
      condiciones_version: 'v3',
      descuento_bob: '0.00',
      empresa_id: '11111111-1111-1111-1111-111111111111',
      envio_bob: '0.00',
      importe_cobro: '14.37',
      lineas: [
        {
          cantidad: 1,
          precio_unitario_bob: '100.00',
          variante_id: '22222222-2222-2222-2222-222222222222'
        }
      ],
      modalidad: 'RECOJO',
      moneda_cobro: 'USD',
      sucursal_id: '33333333-3333-3333-3333-333333333333',
      tasa_bob_por_usd: '6.96',
      tasa_id: '44444444-4444-4444-4444-444444444444',
      total_bob: '100.00',
      usuario_id: '55555555-5555-5555-5555-555555555555',
      vigente_hasta: '2026-11-06T15:00:00Z'
    };

    const vector2Params: HuellaCanonicaParams = {
      base_bob: '100.00',
      condiciones_version: 'v3',
      descuento_bob: '0.00',
      direccion: 'Av. Las Americas 123',
      empresa_id: '11111111-1111-1111-1111-111111111111',
      envio_bob: '15.00',
      importe_cobro: '16.52',
      lineas: [
        {
          cantidad: 1,
          precio_unitario_bob: '100.00',
          variante_id: '22222222-2222-2222-2222-222222222222'
        }
      ],
      modalidad: 'DELIVERY',
      moneda_cobro: 'USD',
      sucursal_id: '33333333-3333-3333-3333-333333333333',
      tasa_bob_por_usd: '6.96',
      tasa_id: '44444444-4444-4444-4444-444444444444',
      total_bob: '115.00',
      usuario_id: '55555555-5555-5555-5555-555555555555',
      vigente_hasta: '2026-11-06T15:00:00Z'
    };

    it('coincide exactamente con el Vector 1 pactado (RECOJO)', () => {
      const res = calcularHuellaCanonicaV3(vector1Params);
      expect(res.hash).toBe('5249e0cea418ec6262f9f0ef7a71686d2d6cecf8c4083dafe77aa0d24c3eacee');
      expect(res.json).toBe(
        '{"base_bob":"100.00","condiciones_version":"v3","descuento_bob":"0.00","empresa_id":"11111111-1111-1111-1111-111111111111","envio_bob":"0.00","importe_cobro":"14.37","lineas":[{"cantidad":1,"precio_unitario_bob":"100.00","variante_id":"22222222-2222-2222-2222-222222222222"}],"modalidad":"RECOJO","moneda_cobro":"USD","sucursal_id":"33333333-3333-3333-3333-333333333333","tasa_bob_por_usd":"6.96","tasa_id":"44444444-4444-4444-4444-444444444444","total_bob":"100.00","usuario_id":"55555555-5555-5555-5555-555555555555","vigente_hasta":"2026-11-06T15:00:00Z"}'
      );
    });

    it('coincide exactamente con el Vector 2 pactado (DELIVERY con dirección)', () => {
      const res = calcularHuellaCanonicaV3(vector2Params);
      expect(res.hash).toBe('b095703bdd526b2a7da5d97f5e52dbe7ec7a118d72511c72b9602cd03fd98f07');
      expect(res.json).toBe(
        '{"base_bob":"100.00","condiciones_version":"v3","descuento_bob":"0.00","direccion":"Av. Las Americas 123","empresa_id":"11111111-1111-1111-1111-111111111111","envio_bob":"15.00","importe_cobro":"16.52","lineas":[{"cantidad":1,"precio_unitario_bob":"100.00","variante_id":"22222222-2222-2222-2222-222222222222"}],"modalidad":"DELIVERY","moneda_cobro":"USD","sucursal_id":"33333333-3333-3333-3333-333333333333","tasa_bob_por_usd":"6.96","tasa_id":"44444444-4444-4444-4444-444444444444","total_bob":"115.00","usuario_id":"55555555-5555-5555-5555-555555555555","vigente_hasta":"2026-11-06T15:00:00Z"}'
      );
    });

    it('colapsa espacios redundantes en la dirección sin alterar el hash del Vector 2', () => {
      const conEspacios = {
        ...vector2Params,
        direccion: '  Av.   Las    Americas  123   '
      };
      const res = calcularHuellaCanonicaV3(conEspacios);
      expect(res.hash).toBe('b095703bdd526b2a7da5d97f5e52dbe7ec7a118d72511c72b9602cd03fd98f07');
    });

    it('alterar cualquier línea altera el hash', () => {
      const baseHash = '5249e0cea418ec6262f9f0ef7a71686d2d6cecf8c4083dafe77aa0d24c3eacee';

      // Cambiar cantidad
      const resCant = calcularHuellaCanonicaV3({
        ...vector1Params,
        lineas: [{ cantidad: 2, precio_unitario_bob: '100.00', variante_id: '22222222-2222-2222-2222-222222222222' }]
      });
      expect(resCant.hash).not.toBe(baseHash);

      // Cambiar variante_id
      const resVar = calcularHuellaCanonicaV3({
        ...vector1Params,
        lineas: [{ cantidad: 1, precio_unitario_bob: '100.00', variante_id: '99999999-9999-9999-9999-999999999999' }]
      });
      expect(resVar.hash).not.toBe(baseHash);

      // Cambiar precio unitario
      const resPrec = calcularHuellaCanonicaV3({
        ...vector1Params,
        lineas: [{ cantidad: 1, precio_unitario_bob: '99.99', variante_id: '22222222-2222-2222-2222-222222222222' }]
      });
      expect(resPrec.hash).not.toBe(baseHash);
    });

    it('alterar la tasa de cambio o tasa_id altera el hash', () => {
      const baseHash = '5249e0cea418ec6262f9f0ef7a71686d2d6cecf8c4083dafe77aa0d24c3eacee';

      // Cambiar tasa_bob_por_usd
      const resTasaVal = calcularHuellaCanonicaV3({
        ...vector1Params,
        tasa_bob_por_usd: '6.97'
      });
      expect(resTasaVal.hash).not.toBe(baseHash);

      // Cambiar tasa_id
      const resTasaId = calcularHuellaCanonicaV3({
        ...vector1Params,
        tasa_id: '88888888-8888-8888-8888-888888888888'
      });
      expect(resTasaId.hash).not.toBe(baseHash);
    });

    it('alterar la vigencia_hasta altera el hash', () => {
      const baseHash = '5249e0cea418ec6262f9f0ef7a71686d2d6cecf8c4083dafe77aa0d24c3eacee';

      const resVig = calcularHuellaCanonicaV3({
        ...vector1Params,
        vigente_hasta: '2026-11-07T15:00:00Z'
      });
      expect(resVig.hash).not.toBe(baseHash);
    });

    it('ordena las líneas por variante_id asc de forma canónica garantizando invariancia de orden de entrada', () => {
      const l1 = { cantidad: 1, precio_unitario_bob: '50.00', variante_id: 'aaaa-1111' };
      const l2 = { cantidad: 2, precio_unitario_bob: '25.00', variante_id: 'zzzz-9999' };

      const paramsOrden1: HuellaCanonicaParams = {
        ...vector1Params,
        lineas: [l1, l2]
      };
      const paramsOrden2: HuellaCanonicaParams = {
        ...vector1Params,
        lineas: [l2, l1]
      };

      const res1 = calcularHuellaCanonicaV3(paramsOrden1);
      const res2 = calcularHuellaCanonicaV3(paramsOrden2);

      expect(res1.hash).toBe(res2.hash);
      expect(res1.json).toBe(res2.json);
    });
  });
});
