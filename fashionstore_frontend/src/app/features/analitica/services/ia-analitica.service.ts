import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, catchError, throwError } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  DecisionPedirDTO,
  DecisionRespuestaDTO,
  ReportePedirDTO,
  ReporteRespuestaDTO,
  ReporteInterpretadoPeticionDTO,
  ReporteInterpretadoResultadoDTO,
  PronosticoDemandaPeticionDTO,
  PronosticoDemandaResultadoDTO,
  SegmentacionProductosPeticionDTO,
  SegmentacionProductosResultadoDTO
} from '../models/analitica-ia.models';

@Injectable({ providedIn: 'root' })
export class IAAnaliticaService {
  private readonly api = environment.apiUrl;

  constructor(private http: HttpClient) {}

  // ========================================================
  // CU24: Reportes Tipados Interpretados (Gemini / Determinista)
  // ========================================================
  solicitarReporteInterpretado(dto: ReporteInterpretadoPeticionDTO): Observable<ReporteInterpretadoResultadoDTO> {
    return this.http.post<ReporteInterpretadoResultadoDTO>(
      `${this.api}/analitica/reportes-interpretados`,
      dto
    ).pipe(
      catchError(error => error.status === 404
        ? this.http.post<ReporteInterpretadoResultadoDTO>(
          `${this.api}/ia/reportes-interpretados`,
          dto
        ) : throwError(() => error)
      )
    );
  }

  // ========================================================
  // CU10: Pronóstico Supervisado de Demanda (Regresión y Baseline)
  // ========================================================
  consultarPronosticos(filtros: PronosticoDemandaPeticionDTO = {}): Observable<PronosticoDemandaResultadoDTO> {
    let params = new HttpParams();
    if (filtros.sucursal_id) params = params.set('sucursal', filtros.sucursal_id);
    if (filtros.producto_id) params = params.set('producto', filtros.producto_id);
    if (filtros.semanas_adelante) params = params.set('semanas', filtros.semanas_adelante.toString());
    if (filtros.origen_datos) params = params.set('origen_datos', filtros.origen_datos);
    if (filtros.semilla !== undefined) params = params.set('semilla', filtros.semilla.toString());

    return this.http.get<PronosticoDemandaResultadoDTO>(
      `${this.api}/analitica/pronosticos`,
      { params }
    );
  }

  entrenarSupervisado(dto: PronosticoDemandaPeticionDTO): Observable<PronosticoDemandaResultadoDTO> {
    return this.http.post<PronosticoDemandaResultadoDTO>(
      `${this.api}/analitica/entrenamientos/supervisado`,
      dto
    );
  }

  // ========================================================
  // CU11: Segmentación No Supervisada de Productos (K-Means)
  // ========================================================
  consultarSegmentacion(filtros: SegmentacionProductosPeticionDTO = {}): Observable<SegmentacionProductosResultadoDTO> {
    let params = new HttpParams();
    if (filtros.num_grupos) params = params.set('num_grupos', filtros.num_grupos.toString());
    if (filtros.periodo_dias) params = params.set('periodo_dias', filtros.periodo_dias.toString());
    if (filtros.origen_datos) params = params.set('origen_datos', filtros.origen_datos);
    if (filtros.semilla !== undefined) params = params.set('semilla', filtros.semilla.toString());

    return this.http.get<SegmentacionProductosResultadoDTO>(
      `${this.api}/analitica/grupos-productos`,
      { params }
    );
  }

  entrenarNoSupervisado(dto: SegmentacionProductosPeticionDTO): Observable<SegmentacionProductosResultadoDTO> {
    return this.http.post<SegmentacionProductosResultadoDTO>(
      `${this.api}/analitica/entrenamientos/no-supervisado`,
      dto
    );
  }

  // ========================================================
  // Compatibilidad legada Ciclo 3
  // ========================================================
  generarReporte(consulta: string): Observable<ReporteRespuestaDTO> {
    const dto: ReportePedirDTO = { consulta };
    return this.http.post<ReporteRespuestaDTO>(`${this.api}/analitica/reportes`, dto).pipe(
      catchError(error => error.status === 404
        ? this.http.post<ReporteRespuestaDTO>(`${this.api}/ia/reportes`, dto)
        : throwError(() => error))
    );
  }

  decisionesInventario(dto: DecisionPedirDTO = {}): Observable<DecisionRespuestaDTO> {
    return this.http.post<DecisionRespuestaDTO>(`${this.api}/analitica/decisiones-inventario`, dto).pipe(
      catchError(error => error.status === 404
        ? this.http.post<DecisionRespuestaDTO>(`${this.api}/ia/decisiones-inventario`, dto)
        : throwError(() => error))
    );
  }
}
