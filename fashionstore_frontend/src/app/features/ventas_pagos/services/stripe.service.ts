import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  IntencionDTO,
  EstadoPagoDTO,
  MetodoPrepararDTO,
  MetodoPreparadoDTO,
  OrdenPagoCrearDTO,
  OrdenPagoDTO,
  ContinuarAccionDTO
} from '../models/venta-digital.models';
import { IniciarVentaPresencialStripeRespuestaDTO, OrdenActivaCajaDTO } from '../models/venta-presencial.models';

@Injectable({ providedIn: 'root' })
export class StripeService {
  private readonly api = environment.apiUrl;
  constructor(private http: HttpClient) {}

  crearIntencion(ventaId: string, idempotencyKey: string): Observable<IntencionDTO> {
    return this.http.post<IntencionDTO>(
      `${this.api}/pagos/stripe/intenciones`,
      { venta_id: ventaId },
      { headers: new HttpHeaders({ 'Idempotency-Key': idempotencyKey }) }
    );
  }

  reintentar(ventaId: string, idempotencyKey: string): Observable<IntencionDTO> {
    return this.http.post<IntencionDTO>(
      `${this.api}/pagos/stripe/intenciones/reintento`,
      { venta_id: ventaId },
      { headers: new HttpHeaders({ 'Idempotency-Key': idempotencyKey }) }
    );
  }

  consultarEstado(ventaId: string): Observable<EstadoPagoDTO> {
    return this.http.get<EstadoPagoDTO>(`${this.api}/pagos/stripe/estado/${ventaId}`);
  }

  prepararMetodo(dto?: MetodoPrepararDTO, idempotencyKey?: string): Observable<MetodoPreparadoDTO> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.http.post<MetodoPreparadoDTO>(
      `${this.api}/pagos/stripe/metodos/preparar`,
      dto || {},
      { headers: new HttpHeaders({ 'Idempotency-Key': key }) }
    );
  }

  consultarMetodo(preparacionPagoId: string): Observable<MetodoPreparadoDTO> {
    return this.http.get<MetodoPreparadoDTO>(
      `${this.api}/pagos/stripe/metodos/${preparacionPagoId}`
    );
  }

  confirmarMetodo(
    preparacionPagoId: string,
    dto?: { payment_method_id?: string }
  ): Observable<MetodoPreparadoDTO> {
    return this.http.post<MetodoPreparadoDTO>(
      `${this.api}/pagos/stripe/metodos/${preparacionPagoId}/confirmar`,
      dto || {}
    );
  }

  crearOrdenPago(dto: OrdenPagoCrearDTO, idempotencyKey?: string): Observable<OrdenPagoDTO> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.http.post<OrdenPagoDTO>(
      `${this.api}/pagos/stripe/ordenes`,
      dto,
      { headers: new HttpHeaders({ 'Idempotency-Key': key }) }
    );
  }

  continuarAccion(
    ordenPagoId: string,
    dto: ContinuarAccionDTO,
    idempotencyKey?: string
  ): Observable<OrdenPagoDTO> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.http.post<OrdenPagoDTO>(
      `${this.api}/pagos/stripe/ordenes/${ordenPagoId}/continuar-accion`,
      dto,
      { headers: new HttpHeaders({ 'Idempotency-Key': key }) }
    );
  }

  consultarOrdenPago(ordenPagoId: string): Observable<OrdenPagoDTO> {
    return this.http.get<OrdenPagoDTO>(`${this.api}/pagos/stripe/ordenes/${ordenPagoId}`);
  }

  confirmarOrdenPago(ordenPagoId: string): Observable<OrdenPagoDTO> {
    return this.http.post<OrdenPagoDTO>(
      `${this.api}/pagos/stripe/ordenes/${ordenPagoId}/confirmar`,
      {}
    );
  }

  cancelarOrdenPago(ordenPagoId: string): Observable<OrdenPagoDTO> {
    return this.http.post<OrdenPagoDTO>(
      `${this.api}/pagos/stripe/ordenes/${ordenPagoId}/cancelar`,
      {}
    );
  }

  /**
   * Reanuda una orden de pago provisional generada tras fallo en la segunda transacción de inicio Stripe.
   * Invoca de forma idempotente la creación o reutilización del PaymentIntent en la pasarela.
   */
  reanudarOrdenPago(ordenPagoId: string): Observable<OrdenPagoDTO> {
    return this.http.post<OrdenPagoDTO>(
      `${this.api}/pagos/stripe/ordenes/${ordenPagoId}/reanudar`,
      {}
    );
  }

  /**
   * Recupera la orden de pago activa (PENDIENTE o CAPTURADA) para la caja/sucursal
   * tras una recarga (F5) o reconexión de red sin persistir client_secret localmente.
   */
  obtenerOrdenActivaCaja(
    sucursalId?: string,
    turnoCajaId?: string
  ): Observable<OrdenActivaCajaDTO | null> {
    const params: Record<string, string> = {};
    if (sucursalId) params['sucursal_id'] = sucursalId;
    if (turnoCajaId) params['turno_caja_id'] = turnoCajaId;
    return this.http.get<OrdenActivaCajaDTO | null>(
      `${this.api}/pagos/stripe/ordenes/activa-caja`,
      { params }
    );
  }

  /**
   * Carga Stripe.js de forma dinámica.
   * Retorna el objeto Stripe global.
   */
  cargarStripeJs(): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const win = window as unknown as Record<string, unknown>;
      if (win['Stripe']) {
        resolve(win['Stripe']);
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://js.stripe.com/v3/';
      script.async = true;
      script.onload = () => resolve((window as unknown as Record<string, unknown>)['Stripe']);
      script.onerror = () => reject(new Error('No se pudo cargar Stripe.js'));
      document.head.appendChild(script);
    });
  }
}
