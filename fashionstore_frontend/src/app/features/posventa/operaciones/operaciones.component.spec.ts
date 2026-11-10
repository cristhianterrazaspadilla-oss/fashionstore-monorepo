import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { OperacionesComponent } from './operaciones.component';
import { VentaPresencialService } from '../../ventas_pagos/services/venta-presencial.service';
import { PosventaService } from '../services/posventa.service';
import { ReporteVentasService } from '../../analitica/services/reporte-ventas.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { ProductoService } from '../../catalogo/services/producto.service';
import { Comprobante } from '../../ventas_pagos/models/venta-presencial.models';
import { CambioDTO, DevolucionDTO } from '../models/posventa.models';

describe('OperacionesComponent (Devoluciones, Inspecciones Técnicas y Cambios de Prenda)', () => {
  let component: OperacionesComponent;
  let fixture: ComponentFixture<OperacionesComponent>;

  let ventasServiceSpy: jasmine.SpyObj<VentaPresencialService>;
  let posventaServiceSpy: jasmine.SpyObj<PosventaService>;
  let reportesServiceSpy: jasmine.SpyObj<ReporteVentasService>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let orgServiceSpy: jasmine.SpyObj<OrganizacionService>;
  let productoServiceSpy: jasmine.SpyObj<ProductoService>;

  const mockComprobante: Comprobante = {
    id: 'vta-100',
    numero: 'VNT-2026-0001',
    sucursal_id: 'suc-1',
    canal: 'PRESENCIAL',
    estado: 'PAGADA',
    subtotal: 300,
    descuento: 0,
    adelanto_descontado: 0,
    costo_entrega: 0,
    total: 300,
    creada_en: '2026-11-04T10:00:00-04:00',
    pagos: [],
    detalles: [
      {
        id: 'det-1',
        variante_id: 'var-1',
        cantidad: 2,
        precio_unitario: 150,
        descuento: 0
      }
    ]
  };

  const mockVariantes = [
    { id: 'var-1', sku: 'SKU-001', precio: '150.00' } as any,
    { id: 'var-2', sku: 'SKU-002', precio: '180.00' } as any
  ];

  beforeEach(async () => {
    ventasServiceSpy = jasmine.createSpyObj<VentaPresencialService>('VentaPresencialService', ['comprobante']);
    posventaServiceSpy = jasmine.createSpyObj<PosventaService>('PosventaService', [
      'devolver',
      'solicitarDevolucion',
      'registrarInspeccion',
      'registrarMerma',
      'registrarMermaAuditada',
      'solicitarCambio',
      'resolverDiferenciaCambio'
    ]);
    reportesServiceSpy = jasmine.createSpyObj<ReporteVentasService>('ReporteVentasService', ['reporteVentas']);
    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', ['obtenerUsuarioActual']);
    orgServiceSpy = jasmine.createSpyObj<OrganizacionService>('OrganizacionService', ['gestionarSucursales']);
    productoServiceSpy = jasmine.createSpyObj<ProductoService>('ProductoService', ['gestionarVariantes']);

    authServiceSpy.obtenerUsuarioActual.and.returnValue({
      id: 'usr-1',
      usuario_id: 'usr-1',
      nombres: 'Cajero',
      apellidos: 'Principal',
      nombre_completo: 'Cajero Principal',
      correo: 'cajero@boutique.com',
      rol: 'CAJERO',
      sucursal_id: 'suc-1'
    } as any);

    orgServiceSpy.gestionarSucursales.and.returnValue(of([{ id: 'suc-1', nombre: 'Sucursal Central' } as any]));
    productoServiceSpy.gestionarVariantes.and.returnValue(of(mockVariantes));
    reportesServiceSpy.reporteVentas.and.returnValue(of({ resumen: { total_ventas: 1, unidades: 2, monto_total: 300, ticket_promedio: 300 }, items: [] } as any));

    await TestBed.configureTestingModule({
      imports: [OperacionesComponent],
      providers: [
        { provide: VentaPresencialService, useValue: ventasServiceSpy },
        { provide: PosventaService, useValue: posventaServiceSpy },
        { provide: ReporteVentasService, useValue: reportesServiceSpy },
        { provide: AuthService, useValue: authServiceSpy },
        { provide: OrganizacionService, useValue: orgServiceSpy },
        { provide: ProductoService, useValue: productoServiceSpy }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(OperacionesComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('debe crearse e inicializar sucursales y variantes', () => {
    expect(component).toBeTruthy();
    expect(component.sucursal).toBe('suc-1');
    expect(component.variantes.length).toBe(2);
  });

  it('debe buscar una venta para devolución y seleccionar automáticamente si tiene una sola línea', () => {
    ventasServiceSpy.comprobante.and.returnValue(of(mockComprobante));

    component.buscarVentaParaDevolucion('VNT-2026-0001');

    expect(ventasServiceSpy.comprobante).toHaveBeenCalledWith('VNT-2026-0001');
    expect(component.comprobanteDev).toEqual(mockComprobante);
    expect(component.detalleSeleccionado).toEqual(mockComprobante.detalles[0]);
    expect(component.detalleVenta).toBe('det-1');
  });

  it('debe procesar devolución con inspección técnica CU20', () => {
    ventasServiceSpy.comprobante.and.returnValue(of(mockComprobante));
    component.buscarVentaParaDevolucion('VNT-2026-0001');

    const mockDevResp: DevolucionDTO = {
      devolucion_id: 'dev-1',
      venta_id: 'vta-100',
      estado: 'SOLICITADA'
    };
    posventaServiceSpy.solicitarDevolucion.and.returnValue(of(mockDevResp));
    posventaServiceSpy.registrarInspeccion.and.returnValue(of({ ...mockDevResp, estado: 'APROBADA_REPOSICION' }));

    component.realizarInspeccion = true;
    component.dictamenInspeccion = 'APROBADA_REPOSICION';
    component.condicionFisica = 'EXCELENTE';
    component.observacionesInspeccion = 'Prenda en perfecto estado';

    component.devolver();

    expect(posventaServiceSpy.solicitarDevolucion).toHaveBeenCalled();
    expect(posventaServiceSpy.registrarInspeccion).toHaveBeenCalledWith('dev-1', jasmine.objectContaining({
      dictamen: 'APROBADA_REPOSICION'
    }));
    expect(component.exito).toContain('dictamen');
  });

  it('debe calcular la diferencia financiera para cambio de prenda CU08', () => {
    component.lineasOriginalesCambio = [
      { variante_id: 'var-1', cantidad: 1, precio_unitario_bob: 150 }
    ];
    component.reemplazosCambio = [
      { variante_id: 'var-2', cantidad: 1, precio_unitario_bob: 180 }
    ];

    // Reemplazo (180) - Original (150) = 30 a pagar por el cliente
    expect(component.calcularDiferenciaCambio()).toBe(30);

    // Si el reemplazo es de 100, la diferencia es -50 (a favor del cliente)
    component.reemplazosCambio[0].precio_unitario_bob = 100;
    expect(component.calcularDiferenciaCambio()).toBe(-50);
  });

  it('debe solicitar cambio de prenda y permitir resolver diferencia', () => {
    component.comprobanteCambio = mockComprobante;
    component.lineasOriginalesCambio = [
      { variante_id: 'var-1', cantidad: 1, precio_unitario_bob: 150 }
    ];
    component.reemplazosCambio = [
      { variante_id: 'var-2', cantidad: 1, precio_unitario_bob: 180 }
    ];

    const mockCambioResp: CambioDTO = {
      cambio_id: 'cam-1',
      nota_codigo: 'NOT-CAM-01',
      vence_espera_en: '2026-11-05T10:00:00-04:00',
      diferencia_bob: 30,
      estado: 'SOLICITADO'
    };
    posventaServiceSpy.solicitarCambio.and.returnValue(of(mockCambioResp));
    posventaServiceSpy.resolverDiferenciaCambio.and.returnValue(of({ ...mockCambioResp, estado: 'COMPLETADO' }));

    component.solicitarCambio();
    expect(posventaServiceSpy.solicitarCambio).toHaveBeenCalled();
    expect(component.cambioRegistrado).toEqual(mockCambioResp);

    component.destinoDiferencia = 'PAGO_CLIENTE';
    component.resolverDiferencia();
    expect(posventaServiceSpy.resolverDiferenciaCambio).toHaveBeenCalledWith('cam-1', jasmine.objectContaining({
      destino_diferencia: 'PAGO_CLIENTE'
    }));
    expect(component.exito).toContain('resuelta con éxito');
  });

  describe('Políticas de Plazo y Garantía Posventa (CU20 / CU08 / CU09)', () => {
    it('calcula los días desde la entrega confirmada (entregada_en) en lugar de la creación', () => {
      const ahora = new Date();
      const hace10Dias = new Date(ahora.getTime() - 10 * 86400 * 1000).toISOString();
      const hace30Dias = new Date(ahora.getTime() - 30 * 86400 * 1000).toISOString();

      const compEntregado = {
        ...mockComprobante,
        creada_en: hace30Dias,
        entregada_en: hace10Dias
      };

      const dias = component.diasDesdeEntrega(compEntregado);
      expect(dias).toBe(10);
      expect(component.estaDentroPlazo15Dias(compEntregado)).toBeTrue();
    });

    it('marca reclamos fuera de 15 días por defecto como PENDIENTE_EVALUACION en lugar de rechazo', () => {
      const ahora = new Date();
      const hace25Dias = new Date(ahora.getTime() - 25 * 86400 * 1000).toISOString();

      const compVencido = {
        ...mockComprobante,
        entregada_en: hace25Dias
      };
      component.comprobanteDev = compVencido;
      component.detalleSeleccionado = compVencido.detalles[0];
      component.detalleVenta = 'det-1';
      component.motivoCodigoDev = 'DEFECTO_FABRICACION';

      expect(component.estaDentroPlazo15Dias(compVencido)).toBeFalse();
      expect(component.esReclamoTardioDefecto(compVencido, component.motivoCodigoDev)).toBeTrue();

      posventaServiceSpy.solicitarDevolucion.and.returnValue(of({
        devolucion_id: 'dev-eval-1',
        venta_id: 'vta-100',
        estado: 'PENDIENTE_EVALUACION'
      }));

      component.devolver();
      expect(posventaServiceSpy.solicitarDevolucion).toHaveBeenCalledWith(jasmine.objectContaining({
        motivo_codigo: 'DEFECTO_FABRICACION'
      }));
    });

    it('permite seleccionar resoluciones financieras exclusivas (SALDO o REEMBOLSO)', () => {
      component.destinoDiferencia = 'SALDO';
      expect(component.destinoDiferencia).toBe('SALDO');

      component.destinoDiferencia = 'REEMBOLSO';
      expect(component.destinoDiferencia).toBe('REEMBOLSO');
    });

    it('formatea fechas en zona horaria boliviana (America/La_Paz)', () => {
      const fechaUtc = '2026-11-04T16:00:00Z';
      const texto = component.fechaHoraBO(fechaUtc);
      expect(texto).toContain('12:00'); // UTC-4 en La Paz
    });
  });
});
