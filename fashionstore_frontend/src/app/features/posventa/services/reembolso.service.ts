import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  ReembolsoSolicitudDTO,
  ReembolsoDetalleDTO,
  ReembolsoAutorizarDTO,
  ReembolsoEjecutarDTO
} from '../models/reembolso.models';

@Injectable({ providedIn: 'root' })
export class ReembolsoService {
  private readonly api = environment.apiUrl;

  constructor(private http: HttpClient) {}

  private idemHeaders(key?: string): { headers: HttpHeaders } {
    return {
      headers: new HttpHeaders({
        'Idempotency-Key': key || crypto.randomUUID()
      })
    };
  }

  solicitar(dto: ReembolsoSolicitudDTO, idempotencyKey?: string): Observable<ReembolsoDetalleDTO> {
    return this.http.post<ReembolsoDetalleDTO>(
      `${this.api}/reembolsos`,
      dto,
      this.idemHeaders(idempotencyKey)
    );
  }

  consultar(reembolsoId: string): Observable<ReembolsoDetalleDTO> {
    return this.http.get<ReembolsoDetalleDTO>(`${this.api}/reembolsos/${reembolsoId}`);
  }

  listar(): Observable<ReembolsoDetalleDTO[]> {
    return this.http.get<ReembolsoDetalleDTO[]>(`${this.api}/reembolsos`);
  }

  autorizar(
    reembolsoId: string,
    dto?: ReembolsoAutorizarDTO,
    idempotencyKey?: string
  ): Observable<ReembolsoDetalleDTO> {
    return this.http.post<ReembolsoDetalleDTO>(
      `${this.api}/reembolsos/${reembolsoId}/autorizar`,
      dto || {},
      this.idemHeaders(idempotencyKey)
    );
  }

  ejecutar(
    reembolsoId: string,
    dto?: ReembolsoEjecutarDTO,
    idempotencyKey?: string
  ): Observable<ReembolsoDetalleDTO> {
    return this.http.post<ReembolsoDetalleDTO>(
      `${this.api}/reembolsos/${reembolsoId}/ejecutar`,
      dto || {},
      this.idemHeaders(idempotencyKey)
    );
  }

  conciliar(reembolsoId: string, idempotencyKey?: string): Observable<ReembolsoDetalleDTO> {
    return this.http.post<ReembolsoDetalleDTO>(
      `${this.api}/reembolsos/${reembolsoId}/conciliar`,
      {},
      this.idemHeaders(idempotencyKey)
    );
  }
}
