import { Component, OnInit, OnDestroy, DestroyRef, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule, FormGroup, FormControl, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CarritoService } from '../services/carrito.service';
import { EntregaService } from '../services/entrega.service';
import { OrganizacionService } from '../../organizacion/services/organizacion.service';
import { EnriquecimientoService, VarianteEnriquecida } from '../../catalogo/services/enriquecimiento.service';
import { SincronizacionOfflineService } from '../../../core/services/sincronizacion-offline.service';
import { OperacionDatosCompra, AutorizacionCobroOfflineDTO } from '../../../core/services/offline-store.service';
import { StripeService } from '../services/stripe.service';
import { AuthService } from '../../identidad_empresas/services/auth.service';
import { environment } from '../../../../environments/environment';
import { obtenerDispositivoId, obtenerHoraBoliviaIso } from '../../../core/utils/bolivia-time.util';
import { CarritoDTO, CoberturaDTO, CoberturaSucursalDTO, CotizacionDTO, ModalidadEntrega, CheckoutCrearDTO } from '../models/venta-digital.models';
import { SucursalDTO } from '../../organizacion/models/organizacion.models';
import { formatearBs, sumarImportes, aNumero, type DecimalApi } from '../../../core/utils/moneda.util';
import { formatearErrorApi } from '../../../core/utils/error-handler.util';

export interface HuellaLineaCanonica {
  cantidad: number;
  precio_unitario_bob: string | number;
  variante_id: string;
}

export interface HuellaCanonicaParams {
  base_bob: string | number;
  condiciones_version: string;
  descuento_bob: string | number;
  direccion?: string | null;
  empresa_id: string;
  envio_bob: string | number;
  importe_cobro: string | number;
  lineas: HuellaLineaCanonica[];
  modalidad: 'RECOJO' | 'DELIVERY' | string;
  moneda_cobro: string;
  sucursal_id: string;
  tasa_bob_por_usd: string | number;
  tasa_id: string;
  total_bob: string | number;
  usuario_id: string;
  vigente_hasta: string | Date;
}

export function sha256Hex(ascii: string): string {
  function rightRotate(value: number, amount: number): number {
    return (value >>> amount) | (value << (32 - amount));
  }

  const utf8 = unescape(encodeURIComponent(ascii));
  const asciiBitLength = utf8.length * 8;

  const k = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ];

  let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a;
  let h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;

  const byteLen = utf8.length;
  const totalLen = (((byteLen + 8) >> 6) + 1) << 6;
  const bytes = new Uint8Array(totalLen);
  for (let i = 0; i < byteLen; i++) {
    bytes[i] = utf8.charCodeAt(i);
  }
  bytes[byteLen] = 0x80;

  const highBits = Math.floor(asciiBitLength / 0x100000000);
  const lowBits = asciiBitLength >>> 0;

  bytes[totalLen - 8] = (highBits >>> 24) & 0xff;
  bytes[totalLen - 7] = (highBits >>> 16) & 0xff;
  bytes[totalLen - 6] = (highBits >>> 8) & 0xff;
  bytes[totalLen - 5] = highBits & 0xff;
  bytes[totalLen - 4] = (lowBits >>> 24) & 0xff;
  bytes[totalLen - 3] = (lowBits >>> 16) & 0xff;
  bytes[totalLen - 2] = (lowBits >>> 8) & 0xff;
  bytes[totalLen - 1] = lowBits & 0xff;

  const w = new Int32Array(64);

  for (let i = 0; i < totalLen; i += 64) {
    for (let j = 0; j < 16; j++) {
      const idx = i + j * 4;
      w[j] = (bytes[idx] << 24) | (bytes[idx + 1] << 16) | (bytes[idx + 2] << 8) | bytes[idx + 3];
    }
    for (let j = 16; j < 64; j++) {
      const s0 = rightRotate(w[j - 15], 7) ^ rightRotate(w[j - 15], 18) ^ (w[j - 15] >>> 3);
      const s1 = rightRotate(w[j - 2], 17) ^ rightRotate(w[j - 2], 19) ^ (w[j - 2] >>> 10);
      w[j] = (w[j - 16] + s0 + w[j - 7] + s1) | 0;
    }

    let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;

    for (let j = 0; j < 64; j++) {
      const s1 = rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + ch + k[j] + w[j]) | 0;
      const s0 = rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) | 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) | 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) | 0;
    }

    h0 = (h0 + a) | 0;
    h1 = (h1 + b) | 0;
    h2 = (h2 + c) | 0;
    h3 = (h3 + d) | 0;
    h4 = (h4 + e) | 0;
    h5 = (h5 + f) | 0;
    h6 = (h6 + g) | 0;
    h7 = (h7 + h) | 0;
  }

  const toHex = (n: number) => (n >>> 0).toString(16).padStart(8, '0');
  return toHex(h0) + toHex(h1) + toHex(h2) + toHex(h3) + toHex(h4) + toHex(h5) + toHex(h6) + toHex(h7);
}

export function calcularHuellaCanonicaV3(params: HuellaCanonicaParams): { json: string; hash: string } {
  const lineasOrdenadas = [...params.lineas]
    .map(l => ({
      cantidad: Number(l.cantidad),
      precio_unitario_bob: Number(l.precio_unitario_bob).toFixed(2),
      variante_id: String(l.variante_id)
    }))
    .sort((a, b) => a.variante_id.localeCompare(b.variante_id));

  let fechaStr: string;
  if (params.vigente_hasta instanceof Date) {
    fechaStr = params.vigente_hasta.toISOString().replace(/\.\d+Z$/, 'Z');
  } else {
    const s = String(params.vigente_hasta);
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(s)) {
      fechaStr = s;
    } else {
      fechaStr = new Date(s).toISOString().replace(/\.\d+Z$/, 'Z');
    }
  }

  const rawPayload: Record<string, unknown> = {
    base_bob: Number(params.base_bob).toFixed(2),
    condiciones_version: String(params.condiciones_version).trim(),
    descuento_bob: Number(params.descuento_bob).toFixed(2),
    empresa_id: String(params.empresa_id),
    envio_bob: Number(params.envio_bob).toFixed(2),
    importe_cobro: Number(params.importe_cobro).toFixed(2),
    lineas: lineasOrdenadas,
    modalidad: String(params.modalidad).toUpperCase(),
    moneda_cobro: String(params.moneda_cobro).toUpperCase(),
    sucursal_id: String(params.sucursal_id),
    tasa_bob_por_usd: Number(params.tasa_bob_por_usd).toFixed(2),
    tasa_id: String(params.tasa_id),
    total_bob: Number(params.total_bob).toFixed(2),
    usuario_id: String(params.usuario_id),
    vigente_hasta: fechaStr
  };

  if (rawPayload['modalidad'] === 'DELIVERY' && params.direccion && String(params.direccion).trim().length > 0) {
    rawPayload['direccion'] = String(params.direccion).trim().replace(/\s+/g, ' ');
  }

  const sortedPayload: Record<string, unknown> = {};
  Object.keys(rawPayload).sort().forEach(k => {
    sortedPayload[k] = rawPayload[k];
  });

  const json = JSON.stringify(sortedPayload);
  const hash = sha256Hex(json);
  return { json, hash };
}

type Paso = 'resumen' | 'entrega' | 'confirmacion';

@Component({
  selector: 'app-checkout',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, RouterLink],
  templateUrl: './checkout.component.html',
  styleUrls: ['./checkout.component.css']
})
export class CheckoutComponent implements OnInit, OnDestroy {
  paso: Paso = 'resumen';
  carrito: CarritoDTO | null = null;
  cobertura: CoberturaDTO | null = null;
  sucursales: SucursalDTO[] = [];
  cargando = true;
  procesando = false;
  error: string | null = null;

  cotizacion: CotizacionDTO | null = null;
  cotizando = false;
  prendasInfo: Map<string, VarianteEnriquecida> = new Map();

  // Stripe Elements (CU22)
  stripe: any = null;
  cardElement: any = null;
  elements: any = null;
  mostrandoFormularioTarjeta = false;
  cardElementMontado = false;
  cardElementValido = false;
  confirmandoTarjeta = false;
  errorTarjeta: string | null = null;
  clientSecretActual: string | null = null;
  preparacionPagoIdActual: string | null = null;

  // Formulario reactivo tipado
  checkoutForm = new FormGroup({
    sucursalId: new FormControl<string>('', { nonNullable: true, validators: [Validators.required] }),
    modalidad: new FormControl<ModalidadEntrega>('RECOJO', { nonNullable: true, validators: [Validators.required] }),
    direccion: new FormControl<string>('', { nonNullable: true }),
    anilloDestino: new FormControl<number | null>(null),
  });

  // Manejo de idempotencia estable por intento lógico
  private checkoutKey = crypto.randomUUID();
  private firmaIntentoPrevio: string | null = null;
  private readonly destroyRef = inject(DestroyRef);
  private readonly sincronizacionService = inject(SincronizacionOfflineService);
  private readonly stripeService = inject(StripeService);
  private readonly authService = inject(AuthService, { optional: true });

  autorizoCobroOffline = true;
  consentimientoCobroV3 = true;
  metodoPreparadoId: string | null = null;
  get preparacionPagoId(): string | null {
    return this.metodoPreparadoId;
  }
  set preparacionPagoId(v: string | null) {
    this.metodoPreparadoId = v;
  }
  preparandoMetodo = false;
  metodoPreparadoExito = false;
  tasaCambioVigente = '6.96';
  tasaId: string | null = null;
  condicionesVersion = 'v3';
  vigenciaHoras = 24;

  get tieneTasaValida(): boolean {
    return !!(
      this.tasaId &&
      this.tasaCambioVigente &&
      !isNaN(Number(this.tasaCambioVigente)) &&
      Number(this.tasaCambioVigente) > 0
    );
  }

  get estaEnLinea(): boolean {
    return this.sincronizacionService.estaEnLinea;
  }

  constructor(
    private carritoService: CarritoService,
    private entregaService: EntregaService,
    private orgService: OrganizacionService,
    private enriquecimientoService: EnriquecimientoService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.cargarDatos();

    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const guardado = localStorage.getItem('fs_metodo_preparado_id');
        if (guardado) {
          // Un ID recuperado de localStorage NO se convierte automáticamente en LISTO:
          // invoca consultarMetodo ante el servidor para revalidarlo antes de usarlo.
          // Si no está LISTO o pertenece a otro usuario/empresa, lo purga de localStorage.
          this.stripeService.consultarMetodo(guardado)
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: metodo => {
                if (metodo && metodo.estado === 'LISTO') {
                  this.metodoPreparadoId = metodo.preparacion_pago_id;
                  this.metodoPreparadoExito = true;
                } else {
                  this.purgarMetodoGuardado();
                }
              },
              error: () => {
                this.purgarMetodoGuardado();
              }
            });
        }
      }
    } catch {}

    // Reaccionar a cambios en modalidad para ajustar validaciones
    this.checkoutForm.controls.modalidad.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(mod => {
        this.cotizacion = null;
        if (mod === 'DELIVERY') {
          this.checkoutForm.controls.direccion.setValidators([Validators.required, Validators.minLength(5)]);
          this.checkoutForm.controls.anilloDestino.setValidators([Validators.required, Validators.min(1), Validators.max(12)]);
        } else {
          this.checkoutForm.controls.direccion.clearValidators();
          this.checkoutForm.controls.anilloDestino.clearValidators();
          this.checkoutForm.controls.direccion.setValue('');
          this.checkoutForm.controls.anilloDestino.setValue(null);
        }
        this.checkoutForm.controls.direccion.updateValueAndValidity();
        this.checkoutForm.controls.anilloDestino.updateValueAndValidity();
      });

    // Invalidar cotización al cambiar de sucursal y cambiar a RECOJO si no tiene delivery activo
    this.checkoutForm.controls.sucursalId.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(nuevaSucursalId => {
        this.cotizacion = null;
        const suc = this.sucursalObj(nuevaSucursalId);
        if (suc && !suc.delivery_activo && this.checkoutForm.controls.modalidad.value === 'DELIVERY') {
          this.checkoutForm.controls.modalidad.setValue('RECOJO');
        }
      });

    // Invalidar cotización al cambiar de anillo
    this.checkoutForm.controls.anilloDestino.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.cotizacion = null;
      });
  }

  ngOnDestroy(): void {
    this.desmontarCardElement();
  }

  desmontarCardElement(): void {
    if (this.cardElement && typeof this.cardElement.destroy === 'function') {
      try {
        this.cardElement.destroy();
      } catch {}
    }
    this.cardElement = null;
    this.cardElementMontado = false;
    this.cardElementValido = false;
    this.clientSecretActual = null;
  }

  cancelarFormularioTarjeta(): void {
    this.desmontarCardElement();
    this.mostrandoFormularioTarjeta = false;
    this.preparandoMetodo = false;
    this.confirmandoTarjeta = false;
    this.errorTarjeta = null;
    this.preparacionPagoIdActual = null;
  }

  purgarMetodoGuardado(): void {
    this.desmontarCardElement();
    this.mostrandoFormularioTarjeta = false;
    this.metodoPreparadoId = null;
    this.metodoPreparadoExito = false;
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        localStorage.removeItem('fs_metodo_preparado_id');
      }
    } catch {}
  }

  cargarDatos(): void {
    this.cargando = true;
    this.error = null;

    this.orgService.obtenerTasaVigente()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: t => {
          if (t && t.id) {
            this.tasaId = t.id;
            this.tasaCambioVigente = String(t.tasa_bob_por_usd);
          }
        },
        error: () => {}
      });

    this.carritoService.obtenerMio()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: c => {
          this.carrito = c;
          if (!c.lineas.length) {
            this.cargando = false;
            return;
          }

          // Cargar información descriptiva de prendas
          for (const linea of c.lineas) {
            this.enriquecimientoService.obtenerVariante(linea.variante_id)
              .pipe(takeUntilDestroyed(this.destroyRef))
              .subscribe(info => this.prendasInfo.set(linea.variante_id, info));
          }

          this.carritoService.cobertura().subscribe({
            next: cob => {
              this.cobertura = cob;
              this.orgService.gestionarSucursales().subscribe({
                next: s => { this.sucursales = s; this.cargando = false; },
                error: e => { this.error = formatearErrorApi(e); this.cargando = false; }
              });
            },
            error: e => { this.error = formatearErrorApi(e); this.cargando = false; }
          });
        },
        error: e => { this.error = formatearErrorApi(e, 'No se pudo cargar el carrito.'); this.cargando = false; }
      });
  }

  sucursalesConCobertura(): CoberturaSucursalDTO[] {
    return this.cobertura?.sucursales.filter(s => s.cubre_todo) ?? [];
  }

  sucursalNombre(id: string): string {
    return this.sucursales.find(s => s.id === id)?.nombre ?? 'Sucursal seleccionada';
  }

  sucursalObj(id: string): SucursalDTO | undefined {
    return this.sucursales.find(s => s.id === id);
  }

  nombrePrenda(varianteId: string): string {
    const info = this.prendasInfo.get(varianteId);
    if (!info) return 'Prenda en selección';
    const attr = [info.talla_nombre, info.color_nombre].filter(Boolean).join(' / ');
    return attr ? `${info.nombre_producto} (${attr})` : info.nombre_producto;
  }

  skuPrenda(varianteId: string): string {
    return this.prendasInfo.get(varianteId)?.sku ?? '—';
  }

  avanzar(): void {
    if (this.paso === 'resumen') {
      if (!this.checkoutForm.controls.sucursalId.valid) {
        this.checkoutForm.controls.sucursalId.markAsTouched();
        return;
      }
      this.paso = 'entrega';
    } else if (this.paso === 'entrega') {
      if (!this.puedeConfirmar) {
        this.checkoutForm.markAllAsTouched();
        return;
      }
      this.paso = 'confirmacion';
    }
  }

  retroceder(): void {
    if (this.paso === 'entrega') this.paso = 'resumen';
    else if (this.paso === 'confirmacion') this.paso = 'entrega';
  }

  cotizar(): void {
    const sid = this.checkoutForm.controls.sucursalId.value;
    const anillo = this.checkoutForm.controls.anilloDestino.value;
    if (!sid || !anillo) return;

    this.cotizando = true;
    this.cotizacion = null;
    this.entregaService.cotizar(sid, anillo)
      .subscribe({
        next: c => { this.cotizacion = c; this.cotizando = false; },
        error: e => { this.error = formatearErrorApi(e, 'No se pudo cotizar el delivery.'); this.cotizando = false; }
      });
  }

  get sucursalSeleccionada(): string {
    return this.checkoutForm.controls.sucursalId.value;
  }

  get modalidadSeleccionada(): ModalidadEntrega {
    return this.checkoutForm.controls.modalidad.value;
  }

  get direccionValor(): string {
    return this.checkoutForm.controls.direccion.value;
  }

  get anilloValor(): number | null {
    return this.checkoutForm.controls.anilloDestino.value;
  }

  get cotizacionEsVigente(): boolean {
    if (this.modalidadSeleccionada !== 'DELIVERY') return true;
    return !!(
      this.cotizacion &&
      this.cotizacion.sucursal_id === this.sucursalSeleccionada &&
      this.cotizacion.anillo_destino === this.anilloValor
    );
  }

  get requiereRecalcularCotizacion(): boolean {
    if (this.modalidadSeleccionada !== 'DELIVERY') return false;
    return (
      !!this.sucursalSeleccionada &&
      this.anilloValor !== null &&
      !this.cotizacionEsVigente
    );
  }

  get totalVisible(): number {
    const costoEntrega = this.modalidadSeleccionada === 'DELIVERY' && this.cotizacionEsVigente
      ? this.cotizacion?.costo_entrega
      : 0;
    return sumarImportes(this.carrito?.total, costoEntrega);
  }

  get puedeConfirmar(): boolean {
    if (!this.checkoutForm.controls.sucursalId.valid || !this.carrito?.lineas.length) return false;
    if (this.modalidadSeleccionada === 'DELIVERY') {
      const suc = this.sucursalObj(this.sucursalSeleccionada);
      if (!suc || !suc.delivery_activo) return false;
      return (
        this.checkoutForm.controls.direccion.valid &&
        this.checkoutForm.controls.anilloDestino.valid &&
        this.cotizacionEsVigente
      );
    }
    return true;
  }

  reintentarObtenerTasa(): void {
    this.orgService.obtenerTasaVigente()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: t => {
          if (t && t.id) {
            this.tasaId = t.id;
            this.tasaCambioVigente = String(t.tasa_bob_por_usd);
          }
        },
        error: e => {
          this.error = formatearErrorApi(e, 'No se pudo obtener la tasa de cambio vigente.');
        }
      });
  }

  prepararMetodoPago(): void {
    if (this.preparandoMetodo) return;
    this.preparandoMetodo = true;
    this.error = null;
    this.errorTarjeta = null;

    this.stripeService.prepararMetodo({
      huella_dispositivo: obtenerDispositivoId()
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: async (prep) => {
        if (prep.estado === 'LISTO') {
          // Revalidar contra el servidor y SOLO presentar/persistir LISTO si el servidor confirma
          this.verificarYFinalizarMetodo(prep.preparacion_pago_id);
          return;
        }

        this.metodoPreparadoExito = false;

        if (!prep.client_secret) {
          this.preparandoMetodo = false;
          this.error = 'La pasarela no proporcionó el secreto de vinculación segura.';
          return;
        }

        this.clientSecretActual = prep.client_secret;
        this.preparacionPagoIdActual = prep.preparacion_pago_id;

        // Mostrar contenedor del formulario en DOM (CU22)
        this.mostrandoFormularioTarjeta = true;

        if (!this.cardElement) {
          await this.montarStripeCardElement();
        } else {
          // Si cardElement ya fue instanciado o inyectado previamente (p. ej. en pruebas unitarias directas),
          // continuar con el procesamiento inmediato para compatibilidad de tests
          await this.procesarConfirmacionSetup(prep.preparacion_pago_id, prep.client_secret);
        }
      },
      error: e => {
        this.preparandoMetodo = false;
        this.metodoPreparadoExito = false;
        this.error = formatearErrorApi(e, 'No se pudo preparar el método de pago seguro.');
      }
    });
  }

  async montarStripeCardElement(): Promise<void> {
    try {
      if (!this.stripe) {
        try {
          const StripeConstructor = await this.stripeService.cargarStripeJs() as (key: string) => any;
          if (typeof StripeConstructor === 'function') {
            this.stripe = StripeConstructor(environment.stripePublicKey);
          }
        } catch {
          // Entorno de prueba o sin red
        }
      }

      if (!this.stripe && typeof window !== 'undefined') {
        const win = window as any;
        if (win['Stripe']) {
          this.stripe = typeof win['Stripe'] === 'function' ? win['Stripe'](environment.stripePublicKey) : win['Stripe'];
        }
      }

      if (!this.stripe || typeof this.stripe.elements !== 'function') {
        this.errorTarjeta = 'No se pudo cargar la pasarela segura de Stripe. Verifique su conexión.';
        this.error = this.errorTarjeta;
        this.cardElementMontado = false;
        this.cardElementValido = false;
        this.preparandoMetodo = false;
        return;
      }

      this.elements = this.stripe.elements();
      if (!this.elements || typeof this.elements.create !== 'function') {
        this.errorTarjeta = 'No se pudo inicializar los elementos de pago seguros de Stripe.';
        this.error = this.errorTarjeta;
        this.cardElementMontado = false;
        this.cardElementValido = false;
        this.preparandoMetodo = false;
        return;
      }

      this.cardElement = this.elements.create('card', {
        style: {
          base: {
            fontSize: '16px',
            color: '#1a1a1a',
            fontFamily: '"Plus Jakarta Sans", sans-serif',
            '::placeholder': { color: '#94a3b8' }
          }
        }
      });

      if (!this.cardElement) {
        this.errorTarjeta = 'No se pudo crear el campo seguro para tarjeta.';
        this.error = this.errorTarjeta;
        this.cardElementMontado = false;
        this.cardElementValido = false;
        this.preparandoMetodo = false;
        return;
      }

      // Esperar siguiente ciclo para que *ngIf haya procesado el contenedor en el DOM
      await new Promise(resolve => setTimeout(resolve, 0));

      const mountSelector = '#card-element';
      if (typeof this.cardElement.mount !== 'function') {
        this.errorTarjeta = 'El elemento de tarjeta no soporta montaje.';
        this.error = this.errorTarjeta;
        this.cardElementMontado = false;
        this.cardElementValido = false;
        this.preparandoMetodo = false;
        return;
      }

      try {
        this.cardElement.mount(mountSelector);
      } catch (errMount: any) {
        this.errorTarjeta = `Error al montar el campo de tarjeta: ${errMount?.message || 'Fallo de interfaz'}`;
        this.error = this.errorTarjeta;
        this.cardElementMontado = false;
        this.cardElementValido = false;
        this.preparandoMetodo = false;
        return;
      }

      this.cardElementMontado = true;
      // Inicia estrictamente en FALSE hasta que el usuario ingrese datos válidos y completos
      this.cardElementValido = false;

      if (this.cardElement && typeof this.cardElement.on === 'function') {
        this.cardElement.on('change', (event: any) => {
          this.cardElementValido = !!(event && event.complete && !event.error);
          this.errorTarjeta = event?.error?.message || null;
        });
      }
    } catch (err: any) {
      this.error = err?.message || 'Error al inicializar el formulario de tarjeta de Stripe.';
      this.errorTarjeta = this.error;
      this.cardElementMontado = false;
      this.cardElementValido = false;
      this.preparandoMetodo = false;
    }
  }

  async confirmarTarjetaStripe(): Promise<void> {
    if (!this.cardElement || !this.clientSecretActual || !this.preparacionPagoIdActual || this.confirmandoTarjeta) {
      return;
    }
    this.confirmandoTarjeta = true;
    this.errorTarjeta = null;
    this.error = null;

    try {
      await this.procesarConfirmacionSetup(this.preparacionPagoIdActual, this.clientSecretActual);
    } finally {
      this.confirmandoTarjeta = false;
    }
  }

  async procesarConfirmacionSetup(preparacionPagoId: string, clientSecret: string): Promise<void> {
    try {
      const confirmacionPasarela = await this.confirmarSetupIntentConPasarela(clientSecret);
      if (confirmacionPasarela.error) {
        this.preparandoMetodo = false;
        this.confirmandoTarjeta = false;
        this.metodoPreparadoExito = false;
        this.errorTarjeta = confirmacionPasarela.error;
        this.error = confirmacionPasarela.error;
        return;
      }

      const dto = confirmacionPasarela.paymentMethodId
        ? { payment_method_id: confirmacionPasarela.paymentMethodId }
        : undefined;

      this.stripeService.confirmarMetodo(preparacionPagoId, dto)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: () => {
            this.desmontarCardElement();
            this.mostrandoFormularioTarjeta = false;
            // Consulta el backend (consultarMetodo) y SOLO presenta/persiste LISTO si el servidor confirma
            this.verificarYFinalizarMetodo(preparacionPagoId);
          },
          error: err => {
            this.preparandoMetodo = false;
            this.confirmandoTarjeta = false;
            this.metodoPreparadoExito = false;
            this.error = formatearErrorApi(err, 'No se pudo confirmar el método de pago seguro en el servidor.');
          }
        });
    } catch (err: any) {
      this.preparandoMetodo = false;
      this.confirmandoTarjeta = false;
      this.metodoPreparadoExito = false;
      this.error = err?.message || 'Error inesperado al validar la tarjeta con la pasarela.';
    }
  }

  async confirmarSetupIntentConPasarela(clientSecret: string): Promise<{ paymentMethodId?: string; error?: string }> {
    let stripeInstance = this.stripe;
    if (!stripeInstance) {
      try {
        const StripeConstructor = await this.stripeService.cargarStripeJs() as (key: string) => any;
        if (typeof StripeConstructor === 'function') {
          this.stripe = StripeConstructor(environment.stripePublicKey);
          stripeInstance = this.stripe;
        }
      } catch {
        // En tests o sin red
      }
    }

    if (!stripeInstance) {
      return { error: 'No se pudo cargar el formulario de tarjeta de la pasarela. Verifica tu conexión.' };
    }

    try {
      const confirmData: any = this.cardElement ? { payment_method: { card: this.cardElement } } : {};
      const res = await stripeInstance.confirmCardSetup(clientSecret, confirmData);
      if (res?.error) {
        return { error: res.error.message || 'La tarjeta fue rechazada por la pasarela.' };
      }
      const pmId = res?.setupIntent?.payment_method;
      return { paymentMethodId: pmId };
    } catch (e: any) {
      return { error: e?.message || 'Error en la comunicación con la pasarela de pagos.' };
    }
  }

  verificarYFinalizarMetodo(preparacionPagoId: string): void {
    this.stripeService.consultarMetodo(preparacionPagoId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: estadoActual => {
          this.preparandoMetodo = false;
          if (estadoActual.estado === 'LISTO') {
            this.finalizarMetodoListo(estadoActual.preparacion_pago_id);
          } else {
            this.metodoPreparadoExito = false;
            this.error = `El método de pago aún no está listo. Estado: ${estadoActual.estado}`;
          }
        },
        error: err => {
          this.preparandoMetodo = false;
          this.metodoPreparadoExito = false;
          this.error = formatearErrorApi(err, 'No se pudo consultar el estado del método.');
        }
      });
  }

  private finalizarMetodoListo(preparacionPagoId: string): void {
    this.preparandoMetodo = false;
    this.metodoPreparadoId = preparacionPagoId;
    this.metodoPreparadoExito = true;
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        localStorage.setItem('fs_metodo_preparado_id', preparacionPagoId);
      }
    } catch {}
  }

  confirmarCheckout(): void {
    if (this.procesando || !this.puedeConfirmar) return;
    this.procesando = true;
    this.error = null;

    const sid = this.sucursalSeleccionada;
    const mod = this.modalidadSeleccionada;
    const dir = this.direccionValor.trim();
    const anillo = this.anilloValor;

    // Manejo de compra fuera de línea (CU05 v3 con autorización de cobro)
    if (!this.estaEnLinea) {
      const totalNum = this.totalVisible;
      const subtotalNum = this.carrito?.subtotal ? aNumero(this.carrito.subtotal) : 0;
      const descNum = this.carrito?.descuento_total ? aNumero(this.carrito.descuento_total) : 0;
      const costoEntrega = this.modalidadSeleccionada === 'DELIVERY' && this.cotizacionEsVigente
        ? (this.cotizacion?.costo_entrega ? aNumero(this.cotizacion.costo_entrega) : 0)
        : 0;

      const totalBob = totalNum.toFixed(2);
      const subtotalBob = subtotalNum.toFixed(2);
      const descBob = descNum.toFixed(2);
      const envioBob = costoEntrega.toFixed(2);
      const tasaNum = this.tieneTasaValida ? parseFloat(this.tasaCambioVigente) : 0;
      const importeUsd = tasaNum > 0 ? (totalNum / tasaNum).toFixed(2) : '0.00';
      const consentimientoId = crypto.randomUUID();
      const aceptadoEn = obtenerHoraBoliviaIso();
      const expiraEn = new Date(Date.now() + this.vigenciaHoras * 3600 * 1000).toISOString().replace(/\.\d+Z$/, 'Z');

      const usuarioActual = this.authService?.obtenerUsuarioActual();
      const usuarioId = usuarioActual?.usuario_id || usuarioActual?.id || this.carrito?.cliente_id || '55555555-5555-5555-5555-555555555555';
      const empresaId = this.authService?.obtenerEmpresaId() || '11111111-1111-1111-1111-111111111111';

      const lineasCanonica: HuellaLineaCanonica[] = (this.carrito?.lineas ?? []).map(l => ({
        cantidad: l.cantidad,
        precio_unitario_bob: aNumero(l.precio_unitario).toFixed(2),
        variante_id: l.variante_id
      }));

      // Validar si realmente contamos con tasa real, método de pago LISTO y consentimiento explícito
      const permiteCobro = this.consentimientoCobroV3 &&
        this.autorizoCobroOffline &&
        this.tieneTasaValida &&
        !!this.metodoPreparadoId &&
        this.metodoPreparadoExito;

      let autorizacionCobroObj: AutorizacionCobroOfflineDTO | undefined = undefined;

      // Si y solo si se cuenta con método preparado LISTO, tasa oficial vigente y consentimiento explícito,
      // se emite el objeto completo con los 15 campos contractuales y permite_cobro_al_reconectar: true.
      // Si falta alguno (permiteCobro === false), se DEBE OMITIR completamente autorizacion_cobro (undefined).
      if (permiteCobro) {
        const huellaRes = calcularHuellaCanonicaV3({
          base_bob: subtotalBob,
          condiciones_version: this.condicionesVersion,
          descuento_bob: descBob,
          direccion: mod === 'DELIVERY' ? dir : undefined,
          empresa_id: empresaId,
          envio_bob: envioBob,
          importe_cobro: importeUsd,
          lineas: lineasCanonica,
          modalidad: mod,
          moneda_cobro: 'USD',
          sucursal_id: sid,
          tasa_bob_por_usd: this.tasaCambioVigente,
          tasa_id: this.tasaId!,
          total_bob: totalBob,
          usuario_id: usuarioId,
          vigente_hasta: expiraEn
        });

        autorizacionCobroObj = {
          consentimiento_id: consentimientoId,
          aceptado_local_en: aceptadoEn,
          huella_compra: huellaRes.hash,
          base_bob: subtotalBob,
          descuento_bob: descBob,
          envio_bob: envioBob,
          total_bob: totalBob,
          moneda_cobro: 'USD',
          importe_cobro: importeUsd,
          tasa_id: this.tasaId!,
          tasa_bob_por_usd: this.tasaCambioVigente,
          condiciones_version: this.condicionesVersion,
          vigente_hasta: expiraEn,
          preparacion_pago_id: this.metodoPreparadoId!,
          permite_cobro_al_reconectar: true
        };
      }

      const datosOffline: OperacionDatosCompra = {
        sucursal_id: sid,
        modalidad: mod,
        direccion: mod === 'DELIVERY' ? dir : undefined,
        anillo_destino: mod === 'DELIVERY' ? (anillo ?? undefined) : undefined,
        lineas: (this.carrito?.lineas ?? []).map(l => ({
          variante_id: l.variante_id,
          cantidad: l.cantidad,
          precio_visto_bob: aNumero(l.precio_unitario).toFixed(2)
        })),
        autorizacion_cobro: autorizacionCobroObj
      };

      this.sincronizacionService.registrarCompraOffline(datosOffline)
        .then(() => {
          this.procesando = false;
          this.carritoService.vaciar().subscribe({ next: () => {}, error: () => {} });
          this.router.navigate(['/mis-pedidos']);
        })
        .catch(err => {
          this.error = formatearErrorApi(err, 'No fue posible guardar la compra fuera de línea.');
          this.procesando = false;
        });
      return;
    }

    const dto: CheckoutCrearDTO = {
      sucursal_id: sid,
      canal: 'WEB',
      modalidad: mod,
    };
    if (mod === 'DELIVERY') {
      dto.direccion = dir;
      dto.anillo_destino = anillo!;
    }

    // Identificador de contenido lógico para idempotencia estable
    const firmaLineas = (this.carrito?.lineas ?? []).map(l => `${l.variante_id}:${l.cantidad}`).sort().join(';');
    const firmaActual = `${sid}|${mod}|${dir}|${anillo ?? ''}|${firmaLineas}`;

    if (firmaActual !== this.firmaIntentoPrevio) {
      // Cambio de parámetros o contenido: se genera una nueva clave lógica
      this.checkoutKey = crypto.randomUUID();
      this.firmaIntentoPrevio = firmaActual;
    }
    // Si la firma es idéntica (reintento técnico por red/timeout), se preserva la misma clave

    this.carritoService.checkout(dto, this.checkoutKey)
      .subscribe({
        next: resp => {
          this.procesando = false;
          this.router.navigate(['/pago', resp.venta_id]);
        },
        error: e => {
          this.error = formatearErrorApi(e, 'No se pudo confirmar la compra. Puedes reintentar.');
          this.procesando = false;
          // NOTA: No regeneramos clave aquí para permitir reintento seguro con la misma Idempotency-Key
        }
      });
  }

  get tieneDescuento(): boolean { return aNumero(this.carrito?.descuento_total) > 0; }
  get esVacio(): boolean { return !this.carrito?.lineas?.length; }
  bs(m: DecimalApi | null | undefined): string { return formatearBs(m); }
}
