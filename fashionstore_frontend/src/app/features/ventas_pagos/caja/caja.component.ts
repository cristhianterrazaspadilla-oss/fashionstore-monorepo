import { CommonModule } from '@angular/common';
import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { ReservaTrasladoService } from '../../reservas_traslados/services/reserva-traslado.service';
import { VentaPresencialService } from '../services/venta-presencial.service';
import {
  CajaService,
  TurnoHabilitacion,
  CupoRespuesta,
  VentaOfflineCrear,
  ComprobanteCajaOffline
} from '../services/caja.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { UsuarioService } from '../../identidad_empresas/services/usuario.service';
import { UsuarioListadoDTO } from '../../identidad_empresas/models/usuario.models';
import { ProductoService } from '../../catalogo/services/producto.service';
import { Reserva } from '../../reservas_traslados/models/reserva-traslado.models';
import {
  Comprobante,
  ItemVenta,
  MetodoCaja,
  VentaLiquidadaDTO,
  VentaPresencialLiquidarDTO,
  IniciarVentaPresencialStripeRespuestaDTO,
  OrdenActivaCajaDTO,
  LineaVentaPresencialDTO
} from '../models/venta-presencial.models';
import { StripeService } from '../services/stripe.service';
import { VarianteDTO } from '../../catalogo/models/catalogo.models';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';

@Component({
  selector: 'app-caja',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './caja.component.html',
  styleUrls: ['./caja.component.css']
})
export class CajaComponent implements OnInit, OnDestroy {
  readonly Math = Math;
  // Modalidad de operación: 'RESERVA' o 'TURNO_OFFLINE'
  vistaModo: 'RESERVA' | 'TURNO_OFFLINE' = 'TURNO_OFFLINE';

  // Datos comunes
  variantes: VarianteDTO[] = [];
  cargando = false;
  procesando = false;
  error = '';
  avisoCatalogo = '';
  diagnosticoLegado = '';
  turnoRecuperacionId = '';
  mensajeExito = '';

  // Modo Venta Online / Reserva (Online)
  codigo = '';
  reserva?: Reserva;
  items: ItemVenta[] = [];
  variante = '';
  cantidad = 1;
  metodo: MetodoCaja = 'EFECTIVO';
  comprobante?: Comprobante;
  ventaLiquidada?: VentaLiquidadaDTO;
  clienteIdPresencial = '';
  efectivoRecibidoPresencial = 0;
  saldoAplicadoPresencial?: number;
  totalPresencialEstimado = 0;
  cambioPresencialEstimado = 0;

  // Modo Turno y Caja Offline
  turnoActivo: TurnoHabilitacion | null = null;
  turnoPendienteRecuperacion: TurnoHabilitacion | null = null;
  cajaId = 'CAJA-01';
  cajeroSeleccionado = '';
  cajeros: UsuarioListadoDTO[] = [];
  private readonly usuarios = inject(UsuarioService);
  get puedeAsignarCajero(): boolean { return this.auth.obtenerUsuarioActual()?.rol === 'ADMINISTRADOR'; }
  dispositivoId = '';
  cupoVarianteSeleccionada = '';
  cupoCantidadSolicitada = 1;
  cuposSolicitados: { variante_id: string; cantidad: number }[] = [];

  // Venta Contado Offline
  lineasVentaOffline: { variante_id: string; cantidad: number; precio_bob: number; descuento_bob?: number }[] = [];
  varianteVentaOffline = '';
  cantidadVentaOffline = 1;
  efectivoRecibido = 0;
  cambioEntregado = 0;
  ventasPendientesSync = 0;
  pendientesPorVariante: Record<string, number> = {};
  etiquetaCupo(c: CupoRespuesta): string { return [c.producto_nombre, c.talla, c.color, c.sku].filter(Boolean).join(' · ') || this.v(c.variante_id); }
  disponibleCupo(c: CupoRespuesta): number { return c.otorgado - c.consumido - c.liberado - (c.mermado || 0); }
  comprobanteOffline?: ComprobanteCajaOffline;
  operacionIdActual: string | null = null;
  medioPagoCaja: 'EFECTIVO' | 'SALDO' | 'STRIPE_TEST' = 'EFECTIVO';
  clienteIdCaja = '';

  // Modo Stripe Presencial y Caja (CU19)
  ordenStripeCaja: OrdenActivaCajaDTO | IniciarVentaPresencialStripeRespuestaDTO | null = null;
  iniciandoStripeCaja = false;
  capturandoStripeCaja = false;
  reanudandoStripeCaja = false;
  cargandoStripeCaja = false;
  cardElementCaja: any = null;
  cardElementCajaValido = false;
  errorTarjetaCaja: string | null = null;

  ordenStripePresencial: OrdenActivaCajaDTO | IniciarVentaPresencialStripeRespuestaDTO | null = null;
  iniciandoStripePresencial = false;
  capturandoStripePresencial = false;
  reanudandoStripePresencial = false;
  cargandoStripePresencial = false;
  cardElementPresencial: any = null;
  cardElementPresencialValido = false;
  errorTarjetaPresencial: string | null = null;

  stripeInstance: any = null;
  private readonly stripeService = inject(StripeService, { optional: true });

  // Cierre de Turno y Arqueo
  mostrarDialogoCierre = false;
  cierreSupervisado = false;
  supervisandoTurno = false;
  turnosConciliacion: TurnoHabilitacion[] = [];
  errorSupervision = '';
  private turnoOperacionPrevio: TurnoHabilitacion | null = null;

  cargarConciliaciones(): void {
    if (!this.puedeSupervisarCierre || !navigator.onLine) return;
    this.cajaService.listarConciliacion().subscribe({
      next: turnos => { this.turnosConciliacion = turnos; this.errorSupervision = ''; },
      error: e => this.errorSupervision = this.msg(e)
    });
  }

  async resolverTurnoSupervisado(turno: TurnoHabilitacion): Promise<void> {
    if (!this.puedeSupervisarCierre || !navigator.onLine || this.procesando) return;
    try {
      const actualizado = await firstValueFrom(this.cajaService.consultarTurno(turno.turno_id));
      if (actualizado.estado !== 'CONCILIACION') {
        this.errorSupervision = 'El turno cambió de estado. Actualiza la lista.';
        this.cargarConciliaciones();
        return;
      }
      this.turnoOperacionPrevio = this.turnoActivo;
      this.supervisandoTurno = true;
      this.vistaModo = 'TURNO_OFFLINE';
      this.turnoActivo = actualizado; // Consulta de supervisión en memoria, sin habilitación offline.
      this.abrirModalCierre(true);
    } catch (e) { this.errorSupervision = this.msg(e); }
  }

  volverAMiCaja(): void {
    if (this.supervisandoTurno) this.turnoActivo = this.turnoOperacionPrevio;
    this.turnoOperacionPrevio = null;
    this.supervisandoTurno = false;
  }
  arqueoEfectivoBob = 0;
  motivoSupervision = '';
  referenciaActa = '';
  conteoFisicoPorVariante: Record<string, number | null> = {};
  resolucionFaltantePorVariante: Record<string, 'PENDIENTE_SINCRONIZACION' | 'MERMA'> = {};
  motivoFaltantePorVariante: Record<string, string> = {};

  constructor(
    private api: VentaPresencialService,
    private cajaService: CajaService,
    private reservas: ReservaTrasladoService,
    public auth: AuthService,
    private productos: ProductoService
  ) {}

  async ngOnInit() {
    this.dispositivoId = this.cajaService.obtenerDispositivoId();
    this.cargarVariantes();
    if (this.puedeAsignarCajero && navigator.onLine) {
      this.usuarios.gestionarUsuarios(undefined, 'ACTIVO').subscribe({
        next: usuarios => this.cajeros = usuarios.filter(u => u.rol_nombre === 'CAJERO' && !!u.sucursal_id),
        error: e => this.error = this.msg(e)
      });
    }
    await this.cargarTurnoActivo();
    await this.actualizarContadorPendientes();
    this.diagnosticoLegado = (await this.cajaService.diagnosticosRecuperacion()).join(' ');
    this.recuperarOrdenActivaCaja();
    this.cargarConciliaciones();
  }

  cargarVariantes() {
    this.productos.gestionarVariantes().subscribe({
      next: v => { this.variantes = v; this.avisoCatalogo = ''; },
      error: e => {
        if (e?.status === 502 || e?.status === 504) {
          this.avisoCatalogo = 'No se pudo actualizar el catálogo. Los datos locales pueden estar desactualizados.';
          console.warn('Actualización del catálogo de Caja no disponible', { estado: e.status });
        } else { this.error = this.msg(e); }
      }
    });
  }

  async cargarTurnoActivo() {
    // 1. Verificar primero en almacenamiento transaccional local canónico
    try {
      const turnoLocal = await this.cajaService.obtenerTurnoLocal();
      if (turnoLocal && (turnoLocal.estado === 'ABIERTO' || turnoLocal.estado === 'CONCILIACION')) {
        this.turnoActivo = turnoLocal;
      }
    } catch {
      this.turnoActivo = null;
    }

    // 2. Consultar al servidor si hay conexión disponible
    if (navigator.onLine) {
      this.cajaService.consultarTurnoActivo(this.dispositivoId).subscribe({
        next: async t => {
          if (t && (t.estado === 'ABIERTO' || t.estado === 'CONCILIACION')) {
            if (t.cajero_id !== this.auth.obtenerUsuarioActual()?.id || t.dispositivo_id !== this.dispositivoId) {
              this.turnoPendienteRecuperacion = null;
              return; // Se consulta desde la lista de supervisión, no se persiste como caja propia.
            }
            if (this.turnoActivo && this.turnoActivo.turno_id === t.turno_id) {
              t.ultima_secuencia_local = this.turnoActivo.ultima_secuencia_local ?? 0;
              t.total_operaciones_locales = this.turnoActivo.total_operaciones_locales ?? 0;
            }
            try {
              await this.cajaService.guardarTurnoLocal(t);
              this.turnoActivo = await this.cajaService.obtenerTurnoLocal();
              this.turnoPendienteRecuperacion = null;
              this.recuperarOrdenActivaCaja();
            } catch {
              if (!this.turnoActivo) {
                this.turnoPendienteRecuperacion = t;
                this.error = 'Alerta de almacenamiento local: el turno existe en el servidor pero no pudo persistirse en este dispositivo. Reintente la persistencia antes de operar.';
              }
            }
          } else if (!t) {
            try {
              await this.cajaService.limpiarTurnoLocal();
            } catch {}
            this.turnoActivo = null;
            this.turnoPendienteRecuperacion = null;
          }
        },
        error: async (err) => {
          if ([401, 403, 404].includes(err?.status)) {
            try { await this.cajaService.limpiarTurnoLocal(); } catch {} this.turnoActivo = null;
            this.error = 'La caja requiere reautorizacion online. Se conservan los pendientes.';
          }
          // Si falla conexión, mantenemos el turno local
        }
      });
    }
  }

  async actualizarContadorPendientes() {
    const pendientes = await this.cajaService.obtenerVentasOfflinePendientes();
    this.ventasPendientesSync = pendientes ? pendientes.length : 0;
    this.pendientesPorVariante = {};
    for (const p of pendientes || []) if (p['turno_id'] === this.turnoActivo?.turno_id) {
      for (const l of p['cuerpo']?.lineas || []) {
        this.pendientesPorVariante[l.variante_id] = (this.pendientesPorVariante[l.variante_id] || 0) + l.cantidad;
      }
    }
  }

  /**
   * Recupera la orden de pago Stripe activa (CU19/CU22) tras recarga de página (F5) o reconexión,
   * sin guardar credenciales ni datos de tarjeta en almacenamiento local.
   */
  recuperarOrdenActivaCaja(): void {
    if (!this.stripeService) return;
    const u = this.auth.obtenerUsuarioActual();
    const sucursalId = u?.sucursal_id || (this.turnoActivo ? this.turnoActivo.sucursal_id : undefined);
    const turnoCajaId = this.turnoActivo?.turno_id || undefined;

    this.stripeService.obtenerOrdenActivaCaja(sucursalId, turnoCajaId).subscribe({
      next: (orden: OrdenActivaCajaDTO | null) => {
        if (!orden) return;

        // Manejo de cambio de turno o turno no coincidente
        if (
          orden.procedencia === 'TURNO_OFFLINE' &&
          orden.turno_caja_id &&
          this.turnoActivo &&
          orden.turno_caja_id !== this.turnoActivo.turno_id
        ) {
          this.error = 'La orden activa recuperada pertenece a otro turno de caja. Debe conciliar el turno anterior antes de continuar.';
          return;
        }

        if (orden.procedencia === 'TURNO_OFFLINE') {
          this.vistaModo = 'TURNO_OFFLINE';
          this.ordenStripeCaja = orden;
          this.medioPagoCaja = 'STRIPE_TEST';

          if (orden.lineas && orden.lineas.length) {
            this.lineasVentaOffline = orden.lineas.map(l => {
              const item: { variante_id: string; cantidad: number; precio_bob: number; descuento_bob?: number } = {
                variante_id: l.variante_id,
                cantidad: l.cantidad,
                precio_bob: Number(l.precio_unitario_bob) || 0
              };
              if (l.descuento_bob && Number(l.descuento_bob) > 0) {
                item.descuento_bob = Number(l.descuento_bob);
              }
              return item;
            });
          }
          if (orden.cliente_id) {
            this.clienteIdCaja = orden.cliente_id;
          }

          if (orden.estado_verificacion === 'NO_VERIFICADO_ERROR_PASARELA') {
            this.error = 'No se pudo verificar el estado en Stripe por problema de red. Reintente la verificación antes de cobrar.';
          } else if (this.esOrdenProvisional(orden)) {
            this.desmontarCardElementCaja();
            if (this.error.includes('No se pudo verificar el estado en Stripe')) {
              this.error = '';
            }
          } else {
            if (this.error.includes('No se pudo verificar el estado en Stripe')) {
              this.error = '';
            }
            if (orden.estado_orden === 'CAPTURADO') {
              this.desmontarCardElementCaja();
            } else if (orden.client_secret) {
              this.montarCardElementCaja();
            }
          }
        } else {
          // PRESENCIAL
          this.vistaModo = 'RESERVA';
          this.ordenStripePresencial = orden;
          this.metodo = 'STRIPE_TEST';

          if (orden.lineas && orden.lineas.length) {
            this.items = orden.lineas.map(l => ({
              variante_id: l.variante_id,
              cantidad: l.cantidad
            }));
          }
          if (orden.cliente_id) {
            this.clienteIdPresencial = orden.cliente_id;
          }

          if (orden.estado_verificacion === 'NO_VERIFICADO_ERROR_PASARELA') {
            this.error = 'No se pudo verificar el estado en Stripe por problema de red. Reintente la verificación antes de cobrar.';
          } else if (this.esOrdenProvisional(orden)) {
            this.desmontarCardElementPresencial();
            if (this.error.includes('No se pudo verificar el estado en Stripe')) {
              this.error = '';
            }
          } else {
            if (this.error.includes('No se pudo verificar el estado en Stripe')) {
              this.error = '';
            }
            if (orden.estado_orden === 'CAPTURADO') {
              this.desmontarCardElementPresencial();
            } else if (orden.client_secret) {
              this.montarCardElementPresencial();
            }
          }
        }
      },
      error: () => {
        // Silenciar fallos de recuperación o 404 para no interrumpir al cajero
      }
    });
  }

  esOrdenProvisional(orden: OrdenActivaCajaDTO | IniciarVentaPresencialStripeRespuestaDTO | null): boolean {
    if (!orden) return false;
    return orden.estado_verificacion === 'PROVISIONAL_PENDIENTE_INTENTO' || !orden.stripe_payment_intent_id;
  }

  reanudarCobroStripeCaja(): void {
    if (!this.ordenStripeCaja || !this.stripeService) return;
    this.reanudandoStripeCaja = true;
    this.error = '';
    this.mensajeExito = '';

    const ordenPagoId = this.ordenStripeCaja.orden_pago_id;
    this.stripeService.reanudarOrdenPago(ordenPagoId).subscribe({
      next: (resp: any) => {
        this.reanudandoStripeCaja = false;
        if (this.ordenStripeCaja && this.ordenStripeCaja.orden_pago_id === ordenPagoId) {
          this.ordenStripeCaja.client_secret = resp.client_secret || this.ordenStripeCaja.client_secret;
          this.ordenStripeCaja.stripe_payment_intent_id = resp.referencia_externa || resp.stripe_payment_intent_id || resp.payment_intent_id || this.ordenStripeCaja.stripe_payment_intent_id;
          this.ordenStripeCaja.estado_verificacion = 'VERIFICADO';
          if (resp.estado || resp.estado_orden) {
            this.ordenStripeCaja.estado_orden = resp.estado || resp.estado_orden;
          }
          this.mensajeExito = 'Orden de pago reanudada exitosamente. Complete los datos de tarjeta para confirmar el cobro.';
          if (this.ordenStripeCaja.estado_orden === 'CAPTURADO') {
            this.desmontarCardElementCaja();
          } else if (this.ordenStripeCaja.client_secret) {
            this.montarCardElementCaja();
          }
        }
      },
      error: (err: any) => {
        this.reanudandoStripeCaja = false;
        this.error = this.msg(err);
      }
    });
  }

  reanudarCobroStripePresencial(): void {
    if (!this.ordenStripePresencial || !this.stripeService) return;
    this.reanudandoStripePresencial = true;
    this.error = '';
    this.mensajeExito = '';

    const ordenPagoId = this.ordenStripePresencial.orden_pago_id;
    this.stripeService.reanudarOrdenPago(ordenPagoId).subscribe({
      next: (resp: any) => {
        this.reanudandoStripePresencial = false;
        if (this.ordenStripePresencial && this.ordenStripePresencial.orden_pago_id === ordenPagoId) {
          this.ordenStripePresencial.client_secret = resp.client_secret || this.ordenStripePresencial.client_secret;
          this.ordenStripePresencial.stripe_payment_intent_id = resp.referencia_externa || resp.stripe_payment_intent_id || resp.payment_intent_id || this.ordenStripePresencial.stripe_payment_intent_id;
          this.ordenStripePresencial.estado_verificacion = 'VERIFICADO';
          if (resp.estado || resp.estado_orden) {
            this.ordenStripePresencial.estado_orden = resp.estado || resp.estado_orden;
          }
          this.mensajeExito = 'Orden de pago reanudada exitosamente. Complete los datos de tarjeta para confirmar el cobro.';
          if (this.ordenStripePresencial.estado_orden === 'CAPTURADO') {
            this.desmontarCardElementPresencial();
          } else if (this.ordenStripePresencial.client_secret) {
            this.montarCardElementPresencial();
          }
        }
      },
      error: (err: any) => {
        this.reanudandoStripePresencial = false;
        this.error = this.msg(err);
      }
    });
  }

  reintentarVerificacionOrdenActiva(): void {
    this.error = '';
    this.recuperarOrdenActivaCaja();
  }

  // --- Habilitación de Turno y Cupos ---
  agregarCupoSolicitado() {
    this.error = '';
    if (!this.cupoVarianteSeleccionada) {
      this.error = 'Seleccione una prenda para solicitar cupo.';
      return;
    }
    if (!Number.isInteger(this.cupoCantidadSolicitada) || this.cupoCantidadSolicitada < 1) {
      this.error = 'La cantidad debe ser mayor a 0.';
      return;
    }
    const existente = this.cuposSolicitados.find(c => c.variante_id === this.cupoVarianteSeleccionada);
    if (existente) {
      existente.cantidad += this.cupoCantidadSolicitada;
    } else {
      this.cuposSolicitados.push({
        variante_id: this.cupoVarianteSeleccionada,
        cantidad: this.cupoCantidadSolicitada
      });
    }
    this.cupoVarianteSeleccionada = '';
    this.cupoCantidadSolicitada = 1;
  }

  quitarCupoSolicitado(index: number) {
    this.cuposSolicitados.splice(index, 1);
  }

  abrirTurno() {
    const u = this.auth.obtenerUsuarioActual();
    const cajero = this.cajeros.find(c => c.id === this.cajeroSeleccionado);
    const sucursalId = this.puedeAsignarCajero && cajero ? cajero.sucursal_id : u?.sucursal_id;
    this.error = '';
    this.mensajeExito = '';

    if (!sucursalId) {
      this.error = 'El usuario no tiene una sucursal asignada para operar en caja.';
      return;
    }
    if (!this.cajaId.trim()) {
      this.error = 'Ingrese un código identificador para la caja.';
      return;
    }
    if (!this.cuposSolicitados.length) {
      this.error = 'Debe solicitar al menos un cupo exclusivo de prendas para operar la caja.';
      return;
    }
    if (!navigator.onLine || this.cuposSolicitados.some(c => !Number.isInteger(c.cantidad) || c.cantidad < 1)) {
      this.error = 'La habilitación requiere conexión y cantidades enteras positivas en todas las líneas.';
      return;
    }

    this.procesando = true;
    this.cajaService.habilitarTurno({
      caja_id: this.cajaId.trim(),
      dispositivo_id: this.dispositivoId,
      sucursal_id: sucursalId,
      cajero_id: this.puedeAsignarCajero && cajero ? cajero.id : undefined,
      cupos: this.cuposSolicitados,
      revision: 1
    }).subscribe({
      next: async turno => {
        if (!u?.id || turno.cajero_id !== (cajero?.id || u.id) || turno.dispositivo_id !== this.dispositivoId || turno.sucursal_id !== sucursalId) {
          this.error = 'La habilitación recibida no coincide con el cajero, sucursal y dispositivo solicitados. Requiere revisión central.';
          this.procesando = false;
          return;
        }
        if (turno.cajero_id !== u?.id) {
          this.cuposSolicitados = [];
          this.mensajeExito = `Caja ${turno.caja_codigo} asignada. El cajero debe iniciar sesión EN ESTE DISPOSITIVO con conexión y guardar el turno antes de vender offline.`;
          this.procesando = false;
          return;
        }
        turno.ultima_secuencia_local = 0;
        turno.total_operaciones_locales = 0;
        await this.persistirTurnoLocalmente(turno);
        this.procesando = false;
      },
      error: err => {
        this.error = this.msg(err);
        this.procesando = false;
      }
    });
  }

  habilitarTurno() {
    return this.abrirTurno();
  }

  async persistirTurnoLocalmente(turno: TurnoHabilitacion): Promise<boolean> {
    try {
      await this.cajaService.guardarTurnoLocal(turno);
      this.turnoActivo = await this.cajaService.obtenerTurnoLocal();
      this.turnoPendienteRecuperacion = null;
      this.cuposSolicitados = [];
      this.mensajeExito = `Caja ${turno.caja_codigo} habilitada exitosamente con vigencia de 8 horas.`;
      this.error = '';
      this.recuperarOrdenActivaCaja();
      return true;
    } catch (errPersistencia) {
      this.turnoActivo = null;
      this.turnoPendienteRecuperacion = turno;
      this.error = 'Error de almacenamiento local: no se pudo guardar el turno en el almacenamiento transaccional del dispositivo. El turno fue reservado en el servidor pero la caja no está lista ni puede operar offline. Puede reintentar la persistencia local sin volver a solicitar cupos.';
      return false;
    }
  }

  async reintentarPersistenciaTurno(): Promise<void> {
    if (!this.turnoPendienteRecuperacion) return;
    this.procesando = true;
    this.error = '';
    await this.persistirTurnoLocalmente(this.turnoPendienteRecuperacion);
    this.procesando = false;
  }

  cancelarTurnoPendiente(): void {
    this.turnoPendienteRecuperacion = null;
    this.error = '';
  }

  // --- Venta Contado Offline ---
  agregarLineaVentaOffline() {
    this.error = '';
    if (!this.varianteVentaOffline) {
      this.error = 'Seleccione una prenda del inventario de caja.';
      return;
    }
    if (!Number.isInteger(this.cantidadVentaOffline) || this.cantidadVentaOffline < 1) {
      this.error = 'La cantidad debe ser mayor a 0.';
      return;
    }

    const cupo = this.obtenerCupo(this.varianteVentaOffline);
    if (!cupo) {
      this.error = 'La prenda seleccionada no cuenta con cupo en este turno.';
      return;
    }

    const disponibleCupo = cupo.otorgado - cupo.consumido - cupo.liberado - (cupo.mermado || 0);
    const yaEnVenta = this.lineasVentaOffline
      .filter(l => l.variante_id === this.varianteVentaOffline)
      .reduce((acc, l) => acc + l.cantidad, 0);

    if (yaEnVenta + this.cantidadVentaOffline > disponibleCupo) {
      this.error = `Cupo insuficiente en caja: quedan ${disponibleCupo - yaEnVenta} unidades disponibles.`;
      return;
    }

    const precio = Number(cupo.precio_autorizado_bob) || 0;
    const existente = this.lineasVentaOffline.find(l => l.variante_id === this.varianteVentaOffline);
    if (existente) existente.cantidad += this.cantidadVentaOffline;
    else this.lineasVentaOffline.push({
      variante_id: this.varianteVentaOffline,
      cantidad: this.cantidadVentaOffline,
      precio_bob: precio
    });

    this.varianteVentaOffline = '';
    this.cantidadVentaOffline = 1;
    this.calcularCambio();
  }

  quitarLineaVentaOffline(index: number) {
    this.lineasVentaOffline.splice(index, 1);
    this.calcularCambio();
  }

  totalVentaOffline(): number {
    return this.lineasVentaOffline.reduce((acc, l) => acc + (l.cantidad * l.precio_bob), 0);
  }

  calcularCambio() {
    const total = this.totalVentaOffline();
    if (this.efectivoRecibido >= total) {
      this.cambioEntregado = Math.round((this.efectivoRecibido - total) * 100) / 100;
    } else {
      this.cambioEntregado = 0;
    }
  }

  async obtenerOInicializarStripe(): Promise<any> {
    if (this.stripeInstance) return this.stripeInstance;
    if (!this.stripeService) {
      throw new Error('El servicio de pasarela de pagos Stripe no está disponible.');
    }
    try {
      const StripeConstructor = (await this.stripeService.cargarStripeJs()) as (key: string) => any;
      if (typeof StripeConstructor === 'function') {
        this.stripeInstance = StripeConstructor(environment.stripePublicKey);
        return this.stripeInstance;
      }
    } catch {
      const win = typeof window !== 'undefined' ? (window as any) : {};
      if (typeof win['Stripe'] === 'function') {
        this.stripeInstance = win['Stripe'](environment.stripePublicKey);
        return this.stripeInstance;
      }
    }
    throw new Error('No se pudo cargar la pasarela segura de Stripe. Verifica tu conexión.');
  }

  async montarCardElementCaja(): Promise<void> {
    this.desmontarCardElementCaja();
    this.cardElementCajaValido = false;
    this.errorTarjetaCaja = null;
    this.cargandoStripeCaja = true;

    try {
      const stripe = await this.obtenerOInicializarStripe();
      const elements = stripe.elements();
      this.cardElementCaja = elements.create('card', {
        hidePostalCode: true,
        style: {
          base: {
            fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
            fontSize: '16px',
            color: '#1c1b1f',
            '::placeholder': { color: '#79747e' }
          },
          invalid: {
            color: '#b3261e',
            iconColor: '#b3261e'
          }
        }
      });

      await new Promise(resolve => setTimeout(resolve, 0));

      const mountSelector = '#stripe-card-element-caja';
      const container = typeof document !== 'undefined' ? document.querySelector(mountSelector) : null;
      if (!container) {
        throw new Error('No se encontró el contenedor de tarjeta para caja.');
      }

      this.cardElementCaja.mount(mountSelector);
      this.cardElementCaja.on('change', (event: any) => {
        this.cardElementCajaValido = !!(event && event.complete && !event.error);
        this.errorTarjetaCaja = event?.error?.message || null;
      });
    } catch (err: any) {
      this.errorTarjetaCaja = err?.message || 'Error al inicializar el campo seguro de tarjeta.';
      this.cardElementCajaValido = false;
    } finally {
      this.cargandoStripeCaja = false;
    }
  }

  desmontarCardElementCaja(): void {
    if (this.cardElementCaja) {
      try {
        if (typeof this.cardElementCaja.destroy === 'function') {
          this.cardElementCaja.destroy();
        }
      } catch {}
      this.cardElementCaja = null;
    }
    this.cardElementCajaValido = false;
    this.errorTarjetaCaja = null;
  }

  iniciarStripeCaja(): void {
    if (this.supervisandoTurno) { this.error = 'La consulta de supervisión no habilita ventas.'; return; }
    if (!this.turnoActivo) {
      this.error = 'No hay un turno de caja activo para procesar ventas.';
      return;
    }
    if (!this.lineasVentaOffline.length) {
      this.error = 'Agregue al menos una prenda a la venta.';
      return;
    }
    this.iniciandoStripeCaja = true;
    this.error = '';

    const u = this.auth.obtenerUsuarioActual();
    const sucursalId = u?.sucursal_id || this.turnoActivo.sucursal_id;

    this.api.iniciarVentaPresencialStripe({
      sucursal_id: sucursalId,
      cliente_id: this.clienteIdCaja.trim() || null,
      turno_caja_id: this.turnoActivo.turno_id,
      lineas: this.lineasVentaOffline.map(l => ({
        variante_id: l.variante_id,
        cantidad: l.cantidad,
        precio_unitario_bob: l.precio_bob,
        descuento_bob: 0
      }))
    }).subscribe({
      next: resp => {
        this.ordenStripeCaja = resp;
        this.iniciandoStripeCaja = false;
        if (resp && resp.estado_orden !== 'CAPTURADO') {
          this.montarCardElementCaja();
        }
      },
      error: err => {
        this.error = this.msg(err);
        this.iniciandoStripeCaja = false;
      }
    });
  }

  async capturarStripeCaja(): Promise<void> {
    if (!this.ordenStripeCaja || this.capturandoStripeCaja) return;
    this.capturandoStripeCaja = true;
    this.error = '';
    this.errorTarjetaCaja = null;

    if (!this.stripeService) {
      this.error = 'El servicio de pasarela de pagos Stripe no está disponible.';
      this.capturandoStripeCaja = false;
      return;
    }

    const orden = this.ordenStripeCaja;

    if (orden.estado_orden === 'CAPTURADO') {
      this.capturandoStripeCaja = false;
      return;
    }

    if (!this.cardElementCaja && orden.estado_orden !== 'REQUIERE_ACCION_CLIENTE') {
      this.errorTarjetaCaja = 'Complete los datos de la tarjeta antes de confirmar.';
      this.error = this.errorTarjetaCaja;
      this.capturandoStripeCaja = false;
      return;
    }

    try {
      const stripe = await this.obtenerOInicializarStripe();

      if (orden.estado_orden === 'REQUIERE_ACCION_CLIENTE' && !this.cardElementCaja) {
        this.stripeService.continuarAccion(orden.orden_pago_id, {
          payment_intent_id: orden.stripe_payment_intent_id || ''
        }).subscribe({
          next: accResp => {
            if (accResp && accResp.estado === 'CAPTURADO') {
              if (this.ordenStripeCaja) this.ordenStripeCaja.estado_orden = 'CAPTURADO';
              this.mensajeExito = 'Pago con tarjeta capturado exitosamente.';
            } else {
              if (this.ordenStripeCaja) this.ordenStripeCaja.estado_orden = (accResp?.estado as any) || 'PENDIENTE';
              this.error = `La orden continúa en estado ${accResp?.estado || 'PENDIENTE'}.`;
            }
            this.capturandoStripeCaja = false;
          },
          error: accErr => {
            if (this.ordenStripeCaja) this.ordenStripeCaja.estado_orden = 'FALLIDO';
            this.error = this.msg(accErr);
            this.capturandoStripeCaja = false;
          }
        });
        return;
      }

      if (!orden.client_secret) {
        this.error = 'No se encontró el secreto de cliente para procesar la tarjeta.';
        this.capturandoStripeCaja = false;
        return;
      }

      const confirmResult = await stripe.confirmCardPayment(orden.client_secret, {
        payment_method: {
          card: this.cardElementCaja
        }
      });

      if (confirmResult?.error) {
        const msgError = confirmResult.error.message || 'La tarjeta fue rechazada por la pasarela de pagos.';
        this.errorTarjetaCaja = msgError;
        this.error = msgError;
        this.capturandoStripeCaja = false;
        return;
      }

      const pi = confirmResult?.paymentIntent;
      if (pi?.status === 'requires_action') {
        this.ordenStripeCaja.estado_orden = 'REQUIERE_ACCION_CLIENTE';
        this.error = 'La tarjeta requiere verificación 3D Secure / SCA adicional.';
        this.capturandoStripeCaja = false;
        return;
      }

      if (pi?.status === 'succeeded' || pi?.status === 'requires_capture') {
        this.stripeService.confirmarOrdenPago(orden.orden_pago_id).subscribe({
          next: confResp => {
            if (confResp && confResp.estado === 'CAPTURADO') {
              if (this.ordenStripeCaja) {
                this.ordenStripeCaja.estado_orden = 'CAPTURADO';
              }
              this.desmontarCardElementCaja();
              this.mensajeExito = 'Pago con tarjeta capturado y verificado centralmente con éxito.';
            } else {
              this.error = `La orden fue procesada por Stripe pero el backend reporta estado: ${confResp?.estado || 'PENDIENTE'}. Puede reintentar la confirmación.`;
            }
            this.capturandoStripeCaja = false;
          },
          error: confErr => {
            this.error = `El cobro fue aceptado por Stripe pero ocurrió un error al confirmar con el servidor: ${this.msg(confErr)}. No repita el cobro; reintente la confirmación.`;
            this.capturandoStripeCaja = false;
          }
        });
      } else {
        const estadoInesperado = pi?.status || 'desconocido';
        this.error = `Stripe reportó un estado no concluido: ${estadoInesperado}. Verifique el método de pago.`;
        this.capturandoStripeCaja = false;
      }
    } catch (err: any) {
      this.error = err?.message || 'Error inesperado al procesar la tarjeta con Stripe.';
      this.capturandoStripeCaja = false;
    }
  }

  cancelarStripeCaja(): void {
    if (!this.ordenStripeCaja) return;
    const orden = this.ordenStripeCaja;

    if (orden.estado_orden === 'CAPTURADO') {
      this.error = 'No se puede cancelar una orden con cobro ya capturado en la pasarela. Debe liquidar la venta o solicitar un reembolso formal.';
      return;
    }

    if (this.stripeService && (orden.estado_orden === 'PENDIENTE' || orden.estado_orden === 'REQUIERE_ACCION_CLIENTE')) {
      this.procesando = true;
      this.stripeService.cancelarOrdenPago(orden.orden_pago_id).subscribe({
        next: () => {
          this.desmontarCardElementCaja();
          this.ordenStripeCaja = null;
          this.procesando = false;
        },
        error: err => {
          // H3: Preservar ordenStripeCaja visible ante fallos (409/502/timeout). No desmontar CardElement ni anular orden.
          this.error = this.msg(err);
          this.procesando = false;
        }
      });
      return;
    }

    this.desmontarCardElementCaja();
    this.ordenStripeCaja = null;
  }

  reintentarConfirmacionStripeCaja(): void {
    if (!this.ordenStripeCaja || !this.stripeService) return;
    this.capturandoStripeCaja = true;
    this.stripeService.confirmarOrdenPago(this.ordenStripeCaja.orden_pago_id).subscribe({
      next: resp => {
        if (resp && resp.estado === 'CAPTURADO') {
          if (this.ordenStripeCaja) this.ordenStripeCaja.estado_orden = 'CAPTURADO';
          this.desmontarCardElementCaja();
          this.mensajeExito = 'Pago confirmado centralmente.';
        }
        this.capturandoStripeCaja = false;
      },
      error: err => {
        this.error = this.msg(err);
        this.capturandoStripeCaja = false;
      }
    });
  }

  async cobrarVentaContado() {
    if (this.supervisandoTurno) { this.error = 'La consulta de supervisión no habilita ventas.'; return; }
    this.error = '';
    this.mensajeExito = '';
    if (!this.turnoActivo) {
      this.error = 'No hay un turno de caja activo para procesar ventas.';
      return;
    }
    if (!this.lineasVentaOffline.length) {
      this.error = 'Agregue al menos una prenda a la venta.';
      return;
    }

    // Liquidación con saldo o tarjeta conectada (CU19)
    if (this.medioPagoCaja === 'SALDO' || this.medioPagoCaja === 'STRIPE_TEST') {
      if (!navigator.onLine) {
        this.error = 'La liquidación con saldo o tarjeta requiere conexión con el servidor central para verificar y capturar los fondos.';
        return;
      }
      if (this.medioPagoCaja === 'SALDO' && !this.clienteIdCaja.trim()) {
        this.error = 'La liquidación con saldo requiere indicar el identificador del cliente.';
        return;
      }
      if (this.medioPagoCaja === 'STRIPE_TEST') {
        if (!this.ordenStripeCaja) {
          this.error = 'Debe iniciar el cobro con tarjeta Stripe antes de liquidar.';
          return;
        }
        if (this.ordenStripeCaja.estado_orden !== 'CAPTURADO') {
          this.error = 'La orden de pago Stripe debe estar en estado CAPTURADO antes de liquidar.';
          return;
        }
      }

      this.procesando = true;
      const u = this.auth.obtenerUsuarioActual();
      const sucursalId = u?.sucursal_id || this.turnoActivo?.sucursal_id || (this.ordenStripeCaja as OrdenActivaCajaDTO)?.sucursal_id || '';

      const dto: VentaPresencialLiquidarDTO = {
        venta_id: this.ordenStripeCaja?.venta_id,
        orden_pago_id: this.ordenStripeCaja?.orden_pago_id,
        sucursal_id: sucursalId,
        lineas: this.lineasVentaOffline.map(l => {
          const linea: LineaVentaPresencialDTO = {
            variante_id: l.variante_id,
            cantidad: l.cantidad,
            precio_unitario_bob: l.precio_bob
          };
          if (l.descuento_bob && l.descuento_bob > 0) {
            linea.descuento_bob = l.descuento_bob;
          }
          return linea;
        }),
        medio_pago: this.medioPagoCaja,
        cliente_id: this.clienteIdCaja.trim() || (this.ordenStripeCaja as OrdenActivaCajaDTO)?.cliente_id || undefined,
        stripe_payment_intent_id: this.ordenStripeCaja?.stripe_payment_intent_id,
        turno_caja_id: this.turnoActivo?.turno_id || (this.ordenStripeCaja as OrdenActivaCajaDTO)?.turno_caja_id || undefined
      };

      this.api.liquidarVentaPresencial(dto).subscribe({
        next: async resp => {
          if (this.turnoActivo?.cupos) {
            for (const l of this.lineasVentaOffline) {
              const c = this.turnoActivo.cupos.find(cupo => cupo.variante_id === l.variante_id);
              if (c) c.consumido += l.cantidad;
            }
            await this.cajaService.guardarTurnoLocal(this.turnoActivo);
          }

          this.comprobanteOffline = {
            operacion_id: resp.venta_id,
            numero: resp.numero,
            fecha: resp.fecha_hora || new Date().toISOString(),
            lineas: this.lineasVentaOffline.map(l => ({
              sku: this.v(l.variante_id),
              cantidad: l.cantidad,
              subtotal: l.cantidad * l.precio_bob
            })),
            total: Number(resp.total_bob),
            efectivo: Number(resp.total_bob),
            cambio: Number(resp.cambio_entregado_bob || 0),
            esOffline: false
          };
          this.desmontarCardElementCaja();
          this.ordenStripeCaja = null;
          this.limpiarFormularioVentaOffline();
          this.procesando = false;
        },
        error: err => {
          this.error = this.msg(err);
          this.procesando = false;
        }
      });
      return;
    }

    const total = this.totalVentaOffline();
    if (this.efectivoRecibido < total) {
      this.error = 'El efectivo recibido es menor al total de la venta.';
      return;
    }

    this.procesando = true;

    // Preservar el mismo operacion_id si se reintenta tras un fallo de almacenamiento
    if (!this.operacionIdActual) {
      this.operacionIdActual = crypto.randomUUID();
    }
    const operacionId = this.operacionIdActual;
    const ahoraIso = new Date().toISOString();

    const ventaDto: VentaOfflineCrear = {
      operacion_id: operacionId,
      secuencia_local: 0,
      vendida_local_en: ahoraIso,
      entregada_local_en: ahoraIso,
      version_precios: this.turnoActivo.version_precios,
      lineas: this.lineasVentaOffline.map(l => ({
        variante_id: l.variante_id,
        cantidad: l.cantidad,
        precio_autorizado_bob: l.precio_bob
      })),
      total_bob: total,
      efectivo_recibido_bob: this.efectivoRecibido,
      cambio_entregado_bob: this.cambioEntregado
    };

    // Preparar comprobante local durable
    const comprobanteInfo: ComprobanteCajaOffline = {
      operacion_id: operacionId,
      numero: `VNT-OFF-${operacionId.substring(0, 6).toUpperCase()}`,
      fecha: ahoraIso,
      lineas: this.lineasVentaOffline.map(l => ({
        sku: this.v(l.variante_id),
        cantidad: l.cantidad,
        subtotal: l.cantidad * l.precio_bob
      })),
      total: total,
      efectivo: this.efectivoRecibido,
      cambio: this.cambioEntregado,
      esOffline: true // El registro local aun no tiene confirmacion central.
    };

    // La transaccion relee el balance durable y asigna la secuencia; no guarda una copia obsoleta.
    let registrado;
    try {
      registrado = await this.cajaService.registrarVentaOfflineTransaccional(this.turnoActivo, ventaDto, comprobanteInfo);
    } catch (e: any) {
      this.procesando = false;
      this.comprobanteOffline = undefined;
      this.error = e?.message || 'No se pudo persistir la venta. No entregue prendas sin registro durable.';
      return;
    }
    this.turnoActivo = registrado.turno;
    Object.assign(ventaDto, registrado.venta);
    comprobanteInfo.fecha = registrado.venta.vendida_local_en;
    this.operacionIdActual = null;

    if (navigator.onLine) {
      this.cajaService.registrarVentaOffline(this.turnoActivo.turno_id, ventaDto).subscribe({
        next: async (resultado) => {
          if (resultado.resultado !== 'REGISTRADA_CENTRAL') this.error = 'Cobro local conservado; requiere conciliacion central.';
          await this.actualizarContadorPendientes();
          this.comprobanteOffline = { ...comprobanteInfo, esOffline: resultado.resultado !== 'REGISTRADA_CENTRAL' };
          this.limpiarFormularioVentaOffline();
          this.procesando = false;
        },
        error: async () => {
          // Si falla la sincronización por red, la venta ya está segura en la base de datos local
          await this.actualizarContadorPendientes();
          this.comprobanteOffline = { ...comprobanteInfo, esOffline: true };
          this.limpiarFormularioVentaOffline();
          this.procesando = false;
        }
      });
    } else {
      await this.actualizarContadorPendientes();
      this.comprobanteOffline = { ...comprobanteInfo, esOffline: true };
      this.limpiarFormularioVentaOffline();
      this.procesando = false;
    }
  }

  liquidarVentaOffline(): Promise<void> {
    return this.cobrarVentaContado();
  }

  limpiarFormularioVentaOffline() {
    this.lineasVentaOffline = [];
    this.efectivoRecibido = 0;
    this.cambioEntregado = 0;
    this.operacionIdActual = null;
  }

  nuevaVentaOffline() {
    this.comprobanteOffline = undefined;
    this.limpiarFormularioVentaOffline();
  }

  // --- Sincronización y Cierre de Turno ---
  async sincronizarVentasPendientes() {
    this.procesando = true;
    try {
      const r = await this.cajaService.sincronizarPendientes();
      await this.actualizarContadorPendientes();
      this.mensajeExito = `${r.completadas} venta(s) registradas centralmente; ${r.pendientes} pendientes de resolucion.`;
      if (this.turnoActivo) await this.refrescarTurnoCentral();
    } catch (e: any) { this.error = e?.message || this.msg(e); }
    finally { this.procesando = false; }
  }

  async recuperarPendientesSupervisados() {
    this.procesando = true;
    try {
      const n = await this.cajaService.recuperarPendientesSupervisados(this.turnoRecuperacionId.trim());
      this.mensajeExito = `${n} operaciones originales registradas centralmente; las restantes se conservan para conciliacion.`;
      await this.actualizarContadorPendientes();
    } catch (e: any) { this.error = e?.message || this.msg(e); }
    finally { this.procesando = false; }
  }

  private async refrescarTurnoCentral(): Promise<void> {
    const turnoActual = this.turnoActivo;
    if (!turnoActual) return;
    try {
      const actualizado = await firstValueFrom(this.cajaService.consultarTurno(turnoActual.turno_id));
      actualizado.ultima_secuencia_local = turnoActual.ultima_secuencia_local ?? 0;
      actualizado.total_operaciones_locales = turnoActual.total_operaciones_locales ?? 0;
      await this.cajaService.guardarTurnoLocal(actualizado);
      this.turnoActivo = await this.cajaService.obtenerTurnoLocal();
    } catch {
      this.error = 'Las ventas se sincronizaron, pero no se pudo actualizar el estado central del turno. Recarga el turno antes de cerrar.';
    }
  }

  get puedeSupervisarCierre(): boolean {
    const rol = this.auth.obtenerUsuarioActual()?.rol;
    return ['ADMINISTRADOR', 'PROPIETARIO', 'ENCARGADO'].includes(rol || '');
  }

  get cuposConFaltanteFisico(): CupoRespuesta[] {
    if (!this.turnoActivo) return [];
    return this.turnoActivo.cupos.filter(cupo => {
      const remanente = Math.max(0, cupo.otorgado - cupo.consumido - cupo.liberado - (cupo.mermado || 0));
      const encontrado = this.conteoFisicoPorVariante[cupo.variante_id];
      return encontrado !== null && encontrado !== undefined && encontrado < remanente;
    });
  }

  get formularioSupervisionValido(): boolean {
    if (!this.turnoActivo || !this.cierreSupervisado) return true;
    if (this.referenciaActa.trim().length < 3 || this.motivoSupervision.trim().length < 10) return false;
    if (!Number.isFinite(this.arqueoEfectivoBob) || this.arqueoEfectivoBob < 0) return false;
    const conteoValido = this.turnoActivo.cupos.every(cupo => {
      const cantidad = this.conteoFisicoPorVariante[cupo.variante_id];
      const remanente = Math.max(0, cupo.otorgado - cupo.consumido - cupo.liberado - (cupo.mermado || 0));
      return Number.isInteger(cantidad) && cantidad! >= 0 && cantidad! <= remanente;
    });
    if (!conteoValido) return false;
    return this.cuposConFaltanteFisico.every(cupo => {
      const resolucion = this.resolucionFaltantePorVariante[cupo.variante_id];
      const motivo = this.motivoFaltantePorVariante[cupo.variante_id]?.trim() || '';
      return !!resolucion && motivo.length >= 10;
    });
  }

  abrirModalCierre(supervisado = false) {
    this.error = '';
    this.mensajeExito = '';
    this.arqueoEfectivoBob = 0;
    this.cierreSupervisado = supervisado;
    this.motivoSupervision = '';
    this.referenciaActa = '';
    this.conteoFisicoPorVariante = {};
    this.resolucionFaltantePorVariante = {};
    this.motivoFaltantePorVariante = {};
    if (supervisado && this.turnoActivo) {
      for (const cupo of this.turnoActivo.cupos) {
        this.conteoFisicoPorVariante[cupo.variante_id] = null;
      }
    }
    this.mostrarDialogoCierre = true;
  }

  cancelarCierre() {
    this.mostrarDialogoCierre = false;
    this.cierreSupervisado = false;
    this.volverAMiCaja();
  }

  async confirmarCierreTurno() {
    if (this.cierreSupervisado && !this.formularioSupervisionValido) {
      this.error = 'Completa el acta, el arqueo y el conteo de cada prenda. Para cada faltante, indica si esperará una sincronización o si se registrará como merma con su motivo.';
      return;
    }
    this.mostrarDialogoCierre = false;
    await this.cerrarTurno(this.arqueoEfectivoBob);
  }

  async cerrarTurno(arqueoDirecto?: number) {
    if (!this.turnoActivo) return;
    try {
      await this.actualizarContadorPendientes();
      const pendientes = await this.cajaService.obtenerVentasOfflinePendientes(this.turnoActivo?.turno_id);
      const pendientesIds = pendientes.map(p => p.operacion_id);
      const arqueo = arqueoDirecto !== undefined ? arqueoDirecto : (this.arqueoEfectivoBob ?? 0);
      const turnoId = this.turnoActivo.turno_id;
      const dto: import('../services/caja.service').TurnoCerrar = {
        revision: this.turnoActivo.revision,
        ultima_secuencia_local: this.turnoActivo.ultima_secuencia_local ?? 0,
        total_operaciones_locales: this.turnoActivo.total_operaciones_locales ?? 0,
        operaciones_pendientes: pendientesIds,
        arqueo_efectivo_bob: arqueo
      };

      if (this.supervisandoTurno) {
        delete dto.ultima_secuencia_local;
        delete dto.total_operaciones_locales;
      }
      if (this.cierreSupervisado) {
        dto.supervision_forzada = true;
        dto.motivo_supervision = this.motivoSupervision.trim();
        // Per-variant evidence is authoritative; never globally discard a variant awaiting sync.
        dto.descarte_venta_fisica = false;
        dto.arqueo_declarado_bob = arqueo;
        dto.evidencia_cierre = {
          referencia_acta: this.referenciaActa.trim(),
          conteo_fisico_por_variante: this.turnoActivo.cupos.map(cupo => ({
            variante_id: cupo.variante_id,
            cantidad_encontrada: Number(this.conteoFisicoPorVariante[cupo.variante_id])
          }))
        };
        dto.ajustes_inventario = {
          resoluciones_por_variante: this.cuposConFaltanteFisico.map(cupo => ({
            variante_id: cupo.variante_id,
            resolucion: this.resolucionFaltantePorVariante[cupo.variante_id]!,
            motivo: this.motivoFaltantePorVariante[cupo.variante_id].trim()
          }))
        };
      }

      this.procesando = true;
      this.error = '';
      const resultado = await firstValueFrom(this.cajaService.cerrarTurno(turnoId, dto));
      this.procesando = false;
      if (resultado.estado === 'CERRADO') {
        const unidadesDevueltas = resultado.cupos_devueltos.reduce((total, cupo) => total + (cupo.devuelto || 0), 0);
        this.mensajeExito = `Turno cerrado. Se liberaron ${unidadesDevueltas} unidad(es) confirmadas por el conteo.`;
        if (this.supervisandoTurno) {
          this.volverAMiCaja();
          this.cierreSupervisado = false;
          this.cargarConciliaciones();
          return;
        }
        this.turnoActivo = null;
        this.turnoPendienteRecuperacion = null;
        this.cierreSupervisado = false;
        try {
          await this.cajaService.limpiarTurnoLocal();
        } catch {
          this.error = 'El turno se cerro en el servidor, pero no se pudo limpiar la copia local. Recarga la caja con conexion antes de operar.';
        }
        return;
      }

      // The response is an action summary. Refresh the central cupo balances before another resolution.
      const actualizado = await firstValueFrom(this.cajaService.consultarTurno(turnoId));
      if (this.supervisandoTurno) {
        this.turnoActivo = actualizado;
        this.cierreSupervisado = false;
        this.error = 'El turno conserva faltantes por conciliar. Revisa el resultado central y vuelve a registrar el conteo.';
        this.cargarConciliaciones();
        return;
      }
      actualizado.ultima_secuencia_local = this.turnoActivo.ultima_secuencia_local ?? 0;
      actualizado.total_operaciones_locales = this.turnoActivo.total_operaciones_locales ?? 0;
      await this.cajaService.guardarTurnoLocal(actualizado);
      this.turnoActivo = await this.cajaService.obtenerTurnoLocal();
      this.cierreSupervisado = false;
      const retenidos = resultado.cupos_retenidos?.reduce((total, cupo) => total + cupo.retenido, 0) || 0;
      this.error = retenidos > 0
        ? `El turno sigue en conciliacion con ${retenidos} prenda(s) retenida(s). Sincroniza las ventas tardias o registra un nuevo conteo supervisado.`
        : `El turno paso a conciliacion por ${pendientesIds.length} operacion(es) pendiente(s). Sincronizalas y vuelve a cerrar.`;
    } catch (err) {
      this.error = this.msg(err);
      this.procesando = false;
    }
  }

  async recuperarTurno() {
    const turno = this.turnoActivo || this.turnoPendienteRecuperacion;
    if (!turno) return;
    this.procesando = true;
    this.error = '';
    try {
      await firstValueFrom(this.cajaService.recuperarTurno(turno.turno_id, {
        revision: turno.revision,
        motivo: 'Fallo irreversible en almacenamiento o dispositivo de caja'
      }));
      turno.estado = 'RECUPERACION';
      this.turnoActivo = null;
      this.turnoPendienteRecuperacion = null;
      this.mensajeExito = 'El turno quedo en recuperacion. Los cupos permanecen retenidos para revision supervisada.';
      try {
        await this.cajaService.limpiarTurnoLocal();
      } catch {
        this.error = 'El servidor puso el turno en recuperacion, pero no se pudo limpiar la copia local. No operes sin conexion y vuelve a cargar la caja con red.';
      }
    } catch (err) {
      this.error = this.msg(err);
    } finally {
      this.procesando = false;
    }
  }

  obtenerCupo(varianteId: string): CupoRespuesta | undefined {
    return this.turnoActivo?.cupos.find(c => c.variante_id === varianteId);
  }

  etiquetaEstadoTurno(estado?: string): string {
    switch (estado) {
      case 'ABIERTO': return 'Abierto';
      case 'CERRADO': return 'Cerrado';
      case 'CONCILIACION': return 'Conciliación requerida';
      case 'RECUPERACION': return 'En recuperación';
      default: return estado || '—';
    }
  }

  // --- Modo Reserva Online (Online legacy) ---
  buscar() {
    if (!this.codigo.trim()) {
      this.error = 'Ingrese un código de reserva para buscar.';
      return;
    }
    this.cargando = true;
    this.error = '';
    this.reservas.reservaPorCodigo(this.codigo.trim()).subscribe({
      next: r => {
        this.reserva = r;
        this.items = r.detalles
          .filter(d => d.cantidad_reservada > d.cantidad_vendida)
          .map(d => ({
            detalle_reserva_id: d.id,
            variante_id: d.variante_id,
            cantidad: d.cantidad_reservada - d.cantidad_vendida
          }));
        this.cargando = false;
        if (!this.items.length) {
          this.error = 'Esta reserva no tiene prendas disponibles para cobro (ya fueron cobradas o liberadas).';
        }
      },
      error: e => {
        this.error = this.msg(e);
        this.cargando = false;
      }
    });
  }

  agregar() {
    this.error = '';
    if (!this.variante) {
      this.error = 'Seleccione una variante antes de agregar.';
      return;
    }
    if (!Number.isInteger(this.cantidad) || this.cantidad < 1) {
      this.error = 'La cantidad debe ser al menos 1.';
      return;
    }
    const existente = this.items.find(i => i.variante_id === this.variante);
    if (existente) existente.cantidad += this.cantidad;
    else this.items.push({ variante_id: this.variante, cantidad: this.cantidad });
    this.variante = '';
    this.cantidad = 1;
  }

  quitar(i: number) {
    this.items.splice(i, 1);
  }

  async montarCardElementPresencial(): Promise<void> {
    this.desmontarCardElementPresencial();
    this.cardElementPresencialValido = false;
    this.errorTarjetaPresencial = null;
    this.cargandoStripePresencial = true;

    try {
      const stripe = await this.obtenerOInicializarStripe();
      const elements = stripe.elements();
      this.cardElementPresencial = elements.create('card', {
        hidePostalCode: true,
        style: {
          base: {
            fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
            fontSize: '16px',
            color: '#1c1b1f',
            '::placeholder': { color: '#79747e' }
          },
          invalid: {
            color: '#b3261e',
            iconColor: '#b3261e'
          }
        }
      });

      await new Promise(resolve => setTimeout(resolve, 0));

      const mountSelector = '#stripe-card-element-presencial';
      const container = typeof document !== 'undefined' ? document.querySelector(mountSelector) : null;
      if (!container) {
        throw new Error('No se encontró el contenedor de tarjeta para venta presencial.');
      }

      this.cardElementPresencial.mount(mountSelector);
      this.cardElementPresencial.on('change', (event: any) => {
        this.cardElementPresencialValido = !!(event && event.complete && !event.error);
        this.errorTarjetaPresencial = event?.error?.message || null;
      });
    } catch (err: any) {
      this.errorTarjetaPresencial = err?.message || 'Error al inicializar el campo seguro de tarjeta.';
      this.cardElementPresencialValido = false;
    } finally {
      this.cargandoStripePresencial = false;
    }
  }

  desmontarCardElementPresencial(): void {
    if (this.cardElementPresencial) {
      try {
        if (typeof this.cardElementPresencial.destroy === 'function') {
          this.cardElementPresencial.destroy();
        }
      } catch {}
      this.cardElementPresencial = null;
    }
    this.cardElementPresencialValido = false;
    this.errorTarjetaPresencial = null;
  }

  iniciarStripePresencial(): void {
    if (!this.items.length) {
      this.error = 'Debe agregar al menos una prenda para procesar la venta.';
      return;
    }
    this.iniciandoStripePresencial = true;
    this.error = '';

    const u = this.auth.obtenerUsuarioActual();
    const sucursalId = u?.sucursal_id || (this.turnoActivo ? this.turnoActivo.sucursal_id : '');

    this.api.iniciarVentaPresencialStripe({
      sucursal_id: sucursalId,
      cliente_id: this.clienteIdPresencial.trim() || null,
      turno_caja_id: this.turnoActivo?.turno_id || null,
      lineas: this.items.map(i => ({
        variante_id: i.variante_id,
        cantidad: i.cantidad
      }))
    }).subscribe({
      next: resp => {
        this.ordenStripePresencial = resp;
        this.iniciandoStripePresencial = false;
        if (resp && resp.estado_orden !== 'CAPTURADO') {
          this.montarCardElementPresencial();
        }
      },
      error: err => {
        this.error = this.msg(err);
        this.iniciandoStripePresencial = false;
      }
    });
  }

  async capturarStripePresencial(): Promise<void> {
    if (!this.ordenStripePresencial || this.capturandoStripePresencial) return;
    this.capturandoStripePresencial = true;
    this.error = '';
    this.errorTarjetaPresencial = null;

    if (!this.stripeService) {
      this.error = 'El servicio de pasarela de pagos Stripe no está disponible.';
      this.capturandoStripePresencial = false;
      return;
    }

    const orden = this.ordenStripePresencial;

    if (orden.estado_orden === 'CAPTURADO') {
      this.capturandoStripePresencial = false;
      return;
    }

    if (!this.cardElementPresencial && orden.estado_orden !== 'REQUIERE_ACCION_CLIENTE') {
      this.errorTarjetaPresencial = 'Complete los datos de la tarjeta antes de confirmar.';
      this.error = this.errorTarjetaPresencial;
      this.capturandoStripePresencial = false;
      return;
    }

    try {
      const stripe = await this.obtenerOInicializarStripe();

      if (orden.estado_orden === 'REQUIERE_ACCION_CLIENTE' && !this.cardElementPresencial) {
        this.stripeService.continuarAccion(orden.orden_pago_id, {
          payment_intent_id: orden.stripe_payment_intent_id || ''
        }).subscribe({
          next: accResp => {
            if (accResp && accResp.estado === 'CAPTURADO') {
              if (this.ordenStripePresencial) this.ordenStripePresencial.estado_orden = 'CAPTURADO';
              this.mensajeExito = 'Pago con tarjeta capturado exitosamente.';
            } else {
              if (this.ordenStripePresencial) this.ordenStripePresencial.estado_orden = (accResp?.estado as any) || 'PENDIENTE';
              this.error = `La orden continúa en estado ${accResp?.estado || 'PENDIENTE'}.`;
            }
            this.capturandoStripePresencial = false;
          },
          error: accErr => {
            if (this.ordenStripePresencial) this.ordenStripePresencial.estado_orden = 'FALLIDO';
            this.error = this.msg(accErr);
            this.capturandoStripePresencial = false;
          }
        });
        return;
      }

      if (!orden.client_secret) {
        this.error = 'No se encontró el secreto de cliente para procesar la tarjeta.';
        this.capturandoStripePresencial = false;
        return;
      }

      const confirmResult = await stripe.confirmCardPayment(orden.client_secret, {
        payment_method: {
          card: this.cardElementPresencial
        }
      });

      if (confirmResult?.error) {
        const msgError = confirmResult.error.message || 'La tarjeta fue rechazada por la pasarela de pagos.';
        this.errorTarjetaPresencial = msgError;
        this.error = msgError;
        this.capturandoStripePresencial = false;
        return;
      }

      const pi = confirmResult?.paymentIntent;
      if (pi?.status === 'requires_action') {
        this.ordenStripePresencial.estado_orden = 'REQUIERE_ACCION_CLIENTE';
        this.error = 'La tarjeta requiere verificación 3D Secure / SCA adicional.';
        this.capturandoStripePresencial = false;
        return;
      }

      if (pi?.status === 'succeeded' || pi?.status === 'requires_capture') {
        this.stripeService.confirmarOrdenPago(orden.orden_pago_id).subscribe({
          next: confResp => {
            if (confResp && confResp.estado === 'CAPTURADO') {
              if (this.ordenStripePresencial) {
                this.ordenStripePresencial.estado_orden = 'CAPTURADO';
              }
              this.desmontarCardElementPresencial();
              this.mensajeExito = 'Pago con tarjeta capturado y verificado centralmente con éxito.';
            } else {
              this.error = `La orden fue procesada por Stripe pero el backend reporta estado: ${confResp?.estado || 'PENDIENTE'}. Puede reintentar la confirmación.`;
            }
            this.capturandoStripePresencial = false;
          },
          error: confErr => {
            this.error = `El cobro fue aceptado por Stripe pero ocurrió un error al confirmar con el servidor: ${this.msg(confErr)}. No repita el cobro; reintente la confirmación.`;
            this.capturandoStripePresencial = false;
          }
        });
      } else {
        const estadoInesperado = pi?.status || 'desconocido';
        this.error = `Stripe reportó un estado no concluido: ${estadoInesperado}. Verifique el método de pago.`;
        this.capturandoStripePresencial = false;
      }
    } catch (err: any) {
      this.error = err?.message || 'Error inesperado al procesar la tarjeta con Stripe.';
      this.capturandoStripePresencial = false;
    }
  }

  cancelarStripePresencial(): void {
    if (!this.ordenStripePresencial) return;
    const orden = this.ordenStripePresencial;

    if (orden.estado_orden === 'CAPTURADO') {
      this.error = 'No se puede cancelar una orden con cobro ya capturado en la pasarela. Debe liquidar la venta o solicitar un reembolso formal.';
      return;
    }

    if (this.stripeService && (orden.estado_orden === 'PENDIENTE' || orden.estado_orden === 'REQUIERE_ACCION_CLIENTE')) {
      this.procesando = true;
      this.stripeService.cancelarOrdenPago(orden.orden_pago_id).subscribe({
        next: () => {
          this.desmontarCardElementPresencial();
          this.ordenStripePresencial = null;
          this.procesando = false;
        },
        error: err => {
          // H3: Preservar ordenStripePresencial visible ante fallos (409/502/timeout). No desmontar CardElement ni anular orden.
          this.error = this.msg(err);
          this.procesando = false;
        }
      });
      return;
    }

    this.desmontarCardElementPresencial();
    this.ordenStripePresencial = null;
  }

  reintentarConfirmacionStripePresencial(): void {
    if (!this.ordenStripePresencial || !this.stripeService) return;
    this.capturandoStripePresencial = true;
    this.stripeService.confirmarOrdenPago(this.ordenStripePresencial.orden_pago_id).subscribe({
      next: resp => {
        if (resp && resp.estado === 'CAPTURADO') {
          if (this.ordenStripePresencial) this.ordenStripePresencial.estado_orden = 'CAPTURADO';
          this.desmontarCardElementPresencial();
          this.mensajeExito = 'Pago confirmado centralmente.';
        }
        this.capturandoStripePresencial = false;
      },
      error: err => {
        this.error = this.msg(err);
        this.capturandoStripePresencial = false;
      }
    });
  }

  v(id: string) {
    const variante = this.variantes.find(x => x.id === id);
    if (variante) return [variante.producto_nombre, variante.talla_nombre, variante.color_nombre, variante.sku].filter(x => x?.trim()).join(' · ');
    const cupo = this.obtenerCupo(id);
    return cupo ? [cupo.producto_nombre, cupo.talla, cupo.color, cupo.sku].filter(x => x?.trim()).join(' · ') || id : (id || '—');
  }

  vender() {
    const u = this.auth.obtenerUsuarioActual();
    this.error = '';
    if (!u?.sucursal_id) {
      this.error = 'El usuario no tiene una sucursal asignada para operar en caja.';
      return;
    }
    if (!this.items.length) {
      this.error = 'Debe agregar al menos una prenda para procesar la venta.';
      return;
    }
    if (this.procesando) return;

    this.procesando = true;

    // Venta presencial directa en caja conectada (CU19)
    if (!this.reserva && (this.metodo === 'EFECTIVO' || this.metodo === 'SALDO' || this.metodo === 'STRIPE_TEST')) {
      if (this.metodo === 'SALDO' && !this.clienteIdPresencial.trim()) {
        this.error = 'La liquidación con saldo requiere indicar el identificador del cliente.';
        this.procesando = false;
        return;
      }
      if (this.metodo === 'STRIPE_TEST') {
        if (!this.ordenStripePresencial) {
          this.error = 'Debe iniciar el cobro con tarjeta Stripe antes de liquidar.';
          this.procesando = false;
          return;
        }
        if (this.ordenStripePresencial.estado_orden !== 'CAPTURADO') {
          this.error = 'La orden de pago Stripe debe estar en estado CAPTURADO antes de liquidar.';
          this.procesando = false;
          return;
        }
      }

      const sucursalId = u?.sucursal_id || this.turnoActivo?.sucursal_id || (this.ordenStripePresencial as OrdenActivaCajaDTO)?.sucursal_id || '';
      const dto: VentaPresencialLiquidarDTO = {
        venta_id: this.ordenStripePresencial?.venta_id,
        orden_pago_id: this.ordenStripePresencial?.orden_pago_id,
        sucursal_id: sucursalId,
        lineas: this.items.map(i => {
          const linea: LineaVentaPresencialDTO = {
            variante_id: i.variante_id,
            cantidad: i.cantidad
          };
          const lineaRecuperada = (this.ordenStripePresencial as OrdenActivaCajaDTO)?.lineas?.find(
            l => l.variante_id === i.variante_id
          );
          if (lineaRecuperada) {
            linea.precio_unitario_bob = Number(lineaRecuperada.precio_unitario_bob) || 0;
            if (lineaRecuperada.descuento_bob && Number(lineaRecuperada.descuento_bob) > 0) {
              linea.descuento_bob = Number(lineaRecuperada.descuento_bob);
            }
          } else if (i.precio_unitario_bob !== undefined) {
            linea.precio_unitario_bob = i.precio_unitario_bob;
            if (i.descuento_bob !== undefined && i.descuento_bob > 0) {
              linea.descuento_bob = i.descuento_bob;
            }
          }
          return linea;
        }),
        medio_pago: this.metodo,
        cliente_id: this.clienteIdPresencial.trim() || (this.ordenStripePresencial as OrdenActivaCajaDTO)?.cliente_id || undefined,
        efectivo_recibido_bob: this.metodo === 'EFECTIVO' ? (this.efectivoRecibidoPresencial || undefined) : undefined,
        saldo_aplicado_bob: this.metodo === 'SALDO' ? this.saldoAplicadoPresencial : undefined,
        stripe_payment_intent_id: this.ordenStripePresencial?.stripe_payment_intent_id,
        turno_caja_id: this.turnoActivo?.turno_id || (this.ordenStripePresencial as OrdenActivaCajaDTO)?.turno_caja_id || undefined
      };

      this.api.liquidarVentaPresencial(dto).subscribe({
        next: v => {
          this.ventaLiquidada = v;
          this.api.comprobante(v.venta_id).subscribe({
            next: c => {
              c.total = Number(v.total_bob);
              this.comprobante = c;
              this.procesando = false;
              this.items = [];
              this.desmontarCardElementPresencial();
              this.ordenStripePresencial = null;
              this.mensajeExito = `Venta ${v.numero} liquidada exitosamente. Total confirmado por servidor: Bs ${v.total_bob}.`;
            },
            error: () => {
              this.comprobante = {
                id: v.venta_id,
                numero: v.numero,
                sucursal_id: u.sucursal_id || '',
                canal: 'PRESENCIAL',
                estado: v.estado_pago || 'PAGADA',
                subtotal: Number(v.total_bob),
                descuento: 0,
                adelanto_descontado: 0,
                costo_entrega: 0,
                total: Number(v.total_bob),
                creada_en: v.fecha_hora || new Date().toISOString(),
                detalles: [],
                pagos: [{
                  id: v.comprobante_id,
                  contexto: 'VENTA',
                  venta_id: v.venta_id,
                  medio_pago: v.medio_pago,
                  monto: Number(v.total_bob),
                  no_reembolsable: false,
                  estado: 'PAGADO'
                }]
              };
              this.procesando = false;
              this.items = [];
              this.desmontarCardElementPresencial();
              this.ordenStripePresencial = null;
              this.mensajeExito = `Venta ${v.numero} liquidada exitosamente. Total confirmado por servidor: Bs ${v.total_bob}.`;
            }
          });
        },
        error: e => {
          this.error = this.msg(e);
          this.procesando = false;
        }
      });
      return;
    }

    this.api.registrarVenta({
      reserva_id: this.reserva?.id,
      sucursal_id: u.sucursal_id,
      cliente_id: this.reserva?.cliente_id,
      metodo: this.metodo,
      items: this.items
    }).subscribe({
      next: v => {
        this.api.comprobante(v.id).subscribe({
          next: c => {
            this.comprobante = c;
            this.procesando = false;
            this.items = [];
          },
          error: e => {
            this.error = this.msg(e);
            this.procesando = false;
          }
        });
      },
      error: e => {
        this.error = this.msg(e);
        this.procesando = false;
      }
    });
  }

  liquidar(): void {
    this.vender();
  }

  calcularTotalesPresenciales() {
    const subtotal = this.items.reduce((acc, it) => {
      const lineaRecuperada = (this.ordenStripePresencial as OrdenActivaCajaDTO)?.lineas?.find(
        l => l.variante_id === it.variante_id
      );
      if (lineaRecuperada) {
        return acc + ((Number(lineaRecuperada.precio_unitario_bob) || 0) * it.cantidad);
      }
      if (it.precio_unitario_bob !== undefined) {
        return acc + (it.precio_unitario_bob * it.cantidad);
      }
      const v = this.variantes.find(x => x.id === it.variante_id);
      const precio = v ? Number(v.precio) : 0;
      return acc + (precio * it.cantidad);
    }, 0);
    this.totalPresencialEstimado = subtotal;
    if (this.efectivoRecibidoPresencial >= subtotal) {
      this.cambioPresencialEstimado = Math.round((this.efectivoRecibidoPresencial - subtotal) * 100) / 100;
    } else {
      this.cambioPresencialEstimado = 0;
    }
  }

  cambiarModo(modo: 'RESERVA' | 'TURNO_OFFLINE'): void {
    if (this.vistaModo === modo) return;
    this.desmontarCardElementCaja();
    this.desmontarCardElementPresencial();
    this.vistaModo = modo;
    this.error = '';
    this.mensajeExito = '';
    this.recuperarOrdenActivaCaja();
  }

  ngOnDestroy(): void {
    this.desmontarCardElementCaja();
    this.desmontarCardElementPresencial();
  }

  nueva() {
    this.desmontarCardElementPresencial();
    this.ordenStripePresencial = null;
    this.reserva = undefined;
    this.comprobante = undefined;
    this.ventaLiquidada = undefined;
    this.codigo = '';
    this.items = [];
    this.error = '';
    this.mensajeExito = '';
    this.clienteIdPresencial = '';
    this.efectivoRecibidoPresencial = 0;
  }

  imprimir() {
    window.print();
  }

  private msg(e: unknown): string {
    return formatearErrorApi(e, 'No se pudo completar la operación en caja.');
  }
}
