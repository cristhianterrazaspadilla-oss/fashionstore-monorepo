import { Component, OnInit, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ReembolsoService } from '../services/reembolso.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import {
  ReembolsoDetalleDTO,
  ReembolsoSolicitudDTO,
  EstadoReembolso,
  MedioReembolso
} from '../models/reembolso.models';
import { formatearBs, formatearFechaHora, type DecimalApi } from '../../../core/utils/moneda.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import { ConfirmDialogComponent } from '../../../shared/confirm-dialog/confirm-dialog.component';

@Component({
  selector: 'app-reembolsos',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, ConfirmDialogComponent],
  templateUrl: './reembolsos.component.html',
  styleUrls: ['./reembolsos.component.css']
})
export class ReembolsosComponent implements OnInit {
  reembolsos: ReembolsoDetalleDTO[] = [];
  cargando = true;
  error: string | null = null;
  exito: string | null = null;

  // Filtros
  filtroEstado: 'TODOS' | EstadoReembolso = 'TODOS';
  filtroMedio: 'TODOS' | MedioReembolso = 'TODOS';

  // Modal de solicitud
  modalSolicitudAbierto = false;
  solicitando = false;
  solicitud: ReembolsoSolicitudDTO = {
    origen_tipo: 'VENTA',
    origen_id: '',
    motivo_codigo: 'DEFECTO_FABRICA',
    motivo_descripcion: '',
    unidades: 1
  };
  errorSolicitud = '';

  // Confirmaciones de acciones operativas
  dialogoConfirmarVisible = false;
  accionPendiente: 'AUTORIZAR' | 'EJECUTAR' | null = null;
  reembolsoSeleccionado: ReembolsoDetalleDTO | null = null;
  procesandoAccion = false;

  private readonly destroyRef = inject(DestroyRef);

  constructor(
    private reembolsoService: ReembolsoService,
    public auth: AuthService
  ) {}

  ngOnInit(): void {
    this.cargarReembolsos();
  }

  cargarReembolsos(): void {
    this.cargando = true;
    this.error = null;
    this.reembolsoService.listar()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (items) => {
          this.reembolsos = items || [];
          this.cargando = false;
        },
        error: (err) => {
          this.error = formatearErrorApi(err, 'No fue posible consultar la lista de reembolsos.');
          this.cargando = false;
        }
      });
  }

  get reembolsosFiltrados(): ReembolsoDetalleDTO[] {
    let list = this.reembolsos;
    if (this.filtroEstado !== 'TODOS') {
      list = list.filter(r => r.estado === this.filtroEstado);
    }
    if (this.filtroMedio !== 'TODOS') {
      list = list.filter(r => r.medio_original === this.filtroMedio);
    }
    return list;
  }

  get esPersonal(): boolean {
    const rol = this.auth.obtenerUsuarioActual()?.rol;
    return rol === 'ADMINISTRADOR' || rol === 'ENCARGADO' || rol === 'SUPERADMIN';
  }

  // Modal Solicitud
  abrirModalSolicitud(origenId = '', tipo: 'VENTA' | 'PEDIDO' | 'DEVOLUCION' = 'VENTA'): void {
    this.solicitud = {
      origen_tipo: tipo,
      origen_id: origenId,
      motivo_codigo: 'DEFECTO_FABRICA',
      motivo_descripcion: '',
      unidades: 1
    };
    this.errorSolicitud = '';
    this.modalSolicitudAbierto = true;
  }

  cerrarModalSolicitud(): void {
    if (this.solicitando) return;
    this.modalSolicitudAbierto = false;
  }

  enviarSolicitud(): void {
    if (!this.solicitud.origen_id.trim()) {
      this.errorSolicitud = 'Indica el identificador o número del comprobante.';
      return;
    }
    this.solicitando = true;
    this.errorSolicitud = '';

    this.reembolsoService.solicitar(this.solicitud)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (nuevo) => {
          this.solicitando = false;
          this.modalSolicitudAbierto = false;
          this.exito = 'Solicitud de reembolso registrada correctamente.';
          this.cargarReembolsos();
        },
        error: (err) => {
          this.solicitando = false;
          this.errorSolicitud = formatearErrorApi(err, 'No se pudo enviar la solicitud de reembolso.');
        }
      });
  }

  // Operaciones de personal
  iniciarAutorizacion(r: ReembolsoDetalleDTO): void {
    this.reembolsoSeleccionado = r;
    this.accionPendiente = 'AUTORIZAR';
    this.dialogoConfirmarVisible = true;
  }

  iniciarEjecucion(r: ReembolsoDetalleDTO): void {
    this.reembolsoSeleccionado = r;
    this.accionPendiente = 'EJECUTAR';
    this.dialogoConfirmarVisible = true;
  }

  confirmarAccion(): void {
    if (!this.reembolsoSeleccionado || !this.accionPendiente || this.procesandoAccion) return;
    this.procesandoAccion = true;
    const id = this.reembolsoSeleccionado.reembolso_id;

    if (this.accionPendiente === 'AUTORIZAR') {
      this.reembolsoService.autorizar(id, { motivo_aprobacion: 'Autorizado tras revisión técnica' })
        .subscribe({
          next: () => {
            this.procesandoAccion = false;
            this.dialogoConfirmarVisible = false;
            this.exito = 'Reembolso autorizado correctamente.';
            this.cargarReembolsos();
          },
          error: (err) => {
            this.procesandoAccion = false;
            this.error = formatearErrorApi(err, 'No se pudo autorizar el reembolso.');
          }
        });
    } else if (this.accionPendiente === 'EJECUTAR') {
      this.reembolsoService.ejecutar(id)
        .subscribe({
          next: () => {
            this.procesandoAccion = false;
            this.dialogoConfirmarVisible = false;
            this.exito = 'Reembolso ejecutado hacia el medio original exitosamente.';
            this.cargarReembolsos();
          },
          error: (err) => {
            this.procesandoAccion = false;
            this.error = formatearErrorApi(err, 'No se pudo ejecutar el reembolso.');
          }
        });
    }
  }

  cancelarAccion(): void {
    this.dialogoConfirmarVisible = false;
    this.reembolsoSeleccionado = null;
    this.accionPendiente = null;
  }

  etiquetaEstado(estado: EstadoReembolso): string {
    switch (estado) {
      case 'PENDIENTE_AUTORIZACION':
      case 'SOLICITADO':
        return 'Pendiente de aprobación';
      case 'AUTORIZADO':
        return 'Aprobado para devolución';
      case 'EN_PROCESO':
        return 'En proceso bancario';
      case 'COMPLETADO':
        return 'Completado';
      case 'FALLIDO':
        return 'Falla en acreditación';
      case 'RECHAZADO':
        return 'Solicitud rechazada';
      default:
        return estado;
    }
  }

  claseEstado(estado: EstadoReembolso): string {
    switch (estado) {
      case 'SOLICITADO':
      case 'PENDIENTE_AUTORIZACION':
        return 'badge-warning';
      case 'AUTORIZADO':
        return 'badge-info';
      case 'EN_PROCESO':
        return 'badge-primary';
      case 'COMPLETADO':
        return 'badge-success';
      case 'FALLIDO':
      case 'RECHAZADO':
        return 'badge-danger';
      default:
        return 'badge-default';
    }
  }

  etiquetaMedio(medio: MedioReembolso): string {
    switch (medio) {
      case 'STRIPE': return 'Tarjeta original (Stripe)';
      case 'SALDO': return 'Saldo a favor cliente';
      case 'EFECTIVO': return 'Efectivo en caja';
      default: return medio;
    }
  }

  iconoMedio(medio: MedioReembolso): string {
    switch (medio) {
      case 'STRIPE': return '💳';
      case 'SALDO': return '👛';
      case 'EFECTIVO': return '💵';
      default: return '🪙';
    }
  }

  bs(monto: DecimalApi | null | undefined): string {
    return formatearBs(monto);
  }

  fechaHora(fecha: string | null | undefined): string {
    return formatearFechaHora(fecha);
  }
}
