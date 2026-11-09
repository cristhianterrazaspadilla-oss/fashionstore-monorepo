import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { PromocionDTO, PromocionCrearDTO, PromocionActualizarDTO, PromocionListaDTO, AsociarVariantesDTO } from '../models/gestion-catalogo.models';

@Injectable({ providedIn: 'root' })
export class PromocionService {
  private readonly api = environment.apiUrl;
  constructor(private http: HttpClient) {}

  listar(soloActivas = false, limit = 50, offset = 0): Observable<PromocionListaDTO> {
    const params = new HttpParams()
      .set('solo_activas', soloActivas.toString())
      .set('limit', limit.toString())
      .set('offset', offset.toString());
    return this.http.get<PromocionListaDTO>(`${this.api}/promociones`, { params });
  }

  obtener(id: string): Observable<PromocionDTO> {
    return this.http.get<PromocionDTO>(`${this.api}/promociones/${id}`);
  }

  crear(dto: PromocionCrearDTO): Observable<PromocionDTO> {
    return this.http.post<PromocionDTO>(`${this.api}/promociones`, dto);
  }

  actualizar(id: string, dto: PromocionActualizarDTO): Observable<PromocionDTO> {
    return this.http.patch<PromocionDTO>(`${this.api}/promociones/${id}`, dto);
  }

  eliminar(id: string): Observable<void> {
    return this.http.delete<void>(`${this.api}/promociones/${id}`);
  }

  asociarVariantes(promocionId: string, dto: AsociarVariantesDTO): Observable<PromocionDTO> {
    return this.http.post<PromocionDTO>(`${this.api}/promociones/${promocionId}/variantes`, dto);
  }

  desasociarVariante(promocionId: string, varianteId: string): Observable<PromocionDTO> {
    return this.http.delete<PromocionDTO>(`${this.api}/promociones/${promocionId}/variantes/${varianteId}`);
  }
}
