import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { SaldoResumenDTO, AplicarSaldoDTO, SaldoAplicadoDTO } from '../models/saldo.models';

@Injectable({ providedIn: 'root' })
export class SaldoService {
  private readonly api = environment.apiUrl;

  constructor(private http: HttpClient) {}

  obtenerMiSaldo(): Observable<SaldoResumenDTO> {
    return this.http.get<SaldoResumenDTO>(`${this.api}/saldos/mio`);
  }

  aplicarSaldoAVenta(
    ventaId: string,
    dto: AplicarSaldoDTO,
    idempotencyKey?: string
  ): Observable<SaldoAplicadoDTO> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.http.post<SaldoAplicadoDTO>(
      `${this.api}/ventas/${ventaId}/aplicar-saldo`,
      dto,
      { headers: new HttpHeaders({ 'Idempotency-Key': key }) }
    );
  }

  aplicarSaldoACompra(
    pedidoId: string,
    dto: AplicarSaldoDTO,
    idempotencyKey?: string
  ): Observable<SaldoAplicadoDTO> {
    const key = idempotencyKey || crypto.randomUUID();
    return this.http.post<SaldoAplicadoDTO>(
      `${this.api}/compras/${pedidoId}/aplicar-saldo`,
      dto,
      { headers: new HttpHeaders({ 'Idempotency-Key': key }) }
    );
  }
}
