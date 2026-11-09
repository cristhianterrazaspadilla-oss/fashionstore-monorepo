import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { cabeceraIdempotencia, parametrosHttp } from '../../../core/utils/solicitud-http.util';
import { Pagina } from '../../../core/models/comunes.models';
import {
  Comprobante,
  MetodoCaja,
  Pago,
  Venta,
  VentaCrear,
  VentaPresencialLiquidarDTO,
  VentaLiquidadaDTO,
  IniciarVentaPresencialStripeDTO,
  IniciarVentaPresencialStripeRespuestaDTO
} from '../models/venta-presencial.models';

@Injectable({ providedIn: 'root' })
export class VentaPresencialService {
  private readonly api = environment.apiUrl;
  constructor(private http: HttpClient) {}

  iniciarVentaPresencialStripe(
    dto: IniciarVentaPresencialStripeDTO,
    idempotencyKey?: string
  ): Observable<IniciarVentaPresencialStripeRespuestaDTO> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.http.post<IniciarVentaPresencialStripeRespuestaDTO>(
      `${this.api}/ventas/presenciales/iniciar-stripe`,
      dto,
      { headers: new HttpHeaders({ 'Idempotency-Key': key }) }
    );
  }

  registrarAdelanto(reserva_id: string, metodo: MetodoCaja): Observable<Pago> {
    return this.http.post<Pago>(`${this.api}/pagos/adelantos`, { reserva_id, metodo }, { headers: cabeceraIdempotencia() });
  }

  registrarVenta(dto: VentaCrear): Observable<Venta> {
    return this.http.post<Venta>(`${this.api}/ventas/presenciales`, dto, { headers: cabeceraIdempotencia() });
  }

  liquidarVentaPresencial(dto: VentaPresencialLiquidarDTO, idempotencyKey?: string): Observable<VentaLiquidadaDTO> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.http.post<VentaLiquidadaDTO>(
      `${this.api}/ventas/presenciales/liquidar`,
      dto,
      { headers: new HttpHeaders({ 'Idempotency-Key': key }) }
    );
  }

  comprobante(id: string): Observable<Comprobante> {
    return this.http.get<Comprobante>(`${this.api}/ventas/${id}/comprobante`);
  }

  historial(clienteId: string, filtros: Record<string, unknown> = {}): Observable<Pagina<Venta>> {
    return this.http.get<Pagina<Venta>>(`${this.api}/clientes/${clienteId}/compras`, { params: parametrosHttp(filtros) });
  }
}
