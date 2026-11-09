import { Component, OnInit, OnDestroy, ViewChild, ElementRef, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { EmpresaService } from '../services/empresa.service';
import { EmpresaCrearDTO, EmpresaDetalleDTO } from '../models/empresa.models';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { PlanDetalleDTO, SucursalDTO, AsignarSuscripcionDTO, SuscripcionRespuestaDTO } from '../../organizacion/models/organizacion.models';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';
import { formatearFechaBolivia } from '../../../core/utils/bolivia-time.util';
import {
  bloquearScrollBody,
  desbloquearScrollBody,
  atraparFocoModal,
  enfocarPrimerElemento,
  devolverFocoDisparador
} from '../../../core/utils/modal-accessibility.util';

@Component({
  selector: 'app-empresas',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './empresas.component.html',
  styleUrls: ['./empresas.component.css']
})
export class EmpresasComponent implements OnInit, OnDestroy {
  empresas: EmpresaDetalleDTO[] = [];
  sucursales: SucursalDTO[] = [];
  planes: PlanDetalleDTO[] = [];
  suscripciones: Record<string, SuscripcionRespuestaDTO | null> = {};
  filtroSoloActivas = false;
  planIdNuevo = '';
  planIdEdicion = '';
  fechaVencimiento = this.fechaPorDefecto();
  motivoPlan = 'Alta administrativa de la tienda';
  asignandoPlan = false;
  confirmandoPlan = false;
  private planPendiente: { firma: string; clave: string; datos: AsignarSuscripcionDTO } | null = null;

  nuevaEmpresa: EmpresaCrearDTO = {
    razon_social: '',
    nombre_comercial: '',
    empresa_codigo: '',
    administrador: {
      nombre: '',
      correo: '',
      credencial_inicial: ''
    }
  };

  cargando = false;
  guardando = false;
  mensajeError: string | null = null;
  mensajeExito: string | null = null;

  empresaSeleccionada: EmpresaDetalleDTO | null = null;
  private claveIdempotenciaActual: string | null = null;

  @ViewChild('modalDetalleBox') modalDetalleBox?: ElementRef<HTMLElement>;
  private disparadorPrevio: HTMLElement | null = null;

  constructor(private empresaService: EmpresaService, private organizacionService: OrganizacionService) {}

  ngOnInit(): void {
    this.cargarEmpresas();
    this.cargarSucursales();
    this.organizacionService.listarPlanes().subscribe({
      next: planes => {
        this.planes = planes;
        if (!this.planIdNuevo && planes.length) this.planIdNuevo = planes[0].id;
      },
      error: err => this.mensajeError = formatearErrorApi(err, 'No se pudieron cargar los planes disponibles.')
    });
  }

  private fechaPorDefecto(): string {
    const fecha = new Date();
    fecha.setFullYear(fecha.getFullYear() + 1);
    return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, '0')}-${String(fecha.getDate()).padStart(2, '0')}`;
  }

  cargarSucursales(): void {
    this.organizacionService.gestionarSucursales(undefined, false).subscribe({
      next: sucursales => this.sucursales = sucursales,
      error: err => this.mensajeError = formatearErrorApi(err, 'No se pudieron cargar las sucursales.')
    });
  }

  sucursalesDe(empresaId: string): SucursalDTO[] {
    return this.sucursales.filter(sucursal => sucursal.empresa_id === empresaId);
  }

  get empresasActivas(): number { return this.empresas.filter(empresa => empresa.estado === 'ACTIVA').length; }
  get empresasPendientes(): number { return this.empresas.filter(empresa => empresa.estado === 'PENDIENTE_PLAN').length; }
  get sucursalesActivas(): number { return this.sucursales.filter(sucursal => sucursal.activa).length; }

  private cargarSuscripcion(empresaId: string): void {
    this.organizacionService.listarHistorialSuscripciones(empresaId).subscribe({
      next: historial => this.suscripciones[empresaId] = historial[0] ?? null,
      error: err => this.mensajeError = formatearErrorApi(err, 'No se pudo consultar el plan de una tienda.')
    });
  }

  cargarEmpresas(): void {
    this.cargando = true;
    this.empresaService.listarEmpresas(this.filtroSoloActivas).subscribe({
      next: (data) => {
        this.empresas = data;
        this.cargando = false;
        data.forEach(empresa => this.cargarSuscripcion(empresa.id));
      },
      error: (err) => {
        this.mensajeError = formatearErrorApi(err, 'No se pudo obtener el listado de empresas.');
        this.cargando = false;
      }
    });
  }

  cambiarFiltroActivas(): void {
    this.cargarEmpresas();
  }

  crearEmpresa(): void {
    this.mensajeError = null;
    this.mensajeExito = null;

    const razon = this.nuevaEmpresa.razon_social?.trim();
    const nombre = this.nuevaEmpresa.nombre_comercial?.trim();
    const codigo = this.nuevaEmpresa.empresa_codigo?.trim().toLowerCase();
    const adminNombre = this.nuevaEmpresa.administrador.nombre?.trim();
    const adminCorreo = this.nuevaEmpresa.administrador.correo?.trim().toLowerCase();
    const adminClave = this.nuevaEmpresa.administrador.credencial_inicial;

    if (!razon || !nombre || !codigo || !adminNombre || !adminCorreo || !adminClave || !this.planIdNuevo) {
      this.mensajeError = 'Por favor complete todos los campos requeridos (*).';
      return;
    }
    if (!this.fechaPlanValida()) {
      this.mensajeError = 'La vigencia del plan debe terminar después de hoy.';
      return;
    }

    const regexCodigo = /^[a-zA-Z0-9_-]+$/;
    if (!regexCodigo.test(codigo)) {
      this.mensajeError = 'El identificador de empresa sólo puede contener letras, números, guiones y guiones bajos (sin espacios).';
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(adminCorreo)) {
      this.mensajeError = 'Por favor ingrese una dirección de correo válida para el administrador.';
      return;
    }

    if (!this.contraseniaValida) {
      const faltantes = this.obtenerRequisitosFaltantes();
      this.mensajeError = `La credencial inicial debe cumplir los requisitos de seguridad. Falta: ${faltantes.join(', ')}.`;
      return;
    }

    const payload: EmpresaCrearDTO = {
      razon_social: razon,
      nombre_comercial: nombre,
      empresa_codigo: codigo,
      administrador: {
        nombre: adminNombre,
        correo: adminCorreo,
        credencial_inicial: adminClave
      }
    };

    if (!this.claveIdempotenciaActual) {
      this.claveIdempotenciaActual = crypto.randomUUID();
    }
    const idempotencyKey = this.claveIdempotenciaActual;
    this.guardando = true;

    this.empresaService.crearEmpresa(payload, idempotencyKey).subscribe({
      next: (resp) => {
        this.guardando = false;
        this.claveIdempotenciaActual = null;
        this.mensajeExito = `Tienda "${payload.nombre_comercial}" creada con administrador inicial. Asignando el plan…`;
        this.nuevaEmpresa = {
          razon_social: '',
          nombre_comercial: '',
          empresa_codigo: '',
          administrador: {
            nombre: '',
            correo: '',
            credencial_inicial: ''
          }
        };
        this.cargarEmpresas();
        this.asignarPlan(resp.empresa_id, this.planIdNuevo, true);
      },
      error: (err) => {
        this.guardando = false;
        // Conservamos this.claveIdempotenciaActual para que reintentos posteriores tras fallo usen la misma clave
        this.mensajeError = formatearErrorApi(err, 'No fue posible completar el registro de la empresa contratante.');
      }
    });
  }

  verDetalle(empresa: EmpresaDetalleDTO, event?: Event): void {
    this.disparadorPrevio = (event?.currentTarget as HTMLElement) || (document.activeElement as HTMLElement);
    this.empresaSeleccionada = empresa;
    this.planIdEdicion = this.suscripciones[empresa.id]?.plan_id || this.planes[0]?.id || '';
    this.fechaVencimiento = this.fechaPorDefecto();
    this.motivoPlan = 'Alta o renovación administrativa de la tienda';
    this.planPendiente = null;
    this.confirmandoPlan = false;
    bloquearScrollBody();
    setTimeout(() => {
      if (this.modalDetalleBox) {
        enfocarPrimerElemento(this.modalDetalleBox.nativeElement);
      }
    }, 50);
  }

  cerrarDetalle(): void {
    if (this.empresaSeleccionada) {
      desbloquearScrollBody();
      this.empresaSeleccionada = null;
      this.confirmandoPlan = false;
    }
    devolverFocoDisparador(this.disparadorPrevio);
    this.disparadorPrevio = null;
  }

  fechaPlanValida(): boolean {
    const vencimiento = new Date(`${this.fechaVencimiento}T23:59:59`);
    return Number.isFinite(vencimiento.getTime()) && vencimiento.getTime() > Date.now();
  }

  asignarPlanSeleccionado(): void {
    if (!this.empresaSeleccionada || !this.confirmandoPlan) return;
    this.confirmandoPlan = false;
    this.asignarPlan(this.empresaSeleccionada.id, this.planIdEdicion, false);
  }

  planSeleccionadoNombre(): string {
    return this.planes.find(plan => plan.id === this.planIdEdicion)?.nombre || 'el plan elegido';
  }

  private asignarPlan(empresaId: string, planId: string, desdeAlta: boolean): void {
    if (!planId || !this.fechaPlanValida() || this.motivoPlan.trim().length < 3) {
      this.mensajeError = 'Selecciona un plan, una vigencia futura y un motivo de al menos 3 caracteres.';
      return;
    }
    const firma = `${empresaId}|${planId}|${this.fechaVencimiento}|${this.motivoPlan.trim()}`;
    if (this.planPendiente?.firma !== firma) {
      this.planPendiente = {
        firma,
        clave: crypto.randomUUID(),
        datos: {
          plan_id: planId,
          inicio_en: new Date().toISOString(),
          vence_en: new Date(`${this.fechaVencimiento}T23:59:59`).toISOString(),
          motivo: this.motivoPlan.trim(),
          ...(this.suscripciones[empresaId]?.version ? { revision: this.suscripciones[empresaId]!.version } : {})
        }
      };
    }
    const intento = this.planPendiente;
    this.asignandoPlan = true;
    this.organizacionService.asignarSuscripcion(empresaId, intento.datos, intento.clave).subscribe({
      next: suscripcion => {
        this.asignandoPlan = false;
        this.planPendiente = null;
        this.suscripciones[empresaId] = suscripcion;
        if (this.empresaSeleccionada?.id === empresaId && this.empresaSeleccionada.estado === 'PENDIENTE_PLAN') {
          this.empresaSeleccionada = { ...this.empresaSeleccionada, estado: 'ACTIVA' };
        }
        this.mensajeError = null;
        this.mensajeExito = desdeAlta
          ? `Tienda creada y plan ${suscripcion.plan_nombre} activado. El administrador inicial ya puede iniciar sesión con el código de tienda y su contraseña.`
          : `Plan ${suscripcion.plan_nombre} asignado correctamente.`;
        this.cargarEmpresas();
      },
      error: err => {
        this.asignandoPlan = false;
        const detalle = formatearErrorApi(err, 'No se pudo asignar el plan.');
        this.mensajeError = desdeAlta
          ? `La tienda y su administrador sí se crearon, pero el plan no se confirmó: ${detalle} Abre la tienda en la lista para consultar su estado y reintentar.`
          : detalle;
        if (desdeAlta) this.filtroSoloActivas = false;
        this.cargarEmpresas();
      }
    });
  }

  formatearFecha(fecha?: string): string {
    return formatearFechaBolivia(fecha);
  }

  @HostListener('keydown.escape')
  alPresionarEscape(): void {
    if (this.empresaSeleccionada) {
      this.cerrarDetalle();
    }
  }

  alManejarTabDetalle(event: KeyboardEvent): void {
    if (this.modalDetalleBox) {
      atraparFocoModal(event, this.modalDetalleBox.nativeElement);
    }
  }

  ngOnDestroy(): void {
    if (this.empresaSeleccionada) {
      desbloquearScrollBody();
    }
  }

  // Validaciones de credencial inicial
  get claveActual(): string {
    return this.nuevaEmpresa.administrador.credencial_inicial || '';
  }

  get tieneLongitudMinima(): boolean {
    return this.claveActual.length >= 6;
  }

  get tieneMinuscula(): boolean {
    return /[a-z]/.test(this.claveActual);
  }

  get tieneMayuscula(): boolean {
    return /[A-Z]/.test(this.claveActual);
  }

  get tieneNumero(): boolean {
    return /[0-9]/.test(this.claveActual);
  }

  get contraseniaValida(): boolean {
    return this.tieneLongitudMinima && this.tieneMinuscula && this.tieneMayuscula && this.tieneNumero;
  }

  obtenerRequisitosFaltantes(): string[] {
    const faltantes: string[] = [];
    if (!this.tieneLongitudMinima) faltantes.push('al menos 6 caracteres');
    if (!this.tieneMinuscula) faltantes.push('una minúscula (a-z)');
    if (!this.tieneMayuscula) faltantes.push('una mayúscula (A-Z)');
    if (!this.tieneNumero) faltantes.push('un número (0-9)');
    return faltantes;
  }
}
