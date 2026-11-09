import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { of } from 'rxjs';
import { DashboardComponent } from './dashboard.component';
import { DashboardService } from '../services/dashboard.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { DashboardDTO } from '../models/analitica-ia.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';

describe('DashboardComponent (Mesa de corte analítica y visualizaciones nativas)', () => {
  let component: DashboardComponent;
  let fixture: ComponentFixture<DashboardComponent>;

  let dashboardServiceSpy: jasmine.SpyObj<DashboardService>;
  let orgServiceSpy: jasmine.SpyObj<OrganizacionService>;
  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let routerSpy: jasmine.SpyObj<Router>;

  const mockDashboardReal: DashboardDTO = {
    desde: '2026-09-01T00:00:00Z',
    hasta: '2026-09-20T23:59:59Z',
    ventas_total: 45,
    ingresos_total: '12500.50',
    margen_bruto_total: '4200.00',
    ticket_promedio: '277.79',
    por_sucursal: [
      { sucursal_id: 'suc-2', sucursal_nombre: 'Sucursal Equipetrol', ventas: 15, ingresos: '4000.50' },
      { sucursal_id: 'suc-1', sucursal_nombre: 'Central Calacoto', ventas: 30, ingresos: '8500.00' }
    ],
    top_productos: [
      { producto: 'Blusa Lino Beige', unidades: 12 },
      { producto: 'Vestido Seda Noir', unidades: 18 }
    ],
    stock_critico: [
      { sku: 'BLU-LIN-M', sucursal_id: 'suc-1', disponible: 2, existencia: 4 },
      { sku: 'VES-SED-S', sucursal_id: 'suc-2', disponible: 0, existencia: 1 },
      { sku: 'PAN-DEN-38', sucursal_id: 'suc-1', disponible: 5, existencia: 8 }
    ],
    valorizacion_total: '38900.00',
    conversion_reservas: {
      total: 50,
      completadas: 40,
      tasa: 0.80
    },
    estados_pedidos: {
      SOLICITADO: 5,
      PREPARADO: 10,
      EN_REPARTO: 4,
      ENTREGADO: 25,
      CANCELADO: 1
    },
    efectividad_promociones: {
      con_promocion: 20,
      sin_promocion: 25,
      descuento_total: '1500.00'
    }
  };

  const mockSucursales: SucursalDTO[] = [
    {
      id: 'suc-1',
      ciudad_id: 'c-1',
      nombre: 'Central Calacoto',
      direccion: 'Av. Ballivian 123',
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
      ciudad_id: 'c-1',
      nombre: 'Sucursal Equipetrol',
      direccion: 'Av. San Martin 456',
      telefono: '70000001',
      numero_anillo: 2,
      tarifa_base_delivery: 20,
      incremento_anillo_delivery: 5,
      anillo_minimo_delivery: 1,
      anillo_maximo_delivery: 5,
      delivery_activo: true,
      activa: true
    }
  ];

  beforeEach(async () => {
    dashboardServiceSpy = jasmine.createSpyObj<DashboardService>('DashboardService', ['consultar']);
    orgServiceSpy = jasmine.createSpyObj<OrganizacionService>('OrganizacionService', ['gestionarSucursales']);
    authServiceSpy = jasmine.createSpyObj<AuthService>('AuthService', ['obtenerUsuarioActual']);
    routerSpy = jasmine.createSpyObj<Router>('Router', ['navigate']);

    dashboardServiceSpy.consultar.and.returnValue(of(JSON.parse(JSON.stringify(mockDashboardReal))));
    orgServiceSpy.gestionarSucursales.and.returnValue(of(mockSucursales));
    authServiceSpy.obtenerUsuarioActual.and.returnValue({
      id: 'u-admin',
      usuario_id: 'u-admin',
      nombres: 'Admin',
      apellidos: 'Principal',
      nombre_completo: 'Admin Principal',
      correo_electronico: 'admin@fs.com',
      rol: 'ADMINISTRADOR',
      estado: 'ACTIVO',
      preferencias: {},
      creado_en: '2026-01-01'
    });

    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [
        { provide: DashboardService, useValue: dashboardServiceSpy },
        { provide: OrganizacionService, useValue: orgServiceSpy },
        { provide: AuthService, useValue: authServiceSpy },
        { provide: Router, useValue: routerSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: {
                get: (k: string) => (k === 'sucursal' ? 'suc-1' : null)
              }
            }
          }
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(DashboardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('procesa el contrato real y presenta la jerarquía de métricas', () => {
    expect(component.dashboard).toBeTruthy();
    const d = component.dashboard!;

    expect(d.ventas_total).toBe(45);
    expect(Number(d.ingresos_total)).toBe(12500.50);
    expect(Number(d.margen_bruto_total)).toBe(4200.00);
    expect(Number(d.ticket_promedio)).toBe(277.79);
    expect(Number(d.valorizacion_total)).toBe(38900.00);

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Dashboard de indicadores');
    expect(compiled.textContent).toContain('Facturación comercial');
    expect(compiled.textContent).toContain('12.500,50');
  });

  it('ordena barras por sucursal sin mutar el DTO original', () => {
    const ordenado = component.sucursalesBarsVM;
    expect(ordenado.length).toBe(2);
    // El primero debe ser Central Calacoto por mayores ingresos (8500 vs 4000.50)
    expect(ordenado[0].etiqueta).toBe('Central Calacoto');
    expect(ordenado[0].valor).toBe(8500);
    expect(ordenado[1].etiqueta).toBe('Sucursal Equipetrol');

    // Comprobar que el DTO en el componente mantiene su primer elemento original
    expect(component.dashboard!.por_sucursal[0].sucursal_id).toBe('suc-2');
  });

  it('ordena el ranking de productos sin mutar el DTO original', () => {
    const ranking = component.topProductosBarsVM;
    expect(ranking.length).toBe(2);
    expect(ranking[0].etiqueta).toBe('Vestido Seda Noir');
    expect(ranking[0].valor).toBe(18);
    expect(ranking[1].etiqueta).toBe('Blusa Lino Beige');
    expect(ranking[1].valor).toBe(12);

    expect(component.dashboard!.top_productos[0].producto).toBe('Blusa Lino Beige');
  });

  it('clasifica los niveles de urgencia de stock crítico basados exclusivamente en disponible', () => {
    const criticos = component.stockCriticoVM;
    expect(criticos.length).toBe(3);

    const agotado = criticos.find(c => c.sku === 'VES-SED-S');
    expect(agotado?.nivelUrgencia).toBe('agotado');
    expect(agotado?.etiquetaUrgencia).toContain('Agotado');

    const critico = criticos.find(c => c.sku === 'BLU-LIN-M');
    expect(critico?.nivelUrgencia).toBe('critico');
    expect(critico?.etiquetaUrgencia).toBe('Crítico');

    const aviso = criticos.find(c => c.sku === 'PAN-DEN-38');
    expect(aviso?.nivelUrgencia).toBe('aviso');
    expect(aviso?.etiquetaUrgencia).toBe('Bajo stock');
  });

  it('maneja de forma segura conversión de reservas cuando el total es cero', () => {
    component.dashboard!.conversion_reservas = {
      total: 0,
      completadas: 0,
      tasa: 0
    };
    fixture.detectChanges();

    expect(component.conversionTasaPorcentaje).toBe(0);
    expect(component.dashboard!.conversion_reservas.total).toBe(0);
  });

  it('maneja de forma segura efectividad de promociones cuando ambas cantidades son cero', () => {
    component.dashboard!.efectividad_promociones = {
      con_promocion: 0,
      sin_promocion: 0,
      descuento_total: '0.00'
    };
    fixture.detectChanges();

    const segs = component.promocionesSegmentosVM;
    expect(segs[0].valor).toBe(0);
    expect(segs[1].valor).toBe(0);
  });

  it('permite alternar la visualización de la tabla detallada de sucursales', () => {
    expect(component.mostrarTablaSucursal).toBeFalse();
    component.toggleTablaSucursal();
    expect(component.mostrarTablaSucursal).toBeTrue();
    fixture.detectChanges();

    const tabla = fixture.nativeElement.querySelector('.table-complementaria');
    expect(tabla).toBeTruthy();
  });

  it('restringe la sucursal forzada si el rol es ENCARGADO', () => {
    authServiceSpy.obtenerUsuarioActual.and.returnValue({
      id: 'u-enc',
      usuario_id: 'u-enc',
      nombres: 'Encargado',
      apellidos: 'Calacoto',
      nombre_completo: 'Encargado Calacoto',
      correo_electronico: 'enc@fs.com',
      rol: 'ENCARGADO',
      estado: 'ACTIVO',
      sucursal_id: 'suc-calacoto',
      preferencias: {},
      creado_en: '2026-01-01'
    });

    component.ngOnInit();

    expect(component.esAdmin).toBeFalse();
    expect(component.sucursalFiltro).toBe('suc-calacoto');
  });

  describe('Verificaciones estructurales de responsividad y accesibilidad (320, 360, 390, 768, 1024 y 1440 px)', () => {
    it('provee tarjetas móviles como alternativa a la tabla de stock crítico para pantallas estrechas (320px - 640px)', () => {
      const compiled = fixture.nativeElement as HTMLElement;

      // La tabla de escritorio y el contenedor de tarjetas móviles coexisten en el DOM
      const tablaDesktop = compiled.querySelector('.critical-table-wrap');
      const tarjetasMobile = compiled.querySelector('.critical-mobile-list');

      expect(tablaDesktop).withContext('Tabla de escritorio presente en DOM').toBeTruthy();
      expect(tarjetasMobile).withContext('Lista de tarjetas móviles presente en DOM').toBeTruthy();

      const cards = compiled.querySelectorAll('.critical-card');
      expect(cards.length).toBe(component.stockCriticoVM.length);

      // Cada tarjeta móvil debe incluir información completa sin depender solo de color
      cards.forEach((card, idx) => {
        const item = component.stockCriticoVM[idx];
        const cardText = card.textContent ?? '';
        expect(cardText).toContain(item.sku);
        expect(cardText).toContain(item.sucursalNombre);
        expect(cardText).toContain(`${item.disponible} un.`);
        expect(cardText).toContain(`${item.existencia} un.`);

        const badge = card.querySelector('.urgency-badge');
        expect(badge?.getAttribute('data-nivel')).toBe(item.nivelUrgencia);
        expect(badge?.textContent).toContain(item.etiquetaUrgencia);
      });
    });

    it('asegura que los controles interactivos y botones cumplen requisitos de accesibilidad y foco táctil', () => {
      const compiled = fixture.nativeElement as HTMLElement;
      const botones = compiled.querySelectorAll('button');

      expect(botones.length).toBeGreaterThan(0);
      botones.forEach(btn => {
        // Todo botón debe tener type="button" explícito
        expect(btn.getAttribute('type')).toBe('button');
        // Debe tener texto visible o aria-label
        const tieneTexto = (btn.textContent?.trim().length ?? 0) > 0;
        const tieneAria = btn.hasAttribute('aria-label');
        expect(tieneTexto || tieneAria).toBeTrue();
      });

      // Inputs accesibles
      const inputs = compiled.querySelectorAll('input, select');
      inputs.forEach(input => {
        const tieneId = input.hasAttribute('id');
        const tieneAria = input.hasAttribute('aria-label') || input.hasAttribute('aria-labelledby');
        expect(tieneId || tieneAria).toBeTrue();
      });
    });

    it('maneja textos largos, SKU e importes extensos sin rotura de elementos clave', () => {
      // DTO con valores extensos para evaluar contención
      component.dashboard!.top_productos = [
        { producto: 'Vestido de Noche en Seda Noir con Corte Asimétrico y Bordado Artesanal de Temporada', unidades: 120 }
      ];
      component.dashboard!.por_sucursal = [
        { sucursal_id: 'suc-ext', sucursal_nombre: 'Sucursal Central Boutique Zona Sur Macrodistrito Calacoto', ventas: 150, ingresos: '1254300.75' }
      ];
      component.dashboard!.stock_critico = [
        { sku: 'SKU-VES-SEDA-NOIR-EDICION-LIMITADA-TALLA-XL', sucursal_id: 'suc-ext', disponible: 1, existencia: 3 }
      ];
      fixture.detectChanges();

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.textContent).toContain('Vestido de Noche en Seda');
      expect(compiled.textContent).toContain('Sucursal Central Boutique');
      expect(compiled.textContent).toContain('SKU-VES-SEDA-NOIR');
      expect(compiled.textContent).toContain('1.254.300,75');
    });

    it('la barra de filtros está estructurada con clases que permiten apilado vertical en móvil', () => {
      const compiled = fixture.nativeElement as HTMLElement;
      const toolbar = compiled.querySelector('.dash-toolbar');
      const filtrosWrap = compiled.querySelector('.toolbar-filtros');

      expect(toolbar).toBeTruthy();
      expect(filtrosWrap).toBeTruthy();

      const fields = compiled.querySelectorAll('.filter-field');
      expect(fields.length).toBeGreaterThanOrEqual(2);
    });

    it('presenta el desglose del flujo financiero comercial (CU23): dinero capturado y neto comercial', () => {
      component.dashboard = {
        ...mockDashboardReal,
        ventas_brutas: 15000,
        descuentos: 1200,
        devoluciones: 800,
        reembolsos: 500,
        neto_comercial: 12500,
        dinero_capturado: 14500,
        pedidos_pendientes_cumplimiento: 3,
        monto_pedidos_pendientes: 1800
      };
      fixture.detectChanges();

      expect(component.dineroCapturado).toContain('14.500');
      expect(component.netoComercial).toContain('12.500');
      expect(component.ventasBrutas).toContain('15.000');
      expect(component.pedidosPendientesCumplimiento).toBe(3);

      const compiled = fixture.nativeElement as HTMLElement;
      expect(compiled.textContent).toContain('Dinero capturado');
      expect(compiled.textContent).toContain('Neto comercial');
      expect(compiled.textContent).toContain('Ventas brutas');
      expect(compiled.textContent).toContain('En preparación / despacho');
    });
  });
});
