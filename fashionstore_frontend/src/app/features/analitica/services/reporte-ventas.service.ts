import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, catchError } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { parametrosHttp } from '../../../core/utils/solicitud-http.util';
import { ReporteVentas } from '../models/reporte-ventas.models';

@Injectable({ providedIn: 'root' })
export class ReporteVentasService {
  private readonly api = environment.apiUrl;

  constructor(private http: HttpClient) {}

  reporteVentas(sucursal: string, filtros: Record<string, unknown> = {}): Observable<ReporteVentas> {
    const params = parametrosHttp({ sucursal, ...filtros });

    // Endpoint canónico E2: /analitica/ventas-sucursal con fallback a /analitica/reportes/ventas-sucursal o /reportes/ventas-sucursal
    return this.http.get<ReporteVentas>(`${this.api}/analitica/ventas-sucursal`, { params }).pipe(
      catchError(() =>
        this.http.get<ReporteVentas>(`${this.api}/analitica/reportes/ventas-sucursal`, { params }).pipe(
          catchError(() =>
            this.http.get<ReporteVentas>(`${this.api}/reportes/ventas-sucursal`, { params })
          )
        )
      )
    );
  }
}
