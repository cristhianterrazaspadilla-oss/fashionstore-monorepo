import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { CotizacionDTO, FiltrosPedidoDTO, PedidoDTO, PedidoListaDTO, TransicionPedidoDTO } from '../models/venta-digital.models';

@Injectable({ providedIn: 'root' })
export class EntregaService {
  private readonly api = environment.apiUrl;
  constructor(private http: HttpClient) {}

  cotizar(sucursalId: string, anilloDestino: number): Observable<CotizacionDTO> {
    const params = new HttpParams()
      .set('sucursal_id', sucursalId)
      .set('anillo_destino', anilloDestino.toString());
    return this.http.get<CotizacionDTO>(`${this.api}/entregas/cotizacion`, { params });
  }

  misPedidos(limit = 50, offset = 0): Observable<PedidoListaDTO> {
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<PedidoListaDTO>(`${this.api}/entregas/mis-pedidos`, { params });
  }

  cola(filtros: FiltrosPedidoDTO = {}): Observable<PedidoListaDTO> {
    let params = new HttpParams();
    if (filtros.sucursal_id) params = params.set('sucursal_id', filtros.sucursal_id);
    if (filtros.estado) params = params.set('estado', filtros.estado);
    params = params.set('limit', (filtros.limit ?? 50).toString());
    params = params.set('offset', (filtros.offset ?? 0).toString());
    return this.http.get<PedidoListaDTO>(`${this.api}/entregas/cola`, { params });
  }

  obtener(pedidoId: string): Observable<PedidoDTO> {
    return this.http.get<PedidoDTO>(`${this.api}/entregas/${pedidoId}`);
  }

  transicionar(pedidoId: string, estado: TransicionPedidoDTO['estado']): Observable<PedidoDTO> {
    const dto: TransicionPedidoDTO = { estado };
    return this.http.patch<PedidoDTO>(`${this.api}/entregas/${pedidoId}/estado`, dto);
  }

  cancelar(pedidoId: string): Observable<PedidoDTO> {
    return this.http.post<PedidoDTO>(`${this.api}/entregas/${pedidoId}/cancelar`, {});
  }
}
