import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, ViewChild, ElementRef, HostListener, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin, interval, Subscription } from 'rxjs';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { ReservaTrasladoService } from '../services/reserva-traslado.service';
import { VentaPresencialService } from '../../ventas_pagos/services/venta-presencial.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { ProductoService } from '../../catalogo/services/producto.service';
import { SincronizacionOfflineService } from '../../../core/services/sincronizacion-offline.service';
import { OperacionEncolada } from '../../../core/services/offline-store.service';
import { EstadoReserva, Reserva } from '../models/reserva-traslado.models';
import { MetodoCaja } from '../../ventas_pagos/models/venta-presencial.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';
import { VarianteDTO } from '../../catalogo/models/catalogo.models';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  atraparFocoModal,
  enfocarPrimerElemento,
  devolverFocoDisparador
} from '../../../core/utils/modal-accessibility.util';
import { formatearFechaBolivia, obtenerHoraBoliviaIso } from '../../../core/utils/bolivia-time.util';

@Component({
  selector: 'app-reservas',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './reservas.component.html',
  styleUrls: ['./reservas.component.css']
})
export class ReservasComponent implements OnInit, OnDestroy {
  reservas: Reserva[] = [];
  reservasLocales: OperacionEncolada[] = [];
  sucursales: SucursalDTO[] = [];
  variantes: VarianteDTO[] = [];

  cargando = false;
  sincronizando = false;
  procesando = '';
  error = '';
  exito = '';
  filtroEstado = '';

  modal: 'crear' | 'cancelar' | 'adelanto' | null = null;
  seleccionada?: Reserva;

  destino = '';
  fechaVisita = '';
  observacion = '';
  nuevaVariante = '';
  nuevaCantidad = 1;
  nuevoOrigen = '';
  lineas: { variante_id: string; cantidad: number; sucursal_origen_id?: string }[] = [];

  metodo: MetodoCaja = 'EFECTIVO';
  private polling?: Subscription;
  private redSub?: Subscription;
  errorHorario = '';
  private claveCrearActual?: string;
  private claveCancelarActual = new Map<string, string>();

  readonly estados: EstadoReserva[] = [
    'PENDIENTE_TRASLADO',
    'PENDIENTE',
    'PREPARADA',
    'ATENDIDA',
    'COMPLETADA',
    'CANCELADA',
    'VENCIDA'
  ];

  @ViewChild('modalDialog') modalDialog?: ElementRef<HTMLElement>;
  private disparadorPrevio: HTMLElement | null = null;

  constructor(
    public auth: AuthService,
    private api: ReservaTrasladoService,
    private pagos: VentaPresencialService,
    private org: OrganizacionService,
    private productos: ProductoService,
    public syncOfflineService: SincronizacionOfflineService
  ) {}

  ngOnInit(): void {
    forkJoin([this.org.gestionarSucursales(), this.productos.gestionarVariantes()]).subscribe({
      next: ([s, v]) => {
        this.sucursales = s;
        this.variantes = v;
      },
      error: () => {
        this.error = 'No pudimos cargar las opciones para gestionar reservas.';
      }
    });

    this.cargar();

    // Polling en línea para personal de tienda
    if (this.esPersonal) {
      this.polling = interval(30000).subscribe(() => {
        if (!document.hidden && !this.modal && this.syncOfflineService.estaEnLinea) {
          this.cargar(false);
        }
      });
    }

    // Escuchar cambios de conectividad
    this.redSub = this.syncOfflineService.enLinea$.subscribe(enLinea => {
      if (enLinea) {
        this.cargar(false);
      } else {
        this.cargarReservasLocales();
      }
    });
  }

  ngOnDestroy(): void {
    this.polling?.unsubscribe();
    this.redSub?.unsubscribe();
    if (this.modal) {
      desbloquearScrollBody();
    }
  }

  @HostListener('keydown.escape')
  alPresionarEscape(): void {
    if (this.modal && !this.procesando) {
      this.cerrarModal();
    }
  }

  alManejarTabModal(event: KeyboardEvent): void {
    if (this.modalDialog) {
      atraparFocoModal(event, this.modalDialog.nativeElement);
    }
  }

  abrirModal(tipo: 'crear' | 'cancelar' | 'adelanto', r?: Reserva, event?: Event): void {
    this.disparadorPrevio = (event?.currentTarget as HTMLElement) || (document.activeElement as HTMLElement);
    this.seleccionada = r;
    this.modal = tipo;
    this.error = '';
    bloquearScrollBody();
    setTimeout(() => {
      if (this.modalDialog) {
        enfocarPrimerElemento(this.modalDialog.nativeElement);
      }
    }, 50);
  }

  cerrarModal(): void {
    if (this.modal) {
      desbloquearScrollBody();
      this.modal = null;
    }
    devolverFocoDisparador(this.disparadorPrevio);
    this.disparadorPrevio = null;
  }

  get usuario() {
    return this.auth.obtenerUsuarioActual();
  }
  get esCliente(): boolean {
    return this.usuario?.rol === 'CLIENTE';
  }
  get esPersonal(): boolean {
    return ['ADMINISTRADOR', 'ENCARGADO'].includes(this.usuario?.rol || '');
  }
  get puedePreparar(): boolean {
    return ['ADMINISTRADOR', 'ENCARGADO'].includes(this.usuario?.rol || '');
  }

  cargar(mostrar = true): void {
    if (!this.usuario) return;
    if (mostrar) this.cargando = true;
    this.error = '';

    // Cargar pendientes locales (reserva offline)
    this.cargarReservasLocales();

    if (!this.syncOfflineService.estaEnLinea) {
      this.cargando = false;
      return;
    }

    const req = this.esCliente
      ? this.api.listarReservas({ estado: this.filtroEstado })
      : this.api.panelReservas(this.usuario.sucursal_id || this.destino, this.filtroEstado);

    if (!this.esCliente && !this.usuario.sucursal_id && !this.destino) {
      this.cargando = false;
      return;
    }

    req.subscribe({
      next: (p) => {
        this.reservas = p.items;
        this.cargando = false;
      },
      error: (e) => {
        this.error = this.mensaje(e);
        this.cargando = false;
      }
    });
  }

  async cargarReservasLocales(): Promise<void> {
    try {
      this.reservasLocales = await this.syncOfflineService.listarReservasLocales();
    } catch {
      this.reservasLocales = [];
    }
  }

  async sincronizarColaManual(): Promise<void> {
    if (!this.syncOfflineService.estaEnLinea) {
      this.error = 'Se requiere conexión a internet para sincronizar las reservas pendientes.';
      return;
    }

    this.sincronizando = true;
    this.error = '';
    this.exito = '';

    try {
      const resumen = await this.syncOfflineService.sincronizarCola();
      this.sincronizando = false;
      if (resumen.sincronizadas > 0) {
        this.exito = `Se sincronizaron exitosamente ${resumen.sincronizadas} reserva(s) con el servidor.`;
      } else if (resumen.errores > 0) {
        this.error = `Ocurrieron observaciones en ${resumen.errores} reserva(s). Revisa el estado de cada solicitud.`;
      } else {
        this.exito = 'No hay reservas pendientes de sincronización.';
      }
      this.cargar(false);
    } catch (e) {
      this.sincronizando = false;
      this.error = this.mensaje(e);
    }
  }

  validarHorarioVisita(): void {
    this.errorHorario = '';
    if (!this.fechaVisita) return;
    const d = new Date(this.fechaVisita);
    if (isNaN(d.getTime())) return;
    const ahora = new Date();
    if (d.getTime() < ahora.getTime() - 60000) {
      this.errorHorario = 'La fecha de visita no puede ser anterior al momento actual.';
      return;
    }
    const horas = d.getHours();
    const minutos = d.getMinutes();
    if (horas < 9 || horas > 20 || (horas === 20 && minutos > 0)) {
      this.errorHorario = 'Hora fuera de horario de atención. El horario de atención es de 09:00 a 20:00.';
    }
  }

  agregarLinea(): void {
    if (!this.nuevaVariante || this.nuevaCantidad < 1) return;
    const existente = this.lineas.find((x) => x.variante_id === this.nuevaVariante);
    if (existente) existente.cantidad += this.nuevaCantidad;
    else
      this.lineas.push({
        variante_id: this.nuevaVariante,
        cantidad: this.nuevaCantidad,
        sucursal_origen_id: this.nuevoOrigen || undefined
      });
    this.nuevaVariante = '';
    this.nuevaCantidad = 1;
    this.nuevoOrigen = '';
  }

  quitarLinea(i: number): void {
    this.lineas.splice(i, 1);
  }

  async crear(): Promise<void> {
    this.error = '';
    this.errorHorario = '';
    if (this.fechaVisita) {
      this.validarHorarioVisita();
      if (this.errorHorario) return;
    }
    if (!this.destino || !this.lineas.length || this.procesando) return;

    this.procesando = 'crear';

    // Si no hay conexión, registrar reserva fuera de línea (reserva offline)
    if (!this.syncOfflineService.estaEnLinea) {
      try {
        const fechaVisitaIso = this.fechaVisita
          ? obtenerHoraBoliviaIso(new Date(this.fechaVisita))
          : obtenerHoraBoliviaIso(new Date(Date.now() + 24 * 60 * 60 * 1000));

        await this.syncOfflineService.registrarReservaOffline({
          sucursal_id: this.destino,
          visita_en: fechaVisitaIso,
          lineas: this.lineas.map(l => ({
            variante_id: l.variante_id,
            cantidad: l.cantidad
          }))
        });

        this.procesando = '';
        this.cerrarModal();
        this.lineas = [];
        this.fechaVisita = '';
        this.observacion = '';
        this.errorHorario = '';
        this.exito = 'Reserva guardada fuera de línea en este dispositivo. Se sincronizará automáticamente al conectar.';
        this.cargarReservasLocales();
      } catch (e: any) {
        this.procesando = '';
        this.error = e?.message || 'No fue posible guardar la reserva localmente.';
      }
      return;
    }

    // Modalidad en línea normal (gestion de reservas)
    if (!this.claveCrearActual) {
      this.claveCrearActual = crypto.randomUUID();
    }

    this.api
      .crearReserva({
        sucursal_destino_id: this.destino,
        fecha_visita: this.fechaVisita ? new Date(this.fechaVisita).toISOString() : undefined,
        observacion: this.observacion || undefined,
        lineas: this.lineas
      }, this.claveCrearActual)
      .subscribe({
        next: (r) => {
          this.claveCrearActual = undefined;
          this.procesando = '';
          this.cerrarModal();
          this.lineas = [];
          this.fechaVisita = '';
          this.observacion = '';
          this.errorHorario = '';
          this.exito = `Reserva ${r.codigo} confirmada exitosamente.`;
          this.cargar();
        },
        error: (e) => {
          this.procesando = '';
          this.error = this.mensaje(e);
        }
      });
  }

  abrirAccion(tipo: 'cancelar' | 'adelanto', r: Reserva, event?: Event): void {
    this.abrirModal(tipo, r, event);
  }

  /**
   * Cancelación de reserva con Idempotency-Key y revisión concurrente (gestion de reservas).
   * Maneja error 409 por revisión obsoleta recargando la reserva y mostrando explicación.
   */
  confirmarCancelacion(): void {
    if (!this.seleccionada || this.procesando) return;
    this.procesando = 'cancelar';
    const id = this.seleccionada.id;
    const revisionActual = this.seleccionada.revision || 1;

    let clave = this.claveCancelarActual.get(id);
    if (!clave) {
      clave = crypto.randomUUID();
      this.claveCancelarActual.set(id, clave);
    }

    this.api.cancelarReserva(id, revisionActual, clave).subscribe({
      next: () => {
        this.claveCancelarActual.delete(id);
        this.procesando = '';
        this.cerrarModal();
        this.exito = 'La reserva fue cancelada y el inventario se actualizó correctamente.';
        this.cargar();
      },
      error: (e: any) => {
        this.procesando = '';
        if (e.status === 409) {
          this.claveCancelarActual.delete(id);
          this.error = 'La reserva fue actualizada en otra sesión o su estado ha cambiado. Recargamos la información para que revises su estado actual.';
          this.cerrarModal();
          this.cargar();
        } else {
          this.error = this.mensaje(e);
        }
      }
    });
  }

  registrarAdelanto(): void {
    if (!this.seleccionada || this.procesando) return;
    this.procesando = 'adelanto';
    this.pagos.registrarAdelanto(this.seleccionada.id, this.metodo).subscribe({
      next: (p) => {
        this.procesando = '';
        this.cerrarModal();
        this.exito = `Adelanto de Bs ${p.monto} registrado exitosamente. El plazo de tu reserva se extendió a 72 horas.`;
        this.cargar();
      },
      error: (e) => {
        this.procesando = '';
        this.error = this.mensaje(e);
      }
    });
  }

  transicionar(r: Reserva, accion: 'preparar' | 'atender'): void {
    if (this.procesando) return;
    this.procesando = r.id;
    const req = accion === 'preparar' ? this.api.prepararReserva(r.id) : this.api.atenderReserva(r.id);
    req.subscribe({
      next: () => {
        this.procesando = '';
        this.exito = accion === 'preparar' ? 'Reserva preparada en vestidor.' : 'Atención iniciada con el cliente.';
        this.cargar();
      },
      error: (e) => {
        this.procesando = '';
        this.error = this.mensaje(e);
      }
    });
  }

  variante(id: string): string {
    const v = this.variantes.find((x) => x.id === id);
    return v ? `${v.sku}` : 'Sin referencia';
  }

  sucursal(id: string): string {
    return this.sucursales.find((x) => x.id === id)?.nombre || 'No disponible';
  }

  etiqueta(valor: string): string {
    if (!valor) return '—';
    return valor.toLowerCase().replaceAll('_', ' ');
  }

  puedeCancelar(r: Reserva): boolean {
    return ['PENDIENTE_TRASLADO', 'PENDIENTE', 'PREPARADA'].includes(r.estado);
  }

  fechaFormateada(fechaIso?: string | null): string {
    return formatearFechaBolivia(fechaIso);
  }

  private mensaje(e: unknown): string {
    return formatearErrorApi(e, 'No se pudo completar la operación. Intenta nuevamente.');
  }
}
