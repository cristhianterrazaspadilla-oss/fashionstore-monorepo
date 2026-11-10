import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, catchError, throwError } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { DashboardDTO } from '../models/analitica-ia.models';

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly api = environment.apiUrl;

  constructor(private http: HttpClient) {}

  consultar(filtros: { desde?: string; hasta?: string; sucursal_id?: string } = {}): Observable<DashboardDTO> {
    let params = new HttpParams();
    if (filtros.desde) params = params.set('desde', filtros.desde);
    if (filtros.hasta) params = params.set('hasta', filtros.hasta);
    if (filtros.sucursal_id) params = params.set('sucursal', filtros.sucursal_id);

    // Endpoint canónico E2: /analitica/dashboard con fallback a /analitica/dashboard/indicadores o /reportes/dashboard
    return this.http.get<DashboardDTO>(`${this.api}/analitica/dashboard`, { params }).pipe(
      catchError(error => error.status === 404
        ? this.http.get<DashboardDTO>(`${this.api}/reportes/dashboard`, { params })
        : throwError(() => error)
      )
    );
  }
}
