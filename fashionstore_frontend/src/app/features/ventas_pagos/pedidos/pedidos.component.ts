import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EntregaService } from '../services/entrega.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { PedidoDTO, SiguienteEstadoPedido } from '../models/venta-digital.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';
import { formatearBs, formatearFechaHora, type DecimalApi } from '../../../core/utils/moneda.util';
import { etiquetaEstado, claseEstado } from '../../../core/utils/estado-mapper.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';

@Component({
  selector: 'app-pedidos',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pedidos.component.html',
  styleUrls: ['./pedidos.component.css']
})
export class PedidosComponent implements OnInit {
  pedidos: PedidoDTO[] = [];
  total = 0;
  limit = 10;
  offset = 0;
  sucursales: SucursalDTO[] = [];
  sucursalFiltro = '';
  estadoFiltro = '';
  cargando = true;
  error: string | null = null;
  exito: string | null = null;
  operando: Record<string, boolean> = {};
  esAdmin = false;
  sucursalUsuario: string | null = null;
  private readonly destroyRef = inject(DestroyRef);

  readonly ESTADOS_FILTRO = ['SOLICITADO', 'PREPARADO', 'LISTO_RECOJO', 'EN_REPARTO', 'RECOGIDO', 'ENTREGADO', 'CANCELADO'];

  constructor(
    private entregaService: EntregaService,
    private orgService: OrganizacionService,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    const u = this.authService.obtenerUsuarioActual();
    this.esAdmin = u?.rol === 'ADMINISTRADOR';
    this.sucursalUsuario = u?.sucursal_id ?? null;
    if (!this.esAdmin && this.sucursalUsuario) this.sucursalFiltro = this.sucursalUsuario;

    this.orgService.gestionarSucursales().subscribe(s => this.sucursales = s);
    this.cargar();
  }

  cambiarFiltro(): void {
    this.offset = 0;
    this.cargar();
  }

  cargar(): void {
    this.cargando = true;
    this.error = null;
    this.entregaService.cola({
      sucursal_id: this.sucursalFiltro || undefined,
      estado: this.estadoFiltro || undefined,
      limit: this.limit,
      offset: this.offset
    }).pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: r => { this.pedidos = r.items; this.total = r.total; this.cargando = false; },
        error: e => { this.error = formatearErrorApi(e); this.cargando = false; }
      });
  }

  siguienteEstado(p: PedidoDTO): SiguienteEstadoPedido | null {
    return p.siguiente_estado ?? null;
  }

  puedeAvanzar(p: PedidoDTO): boolean {
    return !!p.puede_transicionar && !!p.siguiente_estado && !this.operando[p.id];
  }

  get paginaActual(): number {
    return Math.floor(this.offset / this.limit) + 1;
  }

  get totalPaginas(): number {
    return Math.max(1, Math.ceil(this.total / this.limit));
  }

  get rangoInicio(): number {
    return this.total === 0 ? 0 : this.offset + 1;
  }

  get rangoFin(): number {
    return Math.min(this.offset + this.limit, this.total);
  }

  paginaAnterior(): void {
    if (this.offset >= this.limit) {
      this.offset -= this.limit;
      this.cargar();
    }
  }

  paginaSiguiente(): void {
    if (this.offset + this.limit < this.total) {
      this.offset += this.limit;
      this.cargar();
    }
  }

  avanzar(p: PedidoDTO): void {
    const sig = this.siguienteEstado(p);
    if (!sig || !p.puede_transicionar || this.operando[p.id]) return;
    this.operando[p.id] = true;
    this.exito = null;
    this.entregaService.transicionar(p.id, sig).subscribe({
      next: () => {
        this.operando[p.id] = false;
        this.exito = `Pedido avanzado a "${etiquetaEstado(sig)}".`;
        this.cargar();
      },
      error: e => {
        this.error = formatearErrorApi(e, 'No se pudo avanzar el pedido. Verifica que el estado no haya cambiado.');
        this.operando[p.id] = false;
        this.cargar();
      }
    });
  }

  sucursalNombre(id: string): string {
    return this.sucursales.find(s => s.id === id)?.nombre ?? 'No disponible';
  }
  etiqueta(e: string): string { return etiquetaEstado(e); }
  clase(e: string): string { return claseEstado(e); }
  bs(m: DecimalApi | null | undefined): string { return formatearBs(m); }
  fh(f: string): string { return formatearFechaHora(f); }
}
