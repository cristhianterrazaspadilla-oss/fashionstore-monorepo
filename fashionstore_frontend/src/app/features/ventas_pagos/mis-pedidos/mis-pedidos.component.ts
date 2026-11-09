import { Component, OnInit, OnDestroy, DestroyRef, HostListener, ViewChild, ElementRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterLink, ActivatedRoute } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { map, distinctUntilChanged, switchMap, of, catchError } from 'rxjs';
import { EntregaService } from '../services/entrega.service';
import { PedidoDTO } from '../models/venta-digital.models';
import { formatearBs, formatearFechaHora, type DecimalApi } from '../../../core/utils/moneda.util';
import { etiquetaEstado, claseEstado } from '../../../core/utils/estado-mapper.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import { ConfirmDialogComponent } from '../../../shared/confirm-dialog/confirm-dialog.component';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  atraparFocoModal,
  enfocarPrimerElemento,
  devolverFocoDisparador
} from '../../../core/utils/modal-accessibility.util';

@Component({
  selector: 'app-mis-pedidos',
  standalone: true,
  imports: [CommonModule, RouterLink, ConfirmDialogComponent],
  templateUrl: './mis-pedidos.component.html',
  styleUrls: ['./mis-pedidos.component.css']
})
export class MisPedidosComponent implements OnInit, OnDestroy {
  pedidos: PedidoDTO[] = [];
  total = 0;
  limit = 10;
  offset = 0;
  cargando = true;
  error: string | null = null;
  detalle: PedidoDTO | null = null;
  cargandoDetalle = false;
  errorDetalle: string | null = null;
  cancelando = false;
  idParaCancelar: string | null = null;
  mostrarConfirmacionCancelar = false;

  private triggerElement: HTMLElement | null = null;
  private modalAbierto = false;
  private readonly destroyRef = inject(DestroyRef);

  @ViewChild('modalDetalleBox') modalDetalleBox?: ElementRef<HTMLElement>;

  constructor(
    private entregaService: EntregaService,
    private route: ActivatedRoute,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.cargar();
    this.route.paramMap
      .pipe(
        map(params => params.get('id')),
        distinctUntilChanged(),
        switchMap(id => {
          if (!id) {
            if (this.cancelando) {
              return of(null);
            }
            this.cerrarDetalleLocal();
            return of(null);
          }
          this.cargandoDetalle = true;
          this.errorDetalle = null;
          this.detalle = null;
          this.abrirModalAccesible();
          return this.entregaService.obtener(id).pipe(
            catchError(e => {
              this.cargandoDetalle = false;
              this.errorDetalle = formatearErrorApi(e, 'No se pudo cargar el pedido solicitado.');
              this.abrirModalAccesible();
              return of(null);
            })
          );
        }),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe(p => {
        if (p) {
          this.detalle = p;
          this.cargandoDetalle = false;
          this.errorDetalle = null;
          this.abrirModalAccesible();
        }
      });
  }

  ngOnDestroy(): void {
    if (this.modalAbierto) {
      desbloquearScrollBody();
      this.modalAbierto = false;
    }
  }

  @HostListener('keydown.escape')
  alPresionarEscape(): void {
    if (this.cancelando) return;
    if (this.mostrarConfirmacionCancelar) {
      this.cerrarConfirmacionCancelar();
      return;
    }
    if (this.detalle || this.cargandoDetalle || this.errorDetalle) {
      this.cerrarDetalle();
    }
  }

  alManejarTabModal(event: KeyboardEvent): void {
    if (this.modalDetalleBox) {
      atraparFocoModal(event, this.modalDetalleBox.nativeElement);
    }
  }

  cargar(): void {
    this.cargando = true;
    this.error = null;
    this.entregaService.misPedidos(this.limit, this.offset)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: r => {
          this.pedidos = r.items;
          this.total = r.total;
          this.cargando = false;
        },
        error: e => {
          this.error = formatearErrorApi(e, 'No se pudieron cargar tus pedidos.');
          this.cargando = false;
        }
      });
  }

  verDetalle(p: PedidoDTO, event?: Event): void {
    this.triggerElement = (event?.currentTarget as HTMLElement) || (document.activeElement as HTMLElement);
    this.router.navigate(['/mis-pedidos', p.id]);
  }

  private abrirModalAccesible(): void {
    if (!this.modalAbierto) {
      bloquearScrollBody();
      this.modalAbierto = true;
    }
    setTimeout(() => {
      if (this.modalDetalleBox) {
        enfocarPrimerElemento(this.modalDetalleBox.nativeElement);
      }
    }, 50);
  }

  cerrarDetalle(): void {
    if (this.cancelando) return;
    if (this.mostrarConfirmacionCancelar) {
      this.cerrarConfirmacionCancelar();
      return;
    }
    this.router.navigate(['/mis-pedidos']);
  }

  private cerrarDetalleLocal(): void {
    this.detalle = null;
    this.cargandoDetalle = false;
    this.errorDetalle = null;
    this.mostrarConfirmacionCancelar = false;
    this.idParaCancelar = null;
    if (this.modalAbierto) {
      desbloquearScrollBody();
      this.modalAbierto = false;
    }
    devolverFocoDisparador(this.triggerElement);
    this.triggerElement = null;
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

  solicitarCancelacion(id: string): void {
    this.idParaCancelar = id;
    this.mostrarConfirmacionCancelar = true;
  }

  cerrarConfirmacionCancelar(): void {
    this.mostrarConfirmacionCancelar = false;
    this.idParaCancelar = null;
  }

  confirmarCancelacion(): void {
    if (!this.idParaCancelar || this.cancelando) return;
    const id = this.idParaCancelar;
    this.cancelando = true;
    this.entregaService.cancelar(id).subscribe({
      next: p => {
        this.cancelando = false;
        this.mostrarConfirmacionCancelar = false;
        this.idParaCancelar = null;
        if (this.detalle?.id === id) {
          this.detalle = p;
        }
        this.cargar();
      },
      error: e => {
        this.error = formatearErrorApi(e, 'No se pudo cancelar el pedido.');
        this.cancelando = false;
        this.mostrarConfirmacionCancelar = false;
      }
    });
  }

  puedeCancelar(p: PedidoDTO): boolean {
    return !!p.puede_cancelar;
  }

  private readonly ORDEN_RECOJO = ['SOLICITADO', 'PREPARADO', 'LISTO_RECOJO', 'RECOGIDO'];
  private readonly ORDEN_DELIVERY = ['SOLICITADO', 'PREPARADO', 'EN_REPARTO', 'ENTREGADO'];

  esStepActivo(estadoActual: string, step: string): boolean {
    return estadoActual === step;
  }

  esStepCompletado(estadoActual: string, step: string): boolean {
    const orden = this.ORDEN_RECOJO.includes(estadoActual) || !this.ORDEN_DELIVERY.includes(estadoActual) ? this.ORDEN_RECOJO : this.ORDEN_DELIVERY;
    return orden.indexOf(estadoActual) > orden.indexOf(step);
  }

  etiqueta(e: string): string {
    return etiquetaEstado(e);
  }

  clase(e: string): string {
    return claseEstado(e);
  }

  bs(m: DecimalApi | null | undefined): string {
    return formatearBs(m);
  }

  fh(f: string): string {
    return formatearFechaHora(f);
  }
}
