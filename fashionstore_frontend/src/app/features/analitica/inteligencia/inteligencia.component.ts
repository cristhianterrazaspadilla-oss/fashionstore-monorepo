import { Component, DestroyRef, inject, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { IAAnaliticaService } from '../services/ia-analitica.service';
import {
  ReporteRespuestaDTO,
  DecisionRespuestaDTO,
  DecisionItemDTO,
  TipoReportePermitido,
  ReporteInterpretadoResultadoDTO,
  PronosticoDemandaResultadoDTO,
  SegmentacionProductosResultadoDTO,
  OrigenDatosML
} from '../models/analitica-ia.models';
import { entradaLocalIso, formatearBs, type DecimalApi } from '../../../core/utils/moneda.util';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';
import { etiquetaEstado, claseEstado } from '../../../core/utils/estado-mapper.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import { RadialProgressComponent } from '../../../shared/data-viz/radial-progress/radial-progress.component';
import { HorizontalBarsComponent, HorizontalBarItem } from '../../../shared/data-viz/horizontal-bars/horizontal-bars.component';
import { SegmentedBarComponent, SegmentoItem } from '../../../shared/data-viz/segmented-bar/segmented-bar.component';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { DictadoReporte } from './dictado-reporte';
import { archivoReporte, descargarReporte, FormatoReporte } from './exportar-reporte';

export interface InventarioSucursalReporteVM {
  sucursal: string;
  variantes: number;
  disponible: number;
  reservado: number;
  en_transito: number;
  segmentos: SegmentoItem[];
}

export interface RotacionFilaVM {
  varianteId: string;
  etiquetaLegible: string;
  stock: number;
  ventas: number;
  stockPct: number;
  ventasPct: number;
}

export interface DecisionItemVM extends DecisionItemDTO {
  stockPct: number;
  ventasPct: number;
}

@Component({
  selector: 'app-inteligencia',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RadialProgressComponent,
    HorizontalBarsComponent,
    SegmentedBarComponent
  ],
  templateUrl: './inteligencia.component.html',
  styleUrls: ['./inteligencia.component.css']
})
export class InteligenciaComponent implements OnInit, OnDestroy {
  activeTab: 'reportes' | 'decisiones' = 'reportes';
  subTab: 'reportes' | 'pronostico' | 'segmentacion' = 'reportes';

  // CU24: Reportes interpretados tipados
  consulta = '';
  reporte: ReporteRespuestaDTO | null = null;
  reporteTipado: ReporteInterpretadoResultadoDTO | null = null;
  generando = false;
  errorReporte: string | null = null;
  escuchando = false;
  errorVoz = '';
  errorExportacion = '';
  exportando = false;
  private propietarioReporte = '';
  private secuenciaReporte = 0;
  private readonly auth = inject(AuthService);
  readonly dictado = new DictadoReporte(texto => this.consulta = texto,
    (escuchando, error) => { this.escuchando = escuchando; this.errorVoz = error; });
  tipoSeleccionado?: TipoReportePermitido;
  sucursalesReporte: SucursalDTO[] = [];
  sucursalReporte = '';
  desdeReporte = '';
  hastaReporte = '';
  errorSucursales: string | null = null;

  tiposPermitidos: { id: TipoReportePermitido; label: string; desc: string }[] = [
    { id: 'VENTAS_POR_SUCURSAL', label: 'Ventas por sucursal', desc: 'Consolidado de ingresos y unidades por punto de venta' },
    { id: 'RANKING_PRODUCTOS', label: 'Ranking de productos', desc: 'Prendas más vendidas con ingresos totales' },
    { id: 'EVOLUCION_SEMANAL', label: 'Evolución semanal', desc: 'Serie temporal de transacciones e ingresos por semana' },
    { id: 'INGRESOS_POR_CATEGORIA', label: 'Ingresos por categoría', desc: 'Distribución de ventas por familias del catálogo' }
  ];

  // Secuencia de carga textual intencional
  readonly pasosCarga = [
    'Interpretando consulta',
    'Consultando datos autorizados',
    'Preparando lectura del negocio'
  ];
  pasoCargaActual = 0;
  private intervaloCarga: any = null;

  // CU10: Pronóstico supervisado de demanda
  pronostico: PronosticoDemandaResultadoDTO | null = null;
  pronosticoSemanas = 4;
  pronosticoOrigen: OrigenDatosML = 'AUTO';
  pronosticoSemilla = 42;
  consultandoPronostico = false;
  errorPronostico: string | null = null;

  // CU11: Segmentación no supervisada de productos
  segmentacion: SegmentacionProductosResultadoDTO | null = null;
  segmentacionGrupos = 4;
  segmentacionPeriodo = 60;
  segmentacionOrigen: OrigenDatosML = 'AUTO';
  segmentacionSemilla = 42;
  consultandoSegmentacion = false;
  errorSegmentacion: string | null = null;

  // Decisiones
  diasVentana = 30;
  umbralRotacion = 5;
  decisiones: DecisionRespuestaDTO | null = null;
  consultando = false;
  errorDecision: string | null = null;

  private readonly destroyRef = inject(DestroyRef);
  private readonly organizacionService = inject(OrganizacionService);

  constructor(private iaService: IAAnaliticaService) {}

  ngOnInit(): void {
    let identidad = this.identidadActual();
    this.auth.usuario$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      const actual = this.identidadActual();
      if (actual !== identidad) { this.invalidarReporte(); this.dictado.destruir(); identidad = actual; }
    });
    this.organizacionService.gestionarSucursales(undefined, false)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: sucursales => this.sucursalesReporte = sucursales,
        error: e => this.errorSucursales = formatearErrorApi(e, 'No se pudieron consultar las sucursales autorizadas.')
      });
  }

  ngOnDestroy(): void {
    this.invalidarReporte();
    this.dictado.destruir();
    this.limpiarIntervaloCarga();
  }

  private identidadActual(): string {
    const u = this.auth.obtenerUsuarioActual();
    return u?.empresa_id && u.id ? `${u.empresa_id}:${u.id}` : '';
  }
  private invalidarReporte(): void {
    this.secuenciaReporte++; this.propietarioReporte = ''; this.reporte = null; this.reporteTipado = null;
    this.errorExportacion = ''; this.generando = false; this.limpiarIntervaloCarga();
  }
  alternarDictado(): void { if (this.escuchando) this.dictado.detener(); else this.dictado.iniciar(this.consulta); }
  get exportacionDisponible(): boolean {
    return !!this.reporteTipado && !this.generando && !this.errorReporte &&
      !!this.propietarioReporte && this.propietarioReporte === this.identidadActual();
  }

  get tituloReporte(): string {
    if (this.reporteTipado) {
      const titulosTipados: Record<TipoReportePermitido, string> = {
        VENTAS_POR_SUCURSAL: 'Ventas por sucursal',
        RANKING_PRODUCTOS: 'Ranking de prendas más vendidas',
        EVOLUCION_SEMANAL: 'Evolución semanal de ventas',
        INGRESOS_POR_CATEGORIA: 'Ingresos por categoría'
      };
      return titulosTipados[this.reporteTipado.tipo_reporte] || 'Reporte interpretado';
    }
    const titulos: Record<string, string> = {
      ventasPorSucursal: 'Ventas por sucursal',
      inventarioPorSucursal: 'Inventario por sucursal',
      ventasPorTemporada: 'Ventas por temporada',
      stockCritico: 'Stock crítico',
      topVendidos: 'Productos más vendidos',
      efectividadReservas: 'Efectividad de reservas',
      rotacionPorTemporada: 'Rotación de inventario'
    };
    return this.reporte ? (titulos[this.reporte.funcion_usada] ?? 'Reporte de analítica') : '';
  }

  get nombreProveedor(): string {
    if (this.reporteTipado) {
      const p = String(this.reporteTipado.filtros_efectivos?.['proveedor'] || this.reporteTipado.proveedor || '').toUpperCase();
      return p.includes('GEMINI') ? 'Gemini analítico' : 'Motor determinista local';
    }
    if (!this.reporte?.proveedor) return 'Motor analítico seguro';
    return this.reporte.proveedor === 'GEMINI' ? 'Gemini analítico' : 'Motor determinista local';
  }

  get esProveedorGemini(): boolean {
    return this.nombreProveedor.includes('Gemini');
  }

  // --- CU24: Ejecutar reporte tipado o generativo ---
  ejecutarReporteTipado(tipo?: TipoReportePermitido): void {
    this.dictado.detener();
    this.invalidarReporte();
    const secuencia = this.secuenciaReporte, propietario = this.identidadActual();
    if (!propietario) { this.errorReporte = 'Se requiere una sesión empresarial vigente.'; return; }
    const textoConsulta = this.consulta.trim() || (tipo ? `Reporte de ${tipo.toLowerCase().replace(/_/g, ' ')}` : 'ventas por sucursal');
    this.generando = true;
    this.errorReporte = null;
    this.reporte = null;
    this.reporteTipado = null;
    this.iniciarSecuenciaCarga();

    this.iaService.solicitarReporteInterpretado({
      consulta: textoConsulta,
      tipo_reporte: tipo,
      sucursal_id: this.sucursalReporte || undefined,
      desde: entradaLocalIso(this.desdeReporte),
      hasta: entradaLocalIso(this.hastaReporte)
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: r => {
          if (secuencia !== this.secuenciaReporte || propietario !== this.identidadActual()) return;
          this.reporteTipado = r;
          this.propietarioReporte = propietario;
          this.generando = false;
          this.limpiarIntervaloCarga();
        },
        error: e => {
          if (secuencia !== this.secuenciaReporte) return;
          this.reporteTipado = null; this.propietarioReporte = '';
          this.errorReporte = formatearErrorApi(e, 'No se pudo generar el reporte solicitado.');
          this.generando = false;
          this.limpiarIntervaloCarga();
        }
      });
  }

  generarReporte(): void {
    if (this.escuchando) { this.dictado.detener(); return; }
    if (!this.consulta.trim() || this.generando) return;
    const consulta = this.consulta.trim();
    if (/(inventario|stock|existencia|agot|reserva)/i.test(consulta)) {
      this.invalidarReporte();
      const secuencia = this.secuenciaReporte, propietario = this.identidadActual();
      if (this.sucursalReporte || this.desdeReporte || this.hastaReporte) {
        this.errorReporte = 'Los reportes legados de inventario y reservas consultan el ámbito completo de la empresa. Usa el dashboard para filtros de sucursal o período.';
        return;
      }
      this.generando = true;
      this.errorReporte = null;
      this.reporte = null;
      this.reporteTipado = null;
      this.iniciarSecuenciaCarga();
      this.iaService.generarReporte(consulta).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: r => { if (secuencia !== this.secuenciaReporte || propietario !== this.identidadActual()) return; this.reporte = r; this.generando = false; this.limpiarIntervaloCarga(); },
        error: e => {
          if (secuencia !== this.secuenciaReporte) return;
          this.errorReporte = formatearErrorApi(e, 'No se pudo consultar el reporte legado.');
          this.generando = false;
          this.limpiarIntervaloCarga();
        }
      });
      return;
    }
    this.ejecutarReporteTipado();
  }

  exportarCsv(): void { void this.exportar('csv'); }
  async exportar(formato: FormatoReporte): Promise<void> {
    if (!this.exportacionDisponible || this.exportando || !this.reporteTipado) return;
    this.exportando = true; this.errorExportacion = '';
    const propietario = this.propietarioReporte, secuencia = this.secuenciaReporte;
    const resultado = JSON.parse(JSON.stringify(this.reporteTipado)) as ReporteInterpretadoResultadoDTO;
    const titulo = this.tituloReporte;
    try {
      const blob = await archivoReporte(resultado, titulo, formato);
      if (!this.exportacionDisponible || propietario !== this.identidadActual() || secuencia !== this.secuenciaReporte) return;
      descargarReporte(blob, 'reporte_' + resultado.tipo_reporte.toLowerCase() + '.' + formato);
    } catch { this.errorExportacion = 'No se pudo exportar este resultado. Vuelve a consultar o inténtalo de nuevo.'; }
    finally { this.exportando = false; }
  }

  // --- CU10: Pronóstico Supervisado de Demanda ---
  consultarPronostico(): void {
    this.pronostico = null;
    this.consultandoPronostico = true;
    this.errorPronostico = null;

    this.iaService.consultarPronosticos({
      semanas_adelante: this.pronosticoSemanas,
      origen_datos: this.pronosticoOrigen,
      semilla: this.pronosticoSemilla
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.pronostico = res;
          this.consultandoPronostico = false;
        },
        error: e => {
          this.errorPronostico = formatearErrorApi(e, 'No se pudo obtener el pronóstico de demanda.');
          this.consultandoPronostico = false;
        }
      });
  }

  entrenarPronostico(): void {
    this.pronostico = null;
    this.consultandoPronostico = true;
    this.errorPronostico = null;

    this.iaService.entrenarSupervisado({
      semanas_adelante: this.pronosticoSemanas,
      origen_datos: this.pronosticoOrigen,
      semilla: this.pronosticoSemilla
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.pronostico = res;
          this.consultandoPronostico = false;
        },
        error: e => {
          this.errorPronostico = formatearErrorApi(e, 'No se pudo entrenar el modelo de pronóstico.');
          this.consultandoPronostico = false;
        }
      });
  }

  // --- CU11: Segmentación No Supervisada de Productos ---
  consultarSegmentacion(): void {
    this.segmentacion = null;
    this.consultandoSegmentacion = true;
    this.errorSegmentacion = null;

    this.iaService.consultarSegmentacion({
      num_grupos: this.segmentacionGrupos,
      periodo_dias: this.segmentacionPeriodo,
      origen_datos: this.segmentacionOrigen,
      semilla: this.segmentacionSemilla
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.segmentacion = res;
          this.consultandoSegmentacion = false;
        },
        error: e => {
          this.errorSegmentacion = formatearErrorApi(e, 'No se pudo obtener la segmentación de productos.');
          this.consultandoSegmentacion = false;
        }
      });
  }

  entrenarSegmentacion(): void {
    this.segmentacion = null;
    this.consultandoSegmentacion = true;
    this.errorSegmentacion = null;

    this.iaService.entrenarNoSupervisado({
      num_grupos: this.segmentacionGrupos,
      periodo_dias: this.segmentacionPeriodo,
      origen_datos: this.segmentacionOrigen,
      semilla: this.segmentacionSemilla
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: res => {
          this.segmentacion = res;
          this.consultandoSegmentacion = false;
        },
        error: e => {
          this.errorSegmentacion = formatearErrorApi(e, 'No se pudo entrenar la segmentación.');
          this.consultandoSegmentacion = false;
        }
      });
  }

  // --- View Models para compatibilidad legada ---
  get ventasPorSucursalBarsVM(): HorizontalBarItem[] {
    const filas = this.reporte?.datos['por_sucursal'];
    if (!Array.isArray(filas)) return [];
    return filas.filter(this.esRegistro).map(fila => ({
      etiqueta: String(fila['sucursal'] ?? 'Sucursal'),
      valor: Number(fila['ingresos'] ?? 0),
      valorFormateado: this.bs(fila['ingresos'] as DecimalApi),
      subtitulo: `${fila['ventas'] ?? 0} ventas confirmadas`
    }));
  }

  get inventarioPorSucursalVM(): InventarioSucursalReporteVM[] {
    const filas = this.reporte?.datos['inventario_por_sucursal'];
    if (!Array.isArray(filas)) return [];
    return filas.filter(this.esRegistro).map(fila => {
      const sucursal = String(fila['sucursal'] ?? 'Sucursal');
      const variantes = Number(fila['variantes'] ?? 0);
      const disponible = Number(fila['disponible'] ?? 0);
      const reservado = Number(fila['reservado'] ?? 0);
      const en_transito = Number(fila['en_transito'] ?? 0);

      const segmentos: SegmentoItem[] = [
        { etiqueta: 'Disponible', valor: disponible, colorClase: 'color-success' },
        { etiqueta: 'Reservado', valor: reservado, colorClase: 'color-brass' },
        { etiqueta: 'En tránsito', valor: en_transito, colorClase: 'color-warning' }
      ];

      return {
        sucursal,
        variantes,
        disponible,
        reservado,
        en_transito,
        segmentos
      };
    });
  }

  get temporadasVM(): string[] {
    const temps = this.reporte?.datos['temporadas'];
    return Array.isArray(temps) ? temps.map(String) : [];
  }

  get stockCriticoBarsVM(): HorizontalBarItem[] {
    const filas = this.reporte?.datos['criticos'];
    if (!Array.isArray(filas)) return [];
    return filas.filter(this.esRegistro).map(fila => {
      const disp = Number(fila['disponible'] ?? 0);
      let nivel: 'urgente' | 'critico' | 'normal' = 'normal';
      let valorFormateado = `${disp} un.`;
      if (disp <= 0) {
        nivel = 'urgente';
        valorFormateado = '0 un. (Agotado)';
      } else if (disp <= 2) {
        nivel = 'critico';
        valorFormateado = `${disp} un. (Crítico)`;
      }

      return {
        etiqueta: String(fila['sku'] ?? 'SKU'),
        valor: disp,
        valorFormateado,
        nivel
      };
    });
  }

  get topVendidosBarsVM(): HorizontalBarItem[] {
    const filas = this.reporte?.datos['top'];
    if (!Array.isArray(filas)) return [];
    return filas.filter(this.esRegistro).map(fila => ({
      etiqueta: String(fila['sku'] ?? 'SKU'),
      valor: Number(fila['unidades'] ?? 0),
      valorFormateado: `${fila['unidades'] ?? 0} un.`
    }));
  }

  get reservasReporteVM(): { total: number; completadas: number; conversionPct: number } {
    const d = this.reporte?.datos ?? {};
    const total = Number(d['total'] ?? 0);
    const completadas = Number(d['completadas'] ?? 0);
    const conversion = Number(d['conversion'] ?? 0);
    return {
      total,
      completadas,
      conversionPct: Math.round(conversion * 1000) / 10
    };
  }

  get rotacionFilasVM(): { ventanaDias: number; filas: RotacionFilaVM[] } {
    const d = this.reporte?.datos ?? {};
    const ventanaDias = Number(d['ventana_dias'] ?? 30);
    const filas = Array.isArray(d['filas']) ? d['filas'].filter(this.esRegistro) : [];

    const vmFilas: RotacionFilaVM[] = filas.map((fila, i) => {
      const vid = String(fila['variante_id'] ?? '');
      const stock = Number(fila['stock'] ?? 0);
      const ventas = Number(fila['ventas'] ?? 0);
      const max = Math.max(stock, ventas, 1);
      return {
        varianteId: vid,
        etiquetaLegible: `Ítem de catálogo #${i + 1} (${vid.slice(0, 8)})`,
        stock,
        ventas,
        stockPct: Math.min(100, Math.round((stock / max) * 100)),
        ventasPct: Math.min(100, Math.round((ventas / max) * 100))
      };
    });

    return { ventanaDias, filas: vmFilas };
  }

  get esFuncionDesconocida(): boolean {
    if (!this.reporte) return false;
    const conocidas = [
      'ventasPorSucursal',
      'inventarioPorSucursal',
      'ventasPorTemporada',
      'stockCritico',
      'topVendidos',
      'efectividadReservas',
      'rotacionPorTemporada'
    ];
    return !conocidas.includes(this.reporte.funcion_usada);
  }

  get reporteVacio(): boolean {
    if (this.reporteTipado) {
      return !this.reporteTipado.filas || this.reporteTipado.filas.length === 0;
    }
    if (!this.reporte?.datos) return true;
    const d = this.reporte.datos;
    if (d['total'] === 0) return true;
    if (Array.isArray(d['por_sucursal']) && d['por_sucursal'].length === 0) return true;
    if (Array.isArray(d['inventario_por_sucursal']) && d['inventario_por_sucursal'].length === 0) return true;
    if (Array.isArray(d['temporadas']) && d['temporadas'].length === 0) return true;
    if (Array.isArray(d['criticos']) && d['criticos'].length === 0) return true;
    if (Array.isArray(d['top']) && d['top'].length === 0) return true;
    if (Array.isArray(d['filas']) && d['filas'].length === 0) return true;
    return false;
  }

  get decisionesVM(): DecisionItemVM[] {
    if (!this.decisiones?.items) return [];
    return this.decisiones.items.map(d => {
      const max = Math.max(d.stock_total, d.ventas_periodo, 1);
      return {
        ...d,
        stockPct: Math.min(100, Math.round((d.stock_total / max) * 100)),
        ventasPct: Math.min(100, Math.round((d.ventas_periodo / max) * 100))
      };
    });
  }

  consultarDecisiones(): void {
    if (this.consultando) return;
    this.consultando = true;
    this.errorDecision = null;
    this.decisiones = null;

    this.iaService.decisionesInventario({ dias_ventana: this.diasVentana, umbral_rotacion: this.umbralRotacion })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: d => {
          this.decisiones = d;
          this.consultando = false;
        },
        error: e => {
          this.errorDecision = formatearErrorApi(e, 'No se pudieron obtener decisiones.');
          this.consultando = false;
        }
      });
  }

  private iniciarSecuenciaCarga(): void {
    this.limpiarIntervaloCarga();
    this.pasoCargaActual = 0;
    this.intervaloCarga = setInterval(() => {
      if (this.pasoCargaActual < this.pasosCarga.length - 1) {
        this.pasoCargaActual++;
      }
    }, 1100);
  }

  private limpiarIntervaloCarga(): void {
    if (this.intervaloCarga) {
      clearInterval(this.intervaloCarga);
      this.intervaloCarga = null;
    }
  }

  private esRegistro(valor: unknown): valor is Record<string, unknown> {
    return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
  }

  accionIcono(accion: string): string {
    const m: Record<string, string> = {
      PROMOCION: '🏷️',
      LIQUIDACION: '📉',
      TRASLADO: '🚚',
      REPOSICION: '📦',
      MANTENER: '✓'
    };
    return m[accion] ?? '•';
  }

  etiqueta(e: string): string { return etiquetaEstado(e); }
  clase(e: string): string { return claseEstado(e); }
  bs(m: DecimalApi | number | null | undefined): string { return formatearBs(m); }

  formatearEncabezadoColumna(col: string): string {
    return (col || '').replace(/_bob/gi, '').replace(/_/g, ' ').toUpperCase();
  }

  esColumnaMonetaria(col: string): boolean {
    const c = (col || '').toLowerCase();
    if (c.includes('ventas') || c.includes('unidades') || c.includes('cantidad')) return false;
    return c.includes('ingresos') || c.includes('monto') || c.includes('total') || c.includes('subtotal') || c.includes('precio');
  }

  formatearMonto(val: unknown): string {
    const n = Number(val);
    return isNaN(n) ? '0.00' : n.toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
}
