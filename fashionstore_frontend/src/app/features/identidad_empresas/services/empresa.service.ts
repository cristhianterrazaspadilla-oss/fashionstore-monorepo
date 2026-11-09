import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  EmpresaCrearDTO,
  EmpresaRespuestaDTO,
  EmpresaDetalleDTO
} from '../models/empresa.models';

@Injectable({
  providedIn: 'root'
})
export class EmpresaService {
  private apiUrl = `${environment.apiUrl}`;

  constructor(private http: HttpClient) {}

  /**
   * Registrar una nueva empresa contratante con su administrador inicial (atómico).
   * Requiere clave de idempotencia obligatoria UUID para reintentos seguros.
   */
  crearEmpresa(datos: EmpresaCrearDTO, idempotencyKey: string): Observable<EmpresaRespuestaDTO> {
    const headers = new HttpHeaders().set('Idempotency-Key', idempotencyKey);
    return this.http.post<EmpresaRespuestaDTO>(`${this.apiUrl}/empresas`, datos, { headers });
  }

  /**
   * Obtener detalle de una empresa por su identificador.
   */
  obtenerEmpresa(empresaId: string): Observable<EmpresaDetalleDTO> {
    return this.http.get<EmpresaDetalleDTO>(`${this.apiUrl}/empresas/${empresaId}`);
  }

  /**
   * Listar empresas contratantes registradas en el sistema.
   */
  listarEmpresas(soloActivas = false): Observable<EmpresaDetalleDTO[]> {
    let params = new HttpParams();
    if (soloActivas) {
      params = params.set('solo_activas', 'true');
    }
    return this.http.get<EmpresaDetalleDTO[]>(`${this.apiUrl}/empresas`, { params });
  }
}
