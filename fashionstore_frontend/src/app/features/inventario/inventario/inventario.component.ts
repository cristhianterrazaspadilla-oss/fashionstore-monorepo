import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { InventarioService } from '../services/inventario.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { ProductoService } from '../../catalogo/services/producto.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { MovimientoKardexDTO, ExistenciaDTO, ValorizacionDTO } from '../models/inventario.models';
import { VarianteDTO } from '../../catalogo/models/catalogo.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';

@Component({
  selector: 'app-inventario',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './inventario.component.html',
  styleUrls: ['./inventario.component.css']
})
export class InventarioComponent implements OnInit {
  tab: 'kardex' | 'existencias' | 'valorizacion' = 'kardex';

  // filtros
  sucursales: SucursalDTO[] = [];
  variantes: VarianteDTO[] = [];
  filtroSucursal = '';
  filtroVariante = '';
  filtroTipo = '';

  kardex: MovimientoKardexDTO[] = [];
  existencias: ExistenciaDTO[] = [];
  valorizacion: ValorizacionDTO[] = [];

  valorizacionTotalManual = 0;
  existenciaTotalManual = 0;

  cargando = false;
  mensajeError: string | null = null;
  tipos = [
    'RECEPCION_PROVEEDOR',
    'RESERVA',
    'LIBERACION_RESERVA',
    'COMPROMISO_TRASLADO',
    'DESPACHO_TRASLADO',
    'RECEPCION_TRASLADO',
    'VENTA_PRESENCIAL',
    'VENTA_DIGITAL',
    'DEVOLUCION',
    'MERMA',
    'AJUSTE'
  ];
  esEncargadoOCajero = false;
  sucursalFija = '';

  constructor(
    private inventarioService: InventarioService,
    private orgService: OrganizacionService,
    private productoService: ProductoService,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    const u = this.authService.obtenerUsuarioActual();
    if (u && ['ENCARGADO', 'CAJERO'].includes(u.rol)) {
      this.esEncargadoOCajero = true;
      this.sucursalFija = u.sucursal_id || '';
      this.filtroSucursal = this.sucursalFija;
      this.sucursales = u.sucursal_nombre
        ? [{ id: u.sucursal_id!, nombre: u.sucursal_nombre } as SucursalDTO]
        : [];
    } else {
      this.orgService.gestionarSucursales().subscribe({
        next: (d) => (this.sucursales = d || []),
        error: (err) => console.error('Error cargando sucursales:', err)
      });
    }

    this.productoService.gestionarVariantes().subscribe({
      next: (d) => (this.variantes = d || []),
      error: (err) => console.error('Error cargando variantes:', err)
    });

    this.cargarKardex();
    this.cargarExistencias();
    this.cargarValorizacion();
  }

  cargarKardex(): void {
    this.cargando = true;
    this.mensajeError = null;
    this.inventarioService
      .consultarKardex({
        variante_id: this.filtroVariante || undefined,
        sucursal_id: this.filtroSucursal || undefined,
        tipo: this.filtroTipo || undefined
      })
      .subscribe({
        next: (d) => {
          this.kardex = Array.isArray(d) ? d : [];
          this.cargando = false;
        },
        error: (e) => {
          this.mensajeError = formatearErrorApi(e, 'Error cargando Kardex');
          this.cargando = false;
        }
      });
  }

  cargarExistencias(): void {
    this.inventarioService.consultarExistencias(this.filtroSucursal || undefined).subscribe({
      next: (d) => {
        this.existencias = Array.isArray(d) ? d : [];
      },
      error: (err) => {
        console.error('Error cargando existencias:', err);
        this.existencias = [];
      }
    });
  }

  cargarValorizacion(): void {
    this.inventarioService.consultarValorizacion(this.filtroSucursal || undefined).subscribe({
      next: (d) => {
        if (Array.isArray(d)) {
          this.valorizacion = d;
          this.valorizacionTotalManual = d.reduce((s, v) => s + Number(v.valorizacion || 0), 0);
          this.existenciaTotalManual = d.reduce(
            (s, v) => s + Number(v.total_existencia || 0),
            0
          );
        } else if (d && typeof d === 'object') {
          const arr: ValorizacionDTO[] = (d.por_sucursal || []).map((x) => ({
            ...x,
            total_existencia: x.total_existencia ?? 0
          }));
          this.valorizacion = arr;
          this.valorizacionTotalManual = Number(
            d.global?.valorizacion ?? arr.reduce((s: number, v: ValorizacionDTO) => s + Number(v.valorizacion || 0), 0)
          );
          this.existenciaTotalManual = Number(
            d.global?.total_unidades ?? arr.reduce((s: number, v: ValorizacionDTO) => s + Number(v.total_existencia || 0), 0)
          );
        } else {
          this.valorizacion = [];
          this.valorizacionTotalManual = 0;
          this.existenciaTotalManual = 0;
        }
      },
      error: (err) => {
        console.error('Error cargando valorización:', err);
        this.valorizacion = [];
        this.valorizacionTotalManual = 0;
        this.existenciaTotalManual = 0;
      }
    });
  }

  aplicarFiltros(): void {
    this.cargarKardex();
    this.cargarExistencias();
    this.cargarValorizacion();
  }

  limpiar(): void {
    this.filtroSucursal = this.esEncargadoOCajero ? this.sucursalFija : '';
    this.filtroVariante = '';
    this.filtroTipo = '';
    this.aplicarFiltros();
  }

  get totalValorizacion(): number {
    return this.valorizacionTotalManual;
  }

  get totalExistencia(): number {
    return this.existenciaTotalManual;
  }

  get totalFisico(): number {
    return this.existencias.reduce((s, e) => s + (e.fisico ?? e.existencia_total ?? 0), 0);
  }

  get totalLibre(): number {
    return this.existencias.reduce((s, e) => s + (e.libre ?? e.disponible ?? 0), 0);
  }

  get totalReservado(): number {
    return this.existencias.reduce((s, e) => s + (e.reservado ?? 0), 0);
  }

  get totalCupoOffline(): number {
    return this.existencias.reduce((s, e) => s + (e.cupo_offline ?? e.comprometido_caja ?? 0), 0);
  }

  tipoClass(t: string): string {
    if (t === 'RECEPCION_PROVEEDOR') return 't-rec';
    if (t.startsWith('VENTA')) return 't-venta';
    if (t.includes('TRASLADO')) return 't-tras';
    if (t === 'MERMA') return 't-merma';
    return 't-def';
  }

  etiquetaTipoKardex(tipo: string): string {
    const mapa: Record<string, string> = {
      RECEPCION_PROVEEDOR: 'Recepción de proveedor',
      RESERVA: 'Reserva',
      LIBERACION_RESERVA: 'Liberación de reserva',
      COMPROMISO_TRASLADO: 'Compromiso de traslado',
      DESPACHO_TRASLADO: 'Despacho de traslado',
      RECEPCION_TRASLADO: 'Recepción de traslado',
      VENTA_PRESENCIAL: 'Venta presencial',
      VENTA_DIGITAL: 'Venta online',
      DEVOLUCION: 'Devolución',
      MERMA: 'Merma',
      AJUSTE: 'Ajuste de inventario'
    };
    return mapa[tipo] || tipo;
  }

  formatearReferencia(ref?: string): string {
    if (!ref) return '—';
    const mapa: Record<string, string> = {
      RECEPCION_PROVEEDOR: 'Lote de proveedor',
      RESERVA: 'Reserva de cliente',
      TRASLADO: 'Traslado de sucursal',
      VENTA: 'Venta en tienda',
      VENTA_DIGITAL: 'Venta online',
      VENTA_PRESENCIAL: 'Venta en tienda',
      DEVOLUCION: 'Devolución de prenda',
      MERMA: 'Merma de inventario',
      AJUSTE: 'Ajuste de stock'
    };
    return mapa[ref] || ref;
  }
}
