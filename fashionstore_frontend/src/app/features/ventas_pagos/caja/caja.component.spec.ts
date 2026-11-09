import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { CajaComponent } from './caja.component';
import { CajaService, TurnoHabilitacion, VentaOfflineResultado, ComprobanteCajaOffline } from '../services/caja.service';
import { VentaPresencialService } from '../services/venta-presencial.service';
import { StripeService } from '../services/stripe.service';
import { OrdenActivaCajaDTO } from '../models/venta-presencial.models';
import { ReservaTrasladoService } from '../../reservas_traslados/services/reserva-traslado.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { ProductoService } from '../../catalogo/services/producto.service';

// Doble de persistencia para pruebas de interfaz; IDB real se prueba en tests_aislados_caja.
async function persistirSimulado(t: any, v: any) {
  const turno = structuredClone(t), venta = { ...v, secuencia_local: (turno.ultima_secuencia_local || 0) + 1 };
  for (const l of venta.lineas) turno.cupos.find((c: any) => c.variante_id === l.variante_id).consumido += l.cantidad;
  turno.ultima_secuencia_local = venta.secuencia_local;
  turno.total_operaciones_locales = (turno.total_operaciones_locales || 0) + 1;
  return { turno, venta };
}

describe('CajaComponent (Persistencia Transaccional, Conciliación y Reintentos)', () => {
  let component: CajaComponent;
  let fixture: ComponentFixture<CajaComponent>;

  let cajaServiceSpy: jasmine.SpyObj<CajaService>;
  let ventaPresencialSpy: jasmine.SpyObj<VentaPresencialService>;
  let stripeServiceSpy: jasmine.SpyObj<StripeService>;
  let reservaServiceSpy: jasmine.SpyObj<ReservaTrasladoService>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let productoServiceSpy: jasmine.SpyObj<ProductoService>;

  const mockUUID = '12345678-1234-4234-8234-123456789abc';

  const mockTurno: TurnoHabilitacion = {
    turno_id: 'turno-111',
    habilitacion_id: 'hab-111',
    caja_codigo: 'CAJA-01',
    dispositivo_id: mockUUID,
    sucursal_id: 'suc-111',
    cajero_id: 'caj-111',
    estado: 'ABIERTO',
    inicio_en: '2026-11-04T08:00:00-04:00',
    vence_en: '2026-11-04T16:00:00-04:00',
    version_precios: 'v1.0',
    revision: 1,
    ultima_secuencia_local: 0,
    total_operaciones_locales: 0,
    cupos: [
      {
        variante_id: 'var-1',
        sku: 'SKU-01',
        producto_nombre: 'Blusa Urbana',
        otorgado: 5,
        consumido: 0,
        liberado: 0,
        precio_autorizado_bob: 100
      }
    ]
  };

  beforeEach(async () => {
    cajaServiceSpy = jasmine.createSpyObj<CajaService>('CajaService', [
      'obtenerDispositivoId',
      'obtenerTurnoLocal',
      'guardarTurnoLocal',
      'limpiarTurnoLocal',
      'consultarTurnoActivo',
      'consultarTurno',
      'habilitarTurno',
      'registrarVentaOfflineTransaccional',
      'registrarVentaOffline',
      'obtenerVentasOfflinePendientes',
      'eliminarVentaOfflinePendiente',
      'removerVentaOfflinePendiente',
      'cerrarTurno',
      'recuperarTurno', 'sincronizarPendientes', 'diagnosticosRecuperacion', 'recuperarPendientesSupervisados'
    ]);

    ventaPresencialSpy = jasmine.createSpyObj<VentaPresencialService>('VentaPresencialService', [
      'registrarVenta',
      'liquidarVentaPresencial',
      'comprobante',
      'iniciarVentaPresencialStripe'
    ]);

    reservaServiceSpy = jasmine.createSpyObj<ReservaTrasladoService>('ReservaTrasladoService', [
      'reservaPorCodigo'
    ]);

    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', [
      'obtenerUsuarioActual',
      'estaAutenticado'
    ]);

    productoServiceSpy = jasmine.createSpyObj<ProductoService>('ProductoService', [
      'gestionarVariantes'
    ]);

    stripeServiceSpy = jasmine.createSpyObj<StripeService>('StripeService', [
      'continuarAccion',
      'consultarOrdenPago',
      'confirmarOrdenPago',
      'cancelarOrdenPago',
      'reanudarOrdenPago',
      'cargarStripeJs',
      'obtenerOrdenActivaCaja'
    ]);
    stripeServiceSpy.obtenerOrdenActivaCaja.and.returnValue(of(null));
    stripeServiceSpy.reanudarOrdenPago.and.returnValue(of({
      orden_pago_id: 'ord-pago-test-1',
      estado: 'PENDIENTE',
      client_secret: 'sec_test_reanudado',
      referencia_externa: 'pi_test_reanudado'
    } as any));
    stripeServiceSpy.continuarAccion.and.returnValue(of({
      orden_pago_id: 'ord-pago-test-1',
      estado: 'CAPTURADO'
    } as any));
    stripeServiceSpy.consultarOrdenPago.and.returnValue(of({
      orden_pago_id: 'ord-pago-test-1',
      estado: 'CAPTURADO'
    } as any));
    stripeServiceSpy.confirmarOrdenPago.and.returnValue(of({
      orden_pago_id: 'ord-pago-test-1',
      estado: 'CAPTURADO'
    } as any));
    stripeServiceSpy.cancelarOrdenPago.and.returnValue(of({
      orden_pago_id: 'ord-pago-test-1',
      estado: 'CANCELADO'
    } as any));
    stripeServiceSpy.cargarStripeJs.and.rejectWith(new Error('Test env - no DOM Stripe.js'));

    cajaServiceSpy.obtenerDispositivoId.and.returnValue(mockUUID);
    cajaServiceSpy.obtenerTurnoLocal.and.resolveTo(mockTurno);
    cajaServiceSpy.guardarTurnoLocal.and.resolveTo();
    cajaServiceSpy.limpiarTurnoLocal.and.resolveTo();
    cajaServiceSpy.consultarTurnoActivo.and.returnValue(of(mockTurno));
    cajaServiceSpy.consultarTurno.and.returnValue(of(mockTurno));
    cajaServiceSpy.obtenerVentasOfflinePendientes.and.resolveTo([]);
    cajaServiceSpy.sincronizarPendientes.and.resolveTo({completadas: 0, pendientes: 0});
    cajaServiceSpy.diagnosticosRecuperacion.and.resolveTo([]);
    cajaServiceSpy.eliminarVentaOfflinePendiente.and.resolveTo();
    cajaServiceSpy.removerVentaOfflinePendiente.and.resolveTo();
    productoServiceSpy.gestionarVariantes.and.returnValue(of([]));
    ventaPresencialSpy.liquidarVentaPresencial.and.returnValue(of({
      venta_id: 'vnt-mock-1',
      numero: 'VTA-001',
      total_bob: 150,
      comprobante_id: 'cmp-mock-1',
      kardex_ids: ['k-1'],
      medio_pago: 'EFECTIVO',
      cambio_entregado_bob: 50
    }));
    ventaPresencialSpy.comprobante.and.returnValue(of({
      id: 'cmp-mock-1',
      venta_id: 'vnt-mock-1',
      numero: 'CMP-001',
      fecha_emision: '2026-11-04T12:00:00-04:00',
      cliente_nombre: 'Cliente General',
      cliente_nit_ci: '0',
      total: 150,
      lineas: []
    } as any));

    await TestBed.configureTestingModule({
      imports: [CajaComponent],
      providers: [
        { provide: CajaService, useValue: cajaServiceSpy },
        { provide: VentaPresencialService, useValue: ventaPresencialSpy },
        { provide: ReservaTrasladoService, useValue: reservaServiceSpy },
        { provide: AuthService, useValue: authServiceSpy },
        { provide: ProductoService, useValue: productoServiceSpy },
        { provide: StripeService, useValue: stripeServiceSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(CajaComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('debe inicializarse con dispositivo_id en formato UUID v4 y turno activo desde almacenamiento canónico', fakeAsync(() => {
    tick();
    expect(component.dispositivoId).toBe(mockUUID);
    expect(component.turnoActivo).toEqual(mockTurno);
  }));

  describe('Persistencia Transaccional y Regla de Atomicidad', () => {
    beforeEach(() => {
      component.turnoActivo = JSON.parse(JSON.stringify(mockTurno));
      component.lineasVentaOffline = [
        { variante_id: 'var-1', cantidad: 2, precio_bob: 100 }
      ];
      component.efectivoRecibido = 200;
      component.cambioEntregado = 0;
    });

    it('cuando la persistencia en almacenamiento transaccional es exitosa, descuenta cupo, incrementa contadores y muestra comprobante', fakeAsync(() => {
      cajaServiceSpy.registrarVentaOfflineTransaccional.and.callFake(persistirSimulado);
      const mockResultadoVenta: VentaOfflineResultado = {
        resultado: 'REGISTRADA_CENTRAL',
        operacion_id: 'op-123',
        venta_id: 'vnt-123',
        numero: 'VNT-123',
        total_bob: 200,
        comprobante_id: 'cmp-123',
        recibida_central_en: '2026-11-04T10:00:00-04:00',
        cupos_restantes: []
      };
      cajaServiceSpy.registrarVentaOffline.and.returnValue(of(mockResultadoVenta));

      component.cobrarVentaContado();
      tick();

      expect(cajaServiceSpy.registrarVentaOfflineTransaccional).toHaveBeenCalled();
      const args = cajaServiceSpy.registrarVentaOfflineTransaccional.calls.mostRecent().args;
      const turnoGuardado = component.turnoActivo!;
      const ventaGuardada = args[1];

      expect(turnoGuardado.cupos[0].consumido).toBe(2);
      expect(turnoGuardado.ultima_secuencia_local).toBe(1);
      expect(turnoGuardado.total_operaciones_locales).toBe(1);
      expect(ventaGuardada.secuencia_local).toBe(1);

      expect(component.comprobanteOffline).toBeDefined();
      expect(component.comprobanteOffline?.total).toBe(200);
      expect(component.lineasVentaOffline.length).toBe(0);
      expect(component.error).toBe('');
    }));

    it('si falla la persistencia en almacenamiento transaccional, NUNCA emite comprobante, preserva pedido y REUTILIZA el mismo operacion_id al reintentar', fakeAsync(() => {
      cajaServiceSpy.registrarVentaOfflineTransaccional.and.rejectWith(new Error('Fallo transaccional'));

      // 1. Primer intento (falla almacenamiento)
      component.cobrarVentaContado();
      tick();

      expect(component.comprobanteOffline).toBeUndefined();
      expect(component.error).toContain('Fallo transaccional');
      expect(component.lineasVentaOffline.length).toBe(1);
      expect(component.turnoActivo?.cupos[0].consumido).toBe(0);
      expect(component.procesando).toBeFalse();

      // Capturar operacion_id del primer intento
      const primerIntentoArgs = cajaServiceSpy.registrarVentaOfflineTransaccional.calls.mostRecent().args;
      const operacionIdPrimerIntento = primerIntentoArgs[1].operacion_id;
      expect(operacionIdPrimerIntento).toBeTruthy();

      // 2. Segundo intento (reintento tras resolver almacenamiento)
      cajaServiceSpy.registrarVentaOfflineTransaccional.and.callFake(persistirSimulado);
      cajaServiceSpy.registrarVentaOffline.and.returnValue(of({
        resultado: 'REGISTRADA_CENTRAL',
        operacion_id: operacionIdPrimerIntento,
        venta_id: 'vnt-abc',
        numero: 'VNT-ABC',
        total_bob: 200,
        comprobante_id: 'cmp-abc',
        recibida_central_en: '2026-11-04T10:05:00-04:00',
        cupos_restantes: []
      }));

      component.cobrarVentaContado();
      tick();

      const segundoIntentoArgs = cajaServiceSpy.registrarVentaOfflineTransaccional.calls.mostRecent().args;
      const operacionIdSegundoIntento = segundoIntentoArgs[1].operacion_id;

      // COMPROBACIÓN CRÍTICA DE NO DOBLE COBRO: El reintento DEBE mantener el MISMO operacion_id
      expect(operacionIdSegundoIntento).toBe(operacionIdPrimerIntento);
      expect(component.comprobanteOffline).toBeDefined();
      expect(component.lineasVentaOffline.length).toBe(0);
    }));

    it('ausencia de doble cobro: si falla la sincronización con el servidor, la venta se mantiene offline con el operacion_id canónico', fakeAsync(() => {
      cajaServiceSpy.registrarVentaOfflineTransaccional.and.callFake(persistirSimulado);
      cajaServiceSpy.registrarVentaOffline.and.returnValue(throwError(() => new Error('Network error')));

      component.cobrarVentaContado();
      tick();

      expect(component.comprobanteOffline).toBeDefined();
      expect(component.comprobanteOffline?.esOffline).toBeTrue();
      expect(component.lineasVentaOffline.length).toBe(0);
      expect(cajaServiceSpy.eliminarVentaOfflinePendiente).not.toHaveBeenCalled();
    }));
  });

  describe('Conciliación de Cierre coordinada con Backend', () => {
    it('cerrarTurno() debe enviar revision, ultima_secuencia_local, total_operaciones_locales, operaciones_pendientes y arqueo_efectivo_bob', fakeAsync(() => {
      component.turnoActivo = {
        ...mockTurno,
        revision: 2,
        ultima_secuencia_local: 5,
        total_operaciones_locales: 5
      };

      cajaServiceSpy.obtenerVentasOfflinePendientes.and.resolveTo([
        {
          operacion_id: 'op-pendiente-1',
          secuencia_local: 4,
          vendida_local_en: '2026-11-04T10:00:00Z',
          entregada_local_en: '2026-11-04T10:00:00Z',
          version_precios: 'v1.0',
          lineas: [],
          total_bob: 100,
          efectivo_recibido_bob: 100,
          cambio_entregado_bob: 0
        }
      ]);

      cajaServiceSpy.cerrarTurno.and.returnValue(of({
        turno_id: mockTurno.turno_id,
        estado: 'CONCILIACION',
        cerrado_en: null,
        revision: 3,
        cupos_devueltos: []
      }));
      cajaServiceSpy.consultarTurno.and.returnValue(of({
        ...mockTurno,
        estado: 'CONCILIACION',
        revision: 3
      }));

      // Ejecutar cierre con arqueo ingresado
      component.cerrarTurno(500);
      tick();

      expect(cajaServiceSpy.cerrarTurno).toHaveBeenCalledWith(
        mockTurno.turno_id,
        {
          revision: 2,
          ultima_secuencia_local: 5,
          total_operaciones_locales: 5,
          operaciones_pendientes: ['op-pendiente-1'],
          arqueo_efectivo_bob: 500
        }
      );

      expect(component.turnoActivo?.estado).toBe('CONCILIACION');
      expect(component.error).toContain('1 operacion(es) pendiente(s)');
    }));

    it('modal de cierre interactivo: confirmarCierreTurno() transmite el arqueo ingresado', fakeAsync(() => {
      component.turnoActivo = {
        ...mockTurno,
        revision: 1,
        ultima_secuencia_local: 2,
        total_operaciones_locales: 2
      };

      cajaServiceSpy.obtenerVentasOfflinePendientes.and.resolveTo([]);
      cajaServiceSpy.cerrarTurno.and.returnValue(of({
        turno_id: mockTurno.turno_id,
        estado: 'CERRADO',
        cerrado_en: '2026-11-04T16:00:00Z',
        revision: 2,
        cupos_devueltos: []
      }));

      component.abrirModalCierre();
      expect(component.mostrarDialogoCierre).toBeTrue();

      component.arqueoEfectivoBob = 340.50;
      component.confirmarCierreTurno();
      tick();

      expect(component.mostrarDialogoCierre).toBeFalse();
      expect(cajaServiceSpy.cerrarTurno).toHaveBeenCalledWith(
        mockTurno.turno_id,
        jasmine.objectContaining({
          revision: 1,
          ultima_secuencia_local: 2,
          total_operaciones_locales: 2,
          operaciones_pendientes: [],
          arqueo_efectivo_bob: 340.50
        })
      );
      expect(component.mensajeExito).toContain('Turno cerrado');
      expect(component.turnoActivo).toBeNull();
    }));
  });

  describe('Resolución física supervisada', () => {
    it('no permite enviar un cierre supervisado sin acta, arqueo y conteo completo', fakeAsync(() => {
      authServiceSpy.obtenerUsuarioActual.and.returnValue({ rol: 'ADMINISTRADOR' } as any);
      component.turnoActivo = { ...mockTurno, estado: 'CONCILIACION' };
      component.abrirModalCierre(true);

      component.confirmarCierreTurno();
      tick();

      expect(component.mostrarDialogoCierre).toBeTrue();
      expect(component.error).toContain('Completa el acta');
      expect(cajaServiceSpy.cerrarTurno).not.toHaveBeenCalled();
    }));

    it('envía conteo por variante y retiene faltante que espera sincronización tardía', fakeAsync(() => {
      authServiceSpy.obtenerUsuarioActual.and.returnValue({ rol: 'ENCARGADO' } as any);
      const turnoConciliacion: TurnoHabilitacion = {
        ...mockTurno,
        estado: 'CONCILIACION',
        revision: 3,
        cupos: [{ ...mockTurno.cupos[0], consumido: 1, liberado: 0 }]
      };
      component.turnoActivo = turnoConciliacion;
      cajaServiceSpy.consultarTurno.and.returnValue(of(turnoConciliacion));
      cajaServiceSpy.obtenerVentasOfflinePendientes.and.resolveTo([]);
      cajaServiceSpy.cerrarTurno.and.returnValue(of({
        turno_id: mockTurno.turno_id,
        estado: 'CONCILIACION',
        cerrado_en: '2026-11-04T16:00:00Z',
        revision: 4,
        cupos_devueltos: [{ variante_id: 'var-1', otorgado: 5, consumido: 1, devuelto: 2 }],
        cupos_retenidos: [{ variante_id: 'var-1', otorgado: 5, consumido: 1, retenido: 2 }]
      }));

      component.abrirModalCierre(true);
      component.referenciaActa = 'ACTA-CAJA-2026-014';
      component.motivoSupervision = 'Conteo fisico al recuperar el dispositivo';
      component.arqueoEfectivoBob = 120;
      component.conteoFisicoPorVariante['var-1'] = 2;
      component.resolucionFaltantePorVariante['var-1'] = 'PENDIENTE_SINCRONIZACION';
      component.motivoFaltantePorVariante['var-1'] = 'Venta cobrada pendiente de recuperar';
      component.confirmarCierreTurno();
      tick();

      expect(cajaServiceSpy.cerrarTurno).toHaveBeenCalledWith(mockTurno.turno_id, jasmine.objectContaining({
        supervision_forzada: true,
        descarte_venta_fisica: false,
        arqueo_declarado_bob: 120,
        evidencia_cierre: {
          referencia_acta: 'ACTA-CAJA-2026-014',
          conteo_fisico_por_variante: [{ variante_id: 'var-1', cantidad_encontrada: 2 }]
        },
        ajustes_inventario: {
          resoluciones_por_variante: [{
            variante_id: 'var-1',
            resolucion: 'PENDIENTE_SINCRONIZACION',
            motivo: 'Venta cobrada pendiente de recuperar'
          }]
        }
      }));
      expect(component.turnoActivo?.estado).toBe('CONCILIACION');
      expect(component.error).toContain('2 prenda(s) retenida(s)');
    }));

    it('permite liberar cantidades confirmadas y registrar una merma con motivo', fakeAsync(() => {
      authServiceSpy.obtenerUsuarioActual.and.returnValue({ rol: 'ADMINISTRADOR' } as any);
      component.turnoActivo = { ...mockTurno, estado: 'CONCILIACION', revision: 2 };
      cajaServiceSpy.obtenerVentasOfflinePendientes.and.resolveTo([]);
      cajaServiceSpy.cerrarTurno.and.returnValue(of({
        turno_id: mockTurno.turno_id,
        estado: 'CERRADO',
        cerrado_en: '2026-11-04T16:00:00Z',
        revision: 3,
        cupos_devueltos: [{ variante_id: 'var-1', otorgado: 5, consumido: 0, devuelto: 3 }],
        cupos_retenidos: []
      }));

      component.abrirModalCierre(true);
      component.referenciaActa = 'ACTA-CAJA-2026-015';
      component.motivoSupervision = 'Cierre con conteo fisico documentado';
      component.arqueoEfectivoBob = 0;
      component.conteoFisicoPorVariante['var-1'] = 3;
      component.resolucionFaltantePorVariante['var-1'] = 'MERMA';
      component.motivoFaltantePorVariante['var-1'] = 'Dano confirmado durante la inspeccion';
      component.confirmarCierreTurno();
      tick();

      expect(cajaServiceSpy.cerrarTurno.calls.mostRecent().args[1].ajustes_inventario?.resoluciones_por_variante)
        .toEqual([{
          variante_id: 'var-1',
          resolucion: 'MERMA',
          motivo: 'Dano confirmado durante la inspeccion'
        }]);
      expect(component.turnoActivo).toBeNull();
      expect(component.mensajeExito).toContain('Turno cerrado');
    }));
  });

  describe('Sincronización Idempotente con mismo operacion_id', () => {
    it('delega sincronizacion por origen y conserva resultados en vez de eliminar ventas', fakeAsync(() => {
      cajaServiceSpy.sincronizarPendientes.and.resolveTo({ completadas: 1, pendientes: 0 });
      component.sincronizarVentasPendientes(); tick();
      expect(cajaServiceSpy.sincronizarPendientes).toHaveBeenCalled();
      expect(cajaServiceSpy.eliminarVentaOfflinePendiente).not.toHaveBeenCalled();
    }));
  });

  describe('Accesibilidad y Traducción de Estados', () => {
    it('etiquetaEstadoTurno traduce estados técnicos a español legible', () => {
      expect(component.etiquetaEstadoTurno('ABIERTO')).toBe('Abierto');
      expect(component.etiquetaEstadoTurno('CERRADO')).toBe('Cerrado');
      expect(component.etiquetaEstadoTurno('CONCILIACION')).toBe('Conciliación requerida');
      expect(component.etiquetaEstadoTurno('RECUPERACION')).toBe('En recuperación');
    });
  });

  describe('Persistencia Garantizada de Apertura de Turno', () => {
    beforeEach(() => {
      authServiceSpy.obtenerUsuarioActual.and.returnValue({
        id: 'usr-1',
        email: 'cajero@fashionstore.test',
        nombre: 'Cajero Prueba',
        rol: 'VENDEDOR',
        activo: true,
        sucursal_id: 'suc-111'
      } as any);
      component.cajaId = 'CAJA-01';
      component.cuposSolicitados = [{ variante_id: 'var-1', cantidad: 5 }];
    });

    it('en abrirTurno, si la persistencia en IndexedDB falla: turnoActivo queda null, muestra error, conserva turnoPendienteRecuperacion y bloquea cobros offline', fakeAsync(() => {
      cajaServiceSpy.habilitarTurno.and.returnValue(of(mockTurno));
      cajaServiceSpy.guardarTurnoLocal.and.rejectWith(new Error('IndexedDB no disponible para persistir el turno de caja'));

      component.abrirTurno();
      tick();

      // Comprobaciones críticas
      expect(component.turnoActivo).toBeNull();
      expect(component.turnoPendienteRecuperacion as any).toEqual(mockTurno);
      expect(component.error).toContain('Fallo transaccional');
      expect(component.mensajeExito).toBe('');

      // Comprobación de que no se permiten cobros offline en este estado
      component.lineasVentaOffline = [{ variante_id: 'var-1', cantidad: 1, precio_bob: 100 }];
      component.efectivoRecibido = 100;
      component.cobrarVentaContado();
      tick();

      expect(cajaServiceSpy.registrarVentaOfflineTransaccional).not.toHaveBeenCalled();
      expect(component.error).toBe('No hay un turno de caja activo para procesar ventas.');
    }));

    it('reintento exitoso de persistencia activa el turno correctamente y limpia la referencia pendiente', fakeAsync(() => {
      // Estado inicial con turno pendiente tras fallo previo
      component.turnoActivo = null;
      component.turnoPendienteRecuperacion = { ...mockTurno };
      component.error = 'Error de almacenamiento previo';

      cajaServiceSpy.guardarTurnoLocal.and.resolveTo();

      component.reintentarPersistenciaTurno();
      tick();

      expect(cajaServiceSpy.guardarTurnoLocal).toHaveBeenCalledWith(jasmine.objectContaining({ turno_id: mockTurno.turno_id }));
      expect(component.turnoActivo as any).toEqual(mockTurno);
      expect(component.turnoPendienteRecuperacion).toBeNull();
      expect(component.mensajeExito).toContain('habilitada exitosamente');
      expect(component.error).toBe('');
    }));

    it('cancelarTurnoPendiente() descarta la referencia transitoria y permite volver a la vista inicial', () => {
      component.turnoPendienteRecuperacion = { ...mockTurno };
      component.error = 'Error previo';

      component.cancelarTurnoPendiente();

      expect(component.turnoPendienteRecuperacion).toBeNull();
      expect(component.error).toBe('');
    });

    it('simulación de recarga/reinicio con turno persistido permite cobrar ventas normalmente', fakeAsync(() => {
      cajaServiceSpy.obtenerTurnoLocal.and.resolveTo(mockTurno);
      cajaServiceSpy.registrarVentaOfflineTransaccional.and.callFake(persistirSimulado);
      cajaServiceSpy.registrarVentaOffline.and.returnValue(of({
        resultado: 'REGISTRADA_CENTRAL',
        operacion_id: 'op-rein-1',
        venta_id: 'vnt-rein-1',
        numero: 'VNT-REIN-001',
        total_bob: 100,
        comprobante_id: 'cmp-rein-1',
        recibida_central_en: '2026-11-04T12:00:00-04:00',
        cupos_restantes: []
      }));

      // Ejecutar carga simulada de inicio
      component.cargarTurnoActivo();
      tick();

      expect(component.turnoActivo).toEqual(mockTurno);
      expect(component.turnoPendienteRecuperacion).toBeNull();

      // Proceder a realizar una venta con el turno restaurado
      component.lineasVentaOffline = [{ variante_id: 'var-1', cantidad: 1, precio_bob: 100 }];
      component.efectivoRecibido = 100;
      component.cambioEntregado = 0;

      component.cobrarVentaContado();
      tick();

      expect(cajaServiceSpy.registrarVentaOfflineTransaccional).toHaveBeenCalled();
      expect(component.comprobanteOffline).toBeDefined();
      expect(component.comprobanteOffline?.total).toBe(100);
    }));

    it('cargarTurnoActivo: si la consulta remota obtiene un turno pero falla la persistencia en IndexedDB, no lo activa en memoria', fakeAsync(() => {
      // 1. Localmente no había turno previo
      cajaServiceSpy.obtenerTurnoLocal.and.resolveTo(null);
      // 2. Servidor tiene un turno
      cajaServiceSpy.consultarTurnoActivo.and.returnValue(of(mockTurno));
      // 3. Fallo de persistencia local
      cajaServiceSpy.guardarTurnoLocal.and.rejectWith(new Error('IndexedDB bloqueado'));

      component.turnoActivo = null;
      component.cargarTurnoActivo();
      tick();

      expect(component.turnoActivo).toBeNull();
      expect(component.turnoPendienteRecuperacion as any).toEqual(mockTurno);
      expect(component.error).toContain('el turno existe en el servidor pero no pudo persistirse');
    }));
  });

  describe('Venta Presencial Directa en Caja (CU19)', () => {
    beforeEach(() => {
      authServiceSpy.obtenerUsuarioActual.and.returnValue({
        id: 'usr-cajero-1',
        usuario_id: 'usr-cajero-1',
        nombre_completo: 'Cajero Test',
        rol: 'CAJERO',
        activo: true,
        sucursal_id: 'suc-111'
      } as any);
      component.items = [
        { variante_id: 'var-1', cantidad: 2 }
      ];
      component.reserva = undefined;
    });

    it('liquida en EFECTIVO respetando el cálculo del servidor y el cambio entregado', fakeAsync(() => {
      component.metodo = 'EFECTIVO';
      component.efectivoRecibidoPresencial = 200;

      ventaPresencialSpy.liquidarVentaPresencial.and.returnValue(of({
        venta_id: 'vnt-directa-1',
        numero: 'VTA-DIR-001',
        total_bob: 160,
        comprobante_id: 'cmp-dir-1',
        kardex_ids: ['k-1'],
        medio_pago: 'EFECTIVO',
        cambio_entregado_bob: 40
      }));

      component.vender();
      tick();

      expect(ventaPresencialSpy.liquidarVentaPresencial).toHaveBeenCalledWith(
        jasmine.objectContaining({
          sucursal_id: 'suc-111',
          medio_pago: 'EFECTIVO',
          efectivo_recibido_bob: 200,
          lineas: [{ variante_id: 'var-1', cantidad: 2 }]
        })
      );
      expect(component.ventaLiquidada?.total_bob).toBe(160);
      expect(component.comprobante?.total).toBe(160);
      expect(component.items.length).toBe(0);
    }));

    it('liquida con SALDO validando identificación del cliente', fakeAsync(() => {
      component.metodo = 'SALDO';
      component.clienteIdPresencial = '';
      component.vender();
      expect(component.error).toContain('requiere indicar el identificador del cliente');
      expect(ventaPresencialSpy.liquidarVentaPresencial).not.toHaveBeenCalled();

      // Al proveer cliente_id y saldo aplicado
      component.clienteIdPresencial = 'cli-wallet-1';
      component.saldoAplicadoPresencial = 160;

      ventaPresencialSpy.liquidarVentaPresencial.and.returnValue(of({
        venta_id: 'vnt-saldo-1',
        numero: 'VTA-SAL-001',
        total_bob: 160,
        comprobante_id: 'cmp-sal-1',
        kardex_ids: ['k-1'],
        medio_pago: 'SALDO'
      }));

      component.vender();
      tick();

      expect(ventaPresencialSpy.liquidarVentaPresencial).toHaveBeenCalledWith(
        jasmine.objectContaining({
          medio_pago: 'SALDO',
          cliente_id: 'cli-wallet-1',
          saldo_aplicado_bob: 160
        })
      );
      expect(component.ventaLiquidada?.medio_pago).toBe('SALDO');
    }));

    it('liquida con STRIPE_TEST requiriendo orden de pago previa en estado CAPTURADO', fakeAsync(() => {
      component.metodo = 'STRIPE_TEST';
      component.ordenStripePresencial = null;
      component.vender();
      expect(component.error).toContain('iniciar el cobro con tarjeta Stripe');

      component.ordenStripePresencial = {
        venta_id: 'vnt-stripe-1',
        orden_pago_id: 'ord-stripe-1',
        stripe_payment_intent_id: 'pi_test_12345',
        client_secret: 'sec_test',
        monto_bob: '180.00',
        monto_usd: '25.86',
        centavos_usd: 2586,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'CAPTURADO'
      };

      ventaPresencialSpy.liquidarVentaPresencial.and.returnValue(of({
        venta_id: 'vnt-stripe-1',
        numero: 'VTA-STR-001',
        total_bob: 180,
        comprobante_id: 'cmp-str-1',
        kardex_ids: ['k-1'],
        medio_pago: 'STRIPE_TEST'
      }));

      component.vender();
      tick();

      expect(ventaPresencialSpy.liquidarVentaPresencial).toHaveBeenCalledWith(
        jasmine.objectContaining({
          medio_pago: 'STRIPE_TEST',
          stripe_payment_intent_id: 'pi_test_12345'
        })
      );
      expect(component.ventaLiquidada?.medio_pago).toBe('STRIPE_TEST');
    }));

    it('inicia venta Stripe, monta tarjeta segura, invoca confirmCardPayment con client_secret, confirma centralmente CAPTURADO y liquida la misma venta (CU19)', fakeAsync(() => {
      component.vistaModo = 'RESERVA';
      component.reserva = undefined;
      component.metodo = 'STRIPE_TEST';
      component.items = [{ variante_id: 'var-1', cantidad: 2 }];

      const fakeCardElement = {
        mount: jasmine.createSpy('mount'),
        destroy: jasmine.createSpy('destroy'),
        on: jasmine.createSpy('on')
      };
      const fakeStripe = {
        elements: jasmine.createSpy('elements').and.returnValue({
          create: jasmine.createSpy('create').and.returnValue(fakeCardElement)
        }),
        confirmCardPayment: jasmine.createSpy('confirmCardPayment').and.resolveTo({
          paymentIntent: { id: 'pi_caja_init_999', status: 'succeeded' }
        })
      };
      component.stripeInstance = fakeStripe;

      ventaPresencialSpy.iniciarVentaPresencialStripe.and.returnValue(of({
        venta_id: 'vnt-stripe-init-1',
        orden_pago_id: 'ord-pago-init-1',
        stripe_payment_intent_id: 'pi_caja_init_999',
        client_secret: 'pi_caja_secret_999',
        monto_bob: '200.00',
        monto_usd: '28.74',
        centavos_usd: 2874,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      }));

      // 1. Iniciar ciclo Stripe en venta presencial directa
      component.iniciarStripePresencial();
      tick();
      fixture.detectChanges();

      expect(ventaPresencialSpy.iniciarVentaPresencialStripe).toHaveBeenCalled();
      expect(component.ordenStripePresencial).toBeTruthy();
      expect(component.ordenStripePresencial?.estado_orden).toBe('PENDIENTE');
      expect(component.ordenStripePresencial?.stripe_payment_intent_id).toBe('pi_caja_init_999');

      // 2. Contenedor de tarjeta montado en DOM
      const cardContainer = fixture.nativeElement.querySelector('#stripe-card-element-presencial');
      expect(cardContainer).not.toBeNull();

      // 3. Intentar liquidar antes de capturar debe ser rechazado
      component.vender();
      expect(component.error).toContain('CAPTURADO');

      // 4. Completar tarjeta válida e invocar confirmación SDK
      component.cardElementPresencial = fakeCardElement;
      component.cardElementPresencialValido = true;
      fixture.detectChanges();

      stripeServiceSpy.confirmarOrdenPago.and.returnValue(of({
        orden_pago_id: 'ord-pago-init-1',
        estado: 'CAPTURADO'
      } as any));

      component.capturarStripePresencial();
      tick();
      fixture.detectChanges();

      // Verifica llamada al SDK cliente con el client_secret real de la orden
      expect(fakeStripe.confirmCardPayment).toHaveBeenCalledWith('pi_caja_secret_999', {
        payment_method: { card: fakeCardElement }
      });
      // Verifica sincronización y confirmación con el backend central
      expect(stripeServiceSpy.confirmarOrdenPago).toHaveBeenCalledWith('ord-pago-init-1');
      expect(component.ordenStripePresencial?.estado_orden).toBe('CAPTURADO');
      expect(fakeCardElement.destroy).toHaveBeenCalled();

      // 5. Liquidar la misma venta con el pago capturado
      ventaPresencialSpy.liquidarVentaPresencial.and.returnValue(of({
        venta_id: 'vnt-stripe-init-1',
        numero: 'VTA-STR-002',
        total_bob: 200,
        comprobante_id: 'cmp-str-2',
        kardex_ids: ['k-2'],
        medio_pago: 'STRIPE_TEST'
      }));

      component.vender();
      tick();

      expect(ventaPresencialSpy.liquidarVentaPresencial).toHaveBeenCalledWith(
        jasmine.objectContaining({
          venta_id: 'vnt-stripe-init-1',
          orden_pago_id: 'ord-pago-init-1',
          stripe_payment_intent_id: 'pi_caja_init_999',
          medio_pago: 'STRIPE_TEST'
        })
      );
      expect(component.ventaLiquidada?.venta_id).toBe('vnt-stripe-init-1');
      expect(component.ordenStripePresencial).toBeNull();
    }));

    it('inicia venta Stripe en turno offline de caja, captura mediante SDK y confirmación central, y liquida actualizando cupos de turno (CU19)', fakeAsync(() => {
      component.vistaModo = 'TURNO_OFFLINE';
      component.medioPagoCaja = 'STRIPE_TEST';
      component.lineasVentaOffline = [{ variante_id: 'var-1', cantidad: 1, precio_bob: 100 }];

      const fakeCardElement = {
        mount: jasmine.createSpy('mount'),
        destroy: jasmine.createSpy('destroy'),
        on: jasmine.createSpy('on')
      };
      const fakeStripe = {
        elements: jasmine.createSpy('elements').and.returnValue({
          create: jasmine.createSpy('create').and.returnValue(fakeCardElement)
        }),
        confirmCardPayment: jasmine.createSpy('confirmCardPayment').and.resolveTo({
          paymentIntent: { id: 'pi_turno_stripe_888', status: 'succeeded' }
        })
      };
      component.stripeInstance = fakeStripe;

      ventaPresencialSpy.iniciarVentaPresencialStripe.and.returnValue(of({
        venta_id: 'vnt-turno-stripe-1',
        orden_pago_id: 'ord-turno-stripe-1',
        stripe_payment_intent_id: 'pi_turno_stripe_888',
        client_secret: 'pi_turno_secret_888',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      }));

      component.iniciarStripeCaja();
      tick();
      fixture.detectChanges();

      expect(ventaPresencialSpy.iniciarVentaPresencialStripe).toHaveBeenCalled();
      expect(component.ordenStripeCaja?.estado_orden).toBe('PENDIENTE');

      // Verifica contenedor en DOM
      const cardContainer = fixture.nativeElement.querySelector('#stripe-card-element-caja');
      expect(cardContainer).not.toBeNull();

      component.cardElementCaja = fakeCardElement;
      component.cardElementCajaValido = true;

      stripeServiceSpy.confirmarOrdenPago.and.returnValue(of({
        orden_pago_id: 'ord-turno-stripe-1',
        estado: 'CAPTURADO'
      } as any));

      component.capturarStripeCaja();
      tick();

      expect(fakeStripe.confirmCardPayment).toHaveBeenCalledWith('pi_turno_secret_888', {
        payment_method: { card: fakeCardElement }
      });
      expect(stripeServiceSpy.confirmarOrdenPago).toHaveBeenCalledWith('ord-turno-stripe-1');
      expect(component.ordenStripeCaja?.estado_orden).toBe('CAPTURADO');

      ventaPresencialSpy.liquidarVentaPresencial.and.returnValue(of({
        venta_id: 'vnt-turno-stripe-1',
        numero: 'VTA-TURNO-003',
        total_bob: 100,
        comprobante_id: 'cmp-turno-str-3',
        kardex_ids: ['k-3'],
        medio_pago: 'STRIPE_TEST'
      }));

      const cupoInicial = component.turnoActivo?.cupos[0]?.consumido || 0;
      component.cobrarVentaContado();
      tick();

      expect(ventaPresencialSpy.liquidarVentaPresencial).toHaveBeenCalledWith(
        jasmine.objectContaining({
          venta_id: 'vnt-turno-stripe-1',
          orden_pago_id: 'ord-turno-stripe-1',
          stripe_payment_intent_id: 'pi_turno_stripe_888',
          medio_pago: 'STRIPE_TEST'
        })
      );
      expect(component.comprobanteOffline?.operacion_id).toBe('vnt-turno-stripe-1');
      expect(component.turnoActivo?.cupos[0]?.consumido).toBe(cupoInicial + 1);
      expect(component.ordenStripeCaja).toBeNull();
    }));

    it('capturarStripePresencial falla cerrado si el SDK de Stripe no está disponible', fakeAsync(() => {
      component.stripeInstance = null;
      stripeServiceSpy.cargarStripeJs.and.rejectWith(new Error('Network failure loading Stripe.js'));
      component.cardElementPresencial = {};
      component.cardElementPresencialValido = true;

      component.ordenStripePresencial = {
        venta_id: 'vnt-no-sdk',
        orden_pago_id: 'ord-no-sdk',
        stripe_payment_intent_id: 'pi_no_sdk',
        client_secret: 'sec_no_sdk',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };

      component.capturarStripePresencial();
      tick();

      expect(component.ordenStripePresencial.estado_orden).toBe('PENDIENTE');
      expect(component.error).toContain('pasarela segura de Stripe');
      expect(component.capturandoStripePresencial).toBeFalse();
    }));

    it('capturarStripePresencial no permite confirmar si la tarjeta está incompleta y deshabilita el botón', fakeAsync(() => {
      component.vistaModo = 'RESERVA';
      component.reserva = undefined;
      component.metodo = 'STRIPE_TEST';
      component.ordenStripePresencial = {
        venta_id: 'vnt-inc-1',
        orden_pago_id: 'ord-inc-1',
        stripe_payment_intent_id: 'pi_inc_1',
        client_secret: 'sec_inc_1',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };
      component.cardElementPresencialValido = false;
      component.cardElementPresencial = null;
      fixture.detectChanges();

      const btnCapturar = fixture.nativeElement.querySelector('.btn-capturar-stripe');
      expect(btnCapturar?.disabled).toBeTrue();

      component.capturarStripePresencial();
      tick();

      expect(component.error).toContain('Complete los datos de la tarjeta');
      expect(component.ordenStripePresencial.estado_orden).toBe('PENDIENTE');
    }));

    it('capturarStripePresencial maneja tarjeta rechazada por la pasarela (declined) mostrando error sin liquidar', fakeAsync(() => {
      const fakeStripe = {
        confirmCardPayment: jasmine.createSpy('confirmCardPayment').and.resolveTo({
          error: { message: 'Your card was declined.' }
        })
      };
      component.stripeInstance = fakeStripe;
      component.cardElementPresencial = {};
      component.cardElementPresencialValido = true;
      component.ordenStripePresencial = {
        venta_id: 'vnt-dec-1',
        orden_pago_id: 'ord-dec-1',
        stripe_payment_intent_id: 'pi_dec_1',
        client_secret: 'sec_dec_1',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };

      component.capturarStripePresencial();
      tick();

      expect(fakeStripe.confirmCardPayment).toHaveBeenCalled();
      expect(component.error).toContain('declined');
      expect(component.errorTarjetaPresencial).toContain('declined');
      expect(component.ordenStripePresencial.estado_orden).toBe('PENDIENTE');
      expect(ventaPresencialSpy.liquidarVentaPresencial).not.toHaveBeenCalled();
    }));

    it('capturarStripePresencial gestiona requires_action transicionando a REQUIERE_ACCION_CLIENTE', fakeAsync(() => {
      const fakeStripe = {
        confirmCardPayment: jasmine.createSpy('confirmCardPayment').and.resolveTo({
          paymentIntent: { id: 'pi_3ds_req', status: 'requires_action' }
        })
      };
      component.stripeInstance = fakeStripe;
      component.cardElementPresencial = {};
      component.cardElementPresencialValido = true;
      component.ordenStripePresencial = {
        venta_id: 'vnt-3ds-1',
        orden_pago_id: 'ord-3ds-1',
        stripe_payment_intent_id: 'pi_3ds_req',
        client_secret: 'sec_3ds_req',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };

      component.capturarStripePresencial();
      tick();

      expect(component.ordenStripePresencial.estado_orden).toBe('REQUIERE_ACCION_CLIENTE');
      expect(component.error).toContain('3D Secure');

      // Posteriormente continuar acción con backend
      stripeServiceSpy.continuarAccion.and.returnValue(of({
        orden_pago_id: 'ord-3ds-1',
        estado: 'CAPTURADO'
      } as any));

      component.cardElementPresencial = null;
      component.capturarStripePresencial();
      tick();

      expect(stripeServiceSpy.continuarAccion).toHaveBeenCalledWith('ord-3ds-1', {
        payment_intent_id: 'pi_3ds_req'
      });
      expect(component.ordenStripePresencial.estado_orden).toBe('CAPTURADO');
    }));

    it('capturarStripePresencial conserva la orden visible y permite reintento si falla la confirmación central', fakeAsync(() => {
      const fakeStripe = {
        confirmCardPayment: jasmine.createSpy('confirmCardPayment').and.resolveTo({
          paymentIntent: { id: 'pi_net_1', status: 'succeeded' }
        })
      };
      component.stripeInstance = fakeStripe;
      component.cardElementPresencial = {};
      component.cardElementPresencialValido = true;
      component.ordenStripePresencial = {
        venta_id: 'vnt-net-1',
        orden_pago_id: 'ord-net-1',
        stripe_payment_intent_id: 'pi_net_1',
        client_secret: 'sec_net_1',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };

      stripeServiceSpy.confirmarOrdenPago.and.returnValue(throwError(() => ({
        status: 504,
        error: { detail: 'Gateway Timeout' }
      })));

      component.capturarStripePresencial();
      tick();

      // NO se asigna CAPTURADO localmente ni se borra la orden
      expect(component.ordenStripePresencial).not.toBeNull();
      expect(component.ordenStripePresencial.estado_orden).toBe('PENDIENTE');
      expect(component.error).toContain('error al confirmar con el servidor');

      // Reintentar confirmación central cuando se restablece la red
      stripeServiceSpy.confirmarOrdenPago.and.returnValue(of({
        orden_pago_id: 'ord-net-1',
        estado: 'CAPTURADO'
      } as any));

      component.reintentarConfirmacionStripePresencial();
      tick();

      expect(component.ordenStripePresencial.estado_orden).toBe('CAPTURADO');
      expect(component.mensajeExito).toContain('confirmado');
    }));

    it('bloquea doble clic durante la captura de Stripe en caja y presencial', fakeAsync(() => {
      let resolveStripe: any;
      const fakeStripe = {
        confirmCardPayment: jasmine.createSpy('confirmCardPayment').and.returnValue(
          new Promise(resolve => { resolveStripe = resolve; })
        )
      };
      component.stripeInstance = fakeStripe;
      component.cardElementPresencial = {};
      component.cardElementPresencialValido = true;
      component.ordenStripePresencial = {
        venta_id: 'vnt-dbl-1',
        orden_pago_id: 'ord-dbl-1',
        stripe_payment_intent_id: 'pi_dbl_1',
        client_secret: 'sec_dbl_1',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };

      // Primer clic
      component.capturarStripePresencial();
      expect(component.capturandoStripePresencial).toBeTrue();
      tick();

      expect(fakeStripe.confirmCardPayment.calls.count()).toBe(1);

      // Segundo clic mientras procesa
      component.capturarStripePresencial();
      expect(fakeStripe.confirmCardPayment.calls.count()).toBe(1);

      // Limpiar promesa pendiente
      resolveStripe({ error: { message: 'Desestimado' } });
      tick();
    }));

    it('cancelarStripePresencial invoca backend cancelarOrdenPago si está PENDIENTE', () => {
      component.ordenStripePresencial = {
        venta_id: 'vnt-can-1',
        orden_pago_id: 'ord-can-1',
        stripe_payment_intent_id: 'pi_can_1',
        client_secret: 'sec_can_1',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };

      component.cancelarStripePresencial();
      expect(stripeServiceSpy.cancelarOrdenPago).toHaveBeenCalledWith('ord-can-1');
      expect(component.ordenStripePresencial).toBeNull();
    });

    it('cancelarStripePresencial NO borra la orden a null si ya está en CAPTURADO', () => {
      component.ordenStripePresencial = {
        venta_id: 'vnt-cap-1',
        orden_pago_id: 'ord-cap-1',
        stripe_payment_intent_id: 'pi_cap_1',
        client_secret: 'sec_cap_1',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'CAPTURADO'
      };

      component.cancelarStripePresencial();
      expect(component.ordenStripePresencial).not.toBeNull();
      expect(component.error).toContain('capturado');
      expect(stripeServiceSpy.cancelarOrdenPago).not.toHaveBeenCalled();
    });

    it('cancelarStripeCaja cancela orden en backend si está PENDIENTE y rechaza cancelación si está CAPTURADO', () => {
      component.ordenStripeCaja = {
        venta_id: 'vnt-cajacan-1',
        orden_pago_id: 'ord-cajacan-1',
        stripe_payment_intent_id: 'pi_cajacan_1',
        client_secret: 'sec_cajacan_1',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };

      component.cancelarStripeCaja();
      expect(stripeServiceSpy.cancelarOrdenPago).toHaveBeenCalledWith('ord-cajacan-1');
      expect(component.ordenStripeCaja).toBeNull();

      // Probar intento en CAPTURADO
      component.ordenStripeCaja = {
        venta_id: 'vnt-cajacan-cap',
        orden_pago_id: 'ord-cajacan-cap',
        stripe_payment_intent_id: 'pi_cajacan_cap',
        client_secret: 'sec_cajacan_cap',
        monto_bob: '100.00',
        monto_usd: '14.37',
        centavos_usd: 1437,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'CAPTURADO'
      };

      component.cancelarStripeCaja();
      expect(component.ordenStripeCaja).not.toBeNull();
      expect(component.error).toContain('capturado');
    });

    it('si cancelarStripePresencial falla con 409 o 502, NO debe poner la orden en null para preservar la referencia en UI y permitir reintento', () => {
      component.ordenStripePresencial = {
        venta_id: 'vnt-err-pre-1',
        orden_pago_id: 'ord-err-pre-1',
        stripe_payment_intent_id: 'pi_err_pre_1',
        client_secret: 'sec_err_pre_1',
        monto_bob: '150.00',
        monto_usd: '21.55',
        centavos_usd: 2155,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };

      stripeServiceSpy.cancelarOrdenPago.and.returnValue(
        throwError(() => ({ status: 409, error: { detail: 'Cobro capturado en pasarela; no se puede cancelar localmente' } }))
      );

      component.cancelarStripePresencial();

      // En código anterior (línea 1309): component.ordenStripePresencial = null
      // Esto hace fallar el test demostrando el contraejemplo rojo (H3)
      expect(component.ordenStripePresencial).not.toBeNull();
      expect(component.ordenStripePresencial?.orden_pago_id).toBe('ord-err-pre-1');
      expect(component.error).toBeTruthy();
    });

    it('si cancelarStripeCaja falla con 502 / timeout, NO debe poner la orden en null para mantenerla visible ante incertidumbre', () => {
      component.ordenStripeCaja = {
        venta_id: 'vnt-err-caj-1',
        orden_pago_id: 'ord-err-caj-1',
        stripe_payment_intent_id: 'pi_err_caj_1',
        client_secret: 'sec_err_caj_1',
        monto_bob: '200.00',
        monto_usd: '28.74',
        centavos_usd: 2874,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'PENDIENTE'
      };

      stripeServiceSpy.cancelarOrdenPago.and.returnValue(
        throwError(() => ({ status: 502, error: { detail: 'Fallo de comunicación con pasarela Stripe' } }))
      );

      component.cancelarStripeCaja();

      // En código anterior (línea 589): component.ordenStripeCaja = null
      // Esto hace fallar el test demostrando el contraejemplo rojo (H3)
      expect(component.ordenStripeCaja).not.toBeNull();
      expect(component.ordenStripeCaja?.orden_pago_id).toBe('ord-err-caj-1');
      expect(component.error).toBeTruthy();
    });

    const mockOrdenActivaOffline: OrdenActivaCajaDTO = {
      orden_pago_id: 'ord-rec-1',
      venta_id: 'vnt-rec-1',
      stripe_payment_intent_id: 'pi_rec_1',
      client_secret: 'sec_rec_1',
      monto_bob: '300.00',
      monto_usd: '43.10',
      centavos_usd: 4310,
      tasa_bob_por_usd: '6.96',
      estado_orden: 'PENDIENTE',
      sucursal_id: 'suc-111',
      turno_caja_id: 'turno-111',
      cliente_id: 'cli-rec-1',
      procedencia: 'TURNO_OFFLINE',
      lineas: [
        {
          variante_id: 'var-1',
          cantidad: 2,
          precio_unitario_bob: '150.00',
          descuento_bob: '0.00',
          sku: 'SKU-01',
          nombre_producto: 'Blusa Urbana'
        }
      ],
      estado_verificacion: 'VERIFICADO'
    };

    const mockOrdenActivaPresencial: OrdenActivaCajaDTO = {
      orden_pago_id: 'ord-rec-pres-1',
      venta_id: 'vnt-rec-pres-1',
      stripe_payment_intent_id: 'pi_rec_pres_1',
      client_secret: 'sec_rec_pres_1',
      monto_bob: '200.00',
      monto_usd: '28.74',
      centavos_usd: 2874,
      tasa_bob_por_usd: '6.96',
      estado_orden: 'PENDIENTE',
      sucursal_id: 'suc-111',
      turno_caja_id: null,
      cliente_id: 'cli-rec-pres-1',
      procedencia: 'PRESENCIAL',
      lineas: [
        {
          variante_id: 'var-1',
          cantidad: 1,
          precio_unitario_bob: '200.00',
          sku: 'SKU-01',
          nombre_producto: 'Blusa Urbana'
        }
      ],
      estado_verificacion: 'VERIFICADO'
    };

    it('a) restauracion tras F5 en panel TURNO_OFFLINE con lineas y cliente restaurados', () => {
      component.turnoActivo = mockTurno;
      component.vistaModo = 'RESERVA';
      component.ordenStripeCaja = null;
      component.lineasVentaOffline = [];
      component.clienteIdCaja = '';

      stripeServiceSpy.obtenerOrdenActivaCaja.and.returnValue(of(mockOrdenActivaOffline));

      component.recuperarOrdenActivaCaja();

      expect(stripeServiceSpy.obtenerOrdenActivaCaja).toHaveBeenCalled();
      expect(component.vistaModo).toBe('TURNO_OFFLINE');
      expect(component.ordenStripeCaja as any).toEqual(mockOrdenActivaOffline);
      expect(component.medioPagoCaja).toBe('STRIPE_TEST');
      expect(component.lineasVentaOffline.length).toBe(1);
      expect(component.lineasVentaOffline[0]).toEqual({
        variante_id: 'var-1',
        cantidad: 2,
        precio_bob: 150
      });
      expect(component.clienteIdCaja).toBe('cli-rec-1');
    });

    it('b) restauracion tras F5 en panel PRESENCIAL con items y cliente restaurados', () => {
      component.vistaModo = 'TURNO_OFFLINE';
      component.ordenStripePresencial = null;
      component.items = [];
      component.clienteIdPresencial = '';

      stripeServiceSpy.obtenerOrdenActivaCaja.and.returnValue(of(mockOrdenActivaPresencial));

      component.recuperarOrdenActivaCaja();

      expect(component.vistaModo).toBe('RESERVA');
      expect(component.ordenStripePresencial as any).toEqual(mockOrdenActivaPresencial);
      expect(component.metodo).toBe('STRIPE_TEST');
      expect(component.items.length).toBe(1);
      expect(component.items[0]).toEqual({
        variante_id: 'var-1',
        cantidad: 1
      });
      expect(component.clienteIdPresencial).toBe('cli-rec-pres-1');
    });

    it('c) recupera orden en estado CAPTURADO y liquida posterior a F5 sin re-iniciar PaymentIntent', fakeAsync(() => {
      const mockOrdenCapturada: OrdenActivaCajaDTO = {
        ...mockOrdenActivaOffline,
        estado_orden: 'CAPTURADO',
        client_secret: undefined
      };
      component.turnoActivo = JSON.parse(JSON.stringify(mockTurno));
      stripeServiceSpy.obtenerOrdenActivaCaja.and.returnValue(of(mockOrdenCapturada));

      component.recuperarOrdenActivaCaja();

      expect(component.ordenStripeCaja?.estado_orden).toBe('CAPTURADO');
      expect(component.lineasVentaOffline.length).toBe(1);

      ventaPresencialSpy.liquidarVentaPresencial.and.returnValue(of({
        venta_id: 'vnt-rec-1',
        numero: 'VTA-REC-001',
        total_bob: 300,
        comprobante_id: 'cmp-rec-1',
        medio_pago: 'STRIPE_TEST'
      }));

      component.cobrarVentaContado();
      tick();

      expect(ventaPresencialSpy.iniciarVentaPresencialStripe).not.toHaveBeenCalled();
      expect(ventaPresencialSpy.liquidarVentaPresencial).toHaveBeenCalledWith(
        jasmine.objectContaining({
          venta_id: 'vnt-rec-1',
          orden_pago_id: 'ord-rec-1',
          stripe_payment_intent_id: 'pi_rec_1',
          medio_pago: 'STRIPE_TEST',
          lineas: [{ variante_id: 'var-1', cantidad: 2, precio_unitario_bob: 150 }]
        })
      );
    }));

    it('d) manejo de cambio de turno o turno no coincidente alerta al cajero sin asociar orden', () => {
      component.turnoActivo = mockTurno; // turno_id === 'turno-111'
      const mockOrdenTurnoDiferente: OrdenActivaCajaDTO = {
        ...mockOrdenActivaOffline,
        turno_caja_id: 'turno-otro-888'
      };
      component.ordenStripeCaja = null;
      component.lineasVentaOffline = [];

      stripeServiceSpy.obtenerOrdenActivaCaja.and.returnValue(of(mockOrdenTurnoDiferente));

      component.recuperarOrdenActivaCaja();

      expect(component.ordenStripeCaja).toBeNull();
      expect(component.lineasVentaOffline.length).toBe(0);
      expect(component.error).toContain('turno');
    });

    it('e) manejo de estado NO_VERIFICADO_ERROR_PASARELA con preservacion de la orden y reintento', () => {
      component.turnoActivo = mockTurno;
      const mockOrdenErrorPasarela: OrdenActivaCajaDTO = {
        ...mockOrdenActivaOffline,
        estado_verificacion: 'NO_VERIFICADO_ERROR_PASARELA',
        estado_orden: 'PENDIENTE'
      };

      stripeServiceSpy.obtenerOrdenActivaCaja.and.returnValue(of(mockOrdenErrorPasarela));

      component.recuperarOrdenActivaCaja();

      expect(component.ordenStripeCaja).not.toBeNull();
      expect(component.ordenStripeCaja?.estado_orden).toBe('PENDIENTE');
      expect(component.ordenStripeCaja?.estado_verificacion).toBe('NO_VERIFICADO_ERROR_PASARELA');
      expect(component.error).toContain('No se pudo verificar el estado en Stripe por problema de red');

      // Reintento exitoso: pasarela se recupera y responde VERIFICADO
      stripeServiceSpy.obtenerOrdenActivaCaja.and.returnValue(of({
        ...mockOrdenActivaOffline,
        estado_verificacion: 'VERIFICADO',
        estado_orden: 'CAPTURADO'
      }));

      component.reintentarVerificacionOrdenActiva();

      expect(component.ordenStripeCaja?.estado_orden).toBe('CAPTURADO');
      expect(component.ordenStripeCaja?.estado_verificacion).toBe('VERIFICADO');
      expect(component.error).toBe('');
    });

    const crearMockOrdenProvisionalCaja = (): OrdenActivaCajaDTO => ({
      orden_pago_id: 'ord-prov-caja-1',
      venta_id: 'vnt-prov-caja-1',
      stripe_payment_intent_id: null,
      client_secret: null,
      monto_bob: '300.00',
      monto_usd: '43.10',
      centavos_usd: 4310,
      tasa_bob_por_usd: '6.96',
      estado_orden: 'PENDIENTE',
      sucursal_id: 'suc-111',
      turno_caja_id: 'turno-111',
      cliente_id: 'cli-prov-caja-1',
      procedencia: 'TURNO_OFFLINE',
      lineas: [
        {
          variante_id: 'var-1',
          cantidad: 2,
          precio_unitario_bob: '150.00',
          descuento_bob: '0.00',
          sku: 'SKU-01',
          nombre_producto: 'Blusa Urbana'
        }
      ],
      estado_verificacion: 'PROVISIONAL_PENDIENTE_INTENTO'
    });

    it('f) deteccion de orden provisional tras F5 con aviso accesible, renderizado del boton Reanudar Cobro Stripe y llamada a reanudarOrdenPago', fakeAsync(() => {
      component.turnoActivo = mockTurno;
      component.vistaModo = 'TURNO_OFFLINE';
      (component as any).ordenStripeCaja = null;

      stripeServiceSpy.obtenerOrdenActivaCaja.and.returnValue(of(crearMockOrdenProvisionalCaja()));

      component.recuperarOrdenActivaCaja();
      fixture.detectChanges();

      expect(component.esOrdenProvisional(component.ordenStripeCaja)).toBeTrue();
      const ordenProvisional = component.ordenStripeCaja as unknown as OrdenActivaCajaDTO;
      expect(ordenProvisional?.estado_verificacion).toBe('PROVISIONAL_PENDIENTE_INTENTO');
      expect(ordenProvisional?.stripe_payment_intent_id).toBeNull();

      // Comprobar aviso accesible en DOM
      const alertaProvisional = fixture.nativeElement.querySelector('.stripe-alerta-provisional');
      expect(alertaProvisional).not.toBeNull();
      expect(alertaProvisional.getAttribute('role')).toBe('alert');
      expect(alertaProvisional.getAttribute('aria-live')).toBe('polite');
      expect(alertaProvisional.textContent).toContain('Orden de pago provisional detectada. Reanude el cobro para obtener la pasarela o cancele la orden.');

      // Comprobar botón explícito "Reanudar Cobro Stripe"
      const btnReanudar = fixture.nativeElement.querySelector('.btn-reanudar-stripe');
      expect(btnReanudar).not.toBeNull();
      expect(btnReanudar.textContent).toContain('Reanudar Cobro Stripe');

      // Comprobar que el card element NO está visible mientras la orden es provisional
      const cardElement = fixture.nativeElement.querySelector('#stripe-card-element-caja');
      expect(cardElement).toBeNull();

      // Pulsar "Reanudar Cobro Stripe"
      stripeServiceSpy.reanudarOrdenPago.and.returnValue(of({
        orden_pago_id: 'ord-prov-caja-1',
        estado: 'PENDIENTE',
        client_secret: 'pi_prov_secret_999',
        referencia_externa: 'pi_prov_999'
      } as any));

      component.reanudarCobroStripeCaja();
      tick();
      fixture.detectChanges();

      expect(stripeServiceSpy.reanudarOrdenPago).toHaveBeenCalledWith('ord-prov-caja-1');
      const ordenReanudada = component.ordenStripeCaja as unknown as OrdenActivaCajaDTO;
      expect(ordenReanudada?.client_secret).toBe('pi_prov_secret_999');
      expect(ordenReanudada?.stripe_payment_intent_id).toBe('pi_prov_999');
      expect(ordenReanudada?.estado_verificacion).toBe('VERIFICADO');
      expect(component.esOrdenProvisional(component.ordenStripeCaja)).toBeFalse();
      expect(component.mensajeExito).toContain('reanudada exitosamente');
    }));

    it('g) liquidacion posterior a F5 con orden CAPTURADO en venta presencial preserva lineas congeladas del servidor sin recalcular con catalogo', fakeAsync(() => {
      component.vistaModo = 'RESERVA';
      component.reserva = undefined;
      component.metodo = 'STRIPE_TEST';

      // Simular que el catálogo actual tiene un precio diferente (aumento a Bs 300)
      component.variantes = [
        {
          id: 'var-1',
          producto_id: 'prod-1',
          sku: 'SKU-01',
          precio: '300.00',
          activo: true
        } as any
      ];

      const mockOrdenPresencialCapturada: OrdenActivaCajaDTO = {
        orden_pago_id: 'ord-f5-cap-1',
        venta_id: 'vnt-f5-cap-1',
        stripe_payment_intent_id: 'pi_f5_cap_1',
        client_secret: null,
        monto_bob: '200.00',
        monto_usd: '28.74',
        centavos_usd: 2874,
        tasa_bob_por_usd: '6.96',
        estado_orden: 'CAPTURADO',
        sucursal_id: 'suc-111',
        turno_caja_id: null,
        cliente_id: 'cli-f5-1',
        procedencia: 'PRESENCIAL',
        lineas: [
          {
            variante_id: 'var-1',
            cantidad: 2,
            precio_unitario_bob: '100.00',
            descuento_bob: '0.00',
            sku: 'SKU-01',
            nombre_producto: 'Blusa Urbana'
          }
        ],
        estado_verificacion: 'VERIFICADO'
      };

      stripeServiceSpy.obtenerOrdenActivaCaja.and.returnValue(of(mockOrdenPresencialCapturada));

      component.recuperarOrdenActivaCaja();

      expect(component.ordenStripePresencial?.estado_orden).toBe('CAPTURADO');
      expect(component.items.length).toBe(1);
      expect(component.items[0].variante_id).toBe('var-1');
      expect(component.items[0].cantidad).toBe(2);

      // Simular cálculo de totales presenciales: debe respetar los precios congelados del servidor
      component.calcularTotalesPresenciales();
      expect(component.totalPresencialEstimado).toBe(200); // 2 * 100, NO 2 * 300

      ventaPresencialSpy.liquidarVentaPresencial.and.returnValue(of({
        venta_id: 'vnt-f5-cap-1',
        numero: 'VTA-F5-001',
        total_bob: 200,
        comprobante_id: 'cmp-f5-1',
        medio_pago: 'STRIPE_TEST'
      }));

      component.vender();
      tick();

      expect(ventaPresencialSpy.liquidarVentaPresencial).toHaveBeenCalledWith(
        jasmine.objectContaining({
          venta_id: 'vnt-f5-cap-1',
          orden_pago_id: 'ord-f5-cap-1',
          stripe_payment_intent_id: 'pi_f5_cap_1',
          medio_pago: 'STRIPE_TEST',
          lineas: [{
            variante_id: 'var-1',
            cantidad: 2,
            precio_unitario_bob: 100
          }]
        })
      );
      expect(component.ventaLiquidada?.total_bob).toBe(200);
    }));

    it('h) manejo accesible de error 502 de pasarela con preservacion de estado y reintento exitoso', fakeAsync(() => {
      component.turnoActivo = mockTurno;
      component.vistaModo = 'TURNO_OFFLINE';
      component.ordenStripeCaja = crearMockOrdenProvisionalCaja();

      // 1. Simular error HTTP 502 de pasarela al reanudar orden
      stripeServiceSpy.reanudarOrdenPago.and.returnValue(throwError(() => ({
        status: 502,
        error: { detail: 'Error al comunicar con la pasarela Stripe para reanudar la orden; se conserva provisional para reintento.' }
      })));

      component.reanudarCobroStripeCaja();
      tick();
      fixture.detectChanges();

      // Verificar que el error se muestra de forma accesible y la orden se conserva provisional
      expect(component.error).toContain('Error al comunicar con la pasarela Stripe');
      expect(component.reanudandoStripeCaja).toBeFalse();
      expect(component.esOrdenProvisional(component.ordenStripeCaja)).toBeTrue();

      // 2. Reintento exitoso tras restablecimiento de la pasarela
      stripeServiceSpy.reanudarOrdenPago.and.returnValue(of({
        orden_pago_id: 'ord-prov-caja-1',
        estado: 'PENDIENTE',
        client_secret: 'pi_reintento_sec_1',
        referencia_externa: 'pi_reintento_1'
      } as any));

      component.reanudarCobroStripeCaja();
      tick();
      fixture.detectChanges();

      expect(component.error).toBe('');
      expect(component.ordenStripeCaja?.stripe_payment_intent_id).toBe('pi_reintento_1');
      expect(component.ordenStripeCaja?.client_secret).toBe('pi_reintento_sec_1');
      expect(component.esOrdenProvisional(component.ordenStripeCaja)).toBeFalse();
      expect(component.mensajeExito).toContain('reanudada exitosamente');
    }));
  });
});
