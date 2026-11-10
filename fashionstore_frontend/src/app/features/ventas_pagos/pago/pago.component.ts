import { Component, OnInit, OnDestroy, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { StripeService } from '../services/stripe.service';
import { IntencionDTO, EstadoPagoDTO } from '../models/venta-digital.models';
import { environment } from '../../../../environments/environment';
import { formatearBs, type DecimalApi } from '../../../core/utils/moneda.util';
import { etiquetaEstado, claseEstado } from '../../../core/utils/estado-mapper.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';

@Component({
  selector: 'app-pago',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './pago.component.html',
  styleUrls: ['./pago.component.css']
})
export class PagoComponent implements OnInit, OnDestroy {
  ventaId = '';
  estado: EstadoPagoDTO | null = null;
  intencion: IntencionDTO | null = null;
  cargando = true;
  procesandoPago = false;
  creandoIntencion = false;
  error: string | null = null;
  exito: string | null = null;
  avisoTimeout = false;
  avisoCambioPrecio: string | null = null;
  requiereAccion3DS = false;
  procesando3DS = false;
  guardarMetodo = false;

  private stripe: unknown = null;
  private elements: unknown = null;
  private cardElement: unknown = null;
  private pollingTimer: ReturnType<typeof setInterval> | null = null;
  private pollingCount = 0;
  private readonly MAX_POLLS = 30;
  private idemKey = crypto.randomUUID();
  private readonly destroyRef = inject(DestroyRef);

  constructor(
    private route: ActivatedRoute,
    private stripeService: StripeService
  ) {}

  ngOnInit(): void {
    this.ventaId = this.route.snapshot.paramMap.get('ventaId') ?? '';
    if (!this.ventaId) {
      this.error = 'No se indicó la venta.';
      this.cargando = false;
      return;
    }
    this.consultarEstadoInicial();
  }

  ngOnDestroy(): void {
    this.detenerPolling();
    this.destruirElements();
  }

  private destruirElements(): void {
    if (this.cardElement && typeof (this.cardElement as { destroy: () => void }).destroy === 'function') {
      try {
        (this.cardElement as { destroy: () => void }).destroy();
      } catch {
        // cleanup silencioso
      }
      this.cardElement = null;
    }
  }

  consultarEstadoInicial(): void {
    this.cargando = true;
    this.error = null;
    this.avisoTimeout = false;

    this.stripeService.consultarEstado(this.ventaId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: e => {
          this.estado = e;
          this.cargando = false;
          const visto = this.route.snapshot.queryParamMap.get('importe_visto_bob');
          if (visto !== null && /^\d+(\.\d{1,2})?$/.test(visto) && Number.isFinite(Number(e.monto)) &&
              Math.round(Number(visto) * 100) !== Math.round(Number(e.monto) * 100)) {
            this.avisoCambioPrecio = `El servidor actualizó el total de ${this.bs(visto)} a ${this.bs(e.monto)}. Revisa los precios, promociones y entrega antes de confirmar el pago.`;
          } else {
            this.avisoCambioPrecio = null;
          }

          // Si la venta está pendiente y el pago no tiene intención o está pendiente
          if (e.estado_venta === 'PENDIENTE_PAGO' &&
             (e.estado_pago === 'SIN_INTENCION' || e.estado_pago === 'PENDIENTE')) {
            this.iniciarOReutilizarIntencion();
          } else if (e.estado_pago === 'APROBADO' || e.estado_venta === 'PAGADA') {
            this.exito = 'Pago aprobado correctamente.';
          }
        },
        error: e => {
          this.error = formatearErrorApi(e, 'No se pudo consultar el estado del pago.');
          this.cargando = false;
        }
      });
  }

  private iniciarOReutilizarIntencion(): void {
    if (this.creandoIntencion) return;
    this.creandoIntencion = true;
    this.error = null;

    this.stripeService.crearIntencion(this.ventaId, this.idemKey)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: intent => {
          this.creandoIntencion = false;
          this.intencion = intent;
          if (intent.client_secret) {
            this.montarStripeElements(intent.client_secret);
          } else {
            this.error = 'La pasarela no proporcionó el secreto de pago.';
          }
        },
        error: e => {
          this.creandoIntencion = false;
          this.error = formatearErrorApi(e, 'No se pudo inicializar la pasarela de pago.');
        }
      });
  }

  private async montarStripeElements(clientSecret: string): Promise<void> {
    try {
      this.destruirElements();
      const StripeConstructor = await this.stripeService.cargarStripeJs() as (key: string) => unknown;
      this.stripe = StripeConstructor(environment.stripePublicKey);
      const s = this.stripe as { elements: () => unknown };
      this.elements = s.elements();
      const els = this.elements as { create: (type: string, opts: Record<string, unknown>) => unknown };
      this.cardElement = els.create('card', {
        style: {
          base: {
            fontSize: '16px',
            color: '#0f172a',
            fontFamily: 'Plus Jakarta Sans, sans-serif',
            '::placeholder': { color: '#94a3b8' }
          },
          invalid: { color: '#c43d4b' }
        }
      });
      const mount = this.cardElement as { mount: (el: string) => void };
      mount.mount('#stripe-card-element');
    } catch {
      this.error = 'No se pudo cargar el formulario de pago seguro. Verifica tu conexión.';
    }
  }

  confirmarPago(): void {
    if (this.procesandoPago || !this.stripe || !this.cardElement || !this.intencion?.client_secret) return;
    this.procesandoPago = true;
    this.error = null;
    this.requiereAccion3DS = false;

    const s = this.stripe as {
      confirmCardPayment: (cs: string, data: unknown) => Promise<{
        error?: { message: string; code?: string };
        paymentIntent?: { status: string; id: string };
      }>;
    };

    s.confirmCardPayment(this.intencion.client_secret, {
      payment_method: { card: this.cardElement }
    }).then(result => {
      this.procesandoPago = false;
      if (result.error) {
        if (result.error.code === 'authentication_required' || result.error.code === 'requires_action') {
          this.requiereAccion3DS = true;
          this.error = 'Tu entidad financiera requiere validación de identidad (3D-Secure). Pulsa el botón inferior para continuar.';
        } else {
          this.error = result.error.message ?? 'El pago fue rechazado por la pasarela.';
        }
      } else if (result.paymentIntent?.status === 'requires_action') {
        this.requiereAccion3DS = true;
      } else {
        // Preparar método si el cliente dio su consentimiento para compras futuras y offline (v3)
        if (this.guardarMetodo) {
          this.stripeService.prepararMetodo().subscribe({
            next: prep => {
              try {
                if (typeof window !== 'undefined' && window.localStorage) {
                  localStorage.setItem('fs_metodo_preparado_id', prep.preparacion_pago_id);
                }
              } catch {}
            },
            error: () => {}
          });
        }
        // Se inicia polling para consultar la confirmación definitiva en backend
        this.iniciarPolling();
      }
    }).catch(() => {
      this.error = 'Ocurrió un error inesperado al procesar el pago.';
      this.procesandoPago = false;
    });
  }

  continuarAccion3DS(): void {
    if (!this.stripe || !this.intencion?.client_secret || this.procesando3DS) return;
    this.procesando3DS = true;
    this.error = null;

    const s = this.stripe as {
      handleCardAction: (cs: string) => Promise<{
        error?: { message: string };
        paymentIntent?: { status: string };
      }>;
    };

    if (typeof s.handleCardAction === 'function') {
      s.handleCardAction(this.intencion.client_secret).then(res => {
        this.procesando3DS = false;
        if (res.error) {
          this.error = res.error.message || 'La verificación bancaria no fue completada con éxito.';
        } else {
          this.requiereAccion3DS = false;
          this.iniciarPolling();
        }
      }).catch(() => {
        this.procesando3DS = false;
        this.error = 'No fue posible continuar la autenticación bancaria. Puedes reintentar.';
      });
    } else {
      this.procesando3DS = false;
      this.iniciarPolling();
    }
  }

  reintentar(): void {
    this.error = null;
    this.exito = null;
    this.avisoTimeout = false;
    this.idemKey = crypto.randomUUID(); // Nuevo intento lógico tras rechazo
    this.creandoIntencion = true;

    this.stripeService.reintentar(this.ventaId, this.idemKey)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: intent => {
          this.creandoIntencion = false;
          this.intencion = intent;
          if (intent.client_secret) {
            this.montarStripeElements(intent.client_secret);
          }
        },
        error: e => {
          this.creandoIntencion = false;
          this.error = formatearErrorApi(e, 'No se pudo reintentar el pago.');
        }
      });
  }

  private iniciarPolling(): void {
    this.detenerPolling();
    this.pollingCount = 0;
    this.avisoTimeout = false;

    this.pollingTimer = setInterval(() => {
      this.pollingCount++;
      if (this.pollingCount > this.MAX_POLLS) {
        this.detenerPolling();
        this.avisoTimeout = true;
        return;
      }

      this.stripeService.consultarEstado(this.ventaId).subscribe({
        next: e => {
          this.estado = e;
          if (e.estado_pago === 'APROBADO' || e.estado_venta === 'PAGADA') {
            this.detenerPolling();
            this.exito = 'Pago aprobado correctamente.';
          } else if (e.estado_pago === 'RECHAZADO' || e.estado_pago === 'ANULADO' || e.estado_venta === 'CANCELADA') {
            this.detenerPolling();
          }
        },
        error: (err: unknown) => {
          if (err && typeof err === 'object' && 'status' in err) {
            const st = (err as { status: unknown }).status;
            if (st === 401 || st === 403 || st === 404) {
              this.detenerPolling();
              this.error = formatearErrorApi(err, 'No se pudo consultar el estado del pago.');
            }
          }
        }
      });
    }, 3000);
  }

  private detenerPolling(): void {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = null;
    }
  }

  get esPendiente(): boolean {
    return (this.estado?.estado_pago === 'PENDIENTE' || this.estado?.estado_pago === 'SIN_INTENCION') &&
           this.estado?.estado_venta === 'PENDIENTE_PAGO';
  }

  get esAprobado(): boolean {
    return this.estado?.estado_pago === 'APROBADO' || this.estado?.estado_venta === 'PAGADA';
  }

  get esRechazado(): boolean {
    return this.estado?.estado_pago === 'RECHAZADO' && this.estado?.estado_venta === 'PENDIENTE_PAGO';
  }

  get esCanceladoOAnulado(): boolean {
    return this.estado?.estado_pago === 'ANULADO' || this.estado?.estado_venta === 'CANCELADA';
  }

  get esCanceladoPorExpiracion(): boolean {
    if (this.estado?.estado_venta !== 'CANCELADA') return false;
    if (!this.estado?.expira_en) return false;
    return new Date(this.estado.expira_en).getTime() <= Date.now();
  }

  etiqueta(estado: string): string { return etiquetaEstado(estado); }
  clase(estado: string): string { return claseEstado(estado); }
  bs(m: DecimalApi | null | undefined): string { return formatearBs(m); }
}
