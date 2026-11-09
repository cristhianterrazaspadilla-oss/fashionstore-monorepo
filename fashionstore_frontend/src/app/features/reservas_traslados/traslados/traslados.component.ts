import { CommonModule } from '@angular/common';
import { Component, OnInit, OnDestroy, ViewChild, ElementRef, HostListener } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { ReservaTrasladoService } from '../services/reserva-traslado.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { EstadoTraslado, Traslado } from '../models/reserva-traslado.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  atraparFocoModal,
  enfocarPrimerElemento,
  devolverFocoDisparador
} from '../../../core/utils/modal-accessibility.util';

@Component({
  selector: 'app-traslados',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './traslados.component.html',
  styleUrls: ['./traslados.component.css']
})
export class TrasladosComponent implements OnInit, OnDestroy {
  items: Traslado[] = [];
  sucursales: SucursalDTO[] = [];
  estado = '';
  sucursal = '';
  flujo: 'TODOS' | 'SALIENTES' | 'ENTRANTES' = 'TODOS';
  cargando = false;
  procesando = '';
  error = '';
  exito = '';
  rechazo?: Traslado;
  motivo = '';

  estados: EstadoTraslado[] = ['SOLICITADO', 'APROBADO', 'RECHAZADO', 'DESPACHADO', 'RECIBIDO', 'CANCELADO'];

  @ViewChild('modalRechazoDialog') modalRechazoDialog?: ElementRef<HTMLElement>;
  private disparadorPrevio: HTMLElement | null = null;

  constructor(
    private api: ReservaTrasladoService,
    public auth: AuthService,
    private org: OrganizacionService
  ) {}

  ngOnInit(): void {
    const u = this.auth.obtenerUsuarioActual();
    this.sucursal = u?.sucursal_id || '';
    this.org.gestionarSucursales().subscribe({
      next: (s) => (this.sucursales = s),
      error: () => (this.error = 'No pudimos cargar las sucursales.')
    });
    this.cargar();
  }

  ngOnDestroy(): void {
    if (this.rechazo) {
      desbloquearScrollBody();
    }
  }

  @HostListener('keydown.escape')
  alPresionarEscape(): void {
    if (this.rechazo && !this.procesando) {
      this.cerrarRechazo();
    }
  }

  alManejarTabModal(event: KeyboardEvent): void {
    if (this.modalRechazoDialog) {
      atraparFocoModal(event, this.modalRechazoDialog.nativeElement);
    }
  }

  abrirRechazo(t: Traslado, event?: Event): void {
    this.disparadorPrevio = (event?.currentTarget as HTMLElement) || (document.activeElement as HTMLElement);
    this.rechazo = t;
    this.motivo = '';
    bloquearScrollBody();
    setTimeout(() => {
      if (this.modalRechazoDialog) {
        enfocarPrimerElemento(this.modalRechazoDialog.nativeElement);
      }
    }, 50);
  }

  cerrarRechazo(): void {
    if (this.rechazo) {
      desbloquearScrollBody();
      this.rechazo = undefined;
      this.motivo = '';
    }
    devolverFocoDisparador(this.disparadorPrevio);
    this.disparadorPrevio = null;
  }

  get esAdmin(): boolean {
    return this.auth.obtenerUsuarioActual()?.rol === 'ADMINISTRADOR';
  }

  get esEncargado(): boolean {
    return this.auth.obtenerUsuarioActual()?.rol === 'ENCARGADO';
  }

  get miSucursalId(): string {
    return this.auth.obtenerUsuarioActual()?.sucursal_id || '';
  }

  puedeAprobarODespachar(t: Traslado): boolean {
    if (this.esAdmin) return true;
    return !!this.miSucursalId && t.sucursal_origen_id === this.miSucursalId;
  }

  puedeRecibir(t: Traslado): boolean {
    if (this.esAdmin) return true;
    return !!this.miSucursalId && t.sucursal_destino_id === this.miSucursalId;
  }

  cargar(): void {
    this.cargando = true;
    this.error = '';

    if (this.esEncargado && this.miSucursalId) {
      if (this.flujo === 'SALIENTES') {
        this.api.listarTraslados({ estado: this.estado || undefined, sucursal_origen_id: this.miSucursalId }).subscribe({
          next: (p) => { this.items = p.items; this.cargando = false; },
          error: (e) => { this.error = this.msg(e); this.cargando = false; }
        });
      } else if (this.flujo === 'ENTRANTES') {
        this.api.listarTraslados({ estado: this.estado || undefined, sucursal_destino_id: this.miSucursalId }).subscribe({
          next: (p) => { this.items = p.items; this.cargando = false; },
          error: (e) => { this.error = this.msg(e); this.cargando = false; }
        });
      } else {
        // TODOS para encargado: consultar origen y destino en paralelo
        forkJoin([
          this.api.listarTraslados({ estado: this.estado || undefined, sucursal_origen_id: this.miSucursalId }),
          this.api.listarTraslados({ estado: this.estado || undefined, sucursal_destino_id: this.miSucursalId })
        ]).subscribe({
          next: ([salientes, entrantes]) => {
            const combinados = new Map<string, Traslado>();
            salientes.items.forEach((t) => combinados.set(t.id, t));
            entrantes.items.forEach((t) => combinados.set(t.id, t));
            this.items = Array.from(combinados.values()).sort(
              (a, b) => new Date(b.fecha_solicitud).getTime() - new Date(a.fecha_solicitud).getTime()
            );
            this.cargando = false;
          },
          error: (e) => { this.error = this.msg(e); this.cargando = false; }
        });
      }
    } else {
      // Administrador
      const filtros: Record<string, string | number> = {};
      if (this.estado) filtros['estado'] = this.estado;
      if (this.sucursal) filtros['sucursal_origen_id'] = this.sucursal;
      this.api.listarTraslados(filtros).subscribe({
        next: (p) => { this.items = p.items; this.cargando = false; },
        error: (e) => { this.error = this.msg(e); this.cargando = false; }
      });
    }
  }

  accion(t: Traslado, a: 'aprobar' | 'despachar' | 'recibir'): void {
    this.procesando = t.id;
    this.api.transicionarTraslado(t.id, a).subscribe({
      next: () => {
        this.procesando = '';
        this.exito = {
          aprobar: 'Traslado aprobado.',
          despachar: 'Traslado despachado.',
          recibir: 'Traslado recibido.'
        }[a];
        this.cargar();
      },
      error: (e) => {
        this.procesando = '';
        this.error = this.msg(e);
      }
    });
  }

  confirmarRechazo(): void {
    if (!this.rechazo || this.procesando) return;
    this.procesando = this.rechazo.id;
    this.api.rechazarTraslado(this.rechazo.id, this.motivo).subscribe({
      next: () => {
        this.procesando = '';
        this.cerrarRechazo();
        this.exito = 'Solicitud rechazada.';
        this.cargar();
      },
      error: (e) => {
        this.procesando = '';
        this.error = this.msg(e);
      }
    });
  }

  nombre(id: string): string {
    return this.sucursales.find((s) => s.id === id)?.nombre || 'No disponible';
  }

  etiqueta(v: string): string {
    return v.toLowerCase().replaceAll('_', ' ');
  }

  private msg(e: unknown): string {
    return formatearErrorApi(e, 'No se pudo completar la operación.');
  }
}
