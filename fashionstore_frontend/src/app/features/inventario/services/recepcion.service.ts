import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { ProveedorDTO, ProveedorCrearDTO, LoteRecepcionDTO, LoteRecepcionCrearDTO } from '../models/recepcion.models';

@Injectable({ providedIn: 'root' })
export class RecepcionService {
  private api = environment.apiUrl;
  constructor(private http: HttpClient) {}

  // Gestión de proveedores
  gestionarProveedores(soloActivos = false): Observable<ProveedorDTO[]> {
    let p = new HttpParams();
    if (soloActivos) p = p.set('solo_activos', 'true');
    return this.http.get<ProveedorDTO[]>(`${this.api}/proveedores`, { params: p });
  }

  registrarProveedor(dto: ProveedorCrearDTO): Observable<ProveedorDTO> {
    return this.http.post<ProveedorDTO>(`${this.api}/proveedores`, dto);
  }

  // Registro de recepción
  registrarLoteRecepcion(dto: LoteRecepcionCrearDTO): Observable<LoteRecepcionDTO> {
    return this.http.post<LoteRecepcionDTO>(`${this.api}/recepciones`, dto);
  }

  listarLotes(limit = 50, offset = 0): Observable<LoteRecepcionDTO[]> {
    const p = new HttpParams().set('limit', limit).set('offset', offset);
    return this.http.get<LoteRecepcionDTO[]>(`${this.api}/recepciones`, { params: p });
  }

  obtenerLote(id: string): Observable<LoteRecepcionDTO> {
    return this.http.get<LoteRecepcionDTO>(`${this.api}/recepciones/${id}`);
  }
}
