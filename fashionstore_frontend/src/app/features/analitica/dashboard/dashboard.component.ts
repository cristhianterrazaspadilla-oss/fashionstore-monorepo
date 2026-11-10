import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DashboardService } from '../services/dashboard.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { DashboardDTO, DashboardStockCritico } from '../models/analitica-ia.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';
import { formatearBs, entradaLocalIso } from '../../../core/utils/moneda.util';
import { etiquetaEstado, claseEstado } from '../../../core/utils/estado-mapper.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import { RadialProgressComponent } from '../../../shared/data-viz/radial-progress/radial-progress.component';
import { HorizontalBarsComponent, HorizontalBarItem } from '../../../shared/data-viz/horizontal-bars/horizontal-bars.component';
import { SegmentedBarComponent, SegmentoItem } from '../../../shared/data-viz/segmented-bar/segmented-bar.component';

export interface StockCriticoItemVM extends DashboardStockCritico {
  sucursalNombre: string;
  nivelUrgencia: 'agotado' | 'critico' | 'aviso';
  etiquetaUrgencia: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RadialProgressComponent,
    HorizontalBarsComponent,
    SegmentedBarComponent
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.css']
})
export class DashboardComponent implements OnInit {
  dashboard: DashboardDTO | null = null;
  sucursales: SucursalDTO[] = [];
  sucursalFiltro = '';
  desdeFiltro = '';
  hastaFiltro = '';
  cargando = true;
  error: string | null = null;
  esAdmin = false;
  mostrarTablaSucursal = false;

  private readonly destroyRef = inject(DestroyRef);
  private cargaActual = 0;

  constructor(
    private dashboardService: DashboardService,
    private orgService: OrganizacionService,
    private authService: AuthService,
    private route: ActivatedRoute,
    private router: Router
  ) {}

  ngOnInit(): void {
    const u = this.authService.obtenerUsuarioActual();
    this.esAdmin = u?.rol === 'ADMINISTRADOR';

    // Leer filtros iniciales desde query parameters
    const qp = this.route.snapshot.queryParamMap;
    this.desdeFiltro = qp.get('desde') ?? '';
    this.hastaFiltro = qp.get('hasta') ?? '';

    if (!this.esAdmin && u?.sucursal_id) {
      // El encargado queda estrictamente limitado a su sucursal
      this.sucursalFiltro = u.sucursal_id;
    } else {
      this.sucursalFiltro = qp.get('sucursal') ?? '';
    }

    this.orgService.gestionarSucursales().subscribe(s => this.sucursales = s);
    this.cargar();
  }

  aplicarFiltros(): void {
    const queryParams: Record<string, string | null> = {
      desde: this.desdeFiltro || null,
      hasta: this.hastaFiltro || null,
    };
    if (this.esAdmin) {
      queryParams['sucursal'] = this.sucursalFiltro || null;
    }

    this.router.navigate([], {
      relativeTo: this.route,
      queryParams,
      queryParamsHandling: 'merge'
    });

    this.cargar();
  }

  limpiarFiltros(): void {
    this.desdeFiltro = '';
    this.hastaFiltro = '';
    if (this.esAdmin) {
      this.sucursalFiltro = '';
    }
    this.aplicarFiltros();
  }

  cargar(): void {
    const carga = ++this.cargaActual;
    this.cargando = true;
    this.error = null;
    this.dashboard = null;

    const payload = {
      desde: entradaLocalIso(this.desdeFiltro),
      hasta: entradaLocalIso(this.hastaFiltro),
      sucursal_id: this.sucursalFiltro || undefined
    };

    this.dashboardService.consultar(payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: d => {
          if (carga !== this.cargaActual) return;
          this.dashboard = d;
          this.cargando = false;
        },
        error: e => {
          if (carga !== this.cargaActual) return;
          this.error = formatearErrorApi(e, 'No se pudieron consultar los indicadores del dashboard.');
          this.cargando = false;
        }
      });
  }

  toggleTablaSucursal(): void {
    this.mostrarTablaSucursal = !this.mostrarTablaSucursal;
  }

  sucursalNombre(id: string): string {
    return this.sucursales.find(s => s.id === id)?.nombre ?? 'Sucursal local';
  }

  num(val: number | string | null | undefined): number {
    return Number(val ?? 0);
  }

  bs(m: number | string | null | undefined): string {
    return formatearBs(m);
  }

  etiqueta(estado: string): string {
    return etiquetaEstado(estado);
  }

  clase(estado: string): string {
    return claseEstado(estado);
  }

  // --- View Models seguros (inmutabilidad estricta de DTOs) ---

  get sucursalesBarsVM(): HorizontalBarItem[] {
    if (!this.dashboard?.por_sucursal) return [];
    // Ordenar para presentación sin mutar el array original
    return [...this.dashboard.por_sucursal]
      .sort((a, b) => Number(b.ingresos) - Number(a.ingresos))
      .map(s => ({
        etiqueta: s.sucursal_nombre,
        valor: Number(s.ingresos),
        valorFormateado: this.bs(s.ingresos),
        subtitulo: `${s.ventas} ${s.ventas === 1 ? 'venta' : 'ventas'}`
      }));
  }

  get topProductosBarsVM(): HorizontalBarItem[] {
    if (!this.dashboard?.top_productos) return [];
    return [...this.dashboard.top_productos]
      .sort((a, b) => b.unidades - a.unidades)
      .map(p => ({
        etiqueta: p.producto,
        valor: p.unidades,
        valorFormateado: `${p.unidades} un.`
      }));
  }

  get estadosPedidosSegmentosVM(): SegmentoItem[] {
    if (!this.dashboard?.estados_pedidos) return [];
    const keys = Object.keys(this.dashboard.estados_pedidos);
    return keys.map(key => {
      const valor = this.dashboard?.estados_pedidos[key] ?? 0;
      let colorClase = 'color-neutral';
      if (key === 'ENTREGADO' || key === 'RECOGIDO') colorClase = 'color-success';
      else if (key === 'CANCELADO') colorClase = 'color-danger';
      else if (key === 'SOLICITADO' || key === 'PREPARADO' || key === 'EN_REPARTO') colorClase = 'color-warning';
      return {
        etiqueta: this.etiqueta(key),
        valor,
        colorClase
      };
    });
  }

  get promocionesSegmentosVM(): SegmentoItem[] {
    if (!this.dashboard?.efectividad_promociones) return [];
    const ep = this.dashboard.efectividad_promociones;
    return [
      {
        etiqueta: 'Con promoción',
        valor: ep.con_promocion,
        colorClase: 'color-brass'
      },
      {
        etiqueta: 'Sin promoción',
        valor: ep.sin_promocion,
        colorClase: 'color-ink'
      }
    ];
  }

  get stockCriticoVM(): StockCriticoItemVM[] {
    if (!this.dashboard?.stock_critico) return [];
    return this.dashboard.stock_critico.map(item => {
      let nivel: 'agotado' | 'critico' | 'aviso' = 'aviso';
      let etiqueta = 'Bajo stock';
      if (item.disponible <= 0) {
        nivel = 'agotado';
        etiqueta = 'Agotado (0)';
      } else if (item.disponible <= 2) {
        nivel = 'critico';
        etiqueta = 'Crítico';
      }
      return {
        ...item,
        sucursalNombre: this.sucursalNombre(item.sucursal_id),
        nivelUrgencia: nivel,
        etiquetaUrgencia: etiqueta
      };
    });
  }

  get rangoConsultadoTexto(): string {
    if (this.desdeFiltro && this.hastaFiltro) {
      return `${this.desdeFiltro.replace('T', ' ')} a ${this.hastaFiltro.replace('T', ' ')}`;
    }
    if (this.desdeFiltro) {
      return `Desde ${this.desdeFiltro.replace('T', ' ')}`;
    }
    if (this.hastaFiltro) {
      return `Hasta ${this.hastaFiltro.replace('T', ' ')}`;
    }
    return 'Acumulado histórico disponible';
  }

  get ambitoTexto(): string {
    if (!this.esAdmin) {
      return `Sucursal: ${this.sucursalNombre(this.sucursalFiltro)}`;
    }
    if (this.sucursalFiltro) {
      return `Sucursal: ${this.sucursalNombre(this.sucursalFiltro)}`;
    }
    return 'Consolidado de la empresa (todas sus sucursales)';
  }

  get conversionTasaPorcentaje(): number {
    const tasa = this.num(this.dashboard?.conversion_reservas.tasa);
    return Math.round(tasa * 1000) / 10;
  }

  // --- Desglose comercial y dinero capturado E2 (CU23) ---

  get dineroCapturado(): string {
    return this.dashboard?.dinero_capturado == null ? 'No disponible' : this.bs(this.dashboard.dinero_capturado);
  }

  get ventasBrutas(): string {
    return this.bs(this.dashboard?.ventas_brutas ?? this.dashboard?.ingresos_total);
  }

  get totalDescuentos(): string {
    return this.bs(this.dashboard?.descuentos ?? '0.00');
  }

  get totalDevoluciones(): string {
    return this.bs(this.dashboard?.devoluciones ?? '0.00');
  }

  get totalReembolsos(): string {
    return this.bs(this.dashboard?.reembolsos ?? '0.00');
  }

  get netoComercial(): string {
    return this.bs(this.dashboard?.neto_comercial ?? this.dashboard?.ingresos_total);
  }

  get pedidosPendientesCumplimiento(): number {
    return this.dashboard?.pedidos_pendientes_cumplimiento ?? 0;
  }

  get montoPedidosPendientes(): string {
    return this.bs(this.dashboard?.monto_pedidos_pendientes ?? '0.00');
  }
}
